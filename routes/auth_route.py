from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from config.auth import get_user_repo
from repositories.user_repo import UserRepository
from utils.security import create_access_token, verify_password

auth_router = APIRouter(prefix="/auth", tags=["authentication"])


@auth_router.post("/login")
async def login(form_data: OAuth2PasswordRequestForm = Depends(), repo: UserRepository = Depends(get_user_repo)):
    # 1. Find user by email (OAuth2Form uses 'username' field by default for the identifier)
    user = await repo.get_by_username(form_data.username)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    # 2. Verify password
    if not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    # 3. Print the wristband! Put their email inside it as the "sub" (subject)
    access_token = create_access_token(data={"sub": user.username})

    return {"access_token": access_token, "token_type": "bearer"}
