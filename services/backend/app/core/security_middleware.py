"""
Security Middleware for Noesis Backend
======================================
Implements security headers, rate limiting, and request validation

CRITICAL: Import and apply this middleware in main.py before production deployment
"""

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import logging
from typing import Callable
import re
import hashlib
import time

logger = logging.getLogger(__name__)

SENSITIVE_PATH_PATTERNS = [
    r"(^|/)\.env([^/]*$|[/?#])",
    r"(^|/)\.git($|/)",
    r"(^|/)\.aws($|/)",
    r"(^|/)\.DS_Store$",
    r"(^|/)wp-admin($|/)",
    r"(^|/)wp-login\.php$",
    r"(^|/)xmlrpc\.php$",
    r"(^|/)phpmyadmin($|/)",
    r"(^|/)vendor/phpunit($|/)",
    r"(^|/)actuator($|/)",
    r"\.php$",
]

SENSITIVE_PATH_RE = re.compile("|".join(SENSITIVE_PATH_PATTERNS), re.IGNORECASE)


def is_sensitive_probe_path(path: str) -> bool:
    """Return true for common bot/scanner probes that should never reach app routes."""
    normalized = (path or "").split("?", 1)[0]
    return bool(SENSITIVE_PATH_RE.search(normalized))


# ============================================
# SECURITY HEADERS MIDDLEWARE
# ============================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to all HTTP responses

    Headers added:
    - X-Frame-Options: Prevents clickjacking attacks
    - X-Content-Type-Options: Prevents MIME type sniffing
    - X-XSS-Protection: Enables XSS filter in browsers
    - Strict-Transport-Security: Enforces HTTPS
    - Content-Security-Policy: Restricts resource loading
    - Referrer-Policy: Controls referrer information
    - Permissions-Policy: Controls browser features
    """

    async def dispatch(self, request: Request, call_next: Callable):
        response = await call_next(request)

        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Enable XSS protection (legacy browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Enforce HTTPS (only in production)
        # Note: max-age=31536000 = 1 year
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # Content Security Policy
        # Adjust based on your frontend needs
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self' https://api.openai.com https://*.supabase.co; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )

        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Control browser features (permissions policy)
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "accelerometer=()"
        )

        return response


# ============================================
# RATE LIMITER CONFIGURATION
# ============================================

# Initialize rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],  # Global default
    storage_uri="redis://redis:6379/1",  # Use Redis for distributed rate limiting
    strategy="fixed-window"
)

# Rate limit exception handler
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    Custom handler for rate limit exceeded errors
    """
    logger.warning(
        f"Rate limit exceeded for {request.client.host} on {request.url.path}"
    )
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": "Too many requests. Please try again later.",
            "retry_after": exc.retry_after if hasattr(exc, 'retry_after') else 60
        }
    )


# ============================================
# INPUT VALIDATION MIDDLEWARE
# ============================================

class InputValidationMiddleware(BaseHTTPMiddleware):
    """
    Validates request inputs for common attack patterns
    """

    # Suspicious patterns (SQL injection, XSS, path traversal)
    SUSPICIOUS_PATTERNS = [
        r"(\bUNION\b.*\bSELECT\b)",  # SQL injection
        r"(\bINSERT\b.*\bINTO\b)",
        r"(\bDROP\b.*\bTABLE\b)",
        r"(\bDELETE\b.*\bFROM\b)",
        r"(<script[^>]*>.*?</script>)",  # XSS
        r"(javascript:)",
        r"(onerror=)",
        r"(onload=)",
        r"(\.\./|\.\.\%2[fF])",  # Path traversal
    ]

    MAX_QUERY_LENGTH = 1000
    MAX_BODY_SIZE = 104857600  # 100MB in bytes, matching draft/document upload UI limits

    def __init__(self, app):
        super().__init__(app)
        self.pattern = re.compile("|".join(self.SUSPICIOUS_PATTERNS), re.IGNORECASE)

    def _error_response(self, status_code: int, detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=status_code,
            content={"detail": detail},
        )

    async def dispatch(self, request: Request, call_next: Callable):
        # Skip validation for health checks and static files
        if request.url.path in ["/health", "/docs", "/openapi.json", "/redoc"]:
            return await call_next(request)

        if is_sensitive_probe_path(request.url.path):
            logger.info(
                f"Sensitive path probe detected from {request.client.host}: {request.url.path[:100]}"
            )
            return self._error_response(
                status.HTTP_400_BAD_REQUEST,
                "Invalid request",
            )

        # Validate query parameters
        if request.url.query:
            # Check query length
            if len(request.url.query) > self.MAX_QUERY_LENGTH:
                logger.warning(
                    f"Query string too long from {request.client.host}: {len(request.url.query)} chars"
                )
                return self._error_response(
                    status.HTTP_400_BAD_REQUEST,
                    "Query string too long",
                )

            # Check for suspicious patterns
            if self.pattern.search(request.url.query):
                logger.warning(
                    f"Suspicious query pattern detected from {request.client.host}: {request.url.query[:100]}"
                )
                return self._error_response(
                    status.HTTP_400_BAD_REQUEST,
                    "Invalid request",
                )

        # Validate request body size (for POST/PUT requests)
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > self.MAX_BODY_SIZE:
                logger.warning(
                    f"Request body too large from {request.client.host}: {content_length} bytes"
                )
                return self._error_response(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    "Request body too large",
                )

        response = await call_next(request)
        return response


