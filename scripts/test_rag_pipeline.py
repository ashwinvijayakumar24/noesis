#!/usr/bin/env python3
"""
Comprehensive RAG Pipeline Testing Script

This script tests the entire RAG pipeline end-to-end:
1. Authentication
2. Project creation
3. Document upload
4. RAG ingestion
5. Vector retrieval
6. RAG query

User ID: 8e615456-4a3a-4328-b489-7c8a9f2f38ed
Test PDF: services/backend/app/pdfs/test.pdf
"""

import os
import sys
import json
import time
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
BACKEND_URL = "http://localhost:8000"

# Test configuration
TEST_USER_ID = "8e615456-4a3a-4328-b489-7c8a9f2f38ed"
TEST_PDF_PATH = backend_path / "app" / "pdfs" / "test.pdf"

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_step(step_num, title):
    """Print a step header"""
    print()
    print("=" * 80)
    print(f"{Colors.BOLD}{Colors.BLUE}STEP {step_num}: {title}{Colors.END}")
    print("=" * 80)

def print_success(message):
    """Print success message"""
    print(f"{Colors.GREEN}✅ {message}{Colors.END}")

def print_error(message):
    """Print error message"""
    print(f"{Colors.RED}❌ {message}{Colors.END}")

def print_info(message):
    """Print info message"""
    print(f"{Colors.YELLOW}ℹ️  {message}{Colors.END}")

def print_data(label, data):
    """Print formatted data"""
    print(f"{Colors.BOLD}{label}:{Colors.END}")
    print(json.dumps(data, indent=2))


