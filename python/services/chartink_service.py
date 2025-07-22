import httpx
import json
import os
from pathlib import Path
import asyncio
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class ChartinkService:
    def __init__(self):
        self.timeout = 30.0
        self.max_retries = 2
        # Create a shared client with optimized limits
        self.client_limits = httpx.Limits(
            max_keepalive_connections=5000,
            max_connections=None,
            keepalive_expiry=60.0
        )
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
        # Create shared client instance
        self.client = None

    async def get_client(self):
        """Get or create shared HTTP client."""
        if self.client is None:
            self.client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=self.client_limits
                # http2=True removed - requires additional package
            )
        return self.client

    async def close(self):
        """Close the shared client."""
        if self.client:
            await self.client.aclose()
            self.client = None

    async def fetch_stock_data(self, symbol: str, size: int = 20000) -> Dict[str, Any]:
        """Fetch stock data from Chartink API - FAST VERSION."""
        print(f"[FETCH] Starting fetch for {symbol}")
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

        client = await self.get_client()
        
        # Try once, if it fails, try again - but FAST!
        for attempt in range(self.max_retries):
            try:
                response = await client.post(
                    'https://chartink.com/oapi',
                    headers=self.base_headers,
                    data=form_data
                )
                response.raise_for_status()
                data = response.json()
                print(f"[FETCH] SUCCESS: Successfully fetched data for {symbol}")
                return data
                    
            except (httpx.RequestError, httpx.HTTPStatusError) as error:
                print(f"[FETCH] ERROR: Error fetching {symbol} (attempt {attempt + 1}/{self.max_retries}): {error}")
                if attempt == self.max_retries - 1:
                    logger.error(f"Failed {symbol}: {error}")
                    raise
                # Minimal retry delay - just 0.1 seconds
                await asyncio.sleep(0.1)

    async def process_single_symbol(self, symbol: str, size: int = 2000, progress_callback=None) -> Dict[str, str]:
        """Process a single symbol and save stock data."""
        from datetime import datetime
        try:
            symbol_start = datetime.now()
            print(f"\n[PROCESS SYMBOL] {symbol_start.strftime('%H:%M:%S.%f')[:-3]} - Starting {symbol}")
            logger.info(f"Processing symbol: {symbol}")
            
            # Ensure the directory exists
            json_dir = Path("db")
            json_dir.mkdir(parents=True, exist_ok=True)
            print(f"[PROCESS SYMBOL] DB directory ensured: {json_dir.absolute()}")
            logger.info(f"DB directory path: {json_dir.absolute()}")
            
            # Remove existing file if it exists
            file_path = json_dir / f"{symbol}.json"
            if file_path.exists():
                file_path.unlink()
            
            # Fetch data from Chartink API
            print(f"[PROCESS SYMBOL] Fetching data for {symbol}...")
            response_data = await self.fetch_stock_data(symbol, size * 10)
            print(f"[PROCESS SYMBOL] Got response data for {symbol}")
            logger.info(f"Fetched data for {symbol}")
            
            # Process and map the data
            mapped_data = self._map_response_data(response_data)
            print(f"[PROCESS SYMBOL] Mapped {len(mapped_data)} records for {symbol}")
            logger.info(f"Mapped {len(mapped_data)} records for {symbol}")
            
            # Save to JSON file
            print(f"[PROCESS SYMBOL] Writing to file: {file_path.absolute()}")
            with open(file_path, 'w') as f:
                json.dump(mapped_data, f)
            
            # Verify file was written
            if file_path.exists():
                file_size = file_path.stat().st_size
                print(f"[PROCESS SYMBOL] SUCCESS: File written successfully: {file_path.name} ({file_size} bytes)")
                logger.info(f"File written: {file_path.name} ({file_size} bytes)")
            else:
                print(f"[PROCESS SYMBOL] ERROR: File not found after writing: {file_path}")
                logger.error(f"File not found after writing: {file_path}")
            
            # Call progress callback if provided
            if progress_callback:
                await progress_callback(symbol, True)
            
            symbol_end = datetime.now()
            process_time = (symbol_end - symbol_start).total_seconds()
            success_msg = f"Success: {len(mapped_data)} records in {process_time:.2f}s"
            print(f"[PROCESS SYMBOL] {symbol_end.strftime('%H:%M:%S.%f')[:-3]} - {symbol}: {success_msg}")
            return {symbol: success_msg}
            
        except Exception as error:
            error_msg = f"{symbol}: {type(error).__name__}: {str(error)}"
            logger.error(f"Failed to process {error_msg}")
            
            # Log first few errors in detail
            if hasattr(self, '_error_count'):
                self._error_count += 1
            else:
                self._error_count = 1
            
            if self._error_count <= 5:
                logger.error(f"Detailed error for {symbol}:", exc_info=True)
            
            # Call progress callback with failure
            if progress_callback:
                await progress_callback(symbol, False)
            
            return {symbol: error_msg}

    async def process_payload(self, payload: List[List[str]], concurrent_limit: int = None, progress_callback=None) -> Dict[str, str]:
        """Process ALL symbols at MAXIMUM SPEED - NO LIMITS!"""
        from datetime import datetime
        size = 2000
        
        # Extract symbols from payload
        symbols = []
        for arr in payload:
            if arr and len(arr) >= 2 and arr[1]:
                symbols.append(arr[1])
        
        if not symbols:
            return {}
        
        service_start = datetime.now()
        logger.info(f"Processing {len(symbols)} symbols with unlimited concurrency")
        print(f"\n[CHARTINK SERVICE] {service_start.strftime('%H:%M:%S.%f')[:-3]} - Starting to process {len(symbols)} symbols")
        print(f"[CHARTINK SERVICE] Using unlimited concurrent requests")
        
        # Process ALL symbols at once - no batching, no limits!
        results = {}
        
        async def process_symbol_fast(symbol):
            result = await self.process_single_symbol(symbol, size, progress_callback)
            results.update(result)
            return result
        
        # Create tasks for ALL symbols at once
        tasks = [process_symbol_fast(symbol) for symbol in symbols]
        
        # Fire all requests simultaneously!
        start_time = asyncio.get_event_loop().time()
        
        # Use gather to run all tasks concurrently
        await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = asyncio.get_event_loop().time()
        
        elapsed = end_time - start_time
        rate = len(symbols) / elapsed if elapsed > 0 else 0
        
        service_end = datetime.now()
        print(f"\n[CHARTINK SERVICE] {service_end.strftime('%H:%M:%S.%f')[:-3]} - Processing completed")
        print(f"[CHARTINK SERVICE] Processed {len(symbols)} symbols in {elapsed:.2f} seconds")
        print(f"[CHARTINK SERVICE] Rate: {rate:.1f} symbols/second")
        logger.info(f"Bulk processing completed in {elapsed:.2f} seconds ({rate:.1f} symbols/sec)")
        
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