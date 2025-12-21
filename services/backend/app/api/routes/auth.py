from fastapi import APIRouter, HTTPException, Depends, Header
from app.core.supabase_client import supabase

router = APIRouter()

@router.post("/signup")
def signup(email: str, password: str):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured. Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables.")
    response = supabase.auth.sign_up({"email": email, "password": password})
    if response.user is None:
        raise HTTPException(status_code=400, detail="Signup failed")
    return {"message": "User created successfully", "user": response.user.email}

@router.post("/login")
def login(email: str, password: str):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured. Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables.")
    response = supabase.auth.sign_in_with_password({"email": email, "password": password})
    if not response.session:
        raise HTTPException(status_code=400, detail="Login failed")
    return {
        "access_token": response.session.access_token,
        "refresh_token": response.session.refresh_token,
        "user": response.user.email,
    }

@router.get("/me")
def get_current_user(authorization: str = Header(None)):
    if supabase is None:
        raise HTTPException(status_code=500, detail="Supabase not configured. Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables.")
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    token = authorization.split("Bearer ")[-1]
    try:
        user = supabase.auth.get_user(token)
        return {"email": user.user.email, "id": user.user.id}
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {e}")
