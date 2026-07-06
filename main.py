from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.config_setting import settings
from config.database_config import db
from routes.health_Check import health_check_router
from routes.claim_ingestion import claim_ingestion_router
from routes.policy_ingestion import policy_ingestion_router
from routes.rag_chat import router
from routes.user_route import user_router
from routes.websocket import ws_router
from routes.auth_route import auth_router
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    print("Shutting down API...")
    await db.close_database()


app = FastAPI(title="Claims Auditor API", version="0.1.0")

app.include_router(health_check_router)
app.include_router(claim_ingestion_router)
app.include_router(policy_ingestion_router)
app.include_router(router)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(ws_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)