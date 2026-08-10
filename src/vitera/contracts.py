"""Interface contracts for Vitera.

Every module under ``src/vitera`` codes against these types. They exist to make
the hard architectural rules in the design brief structural rather than conventional —
a rule enforced by a type cannot be forgotten at 2am on day 6.

    rule 3   LLM never sees re-identified data
             -> ``PseudonymisedText`` is a distinct type from ``ClinicalText``;
                ``LLMClient`` accepts only the former. Passing raw text is a
                type error, not a code review finding.

    rule 4   validation gate precedes every model
             -> ``ValidatedEpisode`` is the only input ``Scorer`` accepts, and
                it is returned solely by ``rules.validate``.

    rule 6   every flag carries a verbatim span, or it is dropped
             -> ``Flag.span`` is non-optional. A flag without evidence cannot
                be constructed.

    rule 7   the grouper is authoritative for tariff
             -> ``GroupResult`` is the only type with a money field, and it
                refuses to hold a tariff when ungroupable.

    rule 9   bounded loops
             -> ``LoopBudget``, checked by the harness, not by the prompt.

    rule 10  abstention is a first-class output
             -> ``Verdict.ABSTAIN``.

Sweep rule 4 (a dismissed flag stays dismissed until its evidence changes) is
served by ``Span.evidence_hash``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Literal, NewType, Protocol, runtime_checkable

__all__ = [
    "ClinicalText",
    "PseudonymisedText",
    "DefectClass",
    "Remedy",
    "Verdict",
    "FlagSource",
    "EventKind",
    "DiffStatus",
    "Span",
    "ClinicalEvent",
    "SecondaryDiagnosis",
    "Episode",
    "ValidationFailure",
    "ValidatedEpisode",
    "GroupResult",
    "Flag",
    "RouterDecision",
    "LoopBudget",
    "ToolCall",
    "Trace",
    "PipelineResult",
    "SweepResult",
    "SweepDiff",
    "Pseudonymiser",
    "LLMClient",
    "Grouper",
    "RulesEngine",
    "Scorer",
    "Router",
]


# ---------------------------------------------------------------------------
# Text types — the pseudonymisation boundary (rule 3)
# ---------------------------------------------------------------------------

ClinicalText = NewType("ClinicalText", str)
"""Free text as it appears in the record. Never crosses the model boundary."""

PseudonymisedText = NewType("PseudonymisedText", str)
"""Text after identifier removal. The only text an LLM may receive."""


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class DefectClass(Enum):
    """The eight defect classes. ``rules_reachable`` is a claim we measure in
    bucket 5 (claim 3), not an assumption — arm A must demonstrate it."""

    D1 = ("Berkas tidak lengkap", True)
    D2 = ("Wrong code specificity (sibling code)", False)
    D3 = ("Diagnosis unsupported by narrative", False)
    D4 = ("Severity unsupported by comorbidity documentation", False)
    D5 = ("Missing required supporting examination", None)  # partly
    D6 = ("Procedure-diagnosis incoherence", True)
    D7 = ("Upcoding pattern (valid individually, inflates CBG)", False)
    D8 = ("Administrative mismatch (SEP, identity, dates)", True)

    def __init__(self, label: str, rules_reachable: bool | None) -> None:
        self.label = label
        self.rules_reachable = rules_reachable


class Remedy(Enum):
    """Who acts, and how fast the repair window closes.

    Ordering matters: the sweep's queue weighting uses ``decay_rank`` so that
    remedies needing the patient still on the ward surface first.
    """

    QUERY = ("DPJP", 0)  # care likely delivered, record does not show it
    OBTAIN = ("Petugas berkas", 1)  # required document missing
    RECODE = ("Koder", 2)  # evidence exists, wrong code chosen

    def __init__(self, actor: str, decay_rank: int) -> None:
        self.actor = actor
        self.decay_rank = decay_rank


class Verdict(Enum):
    CLEAN = "clean"
    FLAGGED = "flagged"
    ABSTAIN = "abstain"  # rule 10 — reachable, and measured


class FlagSource(Enum):
    RULES = "rules"
    CROSS_ENCODER = "cross_encoder"
    ROUTER = "router"


class EventKind(Enum):
    LAB = "lab"
    MED = "med"
    PROCEDURE = "procedure"
    NOTE = "note"
    VITALS = "vitals"
    ADMIN = "admin"


class DiffStatus(Enum):
    NEW = "new"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    UNCHANGED = "unchanged"  # never enters the queue — sweep rule 3


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Span:
    """A verbatim quotation from the record.

    ``text`` is copied, never paraphrased and never model-generated. The
    pipeline filter that enforces rule 6 checks that ``text`` occurs at
    ``[start:end]`` of the named document; a span that fails is dropped.
    """

    doc_id: str
    start: int
    end: int
    text: str

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError(f"empty span in {self.doc_id}: [{self.start}:{self.end}]")
        if not self.text:
            raise ValueError(f"span in {self.doc_id} carries no text")

    @property
    def evidence_hash(self) -> str:
        """Suppression key. Sweep rule 4: same hash, silent; new hash, new flag."""
        return hashlib.sha256(f"{self.doc_id}:{self.text}".encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# The episode — a dated sequence, never a snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ClinicalEvent:
    day: int  # days since admission; 0 is admission day
    kind: EventKind
    code: str | None = None
    text: ClinicalText | None = None


@dataclass(frozen=True, slots=True)
class Document:
    """A dated document in the record.

    ``day`` is what makes ``Episode.at_day`` possible: on day 3 the resume
    medis does not exist yet, and a flag citing it would be citing the future.
    """

    doc_id: str
    day: int
    text: ClinicalText


@dataclass(frozen=True, slots=True)
class SecondaryDiagnosis:
    """Carries the two timestamps the whole concurrent thesis rests on.

    ``documented_day is None`` is an undercoding defect, detectable from
    ``signal_day`` onward. ``documented_day - signal_day`` is the window
    Vitera operates in, and ``detection_lead_time`` measures our use of it.
    """

    icd10: str
    signal_day: int | None
    documented_day: int | None

    @property
    def is_undocumented(self) -> bool:
        return self.documented_day is None

    @property
    def visible_window(self) -> int | None:
        """Days between clinical visibility and documentation, if both exist."""
        if self.signal_day is None or self.documented_day is None:
            return None
        return self.documented_day - self.signal_day


@dataclass(frozen=True, slots=True)
class Episode:
    episode_id: str
    site_id: str
    admission_date: date
    primary_dx: str
    secondary_dx: tuple[SecondaryDiagnosis, ...]
    procedures: tuple[str, ...]
    events: tuple[ClinicalEvent, ...]
    documents: tuple[Document, ...]
    discharge_day: int | None = None

    @property
    def is_admitted(self) -> bool:
        return self.discharge_day is None

    @property
    def los_so_far(self) -> int:
        """Length of stay to date. The sweep's cohort filter reads this."""
        if self.discharge_day is not None:
            return self.discharge_day
        return max((e.day for e in self.events), default=0)

    def at_day(self, day: int) -> Episode:
        """Collapse the sequence to what was knowable on ``day``.

        INVARIANT, tested in ``tests/test_contracts.py``:
        ``episode.at_day(episode.discharge_day) == episode``

        This is what makes concurrent monitoring the discharge pipeline invoked
        N times rather than a second system. If this invariant ever fails, the
        concurrent results and the discharge results are not comparable and the
        lead-time claim is void.

        Three things are filtered, and nothing else:

        - **events** to those that had happened by ``day``;
        - **documents** to those written by ``day`` — on day 3 there is no
          resume medis, so a flag citing one would be citing the future;
        - **secondary diagnoses** to those clinically present by ``day``, i.e.
          ``signal_day <= day``. A comorbidity that has not developed yet is
          not a missed diagnosis.

        Note what is deliberately NOT filtered: a diagnosis whose
        ``signal_day <= day`` is kept even when ``documented_day > day`` or is
        ``None``. That is exactly the undercoding case — clinically visible,
        not yet written down — and removing it would erase the phenomenon the
        product exists to detect.
        """
        if day < 0:
            raise ValueError(f"day must be >= 0, got {day}")

        discharged = self.discharge_day is not None and day >= self.discharge_day
        return Episode(
            episode_id=self.episode_id,
            site_id=self.site_id,
            admission_date=self.admission_date,
            primary_dx=self.primary_dx,
            secondary_dx=tuple(
                d
                for d in self.secondary_dx
                if d.signal_day is not None and d.signal_day <= day
            ),
            procedures=self.procedures,
            events=tuple(e for e in self.events if e.day <= day),
            documents=tuple(d for d in self.documents if d.day <= day),
            discharge_day=self.discharge_day if discharged else None,
        )

    def documented_dx_at(self, day: int) -> tuple[str, ...]:
        """Secondary diagnoses actually written down by ``day``.

        The gap between this and ``at_day(day).secondary_dx`` is the value
        Vitera creates, and what ``detection_lead_time`` measures.
        """
        return tuple(
            d.icd10
            for d in self.secondary_dx
            if d.documented_day is not None and d.documented_day <= day
        )


