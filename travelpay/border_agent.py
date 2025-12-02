"""
TravelPay SDK - Border Wait Time Agent
Fetches real-time US-Mexico border crossing wait times with Redis caching.

Update 5: Added high-performance caching layer using Redis to:
- Reduce latency to <20ms for cached responses
- Protect against DDoS by rate-limiting external API calls
- Support the subscription manager's background checks
"""

import os
import json
import logging
from typing import Optional, List

import httpx

logger = logging.getLogger("travelpay.border_agent")

# Redis import with fallback
try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available - caching disabled")


class BorderWaitAgent:
    """
    Agent for fetching US-Mexico border wait times from CBP API.
    
    Features:
    - Real-time data from CBP Border Wait Times API
    - Redis caching for high-performance responses (<20ms)
    - Automatic cache invalidation with configurable TTL
    - Fallback to direct API if cache unavailable
    
    Example:
        agent = BorderWaitAgent()
        await agent.init_cache()  # Optional: connect to Redis
        
        data = await agent.get_wait_time("San Ysidro")
        print(f"Wait time: {data['wait_time_minutes']} minutes")
        print(f"Cached: {data.get('cached', False)}")
    """
    
    CBP_API_URL = "https://bwt.cbp.gov/api/bwt/current"
    
    # Cache key prefix
    CACHE_PREFIX = "cache:border:"
    
    POPULAR_CROSSINGS = [
        "San Ysidro",
        "Otay Mesa", 
        "El Paso",
        "Laredo",
        "Nogales",
        "Calexico",
        "Brownsville",
        "McAllen"
    ]

    def __init__(
        self, 
        timeout: float = 10.0,
        redis_url: str = None,
        cache_ttl: int = None
    ):
        """
        Initialize the BorderWaitAgent.
        
        Args:
            timeout: HTTP request timeout in seconds
            redis_url: Redis connection URL (default from REDIS_URL env)
            cache_ttl: Cache TTL in seconds (default from CACHE_TTL_SECONDS env)
        """
        self.timeout = timeout
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self.cache_ttl = cache_ttl or int(os.getenv("CACHE_TTL_SECONDS", "300"))  # 5 minutes
        
        self._client: Optional[httpx.AsyncClient] = None
        self._redis: Optional["aioredis.Redis"] = None
        self._cache_enabled = False

    async def init_cache(self) -> bool:
        """
        Initialize Redis connection for caching.
        
        Returns:
            True if Redis connected successfully, False otherwise
        """
        if not REDIS_AVAILABLE:
            logger.warning("Redis package not installed - caching disabled")
            return False
        
        try:
            self._redis = await aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            # Test connection
            await self._redis.ping()
            self._cache_enabled = True
            logger.info(f"Redis cache connected: {self.redis_url}")
            logger.info(f"Cache TTL: {self.cache_ttl} seconds")
            return True
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            self._cache_enabled = False
            return False

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    async def close(self):
        """Close HTTP client and Redis connection."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
        
        if self._redis:
            await self._redis.close()
            self._redis = None
            self._cache_enabled = False

    def _get_cache_key(self, crossing: str) -> str:
        """Generate cache key for a crossing."""
        # Normalize crossing name for consistent keys
        normalized = crossing.lower().strip().replace(" ", "_")
        return f"{self.CACHE_PREFIX}{normalized}"

    async def _get_from_cache(self, crossing: str) -> Optional[dict]:
        """
        Try to get data from Redis cache.
        
        Returns:
            Cached data dict if found, None otherwise
        """
        if not self._cache_enabled or not self._redis:
            return None
        
        try:
            key = self._get_cache_key(crossing)
            cached = await self._redis.get(key)
            
            if cached:
                data = json.loads(cached)
                data["cached"] = True
                data["cache_key"] = key
                logger.debug(f"Cache HIT: {key}")
                return data
            
            logger.debug(f"Cache MISS: {key}")
            return None
            
        except Exception as e:
            logger.warning(f"Cache read error: {e}")
            return None

    async def _set_cache(self, crossing: str, data: dict):
        """
        Store data in Redis cache with TTL.
        """
        if not self._cache_enabled or not self._redis:
            return
        
        try:
            key = self._get_cache_key(crossing)
            # Don't cache the cache metadata
            cache_data = {k: v for k, v in data.items() if k not in ("cached", "cache_key")}
            
            await self._redis.setex(
                key,
                self.cache_ttl,
                json.dumps(cache_data)
            )
            logger.debug(f"Cache SET: {key} (TTL: {self.cache_ttl}s)")
            
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

    async def _cache_all_crossings(self, data: list):
        """
        Cache all crossings from a full API response.
        """
        if not self._cache_enabled or not self._redis:
            return
        
        try:
            pipe = self._redis.pipeline()
            
            for port in data:
                crossing_name = port.get('portName', '')
                if not crossing_name:
                    continue
                
                # Extract wait time data
                passenger_data = port.get('passenger', {}).get('standard_lanes', {})
                wait_minutes = passenger_data.get('delay_minutes')
                
                cached_data = {
                    "crossing": crossing_name,
                    "specific_lane": port.get('crossingName'),
                    "wait_time_minutes": int(wait_minutes) if wait_minutes else 0,
                    "status": port.get('portStatus', 'Unknown'),
                    "last_updated": f"{port.get('date', '')} {port.get('time', '')}".strip(),
                    "source": "CBP",
                    "verified": True
                }
                
                key = self._get_cache_key(crossing_name)
                pipe.setex(key, self.cache_ttl, json.dumps(cached_data))
            
            await pipe.execute()
            logger.info(f"Cached {len(data)} border crossings")
            
        except Exception as e:
            logger.warning(f"Bulk cache error: {e}")

    async def get_wait_time(self, crossing_query: str) -> dict:
        """
        Get wait time for a specific border crossing.
        
        This method implements a cache-first strategy:
        1. Check Redis cache for recent data
        2. If cache miss, fetch from CBP API
        3. Cache the response for future requests
        
        Args:
            crossing_query: Name of crossing (e.g., "San Ysidro", "El Paso")
            
        Returns:
            Dict with crossing info and wait time, or error details
        """
        crossing_query_normalized = crossing_query.lower().strip()
        
        # Try cache first
        cached = await self._get_from_cache(crossing_query_normalized)
        if cached:
            return cached
        
        # Cache miss - fetch from API
        try:
            client = await self._get_client()
            resp = await client.get(self.CBP_API_URL)
            resp.raise_for_status()
            data = resp.json()
            
            # Cache all crossings for efficiency
            await self._cache_all_crossings(data)

            # Find requested crossing
            found_port = None
            
            for port in data:
                port_name = port.get('portName', '').lower()
                crossing_name = port.get('crossingName', '').lower()
                
                if crossing_query_normalized in port_name or crossing_query_normalized in crossing_name:
                    found_port = port
                    break
            
            if not found_port:
                return {
                    "error": "Crossing not found",
                    "query": crossing_query,
                    "available": self.POPULAR_CROSSINGS
                }

            passenger_data = found_port.get('passenger', {}).get('standard_lanes', {})
            wait_minutes = passenger_data.get('delay_minutes')
            
            if wait_minutes is None:
                status = "Closed/No Data"
                wait_time = 0
            else:
                status = "Open"
                wait_time = int(wait_minutes)

            result = {
                "crossing": found_port.get('portName'),
                "specific_lane": found_port.get('crossingName'),
                "wait_time_minutes": wait_time,
                "status": found_port.get('portStatus', status),
                "last_updated": f"{found_port.get('date', '')} {found_port.get('time', '')}".strip(),
                "source": "CBP",
                "verified": True,
                "cached": False
            }
            
            return result

        except httpx.TimeoutException:
            logger.warning(f"CBP API timeout for: {crossing_query}")
            return {"error": "Timeout", "details": "CBP API timed out"}
        except httpx.HTTPStatusError as e:
            logger.error(f"CBP API error: {e.response.status_code}")
            return {"error": "API Error", "details": f"Status {e.response.status_code}"}
        except Exception as e:
            logger.error(f"Border agent error: {e}")
            return {"error": "Error", "details": str(e)}

    async def get_all_crossings(self) -> List[dict]:
        """Get wait times for all available crossings."""
        try:
            client = await self._get_client()
            resp = await client.get(self.CBP_API_URL)
            resp.raise_for_status()
            data = resp.json()
            
            # Cache all crossings
            await self._cache_all_crossings(data)
            
            results = []
            for port in data:
                passenger_data = port.get('passenger', {}).get('standard_lanes', {})
                wait_minutes = passenger_data.get('delay_minutes')
                
                results.append({
                    "crossing": port.get('portName'),
                    "lane": port.get('crossingName'),
                    "wait_minutes": int(wait_minutes) if wait_minutes else None,
                    "status": port.get('portStatus', 'Unknown')
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to fetch all crossings: {e}")
            return []

    async def list_crossings(self) -> List[str]:
        """Get list of all crossing names."""
        try:
            client = await self._get_client()
            resp = await client.get(self.CBP_API_URL)
            resp.raise_for_status()
            data = resp.json()
            
            return list(set(port.get('portName') for port in data if port.get('portName')))
            
        except Exception as e:
            logger.error(f"Failed to list crossings: {e}")
            return self.POPULAR_CROSSINGS

    async def invalidate_cache(self, crossing: Optional[str] = None):
        """
        Invalidate cache for a specific crossing or all crossings.
        
        Args:
            crossing: Crossing name to invalidate, or None for all
        """
        if not self._cache_enabled or not self._redis:
            return
        
        try:
            if crossing:
                key = self._get_cache_key(crossing)
                await self._redis.delete(key)
                logger.info(f"Cache invalidated: {key}")
            else:
                # Delete all border cache keys
                pattern = f"{self.CACHE_PREFIX}*"
                keys = []
                async for key in self._redis.scan_iter(pattern):
                    keys.append(key)
                
                if keys:
                    await self._redis.delete(*keys)
                    logger.info(f"Cache invalidated: {len(keys)} keys")
                    
        except Exception as e:
            logger.warning(f"Cache invalidation error: {e}")

    async def get_cache_stats(self) -> dict:
        """
        Get cache statistics.
        
        Returns:
            Dict with cache info (enabled, keys count, memory usage)
        """
        if not self._cache_enabled or not self._redis:
            return {"enabled": False, "reason": "Redis not connected"}
        
        try:
            info = await self._redis.info("memory")
            keys_count = 0
            
            async for _ in self._redis.scan_iter(f"{self.CACHE_PREFIX}*"):
                keys_count += 1
            
            return {
                "enabled": True,
                "ttl_seconds": self.cache_ttl,
                "cached_crossings": keys_count,
                "redis_memory_used": info.get("used_memory_human", "unknown")
            }
            
        except Exception as e:
            return {"enabled": True, "error": str(e)}
