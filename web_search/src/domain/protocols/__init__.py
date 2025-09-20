"""
Domain protocols for web search service
"""

from .web_scraper import (
    WebScraperProtocol,
    CacheServiceProtocol,
    PropertyExtractorProtocol
)

__all__ = [
    "WebScraperProtocol",
    "CacheServiceProtocol", 
    "PropertyExtractorProtocol"
]