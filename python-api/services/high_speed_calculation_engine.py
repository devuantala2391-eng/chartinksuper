"""
High-Speed Calculation Engine
Optimized for concurrent processing of indicators across multiple stocks
"""

import asyncio
import logging
from typing import Dict, List, Any, Tuple, Optional
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import numpy as np
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

class HighSpeedCalculationEngine:
    """
    Ultra-fast calculation engine optimized for concurrent processing.
    Uses process pools for CPU-intensive calculations and async for I/O.
    """
    
    def __init__(self, max_workers: int = None):
        # Use all CPU cores for calculations
        import os
        self.max_workers = max_workers or min(32, os.cpu_count() or 4)
        self.process_executor = ProcessPoolExecutor(max_workers=self.max_workers)
        self.thread_executor = ThreadPoolExecutor(max_workers=self.max_workers * 2)
        
        # Semaphore to control concurrent calculations
        self.calculation_semaphore = asyncio.Semaphore(50)
        
        logger.info(f"Initialized high-speed calculation engine with {self.max_workers} workers")

    async def calculate_all_indicators_batch(self, stock_data_batch: List[Tuple[str, List[Dict]]]) -> Dict[str, List[Dict]]:
        """
        Calculate all indicators for a batch of stocks concurrently.
        Returns enhanced stock data with all indicators calculated.
        """
        logger.info(f"Processing batch of {len(stock_data_batch)} stocks")
        
        # Process stocks concurrently with semaphore control
        tasks = []
        for symbol, candles in stock_data_batch:
            task = asyncio.create_task(self._process_single_stock_with_semaphore(symbol, candles))
            tasks.append(task)
        
        # Execute all calculations in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Organize results
        processed_data = {}
        successful = 0
        failed = 0
        
        for i, (symbol, _) in enumerate(stock_data_batch):
            result = results[i]
            if isinstance(result, Exception):
                logger.error(f"Failed to process {symbol}: {result}")
                failed += 1
                processed_data[symbol] = []
            else:
                processed_data[symbol] = result
                successful += 1
        
        logger.info(f"Batch processing completed: {successful} successful, {failed} failed")
        return processed_data

    async def _process_single_stock_with_semaphore(self, symbol: str, candles: List[Dict]) -> List[Dict]:
        """Process single stock with semaphore control for resource management"""
        async with self.calculation_semaphore:
            return await self._calculate_all_indicators_for_stock(symbol, candles)

    async def _calculate_all_indicators_for_stock(self, symbol: str, candles: List[Dict]) -> List[Dict]:
        """Calculate all indicators for a single stock using parallel processing"""
        try:
            if not candles:
                return []
            
            # Extract price arrays
            closes = np.array([float(c.get('close', 0)) for c in candles], dtype=np.float64)
            highs = np.array([float(c.get('high', 0)) for c in candles], dtype=np.float64)
            lows = np.array([float(c.get('low', 0)) for c in candles], dtype=np.float64)
            opens = np.array([float(c.get('open', 0)) for c in candles], dtype=np.float64)
            volumes = np.array([float(c.get('volume', 0)) for c in candles], dtype=np.float64)
            
            # Calculate all indicators in parallel using process pool
            calculation_tasks = [
                # RSI calculations
                asyncio.get_event_loop().run_in_executor(
                    self.process_executor, calculate_rsi_optimized, closes, 14
                ),
                asyncio.get_event_loop().run_in_executor(
                    self.process_executor, calculate_rsi_optimized, closes, 21
                ),
                
                # SMA calculations
                asyncio.get_event_loop().run_in_executor(
                    self.process_executor, calculate_sma_optimized, closes, 20
                ),
                asyncio.get_event_loop().run_in_executor(
                    self.process_executor, calculate_sma_optimized, closes, 50
                ),
                asyncio.get_event_loop().run_in_executor(
                    self.process_executor, calculate_sma_optimized, closes, 200
                ),
                
                # EMA calculations
                asyncio.get_event_loop().run_in_executor(
                    self.process_executor, calculate_ema_optimized, closes, 12
                ),
                asyncio.get_event_loop().run_in_executor(
                    self.process_executor, calculate_ema_optimized, closes, 26
                ),
                
                # SuperTrend calculations
                asyncio.get_event_loop().run_in_executor(
                    self.process_executor, calculate_supertrend_optimized, highs, lows, closes, 10, 2
                ),
                asyncio.get_event_loop().run_in_executor(
                    self.process_executor, calculate_supertrend_optimized, highs, lows, closes, 10, 3
                ),
                
                # Bollinger Bands calculation
                asyncio.get_event_loop().run_in_executor(
                    self.process_executor, calculate_bollinger_bands_optimized, closes, 20, 2
                ),
                
                # Performance calculations
                asyncio.get_event_loop().run_in_executor(
                    self.process_executor, calculate_performance_metrics, closes
                ),
            ]
            
            # Wait for all calculations to complete
            results = await asyncio.gather(*calculation_tasks)
            
            # Unpack results
            (rsi_14, rsi_21, sma_20, sma_50, sma_200, ema_12, ema_26, 
             supertrend_10_2, supertrend_10_3, bollinger_bands, performance_metrics) = results
            
            # Combine all data into enhanced candles
            enhanced_candles = []
            for i, candle in enumerate(candles):
                enhanced_candle = candle.copy()
                enhanced_candle.update({
                    # RSI indicators
                    'rsi_14': float(rsi_14[i]) if i < len(rsi_14) and not np.isnan(rsi_14[i]) else None,
                    'rsi_21': float(rsi_21[i]) if i < len(rsi_21) and not np.isnan(rsi_21[i]) else None,
                    
                    # SMA indicators
                    'sma_20': float(sma_20[i]) if i < len(sma_20) and not np.isnan(sma_20[i]) else None,
                    'sma_50': float(sma_50[i]) if i < len(sma_50) and not np.isnan(sma_50[i]) else None,
                    'sma_200': float(sma_200[i]) if i < len(sma_200) and not np.isnan(sma_200[i]) else None,
                    
                    # EMA indicators
                    'ema_12': float(ema_12[i]) if i < len(ema_12) and not np.isnan(ema_12[i]) else None,
                    'ema_26': float(ema_26[i]) if i < len(ema_26) and not np.isnan(ema_26[i]) else None,
                    
                    # SuperTrend indicators
                    'supertrend_10_2': float(supertrend_10_2['values'][i]) if i < len(supertrend_10_2['values']) and not np.isnan(supertrend_10_2['values'][i]) else None,
                    'supertrend_signal_10_2': int(supertrend_10_2['signals'][i]) if i < len(supertrend_10_2['signals']) else 0,
                    'supertrend_10_3': float(supertrend_10_3['values'][i]) if i < len(supertrend_10_3['values']) and not np.isnan(supertrend_10_3['values'][i]) else None,
                    'supertrend_signal_10_3': int(supertrend_10_3['signals'][i]) if i < len(supertrend_10_3['signals']) else 0,
                    
                    # Bollinger Bands
                    'bb_upper_20_2': float(bollinger_bands['upper'][i]) if i < len(bollinger_bands['upper']) and not np.isnan(bollinger_bands['upper'][i]) else None,
                    'bb_middle_20_2': float(bollinger_bands['middle'][i]) if i < len(bollinger_bands['middle']) and not np.isnan(bollinger_bands['middle'][i]) else None,
                    'bb_lower_20_2': float(bollinger_bands['lower'][i]) if i < len(bollinger_bands['lower']) and not np.isnan(bollinger_bands['lower'][i]) else None,
                    
                    # Performance metrics
                    'change_1d': float(performance_metrics['change_1d'][i]) if i < len(performance_metrics['change_1d']) and not np.isnan(performance_metrics['change_1d'][i]) else None,
                    'change_7d': float(performance_metrics['change_7d'][i]) if i < len(performance_metrics['change_7d']) and not np.isnan(performance_metrics['change_7d'][i]) else None,
                    'change_30d': float(performance_metrics['change_30d'][i]) if i < len(performance_metrics['change_30d']) and not np.isnan(performance_metrics['change_30d'][i]) else None,
                })
                enhanced_candles.append(enhanced_candle)
            
            return enhanced_candles
            
        except Exception as e:
            logger.error(f"Error calculating indicators for {symbol}: {e}")
            return candles  # Return original candles if calculation fails

    async def calculate_weekly_monthly_aggregations(self, daily_candles: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """Calculate weekly and monthly aggregations with indicators"""
        try:
            # Use thread pool for aggregation calculations
            weekly_task = asyncio.get_event_loop().run_in_executor(
                self.thread_executor, calculate_weekly_aggregation, daily_candles
            )
            monthly_task = asyncio.get_event_loop().run_in_executor(
                self.thread_executor, calculate_monthly_aggregation, daily_candles
            )
            
            weekly_data, monthly_data = await asyncio.gather(weekly_task, monthly_task)
            
            # Calculate indicators for aggregated data
            if weekly_data:
                enhanced_weekly = await self._calculate_indicators_for_aggregated_data(weekly_data, 'weekly')
            else:
                enhanced_weekly = []
                
            if monthly_data:
                enhanced_monthly = await self._calculate_indicators_for_aggregated_data(monthly_data, 'monthly')
            else:
                enhanced_monthly = []
            
            return enhanced_weekly, enhanced_monthly
            
        except Exception as e:
            logger.error(f"Error calculating weekly/monthly aggregations: {e}")
            return [], []

    async def _calculate_indicators_for_aggregated_data(self, aggregated_data: List[Dict], timeframe: str) -> List[Dict]:
        """Calculate indicators for weekly or monthly aggregated data"""
        try:
            if not aggregated_data:
                return []
            
            # Extract price arrays
            closes = np.array([float(c.get('close', 0)) for c in aggregated_data], dtype=np.float64)
            highs = np.array([float(c.get('high', 0)) for c in aggregated_data], dtype=np.float64)
            lows = np.array([float(c.get('low', 0)) for c in aggregated_data], dtype=np.float64)
            
            # Calculate indicators based on timeframe
            if timeframe == 'weekly':
                calculation_tasks = [
                    asyncio.get_event_loop().run_in_executor(
                        self.process_executor, calculate_rsi_optimized, closes, 14
                    ),
                    asyncio.get_event_loop().run_in_executor(
                        self.process_executor, calculate_rsi_optimized, closes, 21
                    ),
                    asyncio.get_event_loop().run_in_executor(
                        self.process_executor, calculate_sma_optimized, closes, 10
                    ),
                    asyncio.get_event_loop().run_in_executor(
                        self.process_executor, calculate_sma_optimized, closes, 20
                    ),
                    asyncio.get_event_loop().run_in_executor(
                        self.process_executor, calculate_ema_optimized, closes, 12
                    ),
                    asyncio.get_event_loop().run_in_executor(
                        self.process_executor, calculate_ema_optimized, closes, 26
                    ),
                    asyncio.get_event_loop().run_in_executor(
                        self.process_executor, calculate_supertrend_optimized, highs, lows, closes, 10, 2
                    ),
                    asyncio.get_event_loop().run_in_executor(
                        self.process_executor, calculate_supertrend_optimized, highs, lows, closes, 10, 3
                    ),
                    asyncio.get_event_loop().run_in_executor(
                        self.process_executor, calculate_bollinger_bands_optimized, closes, 20, 2
                    ),
                ]
                
                results = await asyncio.gather(*calculation_tasks)
                rsi_14, rsi_21, sma_10, sma_20, ema_12, ema_26, supertrend_10_2, supertrend_10_3, bollinger_bands = results
                
                # Enhance data with indicators
                for i, data_point in enumerate(aggregated_data):
                    data_point.update({
                        'rsi_14': float(rsi_14[i]) if i < len(rsi_14) and not np.isnan(rsi_14[i]) else None,
                        'rsi_21': float(rsi_21[i]) if i < len(rsi_21) and not np.isnan(rsi_21[i]) else None,
                        'sma_10': float(sma_10[i]) if i < len(sma_10) and not np.isnan(sma_10[i]) else None,
                        'sma_20': float(sma_20[i]) if i < len(sma_20) and not np.isnan(sma_20[i]) else None,
                        'ema_12': float(ema_12[i]) if i < len(ema_12) and not np.isnan(ema_12[i]) else None,
                        'ema_26': float(ema_26[i]) if i < len(ema_26) and not np.isnan(ema_26[i]) else None,
                        'supertrend_10_2': float(supertrend_10_2['values'][i]) if i < len(supertrend_10_2['values']) and not np.isnan(supertrend_10_2['values'][i]) else None,
                        'supertrend_signal_10_2': int(supertrend_10_2['signals'][i]) if i < len(supertrend_10_2['signals']) else 0,
                        'supertrend_10_3': float(supertrend_10_3['values'][i]) if i < len(supertrend_10_3['values']) and not np.isnan(supertrend_10_3['values'][i]) else None,
                        'supertrend_signal_10_3': int(supertrend_10_3['signals'][i]) if i < len(supertrend_10_3['signals']) else 0,
                        'bb_upper_20_2': float(bollinger_bands['upper'][i]) if i < len(bollinger_bands['upper']) and not np.isnan(bollinger_bands['upper'][i]) else None,
                        'bb_middle_20_2': float(bollinger_bands['middle'][i]) if i < len(bollinger_bands['middle']) and not np.isnan(bollinger_bands['middle'][i]) else None,
                        'bb_lower_20_2': float(bollinger_bands['lower'][i]) if i < len(bollinger_bands['lower']) and not np.isnan(bollinger_bands['lower'][i]) else None,
                    })
                    
            else:  # monthly
                calculation_tasks = [
                    asyncio.get_event_loop().run_in_executor(
                        self.process_executor, calculate_rsi_optimized, closes, 14
                    ),
                    asyncio.get_event_loop().run_in_executor(
                        self.process_executor, calculate_sma_optimized, closes, 10
                    ),
                    asyncio.get_event_loop().run_in_executor(
                        self.process_executor, calculate_sma_optimized, closes, 20
                    ),
                    asyncio.get_event_loop().run_in_executor(
                        self.process_executor, calculate_supertrend_optimized, highs, lows, closes, 10, 2
                    ),
                    asyncio.get_event_loop().run_in_executor(
                        self.process_executor, calculate_bollinger_bands_optimized, closes, 20, 2
                    ),
                ]
                
                results = await asyncio.gather(*calculation_tasks)
                rsi_14, sma_10, sma_20, supertrend_10_2, bollinger_bands = results
                
                # Enhance data with indicators
                for i, data_point in enumerate(aggregated_data):
                    data_point.update({
                        'rsi_14': float(rsi_14[i]) if i < len(rsi_14) and not np.isnan(rsi_14[i]) else None,
                        'sma_10': float(sma_10[i]) if i < len(sma_10) and not np.isnan(sma_10[i]) else None,
                        'sma_20': float(sma_20[i]) if i < len(sma_20) and not np.isnan(sma_20[i]) else None,
                        'supertrend_10_2': float(supertrend_10_2['values'][i]) if i < len(supertrend_10_2['values']) and not np.isnan(supertrend_10_2['values'][i]) else None,
                        'supertrend_signal_10_2': int(supertrend_10_2['signals'][i]) if i < len(supertrend_10_2['signals']) else 0,
                        'bb_upper_20_2': float(bollinger_bands['upper'][i]) if i < len(bollinger_bands['upper']) and not np.isnan(bollinger_bands['upper'][i]) else None,
                        'bb_middle_20_2': float(bollinger_bands['middle'][i]) if i < len(bollinger_bands['middle']) and not np.isnan(bollinger_bands['middle'][i]) else None,
                        'bb_lower_20_2': float(bollinger_bands['lower'][i]) if i < len(bollinger_bands['lower']) and not np.isnan(bollinger_bands['lower'][i]) else None,
                    })
            
            return aggregated_data
            
        except Exception as e:
            logger.error(f"Error calculating {timeframe} indicators: {e}")
            return aggregated_data

    async def close(self):
        """Close all executors"""
        self.process_executor.shutdown(wait=True)
        self.thread_executor.shutdown(wait=True)

# =================================
# OPTIMIZED CALCULATION FUNCTIONS
# =================================

def calculate_rsi_optimized(closes: np.ndarray, period: int) -> np.ndarray:
    """Optimized RSI calculation using numpy"""
    if len(closes) < period + 1:
        return np.full(len(closes), np.nan)
    
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    # Use pandas-style rolling calculation for efficiency
    avg_gains = np.full(len(closes), np.nan)
    avg_losses = np.full(len(closes), np.nan)
    
    # Initialize first average
    avg_gains[period] = np.mean(gains[:period])
    avg_losses[period] = np.mean(losses[:period])
    
    # Calculate smoothed averages
    for i in range(period + 1, len(closes)):
        avg_gains[i] = (avg_gains[i-1] * (period - 1) + gains[i-1]) / period
        avg_losses[i] = (avg_losses[i-1] * (period - 1) + losses[i-1]) / period
    
    # Calculate RSI
    rs = np.divide(avg_gains, avg_losses, out=np.zeros_like(avg_gains), where=avg_losses!=0)
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

def calculate_sma_optimized(closes: np.ndarray, period: int) -> np.ndarray:
    """Optimized SMA calculation using numpy"""
    if len(closes) < period:
        return np.full(len(closes), np.nan)
    
    # Use convolution for efficient moving average
    sma = np.full(len(closes), np.nan)
    kernel = np.ones(period) / period
    
    # Calculate SMA using convolution
    conv_result = np.convolve(closes, kernel, mode='valid')
    sma[period-1:] = conv_result
    
    return sma

def calculate_ema_optimized(closes: np.ndarray, period: int) -> np.ndarray:
    """Optimized EMA calculation using numpy"""
    if len(closes) < 2:
        return np.full(len(closes), np.nan)
    
    alpha = 2.0 / (period + 1)
    ema = np.full(len(closes), np.nan)
    ema[0] = closes[0]
    
    # Vectorized EMA calculation
    for i in range(1, len(closes)):
        ema[i] = alpha * closes[i] + (1 - alpha) * ema[i-1]
    
    return ema

def calculate_supertrend_optimized(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, 
                                 period: int, multiplier: float) -> Dict[str, np.ndarray]:
    """Optimized SuperTrend calculation"""
    if len(closes) < period:
        return {
            'values': np.full(len(closes), np.nan),
            'signals': np.zeros(len(closes), dtype=int)
        }
    
    # Calculate True Range
    high_low = highs - lows
    high_close = np.abs(highs - np.roll(closes, 1))
    low_close = np.abs(lows - np.roll(closes, 1))
    
    true_ranges = np.maximum(high_low, np.maximum(high_close, low_close))
    true_ranges[0] = high_low[0]  # First TR is just high-low
    
    # Calculate ATR using Wilder's smoothing
    atr = np.full(len(closes), np.nan)
    atr[period-1] = np.mean(true_ranges[:period])
    
    for i in range(period, len(closes)):
        atr[i] = (atr[i-1] * (period - 1) + true_ranges[i]) / period
    
    # Calculate basic bands
    hl2 = (highs + lows) / 2
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)
    
    # Initialize SuperTrend arrays
    supertrend = np.full(len(closes), np.nan)
    signals = np.zeros(len(closes), dtype=int)
    
    # Calculate SuperTrend
    for i in range(period, len(closes)):
        if i == period:
            # First calculation
            if closes[i] <= lower_band[i]:
                supertrend[i] = upper_band[i]
                signals[i] = -1
            else:
                supertrend[i] = lower_band[i]
                signals[i] = 1
        else:
            # Subsequent calculations
            prev_supertrend = supertrend[i-1]
            
            # Adjust bands based on previous values
            if upper_band[i] < prev_supertrend or closes[i-1] > prev_supertrend:
                upper_band[i] = upper_band[i]
            else:
                upper_band[i] = prev_supertrend
                
            if lower_band[i] > prev_supertrend or closes[i-1] < prev_supertrend:
                lower_band[i] = lower_band[i]
            else:
                lower_band[i] = prev_supertrend
            
            # Determine SuperTrend value and signal
            if closes[i] <= lower_band[i]:
                supertrend[i] = upper_band[i]
                signals[i] = -1
            else:
                supertrend[i] = lower_band[i]
                signals[i] = 1
    
    return {
        'values': supertrend,
        'signals': signals
    }

