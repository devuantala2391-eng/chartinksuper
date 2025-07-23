import os
import json
from pathlib import Path

# Cache storage
cache = {}

def clear_cache():
    """Clear the entire cache."""
    global cache
    cache.clear()
    print("Cache cleared successfully")

def get_cache_key(symbol, timeframe):
    """Generate a cache key for symbol and timeframe."""
    return f"{symbol}_{timeframe}"

def get_cached_data(symbol, timeframe):
    """Get cached data for a symbol and timeframe."""
    key = get_cache_key(symbol, timeframe)
    return cache.get(key)

def set_cached_data(symbol, timeframe, data):
    """Set cached data for a symbol and timeframe."""
    key = get_cache_key(symbol, timeframe)
    cache[key] = data

def remove_cached_data(symbol, timeframe=None):
    """Remove cached data for a symbol and optionally specific timeframe."""
    if timeframe:
        key = get_cache_key(symbol, timeframe)
        cache.pop(key, None)
    else:
        # Remove all entries for this symbol
        keys_to_remove = [key for key in cache.keys() if key.startswith(f"{symbol}_")]
        for key in keys_to_remove:
            cache.pop(key, None)