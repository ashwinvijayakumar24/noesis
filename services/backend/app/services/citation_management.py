"""
Citation Management Service

Provides comprehensive citation management functionality:
- Citation extraction from draft text using regex and NLP
- Citation format parsing (APA, IEEE, MLA, Chicago)
- Citation formatting and generation
- Semantic search for relevant citation suggestions
- Citation scoring and ranking algorithms
- Citation validation and duplicate detection

Requirements: Phase 1 Tasks 2.1, 2.2, 2.3
"""

import json
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from app.core.config import settings
from app.core.supabase_client import supabase
from app.core.logging_config import get_logger
from app.core.openai_client import get_openai_client, get_completion_params

logger = get_logger(__name__)

# Initialize OpenAI client
client = get_openai_client()


# ============================================
# Citation Format Patterns
# ============================================

# Common citation format regex patterns
CITATION_PATTERNS = {
    # APA: (Author, Year) or Author (Year) or Author et al. (Year)
    'apa_parenthetical': r'\(([A-Z][a-z]+(?:\s+et\s+al\.)?)(?:,\s+|\s+)(\d{4}[a-z]?)\)',
    'apa_narrative': r'\b([A-Z][a-z]+(?:\s+et\s+al\.)?)\s+\((\d{4}[a-z]?)\)',

    # IEEE: [1], [2], etc.
    'ieee_numeric': r'\[(\d+)\]',

    # Multiple authors in parentheses: (Author1 & Author2, Year)
    'apa_multiple': r'\(([A-Z][a-z]+\s+&\s+[A-Z][a-z]+),\s+(\d{4}[a-z]?)\)',

    # MLA-style with page numbers: (Author 123)
    'mla_page': r'\(([A-Z][a-z]+(?:\s+et\s+al\.)?)\s+(\d+)\)',

    # Chicago footnote-style: ^1, ^2
    'chicago_footnote': r'\^(\d+)',
}


# ============================================
# Citation Extraction Functions
# ============================================

def extract_citations_from_draft(draft_text: str) -> List[Dict[str, Any]]:
    """
    Extract all citations from draft text using pattern matching.

    Identifies citations in multiple formats (APA, IEEE, MLA, Chicago) and
    extracts author, year, and context information.

    Args:
        draft_text: Full text of the research draft

    Returns:
        List of citation dictionaries with format, author, year, and context

    Requirements: Task 2.1 - Citation extraction using regex and NLP
    """
    citations = []
    seen_citations = set()  # Track duplicates

    try:
        # Extract APA parenthetical citations: (Author, Year)
        for match in re.finditer(CITATION_PATTERNS['apa_parenthetical'], draft_text):
            author = match.group(1).strip()
            year = match.group(2).strip()
            citation_string = f"({author}, {year})"

            if citation_string not in seen_citations:
                citations.append({
                    "format": "apa",
                    "type": "parenthetical",
                    "citation_string": citation_string,
                    "authors": [author.replace(" et al.", "")],
                    "year": year,
                    "position": match.start(),
                    "context": _get_context(draft_text, match.start(), match.end())
                })
                seen_citations.add(citation_string)

        # Extract APA narrative citations: Author (Year)
        for match in re.finditer(CITATION_PATTERNS['apa_narrative'], draft_text):
            author = match.group(1).strip()
            year = match.group(2).strip()
            citation_string = f"{author} ({year})"

            if citation_string not in seen_citations:
                citations.append({
                    "format": "apa",
                    "type": "narrative",
                    "citation_string": citation_string,
                    "authors": [author.replace(" et al.", "")],
                    "year": year,
                    "position": match.start(),
                    "context": _get_context(draft_text, match.start(), match.end())
                })
                seen_citations.add(citation_string)

        # Extract IEEE numeric citations: [1]
        for match in re.finditer(CITATION_PATTERNS['ieee_numeric'], draft_text):
            ref_num = match.group(1)
            citation_string = f"[{ref_num}]"

            if citation_string not in seen_citations:
                citations.append({
                    "format": "ieee",
                    "type": "numeric",
                    "citation_string": citation_string,
                    "reference_number": ref_num,
                    "position": match.start(),
                    "context": _get_context(draft_text, match.start(), match.end())
                })
                seen_citations.add(citation_string)

        # Extract multiple author citations: (Author1 & Author2, Year)
        for match in re.finditer(CITATION_PATTERNS['apa_multiple'], draft_text):
            authors_str = match.group(1).strip()
            year = match.group(2).strip()
            citation_string = f"({authors_str}, {year})"

            if citation_string not in seen_citations:
                authors_list = [a.strip() for a in authors_str.split('&')]
                citations.append({
                    "format": "apa",
                    "type": "parenthetical",
                    "citation_string": citation_string,
                    "authors": authors_list,
                    "year": year,
                    "position": match.start(),
                    "context": _get_context(draft_text, match.start(), match.end())
                })
                seen_citations.add(citation_string)

        logger.info(f"Extracted {len(citations)} unique citations from draft (found {len(seen_citations)} total)")

        # Sort by position in text
        citations.sort(key=lambda x: x.get('position', 0))

        return citations

    except Exception as e:
        logger.error(f"Citation extraction failed: {e}")
        return []


