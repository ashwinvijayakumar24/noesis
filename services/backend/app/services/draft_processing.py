"""
Draft Processing Service

Handles draft ingestion, text extraction from multiple formats (PDF, DOCX, TXT),
and structural analysis of research drafts.

This service provides the foundation for draft-aware research intelligence by:
- Supporting multiple academic writing formats
- Preserving document structure (sections, paragraphs)
- Extracting metadata for analysis pipeline
- Using GROBID for PDF extraction to get structured sections and citations

Requirements: 1.1, 1.2, 1.4
"""

import fitz  # pymupdf for PDF processing (fallback)
from docx import Document  # python-docx for DOCX processing
import json
import time
from typing import Dict, Any, List, Optional
from app.core.supabase_client import supabase
from app.core.config import settings
from app.core.logging_config import get_logger
from app.core.openai_client import get_openai_client, get_completion_params
from app.core.privacy import safe_exception, strip_manuscript_content_from_structure
from app.services.grobid_client import get_grobid_client
from app.services.draft_errors import (
    DraftProcessingError,
    FileTooLargeError,
    FileTooSmallError,
    FileEmptyError,
    UnsupportedFormatError,
    PDFExtractionError,
    DOCXExtractionError,
    TextEncodingError,
    StructureAnalysisError,
    StorageDownloadError,
    validate_and_suggest,
    wrap_extraction_error
)
import datetime
import re
import asyncio

logger = get_logger(__name__)

# ============================================
# Text Extraction Functions
# ============================================

async def extract_text_from_pdf(file_bytes: bytes) -> Dict[str, Any]:
    """
    Extract structured data from PDF file bytes using GROBID.

    Returns structured data including sections, references, and metadata
    which is much more valuable for draft analysis than plain text.

    Args:
        file_bytes: PDF file as bytes

    Returns:
        Dictionary with structured data:
        - full_text: Complete document text
        - title: Draft title (if extractable)
        - sections: List of sections with titles, types, and content
        - references: List of bibliography entries
        - metadata: Additional metadata from GROBID

    Raises:
        PDFExtractionError: If PDF is corrupted or cannot be read
        FileEmptyError: If PDF contains no extractable text
    """
    try:
        # Use GROBID for structured extraction
        grobid = get_grobid_client()
        structured_data = await grobid.process_pdf(file_bytes)

        if not structured_data["full_text"].strip():
            raise FileEmptyError('pdf')

        logger.info(
            f"Extracted {len(structured_data['full_text'])} characters from PDF using GROBID. "
            f"Sections: {len(structured_data.get('sections', []))}, "
            f"References: {len(structured_data.get('references', []))}"
        )

        return structured_data

    except FileEmptyError:
        raise  # Re-raise our custom error
    except Exception as e:
        logger.warning(f"GROBID extraction failed: {e}. Falling back to PyMuPDF")
        # Fallback to basic PyMuPDF extraction
        try:
            text = extract_text_from_pdf_fallback(file_bytes)
            return {
                "full_text": text,
                "title": "",
                "sections": [],
                "references": [],
                "metadata": {}
            }
        except Exception as fallback_error:
            logger.error(f"PDF extraction failed completely: {fallback_error}")
            raise PDFExtractionError(str(fallback_error))


def extract_text_from_pdf_fallback(file_bytes: bytes) -> str:
    """
    Fallback: Extract text from PDF using PyMuPDF (basic extraction).
    Used only if GROBID fails.

    Args:
        file_bytes: PDF file as bytes

    Returns:
        Extracted text as string

    Raises:
        PDFExtractionError: If PDF is corrupted or cannot be read
        FileEmptyError: If PDF contains no extractable text
    """
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""

        for page_num, page in enumerate(doc):
            page_text = page.get_text()
            text += page_text

        page_count = doc.page_count
        doc.close()

        if not text.strip():
            raise FileEmptyError('pdf')

        logger.info(f"Extracted {len(text)} characters from PDF ({page_count} pages) using fallback")
        return text

    except FileEmptyError:
        raise  # Re-raise our custom error
    except Exception as e:
        logger.error("PDF extraction failed: %s", safe_exception(e))
        raise PDFExtractionError("PDF extraction failed")


