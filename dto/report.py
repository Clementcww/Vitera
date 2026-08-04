from pydantic import BaseModel, Field
from typing import List, Literal

from dto.finding import Finding


class ClaimReviewResponse(BaseModel):
    episode_id: str
    hospital_day: int
    status: Literal["clean", "review", "urgent"]

    findings: List[Finding]
    filtered_count: int = Field(
        0, description="Model findings deleted for failing to quote the record verbatim."
    )
    dropped_docs: List[str] = Field(
        default_factory=list, description="Docs withheld from the model by fail-closed redaction."
    )

    baseline: int = Field(..., description="INA-CBG tariff as currently coded, IDR.")
    adjusted: int = Field(..., description="Tariff the documentation actually supports, IDR.")
    at_risk: int = Field(0, description="Tariff exposed to pend/denial if submitted as is, IDR.")
