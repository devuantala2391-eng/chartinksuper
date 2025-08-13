import asyncio
import json
import logging
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import threading
from services.chartink_service import ChartinkService
from utils.constants import STOCK_SYMBOLS
from services.latest_day_precalculator import latest_day_precalculator
from services.database_service import db_service

logger = logging.getLogger(__name__)

class LatestCandleUpdater:
    """Service to update only the latest daily candle for each symbol."""
    
    def __init__(self):
        self.chartink_service = ChartinkService()
        self.db_path = Path(__file__).parent.parent / "db"
        self.is_running = False
        self.update_task = None
        self.lock = threading.Lock()
        self.force_run = False  # Force updates even outside market hours
        self.update_interval = 2  # Default update interval in minutes
        self.last_update_time = None  # Track last update time
        self.next_update_time = None  # Track next scheduled update
        self.last_update_stats = None  # Store last update statistics
        
    def is_market_hours(self) -> bool:
        """Check if current time is within market hours (9:15 AM to 3:30 PM IST)."""
        now = datetime.now()
        current_time = now.time()
        
        # Market hours: 9:15 AM to 3:30 PM IST
        market_open = time(9, 15)
        market_close = time(15, 30)
        
        # Skip weekends (Saturday=5, Sunday=6)
        if now.weekday() >= 5:
            return False
            
        return market_open <= current_time <= market_close
    
    async def get_latest_candle(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch only the latest candle (size=1) for a symbol."""
        try:
            # Fetch only 1 candle (today's latest)
            response_data = await self.chartink_service.fetch_stock_data(symbol, size=1)
            mapped_data = self.chartink_service._map_response_data(response_data)
            
            if mapped_data and len(mapped_data) > 0:
                return mapped_data[0]  # Return the latest candle
            return None
            
        except Exception as e:
            logger.error(f"Failed to fetch latest candle for {symbol}: {e}")
            return None
    
    async def load_existing_data(self, symbol: str) -> List[Dict[str, Any]]:
        """Load existing stock data from database or JSON file."""
        # Try database first
        if db_service.initialized:
            try:
                candles = await db_service.load_candles(symbol)
                if candles:
                    return candles
            except Exception as e:
                logger.debug(f"Database read failed for {symbol}: {e}")
        
        # Fallback to JSON file
        file_path = self.db_path / f"{symbol}.json"
        
        if not file_path.exists():
            return []
            
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load existing data for {symbol}: {e}")
            return []
    
    async def save_updated_data(self, symbol: str, data: List[Dict[str, Any]]) -> bool:
        """Save updated stock data to database and JSON file."""
        # Try database first
        if db_service.initialized:
            try:
                success = await db_service.update_candles(symbol, data)
                if success:
                    return True
            except Exception as e:
                logger.debug(f"Database save failed for {symbol}: {e}")
        
        # Fallback to JSON file
        file_path = self.db_path / f"{symbol}.json"
        
        try:
            # Ensure directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w') as f:
                json.dump(data, f)
            return True
        except Exception as e:
            logger.error(f"Failed to save data for {symbol}: {e}")
            return False
    
    def update_latest_candle_data(self, existing_data: List[Dict[str, Any]], 
                                  latest_candle: Dict[str, Any]) -> tuple:
        """
        Update the latest candle in existing data.
        Returns (updated_data, was_changed) tuple.
        """
        if not existing_data:
            # If no existing data, add the latest candle
            return [latest_candle], True
        
        # Get the timestamp of the latest candle from API
        latest_timestamp = latest_candle.get('timestamp')
        if not latest_timestamp:
            return existing_data, False
        
        # Check if the last candle in existing data is from the same day
        last_existing = existing_data[-1]
        last_timestamp = last_existing.get('timestamp')
        
        if not last_timestamp:
            # If existing data has no timestamp, append new candle
            existing_data.append(latest_candle)
            return existing_data, True
        
        # Compare timestamps to see if we need to update or append
        if latest_timestamp == last_timestamp:
            # Same timestamp - check if data has changed
            if (last_existing.get('high') != latest_candle.get('high') or
                last_existing.get('low') != latest_candle.get('low') or
                last_existing.get('open') != latest_candle.get('open') or
                last_existing.get('close') != latest_candle.get('close') or
                last_existing.get('volume') != latest_candle.get('volume')):
                
                # Data has changed, update the last candle
                existing_data[-1] = latest_candle
                return existing_data, True
            else:
                # No change needed
                return existing_data, False
        
        elif latest_timestamp > last_timestamp:
            # New day - append the new candle
            existing_data.append(latest_candle)
            return existing_data, True
        
        else:
            # Latest timestamp is older than last existing - no update needed
            return existing_data, False
    
    async def update_symbol(self, symbol: str) -> Dict[str, str]:
        """Update the latest candle for a single symbol."""
        try:
            # Get latest candle from API
            latest_candle = await self.get_latest_candle(symbol)
            if not latest_candle:
                return {symbol: "No latest candle data available"}
            
            # Load existing data
            existing_data = await self.load_existing_data(symbol)
            
            # Update with latest candle
            updated_data, was_changed = self.update_latest_candle_data(existing_data, latest_candle)
            
            if was_changed:
                # Save updated data
                if await self.save_updated_data(symbol, updated_data):
                    return {symbol: f"Updated successfully - {len(updated_data)} total candles"}
                else:
                    return {symbol: "Failed to save updated data"}
            else:
                return {symbol: "No update needed - data unchanged"}
                
        except Exception as e:
            logger.error(f"Failed to update symbol {symbol}: {e}")
            return {symbol: f"Error: {str(e)}"}
    
    async def update_all_symbols(self, symbols: Optional[List[str]] = None) -> Dict[str, str]:
        """Update latest candles for all symbols with concurrency control."""
        if symbols is None:
            symbols = STOCK_SYMBOLS
        
        logger.info(f"🚀 Starting latest candle update for {len(symbols)} symbols")
        logger.info(f"📋 Processing symbols in batches with {50} concurrent connections...")
        
        # Initialize client pool
        await self.chartink_service.initialize_client_pool()
        
        # Use semaphore to control concurrency
        semaphore = asyncio.Semaphore(50)  # Limit concurrent requests
        results = {}
        
        progress_interval = max(1, len(symbols) // 20)  # Show progress 20 times
        processed = 0
        
        async def update_with_semaphore(symbol):
            nonlocal processed
            async with semaphore:
                result = await self.update_symbol(symbol)
                processed += 1
                
                # Show progress periodically
                if processed % progress_interval == 0 or processed == len(symbols):
                    percentage = (processed / len(symbols)) * 100
                    logger.info(f"📈 Progress: {processed}/{len(symbols)} ({percentage:.1f}%) processed...")
                
                return result
        
        # Create tasks for all symbols
        tasks = [update_with_semaphore(symbol) for symbol in symbols]
        
        # Execute all tasks
        task_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect results
        for i, result in enumerate(task_results):
            if isinstance(result, dict):
                results.update(result)
            else:
                results[symbols[i]] = f"Error: {str(result)}"
        
        # Close client pool
        await self.chartink_service.close_all_clients()
        
        # Log summary
        updated_count = sum(1 for msg in results.values() if "Updated successfully" in msg)
        unchanged_count = sum(1 for msg in results.values() if "No update needed" in msg)
        error_count = sum(1 for msg in results.values() if "Error:" in msg or "Failed" in msg)
        
        logger.info(f"Update completed: {updated_count} updated, {unchanged_count} unchanged, {error_count} errors")
        
        return results
    
    async def single_update_cycle(self) -> Dict[str, str]:
        """Perform a single update cycle for all symbols."""
        if not self.is_market_hours() and not self.force_run:
            logger.info("Market is closed, skipping update cycle (use force_run=True to override)")
            return {"status": "Market closed - no update performed"}
        
        logger.info("🔄 Starting latest candle update cycle...")
        logger.info("="*60)
        start_time = datetime.now()
        
        results = await self.update_all_symbols()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Count results
        updated_count = sum(1 for msg in results.values() if "Updated successfully" in msg)
        unchanged_count = sum(1 for msg in results.values() if "No update needed" in msg)
        error_count = sum(1 for msg in results.values() if "Error:" in msg or "Failed" in msg)
        
        logger.info("="*60)
        logger.info(f"✅ Update cycle completed in {duration:.2f} seconds")
        logger.info(f"📊 Results: {updated_count} updated, {unchanged_count} unchanged, {error_count} errors")
        
        # Store update stats
        self.last_update_time = datetime.now()
        self.next_update_time = self.last_update_time + timedelta(minutes=self.update_interval)
        self.last_update_stats = {
            "total": len(results),
            "updated": updated_count,
            "unchanged": unchanged_count,
            "errors": error_count
        }
        
        # Extract symbols that were successfully updated
        updated_symbols = [
            symbol for symbol, msg in results.items() 
            if "Updated successfully" in msg
        ]
        
        logger.info(f"🔍 Candle update summary:")
        logger.info(f"📊 {len(updated_symbols)} symbols had candle updates")
        
        # Always trigger precalculation for ALL stocks after job completes
        logger.info("="*60)
        logger.info(f"🔄 Starting precalculated storage update for ALL stocks...")
        logger.info(f"📋 Processing all {len(STOCK_SYMBOLS)} symbols in precalculatedStorage")
        
        precalc_start = datetime.now()
        
        try:
            # Update precalculated storage for ALL symbols (not just updated ones)
            # This ensures all stocks get their latest indicators calculated
            precalc_results = await latest_day_precalculator.update_all_latest_precalculated(
                symbols=STOCK_SYMBOLS  # Process ALL stocks
            )
            
            precalc_end = datetime.now()
            precalc_duration = (precalc_end - precalc_start).total_seconds()
            
            # Count precalc results
            precalc_success = sum(1 for msg in precalc_results.values() if "Updated" in msg)
            precalc_errors = sum(1 for msg in precalc_results.values() if "Error" in msg)
            
            logger.info(f"✅ Precalculation completed in {precalc_duration:.2f} seconds")
            logger.info(f"📊 Precalc Results: {precalc_success} successful, {precalc_errors} errors")
            
            # Show some sample results for debugging
            if precalc_results:
                sample_results = list(precalc_results.items())[:3]
                for symbol, msg in sample_results:
                    logger.info(f"   {symbol}: {msg}")
                        
        except Exception as e:
            logger.error(f"❌ Error during precalculation: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        logger.info(f"⏰ Next update in {self.update_interval} minutes at {(datetime.now() + timedelta(minutes=self.update_interval)).strftime('%H:%M:%S')}")
        logger.info("="*60)
        
        return results
    
    async def start_periodic_updates(self, interval_minutes: int = 2, force_run: bool = False):
        """Start periodic updates every N minutes."""
        if self.is_running:
            logger.warning("Periodic updates already running")
            return
        
        self.force_run = force_run  # Set force run mode
        self.update_interval = interval_minutes  # Store interval for logging
        
        with self.lock:
            if self.is_running:
                return
            self.is_running = True
        
        logger.info(f"Starting periodic latest candle updates every {interval_minutes} minutes (force_run={force_run})")
        
        try:
            while self.is_running:
                await self.single_update_cycle()
                
                if self.is_running:
                    # Show waiting message
                    next_update_time = datetime.now() + timedelta(minutes=interval_minutes)
                    logger.info(f"⏳ Waiting {interval_minutes} minutes until next update at {next_update_time.strftime('%H:%M:%S')}...")
                    
                    # Wait for the specified interval with countdown
                    for i in range(interval_minutes * 60):
                        if not self.is_running:
                            break
                        await asyncio.sleep(1)
                        
                        # Show countdown every 30 seconds
                        if i > 0 and i % 30 == 0:
                            remaining = (interval_minutes * 60) - i
                            mins = remaining // 60
                            secs = remaining % 60
                            logger.info(f"⏰ Next update in: {mins:02d}:{secs:02d}")
                
        except asyncio.CancelledError:
            logger.info("Periodic updates cancelled")
        except Exception as e:
            logger.error(f"Error in periodic updates: {e}")
        finally:
            with self.lock:
                self.is_running = False
    
    def stop_periodic_updates(self):
        """Stop the periodic updates."""
        with self.lock:
            if self.is_running:
                self.is_running = False
                if self.update_task and not self.update_task.done():
                    self.update_task.cancel()
                logger.info("Periodic updates stopped")

# Global instance
latest_candle_updater = LatestCandleUpdater()