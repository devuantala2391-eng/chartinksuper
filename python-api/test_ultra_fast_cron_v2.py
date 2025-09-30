"""
Test Ultra-Fast Cron V2 - Target < 3 seconds
"""
import asyncio
import time
import logging
from services.ultra_fast_cron_v2 import ultra_fast_cron_v2
from services.ultra_fast_database_service import ultra_fast_db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_ultra_fast_cron_v2():
    """Test the new ultra-fast cron v2 system"""
    print("\n" + "=" * 80)
    print("ULTRA-FAST CRON V2 TEST - TARGET: < 3 SECONDS")
    print("=" * 80)

    start_time = time.time()

    try:
        # Initialize the service
        print("Initializing ultra-fast cron v2...")
        await ultra_fast_cron_v2.initialize()
        print("PASS Ultra-fast cron v2 initialized successfully")

        # Run the ultra-fast cron
        print("\nStarting ultra-fast cron execution...")
        print("-" * 80)

        result = await ultra_fast_cron_v2.run_ultra_fast_cron()

        end_time = time.time()
        execution_time = end_time - start_time

        print("-" * 80)
        print(f"\nSUCCESS ULTRA-FAST CRON V2 COMPLETED")
        print(f"TIME EXECUTION TIME: {execution_time:.2f} seconds")
        print(f"TARGET: < 3 seconds")

        if execution_time < 3.0:
            improvement = ((3.0 - execution_time) / 3.0) * 100
            print(f"PASS TARGET ACHIEVED! {improvement:.1f}% under target!")
        else:
            overage = execution_time - 3.0
            print(f"FAIL TARGET MISSED by {overage:.2f} seconds")

        print(f"\nPERFORMANCE BREAKDOWN:")
        print(f"   Total Symbols: {result['total_symbols']}")
        print(f"   Successful: {result['successful']}")
        print(f"   Failed: {result['failed']}")
        print(f"   Success Rate: {result['success_rate_percent']:.1f}%")
        print(f"   Speed: {result['symbols_per_second']:.1f} symbols/sec")

        print(f"\nTIMING BREAKDOWN:")
        print(f"   HTTP Requests: {result['timing_breakdown']['http_requests']:.2f}s")
        print(f"   Calculations: {result['timing_breakdown']['calculations']:.2f}s")
        print(f"   Database Save: {result['timing_breakdown']['database_save']:.2f}s")

        print(f"\nOPTIMIZATIONS ENABLED:")
        for opt, enabled in result['performance_improvements'].items():
            status = "PASS" if enabled else "FAIL"
            print(f"   {status} {opt.replace('_', ' ').title()}")

    except Exception as e:
        end_time = time.time()
        execution_time = end_time - start_time
        print(f"\nFAIL ULTRA-FAST CRON V2 FAILED after {execution_time:.2f} seconds")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Clean up
        await ultra_fast_cron_v2.cleanup()
        if ultra_fast_db and ultra_fast_db.pool:
            await ultra_fast_db.pool.close()

    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(test_ultra_fast_cron_v2())