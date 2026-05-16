"""
GROBID Client Service

Provides integration with GROBID (GeneRation Of BIbliographic Data) service
for extracting structured information from scientific PDF documents.

GROBID extracts:
- Document metadata (title, authors, affiliations, journal)
- Structured sections (abstract, introduction, methods, results, discussion, conclusion)
- Bibliography/references with structured parsing
- In-text citations and their context
- Figures and tables

This is much more powerful than basic PDF text extraction for scientific documents.
"""

import httpx
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
from app.core.config import settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# TEI (Text Encoding Initiative) namespace used by GROBID
TEI_NAMESPACE = {'tei': 'http://www.tei-c.org/ns/1.0'}


class GrobidClient:
    """Client for interacting with GROBID service."""

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize GROBID client.

        Args:
            base_url: GROBID service URL (defaults to settings.GROBID_URL)
        """
        self.base_url = base_url or settings.GROBID_URL
        if not self.base_url:
            raise ValueError("GROBID_URL not configured in settings")

        # Remove trailing slash for consistency
        self.base_url = self.base_url.rstrip('/')

        logger.info(f"Initialized GROBID client with base URL: {self.base_url}")

    async def process_pdf(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """
        Process a PDF document with GROBID to extract structured information.

        Args:
            pdf_bytes: PDF file content as bytes

        Returns:
            Dictionary containing extracted structured data:
            {
                "title": str,
                "authors": List[Dict],
                "abstract": str,
                "sections": List[Dict],
                "references": List[Dict],
                "full_text": str,
                "metadata": Dict
            }

        Raises:
            httpx.HTTPError: If GROBID service request fails
            Exception: If parsing fails
        """
        try:
            logger.info("Sending PDF to GROBID for processing")

            # Call GROBID's processFulltextDocument endpoint
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/processFulltextDocument",
                    files={"input": ("document.pdf", pdf_bytes, "application/pdf")},
                    data={
                        "consolidateHeader": "1",  # Consolidate metadata
                        "consolidateCitations": "1",  # Consolidate references
                        "includeRawCitations": "1",  # Include raw citation text
                        "includeRawAffiliations": "1",  # Include affiliations
                        "teiCoordinates": ["s", "biblStruct", "ref"]  # Include coordinates
                    }
                )

                response.raise_for_status()
                tei_xml = response.text

            logger.info(f"Received TEI XML from GROBID ({len(tei_xml)} chars)")

            # Parse TEI XML to extract structured data
            structured_data = self._parse_tei_xml(tei_xml)

            logger.info(
                f"Extracted: title='{structured_data.get('title', 'N/A')}', "
                f"authors={len(structured_data.get('authors', []))}, "
                f"sections={len(structured_data.get('sections', []))}, "
                f"references={len(structured_data.get('references', []))}"
            )

            return structured_data

        except httpx.HTTPError as e:
            logger.error(f"GROBID HTTP error: {e}")
            raise
        except Exception as e:
            logger.error(f"GROBID processing failed: {e}")
            raise

    def _parse_tei_xml(self, tei_xml: str) -> Dict[str, Any]:
        """
        Parse GROBID's TEI XML output into structured data.

        Args:
            tei_xml: TEI XML string from GROBID

        Returns:
            Dictionary with extracted structured information
        """
        try:
            root = ET.fromstring(tei_xml)

            # Extract metadata from teiHeader
            metadata = self._extract_metadata(root)

            # Extract abstract
            abstract = self._extract_abstract(root)

            # Extract body sections with structure
            sections = self._extract_sections(root)

            # Extract references/bibliography
            references = self._extract_references(root)

            # Extract full text (concatenate all sections)
            full_text = self._extract_full_text(root)

            return {
                "title": metadata.get("title", ""),
                "authors": metadata.get("authors", []),
                "abstract": abstract,
                "sections": sections,
                "references": references,
                "full_text": full_text,
                "metadata": metadata
            }

        except ET.ParseError as e:
            logger.error(f"Failed to parse TEI XML: {e}")
            raise

    def _extract_metadata(self, root: ET.Element) -> Dict[str, Any]:
        """Extract document metadata from TEI header."""
        metadata = {}

        # Find teiHeader
        header = root.find('.//tei:teiHeader', TEI_NAMESPACE)
        if header is None:
            return metadata

        # Extract title
        title_elem = header.find('.//tei:titleStmt/tei:title[@type="main"]', TEI_NAMESPACE)
        if title_elem is not None and title_elem.text:
            metadata["title"] = title_elem.text.strip()

        # Extract authors
        authors = []
        author_elems = header.findall('.//tei:sourceDesc//tei:author', TEI_NAMESPACE)
        for author_elem in author_elems:
            author_data = {}

            # First name
            forename = author_elem.find('.//tei:forename[@type="first"]', TEI_NAMESPACE)
            if forename is not None and forename.text:
                author_data["first_name"] = forename.text.strip()

            # Middle name
            middle = author_elem.find('.//tei:forename[@type="middle"]', TEI_NAMESPACE)
            if middle is not None and middle.text:
                author_data["middle_name"] = middle.text.strip()

            # Last name
            surname = author_elem.find('.//tei:surname', TEI_NAMESPACE)
            if surname is not None and surname.text:
                author_data["last_name"] = surname.text.strip()

            # Email
            email = author_elem.find('.//tei:email', TEI_NAMESPACE)
            if email is not None and email.text:
                author_data["email"] = email.text.strip()

            if author_data:
                authors.append(author_data)

        metadata["authors"] = authors

        # Extract publication info if available
        pub_date = header.find('.//tei:publicationStmt/tei:date', TEI_NAMESPACE)
        if pub_date is not None and pub_date.get('when'):
            metadata["publication_date"] = pub_date.get('when')

        return metadata

    def _extract_abstract(self, root: ET.Element) -> str:
        """Extract abstract text."""
        abstract_elem = root.find('.//tei:profileDesc//tei:abstract', TEI_NAMESPACE)
        if abstract_elem is not None:
            # Get all text content, removing extra whitespace
            abstract_parts = []
            for div in abstract_elem.findall('.//tei:div', TEI_NAMESPACE):
                text = ''.join(div.itertext()).strip()
                if text:
                    abstract_parts.append(text)

            if abstract_parts:
                return ' '.join(abstract_parts)

            # Fallback: get all text if no divs found
            return ''.join(abstract_elem.itertext()).strip()

        return ""

    def _extract_coordinates(self, element: ET.Element) -> Dict:
        """
        Extract PDF bounding box coordinates from TEI element.

        GROBID returns coordinates in @coords attribute when teiCoordinates enabled.
        Format: "page,x,y,width,height" — multiple boxes are space-separated.
        Returns the first bounding box only (sufficient for scroll-to-location).
        """
        coords = element.get('coords')
        if coords:
            try:
                # Take first box if multiple (multi-line spans)
                first = coords.strip().split(' ')[0]
                parts = first.split(',')
                return {
                    "page": int(parts[0]),
                    "x": float(parts[1]),
                    "y": float(parts[2]),
                    "width": float(parts[3]),
                    "height": float(parts[4])
                }
            except (ValueError, IndexError):
                logger.warning(f"Failed to parse coordinates: {coords}")
                return {}
        return {}

    def _extract_sentence_coords(self, element: ET.Element) -> List[Dict]:
        """
        Extract sentence-level bounding boxes from <s> elements inside a paragraph.

        Returns list of {text, coords} dicts — empty list if no <s> elements found.
        """
        sentences = []
        for s_elem in element.findall('.//tei:s', TEI_NAMESPACE):
            text = ''.join(s_elem.itertext()).strip()
            if not text:
                continue
            coords = self._extract_coordinates(s_elem)
            sentences.append({"text": text, "coords": coords})
        return sentences

    def _extract_sections(self, root: ET.Element) -> List[Dict[str, Any]]:
        """Extract document sections with structure and coordinates."""
        sections = []

        # Find body element
        body = root.find('.//tei:text/tei:body', TEI_NAMESPACE)
        if body is None:
            return sections

        # Find all div elements (sections)
        for idx, div in enumerate(body.findall('.//tei:div', TEI_NAMESPACE)):
            # Extract section heading
            head = div.find('./tei:head', TEI_NAMESPACE)
            if head is not None:
                title = ''.join(head.itertext()).strip()
            else:
                title = "Untitled Section"

            # Extract section content and paragraph-level coordinates
            paragraphs = []
            paragraph_data = []
            for p_idx, p in enumerate(div.findall('.//tei:p', TEI_NAMESPACE)):
                text = ''.join(p.itertext()).strip()
                if text:
                    paragraphs.append(text)
                    paragraph_data.append({
                        "id": f"section-{idx}-para-{p_idx}",
                        "text": text,
                        "coordinates": self._extract_coordinates(p),
                        "sentences": self._extract_sentence_coords(p),
                    })

            content = '\n\n'.join(paragraphs)

            # Only add sections with content
            if content:
                section = {
                    "id": f"section-{idx}",  # Stable section ID
                    "title": title,
                    "content": content,
                    "paragraph_count": len(paragraphs),
                    "type": self._infer_section_type(title),
                    "coordinates": self._extract_coordinates(div),  # Section-level coordinates
                    "paragraphs": paragraph_data  # Paragraph-level coordinates
                }
                sections.append(section)

        return sections

    def _infer_section_type(self, heading: str) -> str:
        """Infer section type from heading text."""
        heading_lower = heading.lower()

        if any(kw in heading_lower for kw in ["abstract"]):
            return "abstract"
        elif any(kw in heading_lower for kw in ["introduction", "background"]):
            return "introduction"
        elif any(kw in heading_lower for kw in ["method", "material", "procedure"]):
            return "methods"
        elif any(kw in heading_lower for kw in ["result", "finding"]):
            return "results"
        elif any(kw in heading_lower for kw in ["discussion", "interpretation"]):
            return "discussion"
        elif any(kw in heading_lower for kw in ["conclusion", "summary", "concluding"]):
            return "conclusion"
        elif any(kw in heading_lower for kw in ["related work", "literature review", "prior work"]):
            return "related_work"
        else:
            return "other"

    def _extract_references(self, root: ET.Element) -> List[Dict[str, Any]]:
        """Extract bibliography/references."""
        references = []

        # Find back matter with bibliography
        back = root.find('.//tei:text/tei:back', TEI_NAMESPACE)
        if back is None:
            return references

        # Find all biblStruct elements (structured bibliography entries)
        for bibl in back.findall('.//tei:biblStruct', TEI_NAMESPACE):
            ref = {}

            # Extract title
            title = bibl.find('.//tei:analytic/tei:title[@type="main"]', TEI_NAMESPACE)
            if title is None:
                title = bibl.find('.//tei:monogr/tei:title', TEI_NAMESPACE)
            if title is not None and title.text:
                ref["title"] = title.text.strip()

            # Extract authors
            authors = []
            for author in bibl.findall('.//tei:analytic/tei:author', TEI_NAMESPACE):
                author_name_parts = []

                forename = author.find('.//tei:forename', TEI_NAMESPACE)
                if forename is not None and forename.text:
                    author_name_parts.append(forename.text.strip())

                surname = author.find('.//tei:surname', TEI_NAMESPACE)
                if surname is not None and surname.text:
                    author_name_parts.append(surname.text.strip())

                if author_name_parts:
                    authors.append(' '.join(author_name_parts))

            ref["authors"] = authors

            # Extract publication year
            date = bibl.find('.//tei:monogr/tei:imprint/tei:date', TEI_NAMESPACE)
            if date is not None and date.get('when'):
                ref["year"] = date.get('when')

            # Extract journal/venue
            venue = bibl.find('.//tei:monogr/tei:title', TEI_NAMESPACE)
            if venue is not None and venue.text:
                ref["venue"] = venue.text.strip()

            # Extract DOI if available
            doi = bibl.find('.//tei:idno[@type="DOI"]', TEI_NAMESPACE)
            if doi is not None and doi.text:
                ref["doi"] = doi.text.strip()

            if ref:  # Only add if we extracted something
                references.append(ref)

        return references

    def _extract_full_text(self, root: ET.Element) -> str:
        """Extract full document text."""
        text_parts = []

        # Get abstract
        abstract = self._extract_abstract(root)
        if abstract:
            text_parts.append(abstract)

        # Get all body text
        body = root.find('.//tei:text/tei:body', TEI_NAMESPACE)
        if body is not None:
            body_text = ''.join(body.itertext()).strip()
            if body_text:
                text_parts.append(body_text)

        return '\n\n'.join(text_parts)


# Global client instance
_grobid_client = None

def get_grobid_client() -> GrobidClient:
    """Get or create global GROBID client instance."""
    global _grobid_client
    if _grobid_client is None:
        _grobid_client = GrobidClient()
    return _grobid_client
