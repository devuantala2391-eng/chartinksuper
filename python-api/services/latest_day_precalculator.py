import json
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging
import concurrent.futures
import multiprocessing
import time
from utils.constants import STOCK_SYMBOLS

logger = logging.getLogger(__name__)

# Performance configuration
PERFORMANCE_CONFIG = {
    "max_cpu_workers": max(4, multiprocessing.cpu_count() - 1),  # Use all CPUs except one
    "batch_size": 100,
    "file_io_workers": 32
}

class LatestDayPrecalculator:
    """Service to update precalculated storage for only the latest day using existing logic."""
    
    def __init__(self):
        self.db_path = Path(__file__).parent.parent.parent / "db"
        self.precalc_path = Path(__file__).parent.parent.parent / "precalculatedStorage"
        self.indicators_config_path = Path(__file__).parent.parent / "precalculatedIndicators.json"
        
        # Ensure precalculatedStorage directory exists
        self.precalc_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 Precalculated storage path: {self.precalc_path.absolute()}")
        
    def load_indicators_config(self) -> List[Dict[str, Any]]:
        """Load the precalculated indicators configuration."""
        try:
            if self.indicators_config_path.exists():
                with open(self.indicators_config_path, 'r') as f:
                    data = json.load(f)
                    # If it's the full config object, extract indicators
                    if isinstance(data, dict) and 'indicators' in data:
                        return data['indicators']
                    # If it's already a list of indicators
                    elif isinstance(data, list):
                        return data
                    return []
            else:
                logger.warning(f"Indicators config not found at {self.indicators_config_path}")
                return []
        except Exception as e:
            logger.error(f"Failed to load indicators config: {e}")
            return []
    
    def prepare_stock_batch(self, symbols: List[str], indicators: List[Dict[str, Any]]) -> List[tuple]:
        """Prepare batch of stocks for processing."""
        batch_data = []
        timeframes = list(set(ind.get('timeframe', 'daily') for ind in indicators))
        
        for symbol in symbols:
            stock_file = self.db_path / f"{symbol}.json"
            if stock_file.exists():
                try:
                    with open(stock_file, 'r') as f:
                        stock_data = json.load(f)
                    if stock_data:
                        batch_data.append((symbol, stock_data, indicators, timeframes))
                except Exception as e:
                    logger.error(f"Error loading {symbol}: {e}")
        
        return batch_data
    
    async def update_latest_day_precalculated(self, symbol: str) -> Dict[str, str]:
        """Update precalculated storage for only the latest day."""
        try:
            # Load indicators configuration
            indicators = self.load_indicators_config()
            if not indicators:
                logger.warning(f"No indicators configured for {symbol}")
                return {symbol: "No indicators configured"}
            
            # Process the stock using existing logic
            stock, result_data, success, error_msg = self.process_single_stock_latest(symbol, indicators)
            
            if not success:
                return {symbol: f"Failed: {error_msg}"}
            
            if result_data and 'data' in result_data:
                # The result contains all processed data
                # We only need to update/append the latest candle
                all_candles = result_data['data']
                
                if not all_candles:
                    return {symbol: "No processed data"}
                
                # Get the latest candle
                latest_candle = all_candles[-1]
                
                # Load existing precalculated data
                precalc_file = self.precalc_path / f"{symbol}_piped.json"
                existing_data = []
                
                if precalc_file.exists():
                    try:
                        with open(precalc_file, 'r') as f:
                            data = json.load(f)
                            if isinstance(data, dict) and 'data' in data:
                                existing_data = data['data']
                            elif isinstance(data, list):
                                existing_data = data
                    except Exception as e:
                        logger.error(f"Error loading existing data for {symbol}: {e}")
                
                # Update or append the latest candle
                latest_timestamp = latest_candle.get('timestamp')
                updated = False
                
                for i, candle in enumerate(existing_data):
                    if candle.get('timestamp') == latest_timestamp:
                        # Update existing candle
                        existing_data[i] = latest_candle
                        updated = True
                        break
                
                if not updated:
                    # Append new candle
                    existing_data.append(latest_candle)
                
                # Keep only last 365 days if needed
                if len(existing_data) > 365:
                    existing_data = existing_data[-365:]
                
                # Save in the same format as the main precalculate function
                output_data = {
                    "symbol": symbol,
                    "data": existing_data
                }
                
                # Write to file
                with open(precalc_file, 'w') as f:
                    json.dump(output_data, f)
                
                return {symbol: f"Updated successfully - {len(existing_data)} candles"}
            else:
                return {symbol: "No data in result"}
                
        except Exception as e:
            logger.error(f"Failed to update precalculated for {symbol}: {e}")
            return {symbol: f"Error: {str(e)}"}
    
    async def update_all_latest_precalculated(self, 
                                            symbols: Optional[List[str]] = None,
                                            updated_symbols: Optional[List[str]] = None) -> Dict[str, str]:
        """Update latest day precalculated for multiple symbols using MAXIMUM PERFORMANCE."""
        # Use updated_symbols if provided, otherwise use all symbols
        if updated_symbols:
            symbols = updated_symbols
        elif symbols is None:
            symbols = STOCK_SYMBOLS
        
        logger.info(f"📊 HIGH-PERFORMANCE Precalculation: {len(symbols)} symbols with {PERFORMANCE_CONFIG['max_cpu_workers']} CPU workers")
        start_time = time.time()
        
        try:
            # Load indicators configuration once
            indicators = self.load_indicators_config()
            if not indicators:
                logger.error("No indicators configured")
                return {symbol: "No indicators configured" for symbol in symbols}
            
            # Import processing function
            import sys
            sys.path.append(str(Path(__file__).parent.parent))
            from main import process_stock_batch_cpu_intensive
            
            # Phase 1: Load all stock data in parallel
            logger.info(f"📂 Loading stock data for {len(symbols)} symbols...")
            stock_data_map = {}
            
            # Load files in batches with ThreadPoolExecutor
            for i in range(0, len(symbols), PERFORMANCE_CONFIG['batch_size']):
                batch_symbols = symbols[i:i + PERFORMANCE_CONFIG['batch_size']]
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=PERFORMANCE_CONFIG['file_io_workers']) as executor:
                    futures = []
                    for symbol in batch_symbols:
                        future = executor.submit(self._load_stock_data, symbol)
                        futures.append((symbol, future))
                    
                    for symbol, future in futures:
                        try:
                            data = future.result()
                            if data:
                                stock_data_map[symbol] = data
                        except Exception as e:
                            logger.error(f"Failed to load {symbol}: {e}")
            
            # Prepare data for CPU-intensive processing
            timeframes = list(set(ind.get('timeframe', 'daily') for ind in indicators))
            valid_stocks = [(stock, stock_data_map[stock], indicators, timeframes) 
                           for stock in symbols if stock in stock_data_map]
            
            if not valid_stocks:
                return {symbol: "No valid data" for symbol in symbols}
            
            # Phase 2: Process using ProcessPoolExecutor for MAXIMUM CPU usage
            logger.info(f"🚀 Processing {len(valid_stocks)} stocks with {PERFORMANCE_CONFIG['max_cpu_workers']} CPU workers")
            
            # Split into optimal chunks
            chunk_size = max(5, len(valid_stocks) // (PERFORMANCE_CONFIG['max_cpu_workers'] * 3))
            chunks = [valid_stocks[i:i + chunk_size] for i in range(0, len(valid_stocks), chunk_size)]
            
            all_results = []
            processed_count = 0
            
            # Process chunks in parallel using ProcessPoolExecutor
            with concurrent.futures.ProcessPoolExecutor(max_workers=PERFORMANCE_CONFIG['max_cpu_workers']) as cpu_executor:
                loop = asyncio.get_event_loop()
                chunk_futures = []
                
                for chunk in chunks:
                    future = loop.run_in_executor(cpu_executor, process_stock_batch_cpu_intensive, chunk)
                    chunk_futures.append(future)
                
                # Process results as they complete
                for future in asyncio.as_completed(chunk_futures):
                    chunk_results = await future
                    all_results.extend(chunk_results)
                    
                    processed_count += len(chunk_results)
                    percentage = (processed_count / len(valid_stocks)) * 100
                    logger.info(f"📈 Processing progress: {processed_count}/{len(valid_stocks)} ({percentage:.1f}%)")
            
            # Phase 3: Update precalculated files in parallel
            logger.info(f"💾 Updating precalculated storage files...")
            
            # Prepare update data
            update_tasks = []
            for stock, result_data, success, error_msg in all_results:
                if success and result_data and 'data' in result_data:
                    update_tasks.append((stock, result_data['data']))
            
            # Update files in parallel batches
            update_results = {}
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=PERFORMANCE_CONFIG['file_io_workers']) as write_executor:
                # Split updates into batches
                update_chunks = [update_tasks[i:i + PERFORMANCE_CONFIG['batch_size']] 
                               for i in range(0, len(update_tasks), PERFORMANCE_CONFIG['batch_size'])]
                
                for chunk in update_chunks:
                    futures = []
                    for stock, all_candles in chunk:
                        future = write_executor.submit(self._update_precalc_file, stock, all_candles)
                        futures.append((stock, future))
                    
                    for stock, future in futures:
                        try:
                            result = future.result()
                            update_results[stock] = result
                        except Exception as e:
                            update_results[stock] = f"Error: {str(e)}"
            
            # Add failed stocks to results
            for stock in symbols:
                if stock not in update_results:
                    update_results[stock] = "Failed to process"
            
            # Log summary
            end_time = time.time()
            duration = end_time - start_time
            
            success_count = sum(1 for msg in update_results.values() if "successfully" in msg)
            error_count = len(update_results) - success_count
            
            logger.info(f"✅ HIGH-PERFORMANCE update complete in {duration:.2f}s")
            logger.info(f"📊 Rate: {len(symbols) / duration:.1f} stocks/sec")
            logger.info(f"📊 Results: {success_count} successful, {error_count} errors")
            
            return update_results
            
        except Exception as e:
            logger.error(f"Critical error in precalculation: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {symbol: f"Critical error: {str(e)}" for symbol in symbols}
    
    def _load_stock_data(self, symbol: str) -> Optional[List[Dict]]:
        """Helper to load stock data from file."""
        try:
            stock_file = self.db_path / f"{symbol}.json"
            if stock_file.exists():
                with open(stock_file, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {symbol}: {e}")
        return None
    
    def _update_precalc_file(self, symbol: str, all_candles: List[Dict]) -> str:
        """Helper to update precalculated file with latest candle."""
        try:
            if not all_candles:
                return "No candle data"
            
            # Get the latest candle
            latest_candle = all_candles[-1]
            
            # Load existing data
            precalc_file = self.precalc_path / f"{symbol}_piped.json"
            existing_data = []
            
            if precalc_file.exists():
                try:
                    with open(precalc_file, 'r') as f:
                        data = json.load(f)
                        if isinstance(data, dict) and 'data' in data:
                            existing_data = data['data']
                        elif isinstance(data, list):
                            existing_data = data
                except Exception:
                    pass
            
            # Update or append latest candle
            latest_timestamp = latest_candle.get('timestamp')
            updated = False
            
            for i, candle in enumerate(existing_data):
                if candle.get('timestamp') == latest_timestamp:
                    existing_data[i] = latest_candle
                    updated = True
                    break
            
            if not updated:
                existing_data.append(latest_candle)
            
            # Keep only last 365 days
            if len(existing_data) > 365:
                existing_data = existing_data[-365:]
            
            # Save in same format
            output_data = {
                "symbol": symbol,
                "data": existing_data
            }
            
            with open(precalc_file, 'w') as f:
                json.dump(output_data, f)
            
            return f"Updated successfully - {len(existing_data)} candles"
            
        except Exception as e:
            return f"Error: {str(e)}"

# Global instance
latest_day_precalculator = LatestDayPrecalculator()