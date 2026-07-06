import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession
from google import genai

from config.database_config import db as db_config
from models.rag_schema import ChatQueryRequest, ChatQueryResponse
from repositories.rag_repository import RAGRepository
from rag_engine.policy_rag_engine import rag_engine_service
from config.auth import get_current_user
from models.user import User
from config.config_setting import settings
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
        # 1. Convert the user's incoming question into the same embedding space as indexed chunks
        query_vector = await rag_engine_service.generate_text_embedding(request.prompt)
        
        # 2. Query our pgvector index to find the top 4 most matching policy markdown blocks
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
            
        # 3. Compile the matching text blocks and preserve citations for validation auditing
        citations = [row[0] for row in matching_chunks]
        context_window = "\n\n---\n\n".join(citations)
        
        # 4. Construct the strict RAG instruction box for the reasoning model
        system_instruction = (
            "You are an expert health insurance assistant. Your sole job is to answer the user's question "
            "using ONLY the verified policy data fragments provided in the reference context window.\n"
            "Rules:\n"
            "1. If the context window does not contain the answer, state explicitly: 'I cannot verify that answer based on the loaded policy contract parameters.'\n"
            "2. Do not utilize outside knowledge or extrapolate statistics.\n"
            "3. Maintain absolute accuracy regarding dollar values, percentage copays, and referral constraints."
        )
        
        prompt_payload = (
            f"### VERIFIED POLICY REFERENCE CONTEXT:\n"
            f"{context_window}\n\n"
            f"### USER CONVERSATIONAL PROMPT:\n"
            f"{request.prompt}\n\n"
            f"Formulate your grounded response now:"
        )
        
        # 5. Execute the grounded inference request via the global GenAI client pool
        # We leverage gemini-2.5-flash for real-time latency optimization
        genai_client = genai.Client()
        response = genai_client.models.generate_content(
            model=settings.GEMINI_RAG_MODEL,
            contents=prompt_payload,
            config={"system_instruction": system_instruction, "temperature": 0.0}
        )
        
        return ChatQueryResponse(
            answer=response.text,
            retrieved_citations=citations
        )
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"RAG Chatbot route hit a processing exception: {str(exc)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fatal exception encountered across conversational RAG pipelines: {str(exc)}"
        )