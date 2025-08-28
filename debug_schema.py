"""
Debug script to examine the daily candles table schema and monthly key columns
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def debug_schema():
    """Debug the daily candles schema and monthly key assignments"""
    try:
        # Connect to database
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database='nse_highspeed',
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', '123')
        )
        
        print("=== DAILY CANDLES TABLE SCHEMA ===")
        
        # Check all columns in daily_candles table
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = 'daily_candles'
            ORDER BY ordinal_position
        """)
        
        print(f"Daily candles table has {len(columns)} columns:")
        for col in columns:
            print(f"  {col['column_name']:25} {col['data_type']:15} {'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL':8} {col['column_default'] or ''}")
        
        print("\n=== MONTHLY KEY COLUMNS ANALYSIS ===")
        
        # Focus on monthly key columns
        monthly_columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns 
            WHERE table_name = 'daily_candles' 
            AND column_name IN ('monthly_key', 'monthly_candle_key_id')
            ORDER BY column_name
        """)
        
        if monthly_columns:
            print(f"Found {len(monthly_columns)} monthly key columns:")
            for col in monthly_columns:
                print(f"  {col['column_name']:25} {col['data_type']:15} {'NULL' if col['is_nullable'] == 'YES' else 'NOT NULL':8}")
        else:
            print("No monthly key columns found!")
            
        print("\n=== SAMPLE DATA ANALYSIS ===")
        
        # Check sample data for these columns
        sample_data = await conn.fetch("""
            SELECT symbol, candle_key_id, monthly_candle_key_id, datetime
            FROM daily_candles 
            ORDER BY datetime DESC 
            LIMIT 10
        """)
        
        print("Sample data from daily_candles (latest 10 rows):")
        for row in sample_data:
            print(f"  {row['symbol']:12} {row['candle_key_id']:15} monthly_candle_key_id={row['monthly_candle_key_id']} {row['datetime'].date()}")
            
        print("\n=== NULL VALUES COUNT ===")
        
        # Count NULL values
        null_counts = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total_rows,
                COUNT(*) - COUNT(monthly_candle_key_id) as monthly_candle_key_id_nulls
            FROM daily_candles
        """)
        
        print(f"Total daily candles: {null_counts['total_rows']}")
        print(f"monthly_candle_key_id NULL values: {null_counts['monthly_candle_key_id_nulls']}")
        
        print("\n=== MONTHLY CANDLES TABLE STATUS ===")
        
        # Check monthly candles table
        monthly_candles_count = await conn.fetchval("SELECT COUNT(*) FROM monthly_candles")
        print(f"Monthly candles table has {monthly_candles_count} records")
        
        if monthly_candles_count > 0:
            monthly_sample = await conn.fetch("""
                SELECT symbol, monthly_candle_key_id, month_sequence_number, month_start_datetime, month_end_datetime
                FROM monthly_candles 
                ORDER BY month_start_datetime DESC 
                LIMIT 5
            """)
            
            print("Sample monthly candles:")
            for row in monthly_sample:
                print(f"  {row['symbol']:12} {row['monthly_candle_key_id']:20} seq={row['month_sequence_number']} {row['month_start_datetime'].date()} to {row['month_end_datetime'].date()}")
        
        print("\n=== RELATIONSHIP CHECK ===")
        
        # Check if there are daily candles that should have monthly assignments
        relationship_check = await conn.fetchrow("""
            SELECT 
                COUNT(dc.candle_key_id) as daily_candles_total,
                COUNT(mc.monthly_candle_key_id) as daily_with_monthly_match,
                COUNT(dc.candle_key_id) - COUNT(mc.monthly_candle_key_id) as daily_without_monthly_match
            FROM daily_candles dc
            LEFT JOIN monthly_candles mc ON (
                dc.symbol = mc.symbol AND
                dc.datetime::date >= mc.month_start_datetime::date AND
                dc.datetime::date <= mc.month_end_datetime::date
            )
        """)
        
        print(f"Daily candles total: {relationship_check['daily_candles_total']}")
        print(f"Daily candles with monthly match: {relationship_check['daily_with_monthly_match']}")  
        print(f"Daily candles without monthly match: {relationship_check['daily_without_monthly_match']}")
        
        await conn.close()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_schema())