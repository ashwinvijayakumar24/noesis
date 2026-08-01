"""
Adaptive chunking utility for RAG optimization.

This module provides intelligent chunking strategies based on document characteristics
to optimize retrieval quality while controlling costs.

Key Features:
- Adaptive chunk sizing based on document page count
- Cost ceiling protection (max chunks per document)
- Optimized overlap ratios for different document lengths
- Section-aware chunking that preserves document structure
"""

from typing import Dict, Tuple, List, Any
import logging
import os
import threading

import pysbd
import tiktoken

logger = logging.getLogger(__name__)


# ============================================
# TOKENISATION
# ============================================

# tiktoken's `encode()` defaults to ``disallowed_special="all"``, which RAISES
# ValueError when the input contains any special-token *string* such as
# "<|endoftext|>" or "<|im_start|>". That default exists to stop text of unknown
# provenance from being silently promoted into real control tokens on a
# *generation* path, where a smuggled <|im_start|> could forge a role boundary.
#
# Every call here is a COUNTING/SPLITTING operation used to size chunks; the
# resulting token ids are decoded straight back to text or just measured, and
# are never handed to a completion endpoint as ids. So the injection concern the
# default guards against does not arise, while the default's failure mode does:
# a real published paper about prompt injection (greshake et al. 2023) quotes
# "<|endoftext|>" in its body, and ingestion of that PDF crashed outright.
#
# Choice: ``disallowed_special=()`` rather than an explicit ``allowed_special``
# set. They differ in what the text BECOMES:
#   - allowed_special={"<|endoftext|>"}  -> the literal string is encoded AS the
#     special token id. That is the option that actually creates control tokens
#     out of document text, and it also distorts the count (13 characters ->
#     1 token) and would let a crafted PDF inject a control token into anything
#     downstream that reuses the ids.
#   - disallowed_special=()              -> nothing is forbidden and nothing is
#     promoted; ``allowed_special`` stays empty, so "<|endoftext|>" is encoded
#     as ordinary bytes and decodes back to exactly the same characters.
# The second is both the safer and the more faithful one: the paper's text is
# text, and chunking must preserve it verbatim. Normal text is unaffected --
# the parameter only governs the special-string case.
_DISALLOWED_SPECIAL: tuple = ()


def count_and_encode(enc: "tiktoken.Encoding", text: str) -> List[int]:
    """Encode ``text`` for chunk sizing, tolerating literal special-token strings."""
    return enc.encode(text, disallowed_special=_DISALLOWED_SPECIAL)


# ============================================
# SENTENCE SEGMENTATION
# ============================================

# `pysbd.Segmenter` is NOT thread-safe: `segment()` stashes the input on
# `self.original_text` and later reads it back, so two threads sharing one
# instance can splice each other's documents. Constructing a Segmenter is also
# not free (it compiles the language module), so we keep exactly one instance
# per thread rather than one per call.
_segmenter_local = threading.local()


def _get_segmenter() -> "pysbd.Segmenter":
    segmenter = getattr(_segmenter_local, "segmenter", None)
    if segmenter is None:
        segmenter = pysbd.Segmenter(language="en", clean=False)
        _segmenter_local.segmenter = segmenter
    return segmenter


def _legacy_split_sentences(content: str) -> List[str]:
    """The original naive splitter, kept as a measurable experiment arm.

    It shatters on academic abbreviations -- `et al.`, `Fig. 3`, `p. 12`,
    `p < 0.05.` -- fragmenting chunks mid-citation. Selected with
    CHUNKING_SPLITTER=legacy so the retrieval-recall cost of that behaviour can
    be quantified against the pysbd arm. Do not delete.
    """
    return content.replace('! ', '!|').replace('? ', '?|').replace('. ', '.|').split('|')


