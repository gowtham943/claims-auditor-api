import re
import uuid
from typing import List, Dict
from google import genai
from google.genai import types
from config.config_setting import settings
from models.policy_chunks import PolicyChunk
import asyncio
import logging

logger = logging.getLogger("uvicorn.error")


class PolicyRAGEngine:
    def __init__(self):
        self.client = genai.Client()
        self.embedding_model = settings.GEMINI_EMBEDDING_MODEL
        self.embedding_dimension = settings.GEMINI_EMBEDDING_DIMENSION

    def _embed_config(self) -> types.EmbedContentConfig | None:
        if self.embedding_dimension >= 3072:
            return None
        return types.EmbedContentConfig(
            output_dimensionality=self.embedding_dimension,
        )

    async def generate_text_embedding(self, text: str) -> List[float]:
        response = self.client.models.embed_content(
            model=self.embedding_model,
            contents=text,
            config=self._embed_config(),
        )
        return response.embeddings[0].values

    async def _embed_batch_with_retry(self, batch_texts: List[str], *, batch_start: int):
        retries = 5
        delay = 60.0

        while retries > 0:
            try:
                return self.client.models.embed_content(
                    model=self.embedding_model,
                    contents=batch_texts,
                    config=self._embed_config(),
                )
            except Exception as api_err:
                err_str = str(api_err)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    retries -= 1
                    logger.warning(
                        "Embedding rate limit at batch index %s. Retries left: %s. Backing off %.1fs...",
                        batch_start,
                        retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    delay *= 1.5
                    continue
                raise api_err

        raise RuntimeError(
            f"Failed to calculate embeddings for batch index {batch_start} after maximum retry attempts."
        )

    def segment_markdown_by_headers(self, markdown_text: str) -> List[Dict[str, str]]:
        """
        A layout-aware structural chunker that segments data at Markdown heading levels
        while keeping section contextual blocks unbroken for the vector DB.
        """
        sections = []
        # Matches markdown headers (e.g., # Section)
        pattern = r"(^#{1,4}\s+.*$)"
        parts = re.split(pattern, markdown_text, flags=re.MULTILINE)

        current_heading = "Introduction/General Terms"

        for part in parts:
            part_stripped = part.strip()
            if not part_stripped:
                continue

            if re.match(pattern, part_stripped):
                current_heading = part_stripped
            else:
                # Group section bodies with their active header paths
                sections.append({
                    "heading": current_heading,
                    "text": f"{current_heading}\n{part_stripped}",
                })
        return sections

    """
    async def chunk_and_index_policy(
        self, 
        policy_id: uuid.UUID, 
        markdown_text: str
    ) -> List[PolicyChunk]:
        text_segments = self.segment_markdown_by_headers(markdown_text)
        staged_chunks = []
        
        for segment in text_segments:
            chunk_body = segment["text"]
            
            # Fetch embedding values asynchronously
            vector_array = await self.generate_text_embedding(chunk_body)
            
            staged_chunks.append(
                PolicyChunk(
                    id=uuid.uuid4(),
                    policy_id=policy_id,
                    chunk_text=chunk_body,
                    heading_context=segment["heading"],
                    embedding=vector_array
                )
            )

            # RATELIMIT THROTTLE FIX: Wait 4.5 seconds between chunks to stay under the Free Tier limits.
            # 15 RPM means 1 request every 4 seconds. 4.5s keeps us perfectly safe!
            await asyncio.sleep(4.5)
        return staged_chunks

    """
    async def chunk_and_index_policy(self, policy_id: uuid.UUID, markdown_text: str) -> List[PolicyChunk]:
        """
        Processes massive document layouts by chunking text and calculating embeddings 
        using micro-batches. Includes a self-healing retry block with exponential backoff 
        to stay resilient against 429 RPM/TPM rate limits on Free Tier keys.
        """
        text_segments = self.segment_markdown_by_headers(markdown_text)
        staged_chunks = []
        
        if not text_segments:
            return []

        BATCH_SIZE = 5
        total_segments = len(text_segments)
        
        logger.info(f"Total layout segments extracted: {total_segments}. Initiating resilient micro-batch vector engine...")

        for i in range(0, total_segments, BATCH_SIZE):
            sub_batch = text_segments[i:i + BATCH_SIZE]
            batch_texts = [segment["text"] for segment in sub_batch]

            response = await self._embed_batch_with_retry(batch_texts, batch_start=i)

            # Model mapping matrix construction upon successful API response
            for j, segment in enumerate(sub_batch):
                vector_array = response.embeddings[j].values
                
                staged_chunks.append(
                    PolicyChunk(
                        id=uuid.uuid4(),
                        policy_id=policy_id,
                        chunk_text=segment["text"],
                        heading_context=segment["heading"],
                        embedding=vector_array
                    )
                )
            
            # Tiny baseline pacing delay to spread requests evenly
            if i + BATCH_SIZE < total_segments:
                await asyncio.sleep(1.0)

        logger.info(f"Successfully vectorized and indexed all {len(staged_chunks)} layout items safely!")
        return staged_chunks

# Global singular engine hook
rag_engine_service = PolicyRAGEngine()