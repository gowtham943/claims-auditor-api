from pydantic import BaseModel, Field
import uuid

class ChatQueryRequest(BaseModel):
    policy_id: uuid.UUID = Field(..., description="The unique ID of the target insurance policy rulebook.")
    prompt: str = Field(..., description="The natural language question from the user (e.g., 'What is the specialist copay?').")

class ChatQueryResponse(BaseModel):
    answer: str = Field(..., description="The context-grounded response derived from verified policy sections.")
    retrieved_citations: list[str] = Field(..., description="The exact markdown blocks pulled from the vector DB used to ground the model.")