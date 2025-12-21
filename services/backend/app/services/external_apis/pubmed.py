"""
PubMed API Client

Provides interface to PubMed's free biomedical literature database (E-utilities).
Docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/
"""

import requests
import time
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Biomedical keywords that indicate PubMed relevance
BIOMEDICAL_KEYWORDS = {
    "medicine", "clinical", "patient", "disease", "treatment", "drug",
    "therapy", "diagnosis", "medical", "health", "healthcare", "hospital",
    "surgery", "cancer", "diabetes", "covid", "virus", "bacteria",
    "gene", "protein", "cell", "biology", "biomedical", "pharmaceutical",
    "epidemiology", "public health", "mental health", "psychiatry"
}


class PubMedAPI:
    """Client for PubMed E-utilities API"""

    def __init__(self, api_key: Optional[str] = None, email: Optional[str] = None):
        """
        Initialize PubMed API client.

        Args:
            api_key: Optional NCBI API key for higher rate limits (10 req/sec vs 3 req/sec)
            email: Email for NCBI (recommended but not required)
        """
        self.api_key = api_key
        self.email = email or "noreply@noesis.app"

    def search_papers(
        self,
        query: str,
        limit: int = 10,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for papers in PubMed.

        Args:
            query: Search query (keywords)
            limit: Maximum number of results
            year_min: Minimum publication year
            year_max: Maximum publication year

        Returns:
            List of paper dictionaries
        """
        print(f"[PUBMED] Searching for: {query[:50]}...")

        try:
            # Step 1: Search to get PMIDs
            pmids = self._search_pmids(query, limit, year_min, year_max)

            if not pmids:
                print("[PUBMED] No results found")
                return []

            # Step 2: Fetch paper details for PMIDs
            papers = self._fetch_paper_details(pmids)

            print(f"[PUBMED] Found {len(papers)} papers")

            return papers

        except Exception as e:
            print(f"[PUBMED] ERROR: {type(e).__name__}: {str(e)}")
            return []

    def is_biomedical_relevant(self, keywords: List[str]) -> bool:
        """
        Check if keywords indicate biomedical research (suitable for PubMed).

        Args:
            keywords: List of keywords from project

        Returns:
            True if keywords suggest biomedical content
        """
        query_lower = " ".join(keywords).lower()

        for keyword in BIOMEDICAL_KEYWORDS:
            if keyword in query_lower:
                return True

        return False

    def _search_pmids(
        self,
        query: str,
        limit: int,
        year_min: Optional[int],
        year_max: Optional[int]
    ) -> List[str]:
        """
        Search PubMed and return list of PMIDs.

        Args:
            query: Search query
            limit: Max results
            year_min: Min year
            year_max: Max year

        Returns:
            List of PubMed IDs
        """
        # Build query with date filter
        search_term = query
        if year_min and year_max:
            search_term += f" AND {year_min}:{year_max}[PDAT]"
        elif year_min:
            search_term += f" AND {year_min}:3000[PDAT]"
        elif year_max:
            search_term += f" AND 1900:{year_max}[PDAT]"

        params = {
            "db": "pubmed",
            "term": search_term,
            "retmax": limit,
            "retmode": "xml",
            "sort": "relevance",
            "email": self.email
        }

        if self.api_key:
            params["api_key"] = self.api_key

        response = requests.get(
            f"{EUTILS_BASE}/esearch.fcgi",
            params=params,
            timeout=30
        )

        # Rate limiting: 3 req/sec without key, 10 req/sec with key
        time.sleep(0.35 if self.api_key else 1.0)

        response.raise_for_status()

        # Parse XML to extract PMIDs
        root = ET.fromstring(response.text)
        pmids = [id_elem.text for id_elem in root.findall(".//Id")]

        return pmids

    def _fetch_paper_details(self, pmids: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch paper details for list of PMIDs.

        Args:
            pmids: List of PubMed IDs

        Returns:
            List of normalized paper dictionaries
        """
        if not pmids:
            return []

        # Fetch up to 200 papers at once
        pmid_str = ",".join(pmids[:200])

        params = {
            "db": "pubmed",
            "id": pmid_str,
            "retmode": "xml",
            "email": self.email
        }

        if self.api_key:
            params["api_key"] = self.api_key

        response = requests.get(
            f"{EUTILS_BASE}/efetch.fcgi",
            params=params,
            timeout=30
        )

        time.sleep(0.35 if self.api_key else 1.0)

        response.raise_for_status()

        # Parse XML response
        return self._parse_pubmed_xml(response.text)

    def _parse_pubmed_xml(self, xml_text: str) -> List[Dict[str, Any]]:
        """
        Parse PubMed fetch XML response.

        Args:
            xml_text: XML response from PubMed

        Returns:
            List of normalized paper dictionaries
        """
        papers = []

        try:
            root = ET.fromstring(xml_text)

            # Find all PubmedArticle elements
            articles = root.findall(".//PubmedArticle")

            for article in articles:
                # Extract PMID
                pmid_elem = article.find(".//PMID")
                pmid = pmid_elem.text if pmid_elem is not None else None

                # Extract title
                title_elem = article.find(".//ArticleTitle")
                title = title_elem.text if title_elem is not None else "Untitled"

                # Extract abstract
                abstract_parts = article.findall(".//AbstractText")
                abstract = " ".join([elem.text for elem in abstract_parts if elem.text]) if abstract_parts else None

                # Extract authors
                authors = []
                author_elems = article.findall(".//Author")
                for author in author_elems:
                    last_name = author.find("LastName")
                    fore_name = author.find("ForeName")
                    if last_name is not None:
                        name = last_name.text
                        if fore_name is not None:
                            name = f"{fore_name.text} {name}"
                        authors.append(name)

                # Extract year
                year = None
                year_elem = article.find(".//PubDate/Year")
                if year_elem is not None:
                    try:
                        year = int(year_elem.text)
                    except:
                        pass

                # Extract journal
                journal = None
                journal_elem = article.find(".//Journal/Title")
                if journal_elem is not None:
                    journal = journal_elem.text

                # Extract DOI
                doi = None
                article_ids = article.findall(".//ArticleId")
                for aid in article_ids:
                    if aid.get("IdType") == "doi":
                        doi = aid.text
                        break

                # Build URL
                paper_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None

                paper = {
                    "title": title,
                    "abstract": abstract,
                    "authors": authors,
                    "year": year,
                    "doi": doi,
                    "arxiv_id": None,
                    "pubmed_id": pmid,
                    "semantic_scholar_id": None,
                    "source": "pubmed",
                    "paper_url": paper_url,
                    "pdf_url": None,  # PubMed doesn't directly provide PDFs
                    "citation_count": None,  # PubMed doesn't provide citation counts
                    "journal_name": journal,
                    "publication_type": "Journal Article",
                    "fields_of_study": ["Biomedical"]
                }

                papers.append(paper)

        except Exception as e:
            print(f"[PUBMED] XML parsing error: {type(e).__name__}: {str(e)}")

        return papers
