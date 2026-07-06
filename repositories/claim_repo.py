import uuid
from typing import Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from enums.submission_status import SubmissionStatus
from models.claim_submission import ClaimSubmission
from models.policy_rule_book import PolicyRulebook
from models.schema import ClaimCreateDTO, ClaimStatusUpdateDTO


class ClaimRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_submission(
        self,
        dto: ClaimCreateDTO,
        user_id: uuid.UUID,
    ) -> ClaimSubmission:
        submission = ClaimSubmission(
            **dto.model_dump(exclude_none=True),
            user_id=user_id,
        )
        self.session.add(submission)
        await self.session.flush()
        return submission

    async def update_claim_status(
        self,
        claim_id: uuid.UUID,
        dto: ClaimStatusUpdateDTO,
        user_id: uuid.UUID,
    ) -> Optional[ClaimSubmission]:
        statement = select(ClaimSubmission).where(
            ClaimSubmission.id == claim_id,
            ClaimSubmission.user_id == user_id,
        )
        result = await self.session.execute(statement)
        claim = result.scalar_one_or_none()

        if claim:
            claim.status = dto.status
            updated_metadata = dict(claim.claim_metadata)
            updated_metadata.update(dto.audit_payload)
            claim.claim_metadata = updated_metadata
            await self.session.flush()
        return claim

    async def get_claim_by_id(
        self,
        claim_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[ClaimSubmission]:
        statement = select(ClaimSubmission).where(
            ClaimSubmission.id == claim_id,
            ClaimSubmission.user_id == user_id,
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_completed_audits_by_user(
        self,
        user_id: uuid.UUID,
    ) -> list[tuple[ClaimSubmission, str]]:
        statement = (
            select(ClaimSubmission, PolicyRulebook.plan_name)
            .join(PolicyRulebook, ClaimSubmission.policy_id == PolicyRulebook.id)
            .where(
                ClaimSubmission.user_id == user_id,
                ClaimSubmission.status != SubmissionStatus.PENDING_RECONCILIATION.value,
            )
            .order_by(ClaimSubmission.patient_name)
        )
        result = await self.session.execute(statement)
        rows = list(result.all())
        rows.sort(
            key=lambda row: row[0].claim_metadata.get("audited_at", ""),
            reverse=True,
        )
        return rows

    async def get_completed_audit_by_id(
        self,
        claim_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[tuple[ClaimSubmission, str]]:
        statement = (
            select(ClaimSubmission, PolicyRulebook.plan_name)
            .join(PolicyRulebook, ClaimSubmission.policy_id == PolicyRulebook.id)
            .where(
                ClaimSubmission.id == claim_id,
                ClaimSubmission.user_id == user_id,
                ClaimSubmission.status != SubmissionStatus.PENDING_RECONCILIATION.value,
            )
        )
        result = await self.session.execute(statement)
        row = result.one_or_none()
        return row
