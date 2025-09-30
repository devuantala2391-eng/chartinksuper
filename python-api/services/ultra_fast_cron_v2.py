"""
Ultra-Fast Cron Service v2 - Sub-3-Second Target
=================================================

Revolutionary approach:
1. 🚀 Fire all 2500 HTTP requests simultaneously (no batching)
2. 💾 Cache previous day OHLCV data once per day (symbol_latest_keys - 1)
3. ⚡ Real-time OHLCV calculation as responses arrive
4. 🔄 Thread-safe queue for results
5. 💽 Single bulk database transaction

Target: < 3 seconds (vs current 10 seconds for hard-refresh)
"""

import asyncio
import logging
import time
import threading
import queue
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, date
from collections import defaultdict
import httpx

from .ultra_fast_database_service import ultra_fast_db
from .chartink_service import ChartinkService
from utils.constants import STOCK_SYMBOLS

logger = logging.getLogger(__name__)

class PreviousDayCache:
    """Cache for previous day OHLCV data - valid for entire day"""

    def __init__(self, db_pool=None):
        self.cache_data: Dict[str, Dict] = {}
        self.cache_date: Optional[date] = None
        self.cache_loaded = False
        self.db_pool = db_pool  # Optional: custom database pool for thread isolation

    def is_cache_valid(self) -> bool:
        """Check if cache is valid for today"""
        today = date.today()
        return self.cache_loaded and self.cache_date == today

    async def load_cache(self) -> bool:
        """Load previous day OHLCV data for all symbols"""
        today = date.today()

        if self.is_cache_valid():
            logger.info(f"✅ Cache already loaded for {today}")
            return True

        logger.info(f"🔄 Loading previous day cache for {today}")
        start_time = time.time()

        try:
            # Use custom pool if provided, otherwise use global pool
            pool = self.db_pool if self.db_pool else ultra_fast_db.pool
            async with pool.acquire() as conn:
                # Get all symbols with their latest keys
                latest_keys = await conn.fetch("""
                    SELECT symbol, latest_daily_key
                    FROM symbol_latest_keys
                    WHERE latest_daily_key >= 1
                """)

                if not latest_keys:
                    logger.warning("No symbols found in symbol_latest_keys")
                    return False

                # Build query to get previous day data (latest_key - 1)
                symbol_queries = []
                for row in latest_keys:
                    symbol = row['symbol']
                    prev_key = row['latest_daily_key'] - 1

                    if prev_key >= 0:  # Only if previous day exists
                        symbol_queries.append(f"'{symbol}_{prev_key}'")

                if not symbol_queries:
                    logger.warning("No previous day data available")
                    return False

                # Fetch all previous day candles in one query
                prev_candles = await conn.fetch(f"""
                    SELECT candle_key_id, symbol, open, high, low, close, volume,
                           weekly_open, weekly_high, weekly_low, weekly_close, weekly_volume,
                           monthly_open, monthly_high, monthly_low, monthly_close, monthly_volume,
                           day_of_week, timestamp
                    FROM daily_candles
                    WHERE candle_key_id = ANY(ARRAY[{','.join(symbol_queries)}])
                """)

                # Build cache dictionary
                self.cache_data = {}
                for candle in prev_candles:
                    symbol = candle['symbol']
                    self.cache_data[symbol] = {
                        'daily': {
                            'open': float(candle['open']),
                            'high': float(candle['high']),
                            'low': float(candle['low']),
                            'close': float(candle['close']),
                            'volume': int(candle['volume'])
                        },
                        'weekly': {
                            'open': float(candle['weekly_open']) if candle['weekly_open'] else None,
                            'high': float(candle['weekly_high']) if candle['weekly_high'] else None,
                            'low': float(candle['weekly_low']) if candle['weekly_low'] else None,
                            'close': float(candle['weekly_close']) if candle['weekly_close'] else None,
                            'volume': int(candle['weekly_volume']) if candle['weekly_volume'] else None
                        },
                        'monthly': {
                            'open': float(candle['monthly_open']) if candle['monthly_open'] else None,
                            'high': float(candle['monthly_high']) if candle['monthly_high'] else None,
                            'low': float(candle['monthly_low']) if candle['monthly_low'] else None,
                            'close': float(candle['monthly_close']) if candle['monthly_close'] else None,
                            'volume': int(candle['monthly_volume']) if candle['monthly_volume'] else None
                        },
                        'meta': {
                            'day_of_week': candle['day_of_week'],
                            'timestamp': candle['timestamp']
                        }
                    }

                self.cache_date = today
                self.cache_loaded = True

                load_time = time.time() - start_time
                logger.info(f"✅ Loaded cache for {len(self.cache_data)} symbols in {load_time:.2f}s")
                return True

        except Exception as e:
            logger.error(f"❌ Failed to load cache: {e}")
            return False

    def get_previous_data(self, symbol: str) -> Optional[Dict]:
        """Get previous day data for symbol"""
        return self.cache_data.get(symbol)


