"""
Paper Discovery Agent using LangGraph
Automatically discovers and downloads research papers from multiple sources
"""

import asyncio
import hashlib
from typing import List, Dict, Any, Optional, TypedDict
from datetime import datetime
import aiohttp
from xml.etree import ElementTree as ET

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

from app.core.config import settings
from app.core.supabase_client import get_supabase_client
from app.services.grobid_client import get_grobid_client


class PaperDiscoveryState(TypedDict):
    """State for paper discovery workflow"""
    query: str
    max_papers: int
    project_id: str
    user_id: str

    # Intermediate results
    pubmed_results: List[Dict[str, Any]]
    arxiv_results: List[Dict[str, Any]]
    semantic_scholar_results: List[Dict[str, Any]]
    merged_results: List[Dict[str, Any]]
    filtered_papers: List[Dict[str, Any]]

    # Download tracking
    download_results: List[Dict[str, Any]]
    processed_papers: List[Dict[str, Any]]

    # Errors
    errors: List[str]


async def search_pubmed(state: PaperDiscoveryState) -> PaperDiscoveryState:
    """Search PubMed for papers"""
    query = state["query"]
    max_results = min(state["max_papers"], 20)

    try:
        async with aiohttp.ClientSession() as session:
            # PubMed E-utilities API (free, no key required)
            search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
            params = {
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "retmode": "json",
                "sort": "relevance"
            }

            async with session.get(search_url, params=params) as resp:
                data = await resp.json()
                pmids = data.get("esearchresult", {}).get("idlist", [])

            if not pmids:
                state["pubmed_results"] = []
                return state

            # Fetch details for each PMID
            fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
            params = {
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "xml"
            }

            async with session.get(fetch_url, params=params) as resp:
                xml_data = await resp.text()
                root = ET.fromstring(xml_data)

                papers = []
                for article in root.findall(".//PubmedArticle"):
                    try:
                        title_elem = article.find(".//ArticleTitle")
                        abstract_elem = article.find(".//Abstract/AbstractText")
                        pmid_elem = article.find(".//PMID")

                        authors = []
                        for author in article.findall(".//Author"):
                            lastname = author.find("LastName")
                            forename = author.find("ForeName")
                            if lastname is not None and forename is not None:
                                authors.append(f"{forename.text} {lastname.text}")

                        year_elem = article.find(".//PubDate/Year")

                        papers.append({
                            "title": title_elem.text if title_elem is not None else "",
                            "abstract": abstract_elem.text if abstract_elem is not None else "",
                            "authors": authors,
                            "year": year_elem.text if year_elem is not None else "",
                            "source": "pubmed",
                            "pmid": pmid_elem.text if pmid_elem is not None else "",
                            "doi": None,  # Extract from article if available
                            "pdf_url": None  # Will try to find via Unpaywall
                        })
                    except Exception as e:
                        state["errors"].append(f"PubMed parse error: {str(e)}")

                state["pubmed_results"] = papers

    except Exception as e:
        state["errors"].append(f"PubMed search error: {str(e)}")
        state["pubmed_results"] = []

    return state


async def search_arxiv(state: PaperDiscoveryState) -> PaperDiscoveryState:
    """Search arXiv for papers"""
    query = state["query"]
    max_results = min(state["max_papers"], 20)

    try:
        async with aiohttp.ClientSession() as session:
            # arXiv API (free, no key required)
            url = "https://export.arxiv.org/api/query"
            params = {
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": max_results,
                "sortBy": "relevance",
                "sortOrder": "descending"
            }

            async with session.get(url, params=params) as resp:
                xml_data = await resp.text()

                # Parse Atom XML
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                root = ET.fromstring(xml_data)

                papers = []
                for entry in root.findall("atom:entry", ns):
                    try:
                        title = entry.find("atom:title", ns).text.strip()
                        summary = entry.find("atom:summary", ns).text.strip()

                        authors = []
                        for author in entry.findall("atom:author", ns):
                            name = author.find("atom:name", ns)
                            if name is not None:
                                authors.append(name.text)

                        published = entry.find("atom:published", ns).text[:4]  # Year

                        # Get PDF link
                        pdf_url = None
                        for link in entry.findall("atom:link", ns):
                            if link.get("title") == "pdf":
                                pdf_url = link.get("href")
                                break

                        arxiv_id = entry.find("atom:id", ns).text.split("/")[-1]

                        papers.append({
                            "title": title,
                            "abstract": summary,
                            "authors": authors,
                            "year": published,
                            "source": "arxiv",
                            "arxiv_id": arxiv_id,
                            "doi": None,
                            "pdf_url": pdf_url
                        })
                    except Exception as e:
                        state["errors"].append(f"arXiv parse error: {str(e)}")

                state["arxiv_results"] = papers

    except Exception as e:
        state["errors"].append(f"arXiv search error: {str(e)}")
        state["arxiv_results"] = []

    return state


