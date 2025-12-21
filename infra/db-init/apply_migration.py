#!/usr/bin/env python3
"""
Apply database migrations to Supabase.
Reads SQL files from the db-init directory and executes them via Supabase.
"""

import os
import sys
from pathlib import Path

# Add the backend directory to the path to import the Supabase client
backend_path = Path(__file__).parent.parent.parent / "services" / "backend"
sys.path.insert(0, str(backend_path))

from app.core.supabase_client import supabase
from dotenv import load_dotenv

# Load environment variables
env_path = backend_path / ".env"
load_dotenv(env_path)


def apply_migration(sql_file: Path):
    """Apply a SQL migration file to Supabase."""
    print(f"\n{'='*60}")
    print(f"Applying migration: {sql_file.name}")
    print(f"{'='*60}")

    # Read the SQL file
    with open(sql_file, 'r') as f:
        sql_content = f.read()

    # Split into individual statements (basic splitting by semicolon)
    statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]

    print(f"Found {len(statements)} SQL statements to execute\n")

    # Execute each statement
    for i, statement in enumerate(statements, 1):
        # Skip comments-only statements
        if statement.replace('-', '').replace('=', '').strip().startswith('--'):
            continue

        try:
            print(f"[{i}/{len(statements)}] Executing statement...")
            # Show first 100 chars of the statement
            preview = statement[:100].replace('\n', ' ')
            print(f"    {preview}{'...' if len(statement) > 100 else ''}")

            # Execute via Supabase RPC or direct SQL execution
            # Note: Supabase client doesn't have direct SQL execution,
            # so we'll use the PostgREST API to execute raw SQL
            result = supabase.rpc('exec_sql', {'sql': statement}).execute()
            print(f"    ✓ Success")

        except Exception as e:
            # Check if error is about function not existing
            if "function public.exec_sql" in str(e).lower():
                print(f"\n⚠️  Warning: exec_sql function not available in Supabase")
                print(f"    Please run this SQL manually in the Supabase SQL Editor:")
                print(f"\n{'-'*60}")
                print(sql_content)
                print(f"{'-'*60}\n")
                return False
            else:
                print(f"    ✗ Error: {e}")
                # Continue with other statements

    print(f"\n✓ Migration {sql_file.name} completed!")
    return True


def main():
    """Main function to apply all migrations in order."""
    if not supabase:
        print("❌ Error: Supabase client not configured")
        print("Please set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env")
        sys.exit(1)

    print("\n" + "="*60)
    print("SUPABASE DATABASE MIGRATION TOOL")
    print("="*60)
    print(f"Supabase URL: {os.getenv('SUPABASE_URL')}")

    # Get migration files
    migrations_dir = Path(__file__).parent
    sql_files = sorted(migrations_dir.glob("*.sql"))

    if not sql_files:
        print("\n⚠️  No SQL migration files found in", migrations_dir)
        sys.exit(0)

    print(f"\nFound {len(sql_files)} migration file(s):")
    for f in sql_files:
        print(f"  • {f.name}")

    print("\n" + "="*60)
    print("IMPORTANT: Supabase doesn't support direct SQL execution via API")
    print("="*60)
    print("\nPlease follow these steps:")
    print("1. Go to https://app.supabase.com/project/ufnaadgdrraqnatvgarq/sql")
    print("2. Copy and paste the SQL from the files below")
    print("3. Run the SQL in the Supabase SQL Editor\n")

    for sql_file in sql_files:
        print(f"\n{'='*60}")
        print(f"FILE: {sql_file.name}")
        print(f"{'='*60}\n")

        with open(sql_file, 'r') as f:
            print(f.read())

    print(f"\n{'='*60}")
    print("After running the SQL, your database schema will be ready!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
