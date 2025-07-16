// services/timeframeAggregator.js

const { sanitizeNumericValue } = require('./dataUtils');

/**
 * Aggregates daily candles into weekly candles
 * @param {Array} candles - Array of daily candles
 * @returns {Array} Array of weekly candles
 */
function aggregateToWeekly(candles) {
  const weeklyCandles = [];
  const weekGroups = new Map();
  
  // Group candles by week
  candles.forEach(candle => {
    const date = new Date(Number(candle.date));
    const weekKey = getISOWeekKey(date);
    
    if (!weekGroups.has(weekKey)) {
      weekGroups.set(weekKey, []);
    }
    weekGroups.get(weekKey).push(candle);
  });
  
  // Create weekly candles from groups
  for (const [weekKey, weekCandles] of weekGroups) {
    if (weekCandles.length === 0) continue;
    
    const firstCandle = weekCandles[0];
    const lastCandle = weekCandles[weekCandles.length - 1];
    
    const weeklyCandle = {
      date: lastCandle.date, // Use last date of week
      day: lastCandle.day,
      open: sanitizeNumericValue(firstCandle.open),
      high: Math.max(...weekCandles.map(c => sanitizeNumericValue(c.high)).filter(v => v !== null)),
      low: Math.min(...weekCandles.map(c => sanitizeNumericValue(c.low)).filter(v => v !== null)),
      close: sanitizeNumericValue(lastCandle.close),
      volume: weekCandles.reduce((sum, c) => {
        const vol = sanitizeNumericValue(c.volume);
        return sum + (vol !== null ? vol : 0);
      }, 0),
      weekKey: weekKey
    };
    
    weeklyCandles.push(weeklyCandle);
  }
  
  // Sort by date
  weeklyCandles.sort((a, b) => Number(a.date) - Number(b.date));
  
  return weeklyCandles;
}

/**
 * Aggregates daily candles into monthly candles
 * @param {Array} candles - Array of daily candles
 * @returns {Array} Array of monthly candles
 */
function aggregateToMonthly(candles) {
  const monthlyCandles = [];
  const monthGroups = new Map();
  
  // Group candles by month
  candles.forEach(candle => {
    const date = new Date(Number(candle.date));
    const monthKey = `${date.getUTCFullYear()}-${date.getUTCMonth()}`;
    
    if (!monthGroups.has(monthKey)) {
      monthGroups.set(monthKey, []);
    }
    monthGroups.get(monthKey).push(candle);
  });
  
  // Create monthly candles from groups
  for (const [monthKey, monthCandles] of monthGroups) {
    if (monthCandles.length === 0) continue;
    
    const firstCandle = monthCandles[0];
    const lastCandle = monthCandles[monthCandles.length - 1];
    
    const monthlyCandle = {
      date: lastCandle.date, // Use last date of month
      day: lastCandle.day,
      open: sanitizeNumericValue(firstCandle.open),
      high: Math.max(...monthCandles.map(c => sanitizeNumericValue(c.high)).filter(v => v !== null)),
      low: Math.min(...monthCandles.map(c => sanitizeNumericValue(c.low)).filter(v => v !== null)),
      close: sanitizeNumericValue(lastCandle.close),
      volume: monthCandles.reduce((sum, c) => {
        const vol = sanitizeNumericValue(c.volume);
        return sum + (vol !== null ? vol : 0);
      }, 0),
      monthKey: monthKey
    };
    
    monthlyCandles.push(monthlyCandle);
  }
  
  // Sort by date
  monthlyCandles.sort((a, b) => Number(a.date) - Number(b.date));
  
  return monthlyCandles;
}

/**
 * Get ISO week key for grouping
 */
function getISOWeekKey(date) {
  const year = date.getUTCFullYear();
  const week = getISOWeek(date);
  return `${year}-W${week}`;
}

/**
 * Get ISO week number
 */
function getISOWeek(date) {
  const tmp = new Date(date.valueOf());
  const dayNum = (date.getUTCDay() + 6) % 7;
  tmp.setUTCDate(tmp.getUTCDate() - dayNum + 3);
  const firstThursday = tmp.valueOf();
  tmp.setUTCMonth(0, 1);
  if (tmp.getUTCDay() !== 4) {
    tmp.setUTCMonth(0, 1 + ((4 - tmp.getUTCDay()) + 7) % 7);
  }
  return 1 + Math.ceil((firstThursday - tmp) / 604800000);
}

/**
 * Maps aggregated indicator values back to daily candles
 * This allows us to access weekly/monthly indicators on any daily candle
 */
function mapAggregatedIndicators(dailyCandles, weeklyCandles, monthlyCandles, indicators) {
  // Create maps for quick lookup
  const weeklyMap = new Map();
  const monthlyMap = new Map();
  
  // Build weekly map
  weeklyCandles.forEach(candle => {
    weeklyMap.set(candle.weekKey, candle);
  });
  
  // Build monthly map
  monthlyCandles.forEach(candle => {
    monthlyMap.set(candle.monthKey, candle);
  });
  
  // Map indicators to daily candles
  dailyCandles.forEach(dailyCandle => {
    const date = new Date(Number(dailyCandle.date));
    const weekKey = getISOWeekKey(date);
    const monthKey = `${date.getUTCFullYear()}-${date.getUTCMonth()}`;
    
    const weeklyCandle = weeklyMap.get(weekKey);
    const monthlyCandle = monthlyMap.get(monthKey);
    
    // Map weekly indicators
    if (weeklyCandle) {
      indicators.forEach(indicator => {
        const { name, period, params } = indicator;
        // Map all weekly indicator fields to daily candle with weekly_ prefix
        Object.keys(weeklyCandle).forEach(key => {
          if (key.startsWith(`${name}_`) || key.startsWith('bb_') || key.startsWith('macd_') || key.startsWith('stoch_')) {
            dailyCandle[`weekly_${key}`] = weeklyCandle[key];
          }
        });
      });
    }
    
    // Map monthly indicators
    if (monthlyCandle) {
      indicators.forEach(indicator => {
        const { name, period, params } = indicator;
        // Map all monthly indicator fields to daily candle with monthly_ prefix
        Object.keys(monthlyCandle).forEach(key => {
          if (key.startsWith(`${name}_`) || key.startsWith('bb_') || key.startsWith('macd_') || key.startsWith('stoch_')) {
            dailyCandle[`monthly_${key}`] = monthlyCandle[key];
          }
        });
      });
    }
  });
  
  return dailyCandles;
}

module.exports = {
  aggregateToWeekly,
  aggregateToMonthly,
  mapAggregatedIndicators
};