class RAGPipelineTester:
    def __init__(self):
        self.supabase = None
        self.auth_token = None
        self.user_id = TEST_USER_ID
        self.project_id = None
        self.document_id = None

    def step1_authenticate(self, email, password):
        """Step 1: Authenticate and get JWT token"""
        print_step(1, "Authentication")

        if not SUPABASE_URL or not SUPABASE_ANON_KEY:
            print_error("Supabase credentials not found in .env")
            return False

        try:
            self.supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

            print_info(f"Signing in with: {email}")
            response = self.supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })

            if response.user and response.session:
                self.auth_token = response.session.access_token
                self.user_id = response.user.id

                print_success("Authentication successful!")
                print(f"   User ID: {self.user_id}")
                print(f"   Email: {response.user.email}")
                print()
                print_info("JWT Token (first 50 chars):")
                print(f"   {self.auth_token[:50]}...")

                return True
            else:
                print_error("No session returned")
                return False

        except Exception as e:
            print_error(f"Authentication failed: {e}")
            return False

    def step2_test_backend_health(self):
        """Step 2: Test backend health"""
        print_step(2, "Backend Health Check")

        import requests

        try:
            # Test /health
            print_info("Testing /health endpoint...")
            response = requests.get(f"{BACKEND_URL}/health")
            print_data("Response", response.json())
            print_success(f"Backend is healthy (status: {response.status_code})")

            # Test /test-supabase
            print()
            print_info("Testing /test-supabase endpoint...")
            response = requests.get(f"{BACKEND_URL}/test-supabase")
            print_data("Response", response.json())

            if response.json().get("connection") == "ok":
                print_success("Supabase connection working")
                return True
            else:
                print_error("Supabase connection failed")
                return False

        except Exception as e:
            print_error(f"Backend health check failed: {e}")
            return False

    def step3_create_project(self):
        """Step 3: Create a test project"""
        print_step(3, "Create Project")

        import requests

        try:
            print_info("Creating test project...")

            headers = {
                "Authorization": f"Bearer {self.auth_token}"
            }

            data = {
                "title": "RAG Pipeline Test Project",
                "description": "Testing the complete RAG ingestion and retrieval pipeline"
            }

            response = requests.post(
                f"{BACKEND_URL}/projects",
                headers=headers,
                data=data
            )

            if response.status_code in [200, 201]:
                result = response.json()
                self.project_id = result["project"]["id"]

                print_success("Project created!")
                print_data("Project", result["project"])

                return True
            else:
                print_error(f"Project creation failed (status: {response.status_code})")
                print(response.text)
                return False

        except Exception as e:
            print_error(f"Project creation error: {e}")
            return False

    def step4_upload_document(self):
        """Step 4: Upload test PDF document"""
        print_step(4, "Upload Document")

        import requests

        try:
            if not TEST_PDF_PATH.exists():
                print_error(f"Test PDF not found: {TEST_PDF_PATH}")
                return False

            print_info(f"Uploading PDF: {TEST_PDF_PATH.name}")
            print_info(f"File size: {TEST_PDF_PATH.stat().st_size / 1024 / 1024:.2f} MB")

            headers = {
                "Authorization": f"Bearer {self.auth_token}"
            }

            files = {
                "file": ("test.pdf", open(TEST_PDF_PATH, "rb"), "application/pdf")
            }

            data = {
                "project_id": self.project_id,
                "title": "Test Research Paper",
                "description": "Sample PDF for testing RAG pipeline"
            }

            response = requests.post(
                f"{BACKEND_URL}/documents/upload",
                headers=headers,
                files=files,
                data=data
            )

            if response.status_code in [200, 201]:
                result = response.json()
                self.document_id = result["document"]["id"]

                print_success("Document uploaded!")
                print_data("Document", {
                    "id": result["document"]["id"],
                    "title": result["document"]["title"],
                    "status": result["document"]["status"],
                    "file_size": result["document"].get("file_size"),
                    "project_id": result["document"]["project_id"]
                })

                return True
            else:
                print_error(f"Upload failed (status: {response.status_code})")
                print(response.text)
                return False

        except Exception as e:
            print_error(f"Upload error: {e}")
            return False

    def step5_ingest_document(self):
        """Step 5: Ingest document into RAG pipeline"""
        print_step(5, "RAG Ingestion (Synchronous)")

        import requests

        try:
            print_info(f"Ingesting document: {self.document_id}")
            print_info("This will:")
            print("   1. Extract text from PDF")
            print("   2. Chunk into ~500 token pieces")
            print("   3. Generate embeddings with OpenAI")
            print("   4. Store in pgvector database")
            print()
            print_info("This may take 30-60 seconds for a 4.7MB PDF...")

            headers = {
                "Authorization": f"Bearer {self.auth_token}"
            }

            start_time = time.time()

            response = requests.post(
                f"{BACKEND_URL}/rag/ingest-sync/{self.document_id}",
                headers=headers
            )

            elapsed = time.time() - start_time

            if response.status_code in [200, 201]:
                result = response.json()

                print_success(f"Ingestion completed in {elapsed:.1f} seconds!")
                print_data("Result", result)

                return True
            else:
                print_error(f"Ingestion failed (status: {response.status_code})")
                print(response.text)
                return False

        except Exception as e:
            print_error(f"Ingestion error: {e}")
            return False

    def step6_check_status(self):
        """Step 6: Check ingestion status"""
        print_step(6, "Check Ingestion Status")

        import requests

        try:
            print_info(f"Checking status for document: {self.document_id}")

            headers = {
                "Authorization": f"Bearer {self.auth_token}"
            }

            response = requests.get(
                f"{BACKEND_URL}/rag/status/{self.document_id}",
                headers=headers
            )

            if response.status_code == 200:
                result = response.json()

                print_success("Status retrieved!")
                print_data("Status", result)

                if result.get("status") == "embedded":
                    print_success(f"Document has {result.get('chunk_count')} chunks embedded!")
                    return True
                else:
                    print_error(f"Document status: {result.get('status')}")
                    return False
            else:
                print_error(f"Status check failed (status: {response.status_code})")
                print(response.text)
                return False

        except Exception as e:
            print_error(f"Status check error: {e}")
            return False

    def step7_test_retrieval(self):
        """Step 7: Test vector similarity search"""
        print_step(7, "Vector Retrieval Test")

        import requests

        try:
            test_query = "What are the main findings of this research?"

            print_info(f"Testing retrieval with query: '{test_query}'")

            headers = {
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json"
            }

            params = {
                "project_id": self.project_id,
                "query": test_query,
                "limit": 3
            }

            response = requests.post(
                f"{BACKEND_URL}/rag/retrieve",
                headers=headers,
                params=params
            )

            if response.status_code == 200:
                result = response.json()

                print_success(f"Retrieved {result.get('num_chunks')} chunks!")

                if result.get("chunks"):
                    for i, chunk in enumerate(result["chunks"], 1):
                        print()
                        print(f"{Colors.BOLD}Chunk {i} (similarity: {chunk.get('similarity', 0):.3f}):{Colors.END}")
                        content = chunk.get("content", "")
                        print(f"   {content[:200]}...")

                return True
            else:
                print_error(f"Retrieval failed (status: {response.status_code})")
                print(response.text)
                return False

        except Exception as e:
            print_error(f"Retrieval error: {e}")
            return False

    def step8_test_rag_query(self):
        """Step 8: Test full RAG query with answer generation"""
        print_step(8, "RAG Query Test (Full Pipeline)")

        import requests

        try:
            test_question = "What are the key conclusions and recommendations from this paper?"

            print_info(f"Asking question: '{test_question}'")
            print_info("This will retrieve relevant chunks and generate an AI answer...")
            print()

            headers = {
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json"
            }

            params = {
                "project_id": self.project_id,
                "query": test_question,
                "model": "gpt-4o",
                "max_chunks": 5
            }

            start_time = time.time()

            response = requests.post(
                f"{BACKEND_URL}/rag/query",
                headers=headers,
                params=params
            )

            elapsed = time.time() - start_time

            if response.status_code == 200:
                result = response.json()

                print_success(f"RAG query completed in {elapsed:.1f} seconds!")
                print()
                print(f"{Colors.BOLD}AI ANSWER:{Colors.END}")
                print("-" * 80)
                print(result.get("answer", "No answer"))
                print("-" * 80)
                print()
                print_info(f"Used {result.get('num_chunks')} chunks as context")
                print_info(f"Model: {result.get('model')}")

                return True
            else:
                print_error(f"RAG query failed (status: {response.status_code})")
                print(response.text)
                return False

        except Exception as e:
            print_error(f"RAG query error: {e}")
            return False

    def run_all_tests(self, email, password):
        """Run all tests in sequence"""
        print()
        print("=" * 80)
        print(f"{Colors.BOLD}{Colors.BLUE}NOESIS RAG PIPELINE - COMPREHENSIVE TEST{Colors.END}")
        print("=" * 80)
        print()
        print_info(f"Backend URL: {BACKEND_URL}")
        print_info(f"Test User ID: {TEST_USER_ID}")
        print_info(f"Test PDF: {TEST_PDF_PATH}")
        print()

        results = []

        # Run each step
        steps = [
            ("Authentication", lambda: self.step1_authenticate(email, password)),
            ("Backend Health", self.step2_test_backend_health),
            ("Create Project", self.step3_create_project),
            ("Upload Document", self.step4_upload_document),
            ("RAG Ingestion", self.step5_ingest_document),
            ("Check Status", self.step6_check_status),
            ("Vector Retrieval", self.step7_test_retrieval),
            ("RAG Query", self.step8_test_rag_query),
        ]

        for step_name, step_func in steps:
            try:
                success = step_func()
                results.append((step_name, success))

                if not success:
                    print_error(f"Test failed at step: {step_name}")
                    print_info("Stopping test execution")
                    break

                # Small delay between steps
                time.sleep(1)

            except KeyboardInterrupt:
                print()
                print_info("Test interrupted by user")
                break
            except Exception as e:
                print_error(f"Unexpected error in {step_name}: {e}")
                results.append((step_name, False))
                break

        # Print summary
        print()
        print("=" * 80)
        print(f"{Colors.BOLD}TEST SUMMARY{Colors.END}")
        print("=" * 80)

        for step_name, success in results:
            status = f"{Colors.GREEN}✅ PASS{Colors.END}" if success else f"{Colors.RED}❌ FAIL{Colors.END}"
            print(f"{status}  {step_name}")

        print()

        all_passed = all(success for _, success in results)
        if all_passed:
            print_success("🎉 ALL TESTS PASSED! RAG pipeline is fully operational!")
        else:
            print_error("Some tests failed. Please check the errors above.")

        return all_passed


if __name__ == "__main__":
    print()

    # Get credentials
    email = input("Enter your test user email [test@noesis.local]: ").strip() or "test@noesis.local"
    password = input("Enter password [TestPassword123!]: ").strip() or "TestPassword123!"

    # Run tests
    tester = RAGPipelineTester()
    tester.run_all_tests(email, password)
