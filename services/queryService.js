// services/queryService.js

const INDICATOR_MAPPINGS = {
  // Bollinger Bands
  'daily upper bollinger band': 'bb_upper_daily',
  'daily lower bollinger band': 'bb_lower_daily',
  'weekly upper bollinger band': 'bb_upper_weekly',
  'weekly lower bollinger band': 'bb_lower_weekly',
  'daily bb upper': 'bb_upper_daily',
  'daily bb lower': 'bb_lower_daily',
  'weekly bb upper': 'bb_upper_weekly',
  'weekly bb lower': 'bb_lower_weekly',
  
  // SMA
  'daily sma': 'sma_daily',
  'weekly sma': 'sma_weekly',
  
  // EMA
  'daily ema': 'ema_daily',
  'weekly ema': 'ema_weekly',
  
  // RSI
  'daily rsi': 'rsi_daily',
  'weekly rsi': 'rsi_weekly',
  
  // SuperTrend
  'daily supertrend': 'supertrend_daily',
  'weekly supertrend': 'supertrend_weekly',
  'daily super trend': 'supertrend_daily',
  'weekly super trend': 'supertrend_weekly',
  
  // Price fields
  'daily close': 'close',
  'close': 'close',
  'open': 'open',
  'high': 'high',
  'low': 'low',
  'volume': 'volume',
  
  // Volume fields
  'weekly volume': 'volume_weekly',
  'week volume': 'volume_weekly',
  
  // Percent change
  'daily percent change': 'pctchg_daily',
  'weekly percent change': 'pctchg_weekly',
  'daily pct change': 'pctchg_daily',
  'weekly pct change': 'pctchg_weekly',
  
  // Special cases
  'current close': 'close',
  'yesterday\'s close': 'prev_close',
  'previous close': 'prev_close',
  'yesterdays close': 'prev_close',
};

// Additional field mappings for simplified names
const SIMPLE_FIELD_MAPPINGS = {
  'rsi': 'rsi_daily',
  'sma': 'sma_daily',
  'ema': 'ema_daily',
  'upper bollinger band': 'bb_upper_daily',
  'lower bollinger band': 'bb_lower_daily',
  'supertrend': 'supertrend_daily',
  'super trend': 'supertrend_daily',
  'percent change': 'pctchg_daily',
  'pct change': 'pctchg_daily',
  '% change': 'pctchg_daily',
};


const OPERATORS = {
  '>': (a, b) => a > b,
  '<': (a, b) => a < b,
  '>=': (a, b) => a >= b,
  '<=': (a, b) => a <= b,
  '=': (a, b) => a === b,
  '==': (a, b) => a === b,
  '!=': (a, b) => a !== b,
  '<>': (a, b) => a !== b,
};

const LOGICAL_OPERATORS = ['and', 'or', '&&', '||'];

function normalizeQuery(query) {
  return query
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .replace(/\s*([><=!]+)\s*/g, ' $1 ')
    .trim();
}

function extractConditions(query) {
  const parts = [];
  let currentPart = '';
  const tokens = query.split(' ');
  
  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];
    if (LOGICAL_OPERATORS.includes(token)) {
      if (currentPart.trim()) {
        parts.push({ type: 'condition', value: currentPart.trim() });
      }
      parts.push({ type: 'operator', value: token });
      currentPart = '';
    } else {
      currentPart += ' ' + token;
    }
  }
  
  if (currentPart.trim()) {
    parts.push({ type: 'condition', value: currentPart.trim() });
  }
  
  return parts;
}

