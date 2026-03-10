"""
API routes for referral system
"""

import secrets
import string
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime

from app.core.supabase_client import get_supabase_client
from app.core.security_middleware import SecureAuthValidator


router = APIRouter()


class ReferralStats(BaseModel):
    total_referrals: int
    completed_referrals: int
    pending_referrals: int
    referral_code: str
    reward_earned: bool


class ReferralCreate(BaseModel):
    referee_email: Optional[EmailStr] = None


class ReferralResponse(BaseModel):
    id: str
    referral_code: str
    referee_email: Optional[str]
    status: str
    created_at: datetime


@router.post("/referrals/generate")
async def generate_referral_code(
    user_id: str = Depends(lambda: None)  # TODO: Replace with actual auth
):
    """
    Generate a unique referral code for the user

    Each user gets one persistent referral code
    """
    try:
        if not user_id:
            raise HTTPException(status_code=401, detail="User authentication required")

        supabase = get_supabase_client()

        # Check if user already has a referral code
        existing = supabase.table("referrals").select("referral_code").eq("referrer_user_id", user_id).limit(1).execute()

        if existing.data:
            return {
                "referral_code": existing.data[0]["referral_code"],
                "referral_url": f"https://noesis.is/signup?ref={existing.data[0]['referral_code']}"
            }

        # Generate new referral code using database function
        result = supabase.rpc("generate_referral_code", {"user_id_param": user_id}).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to generate referral code")

        referral_code = result.data

        # Create referral record
        referral_data = {
            "referrer_user_id": user_id,
            "referral_code": referral_code,
            "status": "active"
        }

        insert_result = supabase.table("referrals").insert(referral_data).execute()

        return {
            "referral_code": referral_code,
            "referral_url": f"https://noesis.is/signup?ref={referral_code}"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate referral code: {str(e)}")


@router.get("/referrals/stats", response_model=ReferralStats)
async def get_referral_stats(
    user_id: str = Depends(lambda: None)  # TODO: Replace with actual auth
):
    """
    Get user's referral statistics
    """
    try:
        if not user_id:
            raise HTTPException(status_code=401, detail="User authentication required")

        supabase = get_supabase_client()

        # Get all referrals for user
        referrals = supabase.table("referrals").select("*").eq("referrer_user_id", user_id).execute()

        if not referrals.data:
            # Generate code if doesn't exist
            code_result = supabase.rpc("generate_referral_code", {"user_id_param": user_id}).execute()
            referral_code = code_result.data if code_result.data else "NOESIS-000000"

            return ReferralStats(
                total_referrals=0,
                completed_referrals=0,
                pending_referrals=0,
                referral_code=referral_code,
                reward_earned=False
            )

        total = len(referrals.data)
        completed = sum(1 for r in referrals.data if r.get("status") == "completed")
        pending = sum(1 for r in referrals.data if r.get("status") == "pending")
        reward_earned = any(r.get("reward_granted", False) for r in referrals.data)
        referral_code = referrals.data[0].get("referral_code", "")

        return ReferralStats(
            total_referrals=total,
            completed_referrals=completed,
            pending_referrals=pending,
            referral_code=referral_code,
            reward_earned=reward_earned
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch referral stats: {str(e)}")


async def _maybe_grant_lab_reward(supabase, referrer_id: str, referee_email: str) -> bool:
    """
    Grant referrer a free Lab tier month if 3+ completed referrals share the same
    institution email domain (e.g., gatech.edu). Only grants once per referrer.
    Returns True if the reward was newly granted.
    """
    try:
        # Get all completed referrals for this referrer with an email address
        completed = (
            supabase.table("referrals")
            .select("referee_email, reward_granted")
            .eq("referrer_user_id", referrer_id)
            .eq("status", "completed")
            .not_.is_("referee_email", "null")
            .execute()
        )

        if not completed.data:
            return False

        # Check if reward already granted for any entry (don't double-grant)
        already_rewarded = any(r.get("reward_granted") for r in completed.data)
        if already_rewarded:
            return False

        # Count referrals per institution domain
        domain_counts: dict = {}
        for row in completed.data:
            email = row.get("referee_email", "") or ""
            if "@" in email:
                domain = email.split("@")[1].lower()
                # Skip generic free email providers
                if domain not in ("gmail.com", "yahoo.com", "hotmail.com", "outlook.com"):
                    domain_counts[domain] = domain_counts.get(domain, 0) + 1

        # Check if any institution has 3+ referrals
        qualifying_domain = next(
            (d for d, count in domain_counts.items() if count >= 3), None
        )
        if not qualifying_domain:
            return False

        # Grant Lab tier to referrer for the next billing cycle
        supabase.table("user_quotas").update({
            "plan_tier": "lab",
            "monthly_draft_limit": 9999,
            "monthly_document_limit": 9999,
            "monthly_chat_messages_limit": 9999,
        }).eq("user_id", referrer_id).execute()

        # Mark the qualifying referrals as reward_granted so we don't double-grant
        supabase.table("referrals").update({"reward_granted": True}).eq(
            "referrer_user_id", referrer_id
        ).eq("status", "completed").execute()

        return True

    except Exception:
        return False  # reward is non-critical, fail silently


@router.post("/referrals/track")
async def track_referral(
    referral_code: str,
    referee_user_id: Optional[str] = None,
    referee_email: Optional[EmailStr] = None
):
    """
    Track a referral (called when referee signs up)

    This endpoint should be called from the signup flow
    """
    try:
        supabase = get_supabase_client()

        # Find referral by code
        referral = supabase.table("referrals").select("*").eq("referral_code", referral_code).eq("status", "active").execute()

        if not referral.data:
            raise HTTPException(status_code=404, detail="Invalid referral code")

        referral_id = referral.data[0]["id"]
        referrer_id = referral.data[0]["referrer_user_id"]

        # Update referral with referee info
        update_data = {
            "status": "completed" if referee_user_id else "pending",
            "referee_email": str(referee_email) if referee_email else None,
            "completed_at": datetime.utcnow().isoformat() if referee_user_id else None
        }

        if referee_user_id:
            update_data["referee_user_id"] = referee_user_id

        result = supabase.table("referrals").update(update_data).eq("id", referral_id).execute()

        # "Refer a Lab" reward: grant free Lab tier for 1 month when 3+
        # completed referrals share the same institution email domain.
        lab_reward_granted = False
        if referee_user_id and referee_email:
            lab_reward_granted = await _maybe_grant_lab_reward(
                supabase, referrer_id, str(referee_email)
            )

        return {
            "success": True,
            "message": "Referral tracked successfully",
            "referrer_notified": True,
            "lab_reward_granted": lab_reward_granted
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to track referral: {str(e)}")


@router.get("/referrals/my", response_model=List[ReferralResponse])
async def get_my_referrals(
    user_id: str = Depends(lambda: None)  # TODO: Replace with actual auth
):
    """
    Get list of user's referrals
    """
    try:
        if not user_id:
            raise HTTPException(status_code=401, detail="User authentication required")

        supabase = get_supabase_client()

        result = supabase.table("referrals").select("*").eq("referrer_user_id", user_id).order("created_at", desc=True).execute()

        return [ReferralResponse(**item) for item in result.data]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch referrals: {str(e)}")


# ──────────────────────────────────────────────
# Lab Invite endpoints (project-scoped team onboarding)
# ──────────────────────────────────────────────

def _get_current_user_for_lab(authorization: str = Header(None)) -> str:
    """Validate Bearer token and return user_id."""
    token = SecureAuthValidator.validate_bearer_token(authorization)
    supabase = get_supabase_client()
    user_response = supabase.auth.get_user(token)
    if not user_response or not user_response.user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_response.user.id


def _generate_lab_invite_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(8))


class LabInviteRequest(BaseModel):
    project_id: str
    lab_name: Optional[str] = None


@router.post("/lab-invite/generate")
async def generate_lab_invite(
    body: LabInviteRequest,
    user_id: str = Depends(_get_current_user_for_lab)
):
    """
    Generate a lab invite code for a project.

    The generated URL can be shared with lab members. When they sign up
    using this link they get a personalized welcome experience and are
    linked to the referrer's project.
    """
    supabase = get_supabase_client()

    # Verify user owns the project
    project = supabase.table("projects")\
        .select("id, title")\
        .eq("id", body.project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not project.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project_title = project.data[0]["title"]
    lab_name = body.lab_name or project_title

    # Check for existing active invite for this project + user
    existing = supabase.table("lab_invites")\
        .select("code")\
        .eq("project_id", body.project_id)\
        .eq("referrer_user_id", user_id)\
        .eq("is_active", True)\
        .execute()

    if existing.data:
        code = existing.data[0]["code"]
    else:
        code = _generate_lab_invite_code()
        supabase.table("lab_invites").insert({
            "code": code,
            "project_id": body.project_id,
            "referrer_user_id": user_id,
            "lab_name": lab_name,
        }).execute()

    invite_url = f"https://noesis.is/signup?lab_invite={code}"

    return {
        "code": code,
        "invite_url": invite_url,
        "lab_name": lab_name,
        "project_title": project_title,
    }


@router.get("/lab-invite/{code}")
async def get_lab_invite(code: str):
    """
    Public endpoint — get lab invite details for display on the signup page.
    Called before the user has an account.
    """
    supabase = get_supabase_client()
    result = supabase.table("lab_invites")\
        .select("code, lab_name, project_id, is_active, projects(title)")\
        .eq("code", code)\
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Invite not found or expired")

    invite = result.data[0]
    if not invite["is_active"]:
        raise HTTPException(status_code=410, detail="This invite link has been deactivated")

    return {
        "code": invite["code"],
        "lab_name": invite["lab_name"],
        "project_title": invite.get("projects", {}).get("title") if invite.get("projects") else None,
    }


@router.post("/lab-invite/{code}/join")
async def join_via_lab_invite(
    code: str,
    user_id: str = Depends(_get_current_user_for_lab)
):
    """
    Called after a new user signs up via a lab invite link.
    Increments the used_count on the invite for tracking.
    """
    supabase = get_supabase_client()
    result = supabase.table("lab_invites")\
        .select("id, used_count, is_active")\
        .eq("code", code)\
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Invite not found")

    invite = result.data[0]
    if not invite["is_active"]:
        return {"success": False, "message": "Invite no longer active"}

    # Increment used_count
    supabase.table("lab_invites")\
        .update({"used_count": invite["used_count"] + 1})\
        .eq("id", invite["id"])\
        .execute()

    return {"success": True, "message": "Welcome to the lab!"}
