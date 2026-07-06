from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config.config_setting import settings


def get_password_hash(password: str) -> str:
    """Takes a raw password, generates a secure salt, and returns a string hash."""
    # Bcrypt requires passwords to be converted to bytes before hashing
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password=pwd_bytes, salt=salt)

    # Convert the bytes back to a string so it can be saved in the database
    return hashed_password.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Checks if a raw password matches the saved hash."""
    password_bytes = plain_password.encode("utf-8")
    hashed_password_bytes = hashed_password.encode("utf-8")

    return bcrypt.checkpw(password=password_bytes, hashed_password=hashed_password_bytes)


def create_access_token(data: dict) -> str:
    """Prints the JWT Wristband."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt
