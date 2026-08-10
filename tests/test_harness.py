"""Harness tests — bucket 7.

Every one of these maps to a hard architectural rule in the design brief. If a test
here fails, a claim in the paper is no longer true.
"""

from __future__ import annotations

import pytest

from vitera.agent import boundary
from vitera.agent.boundary import (
    CacheMiss,
    LLMClient,
    NullLLMClient,
    ReidentifiedTextError,
    pseudonymise,
)
from vitera.agent.loop import BoundedRunner, Tool, run_pipeline
from vitera.agent.router import Router, filter_spans
from vitera.contracts import (
    DefectClass,
    Flag,
    FlagSource,
    GroupResult,
    LoopBudget,
    Remedy,
    Span,
    Verdict,
)
from vitera.generator.defects import clean_claim, inject
from vitera.generator.episode import generate_corpus
from vitera.rules.engine import RuleContext

pytestmark = pytest.mark.filterwarnings(
    "ignore::vitera.generator.reference.UnverifiedReferenceWarning"
)


@pytest.fixture(scope="module")
def corpus() -> list:
    return generate_corpus(60, seed=20260731)


def _ctx(pair, day=None):
    ep, gt = pair
    return RuleContext(
        ep, clean_claim(ep, gt), day if day is not None else ep.discharge_day
    )


# --- rule 3: the LLM never sees re-identified data ------------------------


def test_pseudonymiser_strips_indonesian_identifiers() -> None:
    raw = (
        "Tn. Budi Santoso, NIK: 3174012345678901, No. RM: 00123456\n"
        "No. SEP: SEP000042, dirawat oleh dr. Siti Rahayu, telp 081234567890"
    )
    out = str(pseudonymise(raw))
    for leaked in ("Budi", "3174012345678901", "SEP000042", "081234567890", "Siti"):
        assert leaked not in out, f"{leaked} survived pseudonymisation"


def test_client_refuses_reidentified_text() -> None:
    """Belt and braces behind the type system: even if someone casts around
    the boundary, the client itself refuses."""
    c = LLMClient(mode="live")
    with pytest.raises(ReidentifiedTextError):
        c.complete("Pasien dengan NIK 3174012345678901")  # type: ignore[arg-type]


# --- the cache: reproducibility and demo safety --------------------------


def test_cache_mode_raises_on_miss_and_never_calls_out(tmp_path) -> None:
    """A demo that silently falls back to a live call is a demo that dies on
    stage with the wifi down."""
    c = LLMClient(cache_dir=tmp_path, mode="cache")
    with pytest.raises(CacheMiss):
        c.complete(pseudonymise("halo"))
    assert c.calls == 0


def test_recorded_completion_replays_byte_identically(tmp_path) -> None:
    key = LLMClient._key("prompt uji", 64)
    (tmp_path / f"{key}.json").write_text('{"text": "jawaban"}', encoding="utf-8")
    c = LLMClient(cache_dir=tmp_path, mode="cache")
    r1 = c.complete(pseudonymise("prompt uji"), max_tokens=64)
    r2 = c.complete(pseudonymise("prompt uji"), max_tokens=64)
    assert r1.text == r2.text == "jawaban"
    assert r1.from_cache and c.cache_hits == 2


# --- rule 9: bounded loops ------------------------------------------------


def test_runner_stops_at_the_tool_call_ceiling(corpus: list) -> None:
    runner = BoundedRunner(LoopBudget(max_tool_calls=3))
    tools = [Tool(f"t{i}", lambda c: []) for i in range(10)]
    runner.run(tools, _ctx(corpus[0]))
    assert len(runner.calls) == 3
    assert "max_tool_calls" in (runner.breach or "")


def test_breach_hands_over_what_was_gathered(corpus: list) -> None:
    """A breach must not discard work. The koder gets the partial result and
    the reason it stopped."""
    span = Span("resume_medis", 0, 6, "RESUME")
    flag = Flag(DefectClass.D3, Remedy.RECODE, span, 0.9, FlagSource.RULES)
    runner = BoundedRunner(LoopBudget(max_tool_calls=1))
    got = runner.run(
        [Tool("a", lambda c: [flag]), Tool("b", lambda c: [flag])], _ctx(corpus[0])
    )
    assert len(got) == 1
    assert runner.breach is not None


def test_a_failing_tool_does_not_kill_the_run(corpus: list) -> None:
    def boom(c):
        raise RuntimeError("tool exploded")

    runner = BoundedRunner(LoopBudget())
    runner.run([Tool("boom", boom), Tool("ok", lambda c: [])], _ctx(corpus[0]))
    assert len(runner.calls) == 2
    assert "error" in runner.calls[0].result_digest


# --- rule 6: the span filter is a filter, not an instruction --------------


def test_fabricated_spans_are_dropped(corpus: list) -> None:
    ep, _ = corpus[0]
    real = Span("resume_medis", 0, 6, "RESUME")
    fabricated = Span("resume_medis", 0, 20, "pasien meninggal dunia")
    ghost_doc = Span("dokumen_hantu", 0, 4, "asdf")
    flags = [
        Flag(DefectClass.D3, Remedy.RECODE, s, 0.9, FlagSource.CROSS_ENCODER)
        for s in (real, fabricated, ghost_doc)
    ]
    kept, dropped = filter_spans(flags, ep)
    assert len(kept) == 1 and dropped == 2
    assert kept[0].span is real


# --- rule 5 and 10: the router decides, and abstention is reachable -------


