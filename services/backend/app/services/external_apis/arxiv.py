"""
arXiv API Client

Provides interface to arXiv's free preprint repository API.
Docs: https://info.arxiv.org/help/api/index.html
"""

import requests
import time
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from urllib.parse import quote
from datetime import datetime

BASE_URL = "http://export.arxiv.org/api/query"

# arXiv categories that indicate STEM fields
STEM_CATEGORIES = {
    "cs", "math", "physics", "stat", "eess", "econ", "q-bio", "q-fin"
}


class ArXivAPI:
    """Client for arXiv API"""

    def __init__(self):
        """Initialize arXiv API client (no API key needed)"""
        pass

    def search_papers(
        self,
        query: str,
        limit: int = 10,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
        categories: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for papers on arXiv.

        Args:
            query: Search query (keywords)
            limit: Maximum number of results
            year_min: Minimum publication year
            year_max: Maximum publication year
            categories: Filter by arXiv categories (e.g., ["cs.AI", "cs.LG"])

        Returns:
            List of paper dictionaries
        """
        print(f"[ARXIV] Searching for: {query[:50]}...")

        # Build search query
        search_query = f"all:{query}"

        # Add category filter if provided
        if categories:
            cat_query = "+OR+".join([f"cat:{cat}" for cat in categories])
            search_query = f"({search_query})+AND+({cat_query})"

        # Build parameters
        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": limit,
            "sortBy": "relevance",
            "sortOrder": "descending"
        }

        try:
            response = requests.get(
                BASE_URL,
                params=params,
                timeout=30
            )

            # arXiv recommends 3 seconds between requests
            time.sleep(1)  # Be respectful, 1 second is enough for us

            response.raise_for_status()

            # Parse XML response
            papers = self._parse_arxiv_xml(response.text)

            # Filter by year if specified
            if year_min or year_max:
                papers = self._filter_by_year(papers, year_min, year_max)

            print(f"[ARXIV] Found {len(papers)} papers")

            return papers[:limit]

        except Exception as e:
            print(f"[ARXIV] ERROR: {type(e).__name__}: {str(e)}")
            return []

    def is_stem_relevant(self, keywords: List[str]) -> bool:
        """
        Check if keywords indicate STEM research (suitable for arXiv).

        Args:
            keywords: List of keywords from project

        Returns:
            True if keywords suggest STEM content
        """
        stem_indicators = {
            "machine learning", "deep learning", "neural network", "algorithm",
            "artificial intelligence", "computer science", "physics", "mathematics",
            "statistics", "optimization", "quantum", "data science", "nlp",
            "computer vision", "robotics", "signal processing", "encryption",
            "cryptography", "network", "computational", "statistical"
        }

        query_lower = " ".join(keywords).lower()

        for indicator in stem_indicators:
            if indicator in query_lower:
                return True

        return False

    def _parse_arxiv_xml(self, xml_text: str) -> List[Dict[str, Any]]:
        """
        Parse arXiv API XML response.

        Args:
            xml_text: XML response from arXiv API

        Returns:
            List of normalized paper dictionaries
        """
        papers = []

        try:
            # Parse XML
            root = ET.fromstring(xml_text)

            # arXiv uses Atom namespace
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            # Find all entry elements (papers)
            entries = root.findall("atom:entry", ns)

            for entry in entries:
                # Extract data from XML
                title_elem = entry.find("atom:title", ns)
                title = title_elem.text.strip().replace("\n", " ") if title_elem is not None else "Untitled"

                summary_elem = entry.find("atom:summary", ns)
                abstract = summary_elem.text.strip().replace("\n", " ") if summary_elem is not None else None

                # Extract authors
                authors = []
                author_elems = entry.findall("atom:author", ns)
                for author_elem in author_elems:
                    name_elem = author_elem.find("atom:name", ns)
                    if name_elem is not None:
                        authors.append(name_elem.text.strip())

                # Extract arXiv ID from id element
                id_elem = entry.find("atom:id", ns)
                arxiv_id = None
                paper_url = None
                if id_elem is not None:
                    paper_url = id_elem.text.strip()
                    # Extract ID from URL: http://arxiv.org/abs/2301.12345 -> 2301.12345
                    arxiv_id = paper_url.split("/abs/")[-1]

                # Extract publication date
                published_elem = entry.find("atom:published", ns)
                year = None
                if published_elem is not None:
                    try:
                        pub_date = datetime.fromisoformat(published_elem.text.strip().replace("Z", "+00:00"))
                        year = pub_date.year
                    except:
                        pass

                # Extract categories
                categories = []
                category_elems = entry.findall("atom:category", ns)
                for cat_elem in category_elems:
                    term = cat_elem.get("term")
                    if term:
                        categories.append(term)

                # PDF URL - always available on arXiv
                pdf_url = f"http://arxiv.org/pdf/{arxiv_id}" if arxiv_id else None

                # DOI if available
                doi = None
                doi_elem = entry.find("atom:doi", ns)
                if doi_elem is not None:
                    doi = doi_elem.text.strip()

                paper = {
                    "title": title,
                    "abstract": abstract,
                    "authors": authors,
                    "year": year,
                    "doi": doi,
                    "arxiv_id": arxiv_id,
                    "pubmed_id": None,
                    "semantic_scholar_id": None,
                    "source": "arxiv",
                    "paper_url": paper_url,
                    "pdf_url": pdf_url,
                    "citation_count": None,  # arXiv doesn't provide citation counts
                    "journal_name": "arXiv (preprint)",
                    "publication_type": "Preprint",
                    "fields_of_study": categories
                }

                papers.append(paper)

        except Exception as e:
            print(f"[ARXIV] XML parsing error: {type(e).__name__}: {str(e)}")

        return papers

    def _filter_by_year(
        self,
        papers: List[Dict[str, Any]],
        year_min: Optional[int],
        year_max: Optional[int]
    ) -> List[Dict[str, Any]]:
        """
        Filter papers by publication year.

        Args:
            papers: List of papers
            year_min: Minimum year (inclusive)
            year_max: Maximum year (inclusive)

        Returns:
            Filtered list of papers
        """
        filtered = []

        for paper in papers:
            year = paper.get("year")
            if year is None:
                continue

            if year_min and year < year_min:
                continue

            if year_max and year > year_max:
                continue

            filtered.append(paper)

        return filtered
