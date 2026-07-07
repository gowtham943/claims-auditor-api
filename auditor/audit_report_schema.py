from pydantic import BaseModel, Field
from typing import List
from auditor.violation_details import ViolationDetail


class AuditReportSchema(BaseModel):
    audit_status: str = Field(
        description=(
            "The final claim validation result. Must be strictly one of: "
            "'VALID' (claim follows policy rules), "
            "'NEEDS_REVIEW' (issues or missing details found), "
            "'INVALID' (claim does not follow policy rules)."
        )
    )
    total_billed_amount: float = Field(
        description="The total cumulative charges stated on the incoming operational claim sheet."
    )
    expected_patient_responsibility: float = Field(
        description="The exact financial dollar amount the patient owes based on the policy copay or deductible parameters."
    )
    violations: List[ViolationDetail] = Field(
        description="An array list housing all caught compliance, network tier, or pricing discrepancies."
    )
