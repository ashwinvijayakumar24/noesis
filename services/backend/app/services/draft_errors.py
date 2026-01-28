"""
Draft Processing Error Handling

Provides comprehensive error handling for draft processing operations with:
- Clear, user-friendly error messages
- Format-specific error guidance
- Graceful degradation strategies
- Error recovery suggestions

Requirement 1.4: Provide clear error messages and suggest alternative formats
"""

from typing import Optional, Dict, Any, List
from enum import Enum


class DraftErrorType(Enum):
    """Types of draft processing errors"""
    FILE_TOO_LARGE = "file_too_large"
    FILE_TOO_SMALL = "file_too_small"
    FILE_CORRUPTED = "file_corrupted"
    FILE_EMPTY = "file_empty"
    UNSUPPORTED_FORMAT = "unsupported_format"
    ENCODING_ERROR = "encoding_error"
    PDF_EXTRACTION_FAILED = "pdf_extraction_failed"
    DOCX_EXTRACTION_FAILED = "docx_extraction_failed"
    TEXT_EXTRACTION_FAILED = "text_extraction_failed"
    STRUCTURE_ANALYSIS_FAILED = "structure_analysis_failed"
    STORAGE_DOWNLOAD_FAILED = "storage_download_failed"
    INVALID_FILE_URL = "invalid_file_url"