def _get_context(text: str, start: int, end: int, context_chars: int = 100) -> str:
    """
    Extract surrounding context for a citation.

    Args:
        text: Full text
        start: Start position of citation
        end: End position of citation
        context_chars: Number of characters to include before and after

    Returns:
        Context string with citation highlighted
    """
    context_start = max(0, start - context_chars)
    context_end = min(len(text), end + context_chars)

    before = text[context_start:start]
    citation = text[start:end]
    after = text[end:context_end]

    return f"{before}**{citation}**{after}"


def parse_citation_format(citation_string: str) -> Dict[str, Any]:
    """
    Identify the format of a citation string and extract components.

    Supports: APA, IEEE, MLA, Chicago formats

    Args:
        citation_string: Raw citation text

    Returns:
        Dictionary with format type and extracted components

    Requirements: Task 2.1 - Parse citation formats
    """
    citation_string = citation_string.strip()

    # Try APA parenthetical: (Author, Year)
    match = re.match(r'\(([A-Za-z\s&,]+),\s+(\d{4}[a-z]?)\)', citation_string)
    if match:
        return {
            "format": "apa",
            "type": "parenthetical",
            "authors": [a.strip() for a in match.group(1).split('&')],
            "year": match.group(2),
            "original": citation_string
        }

    # Try APA narrative: Author (Year)
    match = re.match(r'([A-Za-z\s]+(?:et\s+al\.)?)?\s*\((\d{4}[a-z]?)\)', citation_string)
    if match and match.group(1):
        return {
            "format": "apa",
            "type": "narrative",
            "authors": [match.group(1).strip().replace(" et al.", "")],
            "year": match.group(2),
            "original": citation_string
        }

    # Try IEEE numeric: [1]
    match = re.match(r'\[(\d+)\]', citation_string)
    if match:
        return {
            "format": "ieee",
            "type": "numeric",
            "reference_number": match.group(1),
            "original": citation_string
        }

    # Default: unrecognized format
    return {
        "format": "unknown",
        "type": "unknown",
        "original": citation_string
    }


# ============================================
# Citation Formatting Functions
# ============================================

def format_citation_apa(
    authors: List[str],
    year: str,
    title: str,
    journal: Optional[str] = None,
    volume: Optional[str] = None,
    issue: Optional[str] = None,
    pages: Optional[str] = None,
    doi: Optional[str] = None,
    url: Optional[str] = None
) -> str:
    """
    Generate APA format citation from paper metadata.

    Format: Author, A. A., & Author, B. B. (Year). Title. Journal, volume(issue), pages. https://doi.org/xxx

    Args:
        authors: List of author names
        year: Publication year
        title: Paper title
        journal: Journal name
        volume: Volume number
        issue: Issue number
        pages: Page range
        doi: Digital Object Identifier
        url: Paper URL if no DOI

    Returns:
        Formatted APA citation string

    Requirements: Task 2.3 - Citation formatting (APA)
    """
    citation_parts = []

    # Format authors
    if len(authors) == 1:
        author_str = authors[0]
    elif len(authors) == 2:
        author_str = f"{authors[0]} & {authors[1]}"
    elif len(authors) <= 20:
        author_str = ", ".join(authors[:-1]) + f", & {authors[-1]}"
    else:
        # 21+ authors: list first 19, then ..., then last author
        author_str = ", ".join(authors[:19]) + f", ... {authors[-1]}"

    citation_parts.append(f"{author_str} ({year}).")

    # Title (sentence case, italicized in actual formatting)
    citation_parts.append(f"{title}.")

    # Journal info
    if journal:
        journal_part = f"{journal}"
        if volume:
            journal_part += f", {volume}"
            if issue:
                journal_part += f"({issue})"
        if pages:
            journal_part += f", {pages}"
        journal_part += "."
        citation_parts.append(journal_part)

    # DOI or URL
    if doi:
        citation_parts.append(f"https://doi.org/{doi}")
    elif url:
        citation_parts.append(url)

    return " ".join(citation_parts)


