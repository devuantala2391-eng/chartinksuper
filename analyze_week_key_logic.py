#!/usr/bin/env python3
"""
Analyze current week_key logic in daily_candles to understand the implementation
"""

import asyncio
import sys
import os

# Add the python-api directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'python-api'))

from services.ultra_fast_database_service import ultra_fast_db

async def analyze_week_key_logic():
    """Analyze current week_key implementation"""
    try:
        print("=== ANALYZING WEEK_KEY LOGIC ===")
        
        await ultra_fast_db.initialize()
        
        async with ultra_fast_db.pool.acquire() as conn:
            # Check daily_candles structure
            print("=== DAILY CANDLES STRUCTURE ===")
            daily_structure = await conn.fetch("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'daily_candles' 
                ORDER BY ordinal_position
            """)
            
            for col in daily_structure:
                nullable = 'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL'
                print(f"{col['column_name']}: {col['data_type']} ({nullable})")
            
            # Check daily candles data with week_key
            print("\n=== DAILY CANDLES WITH WEEK_KEY SAMPLE ===")
            daily_samples = await conn.fetch("""
                SELECT symbol, candle_sequence_number, timestamp, datetime, week_key, day_of_week, weekly_candle_key_id
                FROM daily_candles 
                ORDER BY timestamp 
                LIMIT 10
            """)
            
            for sample in daily_samples:
                print(f"Daily: seq={sample['candle_sequence_number']}, timestamp={sample['timestamp']}, "
                      f"datetime={sample['datetime']}, week_key={sample['week_key']}, "
                      f"day_of_week={sample['day_of_week']}, weekly_id={sample['weekly_candle_key_id']}")
            
            # Check weekly_candles structure
            print("\n=== WEEKLY CANDLES STRUCTURE ===")
            weekly_structure = await conn.fetch("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'weekly_candles' 
                ORDER BY ordinal_position
            """)
            
            for col in weekly_structure:
                nullable = 'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL'
                print(f"{col['column_name']}: {col['data_type']} ({nullable})")
            
            # Check weekly candles data
            print("\n=== WEEKLY CANDLES SAMPLE ===")
            weekly_samples = await conn.fetch("""
                SELECT weekly_candle_key_id, symbol, week_sequence_number, week_start_timestamp, week_start_datetime
                FROM weekly_candles 
                ORDER BY week_start_timestamp 
                LIMIT 5
            """)
            
            for sample in weekly_samples:
                print(f"Weekly: id={sample['weekly_candle_key_id']}, seq={sample['week_sequence_number']}, "
                      f"start_ts={sample['week_start_timestamp']}, datetime={sample['week_start_datetime']}")
            
            # Check monthly_candles structure
            print("\n=== MONTHLY CANDLES STRUCTURE ===")
            monthly_structure = await conn.fetch("""
                SELECT column_name, data_type, is_nullable 
                FROM information_schema.columns 
                WHERE table_name = 'monthly_candles' 
                ORDER BY ordinal_position
            """)
            
            for col in monthly_structure:
                nullable = 'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL'
                print(f"{col['column_name']}: {col['data_type']} ({nullable})")
            
            # Check monthly candles data
            print("\n=== MONTHLY CANDLES SAMPLE ===")
            monthly_samples = await conn.fetch("""
                SELECT monthly_candle_key_id, symbol, month_sequence_number, month_start_timestamp, month_start_datetime
                FROM monthly_candles 
                ORDER BY month_start_timestamp 
                LIMIT 5
            """)
            
            for sample in monthly_samples:
                print(f"Monthly: id={sample['monthly_candle_key_id']}, seq={sample['month_sequence_number']}, "
                      f"start_ts={sample['month_start_timestamp']}, datetime={sample['month_start_datetime']}")
            
            # Analyze week_key logic
            print("\n=== WEEK_KEY ANALYSIS ===")
            week_key_analysis = await conn.fetch("""
                SELECT week_key, COUNT(*) as daily_count, 
                       MIN(datetime) as first_day, MAX(datetime) as last_day
                FROM daily_candles 
                WHERE week_key IS NOT NULL
                GROUP BY week_key 
                ORDER BY week_key
                LIMIT 5
            """)
            
            for analysis in week_key_analysis:
                print(f"week_key={analysis['week_key']}: {analysis['daily_count']} days, "
                      f"from {analysis['first_day']} to {analysis['last_day']}")
            
            # Check relationship between week_key and weekly_candles
            print("\n=== WEEK_KEY TO WEEKLY_CANDLES RELATIONSHIP ===")
            relationship = await conn.fetch("""
                SELECT dc.week_key, dc.weekly_candle_key_id, wc.week_sequence_number, COUNT(*) as daily_count
                FROM daily_candles dc
                LEFT JOIN weekly_candles wc ON dc.weekly_candle_key_id = wc.weekly_candle_key_id
                WHERE dc.week_key IS NOT NULL
                GROUP BY dc.week_key, dc.weekly_candle_key_id, wc.week_sequence_number
                ORDER BY dc.week_key
                LIMIT 5
            """)
            
            for rel in relationship:
                print(f"week_key={rel['week_key']} -> weekly_id={rel['weekly_candle_key_id']}, "
                      f"weekly_seq={rel['week_sequence_number']}, {rel['daily_count']} daily candles")
        
    except Exception as e:
        print(f"Analysis failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if ultra_fast_db.pool and not ultra_fast_db.pool._closed:
            await ultra_fast_db.pool.close()

if __name__ == "__main__":
    asyncio.run(analyze_week_key_logic())