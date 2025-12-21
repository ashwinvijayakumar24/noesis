"""
Paper Recommendation Service

Aggregates paper recommendations from multiple sources:
- Semantic Scholar (primary)
- arXiv (for STEM preprints)
- PubMed (for biomedical)

Uses project insights, research questions, and themes to find relevant papers.
"""

import os
from typing import List, Dict, Any, Optional
from openai import OpenAI
from app.services.external_apis import SemanticScholarAPI, ArXivAPI, PubMedAPI
from datetime import datetime

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize API clients
semantic_scholar = SemanticScholarAPI()
arxiv = ArXivAPI()
pubmed = PubMedAPI()


def generate_paper_recommendations(
    project_data: Dict[str, Any],
    insights: Optional[Dict[str, Any]] = None,
    research_questions: Optional[List[Dict[str, Any]]] = None,
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Generate paper recommendations from multiple sources.

    Args:
        project_data: Project information (title, description, themes)
        insights: Optional project insights (gaps, themes, etc.)
        research_questions: Optional list of research questions
        limit: Maximum number of recommendations to return

    Returns:
        List of recommended papers with relevance scoring
    """
    print(f"[PAPER-REC] Generating recommendations for project: {project_data.get('title', 'Unknown')}")

    # Step 1: Extract keywords and topics
    keywords = _extract_keywords(project_data, insights, research_questions)
    print(f"[PAPER-REC] Extracted keywords: {keywords[:5]}...")

    # Step 2: Determine which APIs to query based on content
    use_arxiv = arxiv.is_stem_relevant(keywords)
    use_pubmed = pubmed.is_biomedical_relevant(keywords)

    print(f"[PAPER-REC] Query strategy: Semantic Scholar=True, arXiv={use_arxiv}, PubMed={use_pubmed}")

    # Step 3: Query all relevant APIs
    all_papers = []

    # Always query Semantic Scholar (primary source)
    for keyword_group in _create_keyword_groups(keywords, max_groups=3):
        query = " ".join(keyword_group)
        ss_papers = semantic_scholar.search_papers(
            query=query,
            limit=10,
            year_min=datetime.now().year - 5,  # Last 5 years
            min_citation_count=3  # At least somewhat cited
        )
        all_papers.extend(ss_papers)

    # Query arXiv if STEM-relevant
    if use_arxiv:
        for keyword_group in _create_keyword_groups(keywords, max_groups=2):
            query = " ".join(keyword_group)
            arxiv_papers = arxiv.search_papers(
                query=query,
                limit=10,
                year_min=datetime.now().year - 3  # More recent for preprints
            )
            all_papers.extend(arxiv_papers)

    # Query PubMed if biomedical
    if use_pubmed:
        for keyword_group in _create_keyword_groups(keywords, max_groups=2):
            query = " ".join(keyword_group)
            pubmed_papers = pubmed.search_papers(
                query=query,
                limit=10,
                year_min=datetime.now().year - 5
            )
            all_papers.extend(pubmed_papers)

    print(f"[PAPER-REC] Retrieved {len(all_papers)} papers from all sources")

    # Step 4: Deduplicate papers
    unique_papers = _deduplicate_papers(all_papers)
    print(f"[PAPER-REC] After deduplication: {len(unique_papers)} papers")

    # Step 5: Score and rank papers
    scored_papers = _score_papers(
        unique_papers,
        keywords=keywords,
        insights=insights,
        research_questions=research_questions
    )

    # Step 6: Sort by score and return top N
    scored_papers.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

    top_papers = scored_papers[:limit]
    print(f"[PAPER-REC] Returning top {len(top_papers)} recommendations")

    return top_papers


def _extract_keywords(
    project_data: Dict[str, Any],
    insights: Optional[Dict[str, Any]],
    research_questions: Optional[List[Dict[str, Any]]]
) -> List[str]:
    """
    Extract keywords from project data using various sources.

    Args:
        project_data: Project info
        insights: Project insights
        research_questions: Research questions

    Returns:
        List of keywords
    """
    keywords = []

    # From project title and description
    if project_data.get("title"):
        keywords.extend(project_data["title"].split())

    if project_data.get("description"):
        keywords.extend(project_data["description"].split())

    # From insights themes
    if insights and insights.get("common_themes"):
        for theme in insights["common_themes"][:5]:
            if theme.get("theme"):
                keywords.extend(theme["theme"].split())

    # From research gaps
    if insights and insights.get("research_gaps"):
        for gap in insights["research_gaps"][:3]:
            if gap.get("title"):
                keywords.extend(gap["title"].split())

    # From research questions
    if research_questions:
        for rq in research_questions[:3]:
            if rq.get("question"):
                keywords.extend(rq["question"].split())

    # Clean and deduplicate keywords
    keywords = [k.lower().strip('.,;:?!()[]{}') for k in keywords if len(k) > 3]
    keywords = list(dict.fromkeys(keywords))  # Remove duplicates while preserving order

    return keywords


def _create_keyword_groups(keywords: List[str], max_groups: int = 3) -> List[List[str]]:
    """
    Create groups of keywords for targeted searching.

    Args:
        keywords: List of all keywords
        max_groups: Maximum number of groups to create

    Returns:
        List of keyword groups
    """
    if len(keywords) <= 5:
        return [keywords]

    # Take top keywords and create groups
    groups = []
    group_size = 5

    for i in range(0, min(len(keywords), max_groups * group_size), group_size):
        group = keywords[i:i+group_size]
        if group:
            groups.append(group)

    return groups[:max_groups]


def _deduplicate_papers(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate papers based on DOI, title, or arXiv ID.

    Args:
        papers: List of papers

    Returns:
        Deduplicated list of papers
    """
    seen = set()
    unique_papers = []

    for paper in papers:
        # Create identifier
        doi = paper.get("doi")
        arxiv_id = paper.get("arxiv_id")
        title = paper.get("title", "").lower().strip()

        identifier = None

        if doi:
            identifier = f"doi:{doi}"
        elif arxiv_id:
            identifier = f"arxiv:{arxiv_id}"
        elif title:
            # Use normalized title as last resort
            identifier = f"title:{title}"

        if identifier and identifier not in seen:
            seen.add(identifier)
            unique_papers.append(paper)

    return unique_papers


def _score_papers(
    papers: List[Dict[str, Any]],
    keywords: List[str],
    insights: Optional[Dict[str, Any]],
    research_questions: Optional[List[Dict[str, Any]]]
) -> List[Dict[str, Any]]:
    """
    Score papers for relevance based on multiple factors.

    Args:
        papers: List of papers to score
        keywords: Project keywords
        insights: Project insights
        research_questions: Research questions

    Returns:
        Papers with relevance scores and reasons
    """
    scored_papers = []

    for paper in papers:
        score = 0.0
        reasons = []
        matched_keywords = []

        # Get paper text for matching
        paper_text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()

        # Factor 1: Keyword matching (0-40 points)
        keyword_matches = 0
        for keyword in keywords[:20]:  # Check top 20 keywords
            if keyword.lower() in paper_text:
                keyword_matches += 1
                if len(matched_keywords) < 5:
                    matched_keywords.append(keyword)

        keyword_score = min(40, keyword_matches * 4)
        score += keyword_score

        if keyword_matches > 0:
            reasons.append(f"Matches {keyword_matches} project keywords")

        # Factor 2: Citation count (0-30 points)
        citation_count = paper.get("citation_count") or 0
        if citation_count > 0:
            citation_score = min(30, citation_count / 10)
            score += citation_score
            if citation_count > 50:
                reasons.append(f"Highly cited ({citation_count} citations)")
            elif citation_count > 10:
                reasons.append(f"Well cited ({citation_count} citations)")

        # Factor 3: Recency (0-20 points)
        year = paper.get("year")
        if year:
            current_year = datetime.now().year
            years_ago = current_year - year
            if years_ago <= 2:
                recency_score = 20
                reasons.append("Very recent publication")
            elif years_ago <= 5:
                recency_score = 15 - years_ago
                reasons.append("Recent publication")
            else:
                recency_score = max(0, 10 - years_ago)
            score += recency_score

        # Factor 4: Has PDF (0-10 points)
        if paper.get("pdf_url"):
            score += 10
            reasons.append("PDF available")

        # Normalize score to 0-1
        normalized_score = min(1.0, score / 100.0)

        # Add scoring metadata to paper
        paper["relevance_score"] = round(normalized_score, 3)
        paper["relevance_reason"] = " • ".join(reasons) if reasons else "Relevant to project"
        paper["matched_keywords"] = matched_keywords[:5]

        # Identify which gaps this addresses (if insights available)
        if insights and insights.get("research_gaps"):
            addresses_gaps = []
            for gap in insights["research_gaps"][:3]:
                gap_title = gap.get("title", "").lower()
                if any(keyword in gap_title for keyword in matched_keywords):
                    addresses_gaps.append(gap.get("category", "unknown"))

            paper["addresses_gaps"] = addresses_gaps

        scored_papers.append(paper)

    return scored_papers
