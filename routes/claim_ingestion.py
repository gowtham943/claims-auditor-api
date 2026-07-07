import uuid
import logging
from datetime import datetime, timezone
from typing import Any, Dict
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, status, BackgroundTasks
from sqlmodel.ext.asyncio.session import AsyncSession

from enums.pipeline_step import PipelineStep
from enums.submission_status import AUDIT_STATUS_LABELS, SubmissionStatus
from config.database_config import db as db_config
from ws_manager.connection_manager import socket_manager
from repositories.policy_repo import PolicyRepository
from repositories.claim_repo import ClaimRepository
from models.schema import (
    ClaimAuditDetailDTO,
    ClaimAuditSummaryDTO,
    ClaimCreateDTO,
    ClaimStatusUpdateDTO,
)
from services.docling_extraction_service import extraction_service
from auditor.claims_auditor import claims_auditor_service
from config.auth import get_current_user
from models.user import User
logger = logging.getLogger("uvicorn.error")

claim_ingestion_router = APIRouter(prefix="/api/v1/ingestion/claim", tags=["Ingestion Automation Engine"])


def _build_audit_summary(claim, policy_plan_name: str) -> ClaimAuditSummaryDTO:
    metadata = claim.claim_metadata or {}
    summary = metadata.get("audit_report_summary", {})
    violations = summary.get("violations", [])

    return ClaimAuditSummaryDTO(
        id=claim.id,
        patient_name=claim.patient_name,
        policy_id=claim.policy_id,
        policy_plan_name=policy_plan_name,
        audit_status=summary.get("audit_status", str(claim.status)),
        total_billed_amount=float(summary.get("total_billed_amount", 0)),
        expected_patient_responsibility=float(summary.get("expected_patient_responsibility", 0)),
        violation_count=len(violations),
        audited_at=metadata.get("audited_at"),
    )


def _build_audit_detail(claim, policy_plan_name: str) -> ClaimAuditDetailDTO:
    metadata = claim.claim_metadata or {}
    summary = metadata.get("audit_report_summary", {})

    return ClaimAuditDetailDTO(
        id=claim.id,
        patient_name=claim.patient_name,
        policy_id=claim.policy_id,
        policy_plan_name=policy_plan_name,
        audit_status=summary.get("audit_status", str(claim.status)),
        total_billed_amount=float(summary.get("total_billed_amount", 0)),
        expected_patient_responsibility=float(summary.get("expected_patient_responsibility", 0)),
        violations=summary.get("violations", []),
        raw_claim_markdown=metadata.get("raw_claim_markdown", ""),
    )


async def async_claim_audit_worker(
    claim_id: uuid.UUID,
    policy_id: uuid.UUID,
    user_id: uuid.UUID,
    file_bytes: bytes,
    filename: str,
    plan_type: str,
    geography: str,
    db_session_factory
):
    """
    An isolated background worker task that coordinates extraction, auditing,
    and handles streaming state adjustments over WebSockets without blocking main HTTP routing.
    """
    claim_str = str(claim_id)
    
    try:
        # Step 1: Send Docling Status Message down the WebSocket Megaphone
        await socket_manager.stream_status(
            claim_id=claim_str,
            step=PipelineStep.READING_CLAIM.value,
            message="Reading your claim document.",
        )
        
        claim_markdown = await extraction_service.extract_text(file_bytes, filename)
        
        await socket_manager.stream_status(
            claim_id=claim_str,
            step=PipelineStep.REVIEWING_CLAIM.value,
            message="Checking your claim against the policy rules.",
        )
        
        # Open an isolated background session context to fetch references and update statuses safely
        async with db_session_factory() as session:
            policy_repo = PolicyRepository(session)
            claim_repo = ClaimRepository(session)
            
            # Fetch the reference text truth
            master_policy_markdown = await policy_repo.get_policy_markdown_by_id(
                policy_id=policy_id,
                user_id=user_id,
            )
            if not master_policy_markdown:
                raise ValueError("Policy not found for this user.")
            
            # Request zero-variance structured JSON parameters back from Gemini
            audit_report: Dict[str, Any] = await claims_auditor_service.execute_claim_audit(
                policy_markdown=master_policy_markdown,
                claim_markdown=claim_markdown,
                geography=geography,
                plan_type=plan_type,
            )
            
            # Step 3: Extract structured variables from output schema
            final_status = audit_report.get("audit_status", SubmissionStatus.NEEDS_REVIEW.value)
            
            # Pack extracted outputs inside our metadata object fields
            updated_metadata = {
                "raw_claim_markdown": claim_markdown,
                "claim_payload_character_size": len(claim_markdown),
                "audit_report_summary": audit_report,
                "audited_at": datetime.now(timezone.utc).isoformat(),
            }
            
            # Commit the evaluated states back onto our persistent PostgreSQL data nodes 
            await claim_repo.update_claim_status(
                claim_id=claim_id,
                dto=ClaimStatusUpdateDTO(status=final_status, audit_payload=updated_metadata),
                user_id=user_id,
            )
            await session.commit()

            result_label = AUDIT_STATUS_LABELS.get(
                final_status,
                "Claim check finished",
            )
            await socket_manager.stream_status(
                claim_id=claim_str,
                step=PipelineStep.COMPLETE.value,
                message=f"Check complete. {result_label}.",
                payload={
                    **audit_report,
                    "raw_claim_markdown": claim_markdown,
                },
            )
            
    except Exception as background_err:
        logger.error(f"Async worker encountered a fatal crash trace on Claim {claim_str}: {str(background_err)}")
        
        # Alert connected underwriters about the error pipeline shift immediately
        await socket_manager.stream_status(
            claim_id=claim_str,
            step=PipelineStep.FAILED.value,
            message=f"We could not check this claim. {background_err}",
        )
        
        async with db_session_factory() as session:
            claim_repo = ClaimRepository(session)
            await claim_repo.update_claim_status(
                claim_id=claim_id,
                dto=ClaimStatusUpdateDTO(
                    status=SubmissionStatus.INVALID.value,
                    audit_payload={"fatal_ingestion_error": str(background_err)},
                ),
                user_id=user_id,
            )
            await session.commit()


