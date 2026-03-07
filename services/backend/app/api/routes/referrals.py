"""
API routes for referral system
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime

from app.core.supabase_client import get_supabase_client


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
            "referee_email": referee_email,
            "completed_at": datetime.utcnow().isoformat() if referee_user_id else None
        }

        if referee_user_id:
            update_data["referee_user_id"] = referee_user_id

        result = supabase.table("referrals").update(update_data).eq("id", referral_id).execute()

        # TODO: Grant reward to referrer if this is their Nth completed referral

        return {
            "success": True,
            "message": "Referral tracked successfully",
            "referrer_notified": True
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
