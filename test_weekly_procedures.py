"""
Test the weekly candle stored procedures directly
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def test_weekly_procedures():
    """Test weekly procedures directly"""
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database='nse_highspeed',
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', '123')
        )
        
        print("Testing weekly candle generation procedures...")
        
        # Check current state
        daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
        weekly_count_before = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles")
        print(f"Before: {daily_count} daily candles, {weekly_count_before} weekly candles")
        
        # Get a symbol to test with
        test_symbol = await conn.fetchval("SELECT symbol FROM daily_candles LIMIT 1")
        print(f"Testing with symbol: {test_symbol}")
        
        if test_symbol:
            # Test single symbol procedure
            print(f"Calling process_symbol_weekly_only('{test_symbol}')...")
            
            result = await conn.fetchrow("""
                SELECT * FROM process_symbol_weekly_only($1)
            """, test_symbol)
            
            print(f"Result: {dict(result)}")
            
            # Check if weekly candles were created
            weekly_count_after = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles")
            weekly_for_symbol = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles WHERE symbol = $1", test_symbol)
            
            print(f"After single symbol test: {weekly_count_after} weekly candles total, {weekly_for_symbol} for {test_symbol}")
            
            # Test the batch procedure
            print(f"\nTesting batch procedure...")
            
            batch_results = await conn.fetch("""
                SELECT * FROM process_all_symbols_weekly_only()
            """)
            
            print(f"Batch results: {len(batch_results)} symbols processed")
            for result in batch_results:
                print(f"  {result['symbol']}: {result['weekly_candles']} weekly candles, status: {result['status']}")
            
            # Final count
            final_weekly_count = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles")
            weekly_refs = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE weekly_candle_key_id IS NOT NULL")
            
            print(f"Final: {final_weekly_count} weekly candles, {weekly_refs} daily candles with weekly references")
            
        await conn.close()
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_weekly_procedures())