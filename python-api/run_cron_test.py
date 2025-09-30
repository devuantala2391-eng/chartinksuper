"""
Direct cron job test to measure execution time
"""
import asyncio
import time
import logging
from services.ultra_fast_cron_service import UltraFastCronService
from services.ultra_fast_database_service import ultra_fast_db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def run_cron_once():
    """Run cron job once and measure time"""
    cron_service = UltraFastCronService()

    print("\n" + "="*80)
    print("STARTING CRON JOB TEST")
    print("="*80)

    start_time = time.time()

    try:
        # Initialize the service
        print("Initializing cron service and database...")
        await cron_service.initialize()
        print("Cron service initialized successfully")

        # Run the cron job
        print("\nStarting cron job execution...")
        print("-" * 80)

        result = await cron_service.process_cron_with_database_saving()

        end_time = time.time()
        execution_time = end_time - start_time

        print("-" * 80)
        print(f"\nCRON JOB COMPLETED SUCCESSFULLY")
        print(f"EXECUTION TIME: {execution_time:.2f} seconds")
        print(f"Previous time: 117 seconds")

        if execution_time < 117:
            improvement = ((117 - execution_time) / 117) * 100
            print(f"IMPROVEMENT: {improvement:.1f}% faster!")
        else:
            print(f"No improvement - took {execution_time - 117:.2f} seconds longer")

    except Exception as e:
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"\nCRON JOB FAILED after {execution_time:.2f} seconds")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Clean up
        if ultra_fast_db and ultra_fast_db.pool:
            await ultra_fast_db.pool.close()

    print("="*80)

if __name__ == "__main__":
    asyncio.run(run_cron_once())