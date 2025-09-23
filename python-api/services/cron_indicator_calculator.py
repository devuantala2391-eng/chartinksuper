"""
Cron-Compatible Indicator Calculator
Optimized for incremental calculation of indicators using previous states
Designed for maximum speed and parallel processing
"""

import asyncio
import asyncpg
import json
import logging
import math
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal, ROUND_HALF_UP
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class CronIndicatorCalculator:
    """
    High-performance incremental indicator calculator for cron jobs.
    Calculates indicators using previous states from database for maximum efficiency.
    """

    def __init__(self):
        self.pool = None
        self.semaphore = asyncio.Semaphore(50)  # Control concurrency

        # Indicator type mappings
        self.stateful_indicators = {
            'rsi', 'atr', 'ema', 'supertrend'
        }
        self.stateless_indicators = {
            'sma', 'bollinger_bands', 'percentage_change'
        }

        # Dependency mapping (indicators that depend on others)
        self.dependencies = {
            'supertrend': ['atr']  # SuperTrend requires ATR
        }

    async def initialize(self):
        """Initialize database connection pool"""
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                host=os.getenv('POSTGRES_HOST', 'localhost'),
                port=int(os.getenv('POSTGRES_PORT', '5432')),
                database='nse_highspeed',
                user=os.getenv('POSTGRES_USER', 'postgres'),
                password=os.getenv('POSTGRES_PASSWORD', '123'),
                min_size=10,
                max_size=100,  # High concurrency for speed
                command_timeout=60
            )
        logger.info("🔢 Cron indicator calculator initialized")

    async def close(self):
        """Close database connections"""
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def calculate_indicators_for_symbol(self, symbol: str) -> Dict[str, Any]:
        """
        Calculate all indicators for a single symbol's latest candle.
        This is the main entry point for cron jobs.

        Args:
            symbol: Stock symbol to calculate indicators for

        Returns:
            Dict with calculation results and statistics
        """
        async with self.semaphore:
            try:
                start_time = datetime.now()

                # Get active indicators from database
                active_indicators = await self._get_active_indicators()
                if not active_indicators:
                    return {
                        "success": True,
                        "symbol": symbol,
                        "message": "No active indicators found",
                        "indicators_calculated": 0
                    }

                # Get latest candle data for all timeframes
                candle_data = await self._get_latest_candle_data(symbol)
                if not candle_data:
                    return {
                        "success": False,
                        "symbol": symbol,
                        "message": "No candle data found",
                        "indicators_calculated": 0
                    }

                # Group indicators by dependency order
                ordered_indicators = self._order_indicators_by_dependencies(active_indicators)

                # Calculate indicators in dependency order for each timeframe
                results = {}
                for timeframe in ['daily', 'weekly', 'monthly']:
                    timeframe_results = await self._calculate_timeframe_indicators(
                        symbol, timeframe, candle_data, ordered_indicators
                    )
                    results[timeframe] = timeframe_results

                # Update database with calculated values
                await self._update_indicators_in_database(symbol, results)

                duration = (datetime.now() - start_time).total_seconds()
                total_calculated = sum(len(r.get('calculated', [])) for r in results.values())

                return {
                    "success": True,
                    "symbol": symbol,
                    "indicators_calculated": total_calculated,
                    "duration_seconds": duration,
                    "timeframes": list(results.keys())
                }

            except Exception as e:
                logger.error(f"❌ Error calculating indicators for {symbol}: {e}")
                return {
                    "success": False,
                    "symbol": symbol,
                    "message": str(e),
                    "indicators_calculated": 0
                }

    async def _get_active_indicators(self) -> List[Dict]:
        """Get all active indicators from indicator_registry"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT name, parameters, timeframes, enabled
                FROM indicator_registry
                WHERE enabled = true
                ORDER BY name, parameters
            """)

            indicators = []
            for row in rows:
                indicators.append({
                    'name': row['name'],
                    'parameters': json.loads(row['parameters']) if row['parameters'] else {},
                    'timeframes': json.loads(row['timeframes']) if row['timeframes'] else ['daily'],
                    'enabled': row['enabled']
                })

            logger.debug(f"📊 Found {len(indicators)} active indicators")
            return indicators

    async def _get_latest_candle_data(self, symbol: str) -> Optional[Dict]:
        """Get latest candle data for all timeframes"""
        async with self.pool.acquire() as conn:
            # Get latest daily candle with all timeframe data
            daily_candle = await conn.fetchrow("""
                SELECT
                    symbol, datetime, open, high, low, close, volume,
                    weekly_open, weekly_high, weekly_low, weekly_close, weekly_volume,
                    monthly_open, monthly_high, monthly_low, monthly_close, monthly_volume,
                    weekly_candle_key_id, monthly_candle_key_id,
                    indicators
                FROM daily_candles
                WHERE symbol = $1
                ORDER BY datetime DESC
                LIMIT 1
            """, symbol)

            if not daily_candle:
                return None

            # Get previous candle for calculations that need it
            previous_candle = await conn.fetchrow("""
                SELECT close, indicators
                FROM daily_candles
                WHERE symbol = $1 AND datetime < $2
                ORDER BY datetime DESC
                LIMIT 1
            """, symbol, daily_candle['datetime'])

            # Get weekly candle data if available
            weekly_candle = None
            if daily_candle['weekly_candle_key_id']:
                weekly_candle = await conn.fetchrow("""
                    SELECT indicators
                    FROM weekly_candles
                    WHERE candle_key_id = $1
                """, daily_candle['weekly_candle_key_id'])

            # Get monthly candle data if available
            monthly_candle = None
            if daily_candle['monthly_candle_key_id']:
                monthly_candle = await conn.fetchrow("""
                    SELECT indicators
                    FROM monthly_candles
                    WHERE candle_key_id = $1
                """, daily_candle['monthly_candle_key_id'])

            return {
                'daily': {
                    'current': daily_candle,
                    'previous': previous_candle
                },
                'weekly': weekly_candle,
                'monthly': monthly_candle
            }

    def _order_indicators_by_dependencies(self, indicators: List[Dict]) -> List[Dict]:
        """Order indicators by their dependencies (e.g., ATR before SuperTrend)"""
        ordered = []
        remaining = indicators.copy()

        while remaining:
            # Find indicators with no unmet dependencies
            ready = []
            for indicator in remaining:
                name = indicator['name']
                deps = self.dependencies.get(name, [])

                # Check if all dependencies are already in ordered list
                deps_met = all(
                    any(ordered_ind['name'] == dep for ordered_ind in ordered)
                    for dep in deps
                )

                if deps_met:
                    ready.append(indicator)

            if not ready:
                # No more dependencies to resolve, add remaining
                ordered.extend(remaining)
                break

            # Add ready indicators and remove from remaining
            ordered.extend(ready)
            for indicator in ready:
                remaining.remove(indicator)

        return ordered

    async def _calculate_timeframe_indicators(
        self,
        symbol: str,
        timeframe: str,
        candle_data: Dict,
        indicators: List[Dict]
    ) -> Dict[str, Any]:
        """Calculate all indicators for a specific timeframe"""

        # Get timeframe-specific candle data
        if timeframe == 'daily':
            current_candle = candle_data['daily']['current']
            previous_candle = candle_data['daily']['previous']
            ohlcv = {
                'open': current_candle['open'],
                'high': current_candle['high'],
                'low': current_candle['low'],
                'close': current_candle['close'],
                'volume': current_candle['volume']
            }
        elif timeframe == 'weekly':
            current_candle = candle_data['daily']['current']
            ohlcv = {
                'open': current_candle['weekly_open'],
                'high': current_candle['weekly_high'],
                'low': current_candle['weekly_low'],
                'close': current_candle['weekly_close'],
                'volume': current_candle['weekly_volume']
            }
            previous_candle = candle_data.get('weekly')
        elif timeframe == 'monthly':
            current_candle = candle_data['daily']['current']
            ohlcv = {
                'open': current_candle['monthly_open'],
                'high': current_candle['monthly_high'],
                'low': current_candle['monthly_low'],
                'close': current_candle['monthly_close'],
                'volume': current_candle['monthly_volume']
            }
            previous_candle = candle_data.get('monthly')

        # Filter indicators for this timeframe
        timeframe_indicators = [
            ind for ind in indicators
            if timeframe in ind.get('timeframes', ['daily'])
        ]

        calculated = []
        current_indicators = json.loads(current_candle.get('indicators', '{}')) if current_candle.get('indicators') else {}

        # Calculate each indicator
        for indicator in timeframe_indicators:
            try:
                result = await self._calculate_single_indicator(
                    symbol, timeframe, indicator, ohlcv,
                    current_indicators, previous_candle
                )
                if result:
                    calculated.append(result)
                    # Update current_indicators for dependent calculations
                    current_indicators.update(result)

            except Exception as e:
                logger.error(f"❌ Error calculating {indicator['name']} for {symbol} {timeframe}: {e}")

        return {
            'calculated': calculated,
            'ohlcv': ohlcv,
            'indicators': current_indicators
        }

    async def _calculate_single_indicator(
        self,
        symbol: str,
        timeframe: str,
        indicator: Dict,
        ohlcv: Dict,
        current_indicators: Dict,
        previous_candle: Optional[asyncpg.Record]
    ) -> Optional[Dict]:
        """Calculate a single indicator value"""

        name = indicator['name']
        params = indicator['parameters']

        # Dispatch to appropriate calculation method
        if name == 'rsi':
            return await self._calculate_rsi_incremental(
                symbol, timeframe, params, ohlcv, current_indicators, previous_candle
            )
        elif name == 'atr':
            return await self._calculate_atr_incremental(
                symbol, timeframe, params, ohlcv, current_indicators, previous_candle
            )
        elif name == 'ema':
            return await self._calculate_ema_incremental(
                symbol, timeframe, params, ohlcv, current_indicators, previous_candle
            )
        elif name == 'sma':
            return await self._calculate_sma_incremental(
                symbol, timeframe, params, ohlcv
            )
        elif name == 'bollinger_bands':
            return await self._calculate_bollinger_bands_incremental(
                symbol, timeframe, params, ohlcv
            )
        elif name == 'supertrend':
            return await self._calculate_supertrend_incremental(
                symbol, timeframe, params, ohlcv, current_indicators, previous_candle
            )
        elif name == 'percentage_change':
            return await self._calculate_percentage_change_incremental(
                symbol, timeframe, params, ohlcv, previous_candle
            )
        else:
            logger.warning(f"⚠️ Unknown indicator: {name}")
            return None

    # Placeholder methods for individual indicators - to be implemented
    async def _calculate_rsi_incremental(self, symbol, timeframe, params, ohlcv, current_indicators, previous_candle):
        """RSI incremental calculation using Wilder's smoothing"""
        try:
            period = params.get('period', 14)

            if not previous_candle:
                logger.warning(f"⚠️ No previous candle for RSI calculation for {symbol} {timeframe}")
                # Fallback: calculate from history
                return await self._calculate_rsi_from_history(symbol, timeframe, period)

            # Get previous states from indicators
            avg_gain_key = f"_{timeframe}_rsi_{period}_avg_gain"
            avg_loss_key = f"_{timeframe}_rsi_{period}_avg_loss"

            # Try to get previous states from current indicators first, then from previous candle
            previous_avg_gain = current_indicators.get(avg_gain_key)
            previous_avg_loss = current_indicators.get(avg_loss_key)

            if previous_avg_gain is None or previous_avg_loss is None:
                # Try from previous candle
                prev_indicators = json.loads(previous_candle.get('indicators', '{}')) if previous_candle.get('indicators') else {}
                previous_avg_gain = prev_indicators.get(avg_gain_key)
                previous_avg_loss = prev_indicators.get(avg_loss_key)

            if previous_avg_gain is None or previous_avg_loss is None:
                logger.warning(f"⚠️ Missing RSI state for {symbol} {timeframe}, calculating from history")
                # Fallback: calculate from history
                return await self._calculate_rsi_from_history(symbol, timeframe, period)

            # Get previous close for change calculation
            if timeframe == 'daily':
                previous_close = float(previous_candle['close'])
            elif timeframe == 'weekly':
                # For weekly RSI, we need the previous week's close
                async with self.pool.acquire() as conn:
                    prev_week = await conn.fetchrow("""
                        SELECT weekly_close
                        FROM daily_candles
                        WHERE symbol = $1 AND weekly_close IS NOT NULL
                        AND datetime < (
                            SELECT MAX(datetime) FROM daily_candles WHERE symbol = $1
                        )
                        ORDER BY datetime DESC
                        LIMIT 1
                    """, symbol)

                    if not prev_week:
                        return await self._calculate_rsi_from_history(symbol, timeframe, period)
                    previous_close = float(prev_week['weekly_close'])
            elif timeframe == 'monthly':
                # For monthly RSI, we need the previous month's close
                async with self.pool.acquire() as conn:
                    prev_month = await conn.fetchrow("""
                        SELECT monthly_close
                        FROM daily_candles
                        WHERE symbol = $1 AND monthly_close IS NOT NULL
                        AND datetime < (
                            SELECT MAX(datetime) FROM daily_candles WHERE symbol = $1
                        )
                        ORDER BY datetime DESC
                        LIMIT 1
                    """, symbol)

                    if not prev_month:
                        return await self._calculate_rsi_from_history(symbol, timeframe, period)
                    previous_close = float(prev_month['monthly_close'])

            current_close = float(ohlcv['close'])

            # Calculate current change
            change = current_close - previous_close
            current_gain = max(0, change)
            current_loss = max(0, -change)

            # Apply Wilder's smoothing (α = 1/period)
            alpha = 1.0 / period
            new_avg_gain = float(previous_avg_gain) + alpha * (current_gain - float(previous_avg_gain))
            new_avg_loss = float(previous_avg_loss) + alpha * (current_loss - float(previous_avg_loss))

            # Calculate RSI
            if new_avg_loss == 0:
                rsi = 100.0
            else:
                rs = new_avg_gain / new_avg_loss
                rsi = 100 - (100 / (1 + rs))

            # Format keys
            rsi_key = f"{timeframe}_rsi_{period}"

            return {
                rsi_key: round(rsi, 2),
                avg_gain_key: round(new_avg_gain, 6),  # Store state for next calculation
                avg_loss_key: round(new_avg_loss, 6)   # Store state for next calculation
            }

        except Exception as e:
            logger.error(f"❌ Error calculating RSI for {symbol} {timeframe}: {e}")
            # Fallback: calculate from history
            return await self._calculate_rsi_from_history(symbol, timeframe, period)

    async def _calculate_rsi_from_history(self, symbol: str, timeframe: str, period: int):
        """Fallback RSI calculation from historical data"""
        try:
            logger.warning(f"⚠️ Calculating RSI from history for {symbol} {timeframe} (period={period})")

            # Get historical data
            async with self.pool.acquire() as conn:
                if timeframe == 'daily':
                    rows = await conn.fetch("""
                        SELECT close
                        FROM daily_candles
                        WHERE symbol = $1
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period + 1)  # +1 for change calculation
                elif timeframe == 'weekly':
                    rows = await conn.fetch("""
                        SELECT weekly_close as close
                        FROM daily_candles
                        WHERE symbol = $1 AND weekly_close IS NOT NULL
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period + 1)
                elif timeframe == 'monthly':
                    rows = await conn.fetch("""
                        SELECT monthly_close as close
                        FROM daily_candles
                        WHERE symbol = $1 AND monthly_close IS NOT NULL
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period + 1)

                if len(rows) < period + 1:
                    logger.warning(f"⚠️ Insufficient data for RSI({period}) for {symbol} {timeframe}: {len(rows)}/{period + 1}")
                    return None

                # Calculate changes (newest first, so reverse for calculation)
                prices = [float(row['close']) for row in reversed(rows)]
                changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]

                gains = [max(0, change) for change in changes]
                losses = [max(0, -change) for change in changes]

                # Calculate initial averages
                if len(gains) >= period:
                    avg_gain = sum(gains[-period:]) / period
                    avg_loss = sum(losses[-period:]) / period
                else:
                    avg_gain = sum(gains) / len(gains) if gains else 0
                    avg_loss = sum(losses) / len(losses) if losses else 0

                # Calculate RSI
                if avg_loss == 0:
                    rsi = 100.0
                else:
                    rs = avg_gain / avg_loss
                    rsi = 100 - (100 / (1 + rs))

                # Format keys
                rsi_key = f"{timeframe}_rsi_{period}"
                avg_gain_key = f"_{timeframe}_rsi_{period}_avg_gain"
                avg_loss_key = f"_{timeframe}_rsi_{period}_avg_loss"

                return {
                    rsi_key: round(rsi, 2),
                    avg_gain_key: round(avg_gain, 6),
                    avg_loss_key: round(avg_loss, 6)
                }

        except Exception as e:
            logger.error(f"❌ Error calculating RSI from history for {symbol} {timeframe}: {e}")
            return None

    async def _calculate_atr_incremental(self, symbol, timeframe, params, ohlcv, current_indicators, previous_candle):
        """ATR incremental calculation using Wilder's smoothing"""
        try:
            period = params.get('period', 14)

            if not previous_candle:
                logger.warning(f"⚠️ No previous candle for ATR calculation for {symbol} {timeframe}")
                # Fallback: calculate from history
                return await self._calculate_atr_from_history(symbol, timeframe, period)

            # Get previous ATR from indicators
            atr_key = f"{timeframe}_atr_{period}"
            previous_atr = current_indicators.get(atr_key)

            if previous_atr is None:
                # Try from previous candle
                prev_indicators = json.loads(previous_candle.get('indicators', '{}')) if previous_candle.get('indicators') else {}
                previous_atr = prev_indicators.get(atr_key)

            if previous_atr is None:
                logger.warning(f"⚠️ Missing ATR state for {symbol} {timeframe}, calculating from history")
                # Fallback: calculate from history
                return await self._calculate_atr_from_history(symbol, timeframe, period)

            # Get previous close for True Range calculation
            if timeframe == 'daily':
                previous_close = float(previous_candle['close'])
            elif timeframe == 'weekly':
                # For weekly ATR, get previous week's close
                async with self.pool.acquire() as conn:
                    prev_week = await conn.fetchrow("""
                        SELECT weekly_close
                        FROM daily_candles
                        WHERE symbol = $1 AND weekly_close IS NOT NULL
                        AND datetime < (
                            SELECT MAX(datetime) FROM daily_candles WHERE symbol = $1
                        )
                        ORDER BY datetime DESC
                        LIMIT 1
                    """, symbol)

                    if not prev_week:
                        return await self._calculate_atr_from_history(symbol, timeframe, period)
                    previous_close = float(prev_week['weekly_close'])
            elif timeframe == 'monthly':
                # For monthly ATR, get previous month's close
                async with self.pool.acquire() as conn:
                    prev_month = await conn.fetchrow("""
                        SELECT monthly_close
                        FROM daily_candles
                        WHERE symbol = $1 AND monthly_close IS NOT NULL
                        AND datetime < (
                            SELECT MAX(datetime) FROM daily_candles WHERE symbol = $1
                        )
                        ORDER BY datetime DESC
                        LIMIT 1
                    """, symbol)

                    if not prev_month:
                        return await self._calculate_atr_from_history(symbol, timeframe, period)
                    previous_close = float(prev_month['monthly_close'])

            # Calculate True Range
            current_high = float(ohlcv['high'])
            current_low = float(ohlcv['low'])

            tr1 = current_high - current_low
            tr2 = abs(current_high - previous_close)
            tr3 = abs(current_low - previous_close)

            true_range = max(tr1, tr2, tr3)

            # Apply Wilder's smoothing: ATR = ((n-1) × Previous_ATR + TR) / n
            new_atr = ((period - 1) * float(previous_atr) + true_range) / period

            return {atr_key: round(new_atr, 2)}

        except Exception as e:
            logger.error(f"❌ Error calculating ATR for {symbol} {timeframe}: {e}")
            # Fallback: calculate from history
            return await self._calculate_atr_from_history(symbol, timeframe, period)

    async def _calculate_atr_from_history(self, symbol: str, timeframe: str, period: int):
        """Fallback ATR calculation from historical data"""
        try:
            logger.warning(f"⚠️ Calculating ATR from history for {symbol} {timeframe} (period={period})")

            # Get historical data
            async with self.pool.acquire() as conn:
                if timeframe == 'daily':
                    rows = await conn.fetch("""
                        SELECT high, low, close
                        FROM daily_candles
                        WHERE symbol = $1
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period + 1)  # +1 for previous close
                elif timeframe == 'weekly':
                    rows = await conn.fetch("""
                        SELECT weekly_high as high, weekly_low as low, weekly_close as close
                        FROM daily_candles
                        WHERE symbol = $1 AND weekly_high IS NOT NULL
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period + 1)
                elif timeframe == 'monthly':
                    rows = await conn.fetch("""
                        SELECT monthly_high as high, monthly_low as low, monthly_close as close
                        FROM daily_candles
                        WHERE symbol = $1 AND monthly_high IS NOT NULL
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period + 1)

                if len(rows) < period + 1:
                    logger.warning(f"⚠️ Insufficient data for ATR({period}) for {symbol} {timeframe}: {len(rows)}/{period + 1}")
                    return None

                # Calculate True Ranges (newest first, so reverse for calculation)
                candles = list(reversed(rows))
                true_ranges = []

                for i in range(1, len(candles)):
                    high = float(candles[i]['high'])
                    low = float(candles[i]['low'])
                    prev_close = float(candles[i-1]['close'])

                    tr1 = high - low
                    tr2 = abs(high - prev_close)
                    tr3 = abs(low - prev_close)

                    true_ranges.append(max(tr1, tr2, tr3))

                if len(true_ranges) < period:
                    logger.warning(f"⚠️ Insufficient true ranges for ATR({period}) for {symbol} {timeframe}")
                    return None

                # Calculate initial ATR (simple average of first period true ranges)
                atr = sum(true_ranges[-period:]) / period

                # Format key
                atr_key = f"{timeframe}_atr_{period}"

                return {atr_key: round(atr, 2)}

        except Exception as e:
            logger.error(f"❌ Error calculating ATR from history for {symbol} {timeframe}: {e}")
            return None

    async def _calculate_ema_incremental(self, symbol, timeframe, params, ohlcv, current_indicators, previous_candle):
        """EMA incremental calculation using exponential smoothing"""
        try:
            period = params.get('period', 20)

            if not previous_candle:
                logger.warning(f"⚠️ No previous candle for EMA calculation for {symbol} {timeframe}")
                # Fallback: calculate from history
                return await self._calculate_ema_from_history(symbol, timeframe, period)

            # Get previous EMA from indicators
            ema_key = f"{timeframe}_ema_{period}"
            previous_ema = current_indicators.get(ema_key)

            if previous_ema is None:
                # Try from previous candle
                prev_indicators = json.loads(previous_candle.get('indicators', '{}')) if previous_candle.get('indicators') else {}
                previous_ema = prev_indicators.get(ema_key)

            if previous_ema is None:
                logger.warning(f"⚠️ Missing EMA state for {symbol} {timeframe}, calculating from history")
                # Fallback: calculate from history
                return await self._calculate_ema_from_history(symbol, timeframe, period)

            # Calculate EMA
            current_close = float(ohlcv['close'])
            smoothing_factor = 2.0 / (period + 1)  # α = 2/(n+1)

            # EMA = (Price × α) + (Previous_EMA × (1-α))
            new_ema = (current_close * smoothing_factor) + (float(previous_ema) * (1 - smoothing_factor))

            return {ema_key: round(new_ema, 2)}

        except Exception as e:
            logger.error(f"❌ Error calculating EMA for {symbol} {timeframe}: {e}")
            # Fallback: calculate from history
            return await self._calculate_ema_from_history(symbol, timeframe, period)

    async def _calculate_ema_from_history(self, symbol: str, timeframe: str, period: int):
        """Fallback EMA calculation from historical data"""
        try:
            logger.warning(f"⚠️ Calculating EMA from history for {symbol} {timeframe} (period={period})")

            # Get historical data (need more data for EMA initialization)
            async with self.pool.acquire() as conn:
                if timeframe == 'daily':
                    rows = await conn.fetch("""
                        SELECT close
                        FROM daily_candles
                        WHERE symbol = $1
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period * 2)  # Extra data for proper EMA initialization
                elif timeframe == 'weekly':
                    rows = await conn.fetch("""
                        SELECT weekly_close as close
                        FROM daily_candles
                        WHERE symbol = $1 AND weekly_close IS NOT NULL
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period * 2)
                elif timeframe == 'monthly':
                    rows = await conn.fetch("""
                        SELECT monthly_close as close
                        FROM daily_candles
                        WHERE symbol = $1 AND monthly_close IS NOT NULL
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period * 2)

                if len(rows) < period:
                    logger.warning(f"⚠️ Insufficient data for EMA({period}) for {symbol} {timeframe}: {len(rows)}/{period}")
                    return None

                # Calculate EMA (newest first, so reverse for calculation)
                prices = [float(row['close']) for row in reversed(rows)]

                # Initialize EMA with SMA of first 'period' values
                if len(prices) >= period:
                    ema = sum(prices[:period]) / period
                    smoothing_factor = 2.0 / (period + 1)

                    # Apply EMA formula for remaining values
                    for i in range(period, len(prices)):
                        ema = (prices[i] * smoothing_factor) + (ema * (1 - smoothing_factor))
                else:
                    # Not enough data, use simple average
                    ema = sum(prices) / len(prices)

                # Format key
                ema_key = f"{timeframe}_ema_{period}"

                return {ema_key: round(ema, 2)}

        except Exception as e:
            logger.error(f"❌ Error calculating EMA from history for {symbol} {timeframe}: {e}")
            return None

    async def _calculate_sma_incremental(self, symbol, timeframe, params, ohlcv):
        """SMA calculation using database window"""
        try:
            period = params.get('period', 20)

            # Get the last 'period' candles for SMA calculation
            async with self.pool.acquire() as conn:
                if timeframe == 'daily':
                    rows = await conn.fetch("""
                        SELECT close
                        FROM daily_candles
                        WHERE symbol = $1
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period)
                elif timeframe == 'weekly':
                    rows = await conn.fetch("""
                        SELECT weekly_close as close
                        FROM daily_candles
                        WHERE symbol = $1 AND weekly_close IS NOT NULL
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period)
                elif timeframe == 'monthly':
                    rows = await conn.fetch("""
                        SELECT monthly_close as close
                        FROM daily_candles
                        WHERE symbol = $1 AND monthly_close IS NOT NULL
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period)

                if len(rows) < period:
                    logger.warning(f"⚠️ Insufficient data for SMA({period}) for {symbol} {timeframe}: {len(rows)}/{period}")
                    return None

                # Calculate SMA
                prices = [float(row['close']) for row in rows]
                sma_value = sum(prices) / len(prices)

                # Format key
                key = f"{timeframe}_sma_{period}"

                return {key: round(sma_value, 2)}

        except Exception as e:
            logger.error(f"❌ Error calculating SMA for {symbol} {timeframe}: {e}")
            return None

    async def _calculate_bollinger_bands_incremental(self, symbol, timeframe, params, ohlcv):
        """Bollinger Bands calculation using database window"""
        try:
            period = params.get('period', 20)
            multiplier = params.get('multiplier', 2.0)

            # Get the last 'period' candles for BB calculation
            async with self.pool.acquire() as conn:
                if timeframe == 'daily':
                    rows = await conn.fetch("""
                        SELECT close
                        FROM daily_candles
                        WHERE symbol = $1
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period)
                elif timeframe == 'weekly':
                    rows = await conn.fetch("""
                        SELECT weekly_close as close
                        FROM daily_candles
                        WHERE symbol = $1 AND weekly_close IS NOT NULL
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period)
                elif timeframe == 'monthly':
                    rows = await conn.fetch("""
                        SELECT monthly_close as close
                        FROM daily_candles
                        WHERE symbol = $1 AND monthly_close IS NOT NULL
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period)

                if len(rows) < period:
                    logger.warning(f"⚠️ Insufficient data for BB({period},{multiplier}) for {symbol} {timeframe}: {len(rows)}/{period}")
                    return None

                # Calculate SMA (middle band)
                prices = [float(row['close']) for row in rows]
                sma = sum(prices) / len(prices)

                # Calculate standard deviation
                variance = sum((price - sma) ** 2 for price in prices) / len(prices)
                std_dev = math.sqrt(variance)

                # Calculate bands
                upper_band = sma + (multiplier * std_dev)
                lower_band = sma - (multiplier * std_dev)

                # Format keys
                multiplier_str = str(multiplier).replace('.', '_')
                bb_key = f"{timeframe}_bb_{period}_{multiplier_str}"

                return {
                    bb_key: {
                        "upper": round(upper_band, 2),
                        "middle": round(sma, 2),
                        "lower": round(lower_band, 2)
                    }
                }

        except Exception as e:
            logger.error(f"❌ Error calculating Bollinger Bands for {symbol} {timeframe}: {e}")
            return None

    async def _calculate_supertrend_incremental(self, symbol, timeframe, params, ohlcv, current_indicators, previous_candle):
        """SuperTrend incremental calculation using ATR and band persistence"""
        try:
            period = params.get('period', 10)
            multiplier = params.get('multiplier', 2.0)

            # SuperTrend requires ATR - it should already be calculated due to dependency ordering
            atr_key = f"{timeframe}_atr_{period}"
            current_atr = current_indicators.get(atr_key)

            if current_atr is None:
                logger.error(f"❌ ATR not available for SuperTrend calculation for {symbol} {timeframe}")
                return None

            if not previous_candle:
                logger.warning(f"⚠️ No previous candle for SuperTrend calculation for {symbol} {timeframe}")
                # Fallback: calculate from history
                return await self._calculate_supertrend_from_history(symbol, timeframe, period, multiplier)

            # Get previous SuperTrend states
            multiplier_str = str(multiplier).replace('.', '_')
            st_key = f"{timeframe}_supertrend_{period}_{multiplier_str}"
            st_dir_key = f"{timeframe}_supertrend_{period}_{multiplier_str}_direction"
            upper_band_key = f"_{timeframe}_supertrend_{period}_{multiplier_str}_upper_band"
            lower_band_key = f"_{timeframe}_supertrend_{period}_{multiplier_str}_lower_band"

            # Get previous states from indicators
            previous_st = current_indicators.get(st_key)
            previous_direction = current_indicators.get(st_dir_key)
            previous_upper_band = current_indicators.get(upper_band_key)
            previous_lower_band = current_indicators.get(lower_band_key)

            if any(x is None for x in [previous_st, previous_direction, previous_upper_band, previous_lower_band]):
                # Try from previous candle
                prev_indicators = json.loads(previous_candle.get('indicators', '{}')) if previous_candle.get('indicators') else {}
                previous_st = prev_indicators.get(st_key)
                previous_direction = prev_indicators.get(st_dir_key)
                previous_upper_band = prev_indicators.get(upper_band_key)
                previous_lower_band = prev_indicators.get(lower_band_key)

            if any(x is None for x in [previous_st, previous_direction, previous_upper_band, previous_lower_band]):
                logger.warning(f"⚠️ Missing SuperTrend state for {symbol} {timeframe}, calculating from history")
                # Fallback: calculate from history
                return await self._calculate_supertrend_from_history(symbol, timeframe, period, multiplier)

            # Calculate basic bands
            current_high = float(ohlcv['high'])
            current_low = float(ohlcv['low'])
            current_close = float(ohlcv['close'])

            hl2 = (current_high + current_low) / 2.0
            atr_value = float(current_atr)

            basic_upper_band = hl2 + (multiplier * atr_value)
            basic_lower_band = hl2 - (multiplier * atr_value)

            # Get previous close for band persistence logic
            previous_close = self._get_previous_close_for_timeframe(symbol, timeframe, previous_candle)
            if previous_close is None:
                return await self._calculate_supertrend_from_history(symbol, timeframe, period, multiplier)

            # Apply band persistence logic
            # Upper band can only move down or stay same
            if basic_upper_band < float(previous_upper_band) or previous_close <= float(previous_upper_band):
                final_upper_band = basic_upper_band
            else:
                final_upper_band = float(previous_upper_band)

            # Lower band can only move up or stay same
            if basic_lower_band > float(previous_lower_band) or previous_close >= float(previous_lower_band):
                final_lower_band = basic_lower_band
            else:
                final_lower_band = float(previous_lower_band)

            # SuperTrend logic
            if float(previous_st) == float(previous_upper_band):
                # Was in downtrend
                if current_close <= final_lower_band:
                    supertrend = final_upper_band
                    direction = -1  # Downtrend
                else:
                    supertrend = final_lower_band
                    direction = 1   # Uptrend
            else:
                # Was in uptrend
                if current_close >= final_upper_band:
                    supertrend = final_lower_band
                    direction = 1   # Uptrend
                else:
                    supertrend = final_upper_band
                    direction = -1  # Downtrend

            return {
                st_key: round(supertrend, 2),
                st_dir_key: direction,
                upper_band_key: round(final_upper_band, 2),  # Store for next calculation
                lower_band_key: round(final_lower_band, 2)   # Store for next calculation
            }

        except Exception as e:
            logger.error(f"❌ Error calculating SuperTrend for {symbol} {timeframe}: {e}")
            # Fallback: calculate from history
            return await self._calculate_supertrend_from_history(symbol, timeframe, period, multiplier)

    def _get_previous_close_for_timeframe(self, symbol: str, timeframe: str, previous_candle):
        """Helper to get previous close based on timeframe"""
        try:
            if timeframe == 'daily':
                return float(previous_candle['close'])
            # For weekly/monthly, we need more complex logic - simplified for now
            return float(previous_candle['close'])
        except:
            return None

    async def _calculate_supertrend_from_history(self, symbol: str, timeframe: str, period: int, multiplier: float):
        """Fallback SuperTrend calculation from historical data"""
        try:
            logger.warning(f"⚠️ Calculating SuperTrend from history for {symbol} {timeframe} (period={period}, multiplier={multiplier})")

            # First ensure ATR is calculated
            atr_result = await self._calculate_atr_from_history(symbol, timeframe, period)
            if not atr_result:
                return None

            # Get historical data for SuperTrend calculation
            async with self.pool.acquire() as conn:
                if timeframe == 'daily':
                    rows = await conn.fetch("""
                        SELECT high, low, close
                        FROM daily_candles
                        WHERE symbol = $1
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period + 5)  # Extra data for stability
                elif timeframe == 'weekly':
                    rows = await conn.fetch("""
                        SELECT weekly_high as high, weekly_low as low, weekly_close as close
                        FROM daily_candles
                        WHERE symbol = $1 AND weekly_high IS NOT NULL
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period + 5)
                elif timeframe == 'monthly':
                    rows = await conn.fetch("""
                        SELECT monthly_high as high, monthly_low as low, monthly_close as close
                        FROM daily_candles
                        WHERE symbol = $1 AND monthly_high IS NOT NULL
                        ORDER BY datetime DESC
                        LIMIT $2
                    """, symbol, period + 5)

                if len(rows) < 3:  # Need at least 3 candles for SuperTrend
                    logger.warning(f"⚠️ Insufficient data for SuperTrend for {symbol} {timeframe}")
                    return None

                # Use the latest candle for calculation
                latest = rows[0]
                current_high = float(latest['high'])
                current_low = float(latest['low'])
                current_close = float(latest['close'])

                # Calculate basic SuperTrend (simplified)
                hl2 = (current_high + current_low) / 2.0
                atr_value = float(list(atr_result.values())[0])

                upper_band = hl2 + (multiplier * atr_value)
                lower_band = hl2 - (multiplier * atr_value)

                # Initial SuperTrend (simplified - use lower band for uptrend assumption)
                supertrend = lower_band
                direction = 1

                # Format keys
                multiplier_str = str(multiplier).replace('.', '_')
                st_key = f"{timeframe}_supertrend_{period}_{multiplier_str}"
                st_dir_key = f"{timeframe}_supertrend_{period}_{multiplier_str}_direction"
                upper_band_key = f"_{timeframe}_supertrend_{period}_{multiplier_str}_upper_band"
                lower_band_key = f"_{timeframe}_supertrend_{period}_{multiplier_str}_lower_band"

                result = {
                    st_key: round(supertrend, 2),
                    st_dir_key: direction,
                    upper_band_key: round(upper_band, 2),
                    lower_band_key: round(lower_band, 2)
                }

                # Merge with ATR result
                result.update(atr_result)
                return result

        except Exception as e:
            logger.error(f"❌ Error calculating SuperTrend from history for {symbol} {timeframe}: {e}")
            return None

    async def _calculate_percentage_change_incremental(self, symbol, timeframe, params, ohlcv, previous_candle):
        """Percentage change calculation"""
        try:
            if not previous_candle:
                logger.warning(f"⚠️ No previous candle for percentage change calculation for {symbol} {timeframe}")
                return None

            current_close = float(ohlcv['close'])

            # Get previous close based on timeframe
            if timeframe == 'daily':
                previous_close = float(previous_candle['close'])
            elif timeframe == 'weekly':
                # For weekly percentage change, we need previous week's close
                async with self.pool.acquire() as conn:
                    prev_week = await conn.fetchrow("""
                        SELECT weekly_close
                        FROM daily_candles
                        WHERE symbol = $1 AND weekly_close IS NOT NULL
                        AND datetime < (
                            SELECT MAX(datetime) FROM daily_candles WHERE symbol = $1
                        )
                        ORDER BY datetime DESC
                        LIMIT 1
                    """, symbol)

                    if not prev_week:
                        return None
                    previous_close = float(prev_week['weekly_close'])
            elif timeframe == 'monthly':
                # For monthly percentage change, we need previous month's close
                async with self.pool.acquire() as conn:
                    prev_month = await conn.fetchrow("""
                        SELECT monthly_close
                        FROM daily_candles
                        WHERE symbol = $1 AND monthly_close IS NOT NULL
                        AND datetime < (
                            SELECT MAX(datetime) FROM daily_candles WHERE symbol = $1
                        )
                        ORDER BY datetime DESC
                        LIMIT 1
                    """, symbol)

                    if not prev_month:
                        return None
                    previous_close = float(prev_month['monthly_close'])

            if previous_close == 0:
                logger.warning(f"⚠️ Previous close is zero for {symbol} {timeframe}")
                return None

            # Calculate percentage change
            percentage_change = ((current_close - previous_close) / previous_close) * 100

            # Format key
            key = f"{timeframe}_percentage_change"

            return {key: round(percentage_change, 2)}

        except Exception as e:
            logger.error(f"❌ Error calculating percentage change for {symbol} {timeframe}: {e}")
            return None

    async def _update_indicators_in_database(self, symbol: str, results: Dict[str, Any]):
        """Update calculated indicators in database tables"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Update daily_candles
                if 'daily' in results:
                    daily_indicators = results['daily']['indicators']
                    await conn.execute("""
                        UPDATE daily_candles
                        SET indicators = $2, updated_at = CURRENT_TIMESTAMP
                        WHERE symbol = $1
                        AND datetime = (
                            SELECT MAX(datetime) FROM daily_candles WHERE symbol = $1
                        )
                    """, symbol, json.dumps(daily_indicators))

                # Update weekly_candles if applicable
                if 'weekly' in results and results['weekly']['indicators']:
                    weekly_indicators = results['weekly']['indicators']
                    await conn.execute("""
                        UPDATE weekly_candles
                        SET indicators = $2, updated_at = CURRENT_TIMESTAMP
                        WHERE candle_key_id = (
                            SELECT weekly_candle_key_id FROM daily_candles
                            WHERE symbol = $1
                            ORDER BY datetime DESC LIMIT 1
                        )
                    """, symbol, json.dumps(weekly_indicators))

                # Update monthly_candles if applicable
                if 'monthly' in results and results['monthly']['indicators']:
                    monthly_indicators = results['monthly']['indicators']
                    await conn.execute("""
                        UPDATE monthly_candles
                        SET indicators = $2, updated_at = CURRENT_TIMESTAMP
                        WHERE candle_key_id = (
                            SELECT monthly_candle_key_id FROM daily_candles
                            WHERE symbol = $1
                            ORDER BY datetime DESC LIMIT 1
                        )
                    """, symbol, json.dumps(monthly_indicators))

# Global instance
cron_indicator_calculator = CronIndicatorCalculator()