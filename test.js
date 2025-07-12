const fs = require('fs');
const path = require('path');
const {
  calculateSMAFactory,
  calculateEMAFactory,
  calculateRSIFactory,
  calculatePercentChangeFactory,
  calculateSuperTrendFactory,
  pipe
} = require('./mapper');

// Read input JSON
const inputPath = path.join(__dirname, 'db', 'jsonfile', 'KELLTONTEC.json');
const outputDir = path.join(__dirname, 'mapperStorage');
const outputPathPiped = path.join(outputDir, 'KELLTONTEC_piped.json');

if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}

const jsonData = JSON.parse(fs.readFileSync(inputPath, 'utf8'));
const candles = jsonData.data;

// Pipe all indicators in both daily and weekly timeframes
const resultPiped = pipe(
  candles,
  // Daily indicators
  calculateSMAFactory('daily', 20, 'sma_daily'),
  calculateEMAFactory('daily', 20, 'ema_daily'),
  calculateRSIFactory('daily', 14, 'rsi_daily'),
  calculatePercentChangeFactory('daily', 1, 'pctchg_daily'),
  calculateSuperTrendFactory('daily', 10, 3, 'supertrend_daily'),
  // Weekly indicators
  calculateSMAFactory('weekly', 10, 'sma_weekly'),
  calculateEMAFactory('weekly', 10, 'ema_weekly'),
  calculateRSIFactory('weekly', 14, 'rsi_weekly'),
  calculatePercentChangeFactory('weekly', 1, 'pctchg_weekly'),
  calculateSuperTrendFactory('weekly', 10, 3, 'supertrend_weekly')
);

fs.writeFileSync(outputPathPiped, JSON.stringify({ data: resultPiped }, null, 2), 'utf8');
console.log('Piped all indicators (daily & weekly) complete. Output saved to', outputPathPiped); 