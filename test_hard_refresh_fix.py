"""
Test script to verify the hard refresh fix for weekly candles
This script will:
1. Connect to database
2. Test hard refresh API
3. Verify weekly candles are created correctly
4. Check that OHLCV data is populated
"""
import asyncio
import asyncpg
import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

async def test_database_connection():
    """Test database connection and basic queries"""
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database='nse_highspeed',
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', '123')
        )
        
        print("✅ Database connection successful")
        
        # Check if tables exist
        tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('daily_candles', 'weekly_candles', 'monthly_candles')
        """)
        
        print(f"📊 Found tables: {[t['table_name'] for t in tables]}")
        
        await conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

async def check_database_state(label=""):
    """Check current state of database"""
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', '5432')),
            database='nse_highspeed',
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', '123')
        )
        
        print(f"\n=== DATABASE STATE {label.upper()} ===")
        
        # Check daily candles
        daily_count = await conn.fetchval("SELECT COUNT(*) FROM daily_candles")
        print(f"Daily candles: {daily_count}")
        
        # Check weekly candles  
        weekly_count = await conn.fetchval("SELECT COUNT(*) FROM weekly_candles")
        print(f"Weekly candles: {weekly_count}")
        
        # Check monthly candles
        monthly_count = await conn.fetchval("SELECT COUNT(*) FROM monthly_candles")
        print(f"Monthly candles: {monthly_count}")
        
        # Check weekly OHLCV data in daily candles
        weekly_ohlcv_count = await conn.fetchval("""
            SELECT COUNT(*) FROM daily_candles 
            WHERE indicators ? 'weekly_open' 
            AND indicators ? 'weekly_high' 
            AND indicators ? 'weekly_low' 
            AND indicators ? 'weekly_close'
        """)
        print(f"Daily candles with weekly OHLCV: {weekly_ohlcv_count}")
        
        # Check if weekly candle references exist
        weekly_refs = await conn.fetchval("SELECT COUNT(*) FROM daily_candles WHERE weekly_candle_key_id IS NOT NULL")
        print(f"Daily candles with weekly references: {weekly_refs}")
        
        # Sample some data
        if daily_count > 0:
            sample = await conn.fetchrow("""
                SELECT symbol, timestamp, weekly_candle_key_id, 
                       indicators ? 'weekly_close' as has_weekly_close,
                       indicators->>'weekly_close' as weekly_close_value
                FROM daily_candles 
                ORDER BY timestamp DESC LIMIT 1
            """)
            print(f"Sample: {sample['symbol']} | Weekly ref: {sample['weekly_candle_key_id']} | Has weekly close: {sample['has_weekly_close']} | Value: {sample['weekly_close_value']}")
        
        await conn.close()
        
        return {
            'daily': daily_count,
            'weekly': weekly_count, 
            'monthly': monthly_count,
            'weekly_ohlcv': weekly_ohlcv_count,
            'weekly_refs': weekly_refs
        }
        
    except Exception as e:
        print(f"❌ Database state check failed: {e}")
        return None

def test_hard_refresh_api():
    """Test the hard refresh API"""
    try:
        print("\n=== TESTING HARD REFRESH API ===")
        
        # Check if API is running
        try:
            response = requests.get("http://127.0.0.1:8001/health", timeout=5)
            if response.status_code == 200:
                print("✅ API server is running")
            else:
                print(f"⚠️ API health check returned: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"❌ Cannot connect to API: {e}")
            return False
        
        # Trigger hard refresh
        print("🔄 Triggering hard refresh...")
        response = requests.post(
            "http://127.0.0.1:8001/api/hard-refresh", 
            json={}, 
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Hard refresh initiated: {result.get('message', 'No message')}")
            return True
        else:
            print(f"❌ Hard refresh failed: {response.status_code}")
            if response.text:
                print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Hard refresh test failed: {e}")
        return False

async def main():
    """Main test function"""
    print("🧪 TESTING HARD REFRESH WEEKLY CANDLES FIX")
    print("=" * 50)
    
    # Step 1: Test database connection
    if not await test_database_connection():
        print("❌ Cannot continue without database connection")
        return
    
    # Step 2: Check initial state
    initial_state = await check_database_state("BEFORE")
    
    # Step 3: Test hard refresh API
    if not test_hard_refresh_api():
        print("❌ Hard refresh API test failed")
        return
    
    # Step 4: Wait for hard refresh to complete
    print("\n⏳ Waiting for hard refresh to complete...")
    wait_time = 0
    max_wait = 180  # 3 minutes max
    
    while wait_time < max_wait:
        await asyncio.sleep(10)
        wait_time += 10
        print(f"⏰ Waited {wait_time}s...")
        
        # Check if we have data
        current_state = await check_database_state("PROGRESS")
        if current_state and current_state['weekly'] > 0:
            print("✅ Weekly candles detected! Hard refresh appears to be working.")
            break
    
    # Step 5: Final verification
    print(f"\n⏳ Waiting additional 30 seconds for full completion...")
    await asyncio.sleep(30)
    
    final_state = await check_database_state("FINAL")
    
    # Step 6: Analysis
    print("\n" + "=" * 50)
    print("🔍 ANALYSIS RESULTS")
    print("=" * 50)
    
    if final_state:
        success = True
        
        if final_state['daily'] == 0:
            print("❌ FAIL: No daily candles found")
            success = False
        else:
            print(f"✅ PASS: {final_state['daily']} daily candles found")
        
        if final_state['weekly'] == 0:
            print("❌ FAIL: No weekly candles found")
            success = False  
        else:
            print(f"✅ PASS: {final_state['weekly']} weekly candles found")
        
        if final_state['weekly_refs'] == 0:
            print("❌ FAIL: No weekly references in daily candles")
            success = False
        else:
            print(f"✅ PASS: {final_state['weekly_refs']} daily candles have weekly references")
        
        if final_state['weekly_ohlcv'] == 0:
            print("❌ FAIL: No weekly OHLCV data found in daily candles")
            success = False
        else:
            print(f"✅ PASS: {final_state['weekly_ohlcv']} daily candles have weekly OHLCV")
        
        if success:
            print("\n🎉 SUCCESS: Hard refresh fix is working!")
            print("✅ Weekly candles are being created")
            print("✅ Weekly OHLCV data is populated") 
            print("✅ Fix has resolved the issue!")
        else:
            print("\n❌ FAILURE: Hard refresh fix needs more work")
            print("Some components are still not working correctly")
    else:
        print("❌ Could not analyze results due to database errors")

if __name__ == "__main__":
    asyncio.run(main())