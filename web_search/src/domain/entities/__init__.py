"""
Domain entities for web search service
"""

from .property import (
    Property,
    PropertyLocation,
    PropertyFeatures,
    PropertyType,
    PropertyListingType,
    SearchQuery,
    SearchResult
)

__all__ = [
    "Property",
    "PropertyLocation", 
    "PropertyFeatures",
    "PropertyType",
    "PropertyListingType",
    "SearchQuery",
    "SearchResult"
]