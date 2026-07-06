from pydantic import BaseModel, Field
from typing import List
from auditor.violation_details import ViolationDetail
class AuditReportSchema(BaseModel):
    audit_status: str = Field(
        description="The final computed validation status. Must be strictly one of: 'APPROVED', 'FLAGGED_ANOMALY', 'DENIED'."
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