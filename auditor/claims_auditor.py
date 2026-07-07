import json
from typing import Any, Dict

from google import genai
from google.genai import types

from auditor.audit_report_schema import AuditReportSchema
from enums.insurance_plan import PLAN_TYPE_LABELS, Geography, PlanType


class ClaimsAuditor:
    def __init__(self):
        self.client = genai.Client()
        self.model_name = "gemini-2.5-flash"

    @staticmethod
    def _build_audit_rules(geography: Geography, plan_type: PlanType) -> str:
        plan_label = PLAN_TYPE_LABELS[plan_type]

        if geography == Geography.INDIA:
            if plan_type == PlanType.CMCHIS:
                return (
                    f"This is an Indian [{plan_type.value}] ({plan_label}) government health insurance scheme claim.\n"
                    "Apply these CMCHIS-specific compliance checks:\n"
                    "1. Verify the treating facility appears empanelled or network-authorized in the policy document.\n"
                    "2. Match procedure or package codes and billed amounts against CMCHIS package-rate tables or ceilings in the policy.\n"
                    "3. Confirm beneficiary identifiers are present (e.g. UHID, CMCHIS enrollment ID, family card, or scheme reference number).\n"
                    "4. Flag missing pre-authorization, government-hospital referral, or PHC referral when tertiary or specialist care is claimed.\n"
                    "5. Verify claimed services fall within covered packages; flag uncovered or upgraded procedures as violations.\n"
                    "6. Use INR amounts as stated on the claim; do not assume USD billing conventions."
                )
            return (
                f"This is an Indian [{plan_type.value}] ({plan_label}) government health insurance scheme claim.\n"
                "Apply these NHIS-specific compliance checks:\n"
                "1. Verify the provider or hospital is empanelled under the NHIS network defined in the policy.\n"
                "2. Match procedure categories and package tariffs against NHIS rate schedules or benefit ceilings in the policy.\n"
                "3. Confirm eligibility references are present (e.g. BPL card, ration card, NHIS enrollment ID, or beneficiary number).\n"
                "4. Flag missing referral from district hospital, PHC, or authorized first-contact facility when required for tertiary care.\n"
                "5. Verify claimed amounts do not exceed per-procedure or annual limits documented in the policy.\n"
                "6. Use INR amounts as stated on the claim; do not assume USD billing conventions."
            )

        if plan_type == PlanType.HMO:
            return (
                f"This is a Western [{plan_type.value}] ({plan_label}) commercial health plan claim.\n"
                "Apply these HMO-specific compliance checks:\n"
                "1. Verify any specialist consultation or treatment line has an accompanying PCP referral ID or authorization.\n"
                "2. Match itemized charge rows against in-network allowable amounts, copay grids, or coinsurance charts in the policy.\n"
                "3. Flag out-of-network services unless the policy explicitly documents an exception.\n"
                "4. Verify deductible and copay math against the EOC benefit tables."
            )

        return (
            f"This is a Western [{plan_type.value}] ({plan_label}) commercial health plan claim.\n"
            "Apply these PPO-specific compliance checks:\n"
            "1. Identify in-network vs out-of-network providers and apply the correct allowable amount tier from the policy.\n"
            "2. Match billed charges against allowed amounts, deductibles, coinsurance, and out-of-pocket maximums.\n"
            "3. PCP referral is not mandatory, but flag services that require prior authorization when the policy says so.\n"
            "4. Flag balance billing or charges above the plan's allowed amount for in-network care."
        )

    def _build_system_instruction(self, geography: Geography, plan_type: PlanType) -> str:
        region_rules = self._build_audit_rules(geography, plan_type)
        return (
            "You are an enterprise health insurance compliance auditor engine. "
            "Audit the operational claim form by cross-referencing it against the provided master policy markdown.\n"
            f"Geography: {geography.value}. Plan scheme: {plan_type.value}.\n"
            f"{region_rules}\n"
            "Universal rules for all geographies:\n"
            "1. Do not assume or extrapolate data missing from the claim or policy.\n"
            "2. Record every mismatch in the violations array with clear severity.\n"
            "3. Paste the exact supporting text or table string from the policy inside 'policy_citation'.\n"
            "4. Compute total_billed_amount and expected_patient_responsibility from the claim data using the policy rules.\n"
            "5. Set audit_status to VALID when the claim follows the policy, NEEDS_REVIEW when issues need human follow-up, "
            "or INVALID when the claim clearly does not comply."
        )

    async def execute_claim_audit(
        self,
        policy_markdown: str,
        claim_markdown: str,
        geography: str,
        plan_type: str,
    ) -> Dict[str, Any]:
        if not policy_markdown or not claim_markdown:
            raise ValueError("Master policy reference truth and claim metadata layouts cannot be empty frames.")

        geo = Geography(geography.upper())
        plan = PlanType(plan_type.upper())

        system_instruction = self._build_system_instruction(geo, plan)
        prompt_payload = (
            f"### GEOGRAPHY: {geo.value}\n"
            f"### PLAN SCHEME: {plan.value} ({PLAN_TYPE_LABELS[plan]})\n\n"
            f"### REFERENCE POLICY CONTRACT SPECIFICATIONS:\n{policy_markdown}\n\n"
            f"### INCOMING OPERATIONAL CLAIM DETAILS FOR COMPLIANCE MATCHING:\n{claim_markdown}\n\n"
            "Perform the cross-audit match now and output using the required JSON schema matrix rules."
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt_payload,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    response_mime_type="application/json",
                    response_schema=AuditReportSchema,
                    temperature=0.0,
                ),
            )

            return json.loads(response.text)

        except Exception as api_error:
            raise RuntimeError(f"Cognitive AI auditing pipeline failed at network endpoint: {str(api_error)}")


claims_auditor_service = ClaimsAuditor()