def format_citation_ieee(
    authors: List[str],
    year: str,
    title: str,
    journal: Optional[str] = None,
    volume: Optional[str] = None,
    issue: Optional[str] = None,
    pages: Optional[str] = None,
    doi: Optional[str] = None
) -> str:
    """
    Generate IEEE format citation from paper metadata.

    Format: A. Author, B. Author, and C. Author, "Title," Journal, vol. X, no. Y, pp. Z, Year.

    Args:
        authors: List of author names
        year: Publication year
        title: Paper title
        journal: Journal name
        volume: Volume number
        issue: Issue number
        pages: Page range
        doi: Digital Object Identifier

    Returns:
        Formatted IEEE citation string

    Requirements: Task 2.3 - Citation formatting (IEEE)
    """
    citation_parts = []

    # Format authors (initials first)
    if len(authors) <= 6:
        if len(authors) == 1:
            author_str = authors[0]
        elif len(authors) == 2:
            author_str = f"{authors[0]} and {authors[1]}"
        else:
            author_str = ", ".join(authors[:-1]) + f", and {authors[-1]}"
    else:
        # 7+ authors: list first author et al.
        author_str = f"{authors[0]} et al."

    citation_parts.append(f"{author_str},")

    # Title in quotes
    citation_parts.append(f'"{title},"')

    # Journal info
    if journal:
        journal_part = f"{journal}"
        if volume:
            journal_part += f", vol. {volume}"
        if issue:
            journal_part += f", no. {issue}"
        if pages:
            journal_part += f", pp. {pages}"
        journal_part += f", {year}."
        citation_parts.append(journal_part)
    else:
        citation_parts.append(f"{year}.")

    # DOI
    if doi:
        citation_parts.append(f"doi: {doi}")

    return " ".join(citation_parts)


def format_citation_mla(
    authors: List[str],
    year: str,
    title: str,
    journal: Optional[str] = None,
    volume: Optional[str] = None,
    issue: Optional[str] = None,
    pages: Optional[str] = None,
    doi: Optional[str] = None,
    url: Optional[str] = None
) -> str:
    """
    Generate MLA format citation from paper metadata.

    Format: Author, First. "Title." Journal, vol. X, no. Y, Year, pp. Z. DOI or URL.

    Args:
        authors: List of author names
        year: Publication year
        title: Paper title
        journal: Journal name
        volume: Volume number
        issue: Issue number
        pages: Page range
        doi: Digital Object Identifier
        url: Paper URL

    Returns:
        Formatted MLA citation string

    Requirements: Task 2.3 - Citation formatting (MLA)
    """
    citation_parts = []

    # Format authors (Last, First)
    if len(authors) == 1:
        author_str = authors[0]
    elif len(authors) == 2:
        author_str = f"{authors[0]}, and {authors[1]}"
    else:
        author_str = f"{authors[0]}, et al."

    citation_parts.append(f"{author_str}.")

    # Title in quotes
    citation_parts.append(f'"{title}."')

    # Journal info
    if journal:
        journal_part = f"{journal}"
        if volume:
            journal_part += f", vol. {volume}"
        if issue:
            journal_part += f", no. {issue}"
        journal_part += f", {year}"
        if pages:
            journal_part += f", pp. {pages}"
        journal_part += "."
        citation_parts.append(journal_part)
    else:
        citation_parts.append(f"{year}.")

    # DOI or URL
    if doi:
        citation_parts.append(f"doi:{doi}.")
    elif url:
        citation_parts.append(f"{url}.")

    return " ".join(citation_parts)


def format_citation_chicago(
    authors: List[str],
    year: str,
    title: str,
    journal: Optional[str] = None,
    volume: Optional[str] = None,
    issue: Optional[str] = None,
    pages: Optional[str] = None,
    doi: Optional[str] = None
) -> str:
    """
    Generate Chicago format citation from paper metadata (author-date style).

    Format: Author, First. Year. "Title." Journal volume, no. issue (Year): pages.

    Args:
        authors: List of author names
        year: Publication year
        title: Paper title
        journal: Journal name
        volume: Volume number
        issue: Issue number
        pages: Page range
        doi: Digital Object Identifier

    Returns:
        Formatted Chicago citation string

    Requirements: Task 2.3 - Citation formatting (Chicago)
    """
    citation_parts = []

    # Format authors
    if len(authors) == 1:
        author_str = authors[0]
    elif len(authors) == 2:
        author_str = f"{authors[0]} and {authors[1]}"
    elif len(authors) <= 10:
        author_str = ", ".join(authors[:-1]) + f", and {authors[-1]}"
    else:
        # 11+ authors: list first 7, then et al.
        author_str = ", ".join(authors[:7]) + " et al."

    citation_parts.append(f"{author_str}. {year}.")

    # Title in quotes
    citation_parts.append(f'"{title}."')

    # Journal info
    if journal:
        journal_part = f"{journal}"
        if volume:
            journal_part += f" {volume}"
            if issue:
                journal_part += f", no. {issue}"
        if pages:
            journal_part += f" ({year}): {pages}"
        else:
            journal_part += f" ({year})"
        journal_part += "."
        citation_parts.append(journal_part)

    # DOI
    if doi:
        citation_parts.append(f"https://doi.org/{doi}.")

    return " ".join(citation_parts)