def split_sentences(content: str) -> List[str]:
    """Split text into sentences.

    CHUNKING_SPLITTER=pysbd (default) uses real sentence boundary detection;
    CHUNKING_SPLITTER=legacy restores the naive punctuation split.

    Returns stripped, non-empty segments -- the shape every caller already
    expects from the old expression.
    """
    if not content or not content.strip():
        return []

    mode = os.getenv("CHUNKING_SPLITTER", "pysbd").strip().lower() or "pysbd"
    if mode == "legacy":
        raw = _legacy_split_sentences(content)
    else:
        if mode != "pysbd":
            logger.warning(
                "Unknown CHUNKING_SPLITTER=%r; falling back to pysbd", mode
            )
        raw = _get_segmenter().segment(content)

    return [s.strip() for s in raw if s and s.strip()]

# Cost control: Maximum chunks allowed per document
MAX_CHUNKS_PER_DOCUMENT = 50

# Which geometry `apply_cost_ceiling` uses to pick the enlarged chunk size.
#
#   legacy (DEFAULT) -- the shipped formula. It overshoots: measured on the eval
#     corpus it exceeds its own ceiling on 16 of 16 documents where it fires
#     (n=344 unique documents), by up to 6 estimated chunks.
#   exact            -- solves the same problem with the overlap it will actually
#     use, so the produced count is <= max_chunks.
#
# The default stays `legacy` on purpose. Every retrieval number in
# docs/BENCHMARKS.md, and the 5,948 chunks currently in the eval database, were
# produced by it; silently swapping the geometry would change the corpus under
# measurements that have already been taken and make the old ones unreproducible.
# It is an arm, selected per run, not a bug awaiting deletion.
CEILING_GEOMETRY_ENV = "CHUNK_CEILING_GEOMETRY"
_CEILING_GEOMETRY_DEFAULT = "legacy"


def _ceiling_geometry() -> str:
    """Read the arm from the environment, defaulting to the shipped behaviour."""
    mode = os.getenv(CEILING_GEOMETRY_ENV, "").strip().lower() or _CEILING_GEOMETRY_DEFAULT
    if mode not in ("legacy", "exact"):
        logger.warning(
            "Unknown %s=%r; falling back to %s",
            CEILING_GEOMETRY_ENV,
            mode,
            _CEILING_GEOMETRY_DEFAULT,
        )
        return _CEILING_GEOMETRY_DEFAULT
    return mode

# Adaptive chunking tiers based on page count
CHUNKING_TIERS = {
    "SHORT": {
        "page_range": (1, 10),
        "chunk_size": 1200,
        "overlap": 200,
        "description": "Short papers (1-10 pages) - smaller chunks for precision"
    },
    "MEDIUM": {
        "page_range": (11, 30),
        "chunk_size": 1600,
        "overlap": 250,
        "description": "Medium papers (11-30 pages) - balanced chunks"
    },
    "LONG": {
        "page_range": (31, float('inf')),
        "chunk_size": 2000,
        "overlap": 300,
        "description": "Long papers (31+ pages) - larger chunks for context"
    }
}


def get_optimal_chunk_params(
    page_count: int,
    doc_type: str = "paper"
) -> Dict[str, int]:
    """
    Return optimal chunk_size, overlap, and chunks_per_query based on document characteristics.

    This function implements adaptive chunking strategy where chunk size increases
    with document length to maintain good context while controlling costs.

    Args:
        page_count: Number of pages in the document
        doc_type: Type of document (currently only "paper" is supported)

    Returns:
        Dict containing:
            - chunk_size: Optimal chunk size in tokens
            - overlap: Overlap between chunks in tokens
            - tier: The tier name (SHORT, MEDIUM, LONG)
            - max_chunks: Maximum allowed chunks for this document

    Examples:
        >>> get_optimal_chunk_params(5)
        {'chunk_size': 1200, 'overlap': 200, 'tier': 'SHORT', 'max_chunks': 50}

        >>> get_optimal_chunk_params(20)
        {'chunk_size': 1600, 'overlap': 250, 'tier': 'MEDIUM', 'max_chunks': 50}

        >>> get_optimal_chunk_params(50)
        {'chunk_size': 2000, 'overlap': 300, 'tier': 'LONG', 'max_chunks': 50}
    """
    # Validate input
    if page_count <= 0:
        logger.warning(f"Invalid page_count={page_count}, defaulting to 1")
        page_count = 1

    # Determine the appropriate tier
    tier = None
    for tier_name, tier_config in CHUNKING_TIERS.items():
        min_pages, max_pages = tier_config["page_range"]
        if min_pages <= page_count <= max_pages:
            tier = tier_name
            chunk_size = tier_config["chunk_size"]
            overlap = tier_config["overlap"]
            break

    # Fallback to LONG tier if somehow not matched
    if tier is None:
        tier = "LONG"
        chunk_size = CHUNKING_TIERS["LONG"]["chunk_size"]
        overlap = CHUNKING_TIERS["LONG"]["overlap"]

    logger.info(
        f"Document with {page_count} pages assigned to {tier} tier: "
        f"chunk_size={chunk_size}, overlap={overlap}"
    )

    return {
        "chunk_size": chunk_size,
        "overlap": overlap,
        "tier": tier,
        "max_chunks": MAX_CHUNKS_PER_DOCUMENT
    }