function parseCondition(conditionStr) {
  let operator = null;
  let operatorIndex = -1;
  
  for (const op of Object.keys(OPERATORS).sort((a, b) => b.length - a.length)) {
    const index = conditionStr.indexOf(' ' + op + ' ');
    if (index !== -1) {
      operator = op;
      operatorIndex = index;
      break;
    }
  }
  
  if (!operator) {
    throw new Error(`No valid operator found in condition: ${conditionStr}`);
  }
  
  const leftSide = conditionStr.substring(0, operatorIndex).trim();
  const rightSide = conditionStr.substring(operatorIndex + operator.length + 2).trim();
  
  const leftField = parseField(leftSide);
  const rightField = parseField(rightSide);
  
  return {
    left: leftField,
    operator: operator,
    right: rightField,
    compareFn: OPERATORS[operator]
  };
}

function parseField(fieldStr) {
  // Check if it's a number
  const numValue = parseFloat(fieldStr);
  if (!isNaN(numValue) && !fieldStr.includes(' ')) {
    return { type: 'value', value: numValue };
  }
  
  // Check if it's a percentage (e.g., "5%")
  if (fieldStr.endsWith('%')) {
    const percentValue = parseFloat(fieldStr.slice(0, -1));
    if (!isNaN(percentValue)) {
      return { type: 'percentage', value: percentValue };
    }
  }
  
  // Check for field expressions with multipliers (e.g., "1 week ago volume * 1.2")
  const exprPattern = /^(.+?)\s*([*\/])\s*([\d.]+)$/;
  const exprMatch = fieldStr.match(exprPattern);
  
  if (exprMatch) {
    const fieldPart = exprMatch[1].trim();
    const operator = exprMatch[2];
    const multiplier = parseFloat(exprMatch[3]);
    
    // Parse the field part recursively
    const parsedField = parseField(fieldPart);
    
    return {
      type: 'expression',
      field: parsedField,
      operator: operator,
      multiplier: multiplier
    };
  }
  
  // Check for time-based patterns (e.g., "1 day ago volume", "3 days ago rsi", "1 week ago high", "1 month ago close")
  const dayPattern = /^(\d+)\s+days?\s+ago\s+(.+)$/;
  const weekPattern = /^(\d+)\s+weeks?\s+ago\s+(.+)$/;
  const monthPattern = /^(\d+)\s+months?\s+ago\s+(.+)$/;
  
  let match = fieldStr.match(dayPattern);
  let timeUnit = 'day';
  
  if (!match) {
    match = fieldStr.match(weekPattern);
    if (match) {
      timeUnit = 'week';
    }
  }
  
  if (!match) {
    match = fieldStr.match(monthPattern);
    if (match) {
      timeUnit = 'month';
    }
  }
  
  if (match) {
    const unitsAgo = parseInt(match[1]);
    const fieldName = match[2];
    
    // For week-based and month-based queries, check if we need to use aggregation
    let field = null;
    let useWeeklyAggregation = false;
    let useMonthlyAggregation = false;
    const priceFields = ['open', 'high', 'low', 'close', 'volume'];
    
    if (timeUnit === 'week') {
      // Check if it's a price field that needs aggregation
      if (priceFields.includes(fieldName)) {
        field = fieldName;
        useWeeklyAggregation = true;
      } else {
        // For indicators, try to find the weekly version
        const weeklyMapping = {
          'rsi': 'rsi_weekly',
          'sma': 'sma_weekly',
          'ema': 'ema_weekly',
          'supertrend': 'supertrend_weekly',
          'super trend': 'supertrend_weekly',
          'upper bollinger band': 'bb_upper_weekly',
          'lower bollinger band': 'bb_lower_weekly',
          'percent change': 'pctchg_weekly',
          'pct change': 'pctchg_weekly',
          '% change': 'pctchg_weekly',
          'weekly volume': 'volume_weekly',
          'week volume': 'volume_weekly'
        };
        
        field = weeklyMapping[fieldName];
        if (!field) {
          // Try full indicator mappings
          for (const [pattern, key] of Object.entries(INDICATOR_MAPPINGS)) {
            if (fieldName.includes(pattern)) {
              // Check if there's a weekly version
              const weeklyKey = key.replace('_daily', '_weekly');
              if (key.includes('_daily')) {
                field = weeklyKey;
              } else {
                field = key;
              }
              break;
            }
          }
        }
      }
    } else if (timeUnit === 'month') {
      // For month-based queries
      if (priceFields.includes(fieldName)) {
        field = fieldName;
        useMonthlyAggregation = true;
      } else {
        // For indicators, we'll use the daily value from N months ago
        for (const [pattern, key] of Object.entries(INDICATOR_MAPPINGS)) {
          if (fieldName.includes(pattern)) {
            field = key;
            break;
          }
        }
        
        if (!field) {
          field = SIMPLE_FIELD_MAPPINGS[fieldName] || fieldName;
        }
      }
    } else {
      // For day-based queries, use normal field resolution
      for (const [pattern, key] of Object.entries(INDICATOR_MAPPINGS)) {
        if (fieldName.includes(pattern)) {
          field = key;
          break;
        }
      }
      
      if (!field) {
        field = SIMPLE_FIELD_MAPPINGS[fieldName] || fieldName;
      }
    }
    
    if (!field) {
      field = fieldName; // fallback to original field name
    }
    
    let daysAgo = unitsAgo;
    if (timeUnit === 'week') {
      daysAgo = unitsAgo * 7;
    } else if (timeUnit === 'month') {
      daysAgo = unitsAgo * 30; // Approximate month as 30 days
    }
    
    return { 
      type: 'field', 
      field: field,
      timeUnit: timeUnit,
      unitsAgo: unitsAgo,
      daysAgo: daysAgo,
      useWeeklyAggregation: useWeeklyAggregation,
      useMonthlyAggregation: useMonthlyAggregation
    };
  }
  
  // Try to find a matching indicator
  for (const [pattern, key] of Object.entries(INDICATOR_MAPPINGS)) {
    if (fieldStr.includes(pattern)) {
      return { type: 'field', field: key };
    }
  }
  
  // Check simple field mappings
  const simpleField = SIMPLE_FIELD_MAPPINGS[fieldStr];
  if (simpleField) {
    return { type: 'field', field: simpleField };
  }
  
  // If no match found, treat as field name directly
  return { type: 'field', field: fieldStr };
}

