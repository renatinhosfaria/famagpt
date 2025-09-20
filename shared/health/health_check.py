"""
Sistema de health checks avançados para FamaGPT
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import asyncio
import aiohttp
import redis.asyncio as redis
from datetime import datetime, timedelta
import time

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus
    response_time_ms: Optional[float] = None
    message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class HealthChecker:
    """Sistema de verificação de saúde de componentes"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.start_time = datetime.utcnow()
        self.checks: List[ComponentHealth] = []
    
    async def check_database(self, db_url: str) -> ComponentHealth:
        """Verificar conectividade do banco de dados"""
        start = time.time()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{db_url}/health",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    response_time = (time.time() - start) * 1000
                    if response.status == 200:
                        data = await response.json()
                        return ComponentHealth(
                            name="database",
                            status=HealthStatus.HEALTHY,
                            response_time_ms=response_time,
                            metadata=data
                        )
                    else:
                        return ComponentHealth(
                            name="database",
                            status=HealthStatus.UNHEALTHY,
                            response_time_ms=response_time,
                            message=f"HTTP {response.status}"
                        )
        except asyncio.TimeoutError:
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message="Connection timeout"
            )
        except Exception as e:
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=str(e)
            )
    
    async def check_redis(self, redis_url: str) -> ComponentHealth:
        """Verificar conectividade do Redis"""
        start = time.time()
        try:
            client = redis.from_url(redis_url)
            
            # Test basic operations
            await client.ping()
            test_key = f"health_check_{int(time.time())}"
            await client.set(test_key, "test", ex=10)
            value = await client.get(test_key)
            await client.delete(test_key)
            
            response_time = (time.time() - start) * 1000
            await client.close()
            
            if value == b"test":
                return ComponentHealth(
                    name="redis",
                    status=HealthStatus.HEALTHY,
                    response_time_ms=response_time,
                    metadata={"operations_tested": ["ping", "set", "get", "delete"]}
                )
            else:
                return ComponentHealth(
                    name="redis",
                    status=HealthStatus.DEGRADED,
                    response_time_ms=response_time,
                    message="Read/write test failed"
                )
        except Exception as e:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=str(e)
            )
    
    async def check_openai(self, api_key: str) -> ComponentHealth:
        """Verificar disponibilidade da API OpenAI"""
        if not api_key:
            return ComponentHealth(
                name="openai",
                status=HealthStatus.UNHEALTHY,
                message="API key not configured"
            )
        
        start = time.time()
        try:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "FamaGPT-Health-Check/1.0"
            }
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.openai.com/v1/models",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    response_time = (time.time() - start) * 1000
                    
                    if response.status == 200:
                        data = await response.json()
                        models_count = len(data.get("data", []))
                        return ComponentHealth(
                            name="openai",
                            status=HealthStatus.HEALTHY,
                            response_time_ms=response_time,
                            metadata={"available_models": models_count}
                        )
                    elif response.status == 429:
                        return ComponentHealth(
                            name="openai",
                            status=HealthStatus.DEGRADED,
                            response_time_ms=response_time,
                            message="Rate limited"
                        )
                    else:
                        return ComponentHealth(
                            name="openai",
                            status=HealthStatus.UNHEALTHY,
                            response_time_ms=response_time,
                            message=f"HTTP {response.status}"
                        )
        except asyncio.TimeoutError:
            return ComponentHealth(
                name="openai",
                status=HealthStatus.DEGRADED,
                message="API timeout - may be slow"
            )
        except Exception as e:
            return ComponentHealth(
                name="openai",
                status=HealthStatus.DEGRADED,
                message=f"API check failed: {str(e)}"
            )
    
    async def check_service(self, name: str, url: str, timeout: int = 5) -> ComponentHealth:
        """Verificar saúde de serviço dependente"""
        start = time.time()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{url.rstrip('/')}/health",
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as response:
                    response_time = (time.time() - start) * 1000
                    
                    if response.status == 200:
                        try:
                            data = await response.json()
                            return ComponentHealth(
                                name=name,
                                status=HealthStatus.HEALTHY,
                                response_time_ms=response_time,
                                metadata=data
                            )
                        except:
                            return ComponentHealth(
                                name=name,
                                status=HealthStatus.HEALTHY,
                                response_time_ms=response_time
                            )
                    elif response.status == 503:
                        return ComponentHealth(
                            name=name,
                            status=HealthStatus.UNHEALTHY,
                            response_time_ms=response_time,
                            message="Service unavailable"
                        )
                    else:
                        return ComponentHealth(
                            name=name,
                            status=HealthStatus.DEGRADED,
                            response_time_ms=response_time,
                            message=f"HTTP {response.status}"
                        )
        except asyncio.TimeoutError:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="Connection timeout"
            )
        except Exception as e:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=str(e)
            )
    
    async def check_evolution_api(self, base_url: str, api_key: str) -> ComponentHealth:
        """Verificar saúde específica da Evolution API"""
        start = time.time()
        try:
            headers = {"apiKey": api_key} if api_key else {}
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{base_url.rstrip('/')}/manager/status",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    response_time = (time.time() - start) * 1000
                    
                    if response.status == 200:
                        data = await response.json()
                        return ComponentHealth(
                            name="evolution_api",
                            status=HealthStatus.HEALTHY,
                            response_time_ms=response_time,
                            metadata=data
                        )
                    else:
                        return ComponentHealth(
                            name="evolution_api",
                            status=HealthStatus.UNHEALTHY,
                            response_time_ms=response_time,
                            message=f"HTTP {response.status}"
                        )
        except Exception as e:
            return ComponentHealth(
                name="evolution_api",
                status=HealthStatus.UNHEALTHY,
                message=str(e)
            )
    
    async def run_all_checks(self, dependencies: Dict[str, Any]) -> Dict[str, Any]:
        """Executar todas as verificações de saúde"""
        tasks = []
        
        # Check standard dependencies
        if "database_url" in dependencies:
            tasks.append(self.check_database(dependencies["database_url"]))
        
        if "redis_url" in dependencies:
            tasks.append(self.check_redis(dependencies["redis_url"]))
        
        if "openai_key" in dependencies:
            tasks.append(self.check_openai(dependencies["openai_key"]))
        
        if "evolution_api" in dependencies:
            config = dependencies["evolution_api"]
            tasks.append(self.check_evolution_api(
                config.get("base_url", ""), 
                config.get("api_key", "")
            ))
        
        # Check other services
        for name, config in dependencies.items():
            if name not in ["database_url", "redis_url", "openai_key", "evolution_api"]:
                if isinstance(config, str):
                    # Simple URL
                    tasks.append(self.check_service(name, config))
                elif isinstance(config, dict) and "url" in config:
                    # URL with timeout
                    timeout = config.get("timeout", 5)
                    tasks.append(self.check_service(name, config["url"], timeout))
        
        # Execute all checks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        checks = {}
        overall_status = HealthStatus.HEALTHY
        total_response_time = 0
        healthy_count = 0
        
        for result in results:
            if isinstance(result, Exception):
                continue
            if isinstance(result, ComponentHealth):
                checks[result.name] = {
                    "status": result.status.value,
                    "response_time_ms": result.response_time_ms,
                    "message": result.message,
                    "metadata": result.metadata
                }
                
                # Update overall status
                if result.status == HealthStatus.UNHEALTHY:
                    overall_status = HealthStatus.UNHEALTHY
                elif result.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                    overall_status = HealthStatus.DEGRADED
                
                # Calculate average response time
                if result.response_time_ms:
                    total_response_time += result.response_time_ms
                    healthy_count += 1
        
        # Calculate metrics
        uptime_seconds = (datetime.utcnow() - self.start_time).total_seconds()
        avg_response_time = total_response_time / healthy_count if healthy_count > 0 else None
        
        return {
            "service": self.service_name,
            "status": overall_status.value,
            "uptime_seconds": uptime_seconds,
            "uptime_human": str(timedelta(seconds=int(uptime_seconds))),
            "checks": checks,
            "summary": {
                "total_checks": len(checks),
                "healthy": len([c for c in checks.values() if c["status"] == "healthy"]),
                "degraded": len([c for c in checks.values() if c["status"] == "degraded"]),
                "unhealthy": len([c for c in checks.values() if c["status"] == "unhealthy"]),
                "avg_response_time_ms": avg_response_time
            },
            "timestamp": datetime.utcnow().isoformat()
        }

# Utility functions for common health check patterns
async def simple_health_check() -> Dict[str, Any]:
    """Health check simples para endpoints básicos"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }

async def liveness_check(service_name: str, start_time: datetime) -> Dict[str, Any]:
    """Liveness check básico"""
    uptime = (datetime.utcnow() - start_time).total_seconds()
    return {
        "service": service_name,
        "status": "alive",
        "uptime_seconds": uptime,
        "timestamp": datetime.utcnow().isoformat()
    }

# Export main components
__all__ = [
    'HealthChecker',
    'HealthStatus',
    'ComponentHealth',
    'simple_health_check',
    'liveness_check'
]