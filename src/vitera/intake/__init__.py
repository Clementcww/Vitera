"""Paper intake: FPK in, corrected draft FPK out.

The workflow in the design brief starts at step 5 with a berkas klaim that is partly
paper. The FPK (Formulir Pengajuan Klaim) is the cover form a hospital submits
with a batch of claims, and in most of the hospitals we are designing for it
exists as a printed, signed, scanned sheet rather than as a row in a database.

This package closes that gap at both ends:

    render    our cohort -> an FPK, laid out as the real form, with every
              rupiah figure taken from the grouper (rule 7)
    scan      a scanned or photographed FPK -> observations with bounding
              boxes and confidences -> deterministically extracted fields
    validate  the extracted form checked before any model sees it (rule 4)
    correct   the pipeline's findings -> a DRAFT corrected FPK a human signs

What intake is not: a second pipeline. It is a *reader* and a *writer* around
the pipeline that already exists. `correct.py` calls the same `run_pipeline`
that `demo.py`, `export.py` and the sweep call, and it makes no clinical or
monetary determination of its own.
"""

from __future__ import annotations

__all__ = ["form", "render", "scan", "extract", "validate", "correct", "degrade"]