def generate_bibtex_cite_key(title: str, authors: List[str], year: str) -> str:
    """
    Generate a BibTeX citation key in the format: FirstAuthorLastName + Year + FirstTitleWord

    Examples:
    - Smith2023Deep
    - DoeJones2024Machine

    Args:
        title: Paper title
        authors: List of author names (format: "Last, First" or "First Last")
        year: Publication year

    Returns:
        BibTeX citation key
    """
    # Extract first author's last name
    if authors and len(authors) > 0:
        first_author = authors[0]
        # Handle "Last, First" format
        if ',' in first_author:
            last_name = first_author.split(',')[0].strip()
        else:
            # Handle "First Last" format
            parts = first_author.strip().split()
            last_name = parts[-1] if parts else "Unknown"

        # Remove non-alphanumeric characters
        last_name = ''.join(c for c in last_name if c.isalnum())
    else:
        last_name = "Unknown"

    # Extract first word from title
    title_words = title.split()
    first_title_word = ''.join(c for c in title_words[0] if c.isalnum()) if title_words else "Untitled"

    # Combine: LastName + Year + TitleWord
    cite_key = f"{last_name}{year}{first_title_word}"

    return cite_key


def format_citation_bibtex(
    title: str,
    authors: List[str],
    year: str,
    journal: Optional[str] = None,
    volume: Optional[str] = None,
    issue: Optional[str] = None,
    pages: Optional[str] = None,
    doi: Optional[str] = None,
    url: Optional[str] = None,
    booktitle: Optional[str] = None,
    publisher: Optional[str] = None,
    entry_type: str = "article"
) -> str:
    """
    Format citation in BibTeX format.

    Args:
        title: Paper title
        authors: List of author names
        year: Publication year
        journal: Journal name
        volume: Volume number
        issue: Issue number
        pages: Page range
        doi: Digital Object Identifier
        url: Paper URL
        booktitle: Book title (for conference proceedings)
        publisher: Publisher name
        entry_type: BibTeX entry type (article, inproceedings, book, etc.)

    Returns:
        BibTeX-formatted citation string

    Requirements: Export Features - BibTeX citation export
    """
    cite_key = generate_bibtex_cite_key(title, authors, year)

    # Format authors for BibTeX (separate with 'and')
    author_str = " and ".join(authors) if authors else "Unknown"

    # Build BibTeX entry
    bibtex_lines = [f"@{entry_type}{{{cite_key},"]

    # Required fields
    bibtex_lines.append(f'  title = {{{title}}},')
    bibtex_lines.append(f'  author = {{{author_str}}},')
    bibtex_lines.append(f'  year = {{{year}}},')

    # Optional fields (only include if present)
    if journal:
        bibtex_lines.append(f'  journal = {{{journal}}},')
    if booktitle:
        bibtex_lines.append(f'  booktitle = {{{booktitle}}},')
    if volume:
        bibtex_lines.append(f'  volume = {{{volume}}},')
    if issue:
        bibtex_lines.append(f'  number = {{{issue}}},')
    if pages:
        bibtex_lines.append(f'  pages = {{{pages}}},')
    if publisher:
        bibtex_lines.append(f'  publisher = {{{publisher}}},')
    if doi:
        bibtex_lines.append(f'  doi = {{{doi}}},')
    if url:
        bibtex_lines.append(f'  url = {{{url}}},')

    bibtex_lines.append("}")

    return "\n".join(bibtex_lines)


