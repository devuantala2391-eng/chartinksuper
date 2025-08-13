import httpx
import json
import os
from pathlib import Path
import asyncio
from typing import List, Dict, Any, Optional
import logging
import threading
from dotenv import load_dotenv
from .database_service import db_service

# Load environment variables
load_dotenv()

def get_default_size() -> int:
    """Get default size parameter from environment variables."""
    try:
        return int(os.getenv('DEFAULT_SIZE', '200'))
    except (ValueError, TypeError):
        return 200  # Fallback to 200 if env var is invalid

def get_default_candle_count() -> int:
    """Get default candle count parameter from environment variables."""
    try:
        return int(os.getenv('DEFAULT_CANDLE_COUNT', '2000'))
    except (ValueError, TypeError):
        return 2000  # Fallback to 2000 if env var is invalid

logger = logging.getLogger(__name__)

class ChartinkService:
    def __init__(self):
        self.timeout = 10.0  # Faster timeout for maximum speed
        self.max_retries = 1  # Minimal retries for speed
        # Create a shared client with optimized limits
        self.client_limits = httpx.Limits(
            max_keepalive_connections=10000,  # Even more connections!
            max_connections=None,  # Unlimited connections
            keepalive_expiry=300.0  # Longer keepalive
        )
        # Create a pool of clients for better concurrency
        self.client_pool = []
        self.pool_size = 50  # 50 shared clients
        self.pool_index = 0
        self.pool_lock = threading.Lock()  # Thread-safe access
        self.base_headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8,la;q=0.7',
            'content-type': 'application/x-www-form-urlencoded',
            'cookie': '_ga=GA1.2.827081830.1738516382; _gid=GA1.2.158232909.1738612317; XSRF-TOKEN=eyJpdiI6IjVrL2dLek8rSVE4aGFTWWllazd6cHc9PSIsInZhbHVlIjoiQmVUcmlLb0Z2dk9uYVlPeUpJL3d1OTQ0MTdvcUpWZGt6V2tEaHpEeUJidGJVOENDeFpYbnJiaVgxV3NielhMbjBGUzlTVmNuektCaHhTb0V3MFVnS1VUbWZRVCtEYXFxYlhrYzZ4eWpnY2RuZjltSlJJd1NaUkE4dlFTbVA5aDkiLCJtYWMiOiJkYzM1YzY2YTIwOTM5NTQzODNjMzNkMDZiNWMwY2NkNzc5MDQ5OTFmOGJlMTgwMzJmYjM1NDdmNTFjNzAyOGY2IiwidGFnIjoiIn0%3D; ci_session=eyJpdiI6InVrKzF5dXE4b2lzazMxU2lQWkJMN0E9PSIsInZhbHVlIjoiTzdMOHNsZDFJZ1dYd0JxT2EyQ0NVZGIvNUZUdmJsOHFtSXZuc002bnBrck5RSmVpS1NIRTZUUTZjWU9NVTNOcmM0SmtOSnF5UVI0cGVlU2VrNGJCM3Y2NkhKdTBvdWJlVEZzS3k2VDdtNGRDbzJqemo5M3gzbVFWaXEzQWFkbjAiLCJtYWMiOiI2YjYzMzI5N2UwOTZmYTM3OTNlNWMwNzk1NmFjY2E4MTdlMzQxNGVjYzIxMDUxOWE1ODkyYTg1MTM1NTU2NjJjIiwidGFnIjoiIn0%3D',
            'dnt': '1',
            'origin': 'https://chartink.com',
            'priority': 'u=1, i',
            'referer': 'https://chartink.com/screener/copy-double-volume-563',
            'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
            'x-xsrf-token': 'eyJpdiI6IjVrL2dLek8rSVE4aGFTWWllazd6cHc9PSIsInZhbHVlIjoiQmVUcmlLb0Z2dk9uYVlPeUpJL3d1OTQ0MTdvcUpWZGt6V2tEaHpEeUJidGJVOENDeFpYbnJiaVgxV3NielhMbjBGUzlTVmNuektCaHhTb0V3MFVnS1VUbWZRVCtEYXFxYlhrYzZ4eWpnY2RuZjltSlJJd1NaUkE4dlFTbVA5aDkiLCJtYWMiOiJkYzM1YzY2YTIwOTM5NTQzODNjMzNkMDZiNWMwY2NkNzc5MDQ5OTFmOGJlMTgwMzJmYjM1NDdmNTFjNzAyOGY2IiwidGFnIjoiIn0=',
        }
    
    async def initialize_client_pool(self):
        """Initialize the client pool for maximum concurrency."""
        if self.client_pool:  # Already initialized
            return
        
        for i in range(self.pool_size):
            client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=self.client_limits,
                headers=self.base_headers
            )
            self.client_pool.append(client)
    
    async def get_client(self):
        """Get a client from the pool using round-robin."""
        if not self.client_pool:
            await self.initialize_client_pool()
        
        with self.pool_lock:
            client = self.client_pool[self.pool_index % self.pool_size]
            self.pool_index += 1
        return client
    
    async def close_all_clients(self):
        """Close all clients in the pool."""
        for client in self.client_pool:
            await client.aclose()
        self.client_pool = []

    async def fetch_stock_data(self, symbol: str, size: int = None) -> Dict[str, Any]:
        """Fetch stock data from Chartink API using client pool."""
        if size is None:
            size = get_default_candle_count()
        query_string = "select high, low, open, close, volume"
        
        form_data = {
            'query': query_string,
            'use_live': '1',
            'limit': '1',
            'size': str(size),
            'widget_id': '-1',
            'end_time': '-1',
            'timeframe': 'Daily',
            'symbol': symbol,
            'scan_link': 'scanlink:b6b0c6620714e44ab63d271d0ddbd498'
        }

        # Get client from pool instead of creating new one
        client = await self.get_client()
        
        # Try once, if it fails, try again - but FAST!
        for attempt in range(self.max_retries):
            try:
                response = await client.post(
                    'https://chartink.com/oapi',
                    data=form_data
                )
                response.raise_for_status()
                return response.json()
                
            except (httpx.RequestError, httpx.HTTPStatusError) as error:
                # Check if it's a client error (4xx) vs server error (5xx)
                is_client_error = hasattr(error, 'response') and error.response and 400 <= error.response.status_code < 500
                
                if attempt == self.max_retries - 1:
                    if is_client_error:
                        # Don't log client errors (like invalid symbols) as they're expected
                        pass
                    else:
                        print(f"[ERROR] Failed to fetch {symbol} after {self.max_retries} attempts: {error}")
                    raise
                
                # Don't retry client errors, but do retry server errors
                if is_client_error:
                    raise

    async def process_single_symbol(self, symbol: str, size: int = None, progress_callback=None) -> Dict[str, str]:
        """Process a single symbol and save stock data."""
        if size is None:
            size = get_default_candle_count()
        from datetime import datetime
        symbol_start = datetime.now()
        
        # Define fallback sizes for when "Result too large" error occurs
        fallback_sizes = [10000, 5000, 2000, 1000, 500]
        current_size = size
        
        for attempt_size in [current_size] + fallback_sizes:
            try:
                # Fetch data from Chartink API
                response_data = await self.fetch_stock_data(symbol, attempt_size)
                
                # Process and map the data
                mapped_data = self._map_response_data(response_data)
                
                # Save to database
                success = await db_service.save_candles(symbol, mapped_data)
                
                if not success:
                    # Fallback to JSON file if database save fails
                    json_dir = Path(__file__).parent.parent / "db"
                    json_dir.mkdir(parents=True, exist_ok=True)
                    file_path = json_dir / f"{symbol}.json"
                    with open(file_path, 'w') as f:
                        json.dump(mapped_data, f)
                    logger.warning(f"Saved {symbol} to file due to database error")
                
                # Log if we had to use a smaller size
                if attempt_size < size:
                    print(f"[INFO] {symbol}: Fetched {len(mapped_data)} records with reduced size {attempt_size} (original: {size})")
                
                # Call progress callback if provided
                if progress_callback:
                    await progress_callback(symbol, True)
                
                return {symbol: f"Success: {len(mapped_data)} records (size: {attempt_size})"}
                
            except Exception as error:
                # Check if it's a "Result too large" error (error code 34 from libcurl)
                error_str = str(error)
                if "(34," in error_str or "Result too large" in error_str.lower():
                    # If we haven't tried all fallback sizes, continue to next smaller size
                    if attempt_size != fallback_sizes[-1]:
                        print(f"[WARN] {symbol}: Result too large with size {attempt_size}, retrying with smaller size...")
                        continue
                    else:
                        # We've tried the smallest size and still failed
                        error_msg = f"Failed: Data too large even with minimum size {attempt_size}"
                        print(f"[ERROR] {symbol}: {error_msg}")
                        
                        # Call progress callback with failure
                        if progress_callback:
                            await progress_callback(symbol, False)
                        
                        return {symbol: error_msg}
                else:
                    # For other errors, don't retry with different sizes
                    error_msg = f"Failed: {type(error).__name__}: {str(error)}"
                    
                    # Call progress callback with failure
                    if progress_callback:
                        await progress_callback(symbol, False)
                    
                    return {symbol: error_msg}

    async def process_payload(self, payload: List[List[str]], concurrent_limit: int = None, progress_callback=None, size: int = None) -> Dict[str, str]:
        """Process symbols with controlled concurrency using semaphore."""
        from datetime import datetime
        size = size or get_default_size()  # Use provided size or default from env
        
        # Extract symbols from payload
        symbols = []
        for arr in payload:
            if arr and len(arr) >= 2 and arr[1]:
                symbols.append(arr[1])
        
        if not symbols:
            return {}
        
        # Initialize client pool BEFORE processing starts
        await self.initialize_client_pool()
        
        print(f"\n[CHARTINK] Starting concurrent processing of {len(symbols)} symbols...")
        
        # Use semaphore to limit concurrent requests to pool size
        semaphore = asyncio.Semaphore(self.pool_size * 2)  # Allow 2x pool size for better throughput
        results = {}
        
        processed_count = 0
        
        async def process_symbol_with_semaphore(symbol):
            nonlocal processed_count
            async with semaphore:
                try:
                    result = await self.process_single_symbol(symbol, size, progress_callback)
                    results.update(result)
                    processed_count += 1
                    if processed_count % 50 == 0:
                        print(f"[CHARTINK] Progress: {processed_count}/{len(symbols)} symbols processed...")
                    return result
                except Exception as e:
                    processed_count += 1
                    return {symbol: f"Error: {str(e)}"}
        
        # Create tasks for ALL symbols
        tasks = [process_symbol_with_semaphore(symbol) for symbol in symbols]
        
        # Fire all requests with controlled concurrency
        start_time = asyncio.get_event_loop().time()
        
        # Use gather to run all tasks with semaphore control
        await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = asyncio.get_event_loop().time()
        
        elapsed = end_time - start_time
        rate = len(symbols) / elapsed if elapsed > 0 else 0
        
        print(f"\n[CHARTINK] Processed {len(symbols)} symbols in {elapsed:.2f} seconds ({rate:.1f} symbols/sec)")
        
        # Close all clients when done
        await self.close_all_clients()
        
        return results

    def _map_response_data(self, response_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Map the API response data to the required format."""
        group_data = response_data.get('groupData', [{}])[0].get('results', [])
        meta_data = response_data.get('metaData', [{}])[0].get('tradeTimes', [])
        
        mapped_data = []
        
        if group_data and meta_data and len(group_data) >= 5:
            highs = group_data[0].get('high', [])
            lows = group_data[1].get('low', [])
            opens = group_data[2].get('open', [])
            closes = group_data[3].get('close', [])
            volumes = group_data[4].get('volume', [])
            
            for idx, timestamp in enumerate(meta_data):
                if idx < len(highs) and idx < len(lows) and idx < len(opens) and idx < len(closes) and idx < len(volumes):
                    mapped_data.append({
                        "high": highs[idx],
                        "low": lows[idx],
                        "open": opens[idx],
                        "close": closes[idx],
                        "volume": volumes[idx],
                        "timestamp": timestamp
                    })
        
        return mapped_data