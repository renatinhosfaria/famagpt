"""
Generic property scraper implementation
"""

import re
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse
import aiohttp
from bs4 import BeautifulSoup
import asyncio
from datetime import datetime

from shared.src.utils.logging import get_logger

from ...domain.entities.property import (
    Property, PropertyLocation, PropertyFeatures, 
    PropertyType, PropertyListingType, SearchQuery
)
from ...domain.protocols.web_scraper import WebScraperProtocol, PropertyExtractorProtocol


logger = get_logger("web_search.scrapers")


class GenericPropertyScraper(WebScraperProtocol, PropertyExtractorProtocol):
    """Generic property scraper using BeautifulSoup"""
    
    def __init__(self, site_name: str = "generic"):
        self.site_name = site_name
        self.session = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.8,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                timeout=timeout,
                connector=connector
            )
        return self.session
    
    async def _fetch_html(self, url: str) -> Optional[str]:
        """Fetch HTML content from URL"""
        try:
            session = await self._get_session()
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logger.warning(f"HTTP {response.status} for URL: {url}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching URL {url}: {str(e)}")
            return None
    
    def _extract_price(self, text: str) -> Optional[float]:
        """Extract price from text"""
        if not text:
            return None
        
        # Remove common currency symbols and formatting
        clean_text = re.sub(r'[R$\s.]+', '', text)
        clean_text = clean_text.replace(',', '.')
        
        # Find numeric values
        price_matches = re.findall(r'\d+(?:\.\d+)?', clean_text)
        
        if price_matches:
            try:
                # Take the largest number (usually the price)
                prices = [float(match) for match in price_matches]
                return max(prices)
            except ValueError:
                return None
        
        return None
    
    def _extract_number(self, text: str) -> Optional[int]:
        """Extract number from text"""
        if not text:
            return None
        
        numbers = re.findall(r'\d+', text)
        if numbers:
            try:
                return int(numbers[0])
            except ValueError:
                return None
        return None
    
    def _extract_area(self, text: str) -> Optional[float]:
        """Extract area from text (in m²)"""
        if not text:
            return None
        
        # Look for patterns like "120m²", "120 m²", "120m2"
        area_pattern = r'(\d+(?:\.\d+)?)\s*m[²2]'
        matches = re.findall(area_pattern, text, re.IGNORECASE)
        
        if matches:
            try:
                return float(matches[0])
            except ValueError:
                return None
        
        return None
    
    def _determine_property_type(self, text: str) -> PropertyType:
        """Determine property type from text"""
        text_lower = text.lower() if text else ""
        
        if any(word in text_lower for word in ['casa', 'sobrado', 'residencia']):
            return PropertyType.HOUSE
        elif any(word in text_lower for word in ['apartamento', 'apto', 'flat']):
            return PropertyType.APARTMENT
        elif any(word in text_lower for word in ['comercial', 'loja', 'escritório', 'sala']):
            return PropertyType.COMMERCIAL
        elif any(word in text_lower for word in ['terreno', 'lote', 'área']):
            return PropertyType.LAND
        else:
            return PropertyType.ANY
    
    def _determine_listing_type(self, text: str) -> PropertyListingType:
        """Determine listing type from text"""
        text_lower = text.lower() if text else ""
        
        if any(word in text_lower for word in ['aluguel', 'alugar', 'locação', 'locar']):
            return PropertyListingType.RENT
        else:
            return PropertyListingType.SALE
    
    def extract_properties_from_html(
        self, 
        html: str, 
        base_url: str
    ) -> List[Property]:
        """Extract property listings from search results HTML"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            properties = []
            
            # Generic selectors that work on many real estate sites
            property_selectors = [
                '.property-card',
                '.listing-item',
                '.property-item',
                '.result-item',
                '.card',
                '[class*="property"]',
                '[class*="listing"]',
                '[class*="result"]'
            ]
            
            property_elements = []
            for selector in property_selectors:
                elements = soup.select(selector)
                if elements:
                    property_elements = elements
                    logger.debug(f"Found {len(elements)} properties using selector: {selector}")
                    break
            
            if not property_elements:
                # Fallback: look for common patterns
                property_elements = soup.find_all(['div', 'article'], class_=re.compile(r'(property|listing|result|card)', re.I))
                logger.debug(f"Fallback found {len(property_elements)} potential property elements")
            
            for element in property_elements[:20]:  # Limit to first 20 for performance
                try:
                    property_data = self._extract_property_from_element(element, base_url)
                    if property_data and property_data.is_valid():
                        properties.append(property_data)
                except Exception as e:
                    logger.debug(f"Error extracting property from element: {str(e)}")
                    continue
            
            logger.info(f"Successfully extracted {len(properties)} properties from {base_url}")
            return properties
            
        except Exception as e:
            logger.error(f"Error parsing HTML from {base_url}: {str(e)}")
            return []
    
    def _extract_property_from_element(self, element, base_url: str) -> Optional[Property]:
        """Extract property data from a single HTML element"""
        try:
            # Extract title
            title_selectors = ['h1', 'h2', 'h3', '.title', '.name', '[class*="title"]', 'a']
            title = None
            for selector in title_selectors:
                title_elem = element.select_one(selector)
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title and len(title) > 10:  # Reasonable title length
                        break
            
            if not title:
                return None
            
            # Extract price
            price_selectors = ['.price', '[class*="price"]', '[class*="valor"]']
            price = None
            for selector in price_selectors:
                price_elem = element.select_one(selector)
                if price_elem:
                    price_text = price_elem.get_text(strip=True)
                    price = self._extract_price(price_text)
                    if price and price > 1000:  # Reasonable price minimum
                        break
            
            # Extract URL
            link_elem = element.find('a', href=True)
            url = None
            if link_elem:
                href = link_elem['href']
                url = urljoin(base_url, href)
            
            # Extract description
            description_selectors = ['.description', '[class*="description"]', 'p']
            description = None
            for selector in description_selectors:
                desc_elem = element.select_one(selector)
                if desc_elem:
                    desc_text = desc_elem.get_text(strip=True)
                    if desc_text and len(desc_text) > 20:  # Reasonable description length
                        description = desc_text[:500]  # Truncate long descriptions
                        break
            
            # Extract location info
            location_text = element.get_text()
            location = PropertyLocation()
            
            # Simple location extraction
            if 'Uberlândia' in location_text or 'uberlandia' in location_text.lower():
                location.city = "Uberlândia"
                location.state = "MG"
            
            # Extract features
            features = PropertyFeatures()
            full_text = element.get_text().lower()
            
            # Extract bedrooms
            bedroom_patterns = [r'(\d+)\s*quarto', r'(\d+)\s*dorm']
            for pattern in bedroom_patterns:
                match = re.search(pattern, full_text)
                if match:
                    features.bedrooms = int(match.group(1))
                    break
            
            # Extract bathrooms
            bathroom_patterns = [r'(\d+)\s*banheiro', r'(\d+)\s*wc']
            for pattern in bathroom_patterns:
                match = re.search(pattern, full_text)
                if match:
                    features.bathrooms = int(match.group(1))
                    break
            
            # Extract area
            features.area_m2 = self._extract_area(full_text)
            
            # Create property
            property_obj = Property(
                id=None,
                title=title,
                description=description,
                price=price,
                currency="BRL",
                listing_type=self._determine_listing_type(full_text),
                property_type=self._determine_property_type(title + " " + (description or "")),
                location=location,
                features=features,
                source_url=url,
                source_site=self.site_name,
                created_at=datetime.utcnow()
            )
            
            return property_obj
            
        except Exception as e:
            logger.debug(f"Error extracting property from element: {str(e)}")
            return None
    
    def extract_property_details_from_html(
        self, 
        html: str, 
        property_url: str
    ) -> Optional[Property]:
        """Extract detailed property information from property page HTML"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # This would be implemented for specific property detail pages
            # For now, return None as this is more complex and site-specific
            return None
            
        except Exception as e:
            logger.error(f"Error extracting property details from {property_url}: {str(e)}")
            return None
    
    async def search_properties(self, query: SearchQuery) -> List[Property]:
        """Search for properties - generates mock data for demonstration"""
        try:
            logger.info(f"Searching properties for: {query.query} in {query.city}/{query.state}")
            
            # This is a mock implementation for demonstration
            # In a real implementation, you would:
            # 1. Build search URLs for real estate sites
            # 2. Fetch HTML content
            # 3. Extract property data using extract_properties_from_html
            
            properties = []
            
            # Generate some realistic mock data
            mock_properties = [
                {
                    "title": f"Apartamento 2 quartos - {query.city}",
                    "price": 280000.0,
                    "description": "Apartamento moderno com 2 quartos, sala ampla, cozinha planejada e 1 vaga de garagem.",
                    "bedrooms": 2,
                    "bathrooms": 1,
                    "area_m2": 65.0,
                    "property_type": PropertyType.APARTMENT
                },
                {
                    "title": f"Casa 3 quartos com quintal - {query.city}",
                    "price": 450000.0,
                    "description": "Casa térrea com 3 quartos, 2 banheiros, sala, cozinha, área de serviço e quintal.",
                    "bedrooms": 3,
                    "bathrooms": 2,
                    "area_m2": 120.0,
                    "property_type": PropertyType.HOUSE
                },
                {
                    "title": f"Apartamento 1 quarto centro - {query.city}",
                    "price": 180000.0,
                    "description": "Apartamento no centro da cidade, próximo ao comércio e transporte público.",
                    "bedrooms": 1,
                    "bathrooms": 1,
                    "area_m2": 45.0,
                    "property_type": PropertyType.APARTMENT
                }
            ]
            
            for i, mock_data in enumerate(mock_properties):
                location = PropertyLocation(
                    city=query.city,
                    state=query.state,
                    neighborhood="Centro" if i % 2 == 0 else "Bairro Residencial"
                )
                
                features = PropertyFeatures(
                    bedrooms=mock_data["bedrooms"],
                    bathrooms=mock_data["bathrooms"],
                    area_m2=mock_data["area_m2"],
                    garage_spaces=1 if mock_data["property_type"] == PropertyType.HOUSE else 1
                )
                
                property_obj = Property(
                    id=f"mock_{i+1}",
                    title=mock_data["title"],
                    description=mock_data["description"],
                    price=mock_data["price"],
                    currency="BRL",
                    listing_type=query.listing_type,
                    property_type=mock_data["property_type"],
                    location=location,
                    features=features,
                    source_url=f"https://example.com/property/{i+1}",
                    source_site=self.site_name,
                    created_at=datetime.utcnow()
                )
                
                # Apply filters
                if property_obj.matches_criteria(
                    min_price=query.min_price,
                    max_price=query.max_price,
                    property_type=query.property_type,
                    min_bedrooms=query.min_bedrooms,
                    max_bedrooms=query.max_bedrooms,
                    city=query.city
                ):
                    properties.append(property_obj)
            
            logger.info(f"Found {len(properties)} properties matching criteria")
            return properties[:query.max_results]
            
        except Exception as e:
            logger.error(f"Error searching properties: {str(e)}")
            return []
    
    async def get_property_details(self, property_url: str) -> Optional[Property]:
        """Get detailed information about a specific property"""
        try:
            html = await self._fetch_html(property_url)
            if html:
                return self.extract_property_details_from_html(html, property_url)
            return None
        except Exception as e:
            logger.error(f"Error getting property details for {property_url}: {str(e)}")
            return None
    
    def get_site_name(self) -> str:
        """Get the name of the site this scraper handles"""
        return self.site_name
    
    def can_handle_url(self, url: str) -> bool:
        """Check if this scraper can handle the given URL"""
        # Generic scraper can handle any URL
        return True
    
    async def cleanup(self):
        """Clean up resources"""
        if self.session and not self.session.closed:
            await self.session.close()