# ============================================
# AUTHENTICATION TOKEN VALIDATOR
# ============================================

class SecureAuthValidator:
    """
    Enhanced authentication token validation with security checks
    """
    _USER_ID_CACHE: dict[str, tuple[str, float]] = {}
    _USER_ID_CACHE_TTL_SECONDS = 300

    @staticmethod
    def validate_bearer_token(authorization: str) -> str:
        """
        Validates Bearer token format and extracts token

        Args:
            authorization: Authorization header value

        Returns:
            Extracted token

        Raises:
            HTTPException: If token format is invalid
        """
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing Authorization header"
            )

        # Validate Bearer token format
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header format. Expected 'Bearer <token>'"
            )

        # Extract token
        token = authorization[7:]  # Remove "Bearer " prefix

        # Validate token is not empty
        if not token or token.strip() == "":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Empty token provided"
            )

        # Basic token format validation (JWT has 3 parts separated by dots)
        if token.count('.') != 2:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token format"
            )

        return token

    @classmethod
    def get_user_id(cls, authorization: str, supabase_client) -> str:
        """
        Resolve the current user's ID with a short-lived in-memory token cache.
        This avoids repeated Supabase auth lookups across hot page loads.
        """
        token = cls.validate_bearer_token(authorization)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        now = time.time()

        cached = cls._USER_ID_CACHE.get(token_hash)
        if cached and cached[1] > now:
            return cached[0]

        user = supabase_client.auth.get_user(token)
        user_id = user.user.id
        cls._USER_ID_CACHE[token_hash] = (user_id, now + cls._USER_ID_CACHE_TTL_SECONDS)

        if len(cls._USER_ID_CACHE) > 2048:
            cls._USER_ID_CACHE = {
                key: value for key, value in cls._USER_ID_CACHE.items()
                if value[1] > now
            }

        return user_id


# ============================================
# CORS CONFIGURATION HELPER
# ============================================

def get_cors_config(allowed_origins: list[str], environment: str) -> dict:
    """
    Returns secure CORS configuration based on environment

    Args:
        allowed_origins: List of allowed origin URLs
        environment: "development" or "production"

    Returns:
        Dictionary with CORS configuration
    """
    if environment == "production":
        return {
            "allow_origins": allowed_origins,
            "allow_origin_regex": r"chrome-extension://.*",
            "allow_credentials": True,
            "allow_methods": ["GET", "POST", "PUT", "DELETE"],  # Explicit methods only
            "allow_headers": ["authorization", "content-type", "accept"],  # Explicit headers
            "expose_headers": ["content-type", "content-length"],
            "max_age": 3600,  # Cache preflight requests for 1 hour
        }
    else:
        # Development: more permissive but still controlled
        return {
            "allow_origins": allowed_origins,
            "allow_credentials": True,
            "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
            "allow_headers": ["*"],
            "expose_headers": ["*"],
            "max_age": 600,  # 10 minutes cache in dev
        }


# ============================================
# FILE UPLOAD SECURITY VALIDATORS
# ============================================