def extract_text_from_docx(file_bytes: bytes) -> str:
    """
    Extract text from DOCX file bytes using python-docx.

    Args:
        file_bytes: DOCX file as bytes

    Returns:
        Extracted text as string with paragraph structure preserved

    Raises:
        DOCXExtractionError: If DOCX is corrupted or cannot be read
        FileEmptyError: If DOCX contains no text content
    """
    try:
        # python-docx requires a file-like object
        from io import BytesIO
        doc = Document(BytesIO(file_bytes))

        # Extract paragraphs with structure preservation
        paragraphs = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:  # Only include non-empty paragraphs
                paragraphs.append(text)

        if not paragraphs:
            raise FileEmptyError('docx')

        # Join paragraphs with double newline to preserve structure
        full_text = "\n\n".join(paragraphs)

        logger.info(f"Extracted {len(full_text)} characters from DOCX ({len(paragraphs)} paragraphs)")
        return full_text

    except FileEmptyError:
        raise  # Re-raise our custom error
    except Exception as e:
        logger.error("DOCX extraction failed: %s", safe_exception(e))
        raise DOCXExtractionError("DOCX extraction failed")


def extract_text_from_txt(file_bytes: bytes) -> str:
    """
    Extract text from plain text file with encoding detection.

    Args:
        file_bytes: Text file as bytes

    Returns:
        Decoded text as string

    Raises:
        TextEncodingError: If file cannot be decoded
        FileEmptyError: If text file is empty
    """
    try:
        # Try UTF-8 first (most common)
        try:
            text = file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            # Fall back to latin-1 (handles most Western encodings)
            try:
                text = file_bytes.decode('latin-1')
            except UnicodeDecodeError:
                # Last resort: try with error handling
                text = file_bytes.decode('utf-8', errors='ignore')
                logger.warning("Text file decoded with errors ignored")

        if not text.strip():
            raise FileEmptyError('txt')

        logger.info(f"Extracted {len(text)} characters from text file")
        return text

    except FileEmptyError:
        raise  # Re-raise our custom error
    except Exception as e:
        logger.error("Text extraction failed: %s", safe_exception(e))
        raise TextEncodingError("Text extraction failed")


async def extract_text(file_bytes: bytes, file_type: str) -> Dict[str, Any]:
    """
    Extract text from file based on type.

    For PDFs, returns structured data from GROBID with sections and references.
    For DOCX and TXT files, returns basic structure with full text.

    Args:
        file_bytes: File content as bytes
        file_type: File extension ('pdf', 'docx', or 'txt')

    Returns:
        Dictionary with extracted data:
        - full_text: Complete document text
        - title: Document title (if available)
        - sections: List of sections (PDFs only via GROBID)
        - references: List of citations (PDFs only via GROBID)
        - metadata: Additional metadata

    Raises:
        UnsupportedFormatError: If file type is unsupported
        DraftProcessingError: If extraction fails (various subtypes)
    """
    file_type = file_type.lower()

    if file_type == 'pdf':
        # Returns structured data from GROBID
        return await extract_text_from_pdf(file_bytes)
    elif file_type == 'docx':
        # Returns plain text, wrap in standard structure
        text = extract_text_from_docx(file_bytes)
        return {
            "full_text": text,
            "title": "",
            "sections": [],
            "references": [],
            "metadata": {"file_type": "docx"}
        }
    elif file_type == 'txt':
        # Returns plain text, wrap in standard structure
        text = extract_text_from_txt(file_bytes)
        return {
            "full_text": text,
            "title": "",
            "sections": [],
            "references": [],
            "metadata": {"file_type": "txt"}
        }
    else:
        raise UnsupportedFormatError(file_type)


# ============================================
# Document Structure Analysis
# ============================================

STRUCTURE_ANALYSIS_PROMPT = """You are an expert at analyzing academic research document structure.

Analyze this draft and extract its structural components. Respond with ONLY valid JSON.

Return this exact structure:
{
  "sections": [
    {
      "title": "Section heading or type",
      "type": "abstract|introduction|methods|results|discussion|conclusion|other",
      "start_position": 0,
      "word_count": 150,
      "has_subsections": false
    }
  ],
  "document_metadata": {
    "has_abstract": true,
    "has_introduction": true,
    "has_conclusion": true,
    "appears_complete": true,
    "primary_structure": "standard|narrative|methodological|other"
  }
}

Guidelines:
- Identify major sections by headings, content, or position
- Classify section types based on content (abstract, intro, methods, results, discussion, conclusion)
- Use "other" for non-standard sections
- Set appears_complete to true if document has standard academic structure
- primary_structure should be:
  - "standard" for typical research papers (intro/methods/results/discussion)
  - "narrative" for essays or reviews
  - "methodological" for method-focused papers
  - "other" for non-standard structures
"""


