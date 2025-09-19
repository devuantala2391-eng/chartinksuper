"""
Test Bollinger Bands integration with dynamic indicator manager
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.dynamic_indicator_manager import DatabaseDynamicIndicatorManager
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BollingerBandsIntegrationTester:
    def __init__(self):
        self.manager = DatabaseDynamicIndicatorManager()

    async def test_bollinger_bands_integration(self):
        """Test Bollinger Bands integration with dynamic indicator manager"""
        try:
            logger.info("Testing Bollinger Bands integration with dynamic indicator manager")

            # Test 1: Daily Bollinger Bands
            logger.info("1. Testing daily Bollinger Bands via dynamic manager...")
            daily_success = await self.manager.calculate_and_store_indicator({
                'name': 'BollingerBands',
                'params': {'period': 20, 'multiplier': 2.0},
                'timeframe': 'daily'
            })
            logger.info(f"Daily Bollinger Bands result: {daily_success}")

            # Test 2: Weekly Bollinger Bands
            logger.info("2. Testing weekly Bollinger Bands via dynamic manager...")
            weekly_success = await self.manager.calculate_and_store_indicator({
                'name': 'BollingerBands',
                'params': {'period': 20, 'multiplier': 2.0},
                'timeframe': 'weekly'
            })
            logger.info(f"Weekly Bollinger Bands result: {weekly_success}")

            # Test 3: Monthly Bollinger Bands
            logger.info("3. Testing monthly Bollinger Bands via dynamic manager...")
            monthly_success = await self.manager.calculate_and_store_indicator({
                'name': 'BollingerBands',
                'params': {'period': 20, 'multiplier': 2.0},
                'timeframe': 'monthly'
            })
            logger.info(f"Monthly Bollinger Bands result: {monthly_success}")

            # Test 4: Bollinger Bands with different parameters
            logger.info("4. Testing Bollinger Bands with different parameters...")
            custom_success = await self.manager.calculate_and_store_indicator({
                'name': 'BollingerBands',
                'params': {'period': 14, 'multiplier': 1.5},
                'timeframe': 'daily'
            })
            logger.info(f"Custom Bollinger Bands result: {custom_success}")

            # Test 5: Test with 'bb' alias
            logger.info("5. Testing Bollinger Bands with 'BB' alias...")
            alias_success = await self.manager.calculate_and_store_indicator({
                'name': 'BB',
                'params': {'period': 20, 'multiplier': 2.0},
                'timeframe': 'daily'
            })
            logger.info(f"BB alias result: {alias_success}")

            # Test 6: Check active indicators
            logger.info("6. Checking active indicators...")
            active_indicators = await self.manager.get_active_indicators_list()
            bb_indicators = [ind for ind in active_indicators if 'bollinger' in ind.lower() or 'bb' in ind.lower()]
            logger.info(f"Active Bollinger Bands indicators: {bb_indicators}")

            return all([daily_success, weekly_success, monthly_success, custom_success, alias_success])

        except Exception as e:
            logger.error(f"Integration test failed: {e}")
            return False

async def main():
    tester = BollingerBandsIntegrationTester()
    success = await tester.test_bollinger_bands_integration()

    if success:
        print("\n" + "="*80)
        print("BOLLINGER BANDS INTEGRATION TEST PASSED")
        print("Dynamic indicator manager integration working correctly!")
        print("- Daily Bollinger Bands: ✓")
        print("- Weekly Bollinger Bands: ✓")
        print("- Monthly Bollinger Bands: ✓")
        print("- Custom parameters: ✓")
        print("- BB alias support: ✓")
        print("="*80)
    else:
        print("\n" + "="*80)
        print("BOLLINGER BANDS INTEGRATION TEST FAILED")
        print("Please check the logs for specific issues")
        print("="*80)

if __name__ == "__main__":
    asyncio.run(main())