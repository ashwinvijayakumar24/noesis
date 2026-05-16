from fastapi import APIRouter, HTTPException, Depends, Header, Request
from pydantic import BaseModel
from app.core.supabase_client import supabase
from app.core.security_middleware import SecureAuthValidator, limiter
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

# Pydantic models for request validation
class SignupRequest(BaseModel):
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class ResendConfirmationRequest(BaseModel):
    email: str

@router.post("/signup")
@limiter.limit("5/minute")  # Prevent signup spam - 5 attempts per minute
def signup(request: Request, credentials: SignupRequest):
    """
    User registration endpoint

    Rate limit: 5 signups per minute per IP address
    Sends confirmation email - user must verify before logging in
    """
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    try:
        response = supabase.auth.sign_up({
            "email": credentials.email,
            "password": credentials.password
        })
        if response.user is None:
            raise HTTPException(status_code=400, detail="Signup failed")
        logger.info(f"New user signed up: {response.user.email}")
        return {
            "message": "User created successfully. Please check your email to verify your account.",
            "user": response.user.email,
            "email_confirmed": response.user.email_confirmed_at is not None
        }
    except Exception as e:
        logger.error(f"Signup failed: {str(e)}")
        raise HTTPException(status_code=400, detail="Signup failed")

@router.post("/login")
@limiter.limit("5/minute")  # Prevent brute force - 5 attempts per minute
def login(request: Request, credentials: LoginRequest):
    """
    User login endpoint

    Rate limit: 5 login attempts per minute per IP address (prevents brute force)
    Requires email verification to complete
    """
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")
    try:
        response = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })
        if not response.session:
            raise HTTPException(status_code=400, detail="Invalid credentials")

        # Check if email is verified
        if not response.user.email_confirmed_at:
            logger.warning(f"Unverified login attempt: {response.user.email}")
            raise HTTPException(
                status_code=403,
                detail="Please verify your email before logging in. Check your inbox for the confirmation link."
            )

        logger.info(f"User logged in: {response.user.email}")
        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "user": response.user.email,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login failed: {str(e)}")
        # Check for specific Supabase error messages
        error_msg = str(e).lower()
        if "email not confirmed" in error_msg:
            raise HTTPException(
                status_code=403,
                detail="Please verify your email before logging in. Check your inbox for the confirmation link."
            )
        raise HTTPException(status_code=400, detail="Invalid credentials")

@router.get("/me")
def get_current_user(authorization: str = Header(None)):
    """
    Get current authenticated user
    """
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        user_id = SecureAuthValidator.get_user_id(authorization, supabase)
        token = SecureAuthValidator.validate_bearer_token(authorization)
        user = supabase.auth.get_user(token)
        return {
            "email": user.user.email,
            "id": user_id,
            "email_confirmed": user.user.email_confirmed_at is not None
        }
    except Exception as e:
        logger.warning(f"Token validation failed: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"  # Don't expose error details
        )

@router.get("/confirm")
async def confirm_email(token: str, type: str):
    """
    Handles email confirmation callback from Supabase.
    User clicks link in email → Supabase redirects here with token
    """
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # Verify the confirmation token
        response = supabase.auth.verify_otp({
            "token_hash": token,
            "type": type  # Usually "signup" or "email_change"
        })

        if not response.user:
            raise HTTPException(status_code=400, detail="Invalid confirmation token")

        logger.info(f"Email confirmed: {response.user.email}")
        return {
            "message": "Email confirmed successfully",
            "email": response.user.email
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Email confirmation failed: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail="Invalid or expired confirmation link"
        )

@router.get("/quota-summary")
async def get_quota_summary(authorization: str = Header(None)):
    """Return the current user's PDF + BibTeX quota summary for the upload modal."""
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        user_id = SecureAuthValidator.get_user_id(authorization, supabase)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    from app.services.quota_management import get_quota_summary
    return await get_quota_summary(user_id)


@router.post("/resend-confirmation")
@limiter.limit("3/minute")  # Limit resend requests
async def resend_confirmation(request: Request, credentials: ResendConfirmationRequest):
    """
    Allows users to request a new confirmation email.
    Rate limit: 3 attempts per minute to prevent abuse
    """
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    try:
        # Resend confirmation email
        supabase.auth.resend({
            "type": "signup",
            "email": credentials.email
        })
        logger.info(f"Confirmation email resent to: {credentials.email}")
        return {"message": f"Confirmation email sent to {credentials.email}"}
    except Exception as e:
        logger.error(f"Resend confirmation failed: {str(e)}")
        # Don't reveal if email exists or not (security best practice)
        return {"message": "If that email exists, a confirmation was sent"}