def format_citation_all_styles(
    title: str,
    authors: List[str],
    year: str,
    journal: Optional[str] = None,
    volume: Optional[str] = None,
    issue: Optional[str] = None,
    pages: Optional[str] = None,
    doi: Optional[str] = None,
    url: Optional[str] = None
) -> Dict[str, str]:
    """
    Generate citations in all supported formats.

    Args:
        title: Paper title
        authors: List of author names
        year: Publication year
        journal: Journal name
        volume: Volume number
        issue: Issue number
        pages: Page range
        doi: Digital Object Identifier
        url: Paper URL

    Returns:
        Dictionary with citations in APA, IEEE, MLA, Chicago, and BibTeX formats

    Requirements: Task 2.3 - Multiple citation styles, Export Features - BibTeX support
    """
    return {
        "apa": format_citation_apa(authors, year, title, journal, volume, issue, pages, doi, url),
        "ieee": format_citation_ieee(authors, year, title, journal, volume, issue, pages, doi),
        "mla": format_citation_mla(authors, year, title, journal, volume, issue, pages, doi, url),
        "chicago": format_citation_chicago(authors, year, title, journal, volume, issue, pages, doi),
        "bibtex": format_citation_bibtex(title, authors, year, journal, volume, issue, pages, doi, url)
    }


# ============================================
# Citation Suggestion Functions
# ============================================

async def generate_citation_suggestions(
    claim_text: str,
    project_id: str,
    draft_id: str,
    existing_citations: List[str] = [],
    max_suggestions: int = 5
) -> List[Dict[str, Any]]:
    """
    Generate AI-powered citation suggestions for a claim using semantic search.

    Searches the project's literature database for relevant papers and scores
    them by relevance, recency, and impact factor.

    Args:
        claim_text: Text of the claim needing citation support
        project_id: Project ID to search within
        draft_id: Draft ID for tracking suggestions
        existing_citations: Citations already present for this claim
        max_suggestions: Maximum number of suggestions to return

    Returns:
        List of citation suggestions with relevance scores and reasoning

    Requirements: Task 2.2 - AI-powered citation suggestions with semantic search
    """
    suggestions = []

    try:
        if not client:
            raise ValueError("OpenAI API key not configured")

        logger.info(f"Generating citation suggestions for claim: {claim_text[:100]}...")

        # 1. Embed the claim text for semantic search
        from app.services.rag_ingest import embed_chunks

        embeddings = embed_chunks([claim_text])
        if not embeddings:
            logger.warning("Failed to generate embedding for claim")
            return suggestions

        claim_embedding = embeddings[0].embedding

        # 2. Check if project has documents with embeddings
        docs_check = supabase.table("documents").select("id").eq("project_id", project_id).limit(1).execute()
        logger.info(f"Project {project_id} has {len(docs_check.data) if docs_check.data else 0} documents")
        
        chunks_check = supabase.table("document_chunks").select("id").eq("project_id", project_id).limit(1).execute()
        logger.info(f"Project {project_id} has {len(chunks_check.data) if chunks_check.data else 0} document chunks with embeddings")
        
        if not chunks_check.data:
            logger.warning(f"No document chunks with embeddings found for project {project_id}. Documents may need to be processed/ingested first.")
            return suggestions

        # 3. Semantic search in project documents
        logger.info(f"Searching for similar document chunks with match_count={max_suggestions * 2}")
        try:
            search_results = supabase.rpc(
                "match_document_chunks",
                {
                    "query_embedding": claim_embedding,
                    "proj_id": project_id,  # Fixed: parameter name is proj_id, not p_project_id
                    "match_count": max_suggestions * 2  # Get more for filtering
                }
            ).execute()
            
            logger.info(f"Search returned {len(search_results.data) if search_results.data else 0} results")
        except Exception as e:
            logger.error(f"Error calling match_document_chunks RPC: {e}")
            return suggestions

        if not search_results.data:
            logger.info("No relevant documents found for citation suggestion")
            return suggestions

        # 4. Get unique documents and their metadata
        document_ids = []
        doc_similarities = {}

        for result in search_results.data:
            doc_id = result["document_id"]
            similarity = result.get("similarity", 0.0)

            if doc_id not in document_ids:
                document_ids.append(doc_id)
                doc_similarities[doc_id] = similarity

        # 5. Fetch document details and metadata
        for doc_id in document_ids[:max_suggestions]:
            doc_response = supabase.table("documents").select("*").eq("id", doc_id).single().execute()

            if not doc_response.data:
                continue

            document = doc_response.data
            analysis = document.get("analysis", {}) or {}

            # Extract paper metadata
            citation_metadata = analysis.get("citation_metadata", {}) or {}

            title = document.get("title", "Untitled")
            authors = citation_metadata.get("all_authors", []) or ["Unknown Author"]
            year = citation_metadata.get("year", "n.d.")

            # Calculate relevance score (0-1)
            relevance_score = float(doc_similarities.get(doc_id, 0.0))

            # Calculate recency bonus (papers from last 5 years get bonus)
            recency_bonus = 0.0
            try:
                if year and year != "n.d.":
                    year_int = int(str(year)[:4])
                    current_year = datetime.now().year
                    years_old = current_year - year_int

                    if years_old <= 5:
                        recency_bonus = 0.1 * (5 - years_old) / 5  # Up to +0.1 for this year
            except:
                pass

            # Calculate confidence score (relevance + recency)
            confidence_score = min(1.0, relevance_score + recency_bonus)

            # Determine suggestion type
            suggestion_type = _determine_suggestion_type(
                claim_text,
                existing_citations,
                year,
                confidence_score
            )

            # Generate reasoning using AI
            reasoning = _generate_suggestion_reasoning(
                claim_text,
                title,
                authors,
                year,
                analysis.get("executive_summary", ""),
                suggestion_type
            )

            # Determine impact level
            impact_level = _calculate_impact_level(confidence_score, suggestion_type)

            # Format suggested paper metadata
            suggested_paper = {
                "document_id": doc_id,
                "title": title,
                "authors": authors,
                "year": year,
                "doi": citation_metadata.get("doi"),
                "abstract": analysis.get("executive_summary", ""),
                "relevance_excerpt": _extract_relevant_excerpt(claim_text, search_results.data, doc_id)
            }

            suggestion = {
                "suggested_paper": suggested_paper,
                "suggestion_type": suggestion_type,
                "confidence_score": round(confidence_score, 3),
                "relevance_score": round(relevance_score, 3),
                "reasoning": reasoning,
                "impact_level": impact_level,
                "priority_score": _calculate_priority_score(confidence_score, suggestion_type, impact_level)
            }

            suggestions.append(suggestion)

        # 6. Sort by priority score (highest first)
        suggestions.sort(key=lambda x: x["priority_score"], reverse=True)

        logger.info(f"Generated {len(suggestions)} citation suggestions")

        return suggestions[:max_suggestions]

    except Exception as e:
        logger.error(f"Citation suggestion generation failed: {e}")
        return []


