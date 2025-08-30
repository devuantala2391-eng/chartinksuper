"""
Simple SuperTrend Calculator for Dynamic Indicators
Calculates SuperTrend indicators directly and stores them in JSONB
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any
from services.high_speed_database_service import high_speed_db

logger = logging.getLogger(__name__)

class SimpleSuperTrendCalculator:
    """Simple service to calculate and store SuperTrend indicators"""
    
    async def calculate_and_store_supertrend(self, symbol: str, period: int, multiplier: float) -> bool:
        """
        Calculate SuperTrend for a symbol and store in JSONB with direction
        
        Args:
            symbol: Stock symbol
            period: ATR period
            multiplier: ATR multiplier (supports decimals like 2.5)
            
        Returns:
            True if successful
        """
        try:
            # Generate indicator key with improved decimal support
            multiplier_str = self._format_decimal_param(multiplier)
            indicator_key = f"supertrend_{period}_{multiplier_str}"
            direction_key = f"supertrend_{period}_{multiplier_str}_direction"
            
            logger.info(f"Calculating {indicator_key} and {direction_key} for {symbol}")
            
            # Get candles from database
            if not high_speed_db.initialized:
                await high_speed_db.initialize()
            
            candles = await high_speed_db.get_daily_candles_with_indicators(symbol, limit=500)
            
            if not candles or len(candles) < period:
                logger.warning(f"Insufficient data for {symbol}: {len(candles) if candles else 0} candles")
                return False
            
            # Convert to DataFrame for calculation
            df = pd.DataFrame(candles)
            
            # Ensure numeric types and convert Decimal to float
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df.columns:
                    # Convert Decimal to float explicitly
                    df[col] = df[col].apply(lambda x: float(x) if x is not None else None)
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Sort by timestamp
            df = df.sort_values('timestamp')
            
            # Calculate SuperTrend and Direction
            supertrend_values, direction_values = self._calculate_supertrend_with_direction(df, period, multiplier)
            
            # Prepare values for storage with 2 decimal precision
            indicator_values = []
            direction_values_list = []
            
            for i, row in df.iterrows():
                timestamp = int(row['timestamp'])
                
                if not pd.isna(supertrend_values[i]):
                    # Round to 2 decimal places for precision control
                    rounded_value = round(float(supertrend_values[i]), 2)
                    indicator_values.append({
                        'timestamp': timestamp,
                        'value': rounded_value
                    })
                
                if not pd.isna(direction_values[i]):
                    # Direction: 1 for up, 0 for down
                    direction_values_list.append({
                        'timestamp': timestamp,
                        'value': int(direction_values[i])
                    })
            
            # Store both supertrend and direction indicators
            success_count = 0
            
            if indicator_values:
                success = await high_speed_db.update_indicator_in_jsonb(symbol, indicator_key, indicator_values)
                if success:
                    success_count += 1
                    logger.info(f"Stored {len(indicator_values)} SuperTrend values for {indicator_key} in {symbol}")
                else:
                    logger.error(f"Failed to store {indicator_key} for {symbol}")
            
            if direction_values_list:
                success = await high_speed_db.update_indicator_in_jsonb(symbol, direction_key, direction_values_list)
                if success:
                    success_count += 1
                    logger.info(f"Stored {len(direction_values_list)} Direction values for {direction_key} in {symbol}")
                else:
                    logger.error(f"Failed to store {direction_key} for {symbol}")
            
            return success_count == 2  # Both indicators stored successfully
                
        except Exception as e:
            logger.error(f"Error calculating SuperTrend for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _format_decimal_param(self, value: float) -> str:
        """
        Format decimal parameter for indicator key generation
        Examples: 2.5 -> "2dot5", 3.0 -> "3", 10.25 -> "10dot25"
        """
        if value == int(value):
            # If it's a whole number, just return as integer string
            return str(int(value))
        else:
            # Replace decimal point with "dot"
            return str(value).replace('.', 'dot')
    
    def _calculate_supertrend_with_direction(self, df: pd.DataFrame, period: int, multiplier: float) -> tuple:
        """Calculate SuperTrend indicator with direction"""
        try:
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
            
            # Initialize SuperTrend and Direction
            supertrend = pd.Series(index=df.index, dtype=float)
            direction = pd.Series(index=df.index, dtype=float)
            in_uptrend = True
            
            for i in range(len(df)):
                if i < period:
                    supertrend.iloc[i] = np.nan
                    direction.iloc[i] = np.nan
                    continue
                
                # Determine trend direction
                if df['close'].iloc[i] <= lower_band.iloc[i]:
                    in_uptrend = False
                elif df['close'].iloc[i] >= upper_band.iloc[i]:
                    in_uptrend = True
                
                # Set SuperTrend value
                supertrend.iloc[i] = lower_band.iloc[i] if in_uptrend else upper_band.iloc[i]
                
                # Set direction (1 for up, 0 for down)
                direction.iloc[i] = 1 if in_uptrend else 0
            
            return supertrend, direction
            
        except Exception as e:
            logger.error(f"Error in SuperTrend calculation: {e}")
            return pd.Series(index=df.index, dtype=float), pd.Series(index=df.index, dtype=float)
    
    def _calculate_supertrend(self, df: pd.DataFrame, period: int, multiplier: float) -> pd.Series:
        """Calculate SuperTrend indicator"""
        try:
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
                    supertrend.iloc[i] = np.nan
                    continue
                
                if df['close'].iloc[i] <= lower_band.iloc[i]:
                    in_uptrend = False
                elif df['close'].iloc[i] >= upper_band.iloc[i]:
                    in_uptrend = True
                
                supertrend.iloc[i] = lower_band.iloc[i] if in_uptrend else upper_band.iloc[i]
            
            return supertrend
            
        except Exception as e:
            logger.error(f"Error in SuperTrend calculation: {e}")
            return pd.Series(index=df.index, dtype=float)
    
    async def calculate_for_all_stocks(self, period: int, multiplier: float, limit: int = None) -> Dict[str, Any]:
        """
        Calculate SuperTrend for all stocks
        
        Args:
            period: ATR period
            multiplier: ATR multiplier
            limit: Optional limit on number of stocks
            
        Returns:
            Dictionary with success count and errors
        """
        try:
            from utils.constants import STOCK_SYMBOLS
            
            stocks = STOCK_SYMBOLS[:limit] if limit else STOCK_SYMBOLS
            success_count = 0
            error_count = 0
            
            logger.info(f"Calculating SuperTrend({period},{multiplier}) for {len(stocks)} stocks")
            
            for symbol in stocks:
                success = await self.calculate_and_store_supertrend(symbol, period, multiplier)
                if success:
                    success_count += 1
                else:
                    error_count += 1
                
                # Log progress every 100 stocks
                if (success_count + error_count) % 100 == 0:
                    logger.info(f"Progress: {success_count + error_count}/{len(stocks)} stocks")
            
            logger.info(f"Completed: {success_count} successful, {error_count} failed")
            
            # Use proper decimal formatting for consistency
            multiplier_str = self._format_decimal_param(multiplier)
            
            return {
                "total": len(stocks),
                "success": success_count,
                "errors": error_count,
                "indicator": f"supertrend_{period}_{multiplier_str}",
                "direction_indicator": f"supertrend_{period}_{multiplier_str}_direction"
            }
            
        except Exception as e:
            logger.error(f"Error calculating for all stocks: {e}")
            return {
                "total": 0,
                "success": 0,
                "errors": 0,
                "error_message": str(e)
            }

# Global instance
simple_supertrend_calculator = SimpleSuperTrendCalculator()