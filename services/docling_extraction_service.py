import os
import re
from pathlib import Path
from typing import Any, Dict, Final

import httpx

from config.config_setting import settings
from services.document_extraction_service import DocumentExtractionService

ALLOWED_EXTENSIONS: Final[frozenset[str]] = frozenset({
    ".pdf", ".docx",
    ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff",
})
MAX_DOCUMENT_BYTES: Final[int] = 25 * 1024 * 1024
IMAGE_EXTENSIONS: Final[frozenset[str]] = frozenset({
    ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff",
})
MIME_TYPES: Final[Dict[str, str]] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


class DoclingExtractionService(DocumentExtractionService):
    def __init__(self):
        if not settings.DOCLING_SERVICE_URL:
            raise ValueError("DOCLING_SERVICE_URL is not configured.")

        self.service_url = settings.DOCLING_SERVICE_URL.rstrip("/")
        self.timeout = httpx.Timeout(300.0, connect=10.0)

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        basename = Path(filename or "document").name
        safe_name = re.sub(r"[^\w.\-]", "_", basename)
        return safe_name or "document"

    @staticmethod
    def _conversion_options(ext: str) -> Dict[str, str]:
        """
        Request markdown-only output. OCR is enabled only for image inputs;
        enrichment features stay disabled to avoid inflated downstream payloads.
        """
        if ext in IMAGE_EXTENSIONS:
            from_format = "image"
            do_ocr = "true"
        elif ext == ".pdf":
            from_format = "pdf"
            do_ocr = "false"
        else:
            from_format = "docx"
            do_ocr = "false"

        return {
            "from_formats": from_format,
            "to_formats": "md",
            "do_ocr": do_ocr,
            "include_images": "false",
            "include_page_images": "false",
            "do_picture_description": "false",
            "do_formula_enrichment": "false",
            "do_code_enrichment": "false",
            "abort_on_error": "true",
        }

    @staticmethod
    def _extract_markdown(payload: Dict[str, Any]) -> str:
        document_payload = payload.get("document")
        if not isinstance(document_payload, dict):
            return ""

        for key in ("md_content", "text_content"):
            content = document_payload.get(key)
            if isinstance(content, str) and content.strip():
                return content.strip()

        return ""

    async def extract_text(self, document: bytes, filename: str) -> str:
        if not document:
            raise ValueError("Document payload cannot be empty.")

        if len(document) > MAX_DOCUMENT_BYTES:
            raise ValueError(
                f"Document exceeds the {MAX_DOCUMENT_BYTES // (1024 * 1024)}MB upload limit."
            )

        safe_filename = self._sanitize_filename(filename)
        _, ext = os.path.splitext(safe_filename.lower())
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(
                f"Unsupported format '{ext}'. Allowed: PDF, DOCX, PNG, JPG, JPEG, WEBP, TIF, TIFF."
            )

        mime_type = MIME_TYPES[ext]

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    self.service_url,
                    files={"files": (safe_filename, document, mime_type)},
                    data=self._conversion_options(ext),
                )
            except httpx.RequestError as exc:
                raise RuntimeError("Failed to reach the Docling extraction service.") from exc

            if response.status_code != 200:
                raise ValueError(
                    f"Docling extraction failed with status {response.status_code}."
                )

            markdown_result = self._extract_markdown(response.json())
            if not markdown_result:
                raise ValueError("Docling returned empty markdown content.")

            return self.clean_markdown_layout(markdown_result)

    def clean_markdown_layout(self, text: str) -> str:
        """
        Normalize layout artifacts while preserving markdown table structure.
        """
        if not text:
            return ""

        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(
            r"(?i)^\s*(page\s*\d+(\s*of\s*\d+)?|─+\s*page\s*\d+\s*─+)\s*$",
            "",
            text,
            flags=re.MULTILINE,
        )

        lines = [line.strip() for line in text.split("\n")]
        cleaned_lines = []
        for line in lines:
            if "|" in line:
                cleaned_lines.append(line)
            else:
                cleaned_lines.append(re.sub(r"[ \t]+", " ", line))

        text = "\n".join(cleaned_lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


extraction_service = DoclingExtractionService()