# ---------------------------------------------------------------------------
# The validation gate (rule 4)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ValidationFailure:
    check: str
    detail: str


@dataclass(frozen=True, slots=True)
class ValidatedEpisode:
    """An episode that has passed every deterministic check.

    Returned only by ``vitera.rules.validate``. No scorer, router or LLM
    accepts a bare ``Episode`` — that is how rule 4 is enforced.
    """

    episode: Episode
    day: int  # the day this validation was performed for
    checks_passed: tuple[str, ...]


# ---------------------------------------------------------------------------
# Grouping — the only source of money (rule 7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GroupResult:
    cbg_code: str | None
    severity: Literal[1, 2, 3] | None
    tariff_idr: int | None
    ungroupable_reason: str | None = None

    def __post_init__(self) -> None:
        if self.ungroupable_reason is not None and self.tariff_idr is not None:
            raise ValueError(
                "UNGROUPABLE episodes carry no tariff — never estimate one"
            )

    @property
    def is_groupable(self) -> bool:
        return self.ungroupable_reason is None


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Flag:
    """A finding. ``span`` is non-optional by design — rule 6.

    ``subject`` is WHAT the finding is about, as a stable machine token: the
    ICD-10 code for a diagnosis finding, the ICD-9-CM code for a procedure, the
    ``doc_id`` for a missing document, the field name for an administrative
    mismatch. It exists for two reasons, both of which were live bugs:

    1. **Identity.** Without it, two findings about *different codes* that cite
       the same anchor line collide on ``suppression_key`` — which D5 and D7 do
       constantly, because an absence-based finding cites the berkas cover
       sheet. Colliding keys mean staging or dismissing one silently applies to
       the other, and the queue shows two rows a reader cannot tell apart.
    2. **Durability.** The subject used to be recovered by regex over
       ``rationale``. But ``rationale`` is prose and rule 2 lets the LLM rewrite
       it, so every consumer of that regex broke the moment prose was switched
       on — silently, by returning fewer codes rather than by raising.

    ``rationale`` is prose and may be LLM-written. It explains a determination
    already made by the cross-encoder, rules or grouper; it never makes one
    (rule 2). Nothing may be parsed back out of it.
    """

    defect_class: DefectClass
    remedy: Remedy
    span: Span
    score: float  # calibrated, [0, 1]
    source: FlagSource
    rationale: str = ""
    subject: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.score <= 1.0:
            raise ValueError(f"score out of range: {self.score}")

    @property
    def finding_key(self) -> str:
        """**Is this the same finding as yesterday's?** — sweep rule 3.

        Class and subject only. Deliberately NOT the evidence hash, and the
        distinction is not academic: a comorbidity visible in the record is
        re-cited from a newer CPPT every night as the notes accumulate, so a
        diff keyed on evidence reports the identical finding as `resolved` plus
        `new` every single morning. Measured on a 7-night replay before this
        split existed, that alone drove `flag_churn_rate` to 0.79 against a
        0.15 ceiling — the koder would have been shown the same D4 on the same
        code seven times, each with a different quotation.

        Rule 3 is what forbids that: a flag that was true yesterday and is
        still true today does not re-enter the queue.
        """
        return f"{self.defect_class.name}:{self.subject}"

    @property
    def suppression_key(self) -> str:
        """**Did the koder already dismiss this, on this evidence?** — rule 4.

        Adds the evidence hash, because a dismissal is a judgement about a
        specific quotation. "Not this, on this evidence" must not silence a
        finding that later acquires *different* evidence. Same span, silent;
        new span, new flag; never expired by a timer.

        Two keys, two questions. Using this one for the diff conflates them and
        floods the queue; using `finding_key` for dismissal makes a dismissal
        permanent, which rule 4 forbids.
        """
        return f"{self.finding_key}:{self.span.evidence_hash}"


