"""
Latest Candle Updater Service
Background cron job that fetches and updates latest candle (today's data) for all symbols
Maintains consistency with hard refresh logic but for incremental updates
Runs automatically as a background service - not triggered from frontend
"""

import asyncio
import logging
import os
import threading
import time
from datetime import datetime, timezone, time as datetime_time
from typing import List, Dict, Any, Optional
from .chartink_service import ChartinkService
from .db_wrapper import db_wrapper as db_service
from .ultra_fast_database_service import ultra_fast_db
# Removed STOCK_SYMBOLS import - now dynamically gets symbols from database

logger = logging.getLogger(__name__)

def get_latest_candle_cron_enabled() -> bool:
    """Get latest candle cron job enabled flag from environment."""
    try:
        enabled = os.getenv('LATEST_CANDLE_CRON_ENABLED', 'true').lower()  # Default to true for auto-start
        return enabled in ('true', '1', 'yes', 'on')
    except Exception:
        return True  # Default to true if there's an error

def get_latest_candle_cron_interval() -> int:
    """Get latest candle cron job interval in minutes from environment."""
    try:
        return int(os.getenv('LATEST_CANDLE_CRON_INTERVAL', '1'))  # Default 1 minute for testing
    except (ValueError, TypeError):
        return 1

def get_latest_candle_market_hours_only() -> bool:
    """Get whether to run only during market hours from environment."""
    try:
        market_only = os.getenv('LATEST_CANDLE_MARKET_HOURS_ONLY', 'false').lower()  # Default false for testing
        return market_only in ('true', '1', 'yes', 'on')
    except Exception:
        return False

def get_latest_candle_debug_timer() -> bool:
    """Get whether to show debug timer in console from environment."""
    try:
        debug_timer = os.getenv('LATEST_CANDLE_DEBUG_TIMER', 'true').lower()
        return debug_timer in ('true', '1', 'yes', 'on')
    except Exception:
        return True

