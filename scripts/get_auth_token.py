#!/usr/bin/env python3
"""
Authentication Helper Script for Noesis Testing

This script helps you get a JWT token for testing the API endpoints.
It uses your test user credentials to sign in and get a valid session token.
"""

import os
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent / "services" / "backend"
sys.path.insert(0, str(backend_path))

from supabase import create_client
from dotenv import load_dotenv

# Load environment variables
env_path = backend_path / ".env"
load_dotenv(env_path)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

def get_auth_token(email: str, password: str):
    """
    Sign in a user and get their JWT token.

    Args:
        email: User email
        password: User password

    Returns:
        dict with access_token and user info
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        print("❌ Error: Supabase credentials not found in .env file")
        print(f"   Looking for .env at: {env_path}")
        return None

    print(f"🔐 Authenticating with Supabase...")
    print(f"   URL: {SUPABASE_URL}")
    print(f"   Email: {email}")

    try:
        # Create Supabase client (using anon key for auth)
        supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

        # Sign in the user
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        if response.user and response.session:
            print(f"✅ Authentication successful!")
            print(f"   User ID: {response.user.id}")
            print(f"   Email: {response.user.email}")
            print()
            print("=" * 80)
            print("🎟️  YOUR JWT TOKEN (copy this for API testing):")
            print("=" * 80)
            print(response.session.access_token)
            print("=" * 80)
            print()
            print("📋 How to use this token:")
            print("   Add this header to your curl commands:")
            print(f'   -H "Authorization: Bearer {response.session.access_token}"')
            print()

            return {
                "access_token": response.session.access_token,
                "refresh_token": response.session.refresh_token,
                "user_id": response.user.id,
                "email": response.user.email
            }
        else:
            print("❌ Authentication failed: No session returned")
            return None

    except Exception as e:
        print(f"❌ Authentication error: {e}")
        return None


def create_test_user(email: str, password: str):
    """
    Create a test user (requires service role key).
    This is an alternative if you haven't created the user via dashboard.
    """
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not service_key:
        print("❌ Error: SUPABASE_SERVICE_ROLE_KEY not found in .env")
        return None

    try:
        supabase = create_client(SUPABASE_URL, service_key)

        response = supabase.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True
        })

        print(f"✅ User created successfully!")
        print(f"   User ID: {response.user.id}")
        print(f"   Email: {response.user.email}")
        return response.user.id

    except Exception as e:
        print(f"❌ User creation error: {e}")
        return None


if __name__ == "__main__":
    print()
    print("=" * 80)
    print("🔑 NOESIS AUTHENTICATION HELPER")
    print("=" * 80)
    print()

    # Option 1: Sign in with existing user
    print("Do you want to:")
    print("  1. Sign in with existing user (get JWT token)")
    print("  2. Create a new test user")
    print()

    choice = input("Enter choice (1 or 2): ").strip()

    if choice == "1":
        print()
        email = input("Enter email [test@noesis.local]: ").strip() or "test@noesis.local"
        password = input("Enter password [TestPassword123!]: ").strip() or "TestPassword123!"
        print()

        result = get_auth_token(email, password)

        if result:
            # Save token to file for easy access
            token_file = Path(__file__).parent / "auth_token.txt"
            with open(token_file, "w") as f:
                f.write(result["access_token"])
            print(f"💾 Token saved to: {token_file}")
            print()
            print("✅ You can now use this token to test the API!")

    elif choice == "2":
        print()
        email = input("Enter email for new user: ").strip()
        password = input("Enter password: ").strip()
        print()

        user_id = create_test_user(email, password)

        if user_id:
            print()
            print("Now signing in to get token...")
            get_auth_token(email, password)

    else:
        print("❌ Invalid choice")
