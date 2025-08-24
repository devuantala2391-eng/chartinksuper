import asyncio
import logging
import json
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime
import hashlib
from pathlib import Path

from services.db_wrapper import db_wrapper as db_service
from services.optimized_processor import optimized_processor
from services.indicator_metadata_service import indicator_metadata_service
from services.postgres_indicator_service import postgres_indicator_service
from services.postgres_indicator_framework import postgres_indicator_framework
from utils.constants import STOCK_SYMBOLS

logger = logging.getLogger(__name__)

class DynamicIndicatorManager:
    """
    Intelligent system for dynamic indicator calculation and management.
    
    Features:
    - Detects missing indicators from query failures
    - Auto-calculates new indicators for all stocks
    - Permanently adds to precalculation system
    - Maintains indicator registry in database
    - Ensures future scheduler runs include new indicators
    """
    
    def __init__(self):
        self.config_file = Path("python-api/config/dynamic_indicators.json")
        self.ensure_config_directory()
        
        # In-memory cache of active indicators
        self.active_indicators: Set[str] = set()
        self.indicator_definitions: Dict[str, Dict] = {}
        
        # Flag to track if config has been loaded
        self._config_loaded = False
    
    def ensure_config_directory(self):
        """Ensure the config directory exists."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
    
    async def load_indicator_config(self):
        """Load indicator configuration from file and database."""
        if self._config_loaded:
            return
            
        try:
            # Load from file if exists
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    self.indicator_definitions = config.get('indicators', {})
                    self.active_indicators = set(config.get('active_indicators', []))
            
            # Also check database for any stored indicator definitions
            await self.sync_with_database()
            
            self._config_loaded = True
            logger.info(f"Loaded {len(self.active_indicators)} active indicators")
            
        except Exception as e:
            logger.error(f"Failed to load indicator config: {e}")
            # Skip default indicators - calculate on demand only
            logger.info("🚀 Dynamic indicator manager initialized - calculate on demand mode")
            self._config_loaded = True
    
    async def save_indicator_config(self):
        """Save indicator configuration to file and database."""
        try:
            config = {
                'indicators': self.indicator_definitions,
                'active_indicators': list(self.active_indicators),
                'last_updated': datetime.now().isoformat()
            }
            
            # Save to file
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Save to database
            await self.save_to_database(config)
            
            logger.info(f"✅ Saved indicator config with {len(self.active_indicators)} indicators")
            
        except Exception as e:
            logger.error(f"Failed to save indicator config: {e}")
    
    async def sync_with_database(self):
        """Sync indicator definitions with database storage."""
        try:
            if not db_service.initialized:
                await db_service.initialize()
            
            # Create table for indicator definitions if not exists
            await self.create_indicator_registry_table()
            
            # Load any indicators from database
            stored_indicators = await self.load_from_database()
            if stored_indicators:
                self.indicator_definitions.update(stored_indicators.get('indicators', {}))
                self.active_indicators.update(stored_indicators.get('active_indicators', []))
                
        except Exception as e:
            logger.error(f"Database sync failed: {e}")
    
    async def create_indicator_registry_table(self):
        """Create table to store indicator definitions."""
        try:
            # Use ultra-fast database service - NSE database removed
            from services.ultra_fast_database_service import ultra_fast_db
            
            create_table_sql = """
            CREATE TABLE IF NOT EXISTS indicator_registry (
                id SERIAL PRIMARY KEY,
                config_key VARCHAR(50) UNIQUE NOT NULL,
                config_data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
            
            async with ultra_fast_db.pool.acquire() as conn:
                await conn.execute(create_table_sql)
                logger.info("📊 Indicator registry table ready")
                
        except Exception as e:
            logger.error(f"Failed to create indicator registry table: {e}")
    
    async def save_to_database(self, config: Dict):
        """Save indicator config to database."""
        try:
            from services.ultra_fast_database_service import ultra_fast_db
            
            insert_sql = """
            INSERT INTO indicator_registry (config_key, config_data, updated_at)
            VALUES ('dynamic_indicators', $1, CURRENT_TIMESTAMP)
            ON CONFLICT (config_key) 
            DO UPDATE SET config_data = $1, updated_at = CURRENT_TIMESTAMP;
            """
            
            async with ultra_fast_db.pool.acquire() as conn:
                await conn.execute(insert_sql, json.dumps(config))
                
        except Exception as e:
            logger.error(f"Failed to save to database: {e}")
    
    async def load_from_database(self) -> Optional[Dict]:
        """Load indicator config from database."""
        try:
            from services.ultra_fast_database_service import ultra_fast_db
            
            select_sql = "SELECT config_data FROM indicator_registry WHERE config_key = 'dynamic_indicators';"
            
            async with ultra_fast_db.pool.acquire() as conn:
                row = await conn.fetchrow(select_sql)
                if row:
                    return json.loads(row['config_data'])
                    
        except Exception as e:
            logger.error(f"Failed to load from database: {e}")
        
        return None
    
    # Removed initialize_default_indicators - now using on-demand calculation only
    
    def parse_missing_indicator_from_error(self, error_detail: str) -> Optional[Dict]:
        """
        Parse missing indicator from query validation error.
        
        Expected patterns:
        - "RSI_14 not found"
        - "Missing indicator: SMA_50"
        - "SuperTrend_10_3 is not precalculated"
        """
        try:
            # Common patterns to extract indicator info
            patterns = [
                r"([A-Za-z]+)_(\d+)_(\d+dot\d+)",  # SuperTrend_30_1dot1 (decimal format with "dot")
                r"([A-Za-z]+)_(\d+)_(\d+_\d+)",    # SuperTrend_30_1_1 (old decimal format - backward compatibility)
                r"([A-Za-z]+)_(\d+)_(\d+)",        # SuperTrend_30_2 (integer format)
                r"([A-Za-z]+)_(\d+)",              # RSI_14, SMA_20 (single parameter)
                r"([A-Za-z]+)\((\d+)\)",           # RSI(14)
                r"([A-Za-z]+)\s*=\s*(\d+)",        # RSI = 14
            ]
            
            import re
            for pattern in patterns:
                match = re.search(pattern, error_detail)
                if match:
                    groups = match.groups()
                    indicator_name = groups[0].upper()
                    
                    # Build indicator definition
                    if indicator_name in ["RSI", "SMA", "EMA", "WMA"]:
                        return {
                            "name": indicator_name,
                            "params": {"period": int(groups[1])},
                            "timeframe": "daily"
                        }
                    elif indicator_name == "SUPERTREND" and len(groups) >= 3 and groups[2]:
                        # Handle decimal multipliers with new "dot" convention and old "_" format
                        multiplier_str = groups[2]
                        if 'dot' in multiplier_str:
                            # Convert "1dot1" back to 1.1
                            multiplier = float(multiplier_str.replace('dot', '.'))
                        elif '_' in multiplier_str:
                            # Convert "1_1" back to 1.1 (backward compatibility)
                            multiplier = float(multiplier_str.replace('_', '.'))
                        else:
                            multiplier = int(multiplier_str)
                        
                        return {
                            "name": "SuperTrend", 
                            "params": {"period": int(groups[1]), "multiplier": multiplier},
                            "timeframe": "daily"
                        }
                    elif indicator_name == "BOLLINGER" and len(groups) >= 3:
                        return {
                            "name": "BollingerBands",
                            "params": {"period": int(groups[1]), "std_dev": int(groups[2]) if groups[2] else 2},
                            "timeframe": "daily"
                        }
            
            logger.warning(f"Could not parse indicator from error: {error_detail}")
            return None
            
        except Exception as e:
            logger.error(f"Error parsing indicator: {e}")
            return None
    
    def generate_indicator_key(self, indicator_def: Dict) -> str:
        """Generate unique key for indicator definition with unambiguous naming."""
        name = indicator_def['name']
        params = indicator_def.get('params', {})
        timeframe = indicator_def.get('timeframe', 'daily')
        
        if name in ["RSI", "SMA", "EMA", "WMA"]:
            return f"{name}_{params.get('period', 14)}"
        elif name == "SuperTrend":
            period = params.get('period', 10)
            multiplier = params.get('multiplier', 2)
            period_str = str(int(period)) if isinstance(period, float) and period.is_integer() else str(period).replace('.', 'dot')
            multiplier_str = str(int(multiplier)) if isinstance(multiplier, float) and multiplier.is_integer() else str(multiplier).replace('.', 'dot')
            if timeframe != 'daily':
                return f"{timeframe}_supertrend_{period_str}_{multiplier_str}"
            return f"supertrend_{period_str}_{multiplier_str}"
        elif name == "PercentageChange":
            # Simplified format - no longer using lookback parameter
            return f"{timeframe}_pctchg"
        elif name == "BollingerBands":
            return f"Bollinger_{params.get('period', 20)}_{params.get('std_dev', 2)}"
        else:
            # Generic key generation - use "dot" for decimal points to avoid ambiguity
            param_str = "_".join(str(v).replace('.', 'dot') for v in params.values())
            return f"{name}_{param_str}" if param_str else name
    
    async def _check_indicator_coverage(self, indicator_key: str, indicator_def: Dict) -> bool:
        """
        Check if the indicator exists in ALL rows of the database.
        Returns True only if ALL rows have this indicator calculated.
        """
        try:
            from services.ultra_fast_database_service import ultra_fast_db
            
            if not ultra_fast_db.initialized:
                await ultra_fast_db.initialize()
                
            timeframe = indicator_def.get('timeframe', 'daily')
            table_name = f"{timeframe}_candles"
            
            async with ultra_fast_db.pool.acquire() as conn:
                # Get total number of rows in table
                total_rows_result = await conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")
                total_rows = total_rows_result or 0
                
                if total_rows == 0:
                    logger.warning(f"No data found in {table_name} table")
                    return True  # If no data, consider it "covered"
                
                # Count rows where the indicator exists and is not null
                indicator_rows_result = await conn.fetchval(f"""
                    SELECT COUNT(*) FROM {table_name}
                    WHERE indicators ? $1 
                    AND (indicators->$1) IS NOT NULL
                """, indicator_key)
                indicator_rows = indicator_rows_result or 0
                
                coverage_percentage = (indicator_rows / total_rows) * 100
                logger.info(f"Indicator {indicator_key} coverage: {indicator_rows}/{total_rows} rows ({coverage_percentage:.1f}%)")
                
                # Only consider fully calculated if ALL rows have it
                is_fully_covered = indicator_rows == total_rows
                
                if not is_fully_covered:
                    logger.info(f"Indicator {indicator_key} needs calculation: missing from {total_rows - indicator_rows} rows")
                
                return is_fully_covered
                
        except Exception as e:
            logger.error(f"Error checking indicator coverage for {indicator_key}: {e}")
            return False  # If error, assume not covered and force calculation
    
    async def _get_all_symbols_from_database(self, timeframe: str = 'daily') -> List[str]:
        """
        Get all unique symbols from the database for the specified timeframe.
        This ensures we calculate indicators for ALL symbols, not just those in constants.
        """
        try:
            from services.ultra_fast_database_service import ultra_fast_db
            
            if not ultra_fast_db.initialized:
                await ultra_fast_db.initialize()
                
            table_name = f"{timeframe}_candles"
            
            async with ultra_fast_db.pool.acquire() as conn:
                result = await conn.fetch(f"SELECT DISTINCT symbol FROM {table_name}")
                symbols = [row['symbol'] for row in result]
                
                logger.info(f"Found {len(symbols)} unique symbols in {table_name} table")
                return symbols
                
        except Exception as e:
            logger.error(f"Error getting symbols from database: {e}")
            # Fallback to constants if database query fails
            logger.warning("Falling back to constants.py symbols")
            return [s for s in STOCK_SYMBOLS if s]  # Filter out empty strings
    
    async def auto_calculate_missing_indicator(self, error_detail: str) -> bool:
        """
        Automatically calculate and permanently add missing indicator.
        
        Returns True if successfully added, False otherwise.
        """
        try:
            # Ensure config is loaded
            await self.load_indicator_config()
            
            logger.info(f"Analyzing missing indicator from error: {error_detail}")
            
            # Parse the missing indicator
            indicator_def = self.parse_missing_indicator_from_error(error_detail)
            if not indicator_def:
                logger.error("Could not identify missing indicator from error")
                return False
            
            indicator_key = self.generate_indicator_key(indicator_def)
            
            # Check if already exists
            if indicator_key in self.active_indicators:
                logger.info(f"Indicator {indicator_key} already exists")
                return True
            
            logger.info(f"🚀 Auto-calculating new indicator: {indicator_key}")
            logger.info(f"📊 Definition: {indicator_def}")
            
            # Add to active indicators immediately
            self.indicator_definitions[indicator_key] = {
                **indicator_def,
                "description": f"Auto-generated {indicator_def['name']} indicator",
                "auto_added": True,
                "added_at": datetime.now().isoformat()
            }
            self.active_indicators.add(indicator_key)
            
            # Calculate for all stocks
            success = await self.calculate_indicator_for_all_stocks(indicator_key, indicator_def)
            
            if success:
                # Save configuration permanently
                await self.save_indicator_config()
                
                logger.info(f"✅ Successfully added and calculated {indicator_key} for all stocks")
                logger.info(f"📈 Indicator will be included in future scheduler runs")
                return True
            else:
                # Remove from active if calculation failed
                self.active_indicators.discard(indicator_key)
                self.indicator_definitions.pop(indicator_key, None)
                logger.error(f"❌ Failed to calculate {indicator_key}, removed from active list")
                return False
                
        except Exception as e:
            logger.error(f"Auto-calculation failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def calculate_indicator_for_all_stocks(self, indicator_key: str, indicator_def: Dict) -> bool:
        """Calculate the new indicator for all stocks using maximum CPU parallelization."""
        import multiprocessing
        import concurrent.futures
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import time
        
        try:
            start_time = time.time()
            cpu_count = multiprocessing.cpu_count()
            max_workers = min(cpu_count * 2, 32)  # Use 2x CPU cores, capped at 32
            
            # Get all symbols from database instead of using limited STOCK_SYMBOLS
            all_symbols = await self._get_all_symbols_from_database(indicator_def.get('timeframe', 'daily'))
            
            logger.info(f"🚀 HIGH-PERFORMANCE Calculating {indicator_key} for {len(all_symbols)} stocks in database...")
            logger.info(f"💪 Using {max_workers} parallel workers on {cpu_count} CPU cores")
            
            # Prepare indicator list for optimized processor
            indicators = [indicator_def]
            
            # Concurrent data loading phase
            logger.info("📊 Phase 1: Parallel data loading...")
            load_start = time.time()
            
            async def load_stock_data(symbol):
                """Load data for a single stock from high-speed database."""
                try:
                    # Load from ultra-fast database instead of file-based storage
                    from services.ultra_fast_database_service import ultra_fast_db
                    
                    if not ultra_fast_db.initialized:
                        await ultra_fast_db.initialize()
                    
                    # Get available candles from ultra-fast database (work with what we have)
                    # Start with reasonable amount, but system will work with whatever is available
                    max_requested = 200  # Reduced from 500 to be more reasonable
                    candles = await ultra_fast_db.get_last_n_candles(symbol, max_requested, timeframe='daily')
                    
                    if candles:
                        # Convert to format expected by indicator processor
                        stock_data = []
                        for candle in candles:
                            stock_data.append({
                                'timestamp': candle.get('timestamp', 0),
                                'open': candle.get('open', 0),
                                'high': candle.get('high', 0),
                                'low': candle.get('low', 0),
                                'close': candle.get('close', 0),
                                'volume': candle.get('volume', 0)
                            })
                        return (symbol, stock_data, indicators, ["daily"])
                    return None
                except Exception as e:
                    logger.error(f"Failed to load data for {symbol}: {e}")
                    return None
            
            # Load all stock data concurrently with semaphore to control concurrent DB connections
            semaphore = asyncio.Semaphore(50)  # Limit concurrent DB operations
            
            async def load_with_semaphore(symbol):
                async with semaphore:
                    return await load_stock_data(symbol)
            
            # Create tasks for parallel loading
            load_tasks = [load_with_semaphore(symbol) for symbol in all_symbols]
            loaded_data = await asyncio.gather(*load_tasks, return_exceptions=True)
            
            # Filter successful loads
            batch_data = [data for data in loaded_data if data is not None and not isinstance(data, Exception)]
            
            load_time = time.time() - load_start
            logger.info(f"✅ Data loading completed in {load_time:.2f}s - {len(batch_data)}/{len(all_symbols)} stocks loaded")
            
            if not batch_data:
                logger.error("No stock data loaded successfully")
                return False
            
            # Concurrent calculation phase
            logger.info("⚡ Phase 2: Parallel indicator calculation...")
            calc_start = time.time()
            
            # Split data into chunks for parallel processing
            chunk_size = max(1, len(batch_data) // max_workers)
            chunks = [batch_data[i:i + chunk_size] for i in range(0, len(batch_data), chunk_size)]
            
            def process_chunk_sync(chunk):
                """Process a chunk of stocks synchronously (for thread pool)."""
                try:
                    return optimized_processor.process_stock_batch_optimized(chunk)
                except Exception as e:
                    logger.error(f"Chunk processing error: {e}")
                    return []
            
            # Process chunks in parallel using thread pool
            all_results = []
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_chunk = {executor.submit(process_chunk_sync, chunk): chunk for chunk in chunks}
                
                for future in as_completed(future_to_chunk):
                    try:
                        chunk_results = future.result()
                        all_results.extend(chunk_results)
                        
                        # Progress logging
                        progress = (len(all_results) / len(batch_data)) * 100
                        logger.info(f"📈 Calculation progress: {len(all_results)}/{len(batch_data)} ({progress:.1f}%)")
                        
                    except Exception as e:
                        logger.error(f"Chunk future error: {e}")
            
            calc_time = time.time() - calc_start
            logger.info(f"✅ Indicator calculation completed in {calc_time:.2f}s - {len(all_results)} results")
            
            # Concurrent database saving phase
            logger.info("💾 Phase 3: Parallel database saving...")
            save_start = time.time()
            
            async def save_stock_result(result):
                """Save result for a single stock."""
                symbol, result_data, success, error_msg = result
                if success and result_data:
                    try:
                        # Extract candle data from result structure
                        if isinstance(result_data, dict) and 'data' in result_data:
                            candles_data = result_data['data']
                        else:
                            candles_data = result_data
                        
                        # Update indicator in ultra-fast database JSONB
                        from services.ultra_fast_database_service import ultra_fast_db
                        
                        # Extract indicator values from candles_data
                        indicator_values = []
                        for candle in candles_data:
                            # Find the indicator value in the candle
                            indicator_value = None
                            
                            # Check various possible field names based on indicator type
                            possible_names = [
                                indicator_key,  # Exact match first
                                indicator_key.lower(),
                                f"daily_{indicator_key.lower()}",
                                f"daily_{indicator_key}",
                                indicator_key.replace('_', '')  # Without underscores
                            ]
                            
                            # Special handling for weekly/monthly indicators
                            if indicator_key.startswith(('weekly_', 'monthly_')):
                                possible_names.extend([
                                    indicator_key,  # Keep full name
                                    indicator_key.split('_', 1)[1]  # Remove timeframe prefix
                                ])
                            
                            for name in possible_names:
                                if name in candle:
                                    indicator_value = candle[name]
                                    break
                            
                            if indicator_value is not None:
                                indicator_values.append({
                                    'timestamp': candle.get('timestamp', 0),
                                    'value': indicator_value
                                })
                        
                        if indicator_values:
                            # Use indicator key as-is for storage (it's already properly formatted)
                            await ultra_fast_db.update_indicator_in_jsonb(symbol, indicator_key, indicator_values)
                            logger.info(f"Stored {len(indicator_values)} values for {indicator_key} in {symbol}")
                        
                        return (symbol, True, None)
                    except Exception as e:
                        logger.error(f"Failed to save {symbol}: {e}")
                        return (symbol, False, str(e))
                else:
                    return (symbol, False, error_msg)
            
            # Save all results concurrently with semaphore to control DB connections
            save_semaphore = asyncio.Semaphore(20)  # Limit concurrent save operations
            
            async def save_with_semaphore(result):
                async with save_semaphore:
                    return await save_stock_result(result)
            
            # Create tasks for parallel saving
            save_tasks = [save_with_semaphore(result) for result in all_results]
            save_results = await asyncio.gather(*save_tasks, return_exceptions=True)
            
            # Count successes and errors
            total_processed = 0
            errors = 0
            
            for save_result in save_results:
                if isinstance(save_result, Exception):
                    errors += 1
                else:
                    symbol, success, error_msg = save_result
                    if success:
                        total_processed += 1
                    else:
                        errors += 1
                        if error_msg:
                            logger.error(f"Failed to save {symbol}: {error_msg}")
            
            save_time = time.time() - save_start
            total_time = time.time() - start_time
            
            logger.info(f"✅ Database saving completed in {save_time:.2f}s")
            logger.info(f"🎯 TOTAL HIGH-PERFORMANCE PROCESSING TIME: {total_time:.2f}s")
            logger.info(f"⚡ Processing speed: {len(all_symbols) / total_time:.1f} stocks/second")
            logger.info(f"📊 Phase breakdown: Load={load_time:.1f}s, Calc={calc_time:.1f}s, Save={save_time:.1f}s")
            
            success_rate = (total_processed / len(all_symbols)) * 100
            logger.info(f"✅ HIGH-PERFORMANCE calculation completed: {total_processed}/{len(all_symbols)} ({success_rate:.1f}%) successful")
            
            # Consider successful if we processed at least some stocks with data
            # Or if we have a reasonable success rate among stocks that have data
            stocks_with_data = len(batch_data)  # Stocks that actually had data to process
            
            if stocks_with_data == 0:
                logger.warning("No stocks had data for calculation")
                return False
            elif total_processed >= min(stocks_with_data * 0.8, 5):  # At least 80% of available data or 5 stocks minimum
                logger.info(f"✅ Calculation successful: {total_processed} stocks processed from {stocks_with_data} available")
                return True
            else:
                logger.warning(f"Calculation partially successful: {total_processed}/{stocks_with_data} stocks with data processed")
                return total_processed > 0  # Return true if we processed any stocks at all
            
        except Exception as e:
            logger.error(f"HIGH-PERFORMANCE calculation failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def get_active_indicators_list(self) -> List[Dict]:
        """Get list of all active indicators for scheduler."""
        # Ensure config is loaded
        await self.load_indicator_config()
        
        indicator_list = []
        
        for key in self.active_indicators:
            if key in self.indicator_definitions:
                definition = self.indicator_definitions[key]
                indicator_list.append({
                    "name": definition["name"],
                    "params": definition.get("params", {}),
                    "timeframe": definition.get("timeframe", "daily")
                })
        
        return indicator_list
    
    async def handle_query_validation_error(self, error_response: Dict) -> Tuple[bool, str]:
        """
        Handle query validation error by auto-calculating missing indicators.
        
        Returns: (success, message)
        """
        try:
            detail = error_response.get("detail", {})
            if not isinstance(detail, dict):
                return False, "Invalid error format"
            
            error_details = detail.get("details", "")
            if "precalculated data" not in error_details.lower():
                return False, "Not a precalculation error"
            
            # Attempt auto-calculation
            success = await self.auto_calculate_missing_indicator(error_details)
            
            if success:
                return True, "Missing indicator automatically calculated and added to system"
            else:
                return False, "Failed to auto-calculate missing indicator"
                
        except Exception as e:
            logger.error(f"Error handling validation error: {e}")
            return False, f"Error processing validation error: {str(e)}"
    
    async def _save_to_high_speed_database(self, symbol: str, candles_data: List[Dict]):
        """Save calculated indicators to high-speed database for faster queries."""
        try:
            from services.high_speed_database_service import high_speed_db
            
            if not high_speed_db.initialized:
                logger.warning(f"High-speed database not initialized, skipping save for {symbol}")
                return
            
            # Convert candles data to high-speed format and save
            await high_speed_db.insert_daily_candles_with_indicators(symbol, candles_data)
            logger.debug(f"Saved {len(candles_data)} candles to high-speed database for {symbol}")
            
        except Exception as e:
            logger.error(f"Failed to save {symbol} to high-speed database: {e}")
            # Don't fail the entire operation if high-speed save fails
    
    async def calculate_and_store_indicator(self, indicator_def: Dict, store_in_highspeed: bool = True) -> bool:
        """
        Calculate indicator dynamically and store in high-speed database.
        
        Args:
            indicator_def: Dictionary with name, params, and timeframe
            store_in_highspeed: If True, store in high-speed database JSONB
            
        Returns:
            True if successful, False otherwise
        """
        try:
            indicator_key = self.generate_indicator_key(indicator_def)
            logger.info(f"Calculating indicator: {indicator_key}")
            
            # Check if already calculated for ALL rows in database
            is_fully_calculated = await self._check_indicator_coverage(indicator_key, indicator_def)
            if is_fully_calculated:
                logger.info(f"Indicator {indicator_key} already calculated for all rows")
                # Add to active indicators if not already there
                self.active_indicators.add(indicator_key)
                return True
            else:
                logger.info(f"Indicator {indicator_key} missing from some/all rows - will calculate for entire database")
            
            # Use PostgreSQL framework for high-performance calculation when available
            async def python_fallback(ind_def):
                return await self.calculate_indicator_for_all_stocks(indicator_key, ind_def)
            
            framework_result = await postgres_indicator_framework.calculate_indicator(
                indicator_def, 
                fallback_handler=python_fallback
            )
            
            success = framework_result.get("success", False)
            
            if framework_result.get("calculation_method") == "PostgreSQL":
                logger.info(f"✅ Used high-performance PostgreSQL calculation for {indicator_key}")
            elif framework_result.get("calculation_method") == "Python_Fallback":
                logger.info(f"📝 Used Python fallback calculation for {indicator_key}")
            else:
                logger.warning(f"⚠️ Calculation method unclear for {indicator_key}: {framework_result.get('calculation_method')}")
            
            if success:
                # Add to active indicators
                self.active_indicators.add(indicator_key)
                self.indicator_definitions[indicator_key] = indicator_def
                
                # Register in metadata service - get symbol count from database
                all_symbols_for_metadata = await self._get_all_symbols_from_database(indicator_def.get('timeframe', 'daily'))
                stocks_count = len(all_symbols_for_metadata)  # Count of all symbols in database
                await indicator_metadata_service.register_indicator(
                    indicator_key, 
                    indicator_def, 
                    stocks_calculated=stocks_count,
                    candles_calculated=stocks_count * 500  # Estimate: ~500 candles per stock
                )
                
                # Save configuration
                await self.save_indicator_config()
                
                logger.info(f"✅ Successfully calculated and stored {indicator_key}")
                return True
            else:
                logger.error(f"Failed to calculate {indicator_key}")
                return False
                
        except Exception as e:
            logger.error(f"Error in calculate_and_store_indicator: {e}")
            return False
    
    async def _calculate_percentage_change_postgres(self, indicator_def: Dict) -> bool:
        """
        Calculate percentage change using PostgreSQL stored procedure for high performance.
        
        Args:
            indicator_def: Dictionary with name='PercentageChange', timeframe, params
            
        Returns:
            True if successful, False otherwise
        """
        try:
            timeframe = indicator_def.get('timeframe', 'daily')
            
            # Ensure PostgreSQL indicator service is initialized
            await postgres_indicator_service.initialize()
            
            # Check if calculation is needed (skip if >95% coverage)
            if not await postgres_indicator_service.is_calculation_needed(timeframe, threshold_percentage=95.0):
                logger.info(f"✅ {timeframe.title()} percentage change already has sufficient coverage, skipping calculation")
                return True
            
            # Execute PostgreSQL stored procedure calculation
            logger.info(f"🚀 Starting high-performance {timeframe} percentage change calculation via PostgreSQL")
            result = await postgres_indicator_service.calculate_percentage_change(timeframe)
            
            if result["success"]:
                logger.info(f"✅ PostgreSQL {timeframe} percentage change calculation completed successfully:")
                logger.info(f"   📊 Processed {result['processed_symbols']} symbols")
                logger.info(f"   🔄 Updated {result['updated_rows']} rows") 
                logger.info(f"   ⚡ Database execution: {result['db_execution_time_ms']}ms")
                logger.info(f"   🎯 Total time: {result['total_time_seconds']:.2f}s")
                
                # Verify the calculation worked by checking coverage
                coverage = await postgres_indicator_service.check_percentage_change_coverage(timeframe)
                logger.info(f"   📈 Final coverage: {coverage['coverage_percentage']:.1f}% ({coverage['rows_with_indicator']}/{coverage['total_rows']} rows)")
                
                return True
            else:
                logger.error(f"❌ PostgreSQL {timeframe} percentage change calculation failed: {result['status']}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error in PostgreSQL percentage change calculation: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def add_custom_indicator(self, name: str, params: Dict, timeframe: str = "daily") -> bool:
        """Manually add a custom indicator to the system."""
        try:
            indicator_def = {
                "name": name,
                "params": params,
                "timeframe": timeframe,
                "description": f"Custom {name} indicator",
                "manually_added": True,
                "added_at": datetime.now().isoformat()
            }
            
            indicator_key = self.generate_indicator_key(indicator_def)
            
            if indicator_key in self.active_indicators:
                logger.info(f"Indicator {indicator_key} already exists")
                return True
            
            logger.info(f"🔧 Adding custom indicator: {indicator_key}")
            
            self.indicator_definitions[indicator_key] = indicator_def
            self.active_indicators.add(indicator_key)
            
            # Calculate for all stocks
            success = await self.calculate_indicator_for_all_stocks(indicator_key, indicator_def)
            
            if success:
                await self.save_indicator_config()
                logger.info(f"✅ Custom indicator {indicator_key} added successfully")
                return True
            else:
                # Rollback
                self.active_indicators.discard(indicator_key)
                self.indicator_definitions.pop(indicator_key, None)
                logger.error(f"❌ Failed to add custom indicator {indicator_key}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to add custom indicator: {e}")
            return False

# Global instance
dynamic_indicator_manager = DynamicIndicatorManager()