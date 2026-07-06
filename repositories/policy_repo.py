import uuid
from typing import Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.policy_rule_book import PolicyRulebook
from models.schema import PolicyCreateDTO


class PolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def save_policy(
        self,
        dto: PolicyCreateDTO,
        raw_markdown: str,
        user_id: uuid.UUID,
    ) -> PolicyRulebook:
        policy = PolicyRulebook(
            **dto.model_dump(exclude_none=True),
            user_id=user_id,
            raw_markdown_layout=raw_markdown,
        )
        self.session.add(policy)
        await self.session.flush()
        return policy

    async def get_policy_markdown_by_id(
        self,
        policy_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[str]:
        statement = (
            select(PolicyRulebook.raw_markdown_layout)
            .where(
                PolicyRulebook.id == policy_id,
                PolicyRulebook.user_id == user_id,
            )
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_policy_by_id(
        self,
        policy_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[PolicyRulebook]:
        statement = select(PolicyRulebook).where(
            PolicyRulebook.id == policy_id,
            PolicyRulebook.user_id == user_id,
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_ingested_policies_by_user(
        self,
        user_id: uuid.UUID,
    ) -> list[PolicyRulebook]:
        statement = (
            select(PolicyRulebook)
            .where(
                PolicyRulebook.user_id == user_id,
                PolicyRulebook.raw_markdown_layout != "",
            )
            .order_by(PolicyRulebook.plan_name)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def update_policy_markdown_layout(
        self,
        policy_id: uuid.UUID,
        raw_markdown: str,
        user_id: uuid.UUID,
    ) -> None:
        statement = select(PolicyRulebook).where(
            PolicyRulebook.id == policy_id,
            PolicyRulebook.user_id == user_id,
        )
        result = await self.session.execute(statement)
        policy = result.scalar_one_or_none()

        if not policy:
            raise ValueError(f"Policy record with ID {policy_id} does not exist.")

        policy.raw_markdown_layout = raw_markdown
        self.session.add(policy)

    async def mark_policy_as_failed(
        self,
        policy_id: uuid.UUID,
        error_notes: str,
        user_id: uuid.UUID,
    ) -> None:
        statement = select(PolicyRulebook).where(
            PolicyRulebook.id == policy_id,
            PolicyRulebook.user_id == user_id,
        )
        result = await self.session.execute(statement)
        policy = result.scalar_one_or_none()

        if policy:
            return