class LatestCandleUpdater:
    """
    Background cron job service to update latest candle for all symbols.
    Uses same logic as hard refresh but fetches only 1 candle per symbol.
    Runs automatically based on environment configuration.
    """

    def __init__(self):
        self.chartink_service = ChartinkService()
        self.is_running = False
        self._update_task = None
        self._cron_enabled = get_latest_candle_cron_enabled()
        self._cron_interval = get_latest_candle_cron_interval()
        self._market_hours_only = get_latest_candle_market_hours_only()
        self._cron_thread = None
        self._stop_cron = threading.Event()
        self._last_update_time = None

    def start_background_cron(self):
        """Start the background cron job thread."""
        print(f"[CONFIG] Checking cron job configuration...")
        print(f"   - Enabled: {self._cron_enabled}")
        print(f"   - Interval: {self._cron_interval} minutes")
        print(f"   - Market hours only: {self._market_hours_only}")

        if not self._cron_enabled:
            print("[DISABLED] Latest candle cron job is DISABLED (LATEST_CANDLE_CRON_ENABLED=false)")
            logger.info("[DISABLED] Latest candle cron job is DISABLED (LATEST_CANDLE_CRON_ENABLED=false)")
            return

        if self._cron_thread and self._cron_thread.is_alive():
            print("[WARNING] Latest candle cron job already running")
            logger.warning("[WARNING] Latest candle cron job already running")
            return

        print(f"[START] Starting latest candle cron job - Interval: {self._cron_interval} minutes, Market hours only: {self._market_hours_only}")
        logger.info(f"[START] Starting latest candle cron job - Interval: {self._cron_interval} minutes, Market hours only: {self._market_hours_only}")

        self._stop_cron.clear()
        self._cron_thread = threading.Thread(target=self._run_cron_job, daemon=True)
        self._cron_thread.start()

        print(f"[OK] Cron job thread started successfully (Thread ID: {self._cron_thread.ident})")
        logger.info(f"[OK] Cron job thread started successfully")

    def stop_background_cron(self):
        """Stop the background cron job."""
        if self._cron_thread and self._cron_thread.is_alive():
            logger.info("🛑 Stopping latest candle cron job...")
            self._stop_cron.set()
            if self._cron_thread:
                self._cron_thread.join(timeout=5)
            logger.info("[OK] Latest candle cron job stopped")

    def _run_cron_job(self):
        """Background thread that runs the cron job."""
        print(f"[THREAD] Cron job thread STARTED (PID: {os.getpid()}, Thread: {threading.current_thread().ident})")
        logger.info(f"[THREAD] Latest candle cron job started (PID: {os.getpid()})")

        iteration_count = 0
        while not self._stop_cron.is_set():
            try:
                iteration_count += 1
                current_time = datetime.now()

                # Log every 10 iterations for debugging
                if iteration_count % 10 == 1:
                    print(f"[UPDATE] Cron job loop iteration {iteration_count} at {current_time.strftime('%H:%M:%S')}")

                current_time = datetime.now()

                # Check if we should run based on market hours setting
                should_run = True
                if self._market_hours_only:
                    should_run = self._is_market_hours(current_time)

                if should_run:
                    # Check if enough time has passed since last update
                    if self._should_run_update(current_time):
                        # Clear the debug line and start update
                        print()  # New line to clear debug timer
                        logger.info("⏰ Cron job triggered - Starting latest candle update...")

                        update_start_time = datetime.now()

                        # Run the update in a new event loop (since we're in a thread)
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                        try:
                            # Force re-initialization of database services in this thread's event loop
                            result = loop.run_until_complete(self._initialize_and_update())

                            if result["success"]:
                                self._last_update_time = current_time
                                stats = result["statistics"]
                                logger.info(f"[OK] Cron job completed: {stats['successful']}/{stats['total_symbols']} symbols updated in {stats['duration_seconds']:.1f}s")
                                logger.info(f"📊 Update stats: Weekly: {stats['weekly_updated']}, Monthly: {stats['monthly_updated']}, Speed: {stats['symbols_per_second']:.1f} symbols/sec")

                                # Log any failed symbols for debugging
                                if stats['failed'] > 0 and 'failed_symbols' in result:
                                    logger.warning(f"⚠️ Failed symbols ({stats['failed']}): {', '.join(result['failed_symbols'][:5])}")
                            else:
                                logger.error(f"[ERROR] Cron job failed: {result['message']}")

                        finally:
                            # Clean up database connections to prevent connection limit issues
                            try:
                                loop.run_until_complete(self._cleanup_connections())
                            except Exception as cleanup_error:
                                logger.warning(f"Connection cleanup warning: {cleanup_error}")
                            finally:
                                loop.close()
                    else:
                        # Not time yet, just log occasionally
                        minutes_since_last = self._minutes_since_last_update(current_time)
                        if minutes_since_last is not None and int(minutes_since_last) % 5 == 0:
                            next_run_mins = self._cron_interval - minutes_since_last
                            logger.debug(f"📊 Cron job waiting... Next run in {next_run_mins:.1f} minutes")

                else:
                    # Outside market hours, log occasionally
                    if current_time.minute % 30 == 0 and current_time.second < 10:
                        logger.debug(f"🌙 Latest candle cron job waiting for market hours (currently {current_time.strftime('%H:%M')})")

                # Sleep for 10 seconds before next check
                if not self._stop_cron.wait(10):
                    continue
                else:
                    break

            except Exception as e:
                logger.error(f"[ERROR] Cron job error: {e}")
                # Sleep for a bit before retrying
                if not self._stop_cron.wait(60):
                    continue
                else:
                    break

        logger.info("[DISABLED] Latest candle cron job thread exited")

    def _should_run_update(self, current_time: datetime) -> bool:
        """Check if enough time has passed to run another update."""
        if self._last_update_time is None:
            return True

        minutes_since_last = self._minutes_since_last_update(current_time)
        return minutes_since_last is not None and minutes_since_last >= self._cron_interval

    def _minutes_since_last_update(self, current_time: datetime) -> Optional[float]:
        """Get minutes since last update."""
        if self._last_update_time is None:
            return None
        return (current_time - self._last_update_time).total_seconds() / 60

    def _is_market_hours(self, current_time: datetime) -> bool:
        """Check if current time is within market hours (9:15 AM - 3:30 PM IST, Monday-Friday)."""
        try:
            # Check if it's a weekday (Monday=0, Sunday=6)
            if current_time.weekday() >= 5:  # Saturday=5, Sunday=6
                return False

            # Check time (assuming system time is in IST)
            current_time_obj = current_time.time()
            market_start = datetime_time(9, 15)  # 9:15 AM
            market_end = datetime_time(15, 30)   # 3:30 PM

            return market_start <= current_time_obj <= market_end

        except Exception as e:
            logger.error(f"Error checking market hours: {e}")
            return False

    def get_cron_status(self) -> Dict[str, Any]:
        """Get current status of the cron job."""
        return {
            "enabled": self._cron_enabled,
            "running": self._cron_thread is not None and self._cron_thread.is_alive(),
            "interval_minutes": self._cron_interval,
            "market_hours_only": self._market_hours_only,
            "last_update_time": self._last_update_time.isoformat() if self._last_update_time else None,
            "minutes_since_last_update": self._minutes_since_last_update(datetime.now()),
            "is_market_hours": self._is_market_hours(datetime.now())
        }

    async def _initialize_and_update(self) -> Dict[str, Any]:
        """
        Initialize database services in the current event loop and then update candles.
        This ensures the database connections are created in the correct event loop.
        """
        try:
            # Force re-initialization by temporarily resetting the initialized flag
            # This ensures new connection pools are created in this thread's event loop

            # Reset db_service wrapper status
            db_service._init_attempted = False

            # Reset ultra_fast_db initialization status to force recreation of pools in this event loop
            ultra_fast_db.initialized = False

            # Close existing pools if they exist (they're tied to the main event loop)
            if ultra_fast_db.pool:
                try:
                    await ultra_fast_db.pool.close()
                    ultra_fast_db.pool = None
                    logger.debug("🔄 Closed existing database pool from main event loop")
                except Exception as e:
                    # This warning is expected when switching event loops - suppress it
                    if "attached to a different loop" in str(e):
                        logger.debug("🔄 Skipping pool closure (different event loop) - will create new pool")
                    else:
                        logger.debug(f"Could not close existing ultra_fast_db pool: {e}")

            # Now initialize in this event loop
            await db_service.initialize()
            await ultra_fast_db.initialize()

            logger.debug("🔄 Database services re-initialized in background thread event loop")

            # Run the actual update
            result = await self.update_latest_candles_for_all_symbols()

            return result

        except Exception as e:
            logger.error(f"❌ Failed to initialize and update in background thread: {e}")
            return {
                "success": False,
                "message": f"Initialization error: {str(e)}",
                "statistics": {
                    "total_symbols": 0,
                    "successful": 0,
                    "failed": 0,
                    "weekly_updated": 0,
                    "monthly_updated": 0,
                    "duration_seconds": 0,
                    "symbols_per_second": 0
                }
            }

        finally:
            # Always clean up connections, even on exceptions
            try:
                await self._cleanup_connections()
            except Exception as cleanup_error:
                logger.debug(f"Connection cleanup error in _initialize_and_update: {cleanup_error}")

    async def update_latest_candles_for_all_symbols(self, progress_callback=None) -> Dict[str, Any]:
        """
        Update latest candle for all symbols in STOCK_SYMBOLS.

        Args:
            progress_callback: Optional callback function for progress updates

        Returns:
            Dict with update results and statistics
        """
        if self.is_running:
            return {
                "success": False,
                "message": "Latest candle update is already running",
                "status": "already_running"
            }

        self.is_running = True
        start_time = datetime.now()

        try:
            logger.info("[UPDATE] Starting latest candle update for all symbols")

            # Initialize database services
            await db_service.initialize()
            await ultra_fast_db.initialize()

            # Get all symbols that exist in daily_candles table (dynamic, not hardcoded)
            async with ultra_fast_db.get_connection() as conn:
                symbol_rows = await conn.fetch("""
                    SELECT DISTINCT symbol
                    FROM daily_candles
                    ORDER BY symbol
                """)
                symbols = [row['symbol'] for row in symbol_rows]

            if not symbols:
                logger.warning("⚠️ No symbols found in daily_candles table")
                return {
                    "success": False,
                    "message": "No symbols found in daily_candles table",
                    "statistics": {
                        "total_symbols": 0,
                        "successful": 0,
                        "failed": 0,
                        "weekly_updated": 0,
                        "monthly_updated": 0,
                        "duration_seconds": 0,
                        "symbols_per_second": 0
                    }
                }

            total_symbols = len(symbols)
            logger.info(f"🔍 Found {total_symbols} symbols in daily_candles table for latest candle update")
            processed = 0
            successful = 0
            failed = 0
            failed_symbols = []

            logger.info(f"📊 Updating latest candle for {total_symbols} symbols")

            # Create payload for latest candle only (limit=1)
            payload = [[str(datetime.now().timestamp()), symbol] for symbol in symbols]

            # Progress tracking
            async def progress_tracker(symbol: str, success: bool):
                nonlocal processed, successful, failed
                processed += 1
                if success:
                    successful += 1
                    logger.debug(f"[OK] {symbol}: Latest candle updated successfully")
                else:
                    failed += 1
                    failed_symbols.append(symbol)
                    logger.warning(f"[ERROR] {symbol}: Latest candle update failed")

                # Call external progress callback if provided
                if progress_callback:
                    await progress_callback(symbol, success, processed, total_symbols)

                # Log progress every 100 symbols or at key milestones
                if processed % 100 == 0 or processed == total_symbols:
                    percentage = int((processed / total_symbols) * 100)
                    logger.info(f"📈 Progress: {processed}/{total_symbols} ({percentage}%) - Success: {successful}, Failed: {failed}")

            # Process all symbols with limit=1 to get only latest candle
            logger.info("🚀 Starting data fetch for latest candles...")

            # Use the same chartink service but with size=1 for latest candle only
            results = await self.chartink_service.process_payload(
                payload=payload,
                concurrent_limit=20,  # Same concurrency as hard refresh
                progress_callback=progress_tracker,
                size=1  # Hard-coded to 1 for latest candle only
            )

            # After fetching daily data, update weekly and monthly candles
            logger.info("📅 Updating weekly and monthly candles...")
            weekly_updated = 0
            monthly_updated = 0

            for symbol in symbols:
                if symbol in results and "Success" in str(results[symbol]):
                    try:
                        # Update weekly candles for this symbol
                        weekly_result = await self._update_weekly_candles_for_symbol(symbol)
                        if weekly_result:
                            weekly_updated += 1

                        # Update monthly candles for this symbol
                        monthly_result = await self._update_monthly_candles_for_symbol(symbol)
                        if monthly_result:
                            monthly_updated += 1

                    except Exception as e:
                        logger.error(f"[ERROR] Failed to update weekly/monthly candles for {symbol}: {e}")

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            result = {
                "success": True,
                "message": f"Latest candle update completed for {total_symbols} symbols",
                "statistics": {
                    "total_symbols": total_symbols,
                    "processed": processed,
                    "successful": successful,
                    "failed": failed,
                    "weekly_updated": weekly_updated,
                    "monthly_updated": monthly_updated,
                    "duration_seconds": duration,
                    "symbols_per_second": round(processed / duration, 2) if duration > 0 else 0
                },
                "failed_symbols": failed_symbols,
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "status": "completed"
            }

            logger.info(f"[OK] Latest candle update completed in {duration:.2f}s")
            logger.info(f"📊 Results: {successful} successful, {failed} failed out of {total_symbols} symbols")
            logger.info(f"📅 Weekly candles updated: {weekly_updated}, Monthly candles updated: {monthly_updated}")

            return result

        except Exception as e:
            logger.error(f"[ERROR] Latest candle update failed: {e}")
            return {
                "success": False,
                "message": f"Latest candle update failed: {str(e)}",
                "error": str(e),
                "status": "error"
            }
        finally:
            self.is_running = False

    async def _update_weekly_candles_for_symbol(self, symbol: str) -> bool:
        """
        Update weekly candles for a specific symbol using stored procedure.
        Same logic as hard refresh but for single symbol.
        """
        try:
            async with ultra_fast_db.get_connection() as conn:
                # Call the same stored procedure used in hard refresh
                result = await conn.fetchrow(
                    "SELECT * FROM generate_weekly_candles_for_symbol($1)",
                    symbol
                )

            if result and result['status'] == 'SUCCESS':
                logger.debug(f"[OK] Weekly candles updated for {symbol}: {result['generated_weeks']} weeks")
                return True
            else:
                logger.warning(f"⚠️ Weekly candle update failed for {symbol}: {result}")
                return False

        except Exception as e:
            logger.error(f"[ERROR] Weekly candle update error for {symbol}: {e}")
            return False

    async def _update_monthly_candles_for_symbol(self, symbol: str) -> bool:
        """
        Update monthly candles for a specific symbol using stored procedure.
        Same logic as hard refresh but for single symbol.
        """
        try:
            async with ultra_fast_db.get_connection() as conn:
                # Call the same stored procedure used in hard refresh
                result = await conn.fetchrow(
                    "SELECT * FROM generate_monthly_candles_for_symbol($1)",
                    symbol
                )

            if result and result['status'] == 'SUCCESS':
                logger.debug(f"[OK] Monthly candles updated for {symbol}: {result['generated_months']} months")
                return True
            else:
                logger.warning(f"⚠️ Monthly candle update failed for {symbol}: {result}")
                return False

        except Exception as e:
            logger.error(f"[ERROR] Monthly candle update error for {symbol}: {e}")
            return False

    async def update_latest_candle_single_symbol(self, symbol: str) -> Dict[str, Any]:
        """
        Update latest candle for a single symbol.
        Useful for targeted updates or testing.

        Args:
            symbol: Stock symbol to update

        Returns:
            Dict with update result
        """
        try:
            logger.info(f"[UPDATE] Updating latest candle for symbol: {symbol}")

            # Initialize database services
            await db_service.initialize()
            await ultra_fast_db.initialize()

            # Create payload for single symbol with limit=1
            payload = [[str(datetime.now().timestamp()), symbol]]

            # Fetch latest candle
            results = await self.chartink_service.process_payload(
                payload=payload,
                size=1  # Hard-coded to 1 for latest candle only
            )

            if symbol in results and "Success" in str(results[symbol]):
                # Update weekly and monthly candles
                weekly_updated = await self._update_weekly_candles_for_symbol(symbol)
                monthly_updated = await self._update_monthly_candles_for_symbol(symbol)

                return {
                    "success": True,
                    "symbol": symbol,
                    "message": f"Latest candle updated successfully for {symbol}",
                    "daily_updated": True,
                    "weekly_updated": weekly_updated,
                    "monthly_updated": monthly_updated,
                    "raw_result": results[symbol]
                }
            else:
                return {
                    "success": False,
                    "symbol": symbol,
                    "message": f"Failed to update latest candle for {symbol}",
                    "error": results.get(symbol, "Unknown error")
                }

        except Exception as e:
            logger.error(f"[ERROR] Single symbol update failed for {symbol}: {e}")
            return {
                "success": False,
                "symbol": symbol,
                "message": f"Exception during update: {str(e)}",
                "error": str(e)
            }

    async def _cleanup_connections(self):
        """Clean up database connections to prevent connection limit issues."""
        try:
            # Close ultra_fast_db connections
            if ultra_fast_db.pool:
                await ultra_fast_db.pool.close()
                ultra_fast_db.pool = None
                ultra_fast_db.initialized = False
                logger.debug("🧹 Closed ultra_fast_db connection pool")

            # Close db_service connections
            if db_service.initialized:
                await db_service.close()
                logger.debug("🧹 Closed db_service connections")

            # Close chartink service connections
            from services.chartink_service import ChartinkService
            chartink = ChartinkService()
            await chartink.close_all_clients()
            logger.debug("🧹 Closed chartink service HTTP clients")

        except Exception as e:
            logger.debug(f"Connection cleanup error (non-critical): {e}")

    def stop_updates(self):
        """Stop any running update tasks and cron job."""
        # Stop cron job
        self.stop_background_cron()

        # Stop any pending update tasks
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
        self.is_running = False
        logger.info("🛑 Latest candle updater stopped")

# Global instance
latest_candle_updater = LatestCandleUpdater()