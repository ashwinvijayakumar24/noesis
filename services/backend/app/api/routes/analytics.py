"""
Analytics API Endpoints

Provides endpoints for data visualization and analytics.
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from app.core.supabase_client import supabase
from app.core.security_middleware import SecureAuthValidator
from typing import Optional, List, Dict, Any
import json
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


# Helper to extract user info from token
def get_current_user(authorization: str = Header(None)):
    if supabase is None:
        raise HTTPException(
            status_code=500,
            detail="Supabase not configured"  # Don't expose environment details
        )

    # Use secure token validator
    token = SecureAuthValidator.validate_bearer_token(authorization)

    try:
        user = supabase.auth.get_user(token)
        return user.user.id
    except Exception as e:
        logger.warning(f"Token validation failed: {str(e)}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"  # Don't expose error details
        )


@router.get("/projects/{project_id}/citation-graph")
def get_citation_graph(
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Generate citation network graph data for visualization.

    Returns:
        - nodes: List of papers (with metadata)
        - edges: List of citation relationships
        - metrics: Graph-level statistics
    """
    print(f"[ANALYTICS] Generating citation graph for project_id={project_id}")

    # 1. Verify project belongs to user
    project_res = supabase.table("projects").select("id, title")\
        .eq("id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = project_res.data[0]

    # 2. Get all documents in the project (including analysis column)
    docs_res = supabase.table("documents").select("id, title, metadata, analysis")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not docs_res.data:
        return {
            "nodes": [],
            "edges": [],
            "metrics": {
                "total_papers": 0,
                "total_citations": 0,
                "avg_citations_per_paper": 0
            }
        }

    documents = docs_res.data
    print(f"[ANALYTICS] Found {len(documents)} documents")

    # 3. Build nodes (papers)
    nodes = []
    doc_id_map = {}  # Map document IDs to array indices for edge building

    for idx, doc in enumerate(documents):
        # Parse metadata (contains RAG info)
        metadata = doc.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except:
                metadata = {}

        # Parse analysis (contains paper analysis, authors, citations)
        analysis = doc.get("analysis") or {}
        if isinstance(analysis, str):
            try:
                analysis = json.loads(analysis)
            except:
                analysis = {}

        # Extract citation metadata (author info, year)
        citation_metadata = analysis.get("citation_metadata", {})

        # Extract authors from citation_metadata
        authors = citation_metadata.get("all_authors", [])

        # Extract year from citation_metadata
        year_str = citation_metadata.get("year", "N/A")
        try:
            year = int(year_str) if year_str and year_str != "N/A" else None
        except:
            year = None

        # If no year found, try to extract from title or use current year as fallback
        if not year:
            import re
            title = doc.get("title", "")
            year_match = re.search(r'\b(19|20)\d{2}\b', title)
            if year_match:
                year = int(year_match.group(0))
            else:
                # Use a recent year as default for visualization purposes
                year = 2023

        # Extract citations from key_citations in analysis
        key_citations = analysis.get("key_citations", [])

        # Parse key_citations into structured format
        citations = []
        for citation in key_citations:
            if isinstance(citation, str):
                # Try to extract title from citation string
                # Format is usually "Author (Year) Title. Journal."
                citations.append({"title": citation})
            elif isinstance(citation, dict):
                citations.append(citation)

        citation_count = len(citations)

        node = {
            "id": doc["id"],
            "title": doc.get("title", "Untitled"),
            "authors": authors,
            "year": year,
            "citation_count": citation_count,
            "journal": None,  # Not extracted yet
            "doi": None,  # Not extracted yet
            "citations": citations,  # Will use this to build edges
            "type": "paper"
        }

        nodes.append(node)
        doc_id_map[doc["id"]] = idx

    # 4. Build edges (citation relationships)
    edges = []
    edge_id = 0

    for node in nodes:
        source_id = node["id"]
        citations = node.get("citations", [])

        # For each citation, check if it's in our document set
        for citation in citations:
            citation_title = citation.get("title", "").lower().strip()

            if not citation_title:
                continue

            # Try to find matching document in our set
            for target_node in nodes:
                target_title = target_node["title"].lower().strip()

                # Fuzzy matching: exact match, contains, or contained by
                if citation_title == target_title or citation_title in target_title or target_title in citation_title:
                    edge = {
                        "id": f"edge_{edge_id}",
                        "source": source_id,
                        "target": target_node["id"],
                        "type": "citation"
                    }
                    edges.append(edge)
                    edge_id += 1
                    break

    print(f"[ANALYTICS] Built {len(nodes)} nodes and {len(edges)} edges")

    # 5. Calculate graph metrics
    total_citations = sum(node["citation_count"] for node in nodes)
    avg_citations = total_citations / len(nodes) if nodes else 0

    # Calculate in-degree (how many papers cite this one) for each node
    in_degree_map = {node["id"]: 0 for node in nodes}
    for edge in edges:
        in_degree_map[edge["target"]] += 1

    # Add in-degree to nodes
    for node in nodes:
        node["in_degree"] = in_degree_map.get(node["id"], 0)

    # Find most influential papers (highest in-degree within project)
    sorted_by_influence = sorted(nodes, key=lambda x: x["in_degree"], reverse=True)
    most_influential = sorted_by_influence[:5] if len(sorted_by_influence) >= 5 else sorted_by_influence

    metrics = {
        "total_papers": len(nodes),
        "total_citations": total_citations,
        "avg_citations_per_paper": round(avg_citations, 2),
        "total_internal_citations": len(edges),
        "most_influential_papers": [
            {
                "id": paper["id"],
                "title": paper["title"],
                "in_degree": paper["in_degree"]
            }
            for paper in most_influential
        ]
    }

    return {
        "nodes": nodes,
        "edges": edges,
        "metrics": metrics
    }


@router.get("/projects/{project_id}/analytics-summary")
def get_analytics_summary(
    project_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Get high-level analytics summary for the project.

    Returns summary statistics and distributions.
    """
    print(f"[ANALYTICS] Getting summary for project_id={project_id}")

    # Verify project
    project_res = supabase.table("projects").select("*")\
        .eq("id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    if not project_res.data:
        raise HTTPException(status_code=404, detail="Project not found")

    project = project_res.data[0]

    # Get documents
    docs_res = supabase.table("documents").select("*")\
        .eq("project_id", project_id)\
        .eq("user_id", user_id)\
        .execute()

    documents = docs_res.data or []

    # Calculate statistics
    total_papers = len(documents)

    if total_papers == 0:
        return {
            "total_papers": 0,
            "total_authors": 0,
            "year_range": None,
            "total_citations": 0,
            "avg_citations": 0
        }

    # Extract metadata
    all_authors = set()
    years = []
    total_citations = 0

    for doc in documents:
        metadata = doc.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except:
                metadata = {}

        # Authors
        authors = metadata.get("authors", [])
        for author in authors:
            if isinstance(author, str):
                all_authors.add(author)
            elif isinstance(author, dict) and author.get("name"):
                all_authors.add(author["name"])

        # Year
        year = metadata.get("year")
        if year:
            years.append(year)

        # Citations
        citations = metadata.get("citations", [])
        total_citations += len(citations)

    year_range = None
    if years:
        year_range = {
            "min": min(years),
            "max": max(years)
        }

    avg_citations = round(total_citations / total_papers, 2) if total_papers > 0 else 0

    return {
        "total_papers": total_papers,
        "total_authors": len(all_authors),
        "year_range": year_range,
        "total_citations": total_citations,
        "avg_citations": avg_citations
    }