function parseQuery(query) {
  const normalizedQuery = normalizeQuery(query);
  const parts = extractConditions(normalizedQuery);
  
  const conditions = [];
  const logicalOperators = [];
  
  for (const part of parts) {
    if (part.type === 'condition') {
      try {
        const condition = parseCondition(part.value);
        conditions.push(condition);
      } catch (error) {
        throw new Error(`Failed to parse condition "${part.value}": ${error.message}`);
      }
    } else if (part.type === 'operator') {
      logicalOperators.push(part.value === 'and' || part.value === '&&' ? 'AND' : 'OR');
    }
  }
  
  return {
    conditions,
    logicalOperators,
    originalQuery: query
  };
}

function getFieldValue(candle, prevCandle, field, candles, currentIndex) {
  // Handle special case for previous close
  if (field === 'prev_close' && prevCandle) {
    return parseFloat(prevCandle.close);
  }
  
  const value = candle[field];
  if (value === null || value === undefined) {
    return null;
  }
  
  return parseFloat(value);
}

function getHistoricalFieldValue(candles, currentIndex, field, daysAgo) {
  const targetIndex = currentIndex - daysAgo;
  
  if (targetIndex < 0 || targetIndex >= candles.length) {
    return null;
  }
  
  const targetCandle = candles[targetIndex];
  const value = targetCandle[field];
  
  if (value === null || value === undefined) {
    return null;
  }
  
  return parseFloat(value);
}

