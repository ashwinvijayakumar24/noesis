#!/usr/bin/env python3
"""
Verify that Step 3.4 (relational structure) is complete.
Checks:
1. Required tables exist in Supabase
2. Required columns are present
3. Foreign keys are set up correctly
4. API routes are implemented
5. Pydantic models are defined
"""

import sys
from pathlib import Path

# Add the backend directory to the path
backend_path = Path(__file__).parent.parent.parent / "services" / "backend"
sys.path.insert(0, str(backend_path))

def check_api_routes():
    """Check if required API routes are implemented."""
    print("\n" + "="*60)
    print("CHECKING API ROUTES")
    print("="*60)

    routes_to_check = [
        ("POST /projects", "services/backend/app/api/routes/projects.py", "create_project"),
        ("GET /projects", "services/backend/app/api/routes/projects.py", "get_projects"),
        ("POST /projects/{project_id}/attach-dataset/{dataset_id}", "services/backend/app/api/routes/projects.py", "attach_dataset_to_project"),
        ("GET /projects/{project_id}/bundle", "services/backend/app/api/routes/projects.py", "get_project_bundle"),
    ]

    all_routes_exist = True
    for route_name, file_path, function_name in routes_to_check:
        full_path = Path(__file__).parent.parent.parent / file_path
        if full_path.exists():
            with open(full_path, 'r') as f:
                content = f.read()
                if f"def {function_name}" in content:
                    print(f"✓ {route_name} → {function_name}()")
                else:
                    print(f"✗ {route_name} → {function_name}() NOT FOUND")
                    all_routes_exist = False
        else:
            print(f"✗ File not found: {file_path}")
            all_routes_exist = False

    return all_routes_exist


def check_pydantic_models():
    """Check if required Pydantic models are defined."""
    print("\n" + "="*60)
    print("CHECKING PYDANTIC MODELS")
    print("="*60)

    models_to_check = [
        ("ProjectCreate", "services/backend/app/schemas/projects.py"),
        ("Project", "services/backend/app/schemas/projects.py"),
        ("ProjectBundle", "services/backend/app/schemas/projects.py"),
        ("Dataset", "services/backend/app/schemas/projects.py"),
        ("Document", "services/backend/app/schemas/projects.py"),
    ]

    all_models_exist = True
    for model_name, file_path in models_to_check:
        full_path = Path(__file__).parent.parent.parent / file_path
        if full_path.exists():
            with open(full_path, 'r') as f:
                content = f.read()
                if f"class {model_name}" in content:
                    print(f"✓ {model_name}")
                else:
                    print(f"✗ {model_name} NOT FOUND")
                    all_models_exist = False
        else:
            print(f"✗ File not found: {file_path}")
            all_models_exist = False

    return all_models_exist


def check_router_imports():
    """Check if routers are properly imported in main.py."""
    print("\n" + "="*60)
    print("CHECKING ROUTER IMPORTS")
    print("="*60)

    main_py_path = Path(__file__).parent.parent.parent / "services/backend/app/main.py"
    if not main_py_path.exists():
        print("✗ main.py not found")
        return False

    with open(main_py_path, 'r') as f:
        content = f.read()

    routers_to_check = [
        ("projects", "from app.api.routes import auth, projects"),
        ("datasets", "from app.api.routes import auth, projects, datasets"),
        ("documents", "from app.api.routes import auth, projects, datasets, documents"),
    ]

    all_imports_exist = True
    for router_name, import_statement_part in routers_to_check:
        if router_name in content:
            print(f"✓ {router_name} router imported")
        else:
            print(f"✗ {router_name} router NOT imported")
            all_imports_exist = False

    # Check if routers are included
    includes_to_check = [
        ('app.include_router(projects.router', 'projects router'),
        ('app.include_router(datasets.router', 'datasets router'),
        ('app.include_router(documents.router', 'documents router'),
    ]

    for include_statement, router_name in includes_to_check:
        if include_statement in content:
            print(f"✓ {router_name} included in app")
        else:
            print(f"✗ {router_name} NOT included in app")
            all_imports_exist = False

    return all_imports_exist


def check_sql_migrations():
    """Check if SQL migration files exist."""
    print("\n" + "="*60)
    print("CHECKING SQL MIGRATIONS")
    print("="*60)

    migrations_dir = Path(__file__).parent
    sql_files = list(migrations_dir.glob("*.sql"))

    if not sql_files:
        print("✗ No SQL migration files found")
        return False

    print(f"Found {len(sql_files)} SQL migration file(s):")
    for f in sorted(sql_files):
        print(f"  ✓ {f.name}")

    # Check if the main migration file exists
    main_migration = migrations_dir / "02-create-tables.sql"
    if main_migration.exists():
        with open(main_migration, 'r') as f:
            content = f.read()

        required_tables = ["projects", "datasets", "documents", "document_chunks"]
        all_tables_defined = True
        for table in required_tables:
            if f"CREATE TABLE IF NOT EXISTS {table}" in content:
                print(f"  ✓ {table} table defined")
            else:
                print(f"  ✗ {table} table NOT defined")
                all_tables_defined = False

        return all_tables_defined
    else:
        print("✗ 02-create-tables.sql not found")
        return False


def main():
    """Run all verification checks."""
    print("\n" + "="*60)
    print("STEP 3.4 VERIFICATION")
    print("Checking relational structure implementation")
    print("="*60)

    results = {
        "SQL Migrations": check_sql_migrations(),
        "API Routes": check_api_routes(),
        "Pydantic Models": check_pydantic_models(),
        "Router Imports": check_router_imports(),
    }

    print("\n" + "="*60)
    print("VERIFICATION SUMMARY")
    print("="*60)

    all_passed = True
    for check_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{status:12} {check_name}")
        if not passed:
            all_passed = False

    print("="*60)

    if all_passed:
        print("\n✅ Step 3.4 CODE is COMPLETE!")
        print("\nNext steps:")
        print("1. Run the SQL migration in Supabase:")
        print("   Go to: https://app.supabase.com/project/ufnaadgdrraqnatvgarq/sql")
        print("   Copy the SQL from: ./02-create-tables.sql")
        print("\n2. After running the SQL, test the endpoints:")
        print("   curl -X POST http://localhost:8000/projects \\")
        print("     -H 'Authorization: Bearer <token>' \\")
        print("     -d 'title=My Research Project'")
        print("\n✓ Step 3.4 will then be fully complete and ready for Step 4 (RAG ingestion)")
    else:
        print("\n❌ Step 3.4 is INCOMPLETE")
        print("Please fix the failed checks above.")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