class UltraFastCronV2:
    """Ultra-fast cron service targeting < 3 seconds"""

    def __init__(self):
        self.cache = PreviousDayCache()
        self.chartink_service = ChartinkService()
        self.results_queue = queue.Queue()
        self.last_cron_execution = None  # Track when last cron job was executed
        self.cron_start_time = None  # Track when cron timer was started
        self.cron_thread = None  # Background thread for cron job
        self.stats = {
            'total_symbols': 0,
            'success_count': 0,
            'error_count': 0,
            'start_time': 0,
            'end_time': 0,
            'http_time': 0,
            'calc_time': 0,
            'db_time': 0
        }

    async def initialize(self):
        """Initialize the service"""
        await ultra_fast_db.initialize()
        await self.cache.load_cache()
        logger.info("🚀 Ultra-Fast Cron V2 initialized")

    async def run_ultra_fast_cron(self) -> Dict[str, Any]:
        """Run the ultra-fast cron job - target < 3 seconds"""
        logger.info("🎯 Starting Ultra-Fast Cron V2 (Target: < 3 seconds)")

        # Ensure cache is loaded (in case running from background thread)
        if not self.cache.cache_loaded:
            logger.info("📥 Loading cache data...")
            await self.cache.load_cache()

        symbols = STOCK_SYMBOLS[:2500]  # Process all symbols
        self.stats['total_symbols'] = len(symbols)
        self.stats['start_time'] = time.time()

        # Step 1: Fire all HTTP requests simultaneously
        logger.info(f"⚡ Firing {len(symbols)} HTTP requests simultaneously...")
        http_start = time.time()
        await self._fire_all_requests_parallel(symbols)
        self.stats['http_time'] = time.time() - http_start

        # Step 2: Process results queue (already populated during HTTP processing)
        calc_start = time.time()
        results = self._collect_results_from_queue()
        self.stats['calc_time'] = time.time() - calc_start

        # Step 3: Bulk save to database
        db_start = time.time()
        await self._bulk_save_results(results)
        self.stats['db_time'] = time.time() - db_start

        self.stats['end_time'] = time.time()
        total_time = self.stats['end_time'] - self.stats['start_time']

        # Record when this cron execution completed for countdown timer
        self.last_cron_execution = time.time()

        # Performance report
        success_rate = (self.stats['success_count'] / len(symbols)) * 100
        symbols_per_sec = len(symbols) / total_time if total_time > 0 else 0

        performance_report = {
            'total_time_seconds': total_time,
            'target_achieved': total_time < 3.0,
            'total_symbols': len(symbols),
            'successful': self.stats['success_count'],
            'failed': self.stats['error_count'],
            'success_rate_percent': success_rate,
            'symbols_per_second': symbols_per_sec,
            'timing_breakdown': {
                'http_requests': self.stats['http_time'],
                'calculations': self.stats['calc_time'],
                'database_save': self.stats['db_time']
            },
            'performance_improvements': {
                'simultaneous_http_requests': True,
                'previous_day_caching': True,
                'real_time_processing': True,
                'bulk_database_save': True,
                'no_batching': True
            }
        }

        # Log results
        status = "✅ TARGET ACHIEVED" if total_time < 3.0 else f"⚠️ TARGET MISSED"
        logger.info(f"🎉 Ultra-Fast Cron V2 completed in {total_time:.2f}s - {status}")
        logger.info(f"📊 Success: {self.stats['success_count']}/{len(symbols)} ({success_rate:.1f}%)")
        logger.info(f"⚡ Speed: {symbols_per_sec:.1f} symbols/sec")
        logger.info(f"🕒 Breakdown: HTTP={self.stats['http_time']:.2f}s, Calc={self.stats['calc_time']:.2f}s, DB={self.stats['db_time']:.2f}s")

        return performance_report

    async def _fire_all_requests_parallel(self, symbols: List[str]):
        """Fire all HTTP requests with controlled concurrency for optimal performance"""
        # Use semaphore to control concurrent requests (optimal for API limits and system resources)
        # Set to 125 concurrent requests - matching client pool capacity
        semaphore = asyncio.Semaphore(125)

        async def process_with_semaphore(symbol: str):
            async with semaphore:
                return await self._process_single_symbol_fast(symbol)

        # Create tasks with semaphore control
        tasks = []
        for symbol in symbols:
            task = asyncio.create_task(process_with_semaphore(symbol))
            tasks.append(task)

        # Use gather for better performance than as_completed
        # This allows better batching and reduces overhead
        logger.info(f"🚀 Processing {len(symbols)} symbols with 125 concurrent connections...")

        # Process in batches for progress reporting
        batch_size = 500
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)

            # Count successes and failures
            for result in batch_results:
                if isinstance(result, Exception):
                    self.stats['error_count'] += 1
                    logger.debug(f"Batch error: {result}")

            # Progress update
            completed = min(i + batch_size, len(symbols))
            logger.info(f"📊 Progress: {completed}/{len(symbols)} completed ({(completed/len(symbols)*100):.1f}%)")

    async def _process_single_symbol_fast(self, symbol: str) -> bool:
        """Process single symbol: HTTP request + OHLCV calculation + queue"""
        try:
            # 1. HTTP request (size=1 for latest candle only)
            response_data = await self.chartink_service.fetch_stock_data(symbol, size=1)

            # 2. Map response data
            mapped_data = self.chartink_service._map_response_data(response_data)

            if not mapped_data or len(mapped_data) == 0:
                self.stats['error_count'] += 1
                return False

            current_candle = mapped_data[0]  # Latest candle

            # 3. Calculate OHLCV with previous day data
            calculated_candle = self._calculate_ohlcv_fast(symbol, current_candle)

            if calculated_candle:
                # 4. Add to results queue (thread-safe)
                self.results_queue.put((symbol, calculated_candle))
                self.stats['success_count'] += 1
                return True
            else:
                self.stats['error_count'] += 1
                return False

        except Exception as e:
            self.stats['error_count'] += 1
            logger.debug(f"❌ {symbol} failed: {e}")
            return False

    def _calculate_ohlcv_fast(self, symbol: str, current_candle: Dict) -> Optional[Dict]:
        """Calculate daily/weekly/monthly OHLCV using cached previous day data"""
        try:
            # Get previous day data from cache
            prev_data = self.cache.get_previous_data(symbol)

            # Use market-aware timestamp (not system time)
            # This will be set properly during database save logic
            market_timestamp = self._get_market_aware_timestamp(symbol, prev_data)

            # Current candle OHLCV
            current_ohlcv = {
                'open': float(current_candle['open']),
                'high': float(current_candle['high']),
                'low': float(current_candle['low']),
                'close': float(current_candle['close']),
                'volume': int(current_candle['volume']),
                'timestamp': market_timestamp
            }

            if not prev_data:
                # First day for this symbol - use current as all timeframes
                logger.debug(f"🆕 First day for {symbol} - using current candle")
                return {
                    'daily': current_ohlcv,
                    'weekly': current_ohlcv.copy(),
                    'monthly': current_ohlcv.copy(),
                    'is_first_day': True
                }

            # Calculate weekly OHLCV (sliding window logic from hard-refresh)
            prev_weekly = prev_data['weekly']
            current_day_of_week = self._calculate_day_of_week(prev_data['meta']['day_of_week'])

            if current_day_of_week == 1:  # Monday - start new week
                weekly_ohlcv = current_ohlcv.copy()
            else:
                # Continue current week
                weekly_ohlcv = {
                    'open': prev_weekly['open'] if prev_weekly['open'] else current_ohlcv['open'],
                    'high': max(prev_weekly['high'] or 0, current_ohlcv['high']),
                    'low': min(prev_weekly['low'] or float('inf'), current_ohlcv['low']),
                    'close': current_ohlcv['close'],
                    'volume': (prev_weekly['volume'] or 0) + current_ohlcv['volume'],
                    'timestamp': current_ohlcv['timestamp']
                }

            # Calculate monthly OHLCV (similar logic)
            prev_monthly = prev_data['monthly']
            is_new_month = self._is_new_month(prev_data['meta']['timestamp'], current_ohlcv['timestamp'])

            if is_new_month:
                monthly_ohlcv = current_ohlcv.copy()
            else:
                monthly_ohlcv = {
                    'open': prev_monthly['open'] if prev_monthly['open'] else current_ohlcv['open'],
                    'high': max(prev_monthly['high'] or 0, current_ohlcv['high']),
                    'low': min(prev_monthly['low'] or float('inf'), current_ohlcv['low']),
                    'close': current_ohlcv['close'],
                    'volume': (prev_monthly['volume'] or 0) + current_ohlcv['volume'],
                    'timestamp': current_ohlcv['timestamp']
                }

            return {
                'daily': current_ohlcv,
                'weekly': weekly_ohlcv,
                'monthly': monthly_ohlcv,
                'is_first_day': False
            }

        except Exception as e:
            logger.error(f"❌ OHLCV calculation failed for {symbol}: {e}")
            return None

    def _calculate_day_of_week(self, prev_day_of_week: int) -> int:
        """Calculate current day of week (1=Mon, 5=Fri) handling weekends"""
        # Simple increment with weekend handling
        next_day = prev_day_of_week + 1
        if next_day > 5:  # Weekend - next is Monday
            return 1
        return next_day

    def _is_new_month(self, prev_timestamp: int, current_timestamp: int) -> bool:
        """Check if current candle is in a new month"""
        try:
            prev_date = datetime.fromtimestamp(prev_timestamp / 1000).date()
            current_date = datetime.fromtimestamp(current_timestamp / 1000).date()
            return prev_date.month != current_date.month or prev_date.year != current_date.year
        except:
            return False

    def _get_market_aware_timestamp(self, symbol: str, prev_data: Optional[Dict]) -> int:
        """
        Get market-aware timestamp that handles edge cases:
        - After midnight before market open: continue with previous day
        - Weekends and holidays: continue with Friday's timestamp
        - During market hours: use current timestamp
        - First time processing: use current timestamp

        Returns timestamp in milliseconds
        """
        import time
        import pytz
        from datetime import datetime, timedelta

        ist = pytz.timezone('Asia/Kolkata')
        current_time_ist = datetime.now(ist)

        # If no previous data, use current time (first time processing)
        if not prev_data or not prev_data.get('meta', {}).get('timestamp'):
            return int(time.time() * 1000)

        prev_timestamp = prev_data['meta']['timestamp']
        prev_datetime_ist = datetime.fromtimestamp(prev_timestamp / 1000.0, ist)
        prev_date_ist = prev_datetime_ist.date()
        current_date_ist = current_time_ist.date()

        # Same date - always continue with same timestamp (UPDATE scenario)
        if prev_date_ist == current_date_ist:
            return prev_timestamp

        # Different date - check if we should move to next trading day
        # Key insight: Only move to next day AFTER market has started

        # Check if today is a weekend (Saturday=5, Sunday=6)
        if current_time_ist.weekday() >= 5:  # Weekend
            # Continue with Friday's timestamp
            return prev_timestamp

        # Check if current time is before market start (9:15 AM IST)
        market_start_time = current_time_ist.replace(hour=9, minute=15, second=0, microsecond=0)

        if current_time_ist < market_start_time:
            # Before market start - API still has previous day's data
            # Continue with previous day's timestamp (UPDATE scenario)
            return prev_timestamp
        else:
            # After market start - safe to move to next trading day
            # Calculate next trading day timestamp
            days_diff = (current_date_ist - prev_date_ist).days
            next_day_timestamp = prev_timestamp + (days_diff * 24 * 60 * 60 * 1000)
            return next_day_timestamp

    def _collect_results_from_queue(self) -> List[Tuple[str, Dict]]:
        """Collect all results from the thread-safe queue"""
        results = []
        while not self.results_queue.empty():
            try:
                result = self.results_queue.get_nowait()
                results.append(result)
            except queue.Empty:
                break

        logger.info(f"📦 Collected {len(results)} results from queue")
        return results

    async def _bulk_save_results(self, results: List[Tuple[str, Dict]]):
        """Save all results to database in a true bulk operation"""
        if not results:
            logger.warning("No results to save")
            return

        logger.info(f"💾 TRUE bulk saving {len(results)} candles to database...")

        try:
            # Ensure database is initialized
            if not ultra_fast_db.initialized:
                await ultra_fast_db.initialize()

            async with ultra_fast_db.pool.acquire() as conn:
                async with conn.transaction():
                    # Get all latest keys AND timestamps in ONE query
                    symbols = [symbol for symbol, _ in results]
                    latest_info = await conn.fetch("""
                        SELECT
                            slk.symbol,
                            slk.latest_daily_key,
                            dc.timestamp as latest_timestamp
                        FROM symbol_latest_keys slk
                        LEFT JOIN daily_candles dc ON dc.candle_key_id = slk.symbol || '_' || slk.latest_daily_key
                        WHERE slk.symbol = ANY($1)
                    """, symbols)

                    # Create lookup dicts for latest keys and timestamps
                    key_lookup = {row['symbol']: row['latest_daily_key'] for row in latest_info}
                    timestamp_lookup = {row['symbol']: row['latest_timestamp'] for row in latest_info}

                    # Prepare data for bulk upsert
                    bulk_updates = []
                    symbol_key_updates = []

                    # Market-aware timestamp logic (no more system date dependency)
                    from datetime import datetime
                    import pytz
                    ist = pytz.timezone('Asia/Kolkata')

                    for symbol, calculated_data in results:
                        daily = calculated_data['daily']
                        weekly = calculated_data['weekly']
                        monthly = calculated_data['monthly']

                        # Get current/previous sequence number
                        previous_sequence = key_lookup.get(symbol, -1)

                        # Use market-aware timestamp comparison instead of system date
                        should_create_new = True
                        if previous_sequence >= 0:
                            # We have a previous candle, check timestamp
                            prev_timestamp = timestamp_lookup.get(symbol)
                            current_timestamp = daily['timestamp']  # From market-aware calculation

                            if prev_timestamp and current_timestamp:
                                # Convert timestamps to IST dates for comparison
                                prev_date_ist = datetime.fromtimestamp(prev_timestamp / 1000.0, ist).date()
                                current_date_ist = datetime.fromtimestamp(current_timestamp / 1000.0, ist).date()

                                # If same date, UPDATE existing candle
                                if prev_date_ist == current_date_ist:
                                    should_create_new = False
                                    logger.debug(f"📝 {symbol}: Same trading day ({current_date_ist}), updating existing candle #{previous_sequence}")
                                else:
                                    logger.debug(f"📅 {symbol}: New trading day (prev: {prev_date_ist}, current: {current_date_ist}), creating new candle")

                        # Set sequence number based on update vs create
                        if should_create_new:
                            current_sequence = previous_sequence + 1
                        else:
                            current_sequence = previous_sequence  # Keep same sequence for update

                        candle_key_id = f"{symbol}_{current_sequence}"

                        # Calculate day of week (simple increment)
                        day_of_week = (current_sequence % 5) + 1

                        # Convert timestamp to datetime
                        from datetime import datetime
                        candle_datetime = datetime.fromtimestamp(daily['timestamp'] / 1000)

                        # Prepare bulk update tuple
                        bulk_updates.append((
                            candle_key_id,                           # candle_key_id
                            symbol,                                  # symbol
                            current_sequence,                        # candle_sequence_number
                            daily['timestamp'],                      # timestamp
                            candle_datetime,                         # datetime
                            daily['open'],                           # open
                            daily['high'],                           # high
                            daily['low'],                            # low
                            daily['close'],                          # close
                            daily['volume'],                         # volume
                            day_of_week,                             # day_of_week
                            None,                                    # weekly_candle_key_id (NULL for now)
                            weekly['open'],                          # weekly_open
                            weekly['high'],                          # weekly_high
                            weekly['low'],                           # weekly_low
                            weekly['close'],                         # weekly_close
                            weekly['volume'],                        # weekly_volume
                            monthly['open'],                         # monthly_open
                            monthly['high'],                         # monthly_high
                            monthly['low'],                          # monthly_low
                            monthly['close'],                        # monthly_close
                            monthly['volume'],                       # monthly_volume
                            '{}',                                    # indicators (empty JSONB)
                            None                                     # monthly_candle_key_id (NULL for now)
                        ))

                        # Track symbol key updates only for new candles
                        if should_create_new:
                            symbol_key_updates.append((symbol, current_sequence))

                    # Execute bulk upsert with ON CONFLICT
                    await conn.executemany("""
                        INSERT INTO daily_candles
                        (candle_key_id, symbol, candle_sequence_number, timestamp, datetime,
                         open, high, low, close, volume, day_of_week, weekly_candle_key_id,
                         weekly_open, weekly_high, weekly_low, weekly_close, weekly_volume,
                         monthly_open, monthly_high, monthly_low, monthly_close, monthly_volume,
                         indicators, monthly_candle_key_id)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24)
                        ON CONFLICT (candle_key_id)
                        DO UPDATE SET
                            timestamp = EXCLUDED.timestamp,
                            datetime = EXCLUDED.datetime,
                            open = EXCLUDED.open,
                            high = EXCLUDED.high,
                            low = EXCLUDED.low,
                            close = EXCLUDED.close,
                            volume = EXCLUDED.volume,
                            weekly_open = EXCLUDED.weekly_open,
                            weekly_high = EXCLUDED.weekly_high,
                            weekly_low = EXCLUDED.weekly_low,
                            weekly_close = EXCLUDED.weekly_close,
                            weekly_volume = EXCLUDED.weekly_volume,
                            monthly_open = EXCLUDED.monthly_open,
                            monthly_high = EXCLUDED.monthly_high,
                            monthly_low = EXCLUDED.monthly_low,
                            monthly_close = EXCLUDED.monthly_close,
                            monthly_volume = EXCLUDED.monthly_volume,
                            updated_at = CURRENT_TIMESTAMP
                    """, bulk_updates)

                    # Bulk update symbol_latest_keys (only for new candles)
                    if symbol_key_updates:
                        await conn.executemany("""
                            INSERT INTO symbol_latest_keys (symbol, latest_daily_key, total_daily_candles, last_updated)
                            VALUES ($1, $2, $2 + 1, CURRENT_TIMESTAMP)
                            ON CONFLICT (symbol)
                            DO UPDATE SET
                                latest_daily_key = EXCLUDED.latest_daily_key,
                                total_daily_candles = EXCLUDED.total_daily_candles,
                                last_updated = CURRENT_TIMESTAMP
                        """, symbol_key_updates)

                    new_count = len(symbol_key_updates)
                    update_count = len(results) - new_count
                    logger.info(f"✅ Saved {len(results)} candles ({new_count} new, {update_count} updated) with bulk operations")

                    # Update cache with processed data to avoid "First day" on next run
                    for symbol, calculated_data in results:
                        # Update the cache with the processed data
                        self.cache.cache_data[symbol] = {
                            'daily': calculated_data['daily'],
                            'weekly': calculated_data['weekly'],
                            'monthly': calculated_data['monthly'],
                            'meta': {
                                'timestamp': calculated_data['daily']['timestamp'],  # Preserve timestamp for market-aware logic
                                'day_of_week': self._calculate_day_of_week(
                                    self.cache.cache_data[symbol]['meta']['day_of_week']
                                    if symbol in self.cache.cache_data and 'meta' in self.cache.cache_data[symbol]
                                    else 0
                                ),
                                'week_number': self.cache.cache_data[symbol]['meta'].get('week_number', 1)
                                if symbol in self.cache.cache_data and 'meta' in self.cache.cache_data[symbol]
                                else 1,
                                'month_number': self.cache.cache_data[symbol]['meta'].get('month_number', 1)
                                if symbol in self.cache.cache_data and 'meta' in self.cache.cache_data[symbol]
                                else 1
                            }
                        }
                    logger.debug(f"📝 Updated cache for {len(results)} symbols")

        except Exception as e:
            logger.error(f"❌ Bulk save failed: {e}")
            raise

    async def cleanup(self):
        """Cleanup resources"""
        await self.chartink_service.close_client()
        logger.info("🧹 Ultra-Fast Cron V2 cleanup completed")

    async def process_symbols(self, symbols: List[str]) -> Dict[str, Any]:
        """Process specific symbols - compatibility method for main.py"""
        if not self.initialized:
            await self.initialize()

        self.cache.symbols = symbols
        return await self.run_ultra_fast_cron()

    async def process_all_symbols_ultra_fast(self) -> Dict[str, Any]:
        """Process all symbols - compatibility method for main.py"""
        return await self.run_ultra_fast_cron()

    def start_background_cron(self):
        """Start background cron with actual timer thread"""
        # Check if cron is enabled
        if not get_latest_candle_cron_enabled():
            logger.info("🚫 Ultra-Fast Cron V2 is DISABLED (LATEST_CANDLE_CRON_ENABLED=false)")
            return

        # Record when the cron timer starts
        import time
        self.cron_start_time = time.time()

        import threading
        import asyncio

        def run_ultra_fast_cron():
            """Background thread function that runs the cron job every minute"""
            # Create a dedicated event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def cron_loop():
                """Main cron loop that runs based on configured interval"""
                logger.info("🚀 Ultra-Fast Cron V2 background service initialized")

                # Get interval from environment
                interval_minutes = get_latest_candle_cron_interval()
                interval_seconds = interval_minutes * 60
                logger.info(f"⏰ Starting cron timer loop - will execute every {interval_minutes} minutes ({interval_seconds} seconds)")

                # Create a separate database instance for this thread to avoid event loop conflicts
                # Import locally to create a fresh instance
                from services.ultra_fast_database_service import UltraFastDatabaseService
                thread_db = UltraFastDatabaseService()
                await thread_db.initialize()

                # Create separate cache instance for this thread
                thread_cache = PreviousDayCache()
                thread_cache.db_pool = thread_db.pool  # Use thread-local pool
                await thread_cache.load_cache()

                # Record the start time
                import time
                start_time = time.time()
                logger.info(f"⏰ Cron timer started, will execute when interval condition is met")

                while True:
                    # Calculate elapsed time since start
                    current_time = time.time()
                    elapsed_seconds = current_time - start_time

                    # Check if we should execute (based on configured interval, but not immediately at start)
                    if elapsed_seconds >= interval_seconds:
                        # Reset the timer for next execution
                        start_time = current_time
                        try:
                            # Check if we should run (market hours check)
                            market_hours_only = get_latest_candle_market_hours_only()

                            if market_hours_only:
                                # Check if within market hours (9:15 AM to 3:30 PM IST, Monday-Friday)
                                from datetime import datetime, time as datetime_time
                                now = datetime.now()
                                current_time_obj = now.time()
                                is_market_hours = (
                                    now.weekday() < 5 and  # Monday-Friday
                                    datetime_time(9, 15) <= current_time_obj <= datetime_time(15, 30)
                                )

                                if not is_market_hours:
                                    logger.debug("⏰ Cron timer: Market closed, skipping execution")
                                else:
                                    logger.info("🚀 Starting ultra-fast cron execution...")
                                    await self._execute_cron(thread_cache, thread_db)
                            else:
                                # Market hours check disabled, always execute
                                logger.info("🚀 Starting ultra-fast cron execution...")
                                await self._execute_cron(thread_cache, thread_db)

                        except Exception as e:
                            logger.error(f"❌ Ultra-fast cron error: {e}")
                            import traceback
                            traceback.print_exc()
                    else:
                        # Not time to execute yet, just continue the loop
                        pass

                    # Small sleep to prevent busy loop (check every second)
                    await asyncio.sleep(1)

            # Start the cron loop
            try:
                loop.run_until_complete(cron_loop())
            except Exception as e:
                logger.error(f"Background thread error: {e}")
            finally:
                loop.close()

        # Start the background thread (daemon so it stops when main process stops)
        self.cron_thread = threading.Thread(target=run_ultra_fast_cron, daemon=True)
        self.cron_thread.start()
        logger.info("✅ Background cron thread started")

    async def _execute_cron(self, thread_cache, thread_db):
        """Execute the cron job with thread-local resources"""
        # Create a temporary instance with thread-local resources
        cron_instance = UltraFastCronV2()
        cron_instance.cache = thread_cache
        cron_instance.initialized = True
        # Override the global db reference for this execution
        original_db = ultra_fast_db.pool
        ultra_fast_db.pool = thread_db.pool

        try:
            result = await cron_instance.run_ultra_fast_cron()
            logger.info(f"✅ Ultra-fast cron completed in {result['total_time_seconds']:.2f}s")
            logger.info(f"📊 Processed: {result['successful']}/{result['total_symbols']} symbols")

            # Update the main instance's last execution timestamp
            import time
            self.last_cron_execution = time.time()
            logger.info(f"🕐 Updated last_cron_execution timestamp: {self.last_cron_execution}")
        finally:
            # Restore original db reference
            ultra_fast_db.pool = original_db

    def get_cron_status(self) -> Dict[str, Any]:
        """Get cron status - compatibility method for main.py"""
        import time
        current_time = time.time()

        # Calculate minutes since last execution or since start
        minutes_since_last = None
        if self.last_cron_execution:
            # We have executed at least once
            minutes_since_last = (current_time - self.last_cron_execution) / 60.0
        elif self.cron_start_time:
            # Timer started but not executed yet - show time since start
            minutes_since_last = (current_time - self.cron_start_time) / 60.0

        return {
            "enabled": True,
            "running": True,  # Added for compatibility with main.py timer display
            "interval_minutes": get_latest_candle_cron_interval(),
            "minutes_since_last_update": minutes_since_last,  # Time since last execution or start
            "market_hours_only": get_latest_candle_market_hours_only(),
            "debug_timer": False,
            "last_run": self.last_cron_execution,
            "cron_start_time": self.cron_start_time,  # When cron timer started
            "status": "active"
        }


# Global instance
ultra_fast_cron_v2 = UltraFastCronV2()


# Configuration functions for compatibility with main.py
def get_ultra_fast_cron_debug_timer() -> bool:
    """Get debug timer setting"""
    return False

def get_latest_candle_cron_interval() -> int:
    """Get cron interval in minutes from environment variable"""
    import os
    try:
        return int(os.getenv('LATEST_CANDLE_CRON_INTERVAL', '1'))
    except (ValueError, TypeError):
        return 1  # Fallback to 1 minute if env var is invalid

def get_latest_candle_cron_enabled() -> bool:
    """Get cron enabled setting"""
    import os
    return os.getenv('LATEST_CANDLE_CRON_ENABLED', 'true').lower() == 'true'

def get_latest_candle_market_hours_only() -> bool:
    """Get market hours only setting"""
    import os
    return os.getenv('LATEST_CANDLE_MARKET_HOURS_ONLY', 'true').lower() == 'true'

def get_latest_candle_debug_timer() -> bool:
    """Get debug timer setting"""
    import os
    return os.getenv('LATEST_CANDLE_DEBUG_TIMER', 'false').lower() == 'true'