function getWeeklyAggregatedValue(candles, currentIndex, field, weeksAgo) {
  const currentDate = new Date(Number(candles[currentIndex].date));
  const currentWeek = getISOWeek(currentDate);
  const currentYear = currentDate.getUTCFullYear();
  
  // Calculate target week and year
  let targetWeek = currentWeek - weeksAgo;
  let targetYear = currentYear;
  
  // Handle year boundary
  if (targetWeek <= 0) {
    targetYear--;
    // Get the number of weeks in the previous year
    const lastDayOfPrevYear = new Date(Date.UTC(targetYear, 11, 31));
    const lastWeekOfPrevYear = getISOWeek(lastDayOfPrevYear);
    targetWeek = lastWeekOfPrevYear + targetWeek;
  }
  
  // Find candles for the target week
  const weekCandles = [];
  for (let i = 0; i <= currentIndex; i++) {
    const candle = candles[i];
    const candleDate = new Date(Number(candle.date));
    const candleWeek = getISOWeek(candleDate);
    const candleYear = candleDate.getUTCFullYear();
    
    if (candleYear === targetYear && candleWeek === targetWeek) {
      weekCandles.push(candle);
    }
  }
  
  if (weekCandles.length === 0) {
    return null;
  }
  
  // Aggregate based on field type
  switch (field) {
    case 'high':
      return Math.max(...weekCandles.map(c => parseFloat(c.high)));
    case 'low':
      return Math.min(...weekCandles.map(c => parseFloat(c.low)));
    case 'open':
      return parseFloat(weekCandles[0].open); // First candle's open
    case 'close':
      return parseFloat(weekCandles[weekCandles.length - 1].close); // Last candle's close
    case 'volume':
      return weekCandles.reduce((sum, c) => sum + parseFloat(c.volume), 0);
    default:
      // For other fields, return the last value of the week
      return parseFloat(weekCandles[weekCandles.length - 1][field]);
  }
}

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

function getMonthlyAggregatedValue(candles, currentIndex, field, monthsAgo) {
  const currentDate = new Date(Number(candles[currentIndex].date));
  const currentMonth = currentDate.getUTCMonth();
  const currentYear = currentDate.getUTCFullYear();
  
  // Calculate target month and year
  let targetMonth = currentMonth - monthsAgo;
  let targetYear = currentYear;
  
  // Handle year boundaries
  while (targetMonth < 0) {
    targetMonth += 12;
    targetYear--;
  }
  
  // Find candles for the target month
  const monthCandles = [];
  for (let i = 0; i <= currentIndex; i++) {
    const candle = candles[i];
    const candleDate = new Date(Number(candle.date));
    const candleMonth = candleDate.getUTCMonth();
    const candleYear = candleDate.getUTCFullYear();
    
    if (candleYear === targetYear && candleMonth === targetMonth) {
      monthCandles.push(candle);
    }
  }
  
  if (monthCandles.length === 0) {
    return null;
  }
  
  // Aggregate based on field type
  switch (field) {
    case 'high':
      return Math.max(...monthCandles.map(c => parseFloat(c.high)));
    case 'low':
      return Math.min(...monthCandles.map(c => parseFloat(c.low)));
    case 'open':
      return parseFloat(monthCandles[0].open); // First candle's open
    case 'close':
      return parseFloat(monthCandles[monthCandles.length - 1].close); // Last candle's close
    case 'volume':
      return monthCandles.reduce((sum, c) => sum + parseFloat(c.volume), 0);
    default:
      // For other fields, return the last value of the month
      return parseFloat(monthCandles[monthCandles.length - 1][field]);
  }
}

