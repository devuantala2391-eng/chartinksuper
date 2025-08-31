"""
Deploy format utility functions to database
"""
import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def deploy_functions():
    conn = await asyncpg.connect(
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database='nse_highspeed',
        user=os.getenv('POSTGRES_USER', 'postgres'),
        password=os.getenv('POSTGRES_PASSWORD', '123')
    )
    
    try:
        # Read SQL file
        with open('python-api/sql/stored_procedures/format_indicator_key.sql', 'r') as f:
            sql = f.read()
        
        # Execute the SQL
        await conn.execute(sql)
        
        print("Format functions deployed successfully!")
        
        # Test the functions
        result = await conn.fetchrow("""
            SELECT 
                format_multiplier_for_key(3.0) as test1,
                format_multiplier_for_key(3.5) as test2,
                format_multiplier_for_key(1.6) as test3,
                format_multiplier_for_key(1.600000000000000088817841970012523233890533447265625) as test4,
                format_multiplier_for_key(2.25) as test5,
                format_period_for_key(10.0) as test6,
                format_period_for_key(14) as test7
        """)
        
        print("\nTest results:")
        print(f"3.0 -> {result['test1']} (expected: '3')")
        print(f"3.5 -> {result['test2']} (expected: '3dot5')")
        print(f"1.6 -> {result['test3']} (expected: '1dot6')")
        print(f"1.6000...625 -> {result['test4']} (expected: '1dot6')")
        print(f"2.25 -> {result['test5']} (expected: '2dot25')")
        print(f"10.0 -> {result['test6']} (expected: '10')")
        print(f"14 -> {result['test7']} (expected: '14')")
        
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(deploy_functions())