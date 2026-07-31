"""The INA-CBG grouper. Deterministic. Never a model.

Architectural rule 7: this is the only component that produces a monetary
figure, and it refuses to produce one when the episode is ungroupable.

Grouping depends on the CODED claim, not on what is clinically true. A
comorbidity that is present in the record but absent from the claim cannot
lift severity — which is exactly why undercoding costs money, and why the
gap between `group(claim)` and `group(ground_truth)` is the recoverable value
the coder queue is ordered by.
"""

from __future__ import annotations

from vitera.contracts import GroupResult, ValidatedEpisode
from vitera.generator import reference as ref


class Grouper:
    """Deterministic lookup. Readable end to end; no learned parameters."""

    def __init__(self) -> None:
        self._by_primary = {g.primary: g for g in ref.cbg_groups()}
        self._multipliers = ref.severity_multipliers()

    # -- severity ----------------------------------------------------------

    def severity(self, secondary_dx: tuple[str, ...]) -> int:
        """Severity level I / II / III from CODED secondary diagnoses.

        Unknown codes contribute zero weight rather than raising: a koder can
        legitimately code something outside our reference set, and treating
        that as ungroupable would overstate the grouper's strictness.
        """
        weight = 0
        for code in secondary_dx:
            try:
                weight += ref.comorbidity_by_code(code).severity_weight
            except KeyError:
                continue
        if weight >= 4:
            return 3
        if weight >= 2:
            return 2
        return 1

    # -- grouping ----------------------------------------------------------

    def group_codes(
        self,
        primary_dx: str,
        secondary_dx: tuple[str, ...],
        procedures: tuple[str, ...],
    ) -> GroupResult:
        g = self._by_primary.get(primary_dx)
        if g is None:
            return GroupResult(
                cbg_code=None,
                severity=None,
                tariff_idr=None,
                ungroupable_reason=f"diagnosis utama {primary_dx} tidak dikenali",
            )

        if g.required_procedure and g.required_procedure not in procedures:
            return GroupResult(
                cbg_code=None,
                severity=None,
                tariff_idr=None,
                ungroupable_reason=(
                    f"grup {g.cbg} memerlukan prosedur {g.required_procedure}, "
                    "tidak ada pada klaim"
                ),
            )

        sev = self.severity(secondary_dx)
        tariff = int(round(g.base_tariff_idr * self._multipliers[sev]))
        return GroupResult(
            cbg_code=f"{g.cbg}-{'I' * sev}",
            severity=sev,  # type: ignore[arg-type]
            tariff_idr=tariff,
            ungroupable_reason=None,
        )

    def group(self, episode: ValidatedEpisode) -> GroupResult:
        """Protocol entry point. Groups what the record documents."""
        ep = episode.episode
        return self.group_codes(
            ep.primary_dx,
            ep.documented_dx_at(episode.day),
            ep.procedures,
        )
