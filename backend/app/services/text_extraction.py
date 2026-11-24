"""
Text extraction from PDF (PyMuPDF / fitz) and DOCX (python-docx).

Returns plain text string. For PDFs we also keep the option to pass the file
bytes directly to Gemini if preferred — but text extraction gives us full
control and works for both formats uniformly.
"""

import fitz  # PyMuPDF
from docx import Document
from io import BytesIO


async def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from a PDF using PyMuPDF."""
    text_parts = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "\n".join(text_parts).strip()


async def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text from a DOCX using python-docx."""
    doc = Document(BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    # Include tables
    for table in doc.tables:
        for row in table.rows:
            row_text = [cell.text for cell in row.cells if cell.text.strip()]
            if row_text:
                paragraphs.append(" | ".join(row_text))
    return "\n".join(paragraphs).strip()


async def extract_text(file_bytes: bytes, content_type: str) -> str:
    """Dispatch to the right extractor based on content type."""
    ct = content_type.lower()
    if "pdf" in ct:
        return await extract_text_from_pdf(file_bytes)
    if "word" in ct or "officedocument" in ct:
        return await extract_text_from_docx(file_bytes)
    # Fallback: try PDF first, then DOCX
    try:
        return await extract_text_from_pdf(file_bytes)
    except Exception:
        return await extract_text_from_docx(file_bytes)
