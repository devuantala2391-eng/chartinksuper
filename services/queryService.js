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
  const numValue = parseFloat(fieldStr);
  if (!isNaN(numValue)) {
    return { type: 'value', value: numValue };
  }
  
  if (fieldStr.endsWith('%')) {
    const percentValue = parseFloat(fieldStr.slice(0, -1));
    if (!isNaN(percentValue)) {
      return { type: 'percentage', value: percentValue };
    }
  }
  
  for (const [pattern, key] of Object.entries(INDICATOR_MAPPINGS)) {
    if (fieldStr.includes(pattern)) {
      return { type: 'field', field: key };
    }
  }
  
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

function getFieldValue(candle, prevCandle, field) {
  if (field === 'prev_close' && prevCandle) {
    return parseFloat(prevCandle.close);
  }
  
  const value = candle[field];
  if (value === null || value === undefined) {
    return null;
  }
  
  return parseFloat(value);
}

function evaluateCondition(condition, candle, prevCandle) {
  let leftValue;
  if (condition.left.type === 'field') {
    leftValue = getFieldValue(candle, prevCandle, condition.left.field);
    if (leftValue === null) return false;
  } else if (condition.left.type === 'value') {
    leftValue = condition.left.value;
  } else if (condition.left.type === 'percentage') {
    leftValue = condition.left.value;
  }
  
  let rightValue;
  if (condition.right.type === 'field') {
    rightValue = getFieldValue(candle, prevCandle, condition.right.field);
    if (rightValue === null) return false;
  } else if (condition.right.type === 'value') {
    rightValue = condition.right.value;
  } else if (condition.right.type === 'percentage') {
    rightValue = condition.right.value;
  }
  
  return condition.compareFn(leftValue, rightValue);
}

function evaluateAllConditions(parsedQuery, candle, prevCandle) {
  const { conditions, logicalOperators } = parsedQuery;
  
  if (conditions.length === 0) return false;
  
  let result = evaluateCondition(conditions[0], candle, prevCandle);
  
  for (let i = 1; i < conditions.length; i++) {
    const conditionResult = evaluateCondition(conditions[i], candle, prevCandle);
    const operator = logicalOperators[i - 1];
    
    if (operator === 'AND') {
      result = result && conditionResult;
    } else if (operator === 'OR') {
      result = result || conditionResult;
    }
  }
  
  return result;
}

function getDataAvailabilityIndex(candles, parsedQuery) {
  const requiredFields = new Set();
  
  for (const condition of parsedQuery.conditions) {
    if (condition.left.type === 'field' && condition.left.field !== 'prev_close') {
      requiredFields.add(condition.left.field);
    }
    if (condition.right.type === 'field' && condition.right.field !== 'prev_close') {
      requiredFields.add(condition.right.field);
    }
  }
  
  for (let i = 0; i < candles.length; i++) {
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
  
  return candles.length;
}

function findMatchingCandles(candles, parsedQuery, stockSymbol = 'UNKNOWN') {
  const matches = [];
  
  const startIdx = Math.max(1, getDataAvailabilityIndex(candles, parsedQuery));
  
  for (let i = startIdx; i < candles.length; i++) {
    const candle = candles[i];
    const prevCandle = candles[i - 1];
    
    if (!candle.close) continue;
    
    try {
      if (evaluateAllConditions(parsedQuery, candle, prevCandle)) {
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
      query: "weekly supertrend < close and daily ema > daily sma",
      description: "Find stocks in weekly uptrend with daily EMA above SMA"
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
      "weekly percent change (pctchg_weekly)"
    ],
    price: [
      "close",
      "open",
      "high",
      "low",
      "volume",
      "current close",
      "yesterday's close"
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