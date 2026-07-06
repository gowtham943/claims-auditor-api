from pydantic import BaseModel, Field

class ViolationDetail(BaseModel):
    rule_name: str = Field(
        description="Programmatic code label for the violation (e.g., 'PCP_REFERRAL_MISSING', 'COPAY_MISMATCH')."
    )
    severity: str = Field(
        description="The priority risk rating tier. Must be exactly 'HIGH' or 'MEDIUM'."
    )
    description: str = Field(
        description="A mathematically explicit explanation detailing exactly why the parameter failed compliance checks."
    )
    policy_citation: str = Field(
        description="The exact text snippet or markdown table row copied from the master contract used to identify the violation."
    )