function evaluateExpression(expr, candle, prevCandle, candles, currentIndex) {
  if (expr.type === 'expression') {
    // Get the base field value
    const baseValue = evaluateExpression(expr.field, candle, prevCandle, candles, currentIndex);
    if (baseValue === null) return null;
    
    // Apply the operator
    if (expr.operator === '*') {
      return baseValue * expr.multiplier;
    } else if (expr.operator === '/') {
      return baseValue / expr.multiplier;
    }
  } else if (expr.type === 'field') {
    if (expr.timeUnit === 'week' && expr.unitsAgo > 0) {
      // For week-based queries
      if (expr.useWeeklyAggregation) {
        // Aggregate price fields over the week
        return getWeeklyAggregatedValue(candles, currentIndex, expr.field, expr.unitsAgo);
      } else {
        // Use weekly indicator values from N weeks ago
        return getHistoricalFieldValue(candles, currentIndex, expr.field, expr.daysAgo);
      }
    } else if (expr.timeUnit === 'month' && expr.unitsAgo > 0) {
      // For month-based queries
      if (expr.useMonthlyAggregation) {
        // Aggregate price fields over the month
        return getMonthlyAggregatedValue(candles, currentIndex, expr.field, expr.unitsAgo);
      } else {
        // Use indicator values from N months ago (approximated as 30 days)
        return getHistoricalFieldValue(candles, currentIndex, expr.field, expr.daysAgo);
      }
    } else if (expr.daysAgo) {
      // For day-based historical queries
      return getHistoricalFieldValue(candles, currentIndex, expr.field, expr.daysAgo);
    } else {
      // Current value
      return getFieldValue(candle, prevCandle, expr.field, candles, currentIndex);
    }
  } else if (expr.type === 'value') {
    return expr.value;
  } else if (expr.type === 'percentage') {
    return expr.value;
  }
  
  return null;
}

function evaluateCondition(condition, candle, prevCandle, candles, currentIndex) {
  // Get left value
  const leftValue = evaluateExpression(condition.left, candle, prevCandle, candles, currentIndex);
  if (leftValue === null) return false;
  
  // Get right value
  const rightValue = evaluateExpression(condition.right, candle, prevCandle, candles, currentIndex);
  if (rightValue === null) return false;
  
  // Apply the comparison
  return condition.compareFn(leftValue, rightValue);
}

function evaluateAllConditions(parsedQuery, candle, prevCandle, candles, currentIndex) {
  const { conditions, logicalOperators } = parsedQuery;
  
  if (conditions.length === 0) return false;
  
  // Evaluate first condition
  let result = evaluateCondition(conditions[0], candle, prevCandle, candles, currentIndex);
  
  // Apply logical operators for remaining conditions
  for (let i = 1; i < conditions.length; i++) {
    const conditionResult = evaluateCondition(conditions[i], candle, prevCandle, candles, currentIndex);
    const operator = logicalOperators[i - 1];
    
    if (operator === 'AND') {
      result = result && conditionResult;
    } else if (operator === 'OR') {
      result = result || conditionResult;
    }
  }
  
  return result;
}

function findMatchingCandles(candles, parsedQuery, stockSymbol = 'UNKNOWN') {
  const matches = [];
  
  const startIdx = Math.max(1, getDataAvailabilityIndex(candles, parsedQuery));
  
  for (let i = startIdx; i < candles.length; i++) {
    const candle = candles[i];
    const prevCandle = candles[i - 1];
    
    if (!candle.close) continue;
    
    try {
      if (evaluateAllConditions(parsedQuery, candle, prevCandle, candles, i)) {
        matches.push({
          date: candle.date,
          day: candle.day,
          timestamp: new Date(parseInt(candle.date)).toISOString(),
          stock: stockSymbol,
          close: candle.close,
          matchedConditions: parsedQuery.originalQuery
        });
      }
    } catch (error) {
      console.error(`Error evaluating candle at index ${i}:`, error.message);
    }
  }
  
  return matches;
}

function getDataAvailabilityIndex(candles, parsedQuery) {
  const requiredFields = new Set();
  let maxDaysAgo = 0;
  
  function extractFieldInfo(expr) {
    if (expr.type === 'expression' && expr.field) {
      extractFieldInfo(expr.field);
    } else if (expr.type === 'field') {
      if (expr.field !== 'prev_close') {
        requiredFields.add(expr.field);
      }
      if (expr.daysAgo) {
        maxDaysAgo = Math.max(maxDaysAgo, expr.daysAgo);
      }
    }
  }
  
  for (const condition of parsedQuery.conditions) {
    extractFieldInfo(condition.left);
    extractFieldInfo(condition.right);
  }
  
  // Find first index where all fields have non-null values
  for (let i = maxDaysAgo; i < candles.length; i++) {
    const candle = candles[i];
    let allAvailable = true;
    
    for (const field of requiredFields) {
      if (candle[field] === null || candle[field] === undefined) {
        allAvailable = false;
        break;
      }
    }
    
    if (allAvailable) {
      return i;
    }
  }
  
  return candles.length; // No valid data found
}

