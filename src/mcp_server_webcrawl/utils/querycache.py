import hashlib
import time

from typing import Any, Optional

class QueryCountCache:
    """
    A cache for storing total count results from database queries.
    Only caches the count integer values, as these are reusable and light.
    """
    def __init__(self, max: int = 250, ttl: int = 900):
        """
        Initialize the query count cache.
        
        Parameters:
            max: Maximum number of entries to store in the cache
            ttl: Time-to-live for cache entries in seconds
        """
        self._cache: dict[str, int] = {}
        self._timestamps: dict[str, float] = {}
        self._max = max
        self._ttl = ttl
    
    def _hash_query(self, statement: str, params: dict[str, Any]) -> str:
        """
        Generate a hash key from a query statement and parameters.
        
        Parameters:
            statement: SQL statement
            params: Query parameters
            
        Returns:
            MD5 hash of the combined query string
        """
        query = f"{statement}:{str(params)}"
        return hashlib.md5(query.encode()).hexdigest()
    
    def get(self, statement: str, params: dict[str, Any]) -> Optional[int]:
        """
        Get a cached count result if available and not expired.
        
        Parameters:
            statement: SQL statement
            params: Query parameters
            
        Returns:
            Cached count value or None if not found or expired
        """
        key = self._hash_query(statement, params)         
        if key in self._cache:
            if time.time() - self._timestamps[key] > self._ttl:                 
                del self._cache[key]
                del self._timestamps[key]
                return None             
            return self._cache[key]         
        return None
    
    def set(self, statement: str, params: dict[str, Any], count: int) -> None:
        """
        Store a count result in the cache.
        
        Parameters:
            statement: SQL statement
            params: Query parameters
            count: Count value to cache
        """
        key = self._hash_query(statement, params)

        # if cache is full, remove oldest entry
        if len(self._cache) >= self._max and key not in self._cache:
            oldest_key = min(self._timestamps, key=lambda k: self._timestamps[k])
            del self._cache[oldest_key]
            del self._timestamps[oldest_key]         
        
        # store new entry
        self._cache[key] = count
        self._timestamps[key] = time.time()
    
    def clear(self) -> None:
        """
        Clear all entries from the cache.
        """
        self._cache.clear()
        self._timestamps.clear()