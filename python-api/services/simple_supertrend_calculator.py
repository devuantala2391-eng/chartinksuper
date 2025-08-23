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
        Calculate SuperTrend for a symbol and store in JSONB
        
        Args:
            symbol: Stock symbol
            period: ATR period
            multiplier: ATR multiplier
            
        Returns:
            True if successful
        """
        try:
            # Generate indicator key
            indicator_key = f"supertrend_{period}_{str(multiplier).replace('.', 'dot')}"
            logger.info(f"Calculating {indicator_key} for {symbol}")
            
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
            
            # Calculate SuperTrend
            supertrend_values = self._calculate_supertrend(df, period, multiplier)
            
            # Prepare values for storage
            indicator_values = []
            for i, row in df.iterrows():
                if not pd.isna(supertrend_values[i]):
                    indicator_values.append({
                        'timestamp': int(row['timestamp']),
                        'value': float(supertrend_values[i])
                    })
            
            if indicator_values:
                # Store in JSONB
                success = await high_speed_db.update_indicator_in_jsonb(symbol, indicator_key, indicator_values)
                
                if success:
                    logger.info(f"Stored {len(indicator_values)} values for {indicator_key} in {symbol}")
                    return True
                else:
                    logger.error(f"Failed to store {indicator_key} for {symbol}")
                    return False
            else:
                logger.warning(f"No valid SuperTrend values calculated for {symbol}")
                return False
                
        except Exception as e:
            logger.error(f"Error calculating SuperTrend for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
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
            
            return {
                "total": len(stocks),
                "success": success_count,
                "errors": error_count,
                "indicator": f"supertrend_{period}_{multiplier}"
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