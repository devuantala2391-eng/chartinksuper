"""
Test the migration service
"""
import asyncio
import sys
import os
sys.path.insert(0, 'python-api')

from services.database_migration_service import database_migration_service

async def test_migration_service():
    """Test the migration service"""
    print("Testing database migration service...")
    
    # Test the migration check and apply
    result = await database_migration_service.check_and_apply_migrations()
    
    print("Migration result:")
    for key, value in result.items():
        print(f"  {key}: {value}")
    
    if result['success']:
        print("✅ Migration service working correctly!")
        
        # Test weekly candle generation verification
        print("\nTesting weekly candle generation verification...")
        verify_result = await database_migration_service.verify_weekly_candle_generation()
        
        print("Verification result:")
        for key, value in verify_result.items():
            print(f"  {key}: {value}")
        
        if verify_result['success']:
            print("✅ Weekly candle generation verification passed!")
        else:
            print("❌ Weekly candle generation verification failed!")
    else:
        print("❌ Migration service failed!")

if __name__ == "__main__":
    asyncio.run(test_migration_service())