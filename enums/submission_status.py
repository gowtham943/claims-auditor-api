from enum import Enum


class SubmissionStatus(str, Enum):
    PENDING = "PENDING"
    VALID = "VALID"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INVALID = "INVALID"


AUDIT_STATUS_LABELS: dict[str, str] = {
    SubmissionStatus.VALID.value: "Valid claim",
    SubmissionStatus.NEEDS_REVIEW.value: "Claim has issues that need review",
    SubmissionStatus.INVALID.value: "Invalid claim",
}