const getQueryExamples = () => ({
  examples: [
    {
      query: "daily upper bollinger band > daily close",
      description: "Find stocks where price is below upper Bollinger Band"
    },
    {
      query: "weekly rsi > 60 and close > weekly sma",
      description: "Find stocks with weekly RSI above 60 and price above weekly SMA"
    },
    {
      query: "current close > yesterday's close and daily rsi < 30",
      description: "Find stocks that closed higher than previous day with oversold RSI"
    },
    {
      query: "daily percent change > 5 and volume > 1000000",
      description: "Find stocks with 5% daily gain and high volume"
    },
    {
      query: "1 day ago volume > 100000 and volume > 200000",
      description: "Find stocks where volume increased from yesterday"
    },
    {
      query: "3 days ago rsi < 30 and rsi > 50",
      description: "Find stocks that recovered from oversold in 3 days"
    },
    {
      query: "5 days ago close < 100 and close > 110",
      description: "Find stocks that gained 10% in 5 days"
    },
    {
      query: "1 day ago volume > 1 week ago volume * 1.2",
      description: "Find stocks where yesterday's volume was 20% higher than a week ago"
    },
    {
      query: "1 day ago supertrend > weekly supertrend",
      description: "Find stocks where yesterday's supertrend is above weekly supertrend"
    },
    {
      query: "close > sma * 1.05 and rsi < 70",
      description: "Find stocks trading 5% above SMA with RSI below 70"
    },
    {
      query: "1 week ago high < close",
      description: "Find stocks that closed above last week's high"
    },
    {
      query: "volume * 1.5 > 1 week ago volume",
      description: "Find stocks where today's volume is 50% higher than last week's total"
    },
    {
      query: "1 month ago low > close",
      description: "Find stocks trading below last month's low"
    },
    {
      query: "2 * 1 month ago volume < volume",
      description: "Find stocks where current volume is double the monthly volume from a month ago"
    }
  ],
  availableIndicators: {
    daily: [
      "daily upper bollinger band (bb_upper_daily)",
      "daily lower bollinger band (bb_lower_daily)",
      "daily sma (sma_daily)",
      "daily ema (ema_daily)",
      "daily rsi (rsi_daily)",
      "daily supertrend (supertrend_daily)",
      "daily percent change (pctchg_daily)"
    ],
    weekly: [
      "weekly upper bollinger band (bb_upper_weekly)",
      "weekly lower bollinger band (bb_lower_weekly)",
      "weekly sma (sma_weekly)",
      "weekly ema (ema_weekly)",
      "weekly rsi (rsi_weekly)",
      "weekly supertrend (supertrend_weekly)",
      "weekly percent change (pctchg_weekly)",
      "weekly volume (volume_weekly)"
    ],
    price: [
      "close",
      "open",
      "high",
      "low",
      "volume",
      "current close",
      "yesterday's close"
    ],
    timeBased: [
      "n days/weeks/months ago <indicator>",
      "Examples: '1 day ago volume', '3 days ago rsi', '1 week ago high', '1 month ago close'",
      "For week/month ago with price fields (high/low/close/volume), values are aggregated over the entire period"
    ]
  },
  operators: [">", "<", ">=", "<=", "=", "==", "!="],
  logicalOperators: ["and", "or"]
});

module.exports = {
  parseQuery,
  findMatchingCandles,
  getQueryExamples
};