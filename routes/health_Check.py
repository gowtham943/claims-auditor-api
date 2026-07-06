from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from config.database_config import db
from fastapi import Depends, HTTPException, status

health_check_router = APIRouter(prefix="/health", tags=["health"])

@health_check_router.get("/", status_code=status.HTTP_200_OK)
async def health_check(session: AsyncSession = Depends(db.get_session)):
    try:
        await session.execute(text("SELECT 1"))
        return {"status": "healthy", "message": "API is running"}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
