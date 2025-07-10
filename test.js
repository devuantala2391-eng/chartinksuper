const fs = require('fs');
const path = require('path');
const { calculateRollingWeeklySMA } = require('./mapper');

// Read input JSON
const inputPath = path.join(__dirname, 'db', 'jsonfile', 'KELLTONTEC.json');
const outputDir = path.join(__dirname, 'mapperStorage');
const outputPath = path.join(outputDir, 'KELLTONTEC.json');

if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}

const jsonData = JSON.parse(fs.readFileSync(inputPath, 'utf8'));

// Calculate 20-week rolling weekly SMA on daily candles
const result = calculateRollingWeeklySMA(jsonData.data, 20);

fs.writeFileSync(outputPath, JSON.stringify({ data: result }, null, 2), 'utf8');

console.log('Rolling weekly SMA calculation complete. Output saved to', outputPath); 