def calculate_bollinger_bands_optimized(closes: np.ndarray, period: int, std_dev: float) -> Dict[str, np.ndarray]:
    """Optimized Bollinger Bands calculation"""
    if len(closes) < period:
        return {
            'upper': np.full(len(closes), np.nan),
            'middle': np.full(len(closes), np.nan),
            'lower': np.full(len(closes), np.nan)
        }
    
    # Calculate SMA (middle band)
    middle = calculate_sma_optimized(closes, period)
    
    # Calculate rolling standard deviation
    std = np.full(len(closes), np.nan)
    for i in range(period-1, len(closes)):
        window = closes[i-period+1:i+1]
        std[i] = np.std(window)
    
    # Calculate upper and lower bands
    upper = middle + (std_dev * std)
    lower = middle - (std_dev * std)
    
    return {
        'upper': upper,
        'middle': middle,
        'lower': lower
    }

def calculate_performance_metrics(closes: np.ndarray) -> Dict[str, np.ndarray]:
    """Calculate performance metrics (percentage changes)"""
    def calculate_change(period: int) -> np.ndarray:
        changes = np.full(len(closes), np.nan)
        for i in range(period, len(closes)):
            if closes[i-period] != 0:
                changes[i] = ((closes[i] - closes[i-period]) / closes[i-period]) * 100
        return changes
    
    return {
        'change_1d': calculate_change(1),
        'change_7d': calculate_change(7),
        'change_30d': calculate_change(30)
    }

