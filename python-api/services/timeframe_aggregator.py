"""
Timeframe Aggregator Service
Generates weekly and monthly candles from daily candles
"""

import asyncio
import asyncpg
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import pandas as pd
from services.static_indicator_calculator import static_indicator_calculator

logger = logging.getLogger(__name__)

class TimeframeAggregator:
    """Aggregates daily candles into weekly and monthly timeframes"""
    
    def __init__(self, pool):
        self.pool = pool
        
    async def generate_weekly_candles(self, symbol: str = None) -> int:
        """
        Generate weekly candles from daily candles
        
        Args:
            symbol: Optional symbol to process, None for all symbols
        """
        try:
            async with self.pool.acquire() as conn:
                # Get symbols to process
                if symbol:
                    symbols = [symbol]
                else:
                    symbols = await conn.fetch("""
                        SELECT DISTINCT symbol FROM daily_candles
                        ORDER BY symbol
                    """)
                    symbols = [row['symbol'] for row in symbols]
                
                total_candles = 0
                
                for sym in symbols:
                    # Get daily candles for this symbol
                    daily_candles = await conn.fetch("""
                        SELECT timestamp, datetime, open, high, low, close, volume
                        FROM daily_candles
                        WHERE symbol = $1
                        ORDER BY timestamp
                    """, sym)
                    
                    if not daily_candles:
                        continue
                    
                    # Convert to DataFrame for easier aggregation
                    df = pd.DataFrame([dict(row) for row in daily_candles])
                    df['datetime'] = pd.to_datetime(df['datetime'])
                    df.set_index('datetime', inplace=True)
                    
                    # Resample to weekly (W = week ending Sunday)
                    weekly_ohlc = df.resample('W').agg({
                        'open': 'first',
                        'high': 'max',
                        'low': 'min',
                        'close': 'last',
                        'volume': 'sum',
                        'timestamp': 'first'
                    }).dropna()
                    
                    if weekly_ohlc.empty:
                        continue
                    
                    # Prepare data for insertion
                    weekly_candles = []
                    for idx, row in weekly_ohlc.iterrows():
                        # Get week start timestamp (Monday)
                        week_start = idx - timedelta(days=6)
                        week_start_ts = int(week_start.timestamp() * 1000)
                        
                        candle = {
                            'symbol': sym,
                            'week_start_timestamp': week_start_ts,
                            'timestamp': int(row['timestamp']),
                            'open': float(row['open']),
                            'high': float(row['high']),
                            'low': float(row['low']),
                            'close': float(row['close']),
                            'volume': int(row['volume'])
                        }
                        weekly_candles.append(candle)
                    
                    # Calculate indicators for weekly candles
                    weekly_candles = static_indicator_calculator.calculate_static_indicators(
                        weekly_candles, 'weekly_candles'
                    )
                    
                    # Find monthly assignments for weekly candles based on their END dates
                    weekly_monthly_assignments = await self._find_monthly_assignments_for_weekly_candles(
                        conn, weekly_candles
                    )
                    
                    # Insert weekly candles
                    for candle in weekly_candles:
                        # Calculate week_start_date from timestamp
                        week_start_date = datetime.fromtimestamp(candle['week_start_timestamp'] / 1000).date()
                        
                        # Get monthly assignment for this candle
                        candle_key = (candle['symbol'], candle.get('week_end_timestamp'))
                        monthly_key, monthly_candle_key_id = weekly_monthly_assignments.get(candle_key, (None, None))
                        
                        await conn.execute("""
                            INSERT INTO weekly_candles (
                                symbol, week_start_timestamp, week_start_date, 
                                open, high, low, close, volume, trading_days,
                                rsi_14, rsi_21, sma_10, sma_20, ema_12, ema_26,
                                supertrend_10_2, supertrend_signal_10_2,
                                supertrend_10_3, supertrend_signal_10_3,
                                monthly_key, monthly_candle_key_id
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21)
                            ON CONFLICT (symbol, week_start_timestamp) DO UPDATE SET
                                week_start_date = EXCLUDED.week_start_date,
                                open = EXCLUDED.open,
                                high = EXCLUDED.high,
                                low = EXCLUDED.low,
                                close = EXCLUDED.close,
                                volume = EXCLUDED.volume,
                                trading_days = EXCLUDED.trading_days,
                                rsi_14 = EXCLUDED.rsi_14,
                                rsi_21 = EXCLUDED.rsi_21,
                                sma_10 = EXCLUDED.sma_10,
                                sma_20 = EXCLUDED.sma_20,
                                ema_12 = EXCLUDED.ema_12,
                                ema_26 = EXCLUDED.ema_26,
                                supertrend_10_2 = EXCLUDED.supertrend_10_2,
                                supertrend_signal_10_2 = EXCLUDED.supertrend_signal_10_2,
                                supertrend_10_3 = EXCLUDED.supertrend_10_3,
                                supertrend_signal_10_3 = EXCLUDED.supertrend_signal_10_3,
                                monthly_key = EXCLUDED.monthly_key,
                                monthly_candle_key_id = EXCLUDED.monthly_candle_key_id,
                                updated_at = CURRENT_TIMESTAMP
                        """, 
                        candle['symbol'], candle['week_start_timestamp'], week_start_date,
                        candle['open'], candle['high'], candle['low'], candle['close'], candle['volume'],
                        5,  # Assuming 5 trading days per week
                        candle.get('rsi_14'), candle.get('rsi_21'),
                        candle.get('sma_10'), candle.get('sma_20'),
                        candle.get('ema_12'), candle.get('ema_26'),
                        candle.get('supertrend_10_2'), candle.get('supertrend_signal_10_2'),
                        candle.get('supertrend_10_3'), candle.get('supertrend_signal_10_3'),
                        monthly_key, monthly_candle_key_id
                        )
                    
                    total_candles += len(weekly_candles)
                    logger.info(f"Generated {len(weekly_candles)} weekly candles for {sym}")
                
                return total_candles
                
        except Exception as e:
            logger.error(f"Error generating weekly candles: {e}")
            raise
    
    async def _find_monthly_assignments_for_weekly_candles(self, conn, weekly_candles: List[Dict]) -> Dict[Tuple[str, int], Tuple[int, str]]:
        """Find monthly_key and monthly_candle_key_id for weekly candles based on their END dates (per user requirement)"""
        assignments = {}
        
        # Get unique symbols from weekly candles
        symbols = list(set(candle['symbol'] for candle in weekly_candles))
        
        # Get all monthly candles for these symbols
        monthly_candles = await conn.fetch("""
            SELECT symbol, month_sequence_number, monthly_candle_key_id,
                   month_start_datetime, month_end_datetime
            FROM monthly_candles 
            WHERE symbol = ANY($1)
            ORDER BY month_start_datetime
        """, symbols)
        
        # For each weekly candle, find which monthly candle it belongs to (based on END date)
        for candle in weekly_candles:
            symbol = candle['symbol']
            week_end_timestamp = candle.get('week_end_timestamp')
            
            if week_end_timestamp:
                # Convert timestamp to date for comparison
                week_end_date = datetime.fromtimestamp(week_end_timestamp / 1000).date()
                
                # Find matching monthly candle
                monthly_key = None
                monthly_candle_key_id = None
                
                for mc in monthly_candles:
                    if (mc['symbol'] == symbol and 
                        mc['month_start_datetime'].date() <= week_end_date <= mc['month_end_datetime'].date()):
                        monthly_key = mc['month_sequence_number']
                        monthly_candle_key_id = mc['monthly_candle_key_id']
                        break
                
                assignments[(symbol, week_end_timestamp)] = (monthly_key, monthly_candle_key_id)
        
        return assignments
    
    async def generate_monthly_candles(self, symbol: str = None) -> int:
        """
        Generate monthly candles from daily candles
        
        Args:
            symbol: Optional symbol to process, None for all symbols
        """
        try:
            async with self.pool.acquire() as conn:
                # Get symbols to process
                if symbol:
                    symbols = [symbol]
                else:
                    symbols = await conn.fetch("""
                        SELECT DISTINCT symbol FROM daily_candles
                        ORDER BY symbol
                    """)
                    symbols = [row['symbol'] for row in symbols]
                
                total_candles = 0
                
                for sym in symbols:
                    # Get daily candles for this symbol
                    daily_candles = await conn.fetch("""
                        SELECT timestamp, datetime, open, high, low, close, volume
                        FROM daily_candles
                        WHERE symbol = $1
                        ORDER BY timestamp
                    """, sym)
                    
                    if not daily_candles:
                        continue
                    
                    # Convert to DataFrame for easier aggregation
                    df = pd.DataFrame([dict(row) for row in daily_candles])
                    df['datetime'] = pd.to_datetime(df['datetime'])
                    df.set_index('datetime', inplace=True)
                    
                    # Resample to monthly (MS = month start)
                    monthly_ohlc = df.resample('MS').agg({
                        'open': 'first',
                        'high': 'max',
                        'low': 'min',
                        'close': 'last',
                        'volume': 'sum',
                        'timestamp': 'first'
                    }).dropna()
                    
                    if monthly_ohlc.empty:
                        continue
                    
                    # Prepare data for insertion
                    monthly_candles = []
                    for idx, row in monthly_ohlc.iterrows():
                        # Month start timestamp
                        month_start_ts = int(idx.timestamp() * 1000)
                        
                        candle = {
                            'symbol': sym,
                            'month_start_timestamp': month_start_ts,
                            'timestamp': int(row['timestamp']),
                            'open': float(row['open']),
                            'high': float(row['high']),
                            'low': float(row['low']),
                            'close': float(row['close']),
                            'volume': int(row['volume'])
                        }
                        monthly_candles.append(candle)
                    
                    # Monthly candles should have empty indicators by default (like daily candles)
                    # Do NOT calculate indicators - keep them empty like daily candles
                    
                    # Insert monthly candles with updated structure
                    for i, candle in enumerate(monthly_candles):
                        # Calculate month_start_date and month_end_date from timestamp
                        month_start_date = datetime.fromtimestamp(candle['month_start_timestamp'] / 1000)
                        
                        # Calculate month end timestamp (last day of month)
                        if month_start_date.month == 12:
                            month_end_date = month_start_date.replace(year=month_start_date.year + 1, month=1, day=1) - timedelta(days=1)
                        else:
                            month_end_date = month_start_date.replace(month=month_start_date.month + 1, day=1) - timedelta(days=1)
                        
                        month_end_ts = int(month_end_date.timestamp() * 1000)
                        
                        # Create monthly_candle_key_id
                        monthly_candle_key_id = f"{sym}_{month_start_date.strftime('%Y%m')}"
                        
                        # Monthly candles should have empty indicators JSON like daily candles
                        import json
                        indicators_json = json.dumps({})
                        
                        await conn.execute("""
                            INSERT INTO monthly_candles (
                                monthly_candle_key_id, symbol, month_sequence_number,
                                month_start_timestamp, month_end_timestamp,
                                month_start_datetime, month_end_datetime,
                                open, high, low, close, volume, trading_days_count,
                                indicators
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                            ON CONFLICT (monthly_candle_key_id) DO UPDATE SET
                                month_sequence_number = EXCLUDED.month_sequence_number,
                                month_start_timestamp = EXCLUDED.month_start_timestamp,
                                month_end_timestamp = EXCLUDED.month_end_timestamp,
                                month_start_datetime = EXCLUDED.month_start_datetime,
                                month_end_datetime = EXCLUDED.month_end_datetime,
                                open = EXCLUDED.open,
                                high = EXCLUDED.high,
                                low = EXCLUDED.low,
                                close = EXCLUDED.close,
                                volume = EXCLUDED.volume,
                                trading_days_count = EXCLUDED.trading_days_count,
                                indicators = EXCLUDED.indicators,
                                updated_at = CURRENT_TIMESTAMP
                        """, 
                        monthly_candle_key_id, candle['symbol'], i + 1,
                        candle['month_start_timestamp'], month_end_ts,
                        month_start_date, month_end_date,
                        candle['open'], candle['high'], candle['low'], candle['close'], candle['volume'],
                        20,  # Assuming 20 trading days per month
                        indicators_json
                        )
                    
                    total_candles += len(monthly_candles)
                    logger.info(f"Generated {len(monthly_candles)} monthly candles for {sym}")
                
                return total_candles
                
        except Exception as e:
            logger.error(f"Error generating monthly candles: {e}")
            raise