class DraftProcessingError(Exception):
    """
    Base exception for draft processing errors.

    Provides structured error information with user-friendly messages
    and actionable suggestions.
    """

    def __init__(
        self,
        error_type: DraftErrorType,
        message: str,
        suggestions: Optional[List[str]] = None,
        technical_details: Optional[str] = None
    ):
        """
        Initialize draft processing error.

        Args:
            error_type: Type of error that occurred
            message: User-friendly error message
            suggestions: List of suggestions to fix the issue
            technical_details: Technical error details for logging
        """
        self.error_type = error_type
        self.message = message
        self.suggestions = suggestions or []
        self.technical_details = technical_details
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert error to dictionary for API responses.

        Returns:
            Dictionary with error information
        """
        return {
            "error_type": self.error_type.value,
            "message": self.message,
            "suggestions": self.suggestions,
            "technical_details": self.technical_details
        }


# ============================================
# Specific Error Classes
# ============================================

class FileTooLargeError(DraftProcessingError):
    """File exceeds maximum size limit"""

    def __init__(self, file_size: int, max_size: int = 100 * 1024 * 1024):
        size_mb = file_size / (1024 * 1024)
        max_mb = max_size / (1024 * 1024)

        super().__init__(
            error_type=DraftErrorType.FILE_TOO_LARGE,
            message=f"File size ({size_mb:.1f}MB) exceeds maximum allowed size ({max_mb:.0f}MB)",
            suggestions=[
                "Compress your PDF using online tools or Adobe Acrobat",
                "Remove high-resolution images from the document",
                "Split large documents into smaller sections",
                "Convert to a more efficient format (DOCX is typically smaller than PDF)"
            ],
            technical_details=f"file_size={file_size}, max_size={max_size}"
        )


class FileTooSmallError(DraftProcessingError):
    """File is suspiciously small or empty"""

    def __init__(self, file_size: int):
        super().__init__(
            error_type=DraftErrorType.FILE_TOO_SMALL,
            message=f"File appears to be empty or corrupted ({file_size} bytes)",
            suggestions=[
                "Verify the file is not empty",
                "Check that the file uploaded completely",
                "Try re-saving and re-uploading the document",
                "Ensure the file is a valid research draft"
            ],
            technical_details=f"file_size={file_size}"
        )


class FileEmptyError(DraftProcessingError):
    """File contains no extractable text"""

    def __init__(self, file_type: str):
        super().__init__(
            error_type=DraftErrorType.FILE_EMPTY,
            message=f"No text could be extracted from the {file_type.upper()} file",
            suggestions=[
                "If this is a scanned PDF, use OCR (Optical Character Recognition) first",
                "Ensure the PDF is text-based, not just images",
                "For DOCX files, verify the file contains actual text content",
                "Try converting the document to a different format",
                "Check that the file is not password-protected or encrypted"
            ],
            technical_details=f"file_type={file_type}"
        )


class UnsupportedFormatError(DraftProcessingError):
    """File format is not supported"""

    def __init__(self, file_type: str):
        super().__init__(
            error_type=DraftErrorType.UNSUPPORTED_FORMAT,
            message=f"File format '{file_type}' is not supported",
            suggestions=[
                "Supported formats: PDF (.pdf), Word (.docx), Plain Text (.txt)",
                "Convert your file to one of these formats:",
                "  • PDF: Use 'Print to PDF' or export from your word processor",
                "  • DOCX: Save from Microsoft Word or compatible editor",
                "  • TXT: Plain text files with UTF-8 encoding",
                "For Google Docs: File → Download → Microsoft Word (.docx) or PDF"
            ],
            technical_details=f"file_type={file_type}"
        )


class PDFExtractionError(DraftProcessingError):
    """Failed to extract text from PDF"""

    def __init__(self, original_error: str):
        super().__init__(
            error_type=DraftErrorType.PDF_EXTRACTION_FAILED,
            message="Failed to extract text from PDF document",
            suggestions=[
                "Ensure the PDF is not password-protected",
                "Verify the PDF is not corrupted (try opening it in a PDF reader)",
                "If this is a scanned document, use OCR software first",
                "Try re-saving the PDF from the original application",
                "Convert to DOCX format instead"
            ],
            technical_details=original_error
        )


class DOCXExtractionError(DraftProcessingError):
    """Failed to extract text from DOCX"""

    def __init__(self, original_error: str):
        super().__init__(
            error_type=DraftErrorType.DOCX_EXTRACTION_FAILED,
            message="Failed to extract text from Word document",
            suggestions=[
                "Ensure the DOCX file is not corrupted",
                "Try opening and re-saving the file in Microsoft Word",
                "Verify the file is a valid .docx format (not .doc)",
                "For .doc files, save as .docx first",
                "Try converting to PDF format instead"
            ],
            technical_details=original_error
        )


class TextEncodingError(DraftProcessingError):
    """Failed to decode text file"""

    def __init__(self, original_error: str):
        super().__init__(
            error_type=DraftErrorType.ENCODING_ERROR,
            message="Failed to decode text file (encoding issue)",
            suggestions=[
                "Save your text file with UTF-8 encoding",
                "Use a text editor like Notepad++ or VS Code to change encoding",
                "Convert special characters to ASCII equivalents",
                "Try saving as DOCX or PDF instead"
            ],
            technical_details=original_error
        )


class StructureAnalysisError(DraftProcessingError):
    """Failed to analyze document structure"""

    def __init__(self, original_error: str):
        super().__init__(
            error_type=DraftErrorType.STRUCTURE_ANALYSIS_FAILED,
            message="Failed to analyze document structure",
            suggestions=[
                "Ensure your document has clear section headings",
                "Verify the document contains sufficient text (at least 100 words)",
                "Check that the document is in a standard academic format",
                "Try again - this may be a temporary service issue"
            ],
            technical_details=original_error
        )


class StorageDownloadError(DraftProcessingError):
    """Failed to download file from storage"""

    def __init__(self, original_error: str):
        super().__init__(
            error_type=DraftErrorType.STORAGE_DOWNLOAD_FAILED,
            message="Failed to download file from storage",
            suggestions=[
                "Try uploading the file again",
                "Check your internet connection",
                "Verify the file was uploaded successfully",
                "Contact support if the problem persists"
            ],
            technical_details=original_error
        )


# ============================================
# Error Handling Utilities
# ============================================

def get_format_suggestions(current_format: Optional[str] = None) -> List[str]:
    """
    Get format-specific suggestions for users.

    Args:
        current_format: Current format that failed (if known)

    Returns:
        List of suggestions for format alternatives
    """
    suggestions = [
        "✓ PDF (.pdf) - Best for preserving formatting",
        "✓ Word (.docx) - Best for editable documents",
        "✓ Plain Text (.txt) - Best for simple documents"
    ]

    if current_format:
        format_map = {
            'pdf': [
                "If PDF fails, try converting to DOCX using online tools",
                "For scanned PDFs, use OCR tools like Adobe Acrobat"
            ],
            'docx': [
                "If DOCX fails, try exporting as PDF",
                "Ensure you're using .docx format (not older .doc)"
            ],
            'txt': [
                "If TXT fails, try saving as DOCX or PDF",
                "Ensure the file uses UTF-8 encoding"
            ]
        }
        suggestions.extend(format_map.get(current_format.lower(), []))

    return suggestions


def validate_and_suggest(
    file_bytes: bytes,
    file_type: str,
    max_size: int = 100 * 1024 * 1024,
    min_size: int = 100
) -> Dict[str, Any]:
    """
    Validate file and provide suggestions if invalid.

    This function performs comprehensive validation and returns structured
    results with actionable suggestions.

    Args:
        file_bytes: File content
        file_type: File extension
        max_size: Maximum allowed file size in bytes
        min_size: Minimum allowed file size in bytes

    Returns:
        Dictionary with validation results:
        {
            "valid": bool,
            "errors": List[Dict],
            "warnings": List[str],
            "suggestions": List[str]
        }
    """
    result = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "suggestions": []
    }

    file_size = len(file_bytes)

    # Check file size constraints
    if file_size > max_size:
        error = FileTooLargeError(file_size, max_size)
        result["valid"] = False
        result["errors"].append(error.to_dict())
        result["suggestions"].extend(error.suggestions)

    if file_size < min_size:
        error = FileTooSmallError(file_size)
        result["valid"] = False
        result["errors"].append(error.to_dict())
        result["suggestions"].extend(error.suggestions)

    # Check supported format
    supported_formats = ['pdf', 'docx', 'txt']
    if file_type.lower() not in supported_formats:
        error = UnsupportedFormatError(file_type)
        result["valid"] = False
        result["errors"].append(error.to_dict())
        result["suggestions"].extend(error.suggestions)

    # Add format-specific suggestions
    if not result["valid"]:
        result["suggestions"].extend(get_format_suggestions(file_type))

    return result


def wrap_extraction_error(
    error: Exception,
    file_type: str
) -> DraftProcessingError:
    """
    Wrap extraction errors with user-friendly messages.

    Args:
        error: Original exception
        file_type: Type of file being processed

    Returns:
        DraftProcessingError with suggestions
    """
    error_str = str(error)

    if file_type.lower() == 'pdf':
        return PDFExtractionError(error_str)
    elif file_type.lower() == 'docx':
        return DOCXExtractionError(error_str)
    elif file_type.lower() == 'txt':
        return TextEncodingError(error_str)
    else:
        return DraftProcessingError(
            error_type=DraftErrorType.TEXT_EXTRACTION_FAILED,
            message=f"Failed to extract text from {file_type} file",
            suggestions=get_format_suggestions(file_type),
            technical_details=error_str
        )
