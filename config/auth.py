import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from config.config_setting import settings
from config.database_config import db
from models.user import User
from repositories.user_repo import UserRepository

# This tells FastAPI where the login route is so it can generate auto-documentation (Swagger)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_user_repo(session: AsyncSession = Depends(db.get_session)) -> UserRepository:
    return UserRepository(session)


async def get_current_user(token: str = Depends(oauth2_scheme), repo: UserRepository = Depends(get_user_repo)) -> User:
    """The Bouncer: Checks the token and returns the User object."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # 1. Read the wristband
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        print(f"Decoded JWT payload: {payload}")
        user_name: str = payload.get("sub")
        if user_name is None:
            raise credentials_exception
    except jwt.InvalidTokenError:
        raise credentials_exception

    # 2. Look up the user in the database
    user = await repo.get_by_username(username=user_name)
    if user is None:
        raise credentials_exception

    return user
