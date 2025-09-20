"""
HTTP client utilities.
"""
import asyncio
from typing import Any, Dict, Optional, Union
import aiohttp
from aiohttp import ClientSession, ClientTimeout

from ..utils.logging import get_logger
from ..utils.helpers import retry_async


logger = get_logger(__name__)


class HTTPClient:
    """Async HTTP client wrapper."""
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
        headers: Optional[Dict[str, str]] = None
    ):
        self.base_url = base_url
        self.timeout = ClientTimeout(total=timeout)
        self.max_retries = max_retries
        self.default_headers = headers or {}
        self._session: Optional[ClientSession] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def start(self):
        """Start HTTP session."""
        if not self._session:
            self._session = aiohttp.ClientSession(
                base_url=self.base_url,
                timeout=self.timeout,
                headers=self.default_headers
            )
    
    async def close(self):
        """Close HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None
    
    @property
    def session(self) -> ClientSession:
        """Get HTTP session."""
        if not self._session:
            raise RuntimeError("HTTP client not started")
        return self._session
    
    async def _request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Union[str, bytes]] = None,
        files: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic."""
        
        async def make_request():
            async with self.session.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_data,
                data=data
            ) as response:
                response.raise_for_status()
                
                content_type = response.headers.get('Content-Type', '')
                if 'application/json' in content_type:
                    return await response.json()
                else:
                    text = await response.text()
                    return {"content": text, "status": response.status}
        
        try:
            return await retry_async(
                make_request,
                max_retries=self.max_retries,
                exceptions=(aiohttp.ClientError, asyncio.TimeoutError)
            )
        except Exception as e:
            logger.error(
                "HTTP request failed",
                method=method,
                url=url,
                error=str(e)
            )
            raise
    
    async def get(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make GET request."""
        return await self._request("GET", url, headers=headers, params=params)
    
    async def post(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Union[str, bytes]] = None
    ) -> Dict[str, Any]:
        """Make POST request."""
        return await self._request(
            "POST", url, headers=headers, json_data=json_data, data=data
        )
    
    async def put(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Union[str, bytes]] = None
    ) -> Dict[str, Any]:
        """Make PUT request."""
        return await self._request(
            "PUT", url, headers=headers, json_data=json_data, data=data
        )
    
    async def patch(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        data: Optional[Union[str, bytes]] = None
    ) -> Dict[str, Any]:
        """Make PATCH request."""
        return await self._request(
            "PATCH", url, headers=headers, json_data=json_data, data=data
        )
    
    async def delete(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Make DELETE request."""
        return await self._request("DELETE", url, headers=headers, params=params)


class ServiceClient(HTTPClient):
    """HTTP client for internal service communication."""
    
    def __init__(
        self,
        service_name: str,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3
    ):
        headers = {
            "User-Agent": f"FamaGPT-{service_name}",
            "Content-Type": "application/json"
        }
        
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        super().__init__(
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            headers=headers
        )
        
        self.service_name = service_name
    
    async def health_check(self) -> bool:
        """Check service health."""
        try:
            response = await self.get("/health")
            return response.get("status") == "healthy"
        except Exception as e:
            logger.error(
                "Service health check failed",
                service=self.service_name,
                error=str(e)
            )
            return False
