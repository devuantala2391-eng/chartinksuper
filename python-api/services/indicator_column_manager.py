"""
Dynamic Indicator Column Management System
Handles adding new indicators without downtime and optimizes storage
"""

import asyncio
import asyncpg
import logging
from typing import Dict, List, Any, Optional, Set
from enum import Enum
import json

logger = logging.getLogger(__name__)

class IndicatorType(Enum):
    RSI = "rsi"
    SMA = "sma"
    EMA = "ema"
    SUPERTREND = "supertrend"
    BOLLINGER = "bollinger"
    MACD = "macd"
    STOCHASTIC = "stochastic"
    ATR = "atr"
    CUSTOM = "custom"

class TimeFrame(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"  
    MONTHLY = "monthly"

class IndicatorColumnManager:
    """
    Manages dynamic indicator columns for maximum speed.
    Approach: Individual columns for each indicator parameter combination.
    
    Example columns:
    - rsi_14, rsi_21, rsi_30
    - sma_20, sma_50, sma_200
    - supertrend_10_2, supertrend_10_3, supertrend_14_2
    - bb_upper_20_2, bb_middle_20_2, bb_lower_20_2
    """
    
    def __init__(self, db_service):
        self.db = db_service
        
        # Track existing columns to avoid duplicate creation
        self.existing_columns = {
            'daily': set(),
            'weekly': set(), 
            'monthly': set()
        }
        
        # Column naming patterns for consistency
        self.column_patterns = {
            IndicatorType.RSI: "rsi_{period}",
            IndicatorType.SMA: "sma_{period}",
            IndicatorType.EMA: "ema_{period}",
            IndicatorType.SUPERTREND: "supertrend_{period}_{multiplier}",
            IndicatorType.BOLLINGER: "bb_{band}_{period}_{std_dev}",
            IndicatorType.MACD: "macd_{fast}_{slow}_{signal}",
            IndicatorType.STOCHASTIC: "stoch_{k_period}_{d_period}",
            IndicatorType.ATR: "atr_{period}",
            IndicatorType.CUSTOM: "{name}_{params}"
        }
        
        # Initialize with existing columns
        asyncio.create_task(self._load_existing_columns())

    async def _load_existing_columns(self):
        """Load existing indicator columns from database schema"""
        try:
            for timeframe in ['daily', 'weekly', 'monthly']:
                table_name = f"{timeframe}_candles"
                columns = await self._get_table_columns(table_name)
                
                # Filter out base columns to get only indicators
                base_columns = {
                    'symbol', 'timestamp', 'datetime', 'open', 'high', 'low', 'close', 'volume',
                    'trading_days', 'created_at', 'updated_at', 'week_start_timestamp', 
                    'week_start_date', 'month_start_timestamp', 'month_start_date'
                }
                
                indicator_columns = columns - base_columns
                self.existing_columns[timeframe] = indicator_columns
                
                logger.info(f"Loaded {len(indicator_columns)} indicator columns for {timeframe}")
                
        except Exception as e:
            logger.error(f"Error loading existing columns: {e}")

    async def _get_table_columns(self, table_name: str) -> Set[str]:
        """Get all column names for a table"""
        try:
            async with self.db.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = $1 
                    AND table_schema = 'public'
                """, table_name)
                
                return {row['column_name'] for row in rows}
                
        except Exception as e:
            logger.error(f"Error getting columns for {table_name}: {e}")
            return set()

    def generate_column_name(self, indicator_type: IndicatorType, params: Dict[str, Any]) -> str:
        """Generate standardized column name for indicator"""
        pattern = self.column_patterns[indicator_type]
        
        if indicator_type == IndicatorType.RSI:
            return pattern.format(period=params['period'])
            
        elif indicator_type == IndicatorType.SMA:
            return pattern.format(period=params['period'])
            
        elif indicator_type == IndicatorType.EMA:
            return pattern.format(period=params['period'])
            
        elif indicator_type == IndicatorType.SUPERTREND:
            return pattern.format(period=params['period'], multiplier=params['multiplier'])
            
        elif indicator_type == IndicatorType.BOLLINGER:
            # For Bollinger Bands, create multiple columns
            period = params['period']
            std_dev = params['std_dev']
            band = params.get('band', 'middle')  # upper, middle, lower
            return f"bb_{band}_{period}_{std_dev}"
            
        elif indicator_type == IndicatorType.MACD:
            return pattern.format(
                fast=params['fast_period'],
                slow=params['slow_period'], 
                signal=params['signal_period']
            )
            
        elif indicator_type == IndicatorType.CUSTOM:
            name = params['name']
            param_str = '_'.join([str(v) for v in params.values() if v != name])
            return f"{name}_{param_str}"
            
        else:
            # Default pattern
            param_str = '_'.join([str(v) for v in params.values()])
            return f"{indicator_type.value}_{param_str}"

    async def add_indicator_column(self, timeframe: TimeFrame, indicator_type: IndicatorType, 
                                 params: Dict[str, Any]) -> List[str]:
        """
        Add new indicator column(s) to the specified timeframe table.
        Returns list of column names created.
        """
        try:
            table_name = f"{timeframe.value}_candles"
            columns_created = []
            
            # Handle special cases that create multiple columns
            if indicator_type == IndicatorType.BOLLINGER:
                # Bollinger Bands creates 3 columns: upper, middle, lower
                for band in ['upper', 'middle', 'lower']:
                    band_params = params.copy()
                    band_params['band'] = band
                    column_name = self.generate_column_name(indicator_type, band_params)
                    
                    if await self._add_single_column(table_name, column_name, 'DECIMAL(12,4)'):
                        columns_created.append(column_name)
                        self.existing_columns[timeframe.value].add(column_name)
                        
            elif indicator_type == IndicatorType.SUPERTREND:
                # SuperTrend creates 2 columns: value and signal
                base_name = self.generate_column_name(indicator_type, params)
                value_column = base_name
                signal_column = f"{base_name}_signal"
                
                if await self._add_single_column(table_name, value_column, 'DECIMAL(12,4)'):
                    columns_created.append(value_column)
                    self.existing_columns[timeframe.value].add(value_column)
                    
                if await self._add_single_column(table_name, signal_column, 'INTEGER'):
                    columns_created.append(signal_column)
                    self.existing_columns[timeframe.value].add(signal_column)
                    
            elif indicator_type == IndicatorType.MACD:
                # MACD creates 3 columns: macd, signal, histogram
                base_name = self.generate_column_name(indicator_type, params)
                
                for suffix in ['', '_signal', '_histogram']:
                    column_name = f"{base_name}{suffix}"
                    if await self._add_single_column(table_name, column_name, 'DECIMAL(12,4)'):
                        columns_created.append(column_name)
                        self.existing_columns[timeframe.value].add(column_name)
                        
            else:
                # Single column indicators
                column_name = self.generate_column_name(indicator_type, params)
                if await self._add_single_column(table_name, column_name, 'DECIMAL(12,4)'):
                    columns_created.append(column_name)
                    self.existing_columns[timeframe.value].add(column_name)

            # Create indexes for new columns
            for column_name in columns_created:
                await self._create_column_index(table_name, column_name)
                
            logger.info(f"Created {len(columns_created)} columns for {indicator_type.value} in {timeframe.value}")
            return columns_created
            
        except Exception as e:
            logger.error(f"Error adding indicator column: {e}")
            return []

    async def _add_single_column(self, table_name: str, column_name: str, column_type: str) -> bool:
        """Add a single column to the table if it doesn't exist"""
        try:
            # Check if column already exists
            if column_name in self.existing_columns.get(table_name.replace('_candles', ''), set()):
                logger.debug(f"Column {column_name} already exists in {table_name}")
                return False
                
            async with self.db.pool.acquire() as conn:
                await conn.execute(f"""
                    ALTER TABLE {table_name} 
                    ADD COLUMN IF NOT EXISTS {column_name} {column_type}
                """)
                
                logger.info(f"Added column {column_name} to {table_name}")
                return True
                
        except Exception as e:
            logger.error(f"Error adding column {column_name} to {table_name}: {e}")
            return False

    async def _create_column_index(self, table_name: str, column_name: str):
        """Create an index for the new column where values are not NULL"""
        try:
            index_name = f"idx_{table_name.replace('_candles', '')}_{column_name}"
            async with self.db.pool.acquire() as conn:
                await conn.execute(f"""
                    CREATE INDEX CONCURRENTLY IF NOT EXISTS {index_name}
                    ON {table_name} ({column_name})
                    WHERE {column_name} IS NOT NULL
                """)
                
                logger.debug(f"Created index {index_name}")
                
        except Exception as e:
            logger.warning(f"Error creating index for {column_name}: {e}")

    async def backfill_indicator_data(self, timeframe: TimeFrame, indicator_type: IndicatorType,
                                    params: Dict[str, Any], batch_size: int = 1000):
        """
        Backfill historical data for newly added indicator columns.
        This runs in background to avoid blocking new data insertion.
        """
        try:
            table_name = f"{timeframe.value}_candles"
            column_names = []
            
            # Get the column names that were created for this indicator
            if indicator_type == IndicatorType.BOLLINGER:
                for band in ['upper', 'middle', 'lower']:
                    band_params = params.copy()
                    band_params['band'] = band
                    column_names.append(self.generate_column_name(indicator_type, band_params))
                    
            elif indicator_type == IndicatorType.SUPERTREND:
                base_name = self.generate_column_name(indicator_type, params)
                column_names = [base_name, f"{base_name}_signal"]
                
            elif indicator_type == IndicatorType.MACD:
                base_name = self.generate_column_name(indicator_type, params)
                column_names = [f"{base_name}", f"{base_name}_signal", f"{base_name}_histogram"]
                
            else:
                column_names = [self.generate_column_name(indicator_type, params)]

            # Check if any columns need backfilling
            columns_to_backfill = []
            for column_name in column_names:
                if await self._column_needs_backfill(table_name, column_name):
                    columns_to_backfill.append(column_name)

            if not columns_to_backfill:
                logger.info(f"No backfill needed for {indicator_type.value} in {timeframe.value}")
                return

            logger.info(f"Starting backfill for {len(columns_to_backfill)} columns in {timeframe.value}")
            
            # Get symbols that need backfilling
            symbols = await self._get_symbols_needing_backfill(table_name, columns_to_backfill[0])
            
            total_symbols = len(symbols)
            for i, symbol in enumerate(symbols):
                try:
                    await self._backfill_symbol_indicators(
                        table_name, symbol, indicator_type, params, columns_to_backfill
                    )
                    
                    if (i + 1) % 100 == 0:
                        logger.info(f"Backfilled {i + 1}/{total_symbols} symbols for {indicator_type.value}")
                        
                    # Yield control to avoid blocking
                    if i % 10 == 0:
                        await asyncio.sleep(0.01)
                        
                except Exception as e:
                    logger.error(f"Error backfilling {symbol}: {e}")
                    continue

            logger.info(f"Completed backfill for {indicator_type.value} in {timeframe.value}")
            
        except Exception as e:
            logger.error(f"Error in backfill process: {e}")

    async def _column_needs_backfill(self, table_name: str, column_name: str) -> bool:
        """Check if a column needs backfilling (has mostly NULL values)"""
        try:
            async with self.db.pool.acquire() as conn:
                result = await conn.fetchrow(f"""
                    SELECT 
                        COUNT(*) as total_rows,
                        COUNT({column_name}) as non_null_rows
                    FROM {table_name}
                    LIMIT 10000
                """)
                
                if result['total_rows'] == 0:
                    return False
                    
                null_percentage = (result['total_rows'] - result['non_null_rows']) / result['total_rows']
                return null_percentage > 0.1  # If more than 10% NULL, needs backfill
                
        except Exception as e:
            logger.error(f"Error checking backfill need: {e}")
            return False

    async def _get_symbols_needing_backfill(self, table_name: str, column_name: str) -> List[str]:
        """Get list of symbols that have NULL values for the indicator"""
        try:
            async with self.db.pool.acquire() as conn:
                rows = await conn.fetch(f"""
                    SELECT DISTINCT symbol 
                    FROM {table_name}
                    WHERE {column_name} IS NULL
                    ORDER BY symbol
                """)
                
                return [row['symbol'] for row in rows]
                
        except Exception as e:
            logger.error(f"Error getting symbols for backfill: {e}")
            return []

    async def _backfill_symbol_indicators(self, table_name: str, symbol: str, 
                                        indicator_type: IndicatorType, params: Dict[str, Any],
                                        column_names: List[str]):
        """Backfill indicator data for a specific symbol"""
        try:
            # This would integrate with your existing calculation engine
            # For now, just a placeholder that shows the structure
            
            # 1. Fetch historical OHLCV data for the symbol
            # 2. Calculate indicator values using your calculation functions
            # 3. Update the specific columns with calculated values
            
            async with self.db.pool.acquire() as conn:
                # Example update (you'd replace with actual calculations)
                await conn.execute(f"""
                    UPDATE {table_name}
                    SET {column_names[0]} = some_calculated_value
                    WHERE symbol = $1 AND {column_names[0]} IS NULL
                """, symbol)
                
        except Exception as e:
            logger.error(f"Error backfilling {symbol}: {e}")

    async def get_available_indicators(self, timeframe: TimeFrame) -> Dict[str, List[str]]:
        """Get all available indicators for a timeframe organized by type"""
        try:
            columns = self.existing_columns[timeframe.value]
            
            indicators = {
                'rsi': [col for col in columns if col.startswith('rsi_')],
                'sma': [col for col in columns if col.startswith('sma_')],
                'ema': [col for col in columns if col.startswith('ema_')],
                'supertrend': [col for col in columns if col.startswith('supertrend_') and not col.endswith('_signal')],
                'bollinger': [col for col in columns if col.startswith('bb_')],
                'macd': [col for col in columns if col.startswith('macd_')],
                'custom': [col for col in columns if not any(col.startswith(prefix) for prefix in 
                          ['rsi_', 'sma_', 'ema_', 'supertrend_', 'bb_', 'macd_'])]
            }
            
            return indicators
            
        except Exception as e:
            logger.error(f"Error getting available indicators: {e}")
            return {}

# Example usage and testing
async def example_usage():
    """Example of how to use the IndicatorColumnManager"""
    from .high_speed_database_service import high_speed_db
    
    # Initialize
    await high_speed_db.initialize()
    manager = IndicatorColumnManager(high_speed_db)
    
    # Add new RSI indicator
    columns = await manager.add_indicator_column(
        TimeFrame.DAILY, 
        IndicatorType.RSI, 
        {'period': 30}
    )
    print(f"Created RSI columns: {columns}")
    
    # Add new SuperTrend indicator
    columns = await manager.add_indicator_column(
        TimeFrame.WEEKLY,
        IndicatorType.SUPERTREND,
        {'period': 14, 'multiplier': 2.5}
    )
    print(f"Created SuperTrend columns: {columns}")
    
    # Add Bollinger Bands
    columns = await manager.add_indicator_column(
        TimeFrame.DAILY,
        IndicatorType.BOLLINGER,
        {'period': 21, 'std_dev': 2.5}
    )
    print(f"Created Bollinger Bands columns: {columns}")
    
    # Get available indicators
    indicators = await manager.get_available_indicators(TimeFrame.DAILY)
    print(f"Available daily indicators: {indicators}")
    
    # Backfill data (runs in background)
    await manager.backfill_indicator_data(
        TimeFrame.DAILY,
        IndicatorType.RSI,
        {'period': 30}
    )