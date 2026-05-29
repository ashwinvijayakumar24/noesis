"""
Semantic Scholar API Client

Provides interface to Semantic Scholar's free academic search API.
Docs: https://api.semanticscholar.org/api-docs/
"""

import requests
import logging
from typing import List, Dict, Any, Optional
from app.core.privacy import safe_exception

BASE_URL = "https://api.semanticscholar.org/graph/v1"
logger = logging.getLogger(__name__)

# Fields to request from API
PAPER_FIELDS = "paperId,title,abstract,year,authors,citationCount,referenceCount,influentialCitationCount,fieldsOfStudy,s2FieldsOfStudy,publicationTypes,publicationDate,journal,externalIds,url,openAccessPdf"


class SemanticScholarAPI:
    """Client for Semantic Scholar API"""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Semantic Scholar API client.

        Args:
            api_key: Optional API key for higher rate limits (5000 req/5min vs 100 req/5min)
        """
        self.api_key = api_key
        self.headers = {}
        if api_key:
            self.headers["x-api-key"] = api_key

    def search_papers(
        self,
        query: str,
        limit: int = 10,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
        fields_of_study: Optional[List[str]] = None,
        min_citation_count: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for papers by keywords.

        Args:
            query: Search query (keywords)
            limit: Maximum number of results (default 10, max 100)
            year_min: Minimum publication year
            year_max: Maximum publication year
            fields_of_study: Filter by fields (e.g., ["Computer Science", "Medicine"])
            min_citation_count: Minimum citation count

        Returns:
            List of paper dictionaries
        """
        logger.info("[SEMANTIC-SCHOLAR] Searching papers")

        # Build query parameters
        params = {
            "query": query,
            "limit": min(limit, 100),  # API max is 100
            "fields": PAPER_FIELDS
        }

        # Add filters
        if year_min and year_max:
            params["year"] = f"{year_min}-{year_max}"
        elif year_min:
            params["year"] = f"{year_min}-"
        elif year_max:
            params["year"] = f"-{year_max}"

        if fields_of_study:
            params["fieldsOfStudy"] = ",".join(fields_of_study)

        if min_citation_count:
            params["minCitationCount"] = min_citation_count

        try:
            response = requests.get(
                f"{BASE_URL}/paper/search",
                params=params,
                headers=self.headers,
                timeout=15
            )

            # Handle rate limiting — don't sleep/retry, just return empty
            if response.status_code == 429:
                logger.info("[SEMANTIC-SCHOLAR] Rate limited, returning empty results")
                return []

            response.raise_for_status()
            data = response.json()

            papers = data.get("data", [])
            logger.info("[SEMANTIC-SCHOLAR] Found %s papers", len(papers))

            return self._normalize_papers(papers)

        except Exception as e:
            logger.warning("[SEMANTIC-SCHOLAR] Search failed: %s", safe_exception(e))
            return []

    def get_recommendations(self, paper_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get paper recommendations based on a seed paper.

        Args:
            paper_id: Semantic Scholar paper ID
            limit: Maximum number of recommendations

        Returns:
            List of recommended paper dictionaries
        """
        logger.info("[SEMANTIC-SCHOLAR] Getting recommendations for paper")

        try:
            response = requests.get(
                f"{BASE_URL}/paper/{paper_id}/recommendations",
                params={"fields": PAPER_FIELDS, "limit": min(limit, 100)},
                headers=self.headers,
                timeout=30
            )

            if response.status_code == 429:
                logger.info("[SEMANTIC-SCHOLAR] Rate limited, returning empty results")
                return []

            response.raise_for_status()
            data = response.json()

            papers = data.get("recommendedPapers", [])
            logger.info("[SEMANTIC-SCHOLAR] Found %s recommendations", len(papers))

            return self._normalize_papers(papers)

        except Exception as e:
            logger.warning("[SEMANTIC-SCHOLAR] Recommendation lookup failed: %s", safe_exception(e))
            return []

    def _normalize_papers(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize Semantic Scholar paper format to our internal format.

        Args:
            papers: Raw papers from API

        Returns:
            Normalized paper dictionaries
        """
        normalized = []

        for paper in papers:
            # Extract DOI
            doi = None
            external_ids = paper.get("externalIds", {})
            if external_ids:
                doi = external_ids.get("DOI") or external_ids.get("ArXiv")

            # Extract authors
            authors = []
            if paper.get("authors"):
                authors = [author.get("name", "Unknown") for author in paper["authors"]]

            # Extract fields of study
            fields = []
            if paper.get("s2FieldsOfStudy"):
                fields = [field.get("category") for field in paper["s2FieldsOfStudy"] if field.get("category")]
            elif paper.get("fieldsOfStudy"):
                fields = paper["fieldsOfStudy"]

            # Extract PDF URL
            pdf_url = None
            if paper.get("openAccessPdf"):
                pdf_url = paper["openAccessPdf"].get("url")

            # Extract journal
            journal = None
            if paper.get("journal"):
                journal = paper["journal"].get("name")

            # Publication type
            pub_type = None
            if paper.get("publicationTypes"):
                pub_type = paper["publicationTypes"][0] if paper["publicationTypes"] else None

            normalized_paper = {
                "title": paper.get("title", "Untitled"),
                "abstract": paper.get("abstract"),
                "authors": authors,
                "year": paper.get("year"),
                "doi": doi,
                "arxiv_id": external_ids.get("ArXiv") if external_ids else None,
                "pubmed_id": external_ids.get("PubMed") if external_ids else None,
                "semantic_scholar_id": paper.get("paperId"),
                "source": "semantic_scholar",
                "paper_url": paper.get("url"),
                "pdf_url": pdf_url,
                "citation_count": paper.get("citationCount"),
                "journal_name": journal,
                "publication_type": pub_type,
                "fields_of_study": fields
            }

            normalized.append(normalized_paper)

        return normalized