def _determine_suggestion_type(
    claim_text: str,
    existing_citations: List[str],
    paper_year: str,
    relevance_score: float
) -> str:
    """Determine the type of citation suggestion."""
    if not existing_citations or len(existing_citations) == 0:
        return "missing_citation"
    elif len(existing_citations) == 1 and relevance_score > 0.8:
        return "alternative_source"

    # Check if paper is recent (last 5 years)
    try:
        if paper_year and paper_year != "n.d.":
            year_int = int(str(paper_year)[:4])
            if datetime.now().year - year_int <= 5:
                return "recent_work"
    except:
        pass

    # Check if paper is foundational (older but highly relevant)
    try:
        if paper_year and paper_year != "n.d.":
            year_int = int(str(paper_year)[:4])
            if datetime.now().year - year_int > 10 and relevance_score > 0.7:
                return "foundational_work"
    except:
        pass

    return "alternative_source"


def _generate_suggestion_reasoning(
    claim_text: str,
    paper_title: str,
    authors: List[str],
    year: str,
    summary: str,
    suggestion_type: str
) -> str:
    """Generate human-readable reasoning for why a paper is suggested."""
    author_str = authors[0] if authors else "Unknown"
    if len(authors) > 1:
        author_str += " et al."

    if suggestion_type == "missing_citation":
        return f"{author_str} ({year}) directly addresses this claim in '{paper_title}'. This paper provides strong supporting evidence that should be cited."
    elif suggestion_type == "recent_work":
        return f"Recent work by {author_str} ({year}) provides updated findings relevant to this claim. Citing recent literature strengthens your argument."
    elif suggestion_type == "foundational_work":
        return f"{author_str} ({year}) is a foundational paper in this area. Citing this seminal work demonstrates awareness of the field's development."
    elif suggestion_type == "alternative_source":
        return f"{author_str} ({year}) offers an alternative perspective on this claim. Adding this citation diversifies your sources and strengthens support."
    else:
        return f"{author_str} ({year}) is highly relevant to this claim based on semantic similarity and content analysis."


def _calculate_impact_level(confidence_score: float, suggestion_type: str) -> str:
    """Calculate the impact level of adding this citation."""
    if suggestion_type == "missing_citation":
        return "critical" if confidence_score > 0.7 else "high"
    elif suggestion_type == "recent_work" and confidence_score > 0.8:
        return "high"
    elif suggestion_type == "foundational_work" and confidence_score > 0.75:
        return "high"
    elif confidence_score > 0.8:
        return "high"
    elif confidence_score > 0.6:
        return "medium"
    else:
        return "low"


