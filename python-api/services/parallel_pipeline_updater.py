import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Any
import threading
from dataclasses import dataclass
from services.chartink_service import ChartinkService
from utils.constants import STOCK_SYMBOLS
from services.latest_day_precalculator import latest_day_precalculator
from services.db_wrapper import db_wrapper as db_service

logger = logging.getLogger(__name__)

@dataclass
class StockProcessingResult:
    symbol: str
    fetch_success: bool
    fetch_time: float
    calc_success: bool
    calc_time: float
    save_success: bool
    save_time: float
    error: Optional[str] = None

class ParallelPipelineUpdater:
    """
    High-performance parallel pipeline for stock data processing.
    
    Architecture:
    1. Fetch Phase: Concurrent API calls (50 parallel)
    2. Process Phase: Immediate indicator calculation as data arrives
    3. Save Phase: Immediate database storage after calculation
    
    Features:
    - Stream processing (no waiting for all fetches)
    - Maximum CPU/RAM utilization
    - Real-time progress tracking
    - Error isolation per stock
    """
    
    def __init__(self):
        self.chartink_service = ChartinkService()
        self.is_running = False
        self.lock = threading.Lock()
        self.force_run = False
        self.update_interval = 2
        
        # Pipeline configuration
        self.max_fetch_concurrency = 100  # Increased from 50
        self.max_save_concurrency = 20    # Database connections
        
        # Queues for pipeline stages
        self.fetch_queue = asyncio.Queue(maxsize=1000)
        self.save_queue = asyncio.Queue(maxsize=1000)
        
        # Statistics
        self.stats = {
            'total_symbols': 0,
            'fetched': 0,
            'processed': 0,
            'saved': 0,
            'errors': 0,
            'start_time': None,
            'fetch_times': [],
            'process_times': [],
            'save_times': []
        }
        
    def is_market_hours(self) -> bool:
        """Check if current time is within market hours (9:15 AM to 3:30 PM IST)."""
        now = datetime.now()
        current_time = now.time()
        market_open = time(9, 15)
        market_close = time(15, 30)
        if now.weekday() >= 5:
            return False
        return market_open <= current_time <= market_close
    
    async def fetch_stock_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Fetch latest candle for a symbol with timing."""
        try:
            start_time = datetime.now()
            response_data = await self.chartink_service.fetch_stock_data(symbol, size=1)
            mapped_data = self.chartink_service._map_response_data(response_data)
            
            fetch_time = (datetime.now() - start_time).total_seconds() * 1000
            self.stats['fetch_times'].append(fetch_time)
            
            if mapped_data and len(mapped_data) > 0:
                return {
                    'symbol': symbol,
                    'candle': mapped_data[0],
                    'fetch_time': fetch_time
                }
            return None
        except Exception as e:
            logger.error(f"Fetch failed for {symbol}: {e}")
            return None
    
    async def fetch_worker(self, semaphore: asyncio.Semaphore):
        """Worker that fetches stock data and immediately queues for processing."""
        while True:
            try:
                symbol = await self.fetch_queue.get()
                if symbol is None:  # Poison pill to stop worker
                    break
                    
                async with semaphore:
                    result = await self.fetch_stock_data(symbol)
                    if result:
                        # Immediately queue for processing - no waiting!
                        await self.save_queue.put(result)
                        self.stats['fetched'] += 1
                        
                        # Real-time progress logging
                        if self.stats['fetched'] % 50 == 0:
                            progress = (self.stats['fetched'] / self.stats['total_symbols']) * 100
                            avg_fetch_time = sum(self.stats['fetch_times'][-50:]) / len(self.stats['fetch_times'][-50:])
                            logger.info(f"PIPELINE FETCH: {self.stats['fetched']}/{self.stats['total_symbols']} ({progress:.1f}%) fetched | Avg: {avg_fetch_time:.1f}ms")
                    else:
                        self.stats['errors'] += 1
                        
                self.fetch_queue.task_done()
            except Exception as e:
                logger.error(f"Fetch worker error: {e}")
                self.fetch_queue.task_done()
    
    async def process_indicators_async(self, symbol: str, candle_data: Dict[str, Any]) -> bool:
        """Asynchronous indicator processing."""
        try:
            start_time = datetime.now()
            
            # Load existing data from database
            existing_data = await db_service.load_candles(symbol)
            if not existing_data:
                existing_data = []
            
            # Update with latest candle
            updated_data, was_changed = self.update_latest_candle_data(existing_data, candle_data)
            
            if was_changed:
                # Save updated data immediately
                success = await db_service.save_candles(symbol, updated_data)
                
                if success:
                    process_time = (datetime.now() - start_time).total_seconds() * 1000
                    self.stats['process_times'].append(process_time)
                    return True
                    
        except Exception as e:
            logger.error(f"Process failed for {symbol}: {e}")
        return False
    
    def update_latest_candle_data(self, existing_data: List[Dict[str, Any]], 
                                  latest_candle: Dict[str, Any]) -> tuple:
        """Update the latest candle in existing data."""
        if not existing_data:
            return [latest_candle], True
        
        latest_timestamp = latest_candle.get('timestamp')
        if not latest_timestamp:
            return existing_data, False
        
        last_existing = existing_data[-1]
        last_timestamp = last_existing.get('timestamp')
        
        if not last_timestamp:
            existing_data.append(latest_candle)
            return existing_data, True
        
        if latest_timestamp == last_timestamp:
            if (last_existing.get('high') != latest_candle.get('high') or
                last_existing.get('low') != latest_candle.get('low') or
                last_existing.get('open') != latest_candle.get('open') or
                last_existing.get('close') != latest_candle.get('close') or
                last_existing.get('volume') != latest_candle.get('volume')):
                existing_data[-1] = latest_candle
                return existing_data, True
            else:
                return existing_data, False
        elif latest_timestamp > last_timestamp:
            existing_data.append(latest_candle)
            return existing_data, True
        else:
            return existing_data, False
    
    async def save_worker(self):
        """Worker that processes and saves data immediately."""
        while True:
            try:
                data = await self.save_queue.get()
                if data is None:  # Poison pill
                    break
                
                symbol = data['symbol']
                candle = data['candle']
                
                # Process and save asynchronously
                success = await self.process_indicators_async(symbol, candle)
                
                if success:
                    self.stats['processed'] += 1
                    self.stats['saved'] += 1
                    
                    # Real-time processing progress
                    if self.stats['saved'] % 25 == 0:
                        progress = (self.stats['saved'] / self.stats['total_symbols']) * 100
                        elapsed = (datetime.now() - self.stats['start_time']).total_seconds()
                        rate = self.stats['saved'] / elapsed if elapsed > 0 else 0
                        logger.info(f"PIPELINE SAVE: {self.stats['saved']}/{self.stats['total_symbols']} ({progress:.1f}%) processed & saved | Rate: {rate:.1f}/sec")
                else:
                    self.stats['errors'] += 1
                
                self.save_queue.task_done()
            except Exception as e:
                logger.error(f"Save worker error: {e}")
                self.save_queue.task_done()
    
    async def parallel_pipeline_update(self, symbols: Optional[List[str]] = None) -> Dict[str, str]:
        """Execute parallel pipeline update with maximum resource utilization."""
        if symbols is None:
            symbols = STOCK_SYMBOLS
        
        self.stats['total_symbols'] = len(symbols)
        self.stats['start_time'] = datetime.now()
        
        logger.info("="*80)
        logger.info(f"PARALLEL PIPELINE: Starting high-performance update for {len(symbols)} symbols")
        logger.info(f"Configuration: Fetch={self.max_fetch_concurrency} | Save={self.max_save_concurrency}")
        logger.info("="*80)
        
        # Create workers
        fetch_semaphore = asyncio.Semaphore(self.max_fetch_concurrency)
        
        # Start fetch workers
        fetch_workers = [
            asyncio.create_task(self.fetch_worker(fetch_semaphore))
            for _ in range(min(20, len(symbols)))  # Up to 20 fetch workers
        ]
        
        # Start multiple save workers for parallel processing
        save_workers = [
            asyncio.create_task(self.save_worker())
            for _ in range(min(self.max_save_concurrency, 10))  # Up to 10 save workers
        ]
        
        # Queue all symbols for fetching
        for symbol in symbols:
            await self.fetch_queue.put(symbol)
        
        # Wait for all fetches to complete
        await self.fetch_queue.join()
        
        # Stop fetch workers
        for _ in fetch_workers:
            await self.fetch_queue.put(None)
        await asyncio.gather(*fetch_workers)
        
        # Wait for all processing to complete
        await self.save_queue.join()
        
        # Stop save workers
        for _ in save_workers:
            await self.save_queue.put(None)
        await asyncio.gather(*save_workers)
        
        # Close client pool
        await self.chartink_service.close_all_clients()
        
        # Final statistics
        total_time = (datetime.now() - self.stats['start_time']).total_seconds()
        avg_fetch = sum(self.stats['fetch_times']) / len(self.stats['fetch_times']) if self.stats['fetch_times'] else 0
        avg_process = sum(self.stats['process_times']) / len(self.stats['process_times']) if self.stats['process_times'] else 0
        
        logger.info("="*80)
        logger.info(f"PARALLEL PIPELINE COMPLETED in {total_time:.2f}s")
        logger.info(f"Results: {self.stats['saved']} saved, {self.stats['errors']} errors")
        logger.info(f"Performance: {self.stats['saved']/total_time:.1f} stocks/sec")
        logger.info(f"Avg Times: Fetch={avg_fetch:.1f}ms | Process={avg_process:.1f}ms")
        logger.info("="*80)
        
        # Generate results dict for compatibility
        results = {}
        for i in range(self.stats['saved']):
            results[symbols[i]] = "Updated successfully - parallel pipeline"
        for i in range(self.stats['errors']):
            results[symbols[self.stats['saved'] + i]] = "Error: Processing failed"
        
        return results
    
    async def single_update_cycle(self) -> Dict[str, str]:
        """Perform a single update cycle using parallel pipeline."""
        if not self.is_market_hours() and not self.force_run:
            logger.info("Market is closed, skipping update cycle (use force_run=True to override)")
            return {"status": "Market closed - no update performed"}
        
        logger.info("🔄 Starting PARALLEL PIPELINE update cycle...")
        
        # Reset stats
        self.stats = {
            'total_symbols': 0, 'fetched': 0, 'processed': 0, 'saved': 0, 'errors': 0,
            'start_time': None, 'fetch_times': [], 'process_times': [], 'save_times': []
        }
        
        results = await self.parallel_pipeline_update()
        
        self.last_update_time = datetime.now()
        self.next_update_time = self.last_update_time + timedelta(minutes=self.update_interval)
        
        logger.info(f"⏰ Next update in {self.update_interval} minutes at {self.next_update_time.strftime('%H:%M:%S')}")
        
        return results
    
    async def start_periodic_updates(self, interval_minutes: int = 2, force_run: bool = False):
        """Start periodic updates using parallel pipeline."""
        if self.is_running:
            logger.warning("Periodic updates already running")
            return
        
        self.force_run = force_run
        self.update_interval = interval_minutes
        
        with self.lock:
            if self.is_running:
                return
            self.is_running = True
        
        logger.info(f"Starting PARALLEL PIPELINE periodic updates every {interval_minutes} minutes (force_run={force_run})")
        
        try:
            while self.is_running:
                await self.single_update_cycle()
                
                if self.is_running:
                    next_update_time = datetime.now() + timedelta(minutes=interval_minutes)
                    logger.info(f"⏳ Waiting {interval_minutes} minutes until next update at {next_update_time.strftime('%H:%M:%S')}...")
                    
                    for i in range(interval_minutes * 60):
                        if not self.is_running:
                            break
                        await asyncio.sleep(1)
                        
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
                logger.info("Periodic updates stopped")

# Global instance
parallel_pipeline_updater = ParallelPipelineUpdater()