def analyze_document_structure(draft_text: str) -> Dict[str, Any]:
    """
    Analyze document structure using GPT-4 to identify sections and organization.

    This provides structured information about the draft's organization which is used
    for claim extraction and coverage analysis.

    Args:
        draft_text: Full text of the research draft

    Returns:
        Dictionary containing structural analysis with sections and metadata

    Raises:
        StructureAnalysisError: If analysis fails
    """
    client = get_openai_client()
    if not client:
        raise ValueError("OpenAI API key not configured")

    start_time = time.time()

    try:
        logger.info(f"Analyzing document structure (length: {len(draft_text)} chars)")

        # Use first 8000 characters for structure analysis (sufficient for most papers)
        # This reduces token usage while capturing essential structure
        analysis_text = draft_text[:8000]

        # Note: Temperature removed - GPT-5.2 models use default temperature=1.0
        response = client.chat.completions.create(
            model="gpt-5.2-chat-latest",
            messages=[
                {"role": "system", "content": STRUCTURE_ANALYSIS_PROMPT},
                {"role": "user", "content": f"Analyze this research draft structure:\n\n{analysis_text}"}
            ],
            max_completion_tokens=2000,
            **get_completion_params()  # Enable zero data retention
        )

        structure_json = response.choices[0].message.content
        structure = json.loads(structure_json)

        processing_time = time.time() - start_time
        logger.info(f"Structure analysis completed in {processing_time:.2f}s")
        logger.info(f"Identified {len(structure.get('sections', []))} sections")

        return structure

    except json.JSONDecodeError as e:
        logger.error("Failed to parse structure analysis JSON: %s", safe_exception(e))
        raise StructureAnalysisError("Invalid JSON response")

    except Exception as e:
        logger.error("Structure analysis failed: %s", safe_exception(e))
        raise StructureAnalysisError("Structure analysis failed")


def calculate_word_count(text: str) -> int:
    """
    Calculate word count for text.

    Args:
        text: Text to count words in

    Returns:
        Number of words
    """
    # Split on whitespace and filter empty strings
    words = [w for w in text.split() if w.strip()]
    return len(words)


# ============================================
# Main Draft Processing Pipeline
# ============================================