def test_router_abstains_in_the_grey_zone() -> None:
    """Rule 10 is about the mechanism, so the thresholds are supplied here
    rather than read from config.

    The deployed values currently coincide (`bands_crossed` — bucket 8), which
    empties the band for scores; abstention still reaches the koder through the
    ungroupable path below. Reading config here would make this test pass or
    fail on a calibration run rather than on the router's behaviour.
    """
    r = Router(
        thresholds={
            "router": {
                "t": {
                    "flag_at": 0.6,
                    "abstain_below": 0.4,
                    "max_flags_per_episode": 12,
                }
            },
            "severity": {"escalate_at": 0.75},
        },
        profile="t",
    )
    span = Span("resume_medis", 0, 6, "RESUME")
    mid = (r.abstain_below + r.flag_at) / 2
    d = r.decide(
        [Flag(DefectClass.D4, Remedy.QUERY, span, mid, FlagSource.CROSS_ENCODER)],
        GroupResult("A-4-14-I", 1, 3900000),
    )
    assert d.verdict is Verdict.ABSTAIN


def test_router_orders_by_closing_repair_window() -> None:
    """A QUERY needs the DPJP while the patient is on the ward; a RECODE
    survives until submission. Urgency is remedy-driven, not score-driven."""
    r = Router()
    span = Span("resume_medis", 0, 6, "RESUME")
    hi = min(0.99, r.flag_at + 0.2)
    flags = [
        Flag(DefectClass.D2, Remedy.RECODE, span, 0.99, FlagSource.CROSS_ENCODER),
        Flag(DefectClass.D4, Remedy.QUERY, span, hi, FlagSource.CROSS_ENCODER),
    ]
    d = r.decide(flags, GroupResult("A-4-14-I", 1, 3900000))
    assert d.flags[0].remedy is Remedy.QUERY


def test_ungroupable_episode_abstains_rather_than_guessing() -> None:
    d = Router().decide((), GroupResult(None, None, None, "diagnosis tidak dikenali"))
    assert d.verdict is Verdict.ABSTAIN
    assert d.flags == ()


def test_no_threshold_is_hardcoded() -> None:
    """Thresholds live in config/thresholds.yaml, never in code."""
    from vitera import config

    t = config.thresholds()["router"]["high_precision"]
    r = Router(profile="high_precision")
    assert r.flag_at == t["flag_at"]
    assert r.flag_at != Router().flag_at


# --- rule 8: useful with the LLM switched off ----------------------------


def test_pipeline_runs_and_labels_itself_advisory_without_a_model(corpus: list) -> None:
    res = run_pipeline(_ctx(corpus[0]))
    assert res.trace.degraded
    assert res.is_advisory
    assert "advisory" in res.decision.reason


def test_pipeline_survives_a_dead_llm(corpus: list) -> None:
    """The model layer failing must degrade the run, not fail it."""
    ep, gt = corpus[0]
    claim, _, _ = inject(ep, gt, __import__("random").Random(3))
    res = run_pipeline(RuleContext(ep, claim, ep.discharge_day), llm=NullLLMClient())
    assert res.trace.llm_calls == 0
    assert res.decision.verdict in (Verdict.CLEAN, Verdict.FLAGGED, Verdict.ABSTAIN)


# --- rule 4: the gate precedes every model -------------------------------


def test_invalid_record_never_reaches_a_tool(corpus: list) -> None:
    from dataclasses import replace as dc_replace

    ep, gt = corpus[0]
    claim = dc_replace(clean_claim(ep, gt), documents_present=())
    called = []

    class Spy:
        def score(self, ctx):
            called.append(1)
            return []

    res = run_pipeline(RuleContext(ep, claim, ep.discharge_day), scorer=Spy())
    assert not called, "scorer ran on a record that failed validation"
    assert res.validation_failures
    assert res.trace.tool_calls == ()


# --- rule 2: the LLM never changes a determination -----------------------


def test_llm_may_only_rewrite_prose(corpus: list) -> None:
    from vitera.agent.loop import _explain

    span = Span("resume_medis", 0, 6, "RESUME")
    before = Flag(
        DefectClass.D4, Remedy.QUERY, span, 0.83, FlagSource.CROSS_ENCODER, "asli"
    )

    class Liar(LLMClient):
        def __init__(self) -> None:
            super().__init__(mode="cache")

        def complete(self, prompt, *, max_tokens=512):
            return boundary.Completion("prosa baru", True, "x")

    after, n = _explain([before], Liar())
    assert n == 1
    assert after[0].rationale == "prosa baru"
    # everything that constitutes a determination is unchanged
    assert after[0].defect_class is before.defect_class
    assert after[0].remedy is before.remedy
    assert after[0].score == before.score
    assert after[0].span == before.span


# --- the invariant the sweep depends on ----------------------------------


def test_running_at_discharge_reproduces_the_discharge_product(corpus: list) -> None:
    """Concurrent monitoring is this pipeline invoked N times. If the day-N run
    differs from the discharge-time run, we have built a second system."""
    for pair in corpus[:15]:
        ep, gt = pair
        a = run_pipeline(_ctx(pair, ep.discharge_day))
        b = run_pipeline(_ctx(pair, ep.discharge_day))
        assert a.decision == b.decision
        assert a.grouping == b.grouping


def test_pipeline_is_runnable_on_any_day_of_stay(corpus: list) -> None:
    ep, gt = corpus[0]
    for day in range(1, (ep.discharge_day or 1) + 1):
        res = run_pipeline(_ctx((ep, gt), day))
        assert res.day == day
        assert res.trace.elapsed_seconds < 20.0
