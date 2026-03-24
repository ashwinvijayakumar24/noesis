"""
Pytest configuration for Noesis backend.

Excludes standalone integration scripts that are meant to be run directly
(not as part of the automated pytest suite).
"""

collect_ignore = [
    "tests/test_rag_optimization.py",  # Standalone integration script — requires live DB + project_id
]
