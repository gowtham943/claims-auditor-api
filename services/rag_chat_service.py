import logging
from typing import List

from google import genai

from config.config_setting import settings
from models.rag_schema import ChatQueryResponse

logger = logging.getLogger("uvicorn.error")


def build_rag_prompt(prompt: str, citations: List[str]) -> tuple[str, str]:
    context_window = "\n\n---\n\n".join(citations)
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
        f"{prompt}\n\n"
        f"Formulate your grounded response now:"
    )
    return system_instruction, prompt_payload


async def generate_grounded_answer(prompt: str, citations: List[str]) -> str:
    if not citations:
        raise ValueError("At least one citation chunk is required for grounded generation.")

    system_instruction, prompt_payload = build_rag_prompt(prompt, citations)
    genai_client = genai.Client()
    response = genai_client.models.generate_content(
        model=settings.GEMINI_RAG_MODEL,
        contents=prompt_payload,
        config={"system_instruction": system_instruction, "temperature": 0.0},
    )
    return response.text


def build_chat_response(prompt: str, citations: List[str], answer: str) -> ChatQueryResponse:
    return ChatQueryResponse(answer=answer, retrieved_citations=citations)