def _calculate_priority_score(
    confidence_score: float,
    suggestion_type: str,
    impact_level: str
) -> float:
    """Calculate overall priority score for ranking suggestions."""
    # Base score from confidence
    score = confidence_score

    # Bonus for suggestion type
    type_bonus = {
        "missing_citation": 0.3,
        "recent_work": 0.15,
        "foundational_work": 0.1,
        "alternative_source": 0.05,
        "weak_citation": 0.2
    }
    score += type_bonus.get(suggestion_type, 0.0)

    # Bonus for impact level
    impact_bonus = {
        "critical": 0.2,
        "high": 0.1,
        "medium": 0.05,
        "low": 0.0
    }
    score += impact_bonus.get(impact_level, 0.0)

    return min(1.0, score)


def _extract_relevant_excerpt(
    claim_text: str,
    search_results: List[Dict[str, Any]],
    document_id: str,
    max_length: int = 300
) -> str:
    """Extract the most relevant excerpt from document chunks."""
    for result in search_results:
        if result.get("document_id") == document_id:
            content = result.get("content", "")
            if len(content) <= max_length:
                return content
            else:
                return content[:max_length] + "..."

    return ""


# ============================================
# Citation Validation Functions
# ============================================

def validate_citation_format(citation_string: str, expected_format: str = "apa") -> Dict[str, Any]:
    """
    Validate a citation string against a specific format.

    Args:
        citation_string: Citation to validate
        expected_format: Expected format (apa, ieee, mla, chicago)

    Returns:
        Validation result with is_valid flag and error messages

    Requirements: Task 2.3 - Citation validation
    """
    result = {
        "is_valid": False,
        "format": expected_format,
        "errors": [],
        "warnings": []
    }

    parsed = parse_citation_format(citation_string)

    if parsed["format"] == "unknown":
        result["errors"].append("Citation format not recognized")
        return result

    if parsed["format"] != expected_format and expected_format != "any":
        result["warnings"].append(f"Citation appears to be {parsed['format']} format, expected {expected_format}")

    # Check for required components
    if expected_format == "apa":
        if not parsed.get("authors"):
            result["errors"].append("Missing author information")
        if not parsed.get("year"):
            result["errors"].append("Missing year")

    elif expected_format == "ieee":
        if parsed.get("type") != "numeric":
            result["errors"].append("IEEE citations should be numeric [1], [2], etc.")

    # If no errors, mark as valid
    if not result["errors"]:
        result["is_valid"] = True

    return result


