"""
Static Indicator Calculator Service
Calculates indicators defined in schema_indicators.json for database columns
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any
import numpy as np
import pandas as pd
from decimal import Decimal

logger = logging.getLogger(__name__)

class StaticIndicatorCalculator:
    """Calculates static indicators for high-speed database columns"""
    
    def __init__(self):
        self.schema_config = self._load_schema_config()
    
    def _load_schema_config(self) -> Dict:
        """Load schema configuration"""
        config_path = Path(__file__).parent.parent / 'config' / 'schema_indicators.json'
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    return json.load(f)
            else:
                return {"static_indicators": {}}
        except Exception as e:
            logger.error(f"Error loading schema config: {e}")
            return {"static_indicators": {}}
    
    def calculate_static_indicators(self, candles: List[Dict], table_name: str = 'daily_candles') -> List[Dict]:
        """
        Calculate all static indicators for candles based on schema config
        
        Args:
            candles: List of candle dictionaries with OHLCV data
            table_name: Table name to get indicators for
            
        Returns:
            List of candles with calculated indicators added
        """
        if not candles:
            return candles
        
        # Convert to DataFrame for easier calculation
        df = pd.DataFrame(candles)
        
        # Ensure required columns exist and convert Decimal to float
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df.columns:
                logger.error(f"Missing required column: {col}")
                return candles
            # Convert Decimal to float for calculations
            df[col] = df[col].apply(lambda x: float(x) if x is not None else None)
        
        # Get indicators to calculate from schema
        if table_name not in self.schema_config.get('static_indicators', {}):
            logger.warning(f"No indicators configured for {table_name}")
            return candles
        
        indicators_config = self.schema_config['static_indicators'][table_name]
        
        # Calculate each indicator
        for indicator_config in indicators_config:
            col_name = indicator_config['column_name']
            indicator_def = indicator_config.get('indicator_config')
            
            if not indicator_def:
                continue  # Skip non-indicator columns like change_1w
            
            indicator_name = indicator_def['name']
            params = indicator_def.get('params', {})
            
            try:
                if indicator_name == 'RSI':
                    df[col_name] = self._calculate_rsi(df, params.get('period', 14))
                elif indicator_name == 'SMA':
                    df[col_name] = self._calculate_sma(df, params.get('period', 20))
                elif indicator_name == 'EMA':
                    df[col_name] = self._calculate_ema(df, params.get('period', 12))
                elif indicator_name == 'SuperTrend':
                    period = params.get('period', 10)
                    multiplier = params.get('multiplier', 2)
                    df[col_name] = self._calculate_supertrend(df, period, multiplier)
                elif indicator_name == 'SuperTrend_Signal':
                    period = params.get('period', 10)
                    multiplier = params.get('multiplier', 2)
                    df[col_name] = self._calculate_supertrend_signal(df, period, multiplier)
                else:
                    logger.warning(f"Unknown indicator type: {indicator_name}")
                    
            except Exception as e:
                logger.error(f"Error calculating {col_name}: {e}")
        
        # Convert back to list of dicts
        result = df.to_dict('records')
        
        # Convert NaN to None for database compatibility
        for row in result:
            for key, value in row.items():
                if pd.isna(value):
                    row[key] = None
        
        return result
    
    def _calculate_rsi(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate RSI"""
        close_delta = df['close'].diff()
        gains = close_delta.where(close_delta > 0, 0)
        losses = -close_delta.where(close_delta < 0, 0)
        
        avg_gains = gains.rolling(window=period, min_periods=period).mean()
        avg_losses = losses.rolling(window=period, min_periods=period).mean()
        
        rs = avg_gains / avg_losses
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def _calculate_sma(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Simple Moving Average"""
        return df['close'].rolling(window=period, min_periods=period).mean()
    
    def _calculate_ema(self, df: pd.DataFrame, period: int) -> pd.Series:
        """Calculate Exponential Moving Average"""
        return df['close'].ewm(span=period, adjust=False, min_periods=period).mean()
    
    def _calculate_supertrend(self, df: pd.DataFrame, period: int, multiplier: float) -> pd.Series:
        """Calculate SuperTrend indicator"""
        # Calculate ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(period).mean()
        
        # Calculate basic bands
        hl_avg = (df['high'] + df['low']) / 2
        upper_band = hl_avg + (multiplier * atr)
        lower_band = hl_avg - (multiplier * atr)
        
        # Initialize SuperTrend
        supertrend = pd.Series(index=df.index, dtype=float)
        in_uptrend = True
        
        for i in range(len(df)):
            if i < period:
                supertrend.iloc[i] = None
                continue
            
            if df['close'].iloc[i] <= lower_band.iloc[i]:
                in_uptrend = False
            elif df['close'].iloc[i] >= upper_band.iloc[i]:
                in_uptrend = True
            
            supertrend.iloc[i] = lower_band.iloc[i] if in_uptrend else upper_band.iloc[i]
        
        return supertrend
    
    def _calculate_supertrend_signal(self, df: pd.DataFrame, period: int, multiplier: float) -> pd.Series:
        """Calculate SuperTrend signal (1 for buy, -1 for sell)"""
        supertrend = self._calculate_supertrend(df, period, multiplier)
        
        # Signal is 1 when price is above SuperTrend, -1 when below
        signal = pd.Series(index=df.index, dtype=float)
        for i in range(len(df)):
            if pd.isna(supertrend.iloc[i]):
                signal.iloc[i] = None
            elif df['close'].iloc[i] > supertrend.iloc[i]:
                signal.iloc[i] = 1
            else:
                signal.iloc[i] = -1
        
        return signal

# Global instance
static_indicator_calculator = StaticIndicatorCalculator()