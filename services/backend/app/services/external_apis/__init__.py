"""External API clients for paper discovery"""

from .semantic_scholar import SemanticScholarAPI
from .arxiv import ArXivAPI
from .pubmed import PubMedAPI

__all__ = ['SemanticScholarAPI', 'ArXivAPI', 'PubMedAPI']
