"""The agent harness — the bounded loop every model call goes through.

This is the *only* place the pipeline is orchestrated, and it is deliberately
boring. What it enforces:

    rule 4   the validation gate runs first; nothing scores an invalid record
    rule 8   the LLM going away degrades the run to rules-only `advisory`,
             it does not fail the run
    rule 9   max 8 tool calls, 1 reflection, 20s wall clock; a breach hands to
             a human WITH what was gathered rather than discarding it
    rule 6   the span filter runs after scoring, before the router
    rule 5   the router decides; nothing else does
    rule 2   the LLM writes prose onto findings that already exist. It never
             creates, removes or rescores one.

`run_pipeline(episode, claim, day)` is the whole product. Concurrent monitoring
is this function called once per day plus a diff — never a second system.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from vitera.agent.boundary import LLMClient, pseudonymise
from vitera.agent.router import Router, filter_spans
from vitera.contracts import (
    Flag,
    GroupResult,
    LoopBudget,
    PipelineResult,
    ToolCall,
    Trace,
    ValidationFailure,
    Verdict,
)
from vitera.grouper.grouper import Grouper
from vitera.rules.engine import RuleContext, check, validate


class Scorer(Protocol):
    """The cross-encoder, or anything shaped like it. Bucket 8 supplies one."""

    def score(self, ctx: RuleContext) -> Sequence[Flag]: ...


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    fn: Callable[[RuleContext], Sequence[Flag]]


class BoundedRunner:
    """Runs tools under a budget, recording every call.

    The budget is checked BEFORE each call, so a breach never leaves a
    half-finished tool result in the trace.
    """

    def __init__(self, budget: LoopBudget) -> None:
        self.budget = budget
        self.calls: list[ToolCall] = []
        self.breach: str | None = None
        self._t0 = time.monotonic()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._t0

    def run(self, tools: Sequence[Tool], ctx: RuleContext) -> list[Flag]:
        out: list[Flag] = []
        for tool in tools:
            breach = self.budget.exceeded(len(self.calls) + 1, 0, self.elapsed)
            if breach:
                self.breach = breach
                break
            t0 = time.monotonic()
            try:
                flags = list(tool.fn(ctx))
            except Exception as exc:  # a failing tool must not kill the run
                flags = []
                self.calls.append(
                    ToolCall(
                        tool.name,
                        {},
                        f"error: {type(exc).__name__}",
                        time.monotonic() - t0,
                    )
                )
                continue
            out.extend(flags)
            self.calls.append(
                ToolCall(
                    tool.name,
                    {"day": ctx.day},
                    f"{len(flags)} flags",
                    round(time.monotonic() - t0, 4),
                )
            )
        return out


def _explain(flags: Sequence[Flag], llm: LLMClient | None) -> tuple[list[Flag], int]:
    """Ask the LLM to write the rationale prose. Rule 2: it explains findings
    that already exist and may not change, add or remove one.

    Returns (flags, llm_calls). Any failure leaves the deterministic rationale
    in place — prose is a nicety, the finding is the product.
    """
    if llm is None:
        return list(flags), 0
    out: list[Flag] = []
    n = 0
    for f in flags:
        try:
            prompt = pseudonymise(
                "Jelaskan dalam satu kalimat, untuk koder klinis, mengapa temuan "
                f"berikut perlu ditindaklanjuti.\nTemuan: {f.defect_class.label}\n"
                f"Kutipan rekam medis: {f.span.text}\n"
                f"Catatan sistem: {f.rationale}"
            )
            c = llm.complete(prompt, max_tokens=120)
            n += 1
            # Only the prose changes. class, remedy, span and score are frozen.
            out.append(replace(f, rationale=c.text.strip() or f.rationale))
        except Exception:
            out.append(f)
    return out, n


def run_pipeline(
    ctx: RuleContext,
    *,
    scorer: Scorer | None = None,
    llm: LLMClient | None = None,
    router: Router | None = None,
    grouper: Grouper | None = None,
    budget: LoopBudget | None = None,
) -> PipelineResult:
    """The whole product, for one episode on one day.

    Running this at `day = discharge_day` reproduces the discharge-time product
    exactly. The sweep calls it once per day and diffs the results.
    """
    from vitera import config

    t = config.thresholds()["budget"]
    budget = budget or LoopBudget(
        max_tool_calls=int(t["max_tool_calls"]),
        max_reflections=int(t["max_reflections"]),
        wall_clock_seconds=float(t["wall_clock_seconds"]),
    )
    router = router or Router()
    grouper = grouper or Grouper()
    runner = BoundedRunner(budget)

    # --- rule 4: gate first, always -------------------------------------
    validated, failures = validate(ctx)
    if validated is None:
        # Still label the model layer honestly. A record handed back at the
        # gate was scored by nothing at all, so a run without a scorer must not
        # come back looking like a full check (rule 8).
        return PipelineResult(
            episode_id=ctx.episode.episode_id,
            day=ctx.day,
            decision=router.decide((), GroupResult(None, None, None, "gagal validasi")),
            grouping=GroupResult(None, None, None, "gagal validasi"),
            validation_failures=failures,
            trace=Trace(
                ctx.episode.episode_id,
                ctx.day,
                (),
                0,
                None,
                scorer is None,
                runner.elapsed,
            ),
        )

    # --- tools: rules always, scorer when the model layer is up ----------
    tools = [Tool("rules", lambda c: check(c))]
    degraded = scorer is None
    if scorer is not None:

        def _score(c: RuleContext) -> Sequence[Flag]:
            return scorer.score(c)

        tools.append(Tool("cross_encoder", _score))

    flags = runner.run(tools, ctx)

    # --- rule 6: filter, not instruction ---------------------------------
    flags_t, dropped = filter_spans(flags, ctx.episode)

    # --- rule 2: the LLM writes prose, nothing else ----------------------
    explained, llm_calls = _explain(flags_t, llm)
    if llm is not None and llm_calls == 0 and explained:
        degraded = True  # every LLM call failed; say so rather than pretend

    grouping = grouper.group_codes(
        ctx.claim.primary_dx, ctx.claim.secondary_dx, ctx.claim.procedures
    )

    # --- rule 5: the router decides --------------------------------------
    decision = router.decide(explained, grouping, degraded=degraded)

    return PipelineResult(
        episode_id=ctx.episode.episode_id,
        day=ctx.day,
        decision=decision,
        grouping=grouping,
        validation_failures=(),
        trace=Trace(
            episode_id=ctx.episode.episode_id,
            day=ctx.day,
            tool_calls=tuple(runner.calls),
            llm_calls=llm_calls,
            budget_breach=runner.breach,
            degraded=degraded,
            elapsed_seconds=round(runner.elapsed, 4),
        ),
    )


def is_advisory(result: PipelineResult) -> bool:
    """Rules-only output must be labelled. A degraded run that renders as a
    full one is how a koder trusts a check that never happened."""
    return result.trace.degraded


__all__ = [
    "BoundedRunner",
    "Tool",
    "run_pipeline",
    "is_advisory",
    "Verdict",
    "ValidationFailure",
]