def detect_duplicate_citations(citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Detect duplicate citations in a list.

    Args:
        citations: List of citation dictionaries

    Returns:
        List of duplicate groups with suggestions for consolidation

    Requirements: Task 2.3 - Duplicate detection
    """
    duplicates = []
    seen = {}

    for i, citation in enumerate(citations):
        # Create a normalized key (author + year)
        authors = citation.get("authors", [])
        year = citation.get("year", "")

        if authors and year:
            key = f"{authors[0]}_{year}".lower().replace(" ", "")

            if key in seen:
                duplicates.append({
                    "original_index": seen[key],
                    "duplicate_index": i,
                    "original": citations[seen[key]],
                    "duplicate": citation,
                    "recommendation": "Consolidate these citations - they appear to reference the same work"
                })
            else:
                seen[key] = i

    return duplicates


# ============================================
# BibTeX Import Parser
# ============================================

def parse_bibtex_file(bibtex_content: str) -> List[Dict[str, Any]]:
    """
    Parse a BibTeX file and extract paper metadata.

    Handles:
    - Nested braces in field values
    - Quote-delimited and bare values
    - Multiple authors (separated by 'and')
    - Common entry types: article, inproceedings, book, misc, etc.

    Returns:
        List of dicts with keys: entry_type, bibtex_key, title, authors,
        year, abstract, doi, url, journal, booktitle, volume, pages, publisher
    """
    entries = []
    i = 0
    n = len(bibtex_content)

    while i < n:
        # Find @ symbol marking an entry
        at_pos = bibtex_content.find('@', i)
        if at_pos == -1:
            break

        i = at_pos + 1

        # Read entry type (letters only)
        entry_type_start = i
        while i < n and bibtex_content[i].isalpha():
            i += 1
        entry_type = bibtex_content[entry_type_start:i].lower()

        # Skip non-content entry types
        if entry_type in ('comment', 'string', 'preamble') or not entry_type:
            continue

        # Skip whitespace
        while i < n and bibtex_content[i].isspace():
            i += 1

        # Expect opening brace or paren
        if i >= n or bibtex_content[i] not in ('{', '('):
            continue

        close_char = '}' if bibtex_content[i] == '(' else '}'
        i += 1

        # Skip whitespace before cite key
        while i < n and bibtex_content[i].isspace():
            i += 1

        # Read cite key (up to comma or whitespace)
        cite_key_start = i
        while i < n and bibtex_content[i] not in (',', ' ', '\t', '\n', close_char):
            i += 1
        cite_key = bibtex_content[cite_key_start:i]

        # Skip to first comma (end of cite key line)
        while i < n and bibtex_content[i] != ',' and bibtex_content[i] != close_char:
            i += 1

        if i >= n:
            break

        if bibtex_content[i] == close_char:
            # Empty entry
            i += 1
            entries.append({
                'entry_type': entry_type, 'bibtex_key': cite_key,
                'title': 'Untitled', 'authors': [], 'year': '',
                'abstract': '', 'doi': '', 'url': '', 'journal': '',
                'booktitle': '', 'volume': '', 'pages': '', 'publisher': '',
            })
            continue

        i += 1  # skip comma after cite key

        # Parse fields
        fields: Dict[str, str] = {}
        while i < n:
            # Skip whitespace
            while i < n and bibtex_content[i].isspace():
                i += 1

            # End of entry?
            if i >= n or bibtex_content[i] == close_char:
                if i < n:
                    i += 1
                break

            # Read field name (alphanumeric + underscore)
            field_name_start = i
            while i < n and (bibtex_content[i].isalnum() or bibtex_content[i] == '_' or bibtex_content[i] == '-'):
                i += 1
            field_name = bibtex_content[field_name_start:i].lower()

            if not field_name:
                i += 1
                continue

            # Skip whitespace before =
            while i < n and bibtex_content[i].isspace():
                i += 1

            # Expect =
            if i >= n or bibtex_content[i] != '=':
                continue
            i += 1

            # Skip whitespace after =
            while i < n and bibtex_content[i].isspace():
                i += 1

            # Read field value
            field_value = ''
            if i < n and bibtex_content[i] == '{':
                # Brace-delimited: handle nested braces
                i += 1
                depth = 1
                value_chars = []
                while i < n and depth > 0:
                    c = bibtex_content[i]
                    if c == '{':
                        depth += 1
                        value_chars.append(c)
                    elif c == '}':
                        depth -= 1
                        if depth > 0:
                            value_chars.append(c)
                    else:
                        value_chars.append(c)
                    i += 1
                field_value = ''.join(value_chars)
            elif i < n and bibtex_content[i] == '"':
                # Quote-delimited
                i += 1
                value_chars = []
                while i < n and bibtex_content[i] != '"':
                    if bibtex_content[i] == '\\' and i + 1 < n:
                        i += 1
                        value_chars.append(bibtex_content[i])
                    else:
                        value_chars.append(bibtex_content[i])
                    i += 1
                if i < n:
                    i += 1  # skip closing "
                field_value = ''.join(value_chars)
            else:
                # Bare value (number, macro)
                value_chars = []
                while i < n and bibtex_content[i] not in (',', '}', ')') and bibtex_content[i] != '\n':
                    value_chars.append(bibtex_content[i])
                    i += 1
                field_value = ''.join(value_chars).strip()

            # Normalize whitespace
            import re as _re
            field_value = _re.sub(r'\s+', ' ', field_value).strip()

            if field_name:
                fields[field_name] = field_value

            # Skip whitespace, then optional comma
            while i < n and bibtex_content[i].isspace():
                i += 1
            if i < n and bibtex_content[i] == ',':
                i += 1

        # Parse authors list
        raw_authors = fields.get('author', '')
        if raw_authors:
            import re as _re2
            author_parts = _re2.split(r'\s+and\s+', raw_authors, flags=_re2.IGNORECASE)
            authors = [a.strip() for a in author_parts if a.strip()]
        else:
            authors = []

        entries.append({
            'entry_type': entry_type,
            'bibtex_key': cite_key,
            'title': fields.get('title', 'Untitled').strip(),
            'authors': authors,
            'year': fields.get('year', '').strip(),
            'abstract': fields.get('abstract', '').strip(),
            'doi': fields.get('doi', '').strip(),
            'url': (fields.get('url', '') or fields.get('link', '')).strip(),
            'journal': (fields.get('journal', '') or fields.get('journaltitle', '')).strip(),
            'booktitle': fields.get('booktitle', '').strip(),
            'volume': fields.get('volume', '').strip(),
            'pages': fields.get('pages', '').strip(),
            'publisher': fields.get('publisher', '').strip(),
        })

    return entries
