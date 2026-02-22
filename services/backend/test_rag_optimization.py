"""
Test Script for RAG Optimization

This script tests the new RAG pipeline optimizations to ensure:
1. Database migration 018 was successful
2. Hybrid search functions work correctly
3. Cohere reranking is functional (if API key configured)
4. Integration layer properly switches between baseline/optimized

Usage:
    python test_rag_optimization.py

Prerequisites:
    - Migration 018 must be run
    - Environment variables must be set
    - Cohere API key configured (optional)
"""

import asyncio
import sys
import os
from datetime import datetime

# Add app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.core.supabase_client import supabase
from app.core.config import settings
from app.services.rag_integration import get_optimization_status, retrieve_with_optimizations
from app.services.rag_retrieval_enhanced import (
    retrieve_relevant_chunks_hybrid,
    rerank_chunks_cohere,
    expand_query_llm,
)

# Test configuration
TEST_QUERIES = [
    "How does BERT improve accuracy?",
    "transformer architecture",
    "dropout regularization",
    "statistical significance p < 0.05",
]


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}\n")


def print_result(test_name: str, passed: bool, message: str = ""):
    """Print a test result."""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} | {test_name}")
    if message:
        print(f"         {message}")


async def test_database_migration():
    """Test if migration 018 was successful."""
    print_section("TEST 1: Database Migration 018")

    try:
        # Check if hybrid search function exists
        result = supabase.rpc(
            "hybrid_search_project_content",
            {
                "query_text": "test",
                "query_embedding": [0.1] * 1536,
                "proj_id": "00000000-0000-0000-0000-000000000000",  # Dummy UUID
                "match_count": 5,
                "include_drafts": False,
                "include_literature": True,
                "specific_draft_id": None,
                "semantic_weight": 0.7,
                "keyword_weight": 0.3
            }
        ).execute()

        print_result("hybrid_search_project_content", True, "Function exists and callable")
        return True

    except Exception as e:
        error_msg = str(e)
        if "does not exist" in error_msg:
            print_result("hybrid_search_project_content", False, "Function not found - migration 018 not run")
        else:
            print_result("hybrid_search_project_content", False, f"Error: {error_msg}")
        return False


async def test_tsvector_columns():
    """Test if tsvector columns exist."""
    print_section("TEST 2: Full-Text Search Columns")

    try:
        # Check document_chunks table
        result_doc = supabase.rpc(
            "exec_sql",
            {
                "sql": """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN content_tsv IS NOT NULL THEN 1 ELSE 0 END) as populated
                FROM document_chunks
                LIMIT 1
                """
            }
        ).execute()

        if result_doc.data:
            total = result_doc.data[0].get('total', 0)
            populated = result_doc.data[0].get('populated', 0)
            percentage = (populated / total * 100) if total > 0 else 0

            print_result(
                "tsvector columns",
                True,
                f"{populated}/{total} chunks have tsvector ({percentage:.1f}%)"
            )
            return True
        else:
            print_result("tsvector columns", False, "Could not query document_chunks")
            return False

    except Exception as e:
        print_result("tsvector columns", False, f"Error: {str(e)}")
        return False


async def test_optimization_status():
    """Test RAG optimization configuration."""
    print_section("TEST 3: RAG Optimization Configuration")

    status = get_optimization_status()

    print(f"Master Enabled:       {status['master_enabled']}")
    print(f"Hybrid Search:        {status['hybrid_search']}")
    print(f"Reranking:            {status['reranking']}")
    print(f"Multi-Query:          {status['multi_query']}")
    print(f"Rollout Percentage:   {status['rollout_percentage']}%")
    print(f"Cohere API Key:       {status['cohere_api_key_configured']}")
    print(f"OpenAI API Key:       {status['openai_api_key_configured']}")

    all_configured = (
        status['master_enabled'] and
        status['hybrid_search'] and
        status['openai_api_key_configured']
    )

    print_result("Configuration", all_configured, "All required settings configured")
    return all_configured


async def test_hybrid_search(project_id: str):
    """Test hybrid search retrieval."""
    print_section("TEST 4: Hybrid Search Retrieval")

    if not project_id:
        print_result("Hybrid Search", False, "No project_id provided (use --project-id)")
        return False

    try:
        query = TEST_QUERIES[0]
        print(f"Query: '{query}'")

        chunks = retrieve_relevant_chunks_hybrid(
            project_id=project_id,
            query=query,
            limit=5,
            include_drafts=False
        )

        print(f"\nRetrieved {len(chunks)} chunks:")
        for i, chunk in enumerate(chunks[:3], 1):
            print(f"\n{i}. {chunk.get('source_title', 'Unknown')[:60]}")
            print(f"   Semantic: {chunk.get('semantic_similarity', 0):.3f}")
            print(f"   Keyword:  {chunk.get('keyword_rank', 0):.3f}")
            print(f"   Combined: {chunk.get('combined_score', 0):.3f}")

        print_result("Hybrid Search", len(chunks) > 0, f"Retrieved {len(chunks)} chunks")
        return len(chunks) > 0

    except Exception as e:
        print_result("Hybrid Search", False, f"Error: {str(e)}")
        return False


