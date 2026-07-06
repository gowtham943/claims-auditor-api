from fastapi import APIRouter, Depends, HTTPException, status

from config.auth import get_current_user, get_user_repo
from models.schema import UserCreateDTO
from models.user import User
from repositories.user_repo import UserRepository
from utils.security import get_password_hash

user_router = APIRouter(prefix="/user", tags=["users"])


@user_router.post("/enroll", status_code=status.HTTP_201_CREATED)
async def enroll_user(user_in: UserCreateDTO, repo: UserRepository = Depends(get_user_repo)):
    """Registers a new user into the system."""
    existing_user = await repo.get_by_username(user_in.username)
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    # Hash password and save
    hashed_pw = get_password_hash(user_in.password)
    saved_user = await repo.create_user(user_in, hashed_pw)
    await repo.session.commit()

    return {"message": "User enrolled successfully", "user_id": saved_user.id}


@user_router.get("/me")
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Takes a token and returns the full profile of the logged-in user."""
    # current_user is already securely fetched from the database by the Bouncer!
    return {"id": current_user.id, "username": current_user.username, "role": current_user.role}
