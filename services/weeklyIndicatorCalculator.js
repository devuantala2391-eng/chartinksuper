// services/weeklyIndicatorCalculator.js

/**
 * Weekly Indicator Calculator Service
 * Calculates weekly indicators on a daily basis
 * For each day, uses current day's close for current week and Friday's close for previous weeks
 */

const { sanitizeNumericValue } = require('./dataUtils');

// Helper function to get ISO week key
function getISOWeekKey(date) {
  const year = date.getUTCFullYear();
  const week = getISOWeek(date);
  return `${year}-W${week}`;
}

// Get ISO week number
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

// Calculate Weekly SMA for each day
function calculateWeeklySMADaily(candles, period) {
  const result = [];
  
  // Helper to get Monday of a week
  function getMonday(d) {
    d = new Date(d);
    const day = d.getDay();
    const diff = d.getDate() - day + (day === 0 ? -6 : 1); // adjust when day is sunday
    return new Date(d.setDate(diff));
  }
  
  // Group candles by week (Monday to Friday)
  const weeklyData = new Map();
  
  candles.forEach((candle, idx) => {
    const date = new Date(Number(candle.date));
    const monday = getMonday(date);
    const weekKey = monday.toISOString().split('T')[0];
    
    if (!weeklyData.has(weekKey)) {
      weeklyData.set(weekKey, []);
    }
    weeklyData.get(weekKey).push({ ...candle, index: idx });
  });
  
  // For each day, calculate the weekly SMA
  candles.forEach((candle, index) => {
    const targetDate = new Date(Number(candle.date));
    const targetMonday = getMonday(targetDate);
    const targetWeekKey = targetMonday.toISOString().split('T')[0];
    
    // Sort weeks in descending order (most recent first)
    const sortedWeeks = Array.from(weeklyData.keys()).sort().reverse();
    const targetWeekIndex = sortedWeeks.indexOf(targetWeekKey);
    
    // Check if we have enough data
    if (targetWeekIndex === -1 || sortedWeeks.length - targetWeekIndex < period) {
      result.push(null);
      return;
    }
    
    // Collect values: current day + last trading day of previous 19 weeks
    const values = [];
    
    // Current day's close
    values.push(sanitizeNumericValue(candle.close));
    
    // Previous weeks (going back in time)
    for (let i = 1; i < period && targetWeekIndex + i < sortedWeeks.length; i++) {
      const weekKey = sortedWeeks[targetWeekIndex + i];
      const weekCandles = weeklyData.get(weekKey);
      
      if (weekCandles && weekCandles.length > 0) {
        // Get last trading day of the week (but only if it's before our target date)
        const validCandles = weekCandles.filter(c => c.index < index);
        if (validCandles.length > 0) {
          const lastCandle = validCandles[validCandles.length - 1];
          values.push(sanitizeNumericValue(lastCandle.close));
        }
      }
    }
    
    // Calculate SMA if we have exactly 'period' values
    if (values.length === period) {
      const sum = values.reduce((a, b) => a + b, 0);
      result.push(sum / period);
    } else {
      result.push(null);
    }
  });
  
  return result;
}

// Calculate Weekly EMA for each day
function calculateWeeklyEMADaily(candles, period) {
  const result = [];
  const multiplier = 2 / (period + 1);
  
  // Helper to get Monday of a week
  function getMonday(d) {
    d = new Date(d);
    const day = d.getDay();
    const diff = d.getDate() - day + (day === 0 ? -6 : 1);
    return new Date(d.setDate(diff));
  }
  
  // Group candles by week
  const weeklyData = new Map();
  
  candles.forEach((candle, idx) => {
    const date = new Date(Number(candle.date));
    const monday = getMonday(date);
    const weekKey = monday.toISOString().split('T')[0];
    
    if (!weeklyData.has(weekKey)) {
      weeklyData.set(weekKey, []);
    }
    weeklyData.get(weekKey).push({ ...candle, index: idx });
  });
  
  // Sort weeks chronologically
  const sortedWeeks = Array.from(weeklyData.keys()).sort();
  
  // Calculate EMA week by week first (using last trading day's close)
  const weeklyEMA = new Map();
  let lastEMA = null;
  
  sortedWeeks.forEach(weekKey => {
    const weekCandles = weeklyData.get(weekKey);
    if (weekCandles && weekCandles.length > 0) {
      const lastCandle = weekCandles[weekCandles.length - 1];
      const weekClose = sanitizeNumericValue(lastCandle.close);
      
      if (weekClose !== null) {
        if (lastEMA === null) {
          lastEMA = weekClose;
        } else {
          lastEMA = (weekClose - lastEMA) * multiplier + lastEMA;
        }
        weeklyEMA.set(weekKey, lastEMA);
      }
    }
  });
  
  // Now for each day, calculate the EMA including current day
  candles.forEach((candle, index) => {
    const currentDate = new Date(Number(candle.date));
    const currentMonday = getMonday(currentDate);
    const currentWeekKey = currentMonday.toISOString().split('T')[0];
    const currentClose = sanitizeNumericValue(candle.close);
    
    // Find the index of current week
    const weekIndex = sortedWeeks.indexOf(currentWeekKey);
    
    if (weekIndex > 0 && currentClose !== null) {
      // Get EMA from the previous week
      const prevWeekKey = sortedWeeks[weekIndex - 1];
      const prevWeekEMA = weeklyEMA.get(prevWeekKey);
      
      if (prevWeekEMA !== null) {
        // Calculate EMA using current day's close and previous week's EMA
        const currentEMA = (currentClose - prevWeekEMA) * multiplier + prevWeekEMA;
        result.push(currentEMA);
      } else {
        result.push(null);
      }
    } else if (weekIndex === 0 && currentClose !== null) {
      // First week - use the close price as initial EMA
      result.push(currentClose);
    } else {
      result.push(null);
    }
  });
  
  return result;
}

