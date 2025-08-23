"""
Timeframe Aggregator Service
Generates weekly and monthly candles from daily candles
"""

import asyncio
import asyncpg
import logging
from datetime import datetime, timedelta
from typing import Dict, List
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
                    
                    # Insert weekly candles
                    for candle in weekly_candles:
                        # Calculate week_start_date from timestamp
                        week_start_date = datetime.fromtimestamp(candle['week_start_timestamp'] / 1000).date()
                        
                        await conn.execute("""
                            INSERT INTO weekly_candles (
                                symbol, week_start_timestamp, week_start_date, 
                                open, high, low, close, volume, trading_days,
                                rsi_14, rsi_21, sma_10, sma_20, ema_12, ema_26,
                                supertrend_10_2, supertrend_signal_10_2,
                                supertrend_10_3, supertrend_signal_10_3
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
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
                                updated_at = CURRENT_TIMESTAMP
                        """, 
                        candle['symbol'], candle['week_start_timestamp'], week_start_date,
                        candle['open'], candle['high'], candle['low'], candle['close'], candle['volume'],
                        5,  # Assuming 5 trading days per week
                        candle.get('rsi_14'), candle.get('rsi_21'),
                        candle.get('sma_10'), candle.get('sma_20'),
                        candle.get('ema_12'), candle.get('ema_26'),
                        candle.get('supertrend_10_2'), candle.get('supertrend_signal_10_2'),
                        candle.get('supertrend_10_3'), candle.get('supertrend_signal_10_3')
                        )
                    
                    total_candles += len(weekly_candles)
                    logger.info(f"Generated {len(weekly_candles)} weekly candles for {sym}")
                
                return total_candles
                
        except Exception as e:
            logger.error(f"Error generating weekly candles: {e}")
            raise
    
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
                    
                    # Calculate indicators for monthly candles
                    monthly_candles = static_indicator_calculator.calculate_static_indicators(
                        monthly_candles, 'monthly_candles'
                    )
                    
                    # Insert monthly candles
                    for candle in monthly_candles:
                        # Calculate month_start_date from timestamp
                        month_start_date = datetime.fromtimestamp(candle['month_start_timestamp'] / 1000).date()
                        
                        await conn.execute("""
                            INSERT INTO monthly_candles (
                                symbol, month_start_timestamp, month_start_date,
                                open, high, low, close, volume, trading_days,
                                rsi_14, rsi_21, sma_10, sma_20, ema_12, ema_26,
                                supertrend_10_2, supertrend_signal_10_2,
                                supertrend_10_3, supertrend_signal_10_3
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
                            ON CONFLICT (symbol, month_start_timestamp) DO UPDATE SET
                                month_start_date = EXCLUDED.month_start_date,
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
                                updated_at = CURRENT_TIMESTAMP
                        """, 
                        candle['symbol'], candle['month_start_timestamp'], month_start_date,
                        candle['open'], candle['high'], candle['low'], candle['close'], candle['volume'],
                        20,  # Assuming 20 trading days per month
                        candle.get('rsi_14'), candle.get('rsi_21'),
                        candle.get('sma_10'), candle.get('sma_20'),
                        candle.get('ema_12'), candle.get('ema_26'),
                        candle.get('supertrend_10_2'), candle.get('supertrend_signal_10_2'),
                        candle.get('supertrend_10_3'), candle.get('supertrend_signal_10_3')
                        )
                    
                    total_candles += len(monthly_candles)
                    logger.info(f"Generated {len(monthly_candles)} monthly candles for {sym}")
                
                return total_candles
                
        except Exception as e:
            logger.error(f"Error generating monthly candles: {e}")
            raise