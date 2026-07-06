import uuid
import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status, BackgroundTasks
from sqlmodel.ext.asyncio.session import AsyncSession

from config.config_setting import settings
from config.database_config import db as db_config
from ws_manager.connection_manager import socket_manager
from repositories.policy_repo import PolicyRepository
from repositories.rag_repository import RAGRepository
from models.schema import PolicyCreateDTO, PolicySummaryDTO
from services.docling_extraction_service import extraction_service
from rag_engine.policy_rag_engine import rag_engine_service
from config.auth import get_current_user
from models.user import User
logger = logging.getLogger("uvicorn.error")

policy_ingestion_router = APIRouter(prefix="/api/v1/ingestion/policy", tags=["Ingestion Automation Engine"])


async def async_policy_extraction_worker(
    policy_id: uuid.UUID,
    user_id: uuid.UUID,
    dto: PolicyCreateDTO,
    file_bytes: bytes,
    filename: str,
    db_session_factory
):
    """
    An isolated background worker task that handles long-running master policy parsing,
    text normalization cleaning, and streams live progress logs to the UI via WebSockets.
    """
    policy_str = str(policy_id)
    
    try:
        # Step 1: Tell user via WebSocket that Docling is crunching pages
        await socket_manager.stream_status(
            claim_id=policy_str,  # We reuse the ID channel to group socket messages
            step="PARSING_POLICY",
            message="Docling is reading the master layout, headers, and cost tables. This may take a minute..."
        )
        
        # Hits the docling microservice container and triggers our text normalization cleanup pipeline
        extracted_markdown = await extraction_service.extract_text(file_bytes, filename)
        
        await socket_manager.stream_status(
            claim_id=policy_str,
            step="VECTOR_INDEXING",
            message=f"Slicing Markdown layout by heading nodes and generating {settings.GEMINI_EMBEDDING_MODEL} vectors..."
        )
        
        # Generate PolicyChunk rows with embeddings sized to GEMINI_EMBEDDING_DIMENSION
        vector_chunks = await rag_engine_service.chunk_and_index_policy(
            policy_id=policy_id, 
            markdown_text=extracted_markdown
        )

        # Step 3: Save clean text results onto our target PostgreSQL node
        await socket_manager.stream_status(
            claim_id=policy_str,
            step="SAVING_DATA",
            message="Extraction complete! Saving clean Markdown text parameters into the database cache..."
        )
        
        async with db_session_factory() as session:
            policy_repo = PolicyRepository(session)
            rag_repo = RAGRepository(session)
            
            # Formally commit the text into the database row stub we created earlier
            await policy_repo.update_policy_markdown_layout(
                policy_id=policy_id,
                raw_markdown=extracted_markdown,
                user_id=user_id,
            )

            await rag_repo.save_chunks_bulk(vector_chunks)

            await session.commit()
            
        # Step 4: Tell the UI we are 100% complete
        await socket_manager.stream_status(
            claim_id=policy_str,
            step="COMPLETED",
            message="Master policy rules parsed, vectorized, and cached! Context system fully live.",
            payload={
                "total_layout_characters": len(extracted_markdown),
                "generated_vector_chunks": len(vector_chunks)
            }
        )
        
    except Exception as background_err:
        logger.error(f"Policy background task crashed on ID {policy_str}: {str(background_err)}")
        
        await socket_manager.stream_status(
            claim_id=policy_str,
            step="FAILED",
            message=f"Policy processing failed: {str(background_err)}"
        )
        
        # Soft-delete or update status to flag an ingestion error
        async with db_session_factory() as session:
            policy_repo = PolicyRepository(session)
            await policy_repo.mark_policy_as_failed(
                policy_id=policy_id,
                error_notes=str(background_err),
                user_id=user_id,
            )
            await session.commit()


@policy_ingestion_router.get("/", response_model=list[PolicySummaryDTO])
async def list_ingested_policies(
    session: AsyncSession = Depends(db_config.get_session),
    current_user: User = Depends(get_current_user),
) -> list[PolicySummaryDTO]:
    """Return completed policy rulebooks owned by the authenticated user."""
    policy_repo = PolicyRepository(session)
    policies = await policy_repo.list_ingested_policies_by_user(current_user.id)
    return [
        PolicySummaryDTO(
            id=policy.id,
            plan_name=policy.plan_name,
            plan_type=policy.plan_type,
            source_url=policy.source_url,
        )
        for policy in policies
    ]


@policy_ingestion_router.post("/", status_code=status.HTTP_202_ACCEPTED)
async def ingest_policy_rulebook(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(db_config.get_session),
    plan_name: str = Form(...),
    plan_type: str = Form(...),
    source_url: str | None = Form(None),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Stages incoming master reference materials instantly, delegates the heavy multi-page 
    Docling layout parsing tasks to a background thread, and returns a tracking token key.
    """
    try:
        policy_id = uuid.uuid4()
        file_bytes = await file.read()
        
        dto = PolicyCreateDTO(
            id=policy_id,
            plan_name=plan_name,
            plan_type=plan_type,
            source_url=source_url
        )
        
        # 1. Store an initial empty row stub placeholder inside PostgreSQL
        policy_repo = PolicyRepository(session)
        await policy_repo.save_policy(
            dto=dto,
            raw_markdown="",
            user_id=current_user.id,
        )
        await session.commit()
        
        # 2. Hand off the heavy, time-consuming file parse to a background thread pool
        background_tasks.add_task(
            async_policy_extraction_worker,
            policy_id=policy_id,
            user_id=current_user.id,
            dto=dto,
            file_bytes=file_bytes,
            filename=file.filename,
            db_session_factory=db_config.session_factory,
        )
        
        # 3. Respond instantly back to the frontend in milliseconds
        return {
            "status": "accepted",
            "policy_id": str(policy_id),
            "message": "Master document submitted. Ingestion and parsing initiated in background loops."
        }
        
    except Exception as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fatal exception tracked across initialization pipelines: {str(exc)}"
        )