@claim_ingestion_router.get("/", response_model=list[ClaimAuditSummaryDTO])
async def list_completed_claim_audits(
    session: AsyncSession = Depends(db_config.get_session),
    current_user: User = Depends(get_current_user),
) -> list[ClaimAuditSummaryDTO]:
    """Return completed claim audits owned by the authenticated user."""
    claim_repo = ClaimRepository(session)
    claims = await claim_repo.list_completed_audits_by_user(current_user.id)
    return [
        _build_audit_summary(claim, policy_plan_name)
        for claim, policy_plan_name in claims
    ]


@claim_ingestion_router.get("/{claim_id}", response_model=ClaimAuditDetailDTO)
async def get_claim_audit_detail(
    claim_id: uuid.UUID,
    session: AsyncSession = Depends(db_config.get_session),
    current_user: User = Depends(get_current_user),
) -> ClaimAuditDetailDTO:
    """Return the full audit report for a completed claim."""
    claim_repo = ClaimRepository(session)
    result = await claim_repo.get_completed_audit_by_id(claim_id, current_user.id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Completed audit with ID '{claim_id}' not found.",
        )

    claim, policy_plan_name = result
    return _build_audit_detail(claim, policy_plan_name)


@claim_ingestion_router.post("/", status_code=status.HTTP_202_ACCEPTED)
async def ingest_claim_submission(
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(db_config.get_session),
    policy_id: uuid.UUID = Form(...),
    patient_name: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Accepts raw claims files, validates plan presence, spawns non-blocking 
    background workers, and returns a fast transaction tracker key.
    """
    policy_repo = PolicyRepository(session)
    claim_repo = ClaimRepository(session)
    
    # Pre-flight lookup check: Verify target validating rulebook context exists
    policy_record = await policy_repo.get_policy_by_id(
        policy_id=policy_id,
        user_id=current_user.id,
    )
    if not policy_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target core validation rules template with ID '{policy_id}' not found."
        )
        
    try:
        # Pre-allocate tracking token identities immediately
        claim_id = uuid.uuid4()
        file_bytes = await file.read()
        filename = file.filename
        
        # Create initial staging registration record marked as PENDING
        dto = ClaimCreateDTO(
            id=claim_id,
            policy_id=policy_id,
            patient_name=patient_name,
            claim_metadata={"state": "Staged for worker queue allotment."}
        )
        
        await claim_repo.create_submission(dto=dto, user_id=current_user.id)
        await session.commit()
        
        # Hand heavy layout parsing and model calling to an asynchronous task thread 
        # Inject our factory session creator pool so the worker can spin up its own safe isolated database links
        background_tasks.add_task(
            async_claim_audit_worker,
            claim_id=claim_id,
            policy_id=policy_id,
            user_id=current_user.id,
            file_bytes=file_bytes,
            filename=filename,
            plan_type=policy_record.plan_type,
            geography=policy_record.geography,
            db_session_factory=db_config.session_factory,
        )
        
        # Return an instantaneous 202 response containing the unique identifier key
        return {
            "status": "accepted",
            "claim_id": str(claim_id),
            "message": "Claim form uploaded and staged for asynchronous background tracking analysis queues."
        }
        
    except Exception as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fatal exception tracked during claim initialization handshakes: {str(exc)}"
        )