def calculate_estimated_chunks(
    total_tokens: int,
    chunk_size: int,
    overlap: int
) -> int:
    """
    Estimate the number of chunks that will be created given document size and chunking params.

    Args:
        total_tokens: Total number of tokens in the document
        chunk_size: Size of each chunk in tokens
        overlap: Overlap between chunks in tokens

    Returns:
        Estimated number of chunks

    Examples:
        >>> calculate_estimated_chunks(5000, 1200, 200)
        5

        >>> calculate_estimated_chunks(20000, 1600, 250)
        15
    """
    if total_tokens <= 0 or chunk_size <= 0:
        return 0

    if total_tokens <= chunk_size:
        return 1

    # Effective chunk size after accounting for overlap
    effective_chunk_size = chunk_size - overlap

    # Calculate number of chunks needed
    remaining_tokens = total_tokens - chunk_size
    additional_chunks = (remaining_tokens + effective_chunk_size - 1) // effective_chunk_size

    total_chunks = 1 + additional_chunks

    return total_chunks


def apply_cost_ceiling(
    total_tokens: int,
    chunk_size: int,
    overlap: int,
    max_chunks: int = MAX_CHUNKS_PER_DOCUMENT
) -> Tuple[int, int, bool]:
    """
    Adjust chunk_size if document would exceed max_chunks limit.

    This implements cost ceiling protection by automatically increasing chunk_size
    to ensure we don't exceed the maximum allowed chunks per document.

    Args:
        total_tokens: Total number of tokens in the document
        chunk_size: Initial chunk size in tokens
        overlap: Overlap between chunks in tokens
        max_chunks: Maximum allowed chunks (default: 50)

    Returns:
        Tuple of (adjusted_chunk_size, adjusted_overlap, was_adjusted)
        - adjusted_chunk_size: The chunk size to use (may be larger than input)
        - adjusted_overlap: The overlap to use (proportionally adjusted)
        - was_adjusted: True if adjustments were made

    Which geometry is used is selected by CHUNK_CEILING_GEOMETRY (see
    CEILING_GEOMETRY_ENV); the default `legacy` arm does NOT hold the limit.

    Examples:
        >>> apply_cost_ceiling(100000, 1200, 200, 50)   # legacy arm
        (2196, 366, True)  # re-estimates to 55 chunks -- OVER the limit of 50

        >>> apply_cost_ceiling(5000, 1200, 200, 50)
        (1200, 200, False)  # No adjustment needed
    """
    estimated_chunks = calculate_estimated_chunks(total_tokens, chunk_size, overlap)

    if estimated_chunks <= max_chunks:
        # No adjustment needed
        return chunk_size, overlap, False

    logger.warning(
        f"Document would create {estimated_chunks} chunks, exceeding limit of {max_chunks}. "
        f"Adjusting chunk_size to fit within limit."
    )

    # The overlap ratio is preserved across the adjustment, so the overlap this
    # function RETURNS is not the overlap it was passed -- it grows with the
    # enlarged chunk size. Both arms below agree on that; they differ only in
    # whether the chunk size is solved against the old overlap or the new one.
    overlap_ratio = overlap / chunk_size

    if _ceiling_geometry() == "exact":
        # Solve the constraint the estimator actually enforces, with the overlap
        # that will actually be used. calculate_estimated_chunks fits within
        # max_chunks iff
        #     total_tokens <= max_chunks * c - (max_chunks - 1) * o
        # and here o = floor(c * overlap_ratio), so substituting the unfloored
        # o = c * overlap_ratio (which is >= the floored one, hence conservative)
        # and solving for c gives
        #     c >= total_tokens / (max_chunks - (max_chunks - 1) * overlap_ratio)
        # The denominator is > 1 for any overlap_ratio < 1, which every tier and
        # every adjusted pair satisfies, so it never degenerates.
        #
        # Ceiling division, not floor: floor lands one token short of the
        # requirement whenever the division is inexact, and one token short is a
        # whole extra chunk. That, plus solving against the pre-adjustment
        # overlap, is the entire legacy overshoot.
        denominator = max_chunks - (max_chunks - 1) * overlap_ratio
        adjusted_chunk_size = -int(-total_tokens // denominator)
    else:
        # LEGACY ARM -- kept verbatim as a measured comparison point.
        # Two defects, both of which push the produced count OVER max_chunks:
        #   1. floor division rounds the chunk size DOWN, i.e. below the size the
        #      constraint requires;
        #   2. it solves using `overlap`, then returns a LARGER overlap derived
        #      from the enlarged chunk size, which invalidates the solve -- more
        #      overlap means less new material per chunk means more chunks.
        # Defect 2 dominates and grows with the document: the solved size is
        # ~total_tokens/max_chunks while the requirement is
        # ~total_tokens/(max_chunks - (max_chunks-1)*ratio).
        adjusted_chunk_size = (total_tokens + (max_chunks - 1) * overlap) // max_chunks

    # Ensure minimum chunk size of 500 tokens. Raising the size can only reduce
    # the chunk count, so this cannot break the exact arm's guarantee.
    adjusted_chunk_size = max(adjusted_chunk_size, 500)

    adjusted_overlap = int(adjusted_chunk_size * overlap_ratio)

    # Ensure overlap doesn't exceed chunk_size
    adjusted_overlap = min(adjusted_overlap, adjusted_chunk_size // 2)

    logger.info(
        f"Adjusted chunking: chunk_size {chunk_size} -> {adjusted_chunk_size}, "
        f"overlap {overlap} -> {adjusted_overlap}"
    )

    # Verify the adjustment works
    final_estimated = calculate_estimated_chunks(total_tokens, adjusted_chunk_size, adjusted_overlap)
    logger.info(f"After adjustment: estimated {final_estimated} chunks (limit: {max_chunks})")

    return adjusted_chunk_size, adjusted_overlap, True


def build_cost_ceiling_record(
    *,
    applied: bool,
    max_chunks: int,
    original_chunk_size: int,
    original_overlap: int,
    adjusted_chunk_size: int,
    adjusted_overlap: int,
    chunks_before_ceiling: int,
    chunks_after_ceiling: int,
    trigger: str,
) -> Dict[str, Any]:
    """Describe what MAX_CHUNKS_PER_DOCUMENT did to this document's chunk geometry.

    MAX_CHUNKS_PER_DOCUMENT is a COST ceiling, not a retrieval strategy: when it
    fires it makes the LONGEST documents -- the ones that most need fine
    granularity -- carry the COARSEST chunks. That is a deliberate product
    tradeoff and is not changed here. What was missing is that it fired
    invisibly: chunk geometry varied with document length, nothing durable
    recorded it, and every retrieval measurement over a mixed corpus was
    silently confounded by a variable no result file contained.

    This record is persisted per document so the confound is at least
    observable, and so a retrieval result can be split by `applied` after the
    fact. It is emitted whether or not the ceiling fired -- absence of the field
    would otherwise be ambiguous between "did not fire" and "written by an older
    build".

    `trigger` distinguishes the two places the ceiling can bite:
      - "estimated_tokens": the token-arithmetic estimate exceeded the ceiling
        before any chunking happened (basic path, and the first pass of the
        section-aware path).
      - "actual_section_chunks": the estimate was fine but section-aware
        chunking really produced more chunks than the ceiling allows, so the
        document was re-chunked with coarser parameters.
    """
    return {
        "applied": applied,
        "trigger": trigger if applied else None,
        "max_chunks": max_chunks,
        "original_chunk_size": original_chunk_size,
        "original_overlap": original_overlap,
        "adjusted_chunk_size": adjusted_chunk_size,
        "adjusted_overlap": adjusted_overlap,
        "chunks_before_ceiling": chunks_before_ceiling,
        "chunks_after_ceiling": chunks_after_ceiling,
        "chunks_avoided": max(chunks_before_ceiling - chunks_after_ceiling, 0),
    }


def get_chunking_strategy(
    page_count: int,
    total_tokens: int,
    doc_type: str = "paper"
) -> Dict[str, any]:
    """
    Get complete chunking strategy including cost ceiling protection.

    This is the main function to use for determining chunking parameters.
    It combines adaptive chunking based on page count with cost ceiling protection.

    Args:
        page_count: Number of pages in the document
        total_tokens: Total number of tokens in the document
        doc_type: Type of document (currently only "paper" is supported)

    Returns:
        Dict containing:
            - chunk_size: Final chunk size to use
            - overlap: Final overlap to use
            - tier: Chunking tier (SHORT, MEDIUM, LONG)
            - max_chunks: Maximum allowed chunks
            - was_adjusted: Whether cost ceiling adjustment was applied
            - estimated_chunks: Estimated number of chunks that will be created
            - cost_ceiling: Full record of what the ceiling did (see build_cost_ceiling_record)

    Example:
        >>> get_chunking_strategy(page_count=15, total_tokens=8000)["tier"]
        'MEDIUM'
    """
    # Step 1: Get optimal parameters based on page count
    params = get_optimal_chunk_params(page_count, doc_type)

    chunk_size = params["chunk_size"]
    overlap = params["overlap"]
    max_chunks = params["max_chunks"]
    tier = params["tier"]

    # Chunk count the tier's own geometry would have produced. Recorded even when
    # the ceiling does not fire, so "did the ceiling change this document?" is
    # answerable from the stored metadata alone rather than from a log line.
    chunks_before_ceiling = calculate_estimated_chunks(total_tokens, chunk_size, overlap)

    # Step 2: Apply cost ceiling protection
    adjusted_chunk_size, adjusted_overlap, was_adjusted = apply_cost_ceiling(
        total_tokens=total_tokens,
        chunk_size=chunk_size,
        overlap=overlap,
        max_chunks=max_chunks
    )

    # Step 3: Calculate final estimated chunks
    estimated_chunks = calculate_estimated_chunks(
        total_tokens=total_tokens,
        chunk_size=adjusted_chunk_size,
        overlap=adjusted_overlap
    )

    return {
        "chunk_size": adjusted_chunk_size,
        "overlap": adjusted_overlap,
        "tier": tier,
        "max_chunks": max_chunks,
        "was_adjusted": was_adjusted,
        "estimated_chunks": estimated_chunks,
        "cost_ceiling": build_cost_ceiling_record(
            applied=was_adjusted,
            max_chunks=max_chunks,
            original_chunk_size=chunk_size,
            original_overlap=overlap,
            adjusted_chunk_size=adjusted_chunk_size,
            adjusted_overlap=adjusted_overlap,
            chunks_before_ceiling=chunks_before_ceiling,
            chunks_after_ceiling=estimated_chunks,
            trigger="estimated_tokens",
        ),
    }


# ============================================
# SECTION-AWARE CHUNKING
# ============================================


def chunk_section_content(
    content: str,
    max_chunk_size: int,
    overlap: int,
    section_title: str,
    section_type: str
) -> List[Dict[str, Any]]:
    """
    Chunk a single section's content while preserving sentence boundaries.

    If the section fits within max_chunk_size, it's returned as a single chunk.
    Otherwise, it's split into multiple chunks at sentence boundaries.

    Args:
        content: Section content text
        max_chunk_size: Maximum chunk size in tokens
        overlap: Overlap between chunks in tokens
        section_title: Title of the section
        section_type: Type of section (intro, methods, results, etc.)

    Returns:
        List of chunk dictionaries with metadata
    """
    enc = tiktoken.get_encoding("cl100k_base")
    tokens = count_and_encode(enc, content)

    # If section fits in one chunk, return it as-is
    if len(tokens) <= max_chunk_size:
        return [{
            "content": content,
            "section_title": section_title,
            "section_type": section_type,
            "chunk_index_in_section": 0,
            "tokens": len(tokens)
        }]

    # Section is too large - need to split at sentence boundaries
    # Split content into sentences
    sentences = split_sentences(content)

    chunks = []
    current_chunk_sentences = []
    current_chunk_tokens = 0
    chunk_index = 0

    for sentence in sentences:
        sentence_tokens = len(count_and_encode(enc, sentence))

        # Check if adding this sentence would exceed max_chunk_size
        if current_chunk_tokens + sentence_tokens > max_chunk_size and current_chunk_sentences:
            # Save current chunk
            chunk_content = ' '.join(current_chunk_sentences)
            chunks.append({
                "content": chunk_content,
                "section_title": section_title,
                "section_type": section_type,
                "chunk_index_in_section": chunk_index,
                "tokens": current_chunk_tokens
            })

            # Start new chunk with overlap
            # Keep last few sentences for overlap
            overlap_sentences = []
            overlap_tokens = 0
            for s in reversed(current_chunk_sentences):
                s_tokens = len(count_and_encode(enc, s))
                if overlap_tokens + s_tokens <= overlap:
                    overlap_sentences.insert(0, s)
                    overlap_tokens += s_tokens
                else:
                    break

            current_chunk_sentences = overlap_sentences
            current_chunk_tokens = overlap_tokens
            chunk_index += 1

        # Add sentence to current chunk
        current_chunk_sentences.append(sentence)
        current_chunk_tokens += sentence_tokens

    # Add final chunk if there's content
    if current_chunk_sentences:
        chunk_content = ' '.join(current_chunk_sentences)
        chunks.append({
            "content": chunk_content,
            "section_title": section_title,
            "section_type": section_type,
            "chunk_index_in_section": chunk_index,
            "tokens": current_chunk_tokens
        })

    return chunks


def chunk_by_sections(
    sections: List[Dict[str, Any]],
    max_chunk_size: int,
    overlap: int
) -> List[Dict[str, Any]]:
    """
    Chunk document by sections, preserving document structure.

    Each section is chunked independently. Small sections become single chunks,
    large sections are split at sentence boundaries.

    Args:
        sections: List of section dictionaries from GROBID extraction
                  Each should have: title, content, type, paragraph_count
        max_chunk_size: Maximum chunk size in tokens
        overlap: Overlap between chunks in tokens

    Returns:
        List of chunk dictionaries with section metadata

    Example section structure:
        {
            "title": "Introduction",
            "content": "This paper presents...",
            "type": "introduction",
            "paragraph_count": 3
        }

    Example output chunk:
        {
            "content": "This paper presents...",
            "section_title": "Introduction",
            "section_type": "introduction",
            "chunk_index_in_section": 0,
            "tokens": 450
        }
    """
    all_chunks = []

    for section in sections:
        title = section.get("title", "Untitled Section")
        content = section.get("content", "")
        section_type = section.get("type", "other")

        if not content.strip():
            logger.warning(f"Skipping empty section: {title}")
            continue

        # Chunk this section
        section_chunks = chunk_section_content(
            content=content,
            max_chunk_size=max_chunk_size,
            overlap=overlap,
            section_title=title,
            section_type=section_type
        )

        all_chunks.extend(section_chunks)

    logger.info(
        f"Created {len(all_chunks)} chunks from {len(sections)} sections "
        f"(avg {len(all_chunks) / max(len(sections), 1):.1f} chunks per section)"
    )

    return all_chunks


def get_section_aware_chunking_strategy(
    sections: List[Dict[str, Any]],
    page_count: int,
    total_tokens: int,
    doc_type: str = "paper"
) -> Dict[str, Any]:
    """
    Get complete section-aware chunking strategy.

    This function combines adaptive chunking parameters with section-aware chunking
    to create an optimal chunking strategy that preserves document structure.

    Args:
        sections: List of section dictionaries from GROBID extraction
        page_count: Number of pages in the document
        total_tokens: Total number of tokens in the document
        doc_type: Type of document (currently only "paper" is supported)

    Returns:
        Dict containing:
            - chunk_size: Final chunk size to use
            - overlap: Final overlap to use
            - tier: Chunking tier (SHORT, MEDIUM, LONG)
            - max_chunks: Maximum allowed chunks
            - was_adjusted: Whether cost ceiling adjustment was applied
            - estimated_chunks: Estimated number of chunks that will be created
            - chunks: List of actual chunks with section metadata
            - chunking_method: "section-aware" to distinguish from basic chunking
            - cost_ceiling: Full record of what the ceiling did (see build_cost_ceiling_record)

    Example:
        >>> sections = [
        ...     {"title": "Introduction", "content": "...", "type": "introduction"},
        ...     {"title": "Methods", "content": "...", "type": "methods"}
        ... ]
        >>> strategy = get_section_aware_chunking_strategy(sections, 15, 8000)
        >>> strategy['chunks']  # List of chunks with section metadata
    """
    # Step 1: Get base adaptive chunking parameters
    base_strategy = get_chunking_strategy(
        page_count=page_count,
        total_tokens=total_tokens,
        doc_type=doc_type
    )

    chunk_size = base_strategy["chunk_size"]
    overlap = base_strategy["overlap"]
    tier = base_strategy["tier"]
    was_adjusted = base_strategy["was_adjusted"]
    cost_ceiling = base_strategy["cost_ceiling"]

    # Step 2: Chunk by sections using adaptive parameters
    chunks = chunk_by_sections(
        sections=sections,
        max_chunk_size=chunk_size,
        overlap=overlap
    )

    # Step 3: Check if we need to apply cost ceiling
    if len(chunks) > MAX_CHUNKS_PER_DOCUMENT:
        logger.warning(
            f"Section-aware chunking produced {len(chunks)} chunks, "
            f"exceeding limit of {MAX_CHUNKS_PER_DOCUMENT}. Adjusting..."
        )

        chunks_before_rechunk = len(chunks)

        # Calculate new chunk_size to fit within limit
        adjusted_chunk_size, adjusted_overlap, _ = apply_cost_ceiling(
            total_tokens=total_tokens,
            chunk_size=chunk_size,
            overlap=overlap,
            max_chunks=MAX_CHUNKS_PER_DOCUMENT
        )

        # Re-chunk with adjusted parameters
        chunks = chunk_by_sections(
            sections=sections,
            max_chunk_size=adjusted_chunk_size,
            overlap=adjusted_overlap
        )

        # Record against the geometry that was ACTUALLY re-chunked away from --
        # the parameters going into this pass -- not the tier defaults, which
        # the first (estimate-driven) ceiling pass may already have replaced.
        cost_ceiling = build_cost_ceiling_record(
            applied=True,
            max_chunks=MAX_CHUNKS_PER_DOCUMENT,
            original_chunk_size=chunk_size,
            original_overlap=overlap,
            adjusted_chunk_size=adjusted_chunk_size,
            adjusted_overlap=adjusted_overlap,
            chunks_before_ceiling=chunks_before_rechunk,
            chunks_after_ceiling=len(chunks),
            trigger="actual_section_chunks",
        )

        was_adjusted = True
        chunk_size = adjusted_chunk_size
        overlap = adjusted_overlap

    return {
        "chunk_size": chunk_size,
        "overlap": overlap,
        "tier": tier,
        "max_chunks": MAX_CHUNKS_PER_DOCUMENT,
        "was_adjusted": was_adjusted,
        "estimated_chunks": len(chunks),
        "chunks": chunks,
        "chunking_method": "section-aware",
        "cost_ceiling": cost_ceiling,
    }
