import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_symbol_keys_schema():
    """Fix symbol_latest_keys schema and update with correct values"""
    
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    print("=== CHECKING SCHEMA ===")
    
    # Check current schema
    columns = await conn.fetch("""
        SELECT column_name, data_type 
        FROM information_schema.columns 
        WHERE table_name = 'symbol_latest_keys' 
        ORDER BY ordinal_position
    """)
    
    print("Current columns:")
    current_columns = []
    for col in columns:
        current_columns.append(col['column_name'])
        print(f"  {col['column_name']}: {col['data_type']}")
    
    # Add missing columns
    if 'latest_monthly_key' not in current_columns:
        print("\nAdding latest_monthly_key column...")
        await conn.execute("ALTER TABLE symbol_latest_keys ADD COLUMN latest_monthly_key INTEGER DEFAULT -1")
        print("SUCCESS: Added latest_monthly_key column")
    
    print("\n=== UPDATING VALUES ===")
    
    # Get all distinct symbols from daily_candles
    symbols = await conn.fetch("SELECT DISTINCT symbol FROM daily_candles ORDER BY symbol")
    
    for symbol_row in symbols:
        symbol = symbol_row['symbol']
        print(f"Processing {symbol}...")
        
        # Get actual counts and max sequence numbers for each timeframe
        daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE symbol = $1", symbol)
        daily_max_seq = await conn.fetchval("SELECT COALESCE(MAX(candle_sequence_number), -1) FROM daily_candles WHERE symbol = $1", symbol)
        
        weekly_count = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles WHERE symbol = $1", symbol)
        weekly_max_seq = await conn.fetchval("SELECT COALESCE(MAX(week_sequence_number), -1) FROM weekly_candles WHERE symbol = $1", symbol)
        
        monthly_count = await conn.fetchval("SELECT COUNT(*) FROM monthly_candles WHERE symbol = $1", symbol)
        monthly_max_seq = await conn.fetchval("SELECT COALESCE(MAX(month_sequence_number), -1) FROM monthly_candles WHERE symbol = $1", symbol)
        
        print(f"  Daily: {daily_count} candles, max seq: {daily_max_seq}")
        print(f"  Weekly: {weekly_count} candles, max seq: {weekly_max_seq}")
        print(f"  Monthly: {monthly_count} candles, max seq: {monthly_max_seq}")
        
        # Update symbol_latest_keys with correct values  
        await conn.execute("""
            UPDATE symbol_latest_keys SET
                latest_daily_key = $2,
                latest_weekly_key = $3,
                latest_monthly_key = $4,
                total_daily_candles = $5,
                total_weekly_candles = $6,
                total_monthly_candles = $7,
                last_updated = CURRENT_TIMESTAMP
            WHERE symbol = $1
        """, symbol, daily_max_seq, weekly_max_seq, monthly_max_seq, 
             daily_count, weekly_count, monthly_count)
        
        print(f"  SUCCESS: Updated {symbol}")
    
    print("\n=== VERIFICATION ===")
    
    # Check updated data
    rows = await conn.fetch("SELECT * FROM symbol_latest_keys ORDER BY symbol")
    for row in rows:
        print(f"Symbol: {row['symbol']}")
        print(f"  Daily Key: {row.get('latest_daily_key')} (Count: {row.get('total_daily_candles')})")
        print(f"  Weekly Key: {row.get('latest_weekly_key')} (Count: {row.get('total_weekly_candles')})")  
        print(f"  Monthly Key: {row.get('latest_monthly_key')} (Count: {row.get('total_monthly_candles')})")
        print()
    
    await conn.close()
    print("SUCCESS: Symbol latest keys fixed and updated!")

asyncio.run(fix_symbol_keys_schema())
