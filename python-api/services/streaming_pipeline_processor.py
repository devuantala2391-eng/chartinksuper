"""
Streaming Pipeline Processor
- Fetch data in chunks from Chartink
- Process indicators in memory for each chunk
- Store immediately without waiting for entire stock completion
- Maximum parallelization across all operations
"""

import asyncio
import logging
import time
import psutil
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
import numpy as np
import pandas as pd
from dataclasses import dataclass
from collections import deque

from .ultra_fast_database_service import ultra_fast_db
from .chartink_service import ChartinkService
from utils.constants import STOCK_SYMBOLS

logger = logging.getLogger(__name__)

@dataclass
class ChunkProcessingResult:
    symbol: str
    chunk_index: int
    success: bool
    chunk_size: int
    fetch_time: float
    process_time: float
    store_time: float
    error: Optional[str] = None

@dataclass
class StreamingStats:
    total_symbols: int = 0
    completed_symbols: int = 0
    total_chunks: int = 0
    completed_chunks: int = 0
    failed_chunks: int = 0
    total_candles: int = 0
    start_time: float = 0
    active_tasks: int = 0

class StreamingPipelineProcessor:
    """
    Ultra-fast streaming processor that handles fetch-process-store in parallel chunks.
    
    Key Features:
    - Processes RELIANCE in 500-candle chunks simultaneously
    - Each chunk: Fetch → Calculate Indicators → Store (all parallel)
    - No waiting for entire stock completion
    - Maximum CPU/RAM utilization
    - Failure queue with retry logic
    """
    
    def __init__(self):
        self.chartink_service = ChartinkService()
        
        # Dynamic resource allocation - USE FULL SYSTEM
        self.cpu_cores = psutil.cpu_count()
        self.logical_cores = psutil.cpu_count(logical=True)
        self.available_ram_gb = psutil.virtual_memory().total / (1024**3)
        
        # MAXIMUM parallel processing - no artificial limits
        self.max_concurrent_symbols = self.logical_cores * 2  # Use all logical cores
        self.max_concurrent_chunks = self.logical_cores * 8   # Much higher chunk concurrency
        self.max_db_workers = self.logical_cores * 4          # Parallel database writes
        self.chunk_size = 500  # Candles per chunk
        
        # Queues for pipeline stages
        self.fetch_queue = asyncio.Queue(maxsize=1000)
        self.process_queue = asyncio.Queue(maxsize=1000)
        self.store_queue = asyncio.Queue(maxsize=1000)
        self.failure_queue = asyncio.Queue(maxsize=500)
        
        # Statistics
        self.stats = StreamingStats()
        self.results = deque(maxlen=10000)  # Store last 10k results
        
        # Thread pools for CPU-intensive operations - USE ALL CORES
        self.process_executor = ThreadPoolExecutor(
            max_workers=self.logical_cores,  # Use all logical cores
            thread_name_prefix="indicator_calc"
        )
        
        # Database write thread pool for parallel storage
        self.db_executor = ThreadPoolExecutor(
            max_workers=self.max_db_workers,
            thread_name_prefix="db_write"
        )
        
        logger.info(f"🚀 MAXIMUM PERFORMANCE Streaming processor initialized:")
        logger.info(f"   CPU Cores: {self.cpu_cores} physical / {self.logical_cores} logical")
        logger.info(f"   Available RAM: {self.available_ram_gb:.1f}GB")
        logger.info(f"   Max Concurrent Symbols: {self.max_concurrent_symbols}")
        logger.info(f"   Max Concurrent Chunks: {self.max_concurrent_chunks}")
        logger.info(f"   Max DB Workers: {self.max_db_workers}")
        logger.info(f"   Chunk Size: {self.chunk_size} candles")
        logger.info(f"   🚀 NO ARTIFICIAL LIMITS - USING FULL SYSTEM RESOURCES")

    async def initialize(self):
        """Initialize all services"""
        await ultra_fast_db.initialize()
        logger.info("✅ Streaming pipeline initialized")

    def calculate_indicators_sync(self, ohlcv_data: List[Dict]) -> List[Dict]:
        """
        Calculate all indicators for OHLCV data synchronously (CPU-intensive).
        This runs in thread pool to not block async operations.
        """
        if not ohlcv_data:
            return []
        
        try:
            # Convert to pandas for efficient calculation
            df = pd.DataFrame(ohlcv_data)
            
            # Ensure numeric columns
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Calculate common indicators
            if len(df) >= 14:  # Need minimum data for indicators
                
                # RSI calculation
                delta = df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                df['rsi_14'] = 100 - (100 / (1 + rs))
                
                # SMA calculations
                if len(df) >= 20:
                    df['sma_20'] = df['close'].rolling(window=20).mean()
                if len(df) >= 50:
                    df['sma_50'] = df['close'].rolling(window=50).mean()
                
                # EMA calculations
                df['ema_12'] = df['close'].ewm(span=12).mean()
                df['ema_26'] = df['close'].ewm(span=26).mean()
                
                # SuperTrend calculation
                if len(df) >= 10:
                    df = self._calculate_supertrend(df, period=10, multiplier=2)
                    df = self._calculate_supertrend(df, period=10, multiplier=3, suffix='_10_3')
                
                # Bollinger Bands
                if len(df) >= 20:
                    sma_20 = df['close'].rolling(window=20).mean()
                    std_20 = df['close'].rolling(window=20).std()
                    df['bb_upper_20'] = sma_20 + (std_20 * 2)
                    df['bb_lower_20'] = sma_20 - (std_20 * 2)
                    df['bb_middle_20'] = sma_20
            
            # Convert back to list of dictionaries
            df = df.fillna(np.nan).replace([np.inf, -np.inf], np.nan)
            return df.to_dict('records')
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return ohlcv_data  # Return original data if calculation fails

    def _calculate_supertrend(self, df: pd.DataFrame, period: int = 10, 
                            multiplier: float = 2, suffix: str = '') -> pd.DataFrame:
        """Calculate SuperTrend indicator"""
        try:
            # ATR calculation
            high_low = df['high'] - df['low']
            high_close = (df['high'] - df['close'].shift()).abs()
            low_close = (df['low'] - df['close'].shift()).abs()
            
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(window=period).mean()
            
            # SuperTrend calculation
            hl2 = (df['high'] + df['low']) / 2
            basic_upper = hl2 + (multiplier * atr)
            basic_lower = hl2 - (multiplier * atr)
            
            # Initialize final bands
            final_upper = basic_upper.copy()
            final_lower = basic_lower.copy()
            
            for i in range(1, len(df)):
                # Upper band
                if basic_upper.iloc[i] < final_upper.iloc[i-1] or df['close'].iloc[i-1] > final_upper.iloc[i-1]:
                    final_upper.iloc[i] = basic_upper.iloc[i]
                else:
                    final_upper.iloc[i] = final_upper.iloc[i-1]
                
                # Lower band
                if basic_lower.iloc[i] > final_lower.iloc[i-1] or df['close'].iloc[i-1] < final_lower.iloc[i-1]:
                    final_lower.iloc[i] = basic_lower.iloc[i]
                else:
                    final_lower.iloc[i] = final_lower.iloc[i-1]
            
            # SuperTrend
            supertrend = pd.Series(index=df.index, dtype=float)
            trend = pd.Series(index=df.index, dtype=bool)
            
            for i in range(len(df)):
                if i == 0:
                    trend.iloc[i] = True  # Start with uptrend
                    supertrend.iloc[i] = final_lower.iloc[i]
                else:
                    if trend.iloc[i-1] and df['close'].iloc[i] < final_lower.iloc[i]:
                        trend.iloc[i] = False
                        supertrend.iloc[i] = final_upper.iloc[i]
                    elif not trend.iloc[i-1] and df['close'].iloc[i] > final_upper.iloc[i]:
                        trend.iloc[i] = True
                        supertrend.iloc[i] = final_lower.iloc[i]
                    else:
                        trend.iloc[i] = trend.iloc[i-1]
                        supertrend.iloc[i] = final_upper.iloc[i] if not trend.iloc[i] else final_lower.iloc[i]
            
            column_name = f'supertrend_{period}_{multiplier}'.replace('.', 'dot') + suffix
            df[column_name] = supertrend
            
            return df
            
        except Exception as e:
            logger.error(f"Error calculating SuperTrend: {e}")
            return df

    async def fetch_chunk(self, symbol: str, chunk_size: int, offset: int = 0) -> Optional[List[Dict]]:
        """Fetch a chunk of data from Chartink API"""
        try:
            start_time = time.time()
            
            # Fetch data with offset/limit simulation (Chartink doesn't support this directly)
            # For now, we'll fetch all data and slice it
            response_data = await self.chartink_service.fetch_stock_data(symbol, size=2000)
            mapped_data = self.chartink_service._map_response_data(response_data)
            
            if not mapped_data:
                return None
            
            # Slice the chunk we need
            start_idx = offset
            end_idx = min(offset + chunk_size, len(mapped_data))
            chunk_data = mapped_data[start_idx:end_idx]
            
            fetch_time = time.time() - start_time
            
            if chunk_data:
                logger.debug(f"📥 Fetched chunk for {symbol}: {len(chunk_data)} candles (offset={offset}, time={fetch_time:.2f}s)")
                return chunk_data
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to fetch chunk for {symbol} (offset={offset}): {e}")
            return None

    async def process_chunk(self, symbol: str, chunk_index: int, chunk_data: List[Dict]) -> ChunkProcessingResult:
        """Process a single chunk: fetch → calculate indicators → store (TRULY PARALLEL)"""
        
        result = ChunkProcessingResult(
            symbol=symbol,
            chunk_index=chunk_index,
            success=False,
            chunk_size=len(chunk_data),
            fetch_time=0,
            process_time=0,
            store_time=0
        )
        
        try:
            # Step 1: Calculate indicators (CPU-intensive, use thread pool)
            process_start = time.time()
            loop = asyncio.get_event_loop()
            enriched_data = await loop.run_in_executor(
                self.process_executor, 
                self.calculate_indicators_sync, 
                chunk_data
            )
            result.process_time = time.time() - process_start
            
            # Step 2: Store in database IMMEDIATELY and IN PARALLEL
            # Use separate thread pool for database operations to not block processing
            store_start = time.time()
            
            # Run database storage in separate thread pool for true parallelism
            success = await loop.run_in_executor(
                self.db_executor,
                self._store_chunk_sync,
                symbol, enriched_data
            )
            
            result.store_time = time.time() - store_start
            
            if success:
                result.success = True
                self.stats.completed_chunks += 1
                self.stats.total_candles += len(enriched_data)
                logger.debug(f"✅ PARALLEL: Processed chunk {symbol}_{chunk_index}: {len(enriched_data)} candles")
            else:
                result.error = "Database storage failed"
                logger.error(f"❌ Failed to store chunk {symbol}_{chunk_index}")
            
        except Exception as e:
            result.error = str(e)
            logger.error(f"❌ Error processing chunk {symbol}_{chunk_index}: {e}")
        
        self.results.append(result)
        return result

    def _store_chunk_sync(self, symbol: str, enriched_data: List[Dict]) -> bool:
        """Synchronous wrapper for database storage (runs in thread pool)"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run the async database operation
            success = loop.run_until_complete(
                ultra_fast_db.store_chunk_with_indicators(symbol, enriched_data)
            )
            
            loop.close()
            return success
            
        except Exception as e:
            logger.error(f"Sync database store error for {symbol}: {e}")
            return False

    async def process_symbol_streaming(self, symbol: str, total_candles: int = 2000) -> List[ChunkProcessingResult]:
        """
        Process a single symbol in streaming chunks.
        Each chunk is processed independently and stored immediately.
        """
        logger.info(f"🎯 Starting streaming processing for {symbol} ({total_candles} candles)")
        
        # Calculate number of chunks needed
        num_chunks = (total_candles + self.chunk_size - 1) // self.chunk_size
        
        # Fetch all data first (since Chartink doesn't support pagination)
        all_data = await self.fetch_chunk(symbol, total_candles, 0)
        if not all_data:
            logger.error(f"❌ No data fetched for {symbol}")
            return []
        
        logger.info(f"📥 Fetched {len(all_data)} candles for {symbol}, processing in {num_chunks} chunks")
        
        # Create chunk processing tasks
        chunk_tasks = []
        for chunk_index in range(num_chunks):
            start_idx = chunk_index * self.chunk_size
            end_idx = min(start_idx + self.chunk_size, len(all_data))
            chunk_data = all_data[start_idx:end_idx]
            
            if chunk_data:
                # Create task for this chunk
                task = self.process_chunk(symbol, chunk_index, chunk_data)
                chunk_tasks.append(task)
        
        # Process all chunks in TRULY PARALLEL mode - no artificial semaphore limits
        # Let the system handle resource management naturally
        logger.info(f"🚀 PARALLEL EXECUTION: Processing {len(chunk_tasks)} chunks simultaneously")
        
        # Execute all chunk tasks in MAXIMUM parallel mode
        chunk_results = await asyncio.gather(
            *chunk_tasks,
            return_exceptions=True
        )
        
        # Filter out exceptions and count successes
        valid_results = [r for r in chunk_results if isinstance(r, ChunkProcessingResult)]
        successful_chunks = sum(1 for r in valid_results if r.success)
        
        logger.info(f"✅ Completed {symbol}: {successful_chunks}/{len(chunk_tasks)} chunks successful")
        
        return valid_results

    async def hard_refresh_streaming(self, symbols: List[str] = None) -> Dict[str, Any]:
        """
        Perform ultra-fast hard refresh using streaming pipeline.
        All symbols and chunks processed in parallel.
        """
        if symbols is None:
            symbols = STOCK_SYMBOLS[:100]  # Limit for testing
        
        self.stats = StreamingStats()
        self.stats.total_symbols = len(symbols)
        self.stats.start_time = time.time()
        
        logger.info(f"🚀 Starting streaming hard refresh for {len(symbols)} symbols")
        logger.info(f"💻 Using {self.cpu_cores} CPU cores, {self.available_ram_gb:.1f}GB RAM")
        
        # Process symbols with concurrency limit
        symbol_semaphore = asyncio.Semaphore(self.max_concurrent_symbols)
        
        async def process_symbol_with_semaphore(symbol):
            async with symbol_semaphore:
                self.stats.active_tasks += 1
                try:
                    results = await self.process_symbol_streaming(symbol)
                    self.stats.completed_symbols += 1
                    return symbol, results
                finally:
                    self.stats.active_tasks -= 1
        
        # Start all symbol processing tasks
        symbol_tasks = [process_symbol_with_semaphore(symbol) for symbol in symbols]
        
        # Process with progress reporting
        completed_results = []
        
        # Use asyncio.as_completed for real-time progress
        for coro in asyncio.as_completed(symbol_tasks):
            try:
                symbol, results = await coro
                completed_results.append((symbol, results))
                
                # Progress reporting
                progress = (len(completed_results) / len(symbols)) * 100
                elapsed = time.time() - self.stats.start_time
                
                if len(completed_results) % 10 == 0 or len(completed_results) == len(symbols):
                    logger.info(f"📊 Progress: {len(completed_results)}/{len(symbols)} symbols ({progress:.1f}%) "
                              f"| Elapsed: {elapsed:.1f}s | Active: {self.stats.active_tasks}")
                
            except Exception as e:
                logger.error(f"❌ Symbol processing failed: {e}")
        
        # Calculate final statistics
        total_time = time.time() - self.stats.start_time
        
        # Count successful/failed chunks across all symbols
        successful_symbols = 0
        failed_symbols = 0
        total_successful_chunks = 0
        total_failed_chunks = 0
        
        for symbol, results in completed_results:
            if any(r.success for r in results):
                successful_symbols += 1
                total_successful_chunks += sum(1 for r in results if r.success)
                total_failed_chunks += sum(1 for r in results if not r.success)
            else:
                failed_symbols += 1
        
        final_stats = {
            'total_symbols': len(symbols),
            'successful_symbols': successful_symbols,
            'failed_symbols': failed_symbols,
            'total_chunks': total_successful_chunks + total_failed_chunks,
            'successful_chunks': total_successful_chunks,
            'failed_chunks': total_failed_chunks,
            'total_candles': self.stats.total_candles,
            'total_time_seconds': total_time,
            'symbols_per_second': len(symbols) / total_time if total_time > 0 else 0,
            'chunks_per_second': (total_successful_chunks + total_failed_chunks) / total_time if total_time > 0 else 0,
            'candles_per_second': self.stats.total_candles / total_time if total_time > 0 else 0,
            'cpu_cores_used': self.cpu_cores,
            'max_concurrent_symbols': self.max_concurrent_symbols,
            'max_concurrent_chunks': self.max_concurrent_chunks,
            'chunk_size': self.chunk_size
        }
        
        logger.info(f"🎉 Streaming hard refresh completed!")
        logger.info(f"📊 Final Statistics:")
        logger.info(f"   Symbols: {successful_symbols}/{len(symbols)} successful")
        logger.info(f"   Chunks: {total_successful_chunks}/{total_successful_chunks + total_failed_chunks} successful")
        logger.info(f"   Candles: {self.stats.total_candles:,} processed")
        logger.info(f"   Time: {total_time:.2f}s")
        logger.info(f"   Speed: {final_stats['symbols_per_second']:.1f} symbols/sec, {final_stats['candles_per_second']:.0f} candles/sec")
        
        return final_stats

    async def retry_failed_chunks(self, max_retries: int = 10) -> int:
        """Retry failed chunks from the failure queue"""
        retried_count = 0
        
        while not self.failure_queue.empty() and retried_count < max_retries:
            try:
                failed_chunk = await asyncio.wait_for(self.failure_queue.get(), timeout=1.0)
                
                # Retry processing this chunk
                result = await self.process_chunk(
                    failed_chunk['symbol'],
                    failed_chunk['chunk_index'], 
                    failed_chunk['chunk_data']
                )
                
                if result.success:
                    logger.info(f"✅ Retry successful for {failed_chunk['symbol']}_{failed_chunk['chunk_index']}")
                else:
                    logger.warning(f"❌ Retry failed for {failed_chunk['symbol']}_{failed_chunk['chunk_index']}")
                
                retried_count += 1
                
            except asyncio.TimeoutError:
                break  # No more items in queue
            except Exception as e:
                logger.error(f"Error during retry: {e}")
                break
        
        logger.info(f"🔄 Retried {retried_count} failed chunks")
        return retried_count

    def get_performance_report(self) -> Dict[str, Any]:
        """Get real-time performance report"""
        if not self.results:
            return {}
        
        recent_results = list(self.results)
        successful = [r for r in recent_results if r.success]
        failed = [r for r in recent_results if not r.success]
        
        if successful:
            avg_fetch_time = sum(r.fetch_time for r in successful) / len(successful)
            avg_process_time = sum(r.process_time for r in successful) / len(successful)
            avg_store_time = sum(r.store_time for r in successful) / len(successful)
        else:
            avg_fetch_time = avg_process_time = avg_store_time = 0
        
        return {
            'total_chunks_processed': len(recent_results),
            'successful_chunks': len(successful),
            'failed_chunks': len(failed),
            'success_rate': (len(successful) / len(recent_results)) * 100 if recent_results else 0,
            'avg_fetch_time': avg_fetch_time,
            'avg_process_time': avg_process_time,
            'avg_store_time': avg_store_time,
            'avg_total_time': avg_fetch_time + avg_process_time + avg_store_time,
            'active_tasks': self.stats.active_tasks,
            'total_candles_processed': self.stats.total_candles
        }

    async def cleanup(self):
        """Cleanup resources"""
        if hasattr(self, 'process_executor'):
            self.process_executor.shutdown(wait=True)
        if hasattr(self, 'db_executor'):
            self.db_executor.shutdown(wait=True)
        logger.info("🧹 Streaming processor cleanup completed")

# Global instance
streaming_processor = StreamingPipelineProcessor()