// Calculate Weekly RSI for each day
function calculateWeeklyRSIDaily(candles, period = 14) {
  const result = [];
  
  // Group candles by week
  const weeklyData = new Map();
  
  candles.forEach(candle => {
    const date = new Date(Number(candle.date));
    const weekKey = getISOWeekKey(date);
    
    if (!weeklyData.has(weekKey)) {
      weeklyData.set(weekKey, []);
    }
    weeklyData.get(weekKey).push(candle);
  });
  
  // Sort week keys
  const sortedWeeks = Array.from(weeklyData.keys()).sort();
  
  // Calculate weekly gains and losses
  const weeklyGains = [];
  const weeklyLosses = [];
  
  for (let i = 0; i < sortedWeeks.length; i++) {
    const weekKey = sortedWeeks[i];
    const weekCandles = weeklyData.get(weekKey);
    
    if (i === 0 || !weekCandles || weekCandles.length === 0) {
      weeklyGains.push(0);
      weeklyLosses.push(0);
    } else {
      const prevWeekKey = sortedWeeks[i - 1];
      const prevWeekCandles = weeklyData.get(prevWeekKey);
      
      if (prevWeekCandles && prevWeekCandles.length > 0) {
        const currentWeekClose = sanitizeNumericValue(weekCandles[weekCandles.length - 1].close);
        const prevWeekClose = sanitizeNumericValue(prevWeekCandles[prevWeekCandles.length - 1].close);
        
        if (currentWeekClose !== null && prevWeekClose !== null) {
          const change = currentWeekClose - prevWeekClose;
          weeklyGains.push(change > 0 ? change : 0);
          weeklyLosses.push(change < 0 ? Math.abs(change) : 0);
        } else {
          weeklyGains.push(0);
          weeklyLosses.push(0);
        }
      } else {
        weeklyGains.push(0);
        weeklyLosses.push(0);
      }
    }
  }
  
  // Now calculate RSI for each day
  candles.forEach((candle, index) => {
    const currentDate = new Date(Number(candle.date));
    const currentWeekKey = getISOWeekKey(currentDate);
    const currentWeekIndex = sortedWeeks.indexOf(currentWeekKey);
    const currentClose = sanitizeNumericValue(candle.close);
    
    if (currentWeekIndex < period || currentClose === null) {
      result.push(null);
      return;
    }
    
    // Calculate gains/losses including current day
    let gains = [...weeklyGains];
    let losses = [...weeklyLosses];
    
    // Update current week's gain/loss with current day's data
    if (currentWeekIndex > 0) {
      const prevWeekKey = sortedWeeks[currentWeekIndex - 1];
      const prevWeekCandles = weeklyData.get(prevWeekKey);
      
      if (prevWeekCandles && prevWeekCandles.length > 0) {
        const prevWeekClose = sanitizeNumericValue(prevWeekCandles[prevWeekCandles.length - 1].close);
        
        if (prevWeekClose !== null) {
          const change = currentClose - prevWeekClose;
          gains[currentWeekIndex] = change > 0 ? change : 0;
          losses[currentWeekIndex] = change < 0 ? Math.abs(change) : 0;
        }
      }
    }
    
    // Calculate average gain and loss for the period
    const relevantGains = gains.slice(currentWeekIndex - period + 1, currentWeekIndex + 1);
    const relevantLosses = losses.slice(currentWeekIndex - period + 1, currentWeekIndex + 1);
    
    const avgGain = relevantGains.reduce((a, b) => a + b, 0) / period;
    const avgLoss = relevantLosses.reduce((a, b) => a + b, 0) / period;
    
    if (avgLoss === 0) {
      result.push(100);
    } else {
      const rs = avgGain / avgLoss;
      const rsi = 100 - (100 / (1 + rs));
      result.push(rsi);
    }
  });
  
  return result;
}

// Calculate all weekly indicators for daily candles
function calculateWeeklyIndicatorsDaily(candles, indicators) {
  const result = [];
  
  // Extract price arrays
  const closes = candles.map(c => sanitizeNumericValue(c.close));
  const highs = candles.map(c => sanitizeNumericValue(c.high));
  const lows = candles.map(c => sanitizeNumericValue(c.low));
  
  // Calculate each requested indicator
  const calculatedIndicators = {};
  
  for (const indicator of indicators) {
    const { name, period, params } = indicator;
    
    try {
      switch (name.toLowerCase()) {
        case 'sma':
          calculatedIndicators[`weekly_sma_${period}`] = calculateWeeklySMADaily(candles, period);
          break;
          
        case 'ema':
          calculatedIndicators[`weekly_ema_${period}`] = calculateWeeklyEMADaily(candles, period);
          break;
          
        case 'rsi':
          calculatedIndicators[`weekly_rsi_${period}`] = calculateWeeklyRSIDaily(candles, period);
          break;
          
        // Add more indicators as needed
      }
    } catch (error) {
      console.error(`Error calculating weekly ${name}(${period}):`, error.message);
    }
  }
  
  // Combine all indicators with candles
  candles.forEach((candle, i) => {
    const resultCandle = { ...candle };
    
    // Add all calculated indicators
    Object.keys(calculatedIndicators).forEach(key => {
      const value = calculatedIndicators[key][i];
      resultCandle[key] = value !== null ? value.toString() : null;
    });
    
    result.push(resultCandle);
  });
  
  return result;
}

module.exports = {
  calculateWeeklySMADaily,
  calculateWeeklyEMADaily,
  calculateWeeklyRSIDaily,
  calculateWeeklyIndicatorsDaily
};