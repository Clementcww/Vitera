from enum import StrEnum
from pydantic import BaseModel, Field
from typing import Literal, Optional


class DefectClass(StrEnum):
    # Berkas completeness — deterministic, metadata only
    C1_MISSING_DOC = "C1"
    C2_MISSING_SIGNATURE = "C2"
    C3_PROCEDURE_NO_EVIDENCE = "C3"
    # Code validity — deterministic, set membership and table joins
    R1_INVALID_CODE = "R1"
    R2_DEMOGRAPHIC_CONFLICT = "R2"
    R3_STRUCTURAL_VIOLATION = "R3"
    # Judgement against clinical text — cross-encoder
    M1_WRONG_SPECIFICITY = "M1"
    M2_UNSUPPORTED_DIAGNOSIS = "M2"
    M3_UNSUPPORTED_SEVERITY = "M3"
    M4_UPCODING = "M4"
    D8_UNDERCODED = "D8"


class Finding(BaseModel):
    cls: DefectClass
    msg: str
    src: Literal["rules", "model"]

    code: Optional[str] = Field(None, description="The submitted code at issue, if any.")
    suggested: Optional[str] = Field(None, description="The code the record supports instead.")
    doc: Optional[str] = Field(None, description="doc_id the evidence came from.")
    span: Optional[str] = Field(
        None, description="Verbatim quote from the record. Enforced by spanfilter."
    )
    conf: Optional[float] = Field(None, description="Encoder confidence. None = deterministic.")

    delta: int = Field(0, description="Tariff change in IDR if this finding is acted on.")
    risk: int = Field(0, description="Tariff at risk of pend/denial if it is not.")
