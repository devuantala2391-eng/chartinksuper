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
  
  // Price fields
  'daily close': 'close',
  'close': 'close',
  'open': 'open',
  'high': 'high',
  'low': 'low',
  'volume': 'volume',
  
  // Volume fields
  'weekly volume': 'volume_weekly',
  
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
  
  // Check for time-based patterns (e.g., "1 day ago volume", "3 days ago rsi")
  const timePattern = /^(\d+)\s+days?\s+ago\s+(.+)$/;
  const match = fieldStr.match(timePattern);
  
  if (match) {
    const daysAgo = parseInt(match[1]);
    const fieldName = match[2];
    
    // Try to find the field in indicator mappings
    let field = null;
    
    // Check full indicator mappings first
    for (const [pattern, key] of Object.entries(INDICATOR_MAPPINGS)) {
      if (fieldName.includes(pattern)) {
        field = key;
        break;
      }
    }
    
    // If not found, check simple field mappings
    if (!field) {
      field = SIMPLE_FIELD_MAPPINGS[fieldName] || fieldName;
    }
    
    return { 
      type: 'field', 
      field: field,
      daysAgo: daysAgo
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

function evaluateCondition(condition, candle, prevCandle, candles, currentIndex) {
  // Get left value
  let leftValue;
  if (condition.left.type === 'field') {
    if (condition.left.daysAgo) {
      leftValue = getHistoricalFieldValue(candles, currentIndex, condition.left.field, condition.left.daysAgo);
    } else {
      leftValue = getFieldValue(candle, prevCandle, condition.left.field, candles, currentIndex);
    }
    if (leftValue === null) return false;
  } else if (condition.left.type === 'value') {
    leftValue = condition.left.value;
  } else if (condition.left.type === 'percentage') {
    leftValue = condition.left.value;
  }
  
  // Get right value
  let rightValue;
  if (condition.right.type === 'field') {
    if (condition.right.daysAgo) {
      rightValue = getHistoricalFieldValue(candles, currentIndex, condition.right.field, condition.right.daysAgo);
    } else {
      rightValue = getFieldValue(candle, prevCandle, condition.right.field, candles, currentIndex);
    }
    if (rightValue === null) return false;
  } else if (condition.right.type === 'value') {
    rightValue = condition.right.value;
  } else if (condition.right.type === 'percentage') {
    rightValue = condition.right.value;
  }
  
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
  
  for (const condition of parsedQuery.conditions) {
    if (condition.left.type === 'field') {
      if (condition.left.field !== 'prev_close') {
        requiredFields.add(condition.left.field);
      }
      if (condition.left.daysAgo) {
        maxDaysAgo = Math.max(maxDaysAgo, condition.left.daysAgo);
      }
    }
    if (condition.right.type === 'field') {
      if (condition.right.field !== 'prev_close') {
        requiredFields.add(condition.right.field);
      }
      if (condition.right.daysAgo) {
        maxDaysAgo = Math.max(maxDaysAgo, condition.right.daysAgo);
      }
    }
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
      "n days ago <indicator>",
      "Examples: '1 day ago volume', '3 days ago rsi', '5 days ago close'"
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