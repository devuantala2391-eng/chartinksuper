const fs = require('fs');
const path = require('path');
const {
  calculateSMAFactory,
  calculateEMAFactory,
  calculateRSIFactory,
  calculatePercentChangeFactory,
  calculateSuperTrendFactory,
  calculateBollingerBandsFactory,
  calculateWeeklyVolumeFactory,
  pipe
} = require('./mapper');

// Read input JSON
const inputPath = path.join(__dirname, 'db', 'KELLTONTEC.json');
const outputDir = path.join(__dirname, 'mapperStorage');
const outputPathPiped = path.join(outputDir, 'KELLTONTEC_piped.json');

if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}

const jsonData = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
const candles = jsonData.data;

// Debug: Test weekly calculations on last few candles
console.log('=== DEBUG: Last 5 candles ===');
const last5Candles = candles.slice(-5);
last5Candles.forEach((candle, idx) => {
  console.log(`${idx + 1}. ${candle.day} ${new Date(Number(candle.date)).toISOString().split('T')[0]} - Close: ${candle.close}`);
});

// Test weekly calculations individually
console.log('\n=== DEBUG: Weekly calculations ===');
const weeklySMA = calculateSMAFactory('weekly', 10, 'sma_weekly')(candles);
const weeklyEMA = calculateEMAFactory('weekly', 10, 'ema_weekly')(candles);
const weeklyRSI = calculateRSIFactory('weekly', 14, 'rsi_weekly')(candles);
const weeklyPctChg = calculatePercentChangeFactory('weekly', 1, 'pctchg_weekly')(candles);
const weeklySuperTrend = calculateSuperTrendFactory('weekly', 10, 3, 'supertrend_weekly')(candles);

const lastCandle = candles[candles.length - 1];
const lastWeeklySMA = weeklySMA[weeklySMA.length - 1];
const lastWeeklyEMA = weeklyEMA[weeklyEMA.length - 1];
const lastWeeklyRSI = weeklyRSI[weeklyRSI.length - 1];
const lastWeeklyPctChg = weeklyPctChg[weeklyPctChg.length - 1];
const lastWeeklySuperTrend = weeklySuperTrend[weeklySuperTrend.length - 1];

console.log('Last candle date:', new Date(Number(lastCandle.date)).toISOString().split('T')[0]);
console.log('Last candle close:', lastCandle.close);
console.log('Weekly SMA:', lastWeeklySMA.sma_weekly);
console.log('Weekly EMA:', lastWeeklyEMA.ema_weekly);
console.log('Weekly RSI:', lastWeeklyRSI.rsi_weekly);
console.log('Weekly %Change:', lastWeeklyPctChg.pctchg_weekly);
console.log('Weekly SuperTrend:', lastWeeklySuperTrend.supertrend_weekly);
console.log('Weekly SuperTrend Trend:', lastWeeklySuperTrend.supertrend_weekly_trend);

// Pipe all indicators in both daily and weekly timeframes
const resultPiped = pipe(
  candles,
  // Daily indicators
  calculateSMAFactory('daily', 20, 'sma_daily'),
  calculateEMAFactory('daily', 20, 'ema_daily'),
  calculateRSIFactory('daily', 14, 'rsi_daily'),
  calculatePercentChangeFactory('daily', 1, 'pctchg_daily'),
  calculateSuperTrendFactory('daily', 10, 3, 'supertrend_daily'),
  calculateBollingerBandsFactory('daily', 20, 2, 'bb_upper_daily', 'bb_lower_daily'),
  // Weekly indicators
  calculateSMAFactory('weekly', 10, 'sma_weekly'),
  calculateEMAFactory('weekly', 10, 'ema_weekly'),
  calculateRSIFactory('weekly', 14, 'rsi_weekly'),
  calculatePercentChangeFactory('weekly', 1, 'pctchg_weekly'),
  calculateSuperTrendFactory('weekly', 10, 3, 'supertrend_weekly'),
  calculateBollingerBandsFactory('weekly', 20, 2, 'bb_upper_weekly', 'bb_lower_weekly'),
  // Weekly volume
  calculateWeeklyVolumeFactory('volume_weekly')
);

fs.writeFileSync(outputPathPiped, JSON.stringify({ data: resultPiped }, null, 2), 'utf8');
console.log('Piped all indicators (daily & weekly) complete. Output saved to', outputPathPiped);