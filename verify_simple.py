import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def verify_simple():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    print("=== SYMBOL_LATEST_KEYS VERIFICATION ===")
    
    # Check the current state
    rows = await conn.fetch("SELECT * FROM symbol_latest_keys ORDER BY symbol")
    
    for row in rows:
        symbol = row['symbol']
        
        # Get actual data from database
        actual_weekly = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles WHERE symbol = $1", symbol)
        actual_monthly = await conn.fetchval("SELECT COUNT(*) FROM monthly_candles WHERE symbol = $1", symbol)
        
        max_weekly_seq = await conn.fetchval("SELECT MAX(week_sequence_number) FROM weekly_candles WHERE symbol = $1", symbol)
        max_monthly_seq = await conn.fetchval("SELECT MAX(month_sequence_number) FROM monthly_candles WHERE symbol = $1", symbol)
        
        print(f"Symbol: {symbol}")
        print(f"  Stored Weekly Key: {row.get('latest_weekly_key')} | Actual Max Weekly Seq: {max_weekly_seq}")
        print(f"  Stored Monthly Key: {row.get('latest_monthly_key')} | Actual Max Monthly Seq: {max_monthly_seq}")
        print(f"  Stored Weekly Count: {row.get('total_weekly_candles')} | Actual Weekly Count: {actual_weekly}")
        print(f"  Stored Monthly Count: {row.get('total_monthly_candles')} | Actual Monthly Count: {actual_monthly}")
        
        # Check if values are correct
        weekly_key_correct = row.get('latest_weekly_key') == max_weekly_seq
        monthly_key_correct = row.get('latest_monthly_key') == max_monthly_seq
        weekly_count_correct = row.get('total_weekly_candles') == actual_weekly
        monthly_count_correct = row.get('total_monthly_candles') == actual_monthly
        
        if weekly_key_correct and monthly_key_correct and weekly_count_correct and monthly_count_correct:
            print(f"  STATUS: CORRECT")
        else:
            print(f"  STATUS: NEEDS FIX")
            if not weekly_key_correct:
                print(f"    - Weekly key mismatch: {row.get('latest_weekly_key')} != {max_weekly_seq}")
            if not monthly_key_correct:
                print(f"    - Monthly key mismatch: {row.get('latest_monthly_key')} != {max_monthly_seq}")
        print()
    
    await conn.close()

asyncio.run(verify_simple())