async def ingest_draft(draft_id: str, project_id: str) -> Dict[str, Any]:
    """
    Complete draft ingestion pipeline.

    Steps:
    1. Fetch draft record from database
    2. Download file from Supabase Storage
    3. Extract text based on file type (PDF/DOCX/TXT)
    4. Analyze document structure using AI
    5. Store analysis results in draft_analysis table
    6. Update draft status to 'analyzed'

    Args:
        draft_id: UUID of the draft
        project_id: UUID of the project

    Returns:
        Success message with processing statistics

    Raises:
        Exception: If any step fails
    """
    try:
        logger.info(f"[INGEST] ========== STARTING DRAFT INGESTION ==========")
        logger.info(f"[INGEST] draft_id={draft_id}, project_id={project_id}")

        # 1. Fetch draft record
        logger.info(f"[INGEST] Step 1: Fetching draft record from database...")
        draft_record = supabase.table("drafts").select("*").eq("id", draft_id).single().execute()

        if not draft_record.data:
            raise ValueError(f"Draft ID {draft_id} not found")

        file_url = draft_record.data["file_url"]
        file_type = draft_record.data["file_type"]
        user_id = draft_record.data["user_id"]
        paper_type = draft_record.data.get("paper_type", "journal_article")
        citation_style = draft_record.data.get("citation_style", "apa")
        logger.info(
            f"[INGEST] ✓ Found draft: file_type={file_type}, user_id={user_id}, "
            f"paper_type={paper_type}, citation_style={citation_style}"
        )

        # Update status to processing
        logger.info(f"[INGEST] Step 2: Updating status to 'processing'...")
        supabase.table("drafts").update({
            "status": "processing",
            "updated_at": datetime.datetime.utcnow().isoformat()
        }).eq("id", draft_id).execute()
        logger.info(f"[INGEST] ✓ Status updated to 'processing'")

        # 2. Download file from Supabase Storage
        logger.info(f"[INGEST] Step 3: Downloading file from Supabase Storage...")
        try:
            # Extract storage path from URL
            path_parts = file_url.split("/drafts/")
            if len(path_parts) < 2:
                raise ValueError("Invalid file URL format")

            storage_path = path_parts[1]
            logger.info("[INGEST] Downloading draft file from storage")

            file_bytes = supabase.storage.from_("drafts").download(storage_path)
            logger.info(f"[INGEST] ✓ Downloaded {len(file_bytes)} bytes")

        except Exception as e:
            logger.error("[INGEST] ✗ Download failed: %s", safe_exception(e))
            raise ValueError("Failed to download file from storage")

        # 3. Extract text based on file type (structured data for PDFs via GROBID)
        logger.info(f"[INGEST] Step 4: Extracting text from {file_type} file...")
        extracted_data = await extract_text(file_bytes, file_type)
        full_text = extracted_data["full_text"]
        logger.info(f"[INGEST] ✓ Extracted {len(full_text)} characters")

        # Start Stage 1 editing in parallel with the heavier analysis path.
        from app.services.stage1_editing import run_stage1_editing
        editing_task = asyncio.create_task(
            run_stage1_editing(
                full_text,
                citation_style=citation_style,
                paper_type=paper_type,
            )
        )

        # 4. Analyze document structure
        # For PDFs, GROBID already provides structure - use that directly
        # For DOCX/TXT, use GPT-4 analysis
        logger.info(f"[INGEST] Step 5: Analyzing document structure...")
        if file_type == 'pdf' and extracted_data.get("sections"):
            logger.info(f"[INGEST] Using GROBID structure ({len(extracted_data['sections'])} sections)")
            # Convert GROBID sections to our structure format
            structure = {
                "sections": [
                    {
                        "id": s.get("id"),
                        "title": s.get("title", ""),
                        "type": s.get("type", "other"),
                        "content": s.get("content", ""),
                        "coordinates": s.get("coordinates", {}),
                        "paragraphs": s.get("paragraphs", []),
                        "start_position": 0,  # GROBID doesn't provide exact positions
                        "word_count": len(s.get("content", "").split()),
                        "has_subsections": False
                    }
                    for s in extracted_data["sections"]
                ],
                "word_count": len(full_text.split()),
                "page_count": extracted_data.get("metadata", {}).get("page_count", 0),
                "has_abstract": any(s.get("type") == "abstract" for s in extracted_data["sections"]),
                "has_introduction": any(s.get("type") == "introduction" for s in extracted_data["sections"]),
                "has_methods": any(s.get("type") == "methods" for s in extracted_data["sections"]),
                "has_results": any(s.get("type") == "results" for s in extracted_data["sections"]),
                "has_discussion": any(s.get("type") == "discussion" for s in extracted_data["sections"]),
                "has_conclusion": any(s.get("type") == "conclusion" for s in extracted_data["sections"]),
                "document_metadata": {
                    "has_abstract": any(s.get("type") == "abstract" for s in extracted_data["sections"]),
                    "has_introduction": any(s.get("type") == "introduction" for s in extracted_data["sections"]),
                    "has_conclusion": any(s.get("type") == "conclusion" for s in extracted_data["sections"]),
                    "appears_complete": len(extracted_data["sections"]) >= 3,
                    "primary_structure": "standard",
                    "grobid_extracted": True
                }
            }
        else:
            logger.info(f"[INGEST] Using GPT-4 structure analysis")
            structure = analyze_document_structure(full_text)
            structure["document_metadata"]["grobid_extracted"] = False

        logger.info(f"[INGEST] ✓ Structure analysis complete")

        # Calculate word count
        logger.info(f"[INGEST] Step 6: Calculating word count...")
        word_count = calculate_word_count(full_text)
        logger.info(f"[INGEST] ✓ Word count: {word_count}")

        # 5. Store analysis in draft_analysis table
        logger.info(f"[INGEST] Step 7: Storing analysis in database...")
        analysis_record = {
            "draft_id": draft_id,
            "structure": strip_manuscript_content_from_structure(structure),
            "word_count": word_count,
            "analysis": {},
            "analysis_metadata": {
                "processing_timestamp": datetime.datetime.utcnow().isoformat(),
                "file_type": file_type,
                "text_length": len(full_text),
                "model_used": "gpt-5.2-chat-latest" if file_type != 'pdf' else "grobid",
                "paper_type": paper_type,
                "citation_style": citation_style,
                "grobid_sections_count": len(extracted_data.get("sections", [])),
                "grobid_references_count": len(extracted_data.get("references", []))
            }
        }

        supabase.table("draft_analysis").insert(analysis_record).execute()
        logger.info(f"[INGEST] ✓ Stored draft analysis in database")

        # Stage 1 editing data is substantive analysis output, not metadata.
        editing_result = await editing_task
        analysis_res = (
            supabase.table("draft_analysis")
            .select("analysis")
            .eq("draft_id", draft_id)
            .single()
            .execute()
        )
        current_analysis = (analysis_res.data or {}).get("analysis") or {}
        current_analysis["editing_feedback"] = editing_result
        supabase.table("draft_analysis").update(
            {
                "analysis": current_analysis,
                "updated_at": datetime.datetime.utcnow().isoformat(),
            }
        ).eq("draft_id", draft_id).execute()
        logger.info(f"[INGEST] ✓ Stored Stage 1 editing feedback")

        # 6. (Steps 8a-8d removed) — LangGraph is the authoritative analysis writer.
        # Claims, coverage gaps, citation suggestions, and reviewer feedback are all
        # generated by the LangGraph workflow that runs after this function completes.
        # ingest_draft is responsible only for: file extraction, structure analysis,
        # Stage 1 editing, and initial draft_analysis record creation.

        # 7. Update draft status to 'processing' (NOT 'analyzed') —
        # LangGraph runs AFTER this function and writes supporting_literature.
        # Status is set to 'analyzed' only after LangGraph completes (in draft_analysis_langgraph.py).
        # Keeping status='processing' here ensures the frontend keeps polling until everything is ready.
        logger.info(f"[INGEST] Step 9: Updating status to 'processing' (LangGraph will set 'analyzed')...")
        supabase.table("drafts").update({
            "status": "processing",
            "updated_at": datetime.datetime.utcnow().isoformat()
        }).eq("id", draft_id).execute()
        logger.info(f"[INGEST] ✓ Status updated to 'processing'")

        logger.info(f"[INGEST] ========== DRAFT INGESTION COMPLETED SUCCESSFULLY ==========")
        logger.info(f"[INGEST] draft_id={draft_id}, word_count={word_count}")

        return {
            "message": "Draft successfully analyzed",
            "draft_id": draft_id,
            "word_count": word_count,
            "sections_identified": len(structure.get("sections", [])),
            "file_type": file_type
        }

    except Exception as e:
        logger.error("Draft ingestion failed: %s", safe_exception(e))
        # Status is managed by the Celery task (only set 'failed' after all retries exhausted).
        # Just raise so the caller can handle retries and status updates.
        raise


