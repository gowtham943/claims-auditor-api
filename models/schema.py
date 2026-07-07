import uuid
from typing import Any, Dict, Optional
from sqlmodel import SQLModel
from enums.system_role import SystemRole

class UserCreateDTO(SQLModel):
    username: str
    password: str
    role: Optional[SystemRole] = SystemRole.AUDITOR.value


class UserUpdateDTO(SQLModel):
    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[SystemRole] = SystemRole.AUDITOR.value


class PolicyCreateDTO(SQLModel):
    id: Optional[uuid.UUID] = None
    plan_name: str
    geography: str
    plan_type: str
    source_url: Optional[str] = None


class PolicyUpdateDTO(SQLModel):
    plan_name: Optional[str] = None
    geography: Optional[str] = None
    plan_type: Optional[str] = None
    source_url: Optional[str] = None


class PolicySummaryDTO(SQLModel):
    id: uuid.UUID
    plan_name: str
    geography: str
    plan_type: str
    source_url: Optional[str] = None


class ClaimCreateDTO(SQLModel):
    id: Optional[uuid.UUID] = None
    policy_id: uuid.UUID
    patient_name: str
    claim_metadata: Dict[str, Any] = {}
    status: str = "PENDING"


class ClaimStatusUpdateDTO(SQLModel):
    status: str
    audit_payload: Dict[str, Any] = {}


class ClaimAuditSummaryDTO(SQLModel):
    id: uuid.UUID
    patient_name: str
    policy_id: uuid.UUID
    policy_plan_name: str
    audit_status: str
    total_billed_amount: float
    expected_patient_responsibility: float
    violation_count: int
    audited_at: Optional[str] = None


class ClaimAuditDetailDTO(SQLModel):
    id: uuid.UUID
    patient_name: str
    policy_id: uuid.UUID
    policy_plan_name: str
    audit_status: str
    total_billed_amount: float
    expected_patient_responsibility: float
    violations: list[Dict[str, Any]]
    raw_claim_markdown: str = ""
