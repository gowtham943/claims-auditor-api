import uuid
from typing import Optional
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.user import User
from models.schema import UserCreateDTO
from enums.system_role import SystemRole


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_user(self, dto: UserCreateDTO, password_hash: str) -> User:
        user = User(
            username=dto.username,
            password_hash=password_hash,
            role=dto.role or SystemRole.AUDITOR
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_username(self, username: str) -> Optional[User]:
        statement = select(User).where(User.username == username)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        statement = select(User).where(User.id == user_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()
