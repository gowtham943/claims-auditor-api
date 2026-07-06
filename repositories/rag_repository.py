import uuid
from typing import List, Tuple

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.policy_chunks import PolicyChunk
from models.policy_rule_book import PolicyRulebook


class RAGRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def save_chunks_bulk(self, chunks: List[PolicyChunk]) -> None:
        for chunk in chunks:
            self.session.add(chunk)

    async def policy_belongs_to_user(
        self,
        policy_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> bool:
        statement = select(PolicyRulebook.id).where(
            PolicyRulebook.id == policy_id,
            PolicyRulebook.user_id == user_id,
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def query_similar_policy_contexts(
        self,
        policy_id: uuid.UUID,
        query_embedding: List[float],
        user_id: uuid.UUID,
        limit: int = 5,
    ) -> List[Tuple[str, float]]:
        statement = (
            select(
                PolicyChunk.chunk_text,
                PolicyChunk.embedding.l2_distance(query_embedding).label("distance"),
            )
            .join(PolicyRulebook, PolicyChunk.policy_id == PolicyRulebook.id)
            .where(
                PolicyChunk.policy_id == policy_id,
                PolicyRulebook.user_id == user_id,
            )
            .order_by("distance")
            .limit(limit)
        )

        result = await self.session.execute(statement)
        return result.all()