@dataclass(frozen=True, slots=True)
class RouterDecision:
    """Deterministic and readable in one screen (rule 5).

    Models score. This decides. Thresholds are read from
    ``config/thresholds.yaml`` and never appear in code or in a prompt.
    """

    verdict: Verdict
    flags: tuple[Flag, ...]
    threshold_set: str  # which named threshold block was applied
    reason: str


# ---------------------------------------------------------------------------
# The agent harness (rule 9) — bucket 7
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LoopBudget:
    max_tool_calls: int = 8
    max_reflections: int = 1
    wall_clock_seconds: float = 20.0

    def exceeded(self, calls: int, reflections: int, elapsed: float) -> str | None:
        """Return the breached limit, or None. Breach hands to a human with
        whatever was gathered — it never silently truncates."""
        if calls > self.max_tool_calls:
            return f"max_tool_calls ({self.max_tool_calls})"
        if reflections > self.max_reflections:
            return f"max_reflections ({self.max_reflections})"
        if elapsed > self.wall_clock_seconds:
            return f"wall_clock_seconds ({self.wall_clock_seconds})"
        return None


@dataclass(frozen=True, slots=True)
class ToolCall:
    tool: str
    arguments: Mapping[str, object]
    result_digest: str
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class Trace:
    """Everything a human needs to audit one pipeline run."""

    episode_id: str
    day: int
    tool_calls: tuple[ToolCall, ...]
    llm_calls: int
    budget_breach: str | None
    degraded: bool  # rules-only advisory mode (rule 8)
    elapsed_seconds: float