def calculate_weekly_aggregation(daily_candles: List[Dict]) -> List[Dict]:
    """Calculate weekly aggregation from daily candles"""
    from collections import defaultdict
    import calendar
    
    weekly_data = defaultdict(lambda: {
        'open': None, 'high': 0, 'low': float('inf'), 'close': None, 
        'volume': 0, 'count': 0, 'timestamps': []
    })
    
    for candle in daily_candles:
        timestamp = candle.get('timestamp', 0)
        if not timestamp:
            continue
            
        # Get Monday of the week
        dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        monday = dt - timedelta(days=dt.weekday())
        week_start = int(monday.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        
        week_data = weekly_data[week_start]
        
        # Aggregate OHLCV
        if week_data['open'] is None:
            week_data['open'] = float(candle.get('open', 0))
        week_data['high'] = max(week_data['high'], float(candle.get('high', 0)))
        week_data['low'] = min(week_data['low'], float(candle.get('low', 0)))
        week_data['close'] = float(candle.get('close', 0))  # Latest close
        week_data['volume'] += float(candle.get('volume', 0))
        week_data['count'] += 1
        week_data['timestamps'].append(timestamp)
    
    # Convert to list with proper structure
    result = []
    for week_start, data in sorted(weekly_data.items()):
        result.append({
            'week_start_timestamp': week_start,
            'week_start_date': datetime.fromtimestamp(week_start / 1000, tz=timezone.utc).date(),
            'open': data['open'],
            'high': data['high'],
            'low': data['low'] if data['low'] != float('inf') else 0,
            'close': data['close'],
            'volume': data['volume'],
            'trading_days': data['count']
        })
    
    return result

def calculate_monthly_aggregation(daily_candles: List[Dict]) -> List[Dict]:
    """Calculate monthly aggregation from daily candles"""
    from collections import defaultdict
    
    monthly_data = defaultdict(lambda: {
        'open': None, 'high': 0, 'low': float('inf'), 'close': None, 
        'volume': 0, 'count': 0, 'timestamps': []
    })
    
    for candle in daily_candles:
        timestamp = candle.get('timestamp', 0)
        if not timestamp:
            continue
            
        # Get first day of the month
        dt = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        month_start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_start_ts = int(month_start.timestamp() * 1000)
        
        month_data = monthly_data[month_start_ts]
        
        # Aggregate OHLCV
        if month_data['open'] is None:
            month_data['open'] = float(candle.get('open', 0))
        month_data['high'] = max(month_data['high'], float(candle.get('high', 0)))
        month_data['low'] = min(month_data['low'], float(candle.get('low', 0)))
        month_data['close'] = float(candle.get('close', 0))  # Latest close
        month_data['volume'] += float(candle.get('volume', 0))
        month_data['count'] += 1
        month_data['timestamps'].append(timestamp)
    
    # Convert to list with proper structure
    result = []
    for month_start, data in sorted(monthly_data.items()):
        result.append({
            'month_start_timestamp': month_start,
            'month_start_date': datetime.fromtimestamp(month_start / 1000, tz=timezone.utc).date(),
            'open': data['open'],
            'high': data['high'],
            'low': data['low'] if data['low'] != float('inf') else 0,
            'close': data['close'],
            'volume': data['volume'],
            'trading_days': data['count']
        })
    
    return result

# Global instance
high_speed_calculator = HighSpeedCalculationEngine()