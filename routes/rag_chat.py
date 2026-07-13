import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from config.database_config import db as db_config
from models.rag_schema import ChatQueryRequest, ChatQueryResponse
from repositories.rag_repository import RAGRepository
from rag_engine.policy_rag_engine import rag_engine_service
from services.rag_chat_service import build_chat_response, generate_grounded_answer
from config.auth import get_current_user
from models.user import User
logger = logging.getLogger("uvicorn.error")

router = APIRouter(prefix="/api/v1/chat", tags=["RAG Chat Engine"])

@router.post("/query", response_model=ChatQueryResponse, status_code=status.HTTP_200_OK)
async def query_policy_chatbot(
    request: ChatQueryRequest,
    session: AsyncSession = Depends(db_config.get_session),
    current_user: User = Depends(get_current_user)
) -> ChatQueryResponse:
    """
    Accepts an insurance-specific question, converts it to a vector, 
    extracts the top matching clauses via pgvector, and returns a grounded response.
    """
    try:
        query_vector = await rag_engine_service.generate_text_embedding(request.prompt)
        
        rag_repo = RAGRepository(session)
        matching_chunks = await rag_repo.query_similar_policy_contexts(
            policy_id=request.policy_id,
            query_embedding=query_vector,
            user_id=current_user.id,
            limit=4,
        )
        
        if not matching_chunks:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No corresponding policy document chunks found for your account.",
            )
            
        citations = [row[0] for row in matching_chunks]
        answer = await generate_grounded_answer(request.prompt, citations)
        return build_chat_response(request.prompt, citations, answer)
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"RAG Chatbot route hit a processing exception: {str(exc)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fatal exception encountered across conversational RAG pipelines: {str(exc)}"
        )
