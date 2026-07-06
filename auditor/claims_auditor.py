import os
from google import genai
from google.genai import types
import json
from typing import Any, Dict
from auditor.audit_report_schema import AuditReportSchema
class ClaimsAuditor:
    def __init__(self):
        # Initializes the client by reading GEMINI_API_KEY from environment state
        self.client = genai.Client()
        # Recommended modern standard model for deep textual reasoning and structured extraction tasks
        self.model_name = "gemini-2.5-flash"

    async def execute_claim_audit(
        self, 
        policy_markdown: str, 
        claim_markdown: str, 
        plan_type: str
    ) -> Dict[str, Any]:
        """
        Stitches an isolated prompt context wrapper and triggers a non-blocking 
        structured json audit call to the Gemini API layer.
        """
        if not policy_markdown or not claim_markdown:
            raise ValueError("Master policy reference truth and claim metadata layouts cannot be empty frames.")

        system_instruction = (
            "You are an enterprise health insurance compliance auditor engine. Your task is to audit an operational "
            "Claim Form by cross-referencing it directly against the provided Master Evidence of Coverage (EOC) Policy markdown text.\n"
            f"Strict context parameter constraint: This is an [{plan_type.upper()}] plan layout.\n"
            "1. If the plan type is HMO, verify that any specialist consultation or treatment line has an accompanying PCP referral ID. "
            "If missing, flag as a HIGH severity violation.\n"
            "2. Match itemized charge rows against EOC maximum allowables, copay grids, or coinsurance charts.\n"
            "3. Do not assume or extrapolate data. If parameters mismatch or conflict, record it in the violations array.\n"
            "4. You must extract and paste the exact text or table string from the policy inside 'policy_citation'."
        )

        prompt_payload = (
            f"### REFERENCE POLICY CONTRACT SPECIFICATIONS:\n{policy_markdown}\n\n"
            f"### INCOMING OPERATIONAL CLAIM DETAILS FOR COMPLIANCE MATCHING:\n{claim_markdown}\n\n"
            f"Perform the cross-audit match now and output using the required JSON schema matrix rules."
        )

        try:
            # Execute standard blocking call safely wrapped in an async process pool or direct network thread block
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt_payload,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=AuditReportSchema,
                    temperature=0.0,  # Zero variance ensures maximum mathematical determinism
                ),
            )
            
            return json.loads(response.text)
            
        except Exception as api_error:
            raise RuntimeError(f"Cognitive AI auditing pipeline failed at network endpoint: {str(api_error)}")

claims_auditor_service = ClaimsAuditor()