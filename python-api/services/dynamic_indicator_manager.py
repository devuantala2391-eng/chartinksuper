"""
Database-based Dynamic Indicator Manager
Replaces JSON file-based approach with database queries
"""

import asyncio
import asyncpg
import json
from datetime import datetime
from typing import Dict, List, Optional
import os
from dotenv import load_dotenv
from services.utils import format_multiplier_for_key, format_period_for_key

load_dotenv()

class DatabaseDynamicIndicatorManager:
    """Database-based indicator manager"""
    
    def __init__(self):
        self.pool = None
        self._active_indicators = []
        self._indicator_definitions = {}
        
    async def initialize(self):
        """Initialize database connection"""
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                host=os.getenv('POSTGRES_HOST', 'localhost'),
                port=int(os.getenv('POSTGRES_PORT', '5432')),
                database='nse_highspeed',
                user=os.getenv('POSTGRES_USER', 'postgres'),
                password=os.getenv('POSTGRES_PASSWORD', '123'),
                min_size=1,
                max_size=5
            )
        await self.load_indicator_config()
        
    async def close(self):
        """Close database connection"""
        if self.pool:
            await self.pool.close()
            self.pool = None
            
    async def load_indicator_config(self):
        """Load indicator configuration from database"""
        if not self.pool:
            await self.initialize()
            
        async with self.pool.acquire() as conn:
            # Load active indicators list
            active_result = await conn.fetchrow("""
                SELECT config_data FROM indicator_registry 
                WHERE config_key = 'active_indicators_list'
            """)
            
            if active_result and active_result['config_data']:
                data = json.loads(active_result['config_data'])
                self._active_indicators = data.get('active_indicators', [])
            else:
                self._active_indicators = []
                
            # Load all indicator definitions
            definitions = await conn.fetch("""
                SELECT config_key, config_data FROM indicator_registry 
                WHERE config_key != 'active_indicators_list'
            """)
            
            self._indicator_definitions = {}
            for row in definitions:
                if row['config_data']:
                    config = json.loads(row['config_data'])
                    self._indicator_definitions[row['config_key']] = config
    
    @property
    def active_indicators(self) -> List[str]:
        """Get active indicators list"""
        return self._active_indicators
        
    @property 
    def indicator_definitions(self) -> Dict:
        """Get indicator definitions"""
        return self._indicator_definitions
        
    async def get_active_indicators_list(self) -> List[str]:
        """Get active indicators from database"""
        await self.load_indicator_config()
        return self._active_indicators
        
    def generate_indicator_key(self, indicator_def: Dict) -> str:
        """Generate indicator key from definition"""
        name = indicator_def.get('name', '').lower()
        timeframe = indicator_def.get('timeframe', 'daily')
        params = indicator_def.get('params', {})
        
        if name == 'supertrend':
            period = params.get('period', 10)
            multiplier = params.get('multiplier', 2.0)
            # Use utility function to format multiplier properly
            period_str = format_period_for_key(period)
            multiplier_str = format_multiplier_for_key(multiplier)
            # ALWAYS include timeframe prefix for SuperTrend
            return f"{timeframe}_supertrend_{period_str}_{multiplier_str}"
        elif name == 'percentagechange' or name == 'pctchg':
            if timeframe == 'daily':
                lookback = params.get('lookback')
                return f"daily_pctchg_{lookback}" if lookback else "daily_pctchg"
            else:
                return f"{timeframe}_pctchg"
        elif name.lower() in ['rsi', 'sma', 'ema']:
            period = params.get('period', 14)
            period_str = format_period_for_key(period)
            # Include timeframe prefix for all indicators
            return f"{timeframe}_{name.lower()}_{period_str}"
        else:
            # Always include timeframe prefix
            return f"{timeframe}_{name.lower()}"
            
    async def add_custom_indicator(self, name: str, params: Dict, timeframe: str = 'daily') -> bool:
        """Add custom indicator to database"""
        if not self.pool:
            await self.initialize()
            
        config = {
            'name': name,
            'timeframe': timeframe,
            'params': params
        }
        
        key = self.generate_indicator_key(config)
        
        async with self.pool.acquire() as conn:
            try:
                # Add to indicator registry
                await conn.execute("""
                    INSERT INTO indicator_registry (config_key, config_data, created_at, updated_at)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (config_key) DO UPDATE SET
                        config_data = EXCLUDED.config_data,
                        updated_at = EXCLUDED.updated_at
                """,
                key,
                json.dumps(config),
                datetime.now(),
                datetime.now()
                )
                
                # Add to active indicators if not already there
                if key not in self._active_indicators:
                    self._active_indicators.append(key)
                    
                    # Update active indicators list in database
                    await conn.execute("""
                        INSERT INTO indicator_registry (config_key, config_data, created_at, updated_at)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (config_key) DO UPDATE SET
                            config_data = EXCLUDED.config_data,
                            updated_at = EXCLUDED.updated_at
                    """,
                    'active_indicators_list',
                    json.dumps({"active_indicators": self._active_indicators}),
                    datetime.now(),
                    datetime.now()
                    )
                    
                return True
            except Exception as e:
                print(f"Error adding custom indicator {key}: {e}")
                return False
                
    async def auto_calculate_missing_indicator(self, error_detail: str) -> bool:
        """Auto-calculate missing indicator based on error"""
        # Parse error detail to extract indicator info
        try:
            error_lower = error_detail.lower()
            
            # Detect timeframe from the error message
            timeframe = 'daily'  # default
            if 'weekly_' in error_lower:
                timeframe = 'weekly'
            elif 'monthly_' in error_lower:
                timeframe = 'monthly'
            elif 'daily_' in error_lower:
                timeframe = 'daily'
            
            if 'supertrend' in error_lower:
                # Extract supertrend parameters from error like "weekly_supertrend_10_3"
                import re
                pattern = r'(?:daily_|weekly_|monthly_)?supertrend_(\d+)_(\d+(?:dot\d+)?)'  
                match = re.search(pattern, error_lower)
                if match:
                    period = int(match.group(1))
                    multiplier_str = match.group(2)
                    # Convert 'dot' back to decimal point
                    multiplier = float(multiplier_str.replace('dot', '.'))
                    
                    print(f"Auto-calculating {timeframe} SuperTrend({period}, {multiplier}) from error: {error_detail}")
                    return await self.calculate_and_store_indicator(
                        indicator_def={'name': 'SuperTrend', 'params': {'period': period, 'multiplier': multiplier}, 'timeframe': timeframe}
                    )
            elif 'pctchg' in error_lower or 'percentage' in error_lower:
                # Auto-calculate percentage change for the detected timeframe
                print(f"Auto-calculating {timeframe} percentage change from error: {error_detail}")
                return await self.calculate_and_store_indicator(
                    indicator_def={'name': 'percentagechange', 'params': {}, 'timeframe': timeframe}
                )
            elif 'sma_' in error_lower:
                # Extract SMA period from error like "sma_20" or "weekly_sma_50"
                import re
                pattern = r'(?:daily_|weekly_|monthly_)?sma_(\d+)'
                match = re.search(pattern, error_lower)
                if match:
                    period = int(match.group(1))
                    print(f"Auto-calculating {timeframe} SMA({period}) from error: {error_detail}")
                    return await self.calculate_and_store_indicator(
                        indicator_def={'name': 'sma', 'params': {'period': period}, 'timeframe': timeframe}
                    )
            elif 'ema_' in error_lower:
                # Extract EMA period from error like "ema_20" or "weekly_ema_50"
                import re
                pattern = r'(?:daily_|weekly_|monthly_)?ema_(\d+)'
                match = re.search(pattern, error_lower)
                if match:
                    period = int(match.group(1))
                    print(f"Auto-calculating {timeframe} EMA({period}) from error: {error_detail}")
                    return await self.calculate_and_store_indicator(
                        indicator_def={'name': 'ema', 'params': {'period': period}, 'timeframe': timeframe}
                    )
            
            return False
        except Exception as e:
            print(f"Error parsing indicator from error detail '{error_detail}': {e}")
            return False
            
    async def calculate_and_store_indicator(self, indicator_def: Dict = None, store_in_highspeed: bool = True, name: str = None, params: Dict = None, timeframe: str = None) -> bool:
        """Calculate and store indicator - compatible with both old and new call styles"""
        # Handle both call styles for compatibility
        if indicator_def:
            # New style call with indicator_def dict
            name = indicator_def.get('name', name)
            params = indicator_def.get('params', params or {})
            timeframe = indicator_def.get('timeframe', timeframe or 'daily')
        
        # store_in_highspeed is ignored - we always use the database
        
        if not self.pool:
            await self.initialize()
            
        async with self.pool.acquire() as conn:
            try:
                if name and name.lower() == 'supertrend':
                    # Ensure parameters are integers/floats
                    period = params.get('period', 10)
                    multiplier = params.get('multiplier', 2.0)
                    
                    # Convert to proper types if needed
                    if isinstance(period, float) and period.is_integer():
                        period = int(period)
                    else:
                        period = int(period)
                    
                    # Use the NEW timeframe-aware stored procedures
                    if timeframe == 'daily':
                        # Call daily SuperTrend procedure
                        result = await conn.fetchrow("""
                            SELECT * FROM calculate_timeframe_supertrend('daily', $1, $2, NULL)
                        """, period, multiplier)
                    elif timeframe == 'weekly':
                        # Call weekly SuperTrend procedure
                        result = await conn.fetchrow("""
                            SELECT * FROM calculate_weekly_monthly_supertrend('weekly', $1, $2, NULL)
                        """, period, multiplier)
                    elif timeframe == 'monthly':
                        # Call monthly SuperTrend procedure
                        result = await conn.fetchrow("""
                            SELECT * FROM calculate_weekly_monthly_supertrend('monthly', $1, $2, NULL)
                        """, period, multiplier)
                    else:
                        # Default to daily if unknown timeframe
                        result = await conn.fetchrow("""
                            SELECT * FROM calculate_timeframe_supertrend('daily', $1, $2, NULL)
                        """, period, multiplier)
                    
                    if result:
                        print(f"{timeframe.capitalize()} SuperTrend calculation result: {dict(result)}")
                        # Check if status is SUCCESS
                        # Note: updated_rows may be 0 if indicator already exists, which is still a success
                        success = result.get('status') == 'SUCCESS'
                        
                        if success:
                            # Add to active indicators if not already there
                            indicator_key = self.generate_indicator_key({
                                'name': 'SuperTrend',
                                'timeframe': timeframe,
                                'params': {'period': period, 'multiplier': multiplier}
                            })
                            
                            if indicator_key not in self._active_indicators:
                                self._active_indicators.append(indicator_key)
                                # Also add the indicator configuration
                                await self.add_custom_indicator('SuperTrend', 
                                                               {'period': period, 'multiplier': multiplier}, 
                                                               timeframe)
                        
                        return success
                    
                elif name and (name.lower() == 'percentagechange' or name.lower() == 'pctchg'):
                    # Calculate percentage change using correct stored procedure based on timeframe
                    if timeframe == 'monthly':
                        # Use monthly-specific function - it already returns aggregated data
                        result = await conn.fetchrow("""
                            SELECT * FROM calculate_monthly_percentage_change(NULL, 1000)
                        """)
                    elif timeframe == 'weekly':
                        # Use weekly-specific function - use the main function that processes all symbols
                        result = await conn.fetchrow("""
                            SELECT * FROM calculate_weekly_percentage_change(NULL, 1000)
                        """)
                    else:
                        # Use general function for daily
                        result = await conn.fetchrow("""
                            SELECT * FROM calculate_percentage_change($1, NULL, 1000)
                        """, timeframe)
                    
                    if result:
                        print(f"{timeframe.capitalize()} Percentage Change calculation result: {dict(result)}")
                        # Check if status is SUCCESS
                        # Note: updated_rows may be 0 if indicator already exists, which is still a success
                        success = result.get('status') == 'SUCCESS'
                        
                        if success:
                            # Add to active indicators if not already there
                            indicator_key = self.generate_indicator_key({
                                'name': 'percentagechange',
                                'timeframe': timeframe,
                                'params': params
                            })
                            
                            if indicator_key not in self._active_indicators:
                                self._active_indicators.append(indicator_key)
                                await self.add_custom_indicator('percentagechange', params, timeframe)
                        
                        return success
                
                elif name and name.lower() == 'sma':
                    # Calculate SMA using new stored procedure
                    period = params.get('period')
                    if not period:
                        print(f"Error: SMA period not provided in params: {params}")
                        return False
                    
                    # Convert to proper type if needed
                    if isinstance(period, float) and period.is_integer():
                        period = int(period)
                    else:
                        period = int(period)
                    
                    # Call the dynamic SMA/EMA calculation function
                    indicator_name = f"{timeframe}_{name.lower()}_{period}" if timeframe != 'daily' else f"{name.lower()}_{period}"
                    result = await conn.fetchrow("""
                        SELECT * FROM calculate_dynamic_sma_ema($1)
                    """, indicator_name)
                    
                    if result:
                        print(f"{timeframe.capitalize()} SMA({period}) calculation result: {dict(result)}")
                        success = result.get('success', False)
                        
                        if success:
                            # Add to active indicators if not already there
                            indicator_key = self.generate_indicator_key({
                                'name': 'sma',
                                'timeframe': timeframe,
                                'params': {'period': period}
                            })
                            
                            if indicator_key not in self._active_indicators:
                                self._active_indicators.append(indicator_key)
                                await self.add_custom_indicator('sma', {'period': period}, timeframe)
                        
                        return success
                
                elif name and name.lower() == 'ema':
                    # Calculate EMA using new stored procedure
                    period = params.get('period')
                    if not period:
                        print(f"Error: EMA period not provided in params: {params}")
                        return False
                    
                    # Convert to proper type if needed
                    if isinstance(period, float) and period.is_integer():
                        period = int(period)
                    else:
                        period = int(period)
                    
                    # Call the dynamic SMA/EMA calculation function
                    indicator_name = f"{timeframe}_{name.lower()}_{period}" if timeframe != 'daily' else f"{name.lower()}_{period}"
                    result = await conn.fetchrow("""
                        SELECT * FROM calculate_dynamic_sma_ema($1)
                    """, indicator_name)
                    
                    if result:
                        print(f"{timeframe.capitalize()} EMA({period}) calculation result: {dict(result)}")
                        success = result.get('success', False)
                        
                        if success:
                            # Add to active indicators if not already there
                            indicator_key = self.generate_indicator_key({
                                'name': 'ema',
                                'timeframe': timeframe,
                                'params': {'period': period}
                            })
                            
                            if indicator_key not in self._active_indicators:
                                self._active_indicators.append(indicator_key)
                                await self.add_custom_indicator('ema', {'period': period}, timeframe)
                        
                        return success
                    
                # Add other indicator calculations here
                return False
                
            except Exception as e:
                print(f"Error calculating {name} for {timeframe}: {e}")
                return False
                
    async def handle_query_validation_error(self, error_detail: str) -> tuple[bool, str]:
        """Handle query validation error by auto-calculating missing indicators"""
        success = await self.auto_calculate_missing_indicator(error_detail)
        
        if success:
            return True, f"Successfully calculated missing indicator from: {error_detail}"
        else:
            return False, f"Failed to calculate missing indicator from: {error_detail}"

# Create global instance
dynamic_indicator_manager = DatabaseDynamicIndicatorManager()