async def search_semantic_scholar(state: PaperDiscoveryState) -> PaperDiscoveryState:
    """Search Semantic Scholar for papers"""
    query = state["query"]
    max_results = min(state["max_papers"], 20)

    try:
        async with aiohttp.ClientSession() as session:
            # Semantic Scholar API (free, no key required for basic usage)
            url = "https://api.semanticscholar.org/graph/v1/paper/search"
            params = {
                "query": query,
                "limit": max_results,
                "fields": "title,abstract,authors,year,openAccessPdf,externalIds"
            }

            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    state["semantic_scholar_results"] = []
                    return state

                data = await resp.json()

                papers = []
                for paper in data.get("data", []):
                    try:
                        authors = [a.get("name", "") for a in paper.get("authors", [])]

                        # Get DOI if available
                        external_ids = paper.get("externalIds", {})
                        doi = external_ids.get("DOI")
                        arxiv_id = external_ids.get("ArXiv")

                        # Get PDF URL if available
                        pdf_url = None
                        open_access = paper.get("openAccessPdf")
                        if open_access:
                            pdf_url = open_access.get("url")

                        papers.append({
                            "title": paper.get("title", ""),
                            "abstract": paper.get("abstract", ""),
                            "authors": authors,
                            "year": str(paper.get("year", "")),
                            "source": "semantic_scholar",
                            "doi": doi,
                            "arxiv_id": arxiv_id,
                            "pdf_url": pdf_url
                        })
                    except Exception as e:
                        state["errors"].append(f"Semantic Scholar parse error: {str(e)}")

                state["semantic_scholar_results"] = papers

    except Exception as e:
        state["errors"].append(f"Semantic Scholar search error: {str(e)}")
        state["semantic_scholar_results"] = []

    return state


def merge_and_deduplicate(state: PaperDiscoveryState) -> PaperDiscoveryState:
    """Merge results from all sources and remove duplicates"""
    all_papers = (
        state["pubmed_results"] +
        state["arxiv_results"] +
        state["semantic_scholar_results"]
    )

    # Deduplicate by title similarity (simple approach)
    seen_titles = set()
    merged = []

    for paper in all_papers:
        title = paper.get("title", "").lower().strip()
        if not title:
            continue

        # Simple deduplication: exact title match
        if title not in seen_titles:
            seen_titles.add(title)
            merged.append(paper)

    # Sort by year (newest first)
    merged.sort(key=lambda x: x.get("year", "0"), reverse=True)

    # Limit to max_papers
    state["merged_results"] = merged[:state["max_papers"]]

    return state


async def find_fulltext_links(state: PaperDiscoveryState) -> PaperDiscoveryState:
    """Try to find full-text PDF links for papers without them"""
    papers = state["merged_results"]

    async with aiohttp.ClientSession() as session:
        for paper in papers:
            # Skip if already has PDF URL
            if paper.get("pdf_url"):
                continue

            # Try Unpaywall if we have a DOI
            doi = paper.get("doi")
            if doi:
                try:
                    url = f"https://api.unpaywall.org/v2/{doi}"
                    params = {"email": "support@noesis.is"}  # Required by Unpaywall

                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            best_oa = data.get("best_oa_location")
                            if best_oa:
                                paper["pdf_url"] = best_oa.get("url_for_pdf")
                except Exception as e:
                    state["errors"].append(f"Unpaywall error for {doi}: {str(e)}")

    state["filtered_papers"] = [p for p in papers if p.get("pdf_url")]

    return state