async def validate_file_format(file_bytes: bytes, file_type: str) -> Dict[str, Any]:
    """
    Validate file format and check if it can be processed.

    This provides early validation before full processing to give users
    clear feedback about file issues.

    Args:
        file_bytes: File content as bytes
        file_type: Expected file type ('pdf', 'docx', 'txt')

    Returns:
        Dictionary with validation results:
        {
            "valid": bool,
            "errors": List[Dict],
            "suggestions": List[str],
            "file_size": int,
            "can_extract_text": bool
        }
    """
    # Use the comprehensive validation from draft_errors module
    validation_result = validate_and_suggest(file_bytes, file_type)

    # Add text extraction check if basic validation passes
    if validation_result["valid"]:
        try:
            extracted_data = await extract_text(file_bytes, file_type)
            sample_text = extracted_data["full_text"]

            if len(sample_text.strip()) < 50:
                error = FileEmptyError(file_type)
                validation_result["valid"] = False
                validation_result["errors"].append(error.to_dict())
                validation_result["suggestions"].extend(error.suggestions)
                validation_result["can_extract_text"] = False
            else:
                validation_result["can_extract_text"] = True

        except DraftProcessingError as e:
            validation_result["valid"] = False
            validation_result["errors"].append(e.to_dict())
            validation_result["suggestions"].extend(e.suggestions)
            validation_result["can_extract_text"] = False

    validation_result["file_size"] = len(file_bytes)
    return validation_result