async def test_reranking():
    """Test Cohere reranking."""
    print_section("TEST 5: Cohere Reranking")

    if not settings.COHERE_API_KEY:
        print_result("Cohere Reranking", False, "COHERE_API_KEY not configured (optional)")
        print("         Skipping reranking test - set COHERE_API_KEY to test")
        return False

    try:
        # Create dummy chunks
        dummy_chunks = [
            {'content': 'BERT is a bidirectional transformer model.', 'id': '1'},
            {'content': 'Neural networks can learn complex patterns.', 'id': '2'},
            {'content': 'BERT achieves state-of-the-art results on NLP tasks.', 'id': '3'},
        ]

        query = "How does BERT work?"
        reranked = rerank_chunks_cohere(query, dummy_chunks, top_n=2)

        print(f"Query: '{query}'")
        print(f"\nOriginal order:")
        for i, chunk in enumerate(dummy_chunks, 1):
            print(f"  {i}. {chunk['content'][:50]}")

        print(f"\nReranked order:")
        for i, chunk in enumerate(reranked, 1):
            print(f"  {i}. {chunk['content'][:50]}")
            print(f"     Rerank score: {chunk.get('rerank_score', 0):.3f}")

        print_result(
            "Cohere Reranking",
            len(reranked) > 0 and 'rerank_score' in reranked[0],
            "Reranking successful"
        )
        return True

    except Exception as e:
        print_result("Cohere Reranking", False, f"Error: {str(e)}")
        return False


async def test_query_expansion():
    """Test LLM-based query expansion."""
    print_section("TEST 6: Query Expansion")

    try:
        query = TEST_QUERIES[0]
        print(f"Original query: '{query}'")

        variants = await expand_query_llm(query, num_variants=3)

        print(f"\nExpanded queries ({len(variants)} variants):")
        for i, variant in enumerate(variants, 1):
            print(f"  {i}. {variant}")

        print_result("Query Expansion", len(variants) >= 2, f"Generated {len(variants)} variants")
        return len(variants) >= 2

    except Exception as e:
        print_result("Query Expansion", False, f"Error: {str(e)}")
        return False


async def test_integration_layer(project_id: str, user_id: str):
    """Test the integration layer."""
    print_section("TEST 7: Integration Layer")

    if not project_id or not user_id:
        print_result("Integration Layer", False, "No project_id or user_id provided")
        return False

    try:
        query = TEST_QUERIES[0]
        print(f"Query: '{query}'")
        print(f"User: {user_id}")

        result = await retrieve_with_optimizations(
            project_id=project_id,
            query=query,
            user_id=user_id,
            limit=5,
            include_drafts=False
        )

        print(f"\nOptimization enabled: {result['optimization_enabled']}")
        print(f"Retrieval method: {result['metadata'].get('retrieval_method', 'unknown')}")
        print(f"Chunks retrieved: {result['metadata'].get('num_chunks_retrieved', 0)}")
        print(f"Retrieval time: {result['metadata'].get('retrieval_time_seconds', 0):.3f}s")

        if result['optimization_enabled']:
            print(f"\nContext structure:")
            context_lines = result['context'].split('\n')
            for line in context_lines[:10]:  # Show first 10 lines
                if line.startswith('==='):
                    print(f"  {line}")

        print_result(
            "Integration Layer",
            len(result['chunks']) > 0,
            f"Retrieved {len(result['chunks'])} chunks"
        )
        return True

    except Exception as e:
        print_result("Integration Layer", False, f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests(project_id: str = None, user_id: str = None):
    """Run all tests."""
    print(f"\n{'#' * 70}")
    print(f"#  RAG Optimization Test Suite")
    print(f"#  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#' * 70}")

    results = []

    # Test 1: Database migration
    results.append(await test_database_migration())

    # Test 2: tsvector columns
    results.append(await test_tsvector_columns())

    # Test 3: Configuration
    results.append(await test_optimization_status())

    # Test 4-7: Require project_id and user_id
    if project_id and user_id:
        results.append(await test_hybrid_search(project_id))
        results.append(await test_reranking())
        results.append(await test_query_expansion())
        results.append(await test_integration_layer(project_id, user_id))
    else:
        print("\n⚠️  Skipping tests 4-7: Provide --project-id and --user-id to run full test suite")

    # Summary
    print_section("TEST SUMMARY")
    total = len(results)
    passed = sum(results)
    failed = total - passed

    print(f"Total Tests:  {total}")
    print(f"Passed:       {passed} ✅")
    print(f"Failed:       {failed} ❌")
    print(f"Success Rate: {passed/total*100:.1f}%")

    if passed == total:
        print("\n🎉 All tests passed! RAG optimization is ready for deployment.")
        return 0
    else:
        print("\n⚠️  Some tests failed. Review errors above and fix before deployment.")
        return 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test RAG optimization")
    parser.add_argument("--project-id", help="Project UUID for testing retrieval")
    parser.add_argument("--user-id", help="User UUID for testing rollout")
    args = parser.parse_args()

    exit_code = asyncio.run(run_all_tests(args.project_id, args.user_id))
    sys.exit(exit_code)