@dataclass(frozen=True, slots=True)
class PipelineResult:
    episode_id: str
    day: int
    decision: RouterDecision
    grouping: GroupResult
    validation_failures: tuple[ValidationFailure, ...]
    trace: Trace

    @property
    def is_advisory(self) -> bool:
        return self.trace.degraded


# ---------------------------------------------------------------------------
# The sweep — scheduling only, no inference (rule 11) — bucket 13
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SweepResult:
    episode_id: str
    sweep_date: date
    day_of_stay: int
    result: PipelineResult
    status: Literal["complete", "partial", "advisory"]


@dataclass(frozen=True, slots=True)
class SweepDiff:
    """The sweep's output is the diff, not the flag set (sweep rule 3).

    Unchanged flags never enter the queue. Re-presenting yesterday's findings
    every morning is how a monitoring product gets switched off in week two.
    """

    episode_id: str
    sweep_date: date
    new: tuple[Flag, ...]
    resolved: tuple[Flag, ...]
    escalated: tuple[Flag, ...]
    previous_successful_sweep: date | None
    # Findings that went away because the RECORD changed — a note arrived since
    # the last sweep that mentions what the finding was about. Held apart from
    # `resolved` because they are opposite signals wearing the same shape: this
    # is documentation catching up, which is the outcome the product exists to
    # produce, while `resolved` is a finding that vanished with nothing to
    # explain it, which is model instability. Averaging them into one churn
    # number makes the product's successes indistinguishable from its defects.
    documented: tuple[Flag, ...] = ()
    recoverable_idr: int = 0  # grouper output, copied — never computed here
    still_admitted: bool = True
    day_of_stay: int = 0
    # Findings unchanged since the last sweep whose best citation moved to a
    # newer note. Not queue work — reported so the number is visible rather
    # than hidden inside the identity decision that suppresses it.
    citation_moved: int = 0

    @property
    def is_empty(self) -> bool:
        return not (self.new or self.resolved or self.escalated)

    @property
    def actionable(self) -> tuple[Flag, ...]:
        """What the koder is being asked to look at: what appeared and what got
        worse. `resolved` is reported, but it is not work."""
        return self.new + self.escalated

    def queue_weight(self) -> float:
        """Expected recoverable value weighted by remaining repair window.

        Deliberately arithmetic over fields the pipeline already produced, and
        deliberately not a model — sweep rule 11 says the sweep schedules, diffs
        and orders, and nothing else. Read it as: *how much value is here, and
        how fast does the chance to collect it disappear?*

        The decay term is what makes this an ordering and not a leaderboard. A
        QUERY needs the DPJP while the patient is on the ward, so it loses value
        every night; an OBTAIN survives discharge; a RECODE survives until
        submission. A QUERY worth Rp 2 juta on a patient discharging tomorrow
        outranks a RECODE worth Rp 5 juta that will still be there next week.

        `queue.order_key` is the actual sort. This is its money term.
        """
        if not self.actionable:
            return 0.0
        decay = min(f.remedy.decay_rank for f in self.actionable)
        # A window that has already shut cannot be traded against one that has
        # not, so a QUERY on a discharged patient drops to the OBTAIN horizon
        # rather than staying at the top of the queue forever.
        if decay == 0 and not self.still_admitted:
            decay = 1
        urgency = 1.0 / (1.0 + decay)
        return round(self.recoverable_idr * urgency, 2)


