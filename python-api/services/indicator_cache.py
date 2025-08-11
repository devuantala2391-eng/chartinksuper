"""
In-memory cache system for optimizing indicator calculations.
Caches intermediate calculations when only the last candle changes during the trading day.
"""

import logging
from datetime import datetime, date
from typing import Dict, List, Any, Optional, Tuple
import json
import time

logger = logging.getLogger(__name__)

class IndicatorCache:
    """
    Manages cached intermediate calculations for technical indicators.
    Significantly improves performance when only the last candle is updating.
    """
    
    def __init__(self):
        # Cache structure: {symbol: {indicator_key: cache_data}}
        self.cache: Dict[str, Dict[str, Any]] = {}
        
        # Track last known timestamps for cache invalidation
        self.last_timestamps: Dict[str, str] = {}
        
        # Performance tracking
        self.performance_stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "time_saved": 0.0,
            "calculations_saved": 0
        }
        
        # Cache TTL - clear cache after market close
        self.cache_date = date.today()
        
    def _get_cache_key(self, symbol: str, indicator_type: str, params: Dict) -> str:
        """Generate a unique cache key for an indicator configuration."""
        param_str = json.dumps(params, sort_keys=True)
        return f"{indicator_type}_{param_str}"
    
    def _should_invalidate_cache(self, symbol: str, current_timestamp: str) -> bool:
        """Check if cache should be invalidated due to new trading day."""
        if symbol not in self.last_timestamps:
            return True
        
        # If timestamp changed (new day), invalidate cache
        last_ts = self.last_timestamps[symbol]
        if last_ts != current_timestamp:
            # Check if it's actually a new day or just intraday update
            try:
                last_date = datetime.fromisoformat(last_ts).date()
                current_date = datetime.fromisoformat(current_timestamp).date()
                return last_date != current_date
            except:
                return True
        
        return False
    
    def invalidate_symbol_cache(self, symbol: str):
        """Clear cache for a specific symbol."""
        if symbol in self.cache:
            del self.cache[symbol]
            logger.info(f"Cache invalidated for {symbol}")
    
    def invalidate_all_cache(self):
        """Clear entire cache."""
        self.cache.clear()
        self.last_timestamps.clear()
        logger.info("All cache cleared")
    
    def check_daily_reset(self):
        """Reset cache if it's a new trading day."""
        today = date.today()
        if today != self.cache_date:
            self.invalidate_all_cache()
            self.cache_date = today
            logger.info(f"Daily cache reset performed for {today}")
    
    # SMA Cache Management
    def get_sma_cache(self, symbol: str, period: int, timeframe: str = "daily") -> Optional[Dict]:
        """Get cached SMA calculation data."""
        cache_key = self._get_cache_key(symbol, f"sma_{timeframe}", {"period": period})
        return self.cache.get(symbol, {}).get(cache_key)
    
    def set_sma_cache(self, symbol: str, period: int, timeframe: str, 
                      sum_excluding_last: float, count_excluding_last: int, 
                      last_timestamp: str):
        """Cache SMA intermediate calculations."""
        cache_key = self._get_cache_key(symbol, f"sma_{timeframe}", {"period": period})
        
        if symbol not in self.cache:
            self.cache[symbol] = {}
        
        self.cache[symbol][cache_key] = {
            "sum_excluding_last": sum_excluding_last,
            "count_excluding_last": count_excluding_last,
            "last_timestamp": last_timestamp,
            "cached_at": datetime.now().isoformat()
        }
        
        self.last_timestamps[symbol] = last_timestamp
    
    def calculate_sma_with_cache(self, symbol: str, values: List[float], 
                                 period: int, current_timestamp: str,
                                 timeframe: str = "daily") -> Tuple[List[float], bool]:
        """
        Calculate SMA using cached values when possible.
        Returns (sma_values, used_cache).
        """
        start_time = time.time()
        period_int = int(round(period))
        sma_values = []
        used_cache = False
        
        # Check if we should invalidate cache
        if self._should_invalidate_cache(symbol, current_timestamp):
            self.invalidate_symbol_cache(symbol)
        
        # Try to get cached data
        cached = self.get_sma_cache(symbol, period, timeframe)
        
        # If we have cache and enough values
        if cached and len(values) >= period_int:
            # Check if this is for the same day (last candle update)
            if cached["last_timestamp"] == current_timestamp and len(values) > period_int:
                # Use cached sum for all except last candle
                used_cache = True
                self.performance_stats["cache_hits"] += 1
                
                # Calculate SMA for positions before the last 'period' values
                for i in range(len(values)):
                    if i < period_int - 1:
                        sma_values.append(None)
                    elif i == len(values) - 1:
                        # Last value - use cached sum
                        total = cached["sum_excluding_last"] + values[i]
                        sma_values.append(total / period_int)
                    else:
                        # Regular calculation for other positions
                        total = sum(values[i - period_int + 1:i + 1])
                        sma_values.append(total / period_int)
                
                elapsed = time.time() - start_time
                self.performance_stats["time_saved"] += elapsed * 0.8  # Estimate 80% time saved
                self.performance_stats["calculations_saved"] += period_int - 1
                
                logger.debug(f"SMA cache hit for {symbol}: saved {period_int-1} calculations")
                return sma_values, used_cache
        
        # Cache miss - calculate normally
        self.performance_stats["cache_misses"] += 1
        
        for i in range(len(values)):
            if i < period_int - 1:
                sma_values.append(None)
            else:
                sma_values.append(sum(values[i - period_int + 1:i + 1]) / period_int)
        
        # Cache the sum excluding the last value for next time
        if len(values) >= period_int:
            sum_excluding_last = sum(values[-period_int:-1])
            self.set_sma_cache(symbol, period, timeframe, sum_excluding_last, 
                             period_int - 1, current_timestamp)
        
        return sma_values, used_cache
    
    # EMA Cache Management
    def get_ema_cache(self, symbol: str, period: float, timeframe: str = "daily") -> Optional[Dict]:
        """Get cached EMA calculation data."""
        cache_key = self._get_cache_key(symbol, f"ema_{timeframe}", {"period": period})
        return self.cache.get(symbol, {}).get(cache_key)
    
    def set_ema_cache(self, symbol: str, period: float, timeframe: str,
                      previous_ema: float, last_timestamp: str):
        """Cache EMA intermediate calculations."""
        cache_key = self._get_cache_key(symbol, f"ema_{timeframe}", {"period": period})
        
        if symbol not in self.cache:
            self.cache[symbol] = {}
        
        self.cache[symbol][cache_key] = {
            "previous_ema": previous_ema,
            "last_timestamp": last_timestamp,
            "cached_at": datetime.now().isoformat()
        }
        
        self.last_timestamps[symbol] = last_timestamp
    
    def calculate_ema_with_cache(self, symbol: str, values: List[float],
                                 period: float, current_timestamp: str,
                                 timeframe: str = "daily") -> Tuple[List[float], bool]:
        """
        Calculate EMA using cached values when possible.
        Returns (ema_values, used_cache).
        """
        start_time = time.time()
        multiplier = 2 / (period + 1)
        ema_values = []
        used_cache = False
        
        # Check if we should invalidate cache
        if self._should_invalidate_cache(symbol, current_timestamp):
            self.invalidate_symbol_cache(symbol)
        
        # Try to get cached data
        cached = self.get_ema_cache(symbol, period, timeframe)
        
        if cached and cached["last_timestamp"] == current_timestamp and len(values) > 1:
            # Use cached EMA for last calculation
            used_cache = True
            self.performance_stats["cache_hits"] += 1
            
            # Calculate all EMAs except the last one normally
            for i in range(len(values) - 1):
                if i == 0:
                    ema_values.append(values[0])
                else:
                    ema = (values[i] * multiplier) + (ema_values[i-1] * (1 - multiplier))
                    ema_values.append(ema)
            
            # Use cached value for the last EMA
            if len(values) > 1:
                last_ema = (values[-1] * multiplier) + (cached["previous_ema"] * (1 - multiplier))
                ema_values.append(last_ema)
            
            elapsed = time.time() - start_time
            self.performance_stats["time_saved"] += elapsed * 0.5
            logger.debug(f"EMA cache hit for {symbol}")
            
            return ema_values, used_cache
        
        # Cache miss - calculate normally
        self.performance_stats["cache_misses"] += 1
        
        for i in range(len(values)):
            if i == 0:
                ema_values.append(values[0])
            else:
                ema = (values[i] * multiplier) + (ema_values[i-1] * (1 - multiplier))
                ema_values.append(ema)
        
        # Cache the second-to-last EMA for next time
        if len(ema_values) >= 2:
            self.set_ema_cache(symbol, period, timeframe, ema_values[-2], current_timestamp)
        
        return ema_values, used_cache
    
    # RSI Cache Management  
    def get_rsi_cache(self, symbol: str, period: int, timeframe: str = "daily") -> Optional[Dict]:
        """Get cached RSI calculation data."""
        cache_key = self._get_cache_key(symbol, f"rsi_{timeframe}", {"period": period})
        return self.cache.get(symbol, {}).get(cache_key)
    
    def set_rsi_cache(self, symbol: str, period: int, timeframe: str,
                      gains_sum: float, losses_sum: float, last_close: float,
                      last_timestamp: str):
        """Cache RSI intermediate calculations."""
        cache_key = self._get_cache_key(symbol, f"rsi_{timeframe}", {"period": period})
        
        if symbol not in self.cache:
            self.cache[symbol] = {}
        
        self.cache[symbol][cache_key] = {
            "gains_sum": gains_sum,
            "losses_sum": losses_sum,
            "last_close": last_close,
            "last_timestamp": last_timestamp,
            "cached_at": datetime.now().isoformat()
        }
        
        self.last_timestamps[symbol] = last_timestamp
    
    def calculate_rsi_with_cache(self, symbol: str, closes: List[float],
                                 period: int, current_timestamp: str,
                                 timeframe: str = "daily") -> Tuple[List[float], bool]:
        """
        Calculate RSI using cached values when possible.
        Returns (rsi_values, used_cache).
        """
        start_time = time.time()
        period_int = int(round(period))
        used_cache = False
        
        # Check if we should invalidate cache
        if self._should_invalidate_cache(symbol, current_timestamp):
            self.invalidate_symbol_cache(symbol)
        
        # Try to get cached data
        cached = self.get_rsi_cache(symbol, period, timeframe)
        
        if cached and cached["last_timestamp"] == current_timestamp and len(closes) > period_int:
            # Use cached values for optimization
            used_cache = True
            self.performance_stats["cache_hits"] += 1
            
            # Calculate gains and losses
            gains = []
            losses = []
            
            for i in range(1, len(closes)):
                change = closes[i] - closes[i-1]
                gains.append(max(0, change))
                losses.append(max(0, -change))
            
            # Calculate average gains and losses
            avg_gains = []
            avg_losses = []
            
            for i in range(len(gains)):
                if i < period_int - 1:
                    avg_gains.append(None)
                    avg_losses.append(None)
                elif i == len(gains) - 1:
                    # Use cached sums for last calculation
                    # Remove old value, add new value
                    old_change = cached["last_close"] - closes[-period_int-1] if len(closes) > period_int else 0
                    new_change = closes[-1] - closes[-2]
                    
                    old_gain = max(0, old_change)
                    old_loss = max(0, -old_change)
                    new_gain = max(0, new_change)
                    new_loss = max(0, -new_change)
                    
                    avg_gain = (cached["gains_sum"] - old_gain + new_gain) / period_int
                    avg_loss = (cached["losses_sum"] - old_loss + new_loss) / period_int
                    
                    avg_gains.append(avg_gain)
                    avg_losses.append(avg_loss)
                else:
                    avg_gains.append(sum(gains[i - period_int + 1:i + 1]) / period_int)
                    avg_losses.append(sum(losses[i - period_int + 1:i + 1]) / period_int)
            
            # Calculate RSI
            rsi_values = []
            for i in range(len(closes)):
                if i < period_int:
                    rsi_values.append(None)
                else:
                    if avg_losses[i-1] == 0:
                        rsi_values.append(100)
                    else:
                        rs = avg_gains[i-1] / avg_losses[i-1]
                        rsi_values.append(100 - (100 / (1 + rs)))
            
            elapsed = time.time() - start_time
            self.performance_stats["time_saved"] += elapsed * 0.7
            self.performance_stats["calculations_saved"] += period_int * 2
            logger.debug(f"RSI cache hit for {symbol}")
            
            return rsi_values, used_cache
        
        # Cache miss - calculate normally
        self.performance_stats["cache_misses"] += 1
        
        # Standard RSI calculation
        gains = []
        losses = []
        
        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            gains.append(max(0, change))
            losses.append(max(0, -change))
        
        # Calculate simple moving average for initial values
        avg_gains = []
        avg_losses = []
        
        for i in range(len(gains)):
            if i < period_int - 1:
                avg_gains.append(None)
                avg_losses.append(None)
            else:
                avg_gains.append(sum(gains[i - period_int + 1:i + 1]) / period_int)
                avg_losses.append(sum(losses[i - period_int + 1:i + 1]) / period_int)
        
        rsi_values = []
        for i in range(len(closes)):
            if i < period_int:
                rsi_values.append(None)
            else:
                if avg_losses[i-1] == 0:
                    rsi_values.append(100)
                else:
                    rs = avg_gains[i-1] / avg_losses[i-1]
                    rsi_values.append(100 - (100 / (1 + rs)))
        
        # Cache the sums for next time
        if len(gains) >= period_int:
            gains_sum = sum(gains[-period_int:])
            losses_sum = sum(losses[-period_int:])
            self.set_rsi_cache(symbol, period, timeframe, gains_sum, losses_sum,
                             closes[-1], current_timestamp)
        
        return rsi_values, used_cache
    
    # SuperTrend Cache Management
    def get_supertrend_cache(self, symbol: str, period: int, multiplier: float,
                            timeframe: str = "daily") -> Optional[Dict]:
        """Get cached SuperTrend calculation data."""
        cache_key = self._get_cache_key(symbol, f"supertrend_{timeframe}", 
                                       {"period": period, "multiplier": multiplier})
        return self.cache.get(symbol, {}).get(cache_key)
    
    def set_supertrend_cache(self, symbol: str, period: int, multiplier: float,
                           timeframe: str, atr_sum: float, prev_atr: float,
                           prev_final_upper: float, prev_final_lower: float,
                           prev_trend: int, last_timestamp: str):
        """Cache SuperTrend intermediate calculations."""
        cache_key = self._get_cache_key(symbol, f"supertrend_{timeframe}",
                                       {"period": period, "multiplier": multiplier})
        
        if symbol not in self.cache:
            self.cache[symbol] = {}
        
        self.cache[symbol][cache_key] = {
            "atr_sum": atr_sum,
            "prev_atr": prev_atr,
            "prev_final_upper": prev_final_upper,
            "prev_final_lower": prev_final_lower,
            "prev_trend": prev_trend,
            "last_timestamp": last_timestamp,
            "cached_at": datetime.now().isoformat()
        }
        
        self.last_timestamps[symbol] = last_timestamp
    
    # Bollinger Bands Cache Management
    def get_bb_cache(self, symbol: str, period: int, std_dev: float,
                    timeframe: str = "daily") -> Optional[Dict]:
        """Get cached Bollinger Bands calculation data."""
        cache_key = self._get_cache_key(symbol, f"bb_{timeframe}",
                                       {"period": period, "std_dev": std_dev})
        return self.cache.get(symbol, {}).get(cache_key)
    
    def set_bb_cache(self, symbol: str, period: int, std_dev: float,
                    timeframe: str, values_excluding_last: List[float],
                    last_timestamp: str):
        """Cache Bollinger Bands intermediate calculations."""
        cache_key = self._get_cache_key(symbol, f"bb_{timeframe}",
                                       {"period": period, "std_dev": std_dev})
        
        if symbol not in self.cache:
            self.cache[symbol] = {}
        
        self.cache[symbol][cache_key] = {
            "values_excluding_last": values_excluding_last,
            "last_timestamp": last_timestamp,
            "cached_at": datetime.now().isoformat()
        }
        
        self.last_timestamps[symbol] = last_timestamp
    
    def calculate_bb_with_cache(self, symbol: str, closes: List[float],
                               period: int, std_dev: float, current_timestamp: str,
                               timeframe: str = "daily") -> Tuple[List[float], List[float], List[float], bool]:
        """
        Calculate Bollinger Bands using cached values when possible.
        Returns (upper_band, middle_band, lower_band, used_cache).
        """
        start_time = time.time()
        period_int = int(round(period))
        used_cache = False
        
        # Check if we should invalidate cache
        if self._should_invalidate_cache(symbol, current_timestamp):
            self.invalidate_symbol_cache(symbol)
        
        # Try to get cached data
        cached = self.get_bb_cache(symbol, period, std_dev, timeframe)
        
        # Calculate SMA (middle band) with cache
        sma_values, sma_cached = self.calculate_sma_with_cache(
            symbol, closes, period, current_timestamp, f"{timeframe}_bb"
        )
        
        upper_band = []
        lower_band = []
        
        if cached and cached["last_timestamp"] == current_timestamp and len(closes) >= period_int:
            # Use cached values for optimization
            used_cache = True
            self.performance_stats["cache_hits"] += 1
            
            for i in range(len(closes)):
                if i < period_int - 1:
                    upper_band.append(None)
                    lower_band.append(None)
                elif i == len(closes) - 1:
                    # Last value - use cached values and add current
                    values_for_std = cached["values_excluding_last"] + [closes[i]]
                    std = self._calculate_std(values_for_std, sma_values[i])
                    upper_band.append(sma_values[i] + (std_dev * std))
                    lower_band.append(sma_values[i] - (std_dev * std))
                else:
                    # Regular calculation
                    values_for_std = closes[i - period_int + 1:i + 1]
                    std = self._calculate_std(values_for_std, sma_values[i])
                    upper_band.append(sma_values[i] + (std_dev * std))
                    lower_band.append(sma_values[i] - (std_dev * std))
            
            elapsed = time.time() - start_time
            self.performance_stats["time_saved"] += elapsed * 0.6
            logger.debug(f"BB cache hit for {symbol}")
        else:
            # Cache miss - calculate normally
            self.performance_stats["cache_misses"] += 1
            
            for i in range(len(closes)):
                if i < period_int - 1:
                    upper_band.append(None)
                    lower_band.append(None)
                else:
                    values_for_std = closes[i - period_int + 1:i + 1]
                    std = self._calculate_std(values_for_std, sma_values[i])
                    upper_band.append(sma_values[i] + (std_dev * std))
                    lower_band.append(sma_values[i] - (std_dev * std))
            
            # Cache values excluding last for next time
            if len(closes) >= period_int:
                values_excluding_last = closes[-period_int:-1]
                self.set_bb_cache(symbol, period, std_dev, timeframe,
                                values_excluding_last, current_timestamp)
        
        return upper_band, sma_values, lower_band, used_cache
    
    def _calculate_std(self, values: List[float], mean: float) -> float:
        """Calculate standard deviation."""
        if not values:
            return 0
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5
    
    def get_performance_report(self) -> Dict:
        """Get performance statistics report."""
        total_requests = self.performance_stats["cache_hits"] + self.performance_stats["cache_misses"]
        hit_rate = (self.performance_stats["cache_hits"] / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "cache_hits": self.performance_stats["cache_hits"],
            "cache_misses": self.performance_stats["cache_misses"],
            "hit_rate": f"{hit_rate:.2f}%",
            "time_saved_seconds": round(self.performance_stats["time_saved"], 3),
            "calculations_saved": self.performance_stats["calculations_saved"],
            "total_requests": total_requests,
            "cache_size": len(self.cache),
            "symbols_cached": list(self.cache.keys())
        }
    
    def reset_performance_stats(self):
        """Reset performance statistics."""
        self.performance_stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "time_saved": 0.0,
            "calculations_saved": 0
        }

# Global instance
indicator_cache = IndicatorCache()