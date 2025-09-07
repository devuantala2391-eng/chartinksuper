import asyncio
import logging
import threading
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Any
from services.chartink_service import ChartinkService
from utils.constants import STOCK_SYMBOLS
from services.latest_day_precalculator import latest_day_precalculator
from services.db_wrapper import db_wrapper as db_service

logger = logging.getLogger(__name__)

class LatestCandleUpdater:
    """
    Service for updating latest candle data periodically.
    Manages periodic updates during market hours.
    """
    
    def __init__(self):
        self.chartink_service = ChartinkService()
        self.is_running = False
        self.lock = threading.Lock()
        self.force_run = False
        self.update_interval = 2
        self._stop_event = None
        self._update_task = None
        
    async def update_all_symbols(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """Update latest candles for specified symbols or all symbols."""
        try:
            target_symbols = symbols if symbols else STOCK_SYMBOLS
            
            results = {
                "success": 0,
                "failed": 0,
                "errors": []
            }
            
            logger.info(f"Updating latest candles for {len(target_symbols)} symbols...")
            
            for symbol in target_symbols:
                try:
                    # Fetch latest data for the symbol
                    data = await self.chartink_service.fetch_stock_data(symbol, size=1)
                    
                    if data and len(data) > 0:
                        # Process and save the latest candle
                        await latest_day_precalculator.process_symbol_data(symbol, data)
                        results["success"] += 1
                        logger.debug(f"Successfully updated {symbol}")
                    else:
                        logger.warning(f"No data received for {symbol}")
                        results["failed"] += 1
                        results["errors"].append({
                            "symbol": symbol,
                            "error": "No data received"
                        })
                        
                except Exception as e:
                    logger.error(f"Error updating {symbol}: {str(e)}")
                    results["failed"] += 1
                    results["errors"].append({
                        "symbol": symbol,
                        "error": str(e)
                    })
            
            logger.info(f"Latest candle update completed: {results['success']} success, {results['failed']} failed")
            return results
            
        except Exception as e:
            logger.error(f"Error in update_all_symbols: {str(e)}")
            return {
                "success": 0,
                "failed": len(symbols) if symbols else len(STOCK_SYMBOLS),
                "errors": [{"symbol": "all", "error": str(e)}]
            }
    
    async def start_periodic_updates(self, interval_minutes: int = 2, force_run: bool = False):
        """Start periodic updates of latest candles."""
        with self.lock:
            if self.is_running:
                logger.warning("Periodic updates already running")
                return
                
            self.is_running = True
            self.force_run = force_run
            self.update_interval = interval_minutes
            
        self._stop_event = asyncio.Event()
        
        try:
            logger.info(f"Starting periodic latest candle updates every {interval_minutes} minutes")
            
            while not self._stop_event.is_set():
                try:
                    # Check if we should run (market hours or force_run)
                    if self.force_run or self._is_market_hours():
                        logger.info("Running periodic latest candle update...")
                        results = await self.update_all_symbols()
                        logger.info(f"Periodic update completed: {results['success']} success, {results['failed']} failed")
                    else:
                        logger.debug("Skipping update - outside market hours")
                    
                    # Wait for next interval or stop signal
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=interval_minutes * 60)
                        break  # Stop event was set
                    except asyncio.TimeoutError:
                        continue  # Timeout reached, continue with next update
                        
                except Exception as e:
                    logger.error(f"Error in periodic update: {str(e)}")
                    
        except asyncio.CancelledError:
            logger.info("Periodic updates cancelled")
        finally:
            with self.lock:
                self.is_running = False
                self._stop_event = None
            logger.info("Periodic latest candle updates stopped")
    
    def stop_periodic_updates(self):
        """Stop periodic updates."""
        with self.lock:
            if not self.is_running:
                logger.info("Periodic updates not running")
                return
                
            if self._stop_event:
                self._stop_event.set()
                
            logger.info("Stopping periodic latest candle updates...")
    
    def _is_market_hours(self) -> bool:
        """Check if current time is within market hours (9:15 AM - 3:30 PM IST)."""
        try:
            now = datetime.now()
            market_start = time(9, 15)
            market_end = time(15, 30)
            current_time = now.time()
            
            # Check if current time is between market hours
            return market_start <= current_time <= market_end
            
        except Exception as e:
            logger.error(f"Error checking market hours: {str(e)}")
            return False

# Create singleton instance
latest_candle_updater = LatestCandleUpdater()