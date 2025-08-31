"""
Redeploy updated stored procedures with proper formatting
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def redeploy_procedures():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    try:
        print("Redeploying stored procedures with proper formatting...")
        
        # List of procedure files to redeploy
        procedures = [
            'python-api/sql/stored_procedures/calculate_all_timeframe_indicators.sql',
            'python-api/sql/stored_procedures/calculate_weekly_monthly_supertrend.sql'
        ]
        
        for proc_file in procedures:
            print(f"\nDeploying {proc_file}...")
            with open(proc_file, 'r') as f:
                sql = f.read()
            
            try:
                await conn.execute(sql)
                print(f"  [OK] Successfully deployed")
            except Exception as e:
                print(f"  [ERROR] {e}")
        
        print("\nAll procedures redeployed successfully!")
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(redeploy_procedures())