from pydantic import BaseModel, Field
from typing import List, Literal, Optional

from dto.types import SafeText

DocType = Literal[
    "sep", "spri", "resume_medis", "lab", "radiologi",
    "laporan_operasi", "cppt", "tagihan", "grouping", "other",
]
Stage = Literal["checkin", "instay", "checkout"]


class Claim(BaseModel):
    """What the coder submitted, or is about to submit."""

    principal_dx: str
    secondary_dx: List[str] = Field(default_factory=list)
    procedures: List[str] = Field(default_factory=list)
    severity_level: Optional[int] = None

    def codes(self) -> List[str]:
        return [self.principal_dx] + self.secondary_dx + self.procedures


class RawDoc(BaseModel):
    """One document in the berkas, as extracted. Still contains PII."""

    doc_id: str
    doc_type: DocType
    stage: Stage
    received_at: Optional[str] = None
    extraction: Literal["digital", "ocr"] = "digital"
    ocr_confidence: Optional[float] = None
    signed: Optional[bool] = None
    text: str


class Demographics(BaseModel):
    name: str
    nik: Optional[str] = None
    sep: Optional[str] = None
    sex: Literal["M", "F"]
    age_years: int


class RawEpisode(BaseModel):
    """The berkas as it stands tonight. PII-bearing — never passed to a model."""

    episode_id: str
    admitted_at: Optional[str] = None
    discharged_at: Optional[str] = None
    hospital_day: int = 1
    demographics: Demographics
    docs: List[RawDoc]
    claim: Claim


class SafeDoc(BaseModel):
    doc_id: str
    doc_type: DocType
    stage: Stage
    extraction: Literal["digital", "ocr"] = "digital"
    ocr_confidence: Optional[float] = None
    signed: Optional[bool] = None
    text: SafeText


class SafeEpisode(BaseModel):
    """Redacted. The only thing the encoder and the narrator ever see.

    Note what is absent: name, NIK, SEP. Not blanked — structurally absent, so
    there is no field for them to leak out of.
    """

    episode_id: str
    sex: Literal["M", "F"]
    age_years: int
    hospital_day: int
    discharged: bool
    docs: List[SafeDoc]
    claim: Claim
    dropped_docs: List[str] = Field(
        default_factory=list,
        description="Docs withheld from the model by fail-closed redaction. "
        "Reported to the coder, never silently hidden.",
    )