# ---------------------------------------------------------------------------
# Protocols — what each module must provide
# ---------------------------------------------------------------------------


@runtime_checkable
class Pseudonymiser(Protocol):
    def __call__(self, text: ClinicalText) -> PseudonymisedText: ...


@runtime_checkable
class LLMClient(Protocol):
    """Accepts pseudonymised text only. Rule 3, enforced by the type checker.

    Implementations must honour ``VITERA_LLM_MODE`` = live | record | cache.
    """

    def complete(self, prompt: PseudonymisedText, *, max_tokens: int) -> str: ...


@runtime_checkable
class Grouper(Protocol):
    """Deterministic. Never a model. Authoritative for tariff."""

    def group(self, episode: ValidatedEpisode) -> GroupResult: ...


@runtime_checkable
class RulesEngine(Protocol):
    """Reaches D1, D6, D8 and part of D5. Arm A of the experiment."""

    def validate(
        self, episode: Episode, day: int
    ) -> tuple[ValidatedEpisode | None, tuple[ValidationFailure, ...]]: ...

    def check(self, episode: ValidatedEpisode) -> tuple[Flag, ...]: ...


@runtime_checkable
class Scorer(Protocol):
    """The cross-encoder. Decides code support. Accepts validated input only."""

    def score(self, episode: ValidatedEpisode) -> tuple[Flag, ...]: ...


@runtime_checkable
class Router(Protocol):
    """Deterministic. Models score; this decides."""

    def decide(
        self, flags: Sequence[Flag], grouping: GroupResult
    ) -> RouterDecision: ...