class FileUploadValidator:
    """
    Validates file uploads for security issues
    """

    # Magic bytes for file type validation
    MAGIC_BYTES = {
        "pdf": [b"%PDF"],
        "docx": [b"PK\x03\x04"],  # ZIP format (DOCX is ZIP)
        "txt": [b""],  # Text files don't have magic bytes
    }

    # Allowed extensions
    ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}

    # Max file sizes (in bytes)
    MAX_FILE_SIZE = 52428800  # 50MB

    @classmethod
    def validate_file_extension(cls, filename: str) -> str:
        """
        Validates file extension

        Returns:
            Lowercase extension without dot
        """
        if "." not in filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File must have an extension"
            )

        extension = filename.rsplit(".", 1)[1].lower()

        if extension not in cls.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File type not allowed. Allowed types: {', '.join(cls.ALLOWED_EXTENSIONS)}"
            )

        return extension

    @classmethod
    def validate_mime_type(cls, content_type: str, expected_extension: str) -> bool:
        """
        Validates MIME type matches expected file extension
        """
        valid_mime_types = {
            "pdf": ["application/pdf"],
            "docx": [
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "application/zip"  # DOCX is ZIP format
            ],
            "txt": ["text/plain", "text/txt"],
        }

        allowed = valid_mime_types.get(expected_extension, [])

        if content_type not in allowed:
            logger.warning(
                f"MIME type mismatch: got {content_type}, expected one of {allowed} for .{expected_extension}"
            )
            # Don't fail, just log warning (MIME type can be spoofed)

        return True

    @classmethod
    async def validate_file_content(cls, file_content: bytes, extension: str) -> bool:
        """
        Validates file content by checking magic bytes

        Args:
            file_content: First few bytes of the file
            extension: Expected file extension

        Returns:
            True if valid

        Raises:
            HTTPException: If file content doesn't match expected type
        """
        if extension == "txt":
            # Text files don't have magic bytes
            return True

        magic_bytes = cls.MAGIC_BYTES.get(extension, [])

        for magic in magic_bytes:
            if file_content.startswith(magic):
                return True

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File content does not match .{extension} format"
        )

    @classmethod
    def validate_file_size(cls, size: int) -> bool:
        """
        Validates file size is within limits
        """
        if size > cls.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size: {cls.MAX_FILE_SIZE // (1024*1024)}MB"
            )
        return True

    @classmethod
    def sanitize_filename(cls, filename: str) -> str:
        """
        Sanitizes filename to prevent path traversal attacks

        Removes:
        - Path separators (/, \)
        - Null bytes
        - Control characters
        """
        # Remove path separators
        filename = filename.replace("/", "_").replace("\\", "_")

        # Remove null bytes and control characters
        filename = "".join(char for char in filename if ord(char) >= 32 and char != "\x00")

        # Limit length
        if len(filename) > 255:
            name, ext = filename.rsplit(".", 1)
            filename = name[:250] + "." + ext

        return filename


# ============================================
# USAGE EXAMPLE
# ============================================

"""
In main.py, import and apply these security components:

```python
from app.core.security_middleware import (
    SecurityHeadersMiddleware,
    InputValidationMiddleware,
    limiter,
    rate_limit_exceeded_handler,
    get_cors_config,
    SecureAuthValidator,
    FileUploadValidator
)
from slowapi.errors import RateLimitExceeded

# Add middlewares
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(InputValidationMiddleware)

# Configure rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Configure CORS
cors_config = get_cors_config(
    allowed_origins=[settings.CORS_ORIGINS],
    environment=settings.ENVIRONMENT
)
app.add_middleware(CORSMiddleware, **cors_config)

# Use SecureAuthValidator in your auth dependency
def get_current_user(authorization: str = Header(None)):
    token = SecureAuthValidator.validate_bearer_token(authorization)
    # ... rest of your auth logic

# Use FileUploadValidator in upload endpoints
@router.post("/upload")
@limiter.limit("10/minute")  # Apply rate limiting
async def upload_document(file: UploadFile, ...):
    # Validate file
    extension = FileUploadValidator.validate_file_extension(file.filename)
    FileUploadValidator.validate_mime_type(file.content_type, extension)

    # Read first 1024 bytes to check magic bytes
    content = await file.read(1024)
    await FileUploadValidator.validate_file_content(content, extension)
    file.seek(0)  # Reset file pointer

    # ... rest of upload logic
```
"""
