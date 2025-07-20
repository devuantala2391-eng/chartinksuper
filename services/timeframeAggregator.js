// services/timeframeAggregator.js

const { sanitizeNumericValue } = require('./dataUtils');
const { 
  calculateWeeklySMADaily, 
  calculateWeeklyEMADaily, 
  calculateWeeklyRSIDaily,
  calculateMonthlySMADaily,
  calculateMonthlyEMADaily,
  calculateWeeklyBollingerBandsDaily,
  calculateMonthlyBollingerBandsDaily
} = require('./weeklyIndicatorCalculator');

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
  const { calculateAllIndicators } = require('./indicatorCalculator');
  
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
  
  // Calculate weekly indicators using the new daily-based calculation
  const weeklyIndicatorValues = {};
  
  indicators.forEach(indicator => {
    const { name, period, params } = indicator;
    
    switch (name.toLowerCase()) {
      case 'sma':
        weeklyIndicatorValues[`weekly_sma_${period}`] = calculateWeeklySMADaily(dailyCandles, period);
        break;
      case 'ema':
        weeklyIndicatorValues[`weekly_ema_${period}`] = calculateWeeklyEMADaily(dailyCandles, period);
        break;
      case 'rsi':
        weeklyIndicatorValues[`weekly_rsi_${period}`] = calculateWeeklyRSIDaily(dailyCandles, period || 14);
        break;
      case 'bb':
      case 'bollinger':
        const weeklyBB = calculateWeeklyBollingerBandsDaily(dailyCandles, period || 20, params?.stdDev || 2);
        weeklyIndicatorValues[`weekly_bb_upper_${period || 20}_${params?.stdDev || 2}`] = weeklyBB.upper;
        weeklyIndicatorValues[`weekly_bb_middle_${period || 20}_${params?.stdDev || 2}`] = weeklyBB.middle;
        weeklyIndicatorValues[`weekly_bb_lower_${period || 20}_${params?.stdDev || 2}`] = weeklyBB.lower;
        break;
    }
  });
  
  // Calculate monthly indicators using the new daily-based calculation
  const monthlyIndicatorValues = {};
  
  indicators.forEach(indicator => {
    const { name, period, params } = indicator;
    
    switch (name.toLowerCase()) {
      case 'sma':
        monthlyIndicatorValues[`monthly_sma_${period}`] = calculateMonthlySMADaily(dailyCandles, period);
        break;
      case 'ema':
        monthlyIndicatorValues[`monthly_ema_${period}`] = calculateMonthlyEMADaily(dailyCandles, period);
        break;
      case 'bb':
      case 'bollinger':
        const monthlyBB = calculateMonthlyBollingerBandsDaily(dailyCandles, period || 20, params?.stdDev || 2);
        monthlyIndicatorValues[`monthly_bb_upper_${period || 20}_${params?.stdDev || 2}`] = monthlyBB.upper;
        monthlyIndicatorValues[`monthly_bb_middle_${period || 20}_${params?.stdDev || 2}`] = monthlyBB.middle;
        monthlyIndicatorValues[`monthly_bb_lower_${period || 20}_${params?.stdDev || 2}`] = monthlyBB.lower;
        break;
    }
  });
  
  // Check if volume is requested as an indicator
  const hasWeeklyVolume = indicators.some(ind => ind.name === 'volume' && ind.timeframe === 'weekly');
  const hasMonthlyVolume = indicators.some(ind => ind.name === 'volume' && ind.timeframe === 'monthly');
  
  // Map indicators to daily candles
  dailyCandles.forEach((dailyCandle, index) => {
    const date = new Date(Number(dailyCandle.date));
    const weekKey = getISOWeekKey(date);
    const monthKey = `${date.getUTCFullYear()}-${date.getUTCMonth()}`;
    
    const weeklyCandle = weeklyMap.get(weekKey);
    const monthlyCandle = monthlyMap.get(monthKey);
    
    // Only calculate weekly volume if requested
    if (hasWeeklyVolume) {
      // Calculate cumulative weekly volume from Monday to current day
      let cumulativeWeeklyVolume = 0;
      const currentWeekNumber = getISOWeek(date);
      const currentYear = date.getUTCFullYear();
      
      // Go backwards from current candle to find all candles in the same week up to current day
      for (let i = index; i >= 0; i--) {
        const candleDate = new Date(Number(dailyCandles[i].date));
        const candleWeek = getISOWeek(candleDate);
        const candleYear = candleDate.getUTCFullYear();
        
        // If we've gone to a different week, stop
        if (candleYear !== currentYear || candleWeek !== currentWeekNumber) {
          break;
        }
        
        // Add this candle's volume to cumulative total
        const volume = sanitizeNumericValue(dailyCandles[i].volume);
        if (volume !== null) {
          cumulativeWeeklyVolume += volume;
        }
      }
      
      // Set the cumulative weekly volume
      dailyCandle['weekly_volume'] = cumulativeWeeklyVolume;
    }
    
    // Only calculate monthly volume if requested
    if (hasMonthlyVolume) {
      // Calculate cumulative monthly volume from 1st to current day
      let cumulativeMonthlyVolume = 0;
      const currentMonth = date.getUTCMonth();
      const currentMonthYear = date.getUTCFullYear();
      
      // Go backwards from current candle to find all candles in the same month
      for (let i = index; i >= 0; i--) {
        const candleDate = new Date(Number(dailyCandles[i].date));
        const candleMonth = candleDate.getUTCMonth();
        const candleYear = candleDate.getUTCFullYear();
        
        // If we've gone to a different month, stop
        if (candleYear !== currentMonthYear || candleMonth !== currentMonth) {
          break;
        }
        
        // Add this candle's volume to cumulative total
        const volume = sanitizeNumericValue(dailyCandles[i].volume);
        if (volume !== null) {
          cumulativeMonthlyVolume += volume;
        }
      }
      
      // Set the cumulative monthly volume
      dailyCandle['monthly_volume'] = cumulativeMonthlyVolume;
    }
    
    // Always calculate weekly OHLC for current week (default behavior)
    // Find the first and last candle of the current week up to current day
    let weeklyOpen = null, weeklyHigh = null, weeklyLow = null, weeklyClose = null;
    const currentWeekNumber = getISOWeek(date);
    const currentYear = date.getUTCFullYear();
    
    // Collect all candles for current week up to current day
    const currentWeekCandles = [];
    for (let i = index; i >= 0; i--) {
      const candleDate = new Date(Number(dailyCandles[i].date));
      const candleWeek = getISOWeek(candleDate);
      const candleYear = candleDate.getUTCFullYear();
      
      // If we've gone to a different week, stop
      if (candleYear !== currentYear || candleWeek !== currentWeekNumber) {
        break;
      }
      
      currentWeekCandles.unshift(dailyCandles[i]); // Add at beginning to maintain order
    }
    
    if (currentWeekCandles.length > 0) {
      // Open is from first candle of the week
      weeklyOpen = sanitizeNumericValue(currentWeekCandles[0].open);
      // Close is from the current day (last candle)
      weeklyClose = sanitizeNumericValue(currentWeekCandles[currentWeekCandles.length - 1].close);
      
      // High is the max of all highs in the week
      weeklyHigh = Math.max(...currentWeekCandles.map(c => sanitizeNumericValue(c.high)).filter(v => v !== null));
      // Low is the min of all lows in the week
      weeklyLow = Math.min(...currentWeekCandles.map(c => sanitizeNumericValue(c.low)).filter(v => v !== null));
      
      // Set the weekly OHLC values
      dailyCandle['weekly_open'] = weeklyOpen;
      dailyCandle['weekly_high'] = weeklyHigh;
      dailyCandle['weekly_low'] = weeklyLow;
      dailyCandle['weekly_close'] = weeklyClose;
    }
    
    // Always calculate monthly OHLC for current month (default behavior)
    // Find the first and last candle of the current month up to current day
    let monthlyOpen = null, monthlyHigh = null, monthlyLow = null, monthlyClose = null;
    const currentMonth = date.getUTCMonth();
    const currentMonthYear = date.getUTCFullYear();
    
    // Collect all candles for current month up to current day
    const currentMonthCandles = [];
    for (let i = index; i >= 0; i--) {
      const candleDate = new Date(Number(dailyCandles[i].date));
      const candleMonth = candleDate.getUTCMonth();
      const candleYear = candleDate.getUTCFullYear();
      
      // If we've gone to a different month, stop
      if (candleYear !== currentMonthYear || candleMonth !== currentMonth) {
        break;
      }
      
      currentMonthCandles.unshift(dailyCandles[i]); // Add at beginning to maintain order
    }
    
    if (currentMonthCandles.length > 0) {
      // Open is from first candle of the month
      monthlyOpen = sanitizeNumericValue(currentMonthCandles[0].open);
      // Close is from the current day (last candle)
      monthlyClose = sanitizeNumericValue(currentMonthCandles[currentMonthCandles.length - 1].close);
      
      // High is the max of all highs in the month
      monthlyHigh = Math.max(...currentMonthCandles.map(c => sanitizeNumericValue(c.high)).filter(v => v !== null));
      // Low is the min of all lows in the month
      monthlyLow = Math.min(...currentMonthCandles.map(c => sanitizeNumericValue(c.low)).filter(v => v !== null));
      
      // Set the monthly OHLC values
      dailyCandle['monthly_open'] = monthlyOpen;
      dailyCandle['monthly_high'] = monthlyHigh;
      dailyCandle['monthly_low'] = monthlyLow;
      dailyCandle['monthly_close'] = monthlyClose;
    }
    
    // Map the new daily-calculated weekly indicators
    Object.keys(weeklyIndicatorValues).forEach(key => {
      const value = weeklyIndicatorValues[key][index];
      dailyCandle[key] = value !== null ? value.toString() : null;
    });
    
    // Map the new daily-calculated monthly indicators
    Object.keys(monthlyIndicatorValues).forEach(key => {
      const value = monthlyIndicatorValues[key][index];
      dailyCandle[key] = value !== null ? value.toString() : null;
    });
    
    // For other weekly indicators not yet implemented in the new system, use the old approach
    if (weeklyCandle) {
      indicators.forEach(indicator => {
        const { name, period, params } = indicator;
        // Map weekly indicator fields that aren't already handled
        Object.keys(weeklyCandle).forEach(key => {
          if ((key.startsWith('bb_') || key.startsWith('macd_') || key.startsWith('stoch_') || key.startsWith('supertrend_') || key.startsWith('pctchg_')) ||
              (key.startsWith(`${name}_`) && !['sma', 'ema', 'rsi'].includes(name.toLowerCase()))) {
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
          if (key.startsWith(`${name}_`) || key.startsWith('bb_') || key.startsWith('macd_') || key.startsWith('stoch_') || key.startsWith('supertrend_') || key.startsWith('pctchg_')) {
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