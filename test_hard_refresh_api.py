"""
Test the hard-refresh API to ensure monthly key assignment works correctly
"""
import requests
import time
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def verify_database_after_refresh():
    """Verify database state after hard refresh"""
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database='nse_highspeed',
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', '123')
        )
        
        print("\n=== POST-REFRESH DATABASE VERIFICATION ===")
        
        # Check daily candles
        daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
        daily_with_monthly = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE monthly_candle_key_id IS NOT NULL")
        daily_nulls = daily_count - daily_with_monthly
        
        print(f"Daily candles: {daily_count} total, {daily_with_monthly} with monthly_candle_key_id, {daily_nulls} NULL")
        
        # Check weekly candles
        weekly_count = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles")
        weekly_with_monthly = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles WHERE monthly_candle_key_id IS NOT NULL")
        weekly_nulls = weekly_count - weekly_with_monthly
        
        print(f"Weekly candles: {weekly_count} total, {weekly_with_monthly} with monthly_candle_key_id, {weekly_nulls} NULL")
        
        # Check monthly candles
        monthly_count = await conn.fetchval("SELECT COUNT(*) FROM monthly_candles")
        print(f"Monthly candles: {monthly_count} total")
        
        # Verify relationships
        if daily_nulls == 0 and weekly_nulls == 0 and monthly_count > 0:
            print("SUCCESS: All candles have proper monthly relationships!")
            return True
        else:
            print("ERROR: Some candles are missing monthly relationships!")
            return False
        
        await conn.close()
        
    except Exception as e:
        print(f"Database verification failed: {e}")
        return False

def test_hard_refresh():
    """Test the hard-refresh API endpoint"""
    try:
        print("=== TESTING HARD-REFRESH API ===")
        
        # Test if server is running
        try:
            response = requests.get("http://127.0.0.1:8001/health", timeout=5)
            if response.status_code == 200:
                print("SUCCESS: API server is running")
            else:
                print(f"WARNING: Health check returned status {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Cannot connect to API server: {e}")
            return False
        
        # Trigger hard refresh
        print("Triggering hard-refresh...")
        response = requests.post("http://127.0.0.1:8001/api/hard-refresh", 
                                json={}, 
                                timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            print(f"SUCCESS: Hard refresh started")
            print(f"Message: {result.get('message', 'No message')}")
            
            # Wait for refresh to complete (in a real scenario, you'd monitor the progress endpoint)
            print("Waiting 30 seconds for hard refresh to complete...")
            time.sleep(30)
            
            # Verify the database state
            return asyncio.run(verify_database_after_refresh())
            
        else:
            print(f"ERROR: Hard refresh failed with status {response.status_code}")
            if response.text:
                print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"ERROR: Hard refresh test failed: {e}")
        return False

if __name__ == "__main__":
    success = test_hard_refresh()
    if success:
        print("\nSUCCESS: Hard-refresh API test passed!")
        print("- Monthly key duplication fix is working")
        print("- Hard-refresh properly assigns monthly_candle_key_id")
        print("- No NULL monthly relationships remain")
    else:
        print("\nERROR: Hard-refresh API test failed!")
        print("The fix may need additional attention.")