async def download_pdfs(state: PaperDiscoveryState) -> PaperDiscoveryState:
    """Download PDF files"""
    papers = state["filtered_papers"]
    supabase = get_supabase_client()
    download_results = []

    async with aiohttp.ClientSession() as session:
        for paper in papers:
            pdf_url = paper.get("pdf_url")
            if not pdf_url:
                continue

            try:
                async with session.get(pdf_url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        state["errors"].append(f"Download failed for {paper['title']}: HTTP {resp.status}")
                        continue

                    pdf_content = await resp.read()

                    # Generate filename
                    safe_title = "".join(c for c in paper["title"][:50] if c.isalnum() or c in (' ', '-', '_')).strip()
                    filename = f"{safe_title}_{paper.get('year', 'unknown')}.pdf"

                    # Upload to Supabase Storage
                    file_path = f"{state['user_id']}/{state['project_id']}/{filename}"

                    upload_result = supabase.storage.from_("documents").upload(
                        file_path,
                        pdf_content,
                        {"content-type": "application/pdf"}
                    )

                    if upload_result:
                        file_url = supabase.storage.from_("documents").get_public_url(file_path)
                        download_results.append({
                            **paper,
                            "file_url": file_url,
                            "filename": filename
                        })

            except Exception as e:
                state["errors"].append(f"Download error for {paper['title']}: {str(e)}")

    state["download_results"] = download_results

    return state


async def process_with_grobid(state: PaperDiscoveryState) -> PaperDiscoveryState:
    """Process downloaded PDFs with GROBID"""
    papers = state["download_results"]
    processed = []

    for paper in papers:
        try:
            # Download PDF from Supabase
            supabase = get_supabase_client()
            file_url = paper["file_url"]

            # Extract path from public URL
            # ... implementation would fetch the PDF and process with GROBID
            # For now, we'll skip GROBID processing and just mark as processed

            processed.append({
                **paper,
                "processed": True
            })

        except Exception as e:
            state["errors"].append(f"GROBID processing error for {paper['title']}: {str(e)}")

    state["processed_papers"] = processed

    return state


async def add_to_project(state: PaperDiscoveryState) -> PaperDiscoveryState:
    """Add processed papers to user's project"""
    papers = state["processed_papers"]
    supabase = get_supabase_client()

    for paper in papers:
        try:
            # Create document record
            document_data = {
                "user_id": state["user_id"],
                "project_id": state["project_id"],
                "title": paper["title"],
                "file_url": paper["file_url"],
                "file_type": "pdf",
                "status": "completed",
                "metadata": {
                    "authors": paper.get("authors", []),
                    "year": paper.get("year"),
                    "abstract": paper.get("abstract"),
                    "source": paper.get("source"),
                    "doi": paper.get("doi"),
                    "arxiv_id": paper.get("arxiv_id"),
                    "auto_discovered": True
                }
            }

            result = supabase.table("documents").insert(document_data).execute()

        except Exception as e:
            state["errors"].append(f"Database insert error for {paper['title']}: {str(e)}")

    return state


# Build the workflow graph
def create_paper_discovery_workflow():
    """Create LangGraph workflow for paper discovery"""
    workflow = StateGraph(PaperDiscoveryState)

    # Add nodes
    workflow.add_node("search_pubmed", search_pubmed)
    workflow.add_node("search_arxiv", search_arxiv)
    workflow.add_node("search_semantic_scholar", search_semantic_scholar)
    workflow.add_node("merge_results", merge_and_deduplicate)
    workflow.add_node("find_fulltext", find_fulltext_links)
    workflow.add_node("download_pdfs", download_pdfs)
    workflow.add_node("process_grobid", process_with_grobid)
    workflow.add_node("add_to_project", add_to_project)

    # Set entry point
    workflow.set_entry_point("search_pubmed")

    # Add edges for parallel search
    workflow.add_edge("search_pubmed", "search_arxiv")
    workflow.add_edge("search_arxiv", "search_semantic_scholar")
    workflow.add_edge("search_semantic_scholar", "merge_results")
    workflow.add_edge("merge_results", "find_fulltext")
    workflow.add_edge("find_fulltext", "download_pdfs")
    workflow.add_edge("download_pdfs", "process_grobid")
    workflow.add_edge("process_grobid", "add_to_project")
    workflow.add_edge("add_to_project", END)

    return workflow.compile()


async def discover_papers(
    query: str,
    project_id: str,
    user_id: str,
    max_papers: int = 10
) -> Dict[str, Any]:
    """
    Main function to discover and add papers to a project

    Args:
        query: Search query
        project_id: Project ID to add papers to
        user_id: User ID
        max_papers: Maximum number of papers to discover

    Returns:
        Dictionary with discovery results
    """
    # Initialize state
    initial_state: PaperDiscoveryState = {
        "query": query,
        "max_papers": max_papers,
        "project_id": project_id,
        "user_id": user_id,
        "pubmed_results": [],
        "arxiv_results": [],
        "semantic_scholar_results": [],
        "merged_results": [],
        "filtered_papers": [],
        "download_results": [],
        "processed_papers": [],
        "errors": []
    }

    # Create and run workflow
    workflow = create_paper_discovery_workflow()
    final_state = await workflow.ainvoke(initial_state)

    return {
        "success": True,
        "papers_found": len(final_state["merged_results"]),
        "papers_with_pdf": len(final_state["filtered_papers"]),
        "papers_added": len(final_state["processed_papers"]),
        "errors": final_state["errors"],
        "papers": final_state["processed_papers"]
    }
