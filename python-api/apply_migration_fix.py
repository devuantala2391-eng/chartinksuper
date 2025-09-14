import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.database_migration_service import database_migration_service

async def main():
    print("APPLYING DATABASE MIGRATIONS WITH SUPERTREND FIX")
    print("=" * 80)

    result = await database_migration_service.check_and_apply_migrations()

    print("\nMigration Result:")
    print("-" * 80)
    for key, value in result.items():
        print(f"{key}: {value}")

    if result.get('success'):
        print("\nSUCCESS: Migrations applied successfully!")
        if result.get('procedures_created'):
            print(f"Created procedures: {', '.join(result['procedures_created'])}")
    else:
        print(f"\nERROR: Migration failed - {result.get('message')}")

    return result

if __name__ == "__main__":
    asyncio.run(main())