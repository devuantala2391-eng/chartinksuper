"""
Indicator Validation Service
Validates that cron-calculated indicators match hard-refresh indicators exactly
Ensures data integrity and calculation accuracy across different calculation methods
"""

import asyncio
import asyncpg
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

class IndicatorValidationService:
    """
    Service to validate that cron indicator calculations match hard-refresh calculations.
    Tests all indicators across all timeframes for accuracy and consistency.
    """

    def __init__(self):
        self.pool = None
        self.validation_results = {}

        # Tolerance for floating point comparison (0.01 = 1 cent)
        self.tolerance = 0.01

        # Known indicators to validate
        self.indicators_to_validate = [
            'rsi', 'atr', 'ema', 'sma', 'bollinger_bands', 'supertrend', 'percentage_change'
        ]

        # Timeframes to validate
        self.timeframes = ['daily', 'weekly', 'monthly']

    async def initialize(self):
        """Initialize database connection pool"""
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                host=os.getenv('POSTGRES_HOST', 'localhost'),
                port=int(os.getenv('POSTGRES_PORT', '5432')),
                database='nse_highspeed',
                user=os.getenv('POSTGRES_USER', 'postgres'),
                password=os.getenv('POSTGRES_PASSWORD', '123'),
                min_size=5,
                max_size=20,
                command_timeout=300  # 5 minutes for complex calculations
            )
        logger.info("🔍 Indicator validation service initialized")

    async def close(self):
        """Close database connections"""
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def validate_all_symbols(self, symbols: Optional[List[str]] = None,
                                 sample_size: int = 10) -> Dict[str, Any]:
        """
        Validate indicators for all symbols (or a sample).

        Args:
            symbols: List of symbols to validate, or None for all
            sample_size: Number of symbols to sample if symbols is None

        Returns:
            Comprehensive validation report
        """
        try:
            start_time = datetime.now()

            # Get symbols to validate
            if symbols is None:
                symbols = await self._get_sample_symbols(sample_size)

            logger.info(f"🧪 Starting indicator validation for {len(symbols)} symbols")

            validation_results = {
                'summary': {
                    'total_symbols': len(symbols),
                    'symbols_validated': 0,
                    'symbols_failed': 0,
                    'total_indicators_tested': 0,
                    'indicators_passed': 0,
                    'indicators_failed': 0,
                    'accuracy_percentage': 0.0
                },
                'symbol_results': {},
                'failed_symbols': [],
                'failed_indicators': [],
                'start_time': start_time.isoformat(),
                'duration_seconds': 0
            }

            # Validate each symbol
            for symbol in symbols:
                try:
                    symbol_result = await self.validate_symbol_indicators(symbol)
                    validation_results['symbol_results'][symbol] = symbol_result

                    if symbol_result['success']:
                        validation_results['summary']['symbols_validated'] += 1
                        validation_results['summary']['total_indicators_tested'] += symbol_result['total_tested']
                        validation_results['summary']['indicators_passed'] += symbol_result['passed']
                        validation_results['summary']['indicators_failed'] += symbol_result['failed']
                    else:
                        validation_results['summary']['symbols_failed'] += 1
                        validation_results['failed_symbols'].append(symbol)

                        # Add individual failures
                        for failure in symbol_result.get('failures', []):
                            validation_results['failed_indicators'].append({
                                'symbol': symbol,
                                **failure
                            })

                    # Log progress
                    completed = validation_results['summary']['symbols_validated'] + validation_results['summary']['symbols_failed']
                    if completed % 5 == 0 or completed == len(symbols):
                        logger.info(f"📊 Validation progress: {completed}/{len(symbols)} symbols")

                except Exception as e:
                    logger.error(f"❌ Failed to validate {symbol}: {e}")
                    validation_results['summary']['symbols_failed'] += 1
                    validation_results['failed_symbols'].append(symbol)

            # Calculate final accuracy
            total_tested = validation_results['summary']['total_indicators_tested']
            total_passed = validation_results['summary']['indicators_passed']

            if total_tested > 0:
                validation_results['summary']['accuracy_percentage'] = (total_passed / total_tested) * 100

            # Calculate duration
            end_time = datetime.now()
            validation_results['end_time'] = end_time.isoformat()
            validation_results['duration_seconds'] = (end_time - start_time).total_seconds()

            # Log summary
            summary = validation_results['summary']
            logger.info(f"✅ Validation completed: {summary['accuracy_percentage']:.1f}% accuracy")
            logger.info(f"📊 Results: {summary['indicators_passed']}/{summary['total_indicators_tested']} indicators passed")
            logger.info(f"⏱️ Duration: {validation_results['duration_seconds']:.1f}s")

            return validation_results

        except Exception as e:
            logger.error(f"❌ Validation failed: {e}")
            return {
                'success': False,
                'error': str(e),
                'summary': validation_results.get('summary', {})
            }

    async def validate_symbol_indicators(self, symbol: str) -> Dict[str, Any]:
        """
        Validate all indicators for a single symbol across all timeframes.

        Args:
            symbol: Symbol to validate

        Returns:
            Validation results for the symbol
        """
        try:
            logger.debug(f"🔍 Validating indicators for {symbol}")

            result = {
                'success': True,
                'symbol': symbol,
                'total_tested': 0,
                'passed': 0,
                'failed': 0,
                'timeframe_results': {},
                'failures': []
            }

            # Get current indicator values (cron-calculated)
            current_indicators = await self._get_current_indicators(symbol)

            # Backup current indicators
            backed_up_indicators = await self._backup_current_indicators(symbol)

            try:
                # Calculate fresh indicators using hard-refresh method
                fresh_indicators = await self._calculate_fresh_indicators(symbol)

                # Compare indicators across all timeframes
                for timeframe in self.timeframes:
                    timeframe_result = await self._compare_timeframe_indicators(
                        symbol, timeframe, current_indicators.get(timeframe, {}),
                        fresh_indicators.get(timeframe, {})
                    )

                    result['timeframe_results'][timeframe] = timeframe_result
                    result['total_tested'] += timeframe_result['total_tested']
                    result['passed'] += timeframe_result['passed']
                    result['failed'] += timeframe_result['failed']

                    # Collect failures
                    for failure in timeframe_result.get('failures', []):
                        result['failures'].append({
                            'timeframe': timeframe,
                            **failure
                        })

                if result['failed'] > 0:
                    result['success'] = False

            finally:
                # Restore original indicators
                await self._restore_indicators(symbol, backed_up_indicators)

            logger.debug(f"✅ {symbol}: {result['passed']}/{result['total_tested']} indicators validated")
            return result

        except Exception as e:
            logger.error(f"❌ Error validating {symbol}: {e}")
            return {
                'success': False,
                'symbol': symbol,
                'error': str(e),
                'total_tested': 0,
                'passed': 0,
                'failed': 0
            }

    async def _get_sample_symbols(self, sample_size: int) -> List[str]:
        """Get a sample of symbols for validation"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT symbol
                FROM daily_candles
                WHERE indicators IS NOT NULL
                AND jsonb_typeof(indicators) = 'object'
                ORDER BY symbol
                LIMIT $1
            """, sample_size)

            return [row['symbol'] for row in rows]

    async def _get_current_indicators(self, symbol: str) -> Dict[str, Dict]:
        """Get current indicator values for all timeframes"""
        async with self.pool.acquire() as conn:
            indicators = {}

            # Get daily indicators
            daily_row = await conn.fetchrow("""
                SELECT indicators
                FROM daily_candles
                WHERE symbol = $1
                ORDER BY datetime DESC
                LIMIT 1
            """, symbol)

            if daily_row and daily_row['indicators']:
                indicators['daily'] = json.loads(daily_row['indicators'])

            # Get weekly indicators
            weekly_row = await conn.fetchrow("""
                SELECT wc.indicators
                FROM weekly_candles wc
                JOIN daily_candles dc ON wc.candle_key_id = dc.weekly_candle_key_id
                WHERE dc.symbol = $1
                ORDER BY dc.datetime DESC
                LIMIT 1
            """, symbol)

            if weekly_row and weekly_row['indicators']:
                indicators['weekly'] = json.loads(weekly_row['indicators'])

            # Get monthly indicators
            monthly_row = await conn.fetchrow("""
                SELECT mc.indicators
                FROM monthly_candles mc
                JOIN daily_candles dc ON mc.candle_key_id = dc.monthly_candle_key_id
                WHERE dc.symbol = $1
                ORDER BY dc.datetime DESC
                LIMIT 1
            """, symbol)

            if monthly_row and monthly_row['indicators']:
                indicators['monthly'] = json.loads(monthly_row['indicators'])

            return indicators

    async def _backup_current_indicators(self, symbol: str) -> Dict[str, Any]:
        """Backup current indicators before fresh calculation"""
        return await self._get_current_indicators(symbol)

    async def _calculate_fresh_indicators(self, symbol: str) -> Dict[str, Dict]:
        """Calculate fresh indicators using hard-refresh method"""
        async with self.pool.acquire() as conn:
            # Get active indicators configuration
            indicator_configs = await conn.fetch("""
                SELECT name, parameters, timeframes
                FROM indicator_registry
                WHERE enabled = true
            """)

            fresh_indicators = {'daily': {}, 'weekly': {}, 'monthly': {}}

            for config in indicator_configs:
                name = config['name']
                params = json.loads(config['parameters']) if config['parameters'] else {}
                timeframes = json.loads(config['timeframes']) if config['timeframes'] else ['daily']

                for timeframe in timeframes:
                    if timeframe in self.timeframes:
                        # Call appropriate hard-refresh calculation function
                        await self._calculate_indicator_hard_refresh(
                            conn, symbol, timeframe, name, params, fresh_indicators
                        )

            return fresh_indicators

    async def _calculate_indicator_hard_refresh(self, conn, symbol: str, timeframe: str,
                                              indicator_name: str, params: Dict,
                                              fresh_indicators: Dict):
        """Calculate a single indicator using hard-refresh method"""
        try:
            if indicator_name == 'rsi':
                period = params.get('period', 14)
                if timeframe == 'daily':
                    await conn.execute("SELECT calculate_daily_rsi_for_symbol($1, $2, true)", symbol, period)
                elif timeframe == 'weekly':
                    await conn.execute("SELECT calculate_weekly_rsi_for_symbol($1, $2, true)", symbol, period)
                elif timeframe == 'monthly':
                    await conn.execute("SELECT calculate_monthly_rsi_for_symbol($1, $2, true)", symbol, period)

            elif indicator_name == 'atr':
                period = params.get('period', 14)
                if timeframe == 'daily':
                    await conn.execute("SELECT calculate_daily_atr_for_symbol($1, $2, true)", symbol, period)
                elif timeframe == 'weekly':
                    await conn.execute("SELECT calculate_weekly_atr_for_symbol($1, $2, true)", symbol, period)
                elif timeframe == 'monthly':
                    await conn.execute("SELECT calculate_monthly_atr_for_symbol($1, $2, true)", symbol, period)

            elif indicator_name == 'ema':
                period = params.get('period', 20)
                if timeframe == 'daily':
                    await conn.execute("SELECT calculate_daily_ema_for_symbol($1, $2, true)", symbol, period)
                elif timeframe == 'weekly':
                    await conn.execute("SELECT calculate_weekly_ema_for_symbol($1, $2, true)", symbol, period)
                elif timeframe == 'monthly':
                    await conn.execute("SELECT calculate_monthly_ema_for_symbol($1, $2, true)", symbol, period)

            elif indicator_name == 'sma':
                period = params.get('period', 20)
                if timeframe == 'daily':
                    await conn.execute("SELECT calculate_daily_sma_for_symbol($1, $2, true)", symbol, period)
                elif timeframe == 'weekly':
                    await conn.execute("SELECT calculate_weekly_sma_for_symbol($1, $2, true)", symbol, period)
                elif timeframe == 'monthly':
                    await conn.execute("SELECT calculate_monthly_sma_for_symbol($1, $2, true)", symbol, period)

            elif indicator_name == 'bollinger_bands':
                period = params.get('period', 20)
                multiplier = params.get('multiplier', 2.0)
                if timeframe == 'daily':
                    await conn.execute("SELECT calculate_daily_bollinger_bands_for_symbol($1, $2, $3, true)", symbol, period, multiplier)
                elif timeframe == 'weekly':
                    await conn.execute("SELECT calculate_weekly_bollinger_bands_for_symbol($1, $2, $3, true)", symbol, period, multiplier)
                elif timeframe == 'monthly':
                    await conn.execute("SELECT calculate_monthly_bollinger_bands_for_symbol($1, $2, $3, true)", symbol, period, multiplier)

            elif indicator_name == 'supertrend':
                period = params.get('period', 10)
                multiplier = params.get('multiplier', 2.0)
                if timeframe == 'daily':
                    await conn.execute("SELECT calculate_daily_supertrend_for_symbol($1, $2, $3, true)", symbol, period, multiplier)
                elif timeframe == 'weekly':
                    await conn.execute("SELECT calculate_weekly_supertrend_for_symbol($1, $2, $3, true)", symbol, period, multiplier)
                elif timeframe == 'monthly':
                    await conn.execute("SELECT calculate_monthly_supertrend_for_symbol($1, $2, $3, true)", symbol, period, multiplier)

            elif indicator_name == 'percentage_change':
                if timeframe == 'daily':
                    await conn.execute("SELECT calculate_daily_percentage_change_for_symbol($1, true)", symbol)
                elif timeframe == 'weekly':
                    await conn.execute("SELECT calculate_weekly_percentage_change_for_symbol($1, true)", symbol)
                elif timeframe == 'monthly':
                    await conn.execute("SELECT calculate_monthly_percentage_change_for_symbol($1, true)", symbol)

            # Get the fresh indicators after calculation
            await asyncio.sleep(0.1)  # Small delay for database commit
            fresh_data = await self._get_current_indicators(symbol)

            # Update fresh_indicators with the calculated values
            for tf in fresh_data:
                if tf in fresh_indicators:
                    fresh_indicators[tf].update(fresh_data[tf])

        except Exception as e:
            logger.warning(f"⚠️ Failed to calculate {indicator_name} for {symbol} {timeframe}: {e}")

    async def _compare_timeframe_indicators(self, symbol: str, timeframe: str,
                                          current: Dict, fresh: Dict) -> Dict[str, Any]:
        """Compare indicators for a specific timeframe"""
        result = {
            'timeframe': timeframe,
            'total_tested': 0,
            'passed': 0,
            'failed': 0,
            'failures': []
        }

        # Get all indicator keys to compare
        all_keys = set(current.keys()) | set(fresh.keys())

        for key in all_keys:
            # Skip internal state keys (they start with underscore)
            if key.startswith('_'):
                continue

            # Skip if key doesn't match timeframe
            if not key.startswith(timeframe):
                continue

            result['total_tested'] += 1

            current_value = current.get(key)
            fresh_value = fresh.get(key)

            # Check if values match
            if self._values_match(current_value, fresh_value):
                result['passed'] += 1
            else:
                result['failed'] += 1
                result['failures'].append({
                    'indicator_key': key,
                    'current_value': current_value,
                    'fresh_value': fresh_value,
                    'difference': self._calculate_difference(current_value, fresh_value)
                })

        return result

    def _values_match(self, value1: Any, value2: Any) -> bool:
        """Check if two indicator values match within tolerance"""
        try:
            # Handle None values
            if value1 is None and value2 is None:
                return True
            if value1 is None or value2 is None:
                return False

            # Handle complex objects (like Bollinger Bands)
            if isinstance(value1, dict) and isinstance(value2, dict):
                return self._compare_dict_values(value1, value2)

            # Handle numeric values
            if isinstance(value1, (int, float, Decimal)) and isinstance(value2, (int, float, Decimal)):
                return abs(float(value1) - float(value2)) <= self.tolerance

            # Handle string representations of numbers
            if isinstance(value1, str) and isinstance(value2, str):
                try:
                    return abs(float(value1) - float(value2)) <= self.tolerance
                except ValueError:
                    return value1 == value2

            # Direct comparison
            return value1 == value2

        except Exception:
            return False

    def _compare_dict_values(self, dict1: Dict, dict2: Dict) -> bool:
        """Compare dictionary values (for complex indicators like Bollinger Bands)"""
        keys1 = set(dict1.keys())
        keys2 = set(dict2.keys())

        if keys1 != keys2:
            return False

        for key in keys1:
            if not self._values_match(dict1[key], dict2[key]):
                return False

        return True

    def _calculate_difference(self, value1: Any, value2: Any) -> Optional[float]:
        """Calculate numeric difference between two values"""
        try:
            if isinstance(value1, dict) and isinstance(value2, dict):
                # For complex objects, calculate average difference
                differences = []
                for key in value1.keys():
                    if key in value2:
                        diff = self._calculate_difference(value1[key], value2[key])
                        if diff is not None:
                            differences.append(diff)
                return sum(differences) / len(differences) if differences else None

            if isinstance(value1, (int, float, Decimal)) and isinstance(value2, (int, float, Decimal)):
                return abs(float(value1) - float(value2))

            return None
        except:
            return None

    async def _restore_indicators(self, symbol: str, backed_up_indicators: Dict[str, Any]):
        """Restore original indicators after validation"""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Restore daily indicators
                if 'daily' in backed_up_indicators:
                    await conn.execute("""
                        UPDATE daily_candles
                        SET indicators = $2, updated_at = CURRENT_TIMESTAMP
                        WHERE symbol = $1
                        AND datetime = (SELECT MAX(datetime) FROM daily_candles WHERE symbol = $1)
                    """, symbol, json.dumps(backed_up_indicators['daily']))

                # Restore weekly indicators
                if 'weekly' in backed_up_indicators:
                    await conn.execute("""
                        UPDATE weekly_candles
                        SET indicators = $2, updated_at = CURRENT_TIMESTAMP
                        WHERE candle_key_id = (
                            SELECT weekly_candle_key_id FROM daily_candles
                            WHERE symbol = $1
                            ORDER BY datetime DESC LIMIT 1
                        )
                    """, symbol, json.dumps(backed_up_indicators['weekly']))

                # Restore monthly indicators
                if 'monthly' in backed_up_indicators:
                    await conn.execute("""
                        UPDATE monthly_candles
                        SET indicators = $2, updated_at = CURRENT_TIMESTAMP
                        WHERE candle_key_id = (
                            SELECT monthly_candle_key_id FROM daily_candles
                            WHERE symbol = $1
                            ORDER BY datetime DESC LIMIT 1
                        )
                    """, symbol, json.dumps(backed_up_indicators['monthly']))

    async def quick_validation(self, symbol: str) -> Dict[str, Any]:
        """Quick validation for a single symbol (useful for testing)"""
        try:
            logger.info(f"🧪 Quick validation for {symbol}")
            result = await self.validate_symbol_indicators(symbol)

            if result['success']:
                logger.info(f"✅ {symbol}: {result['passed']}/{result['total_tested']} indicators passed")
            else:
                logger.warning(f"❌ {symbol}: {result['failed']} indicators failed")
                for failure in result['failures']:
                    logger.warning(f"   - {failure['timeframe']} {failure['indicator_key']}: {failure['current_value']} ≠ {failure['fresh_value']}")

            return result

        except Exception as e:
            logger.error(f"❌ Quick validation failed for {symbol}: {e}")
            return {'success': False, 'error': str(e)}

# Global instance
indicator_validation_service = IndicatorValidationService()