// services/queryService.js

const { calculateAllIndicators, calculateAllIndicatorsWithTimeframes } = require('./indicatorCalculator');
const { isCached, markAsCached } = require('./indicatorCache');
const { sanitizeCandleArray, sanitizeNumericValue } = require('./dataUtils');
const fs = require('fs');
const path = require('path');

const INDICATOR_MAPPINGS = {
  // Bollinger Bands
  'daily upper bollinger band': 'bb_upper_daily',
  'daily lower bollinger band': 'bb_lower_daily',
  'daily middle bollinger band': 'bb_middle_daily',
  'weekly upper bollinger band': 'bb_upper_weekly',
  'weekly lower bollinger band': 'bb_lower_weekly',
  'weekly middle bollinger band': 'bb_middle_weekly',
  'monthly upper bollinger band': 'bb_upper_monthly',
  'monthly lower bollinger band': 'bb_lower_monthly',
  'monthly middle bollinger band': 'bb_middle_monthly',
  'daily bb upper': 'bb_upper_daily',
  'daily bb lower': 'bb_lower_daily',
  'daily bb middle': 'bb_middle_daily',
  'weekly bb upper': 'bb_upper_weekly',
  'weekly bb lower': 'bb_lower_weekly',
  'weekly bb middle': 'bb_middle_weekly',
  'monthly bb upper': 'bb_upper_monthly',
  'monthly bb lower': 'bb_lower_monthly',
  'monthly bb middle': 'bb_middle_monthly',
  
  // MACD components
  'daily macd line': 'macd_daily',
  'weekly macd line': 'macd_weekly',
  'monthly macd line': 'macd_monthly',
  'daily macd signal': 'macd_signal_daily',
  'weekly macd signal': 'macd_signal_weekly',
  'monthly macd signal': 'macd_signal_monthly',
  'daily macd histogram': 'macd_histogram_daily',
  'weekly macd histogram': 'macd_histogram_weekly',
  'monthly macd histogram': 'macd_histogram_monthly',
  
  // Stochastic components
  'daily stochastic k': 'stoch_k_daily',
  'weekly stochastic k': 'stoch_k_weekly',
  'monthly stochastic k': 'stoch_k_monthly',
  'daily stochastic d': 'stoch_d_daily',
  'weekly stochastic d': 'stoch_d_weekly',
  'monthly stochastic d': 'stoch_d_monthly',
  
  // SMA
  'daily sma': 'sma_daily',
  'weekly sma': 'sma_weekly',
  'monthly sma': 'sma_monthly',
  
  // EMA
  'daily ema': 'ema_daily',
  'weekly ema': 'ema_weekly',
  'monthly ema': 'ema_monthly',
  
  // RSI
  'daily rsi': 'rsi_daily',
  'weekly rsi': 'rsi_weekly',
  'monthly rsi': 'rsi_monthly',
  
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
  'daily volume': 'volume',
  'weekly volume': 'volume_weekly',
  'week volume': 'volume_weekly',
  'monthly volume': 'volume_monthly',
  'month volume': 'volume_monthly',
  
  // Volume fields with underscores
  'daily_volume': 'volume',
  'weekly_volume': 'weekly_volume',
  'monthly_volume': 'monthly_volume',
  
  // Percent change
  'daily percent change': 'pctchg_daily',
  'weekly percent change': 'pctchg_weekly',
  'daily pct change': 'pctchg_daily',
  'weekly pct change': 'pctchg_weekly',
  'daily % change': 'pctchg_daily',
  'weekly % change': 'pctchg_weekly',
  
  // Special cases
  'current close': 'close',
  'yesterday\'s close': 'prev_close',
  'previous close': 'prev_close',
  'yesterdays close': 'prev_close',
  
  // Week volume mappings
  'current week volume': 'current_week_volume',
  'previous week volume': 'previous_week_volume',
  'last week volume': 'previous_week_volume',
  'weekly volume': 'weekly_volume',
  
  // Month volume mappings
  'current month volume': 'current_month_volume',
  'previous month volume': 'previous_month_volume',
  'last month volume': 'previous_month_volume',
  'monthly volume': 'monthly_volume',
  
  // Weekly price fields
  'weekly open': 'open_weekly',
  'weekly high': 'high_weekly',
  'weekly low': 'low_weekly',
  'weekly close': 'close_weekly',
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
  'bb': 'bb_daily',
  'bollinger': 'bb_daily',
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
  'crossed above': 'crossed_above', // Special operator, handled separately
  'crossed below': 'crossed_below', // Special operator, handled separately
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
  
  const result = {
    left: leftField,
    operator: operator,
    right: rightField
  };
  
  // Only add compareFn for regular operators, not crossed above/below
  if (typeof OPERATORS[operator] === 'function') {
    result.compareFn = OPERATORS[operator];
  }
  
  return result;
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
  
  // Check for new dynamic key format with component support (e.g., "daily_bb_upper_20_2", "weekly_macd_signal_12_26_9")
  const dynamicKeyPattern = /^(daily|weekly|monthly)_([a-zA-Z]+)_(.+)$/;
  const dynamicKeyMatch = fieldStr.match(dynamicKeyPattern);
  
  // Check for component-based indicators (e.g., "daily_bb_upper_20_2")
  const componentPattern = /^(daily|weekly|monthly)_([a-zA-Z]+)_(upper|lower|middle|macd|signal|histogram|k|d)_(.+)$/;
  const componentMatch = fieldStr.match(componentPattern);
  
  if (componentMatch) {
    const timeframe = componentMatch[1];
    const indicatorName = componentMatch[2];
    const component = componentMatch[3];
    const paramsStr = componentMatch[4];
    const params = paramsStr.split('_');
    
    return {
      type: 'dynamic_indicator',
      timeframe: timeframe,
      name: indicatorName,
      component: component,
      params: params,
      fieldKey: fieldStr,
      originalString: fieldStr
    };
  } else if (dynamicKeyMatch) {
    const timeframe = dynamicKeyMatch[1];
    const indicatorName = dynamicKeyMatch[2];
    const paramsStr = dynamicKeyMatch[3];
    const params = paramsStr.split('_');
    
    return {
      type: 'dynamic_indicator',
      timeframe: timeframe,
      name: indicatorName,
      params: params,
      fieldKey: fieldStr,
      originalString: fieldStr
    };
  }
  
  // Check for complex expressions with avg and arithmetic (e.g., "avg(...) + 10")
  const complexExprPattern = /^(avg\s*\([^)]+\))\s*([+\-*\/])\s*(\d+(?:\.\d+)?)$/;
  const complexExprMatch = fieldStr.match(complexExprPattern);
  
  if (complexExprMatch) {
    const avgPart = complexExprMatch[1];
    const operator = complexExprMatch[2];
    const rightValue = parseFloat(complexExprMatch[3]);
    
    const avgParsed = parseField(avgPart);
    return {
      type: 'arithmetic_expression',
      leftOperand: avgParsed,
      operator: operator,
      rightOperand: { type: 'value', value: rightValue },
      originalString: fieldStr
    };
  }
  
  // Check for avg function FIRST (e.g., "avg(daily_rsi_14, weekly_rsi_14, monthly_rsi_20)")
  const avgPattern = /^avg\s*\(([^)]+)\)$/;
  const avgMatch = fieldStr.match(avgPattern);
  
  if (avgMatch) {
    const operandsStr = avgMatch[1];
    const operands = operandsStr.split(',').map(op => op.trim()).map(op => parseField(op));
    
    return {
      type: 'avg_function',
      operands: operands,
      originalString: fieldStr
    };
  }
  
  // Check for indicator with parameters (e.g., "rsi(14)", "sma(20)", "bb(20, 2)")
  // But skip if it's "avg" which is handled above
  // Also handle "daily upper bollinger band(20,2)" style
  let timeframePrefix = null;
  let indicatorPattern = /^(?:(daily|weekly|monthly)\s+)?(?:upper\s+|lower\s+)?(bollinger\s+band|supertrend|super\s+trend|rsi|sma|ema|bb)\(([^)]+)\)$/i;
  let indicatorMatch = fieldStr.match(indicatorPattern);
  
  if (indicatorMatch) {
    timeframePrefix = indicatorMatch[1] || null;
    // Shift matches if timeframe was captured
    if (timeframePrefix) {
      indicatorMatch = [indicatorMatch[0], indicatorMatch[2], indicatorMatch[3]];
    }
  } else {
    // Try simpler pattern
    indicatorPattern = /^([a-zA-Z]+)\(([^)]+)\)$/;
    indicatorMatch = fieldStr.match(indicatorPattern);
  }
  
  if (indicatorMatch && indicatorMatch[1].toLowerCase() !== 'avg') {
    let indicatorName = indicatorMatch[1].toLowerCase();
    const params = indicatorMatch[2].split(',').map(p => p.trim());
    
    // Normalize indicator names
    if (indicatorName.includes('bollinger') || indicatorName === 'bb') {
      indicatorName = 'bb';
    } else if (indicatorName.includes('supertrend') || indicatorName.includes('super trend')) {
      indicatorName = 'supertrend';
    }
    
    const result = {
      type: 'indicator',
      name: indicatorName,
      params: params,
      originalString: fieldStr
    };
    
    if (timeframePrefix) {
      result.timeframe = timeframePrefix;
    }
    
    return result;
  }
  
  // First try to find exact matching indicator - check field mappings before generic patterns
  for (const [pattern, key] of Object.entries(INDICATOR_MAPPINGS)) {
    if (fieldStr === pattern) {
      return { type: 'field', field: key };
    }
  }
  
  // Check for bollinger band variations without parameters
  if (fieldStr.includes('bollinger band')) {
    // Default bollinger band parameters
    return {
      type: 'indicator',
      name: 'bb',
      params: ['20', '2'],
      originalString: fieldStr
    };
  }
  
  // Check for supertrend without parameters
  if (fieldStr === 'supertrend' || fieldStr === 'super trend') {
    return {
      type: 'indicator',
      name: 'supertrend',
      params: ['10', '3'],
      originalString: fieldStr
    };
  }
  
  // Check for arithmetic expressions with operators (e.g., "(daily_rsi_14 + weekly_rsi_14)")
  const arithPattern = /^\((.+?)\s*([+\-*\/])\s*(.+?)\)$/;
  const arithMatch = fieldStr.match(arithPattern);
  
  if (arithMatch) {
    const leftOperand = parseField(arithMatch[1].trim());
    const operator = arithMatch[2];
    const rightOperand = parseField(arithMatch[3].trim());
    
    return {
      type: 'arithmetic_expression',
      leftOperand: leftOperand,
      operator: operator,
      rightOperand: rightOperand,
      originalString: fieldStr
    };
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
  
  // Check for time-based patterns with indicators (e.g., "1 day ago rsi(14)", "3 days ago sma(20)")
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
    
    // Check if fieldName is an indicator with parameters
    const indicatorMatch = fieldName.match(/^([a-zA-Z]+)\(([^)]+)\)$/);
    if (indicatorMatch) {
      const indicatorName = indicatorMatch[1].toLowerCase();
      const params = indicatorMatch[2].split(',').map(p => p.trim());
      
      let daysAgo = unitsAgo;
      if (timeUnit === 'week') {
        daysAgo = unitsAgo * 7;
      } else if (timeUnit === 'month') {
        daysAgo = unitsAgo * 30;
      }
      
      return {
        type: 'indicator',
        name: indicatorName,
        params: params,
        originalString: fieldName,
        timeUnit: timeUnit,
        unitsAgo: unitsAgo,
        daysAgo: daysAgo
      };
    }
    
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
  
  // Try to find a matching indicator - first check exact matches, then partial matches
  for (const [pattern, key] of Object.entries(INDICATOR_MAPPINGS)) {
    if (fieldStr === pattern) {
      return { type: 'field', field: key };
    }
  }
  
  // Then check partial matches (for patterns like "daily rsi" in "daily rsi(14)")
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

// Extract indicators from parsed query
function extractIndicatorsFromQuery(parsedQuery) {
  const indicators = new Set();
  const timeframes = new Set(['daily']); // Always include daily
  
  function extractFromField(field) {
    if (field.type === 'dynamic_indicator') {
      // Handle new dynamic indicator format
      const period = parseInt(field.params[0]) || getDefaultPeriod(field.name);
      const params = {};
      
      // Add the timeframe
      timeframes.add(field.timeframe);
      
      // Parse additional parameters based on indicator type
      if (field.name === 'bb' || field.name === 'bollinger') {
        params.stdDev = field.params[1] ? parseFloat(field.params[1]) : 2;
      } else if (field.name === 'supertrend') {
        params.multiplier = field.params[1] ? parseFloat(field.params[1]) : 3;
      } else if (field.name === 'macd') {
        params.fast = field.params[0] ? parseInt(field.params[0]) : 12;
        params.slow = field.params[1] ? parseInt(field.params[1]) : 26;
        params.signal = field.params[2] ? parseInt(field.params[2]) : 9;
      } else if (field.name === 'stochastic') {
        params.k = field.params[0] ? parseInt(field.params[0]) : 14;
        params.d = field.params[1] ? parseInt(field.params[1]) : 3;
      }
      
      // Include component information in the indicator
      const indicatorDef = {
        name: field.name,
        period: period,
        params: params
      };
      
      // Add component if specified
      if (field.component) {
        indicatorDef.component = field.component;
      }
      
      indicators.add(JSON.stringify(indicatorDef));
    } else if (field.type === 'indicator') {
      const period = parseInt(field.params[0]) || getDefaultPeriod(field.name);
      const params = {};
      
      // Parse additional parameters based on indicator type
      if (field.name === 'bb' || field.name === 'bollinger') {
        params.stdDev = field.params[1] ? parseFloat(field.params[1]) : 2;
      } else if (field.name === 'supertrend') {
        params.multiplier = field.params[1] ? parseFloat(field.params[1]) : 3;
      } else if (field.name === 'macd') {
        params.fast = field.params[0] ? parseInt(field.params[0]) : 12;
        params.slow = field.params[1] ? parseInt(field.params[1]) : 26;
        params.signal = field.params[2] ? parseInt(field.params[2]) : 9;
      } else if (field.name === 'stochastic') {
        params.k = field.params[0] ? parseInt(field.params[0]) : 14;
        params.d = field.params[1] ? parseInt(field.params[1]) : 3;
      }
      
      // Add timeframe if specified
      if (field.timeframe) {
        timeframes.add(field.timeframe);
      }
      
      indicators.add(JSON.stringify({
        name: field.name,
        period: period,
        params: params
      }));
    } else if (field.type === 'field') {
      // Handle special fields that need indicator calculation
      if (field.field === 'pctchg_daily') {
        indicators.add(JSON.stringify({
          name: 'pctchg',
          period: 1,
          params: {}
        }));
      } else if (field.field === 'pctchg_weekly') {
        indicators.add(JSON.stringify({
          name: 'pctchg',
          period: 5,
          params: {}
        }));
        timeframes.add('weekly');
      } else if (field.field === 'bb_upper_daily' || field.field === 'bb_lower_daily' || field.field === 'bb_middle_daily') {
        indicators.add(JSON.stringify({
          name: 'bb',
          period: 20,
          params: { stdDev: 2 }
        }));
      } else if (field.field === 'bb_upper_weekly' || field.field === 'bb_lower_weekly' || field.field === 'bb_middle_weekly') {
        indicators.add(JSON.stringify({
          name: 'bb',
          period: 20,
          params: { stdDev: 2 }
        }));
        timeframes.add('weekly');
      } else if (field.field === 'bb_upper_monthly' || field.field === 'bb_lower_monthly' || field.field === 'bb_middle_monthly') {
        indicators.add(JSON.stringify({
          name: 'bb',
          period: 20,
          params: { stdDev: 2 }
        }));
        timeframes.add('monthly');
      } else if (field.field === 'supertrend_daily') {
        indicators.add(JSON.stringify({
          name: 'supertrend',
          period: 10,
          params: { multiplier: 3 }
        }));
      } else if (field.field === 'supertrend_weekly') {
        indicators.add(JSON.stringify({
          name: 'supertrend',
          period: 10,
          params: { multiplier: 3 }
        }));
        timeframes.add('weekly');
      } else if (field.field === 'weekly_volume') {
        indicators.add(JSON.stringify({
          name: 'volume',
          period: 1,
          params: {}
        }));
        timeframes.add('weekly');
      } else if (field.field === 'monthly_volume') {
        indicators.add(JSON.stringify({
          name: 'volume',
          period: 1,
          params: {}
        }));
        timeframes.add('monthly');
      } else {
        // Add basic field as an indicator to ensure it gets processed
        indicators.add(JSON.stringify({
          name: field.field,
          period: 1,
          params: {}
        }));
      }
    } else if (field.type === 'expression') {
      // Handle time-based expressions like "1 day ago volume"
      if (field.daysAgo || field.weeksAgo || field.monthsAgo) {
        indicators.add(JSON.stringify({
          name: field.field,
          period: 1,
          params: {
            daysAgo: field.daysAgo,
            weeksAgo: field.weeksAgo,
            monthsAgo: field.monthsAgo,
            timeUnit: field.timeUnit
          }
        }));
      }
      if (field.field) {
        extractFromField(field.field);
      }
    } else if (field.type === 'avg_function') {
      // Extract indicators from avg function operands
      if (field.operands) {
        field.operands.forEach(operand => extractFromField(operand));
      }
    } else if (field.type === 'arithmetic_expression') {
      // Extract indicators from arithmetic expression operands
      if (field.leftOperand) extractFromField(field.leftOperand);
      if (field.rightOperand) extractFromField(field.rightOperand);
    }
  }
  
  for (const condition of parsedQuery.conditions) {
    extractFromField(condition.left);
    extractFromField(condition.right);
  }
  
  // Always ensure basic calculations are included
  // This ensures mapperStorage is always generated for any query
  if (indicators.size === 0) {
    indicators.add(JSON.stringify({
      name: 'volume',
      period: 1,
      params: {}
    }));
  }
  
  // If we need weekly timeframe, ensure volume is included for weekly volume aggregation
  if (timeframes.has('weekly') && !Array.from(indicators).some(ind => JSON.parse(ind).name === 'volume')) {
    indicators.add(JSON.stringify({
      name: 'volume',
      period: 1,
      params: {}
    }));
  }
  
  return {
    indicators: Array.from(indicators).map(ind => JSON.parse(ind)),
    timeframes: Array.from(timeframes)
  };
}

// Get default period for indicators
function getDefaultPeriod(indicatorName) {
  const defaults = {
    'rsi': 14,
    'sma': 20,
    'ema': 20,
    'bb': 20,
    'bollinger': 20,
    'supertrend': 10,
    'macd': 12,
    'stochastic': 14,
    'williamsr': 14,
    'pctchg': 1,
    'percent_change': 1,
    'pct_change': 1,
    '%_change': 1
  };
  
  return defaults[indicatorName] || 14;
}

// Generate mapped field name for indicators
function generateIndicatorFieldName(indicator) {
  const { name, period, params } = indicator;
  
  switch (name) {
    case 'bb':
    case 'bollinger':
      return {
        upper: `bb_upper_${period}_${params.stdDev}`,
        middle: `bb_middle_${period}_${params.stdDev}`,
        lower: `bb_lower_${period}_${params.stdDev}`
      };
    case 'supertrend':
      return `supertrend_${period}_${params.multiplier}`;
    case 'macd':
      return {
        macd: `macd_${params.fast}_${params.slow}_${params.signal}`,
        signal: `macd_signal_${params.fast}_${params.slow}_${params.signal}`,
        histogram: `macd_histogram_${params.fast}_${params.slow}_${params.signal}`
      };
    case 'stochastic':
      return {
        k: `stoch_k_${params.k}_${params.d}`,
        d: `stoch_d_${params.k}_${params.d}`
      };
    default:
      return `${name}_${period}`;
  }
}

// Process all stocks and store in memory (NEW - replaces file-based storage)
async function processStocksWithIndicatorsInMemory(indicatorsData, stockList = null) {
  // Handle both old format (array) and new format (object with indicators and timeframes)
  let indicators, timeframes;
  if (Array.isArray(indicatorsData)) {
    // Old format - backward compatibility
    indicators = indicatorsData;
    timeframes = ['daily'];
  } else {
    // New format with timeframes
    indicators = indicatorsData.indicators;
    timeframes = indicatorsData.timeframes || ['daily'];
  }
  
  // Helper function to send progress updates
  const sendProgressUpdate = (processed, total, message) => {
    if (global.updateProgress) {
      global.updateProgress({ 
        phase: 'processing_indicators',
        processed, 
        total, 
        message 
      });
    }
  };
  
  const dbPath = path.join(__dirname, '..', 'db');
  
  // Get stock files to process
  let stockFiles;
  if (stockList && stockList.length > 0) {
    // Process only specified stocks
    stockFiles = stockList.map(symbol => `${symbol}.json`).filter(file => 
      fs.existsSync(path.join(dbPath, file))
    );
    console.log(`Processing ${stockFiles.length} specified stocks in memory`);
  } else {
    // Process all stocks
    stockFiles = fs.readdirSync(dbPath).filter(file => file.endsWith('.json'));
  }
  
  console.log(`Processing ${stockFiles.length} stocks with indicators:`, indicators.map(i => `${i.name}(${i.period})`));
  console.log(`Using timeframes:`, timeframes);
  console.log(`Using timeframes:`, timeframes);
  
  const processedCount = { success: 0, failed: 0 };
  const batchSize = 50; // Process 50 stocks at a time
  
  // Send initial progress
  sendProgressUpdate(0, stockFiles.length, 'Starting indicator processing...');
  
  // Process in batches for better performance
  for (let i = 0; i < stockFiles.length; i += batchSize) {
    const batch = stockFiles.slice(i, i + batchSize);
    
    await Promise.all(batch.map(async (stockFile) => {
      try {
        const stockSymbol = stockFile.replace('.json', '');
        const stockData = JSON.parse(fs.readFileSync(path.join(dbPath, stockFile), 'utf8'));
        
        if (!stockData.data || stockData.data.length === 0) {
          console.warn(`No data found for ${stockSymbol}`);
          processedCount.failed++;
          return;
        }
        
        // Sanitize the candle data to handle infinity values
        const sanitizedCandles = sanitizeCandleArray(stockData.data);
        
        // Calculate indicators with timeframe support
        const processedCandles = calculateAllIndicatorsWithTimeframes(sanitizedCandles, indicators, timeframes);
        
        // Store in memory instead of file
        if (global.setInMemoryData) {
          global.setInMemoryData(stockSymbol, { data: processedCandles });
        }
        
        processedCount.success++;
        
      } catch (error) {
        console.error(`Error processing ${stockFile}:`, error.message);
        processedCount.failed++;
      }
    }));
    
    if ((i + batch.length) % 200 === 0 || i + batch.length >= stockFiles.length) {
      console.log(`Processed ${i + batch.length}/${stockFiles.length} stocks in memory...`);
      sendProgressUpdate(i + batch.length, stockFiles.length, 
        `Processing indicators: ${i + batch.length}/${stockFiles.length} stocks`);
    }
    
    // Yield control to event loop
    await new Promise(resolve => setImmediate(resolve));
  }
  
  console.log(`Finished processing ${stockFiles.length} stocks in memory. Success: ${processedCount.success}, Failed: ${processedCount.failed}`);
  
  return processedCount;
}

// COMMENTED OUT - OLD FILE-BASED FUNCTION (kept for potential revert)
// Process all stocks and generate mapperStorage
async function processStocksWithIndicators(indicatorsData, stockList = null) {
  // Handle both old format (array) and new format (object with indicators and timeframes)
  let indicators, timeframes;
  if (Array.isArray(indicatorsData)) {
    // Old format - backward compatibility
    indicators = indicatorsData;
    timeframes = ['daily'];
  } else {
    // New format with timeframes
    indicators = indicatorsData.indicators;
    timeframes = indicatorsData.timeframes || ['daily'];
  }
  
  // Helper function to send progress updates
  const sendProgressUpdate = (processed, total, message) => {
    if (global.updateProgress) {
      global.updateProgress({ 
        phase: 'processing_indicators',
        processed, 
        total, 
        message 
      });
    }
  };
  
  // Check cache first (only if processing all stocks)
  // NOTE: Cache is now cleared for each new query to ensure fresh data
  if (!stockList && isCached(indicators)) {
    console.log('Using cached indicator calculations');
    const mapperStoragePath = path.join(__dirname, '..', 'mapperStorage');
    const files = fs.readdirSync(mapperStoragePath).filter(f => f.endsWith('_piped.json'));
    return { success: files.length, failed: 0, cached: true };
  }
  
  const dbPath = path.join(__dirname, '..', 'db');
  const mapperStoragePath = path.join(__dirname, '..', 'mapperStorage');
  
  // Clear existing mapperStorage
  if (stockList && stockList.length > 0) {
    // If processing specific stocks, only delete their mapper files
    if (!fs.existsSync(mapperStoragePath)) {
      fs.mkdirSync(mapperStoragePath, { recursive: true });
    }
    stockList.forEach(symbol => {
      const mapperFile = path.join(mapperStoragePath, `${symbol}_piped.json`);
      if (fs.existsSync(mapperFile)) {
        fs.unlinkSync(mapperFile);
      }
    });
  } else {
    // Processing all stocks - clear everything
    if (fs.existsSync(mapperStoragePath)) {
      fs.rmSync(mapperStoragePath, { recursive: true, force: true });
    }
    fs.mkdirSync(mapperStoragePath, { recursive: true });
  }
  
  // Get stock files to process
  let stockFiles;
  if (stockList && stockList.length > 0) {
    // Process only specified stocks
    stockFiles = stockList.map(symbol => `${symbol}.json`).filter(file => 
      fs.existsSync(path.join(dbPath, file))
    );
    console.log(`Processing ${stockFiles.length} specified stocks`);
  } else {
    // Process all stocks
    stockFiles = fs.readdirSync(dbPath).filter(file => file.endsWith('.json'));
  }
  
  console.log(`Processing ${stockFiles.length} stocks with indicators:`, indicators.map(i => `${i.name}(${i.period})`));
  console.log(`Using timeframes:`, timeframes);
  
  const processedCount = { success: 0, failed: 0 };
  const batchSize = 50; // Process 50 stocks at a time
  
  // Send initial progress
  sendProgressUpdate(0, stockFiles.length, 'Starting indicator processing...');
  
  // Process in batches for better performance
  for (let i = 0; i < stockFiles.length; i += batchSize) {
    const batch = stockFiles.slice(i, i + batchSize);
    
    await Promise.all(batch.map(async (stockFile) => {
      try {
        const stockSymbol = stockFile.replace('.json', '');
        const stockData = JSON.parse(fs.readFileSync(path.join(dbPath, stockFile), 'utf8'));
        
        if (!stockData.data || stockData.data.length === 0) {
          console.warn(`No data found for ${stockSymbol}`);
          processedCount.failed++;
          return;
        }
        
        // Sanitize the candle data to handle infinity values
        const sanitizedCandles = sanitizeCandleArray(stockData.data);
        
        // Calculate indicators with timeframe support
        const processedCandles = calculateAllIndicatorsWithTimeframes(sanitizedCandles, indicators, timeframes);
        
        // Save to mapperStorage
        const outputPath = path.join(mapperStoragePath, `${stockSymbol}_piped.json`);
        fs.writeFileSync(outputPath, JSON.stringify({ data: processedCandles }));
        
        processedCount.success++;
        
      } catch (error) {
        console.error(`Error processing ${stockFile}:`, error.message);
        processedCount.failed++;
      }
    }));
    
    if ((i + batch.length) % 200 === 0 || i + batch.length >= stockFiles.length) {
      console.log(`Processed ${i + batch.length}/${stockFiles.length} stocks...`);
      sendProgressUpdate(i + batch.length, stockFiles.length, 
        `Processing indicators: ${i + batch.length}/${stockFiles.length} stocks`);
    }
  }
  
  console.log(`Stock processing completed. Success: ${processedCount.success}, Failed: ${processedCount.failed}`);
  
  // Mark as cached for future use (only if processing all stocks)
  if (!stockList && processedCount.success > 0) {
    markAsCached(indicators);
  }
  
  return processedCount;
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
    return sanitizeNumericValue(prevCandle.close);
  }
  
  // Handle current week volume
  if (field === 'current_week_volume') {
    return getCurrentWeekVolume(candles, currentIndex);
  }
  
  // Handle previous week volume
  if (field === 'previous_week_volume') {
    return getPreviousWeekVolume(candles, currentIndex);
  }
  
  // Handle weekly aggregated fields
  if (field === 'open_weekly') {
    return getWeeklyAggregatedValue(candles, currentIndex, 'open', 0);
  }
  if (field === 'high_weekly') {
    return getWeeklyAggregatedValue(candles, currentIndex, 'high', 0);
  }
  if (field === 'low_weekly') {
    return getWeeklyAggregatedValue(candles, currentIndex, 'low', 0);
  }
  if (field === 'close_weekly') {
    return getWeeklyAggregatedValue(candles, currentIndex, 'close', 0);
  }
  if (field === 'weekly_volume') {
    // Weekly volume is already calculated in the candle, just return it
    return sanitizeNumericValue(candle.weekly_volume);
  }
  
  // Handle monthly volume
  if (field === 'monthly_volume') {
    // Monthly volume is already calculated in the candle, just return it
    return sanitizeNumericValue(candle.monthly_volume);
  }
  
  const value = candle[field];
  if (value === null || value === undefined) {
    return null;
  }
  
  return sanitizeNumericValue(value);
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
  
  return sanitizeNumericValue(value);
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
      return Math.max(...weekCandles.map(c => sanitizeNumericValue(c.high)).filter(v => v !== null));
    case 'low':
      return Math.min(...weekCandles.map(c => sanitizeNumericValue(c.low)).filter(v => v !== null));
    case 'open':
      return sanitizeNumericValue(weekCandles[0].open); // First candle's open
    case 'close':
      return sanitizeNumericValue(weekCandles[weekCandles.length - 1].close); // Last candle's close
    case 'volume':
      // For historical weeks (n weeks ago), return the last day's volume of that week
      // Sort weekCandles by date to ensure correct order
      weekCandles.sort((a, b) => Number(a.date) - Number(b.date));
      
      // Get the last candle of the week
      if (weekCandles.length > 0) {
        const lastCandle = weekCandles[weekCandles.length - 1];
        const vol = sanitizeNumericValue(lastCandle.volume);
        return vol !== null ? vol : 0;
      }
      
      return 0;
    default:
      // For other fields, return the last value of the week
      return sanitizeNumericValue(weekCandles[weekCandles.length - 1][field]);
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

function getCurrentWeekVolume(candles, currentIndex) {
  const currentDate = new Date(Number(candles[currentIndex].date));
  const currentWeek = getISOWeek(currentDate);
  const currentYear = currentDate.getUTCFullYear();
  
  // Calculate cumulative volume from Monday to current day
  let totalVolume = 0;
  
  // Go backwards from current index to accumulate volume for the week
  for (let i = currentIndex; i >= 0; i--) {
    const candle = candles[i];
    const candleDate = new Date(Number(candle.date));
    const candleWeek = getISOWeek(candleDate);
    const candleYear = candleDate.getUTCFullYear();
    
    // If we've gone to a different week, stop
    if (candleYear !== currentYear || candleWeek !== currentWeek) {
      break;
    }
    
    const vol = sanitizeNumericValue(candle.volume);
    if (vol !== null) {
      totalVolume += vol;
    }
  }
  
  return totalVolume;
}

function getPreviousWeekVolume(candles, currentIndex) {
  const currentDate = new Date(Number(candles[currentIndex].date));
  const currentWeek = getISOWeek(currentDate);
  const currentYear = currentDate.getUTCFullYear();
  
  // Calculate previous week and year
  let prevWeek = currentWeek - 1;
  let prevYear = currentYear;
  
  if (prevWeek <= 0) {
    prevYear--;
    // Get the last week of previous year
    const lastDayOfPrevYear = new Date(Date.UTC(prevYear, 11, 31));
    prevWeek = getISOWeek(lastDayOfPrevYear);
  }
  
  // Find all candles in the previous week (entire week, not cumulative)
  let totalVolume = 0;
  for (let i = 0; i <= currentIndex; i++) {
    const candle = candles[i];
    const candleDate = new Date(Number(candle.date));
    const candleWeek = getISOWeek(candleDate);
    const candleYear = candleDate.getUTCFullYear();
    
    if (candleYear === prevYear && candleWeek === prevWeek) {
      const vol = sanitizeNumericValue(candle.volume);
      if (vol !== null) {
        totalVolume += vol;
      }
    }
  }
  
  return totalVolume;
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
      return Math.max(...monthCandles.map(c => sanitizeNumericValue(c.high)).filter(v => v !== null));
    case 'low':
      return Math.min(...monthCandles.map(c => sanitizeNumericValue(c.low)).filter(v => v !== null));
    case 'open':
      return sanitizeNumericValue(monthCandles[0].open); // First candle's open
    case 'close':
      return sanitizeNumericValue(monthCandles[monthCandles.length - 1].close); // Last candle's close
    case 'volume':
      return monthCandles.reduce((sum, c) => {
        const vol = sanitizeNumericValue(c.volume);
        return sum + (vol !== null ? vol : 0);
      }, 0);
    default:
      // For other fields, return the last value of the month
      return sanitizeNumericValue(monthCandles[monthCandles.length - 1][field]);
  }
}

function evaluateExpression(expr, candle, prevCandle, candles, currentIndex) {
  if (expr.type === 'avg_function') {
    // Handle avg function
    const values = expr.operands.map(operand => 
      evaluateExpression(operand, candle, prevCandle, candles, currentIndex)
    ).filter(v => v !== null);
    
    if (values.length === 0) return null;
    
    const sum = values.reduce((acc, val) => acc + val, 0);
    return sum / values.length;
  } else if (expr.type === 'arithmetic_expression') {
    // Handle arithmetic expressions with two operands
    const leftValue = evaluateExpression(expr.leftOperand, candle, prevCandle, candles, currentIndex);
    const rightValue = evaluateExpression(expr.rightOperand, candle, prevCandle, candles, currentIndex);
    
    if (leftValue === null || rightValue === null) return null;
    
    switch (expr.operator) {
      case '+': return leftValue + rightValue;
      case '-': return leftValue - rightValue;
      case '*': return leftValue * rightValue;
      case '/': return rightValue !== 0 ? leftValue / rightValue : null;
      default: return null;
    }
  } else if (expr.type === 'expression') {
    // Get the base field value
    const baseValue = evaluateExpression(expr.field, candle, prevCandle, candles, currentIndex);
    if (baseValue === null) return null;
    
    // Apply the operator
    if (expr.operator === '*') {
      return baseValue * expr.multiplier;
    } else if (expr.operator === '/') {
      return baseValue / expr.multiplier;
    }
  } else if (expr.type === 'dynamic_indicator') {
    // Handle new dynamic indicator format with timeframe prefix
    const fieldName = expr.fieldKey; // e.g., "daily_rsi_14", "weekly_sma_20"
    
    if (expr.daysAgo) {
      // Historical indicator value
      return getHistoricalFieldValue(candles, currentIndex, fieldName, expr.daysAgo);
    } else {
      // Current indicator value
      return getFieldValue(candle, prevCandle, fieldName, candles, currentIndex);
    }
  } else if (expr.type === 'indicator') {
    // Handle indicator fields
    const fieldNames = generateIndicatorFieldName({
      name: expr.name,
      period: parseInt(expr.params[0]) || getDefaultPeriod(expr.name),
      params: parseIndicatorParams(expr.name, expr.params)
    });
    
    // For indicators with multiple outputs (like Bollinger Bands, MACD)
    let fieldName = fieldNames;
    if (typeof fieldNames === 'object') {
      // Default to main field for complex indicators
      if (expr.name === 'bb' || expr.name === 'bollinger') {
        fieldName = fieldNames.middle; // Use middle band as default
      } else if (expr.name === 'macd') {
        fieldName = fieldNames.macd; // Use MACD line as default
      } else if (expr.name === 'stochastic') {
        fieldName = fieldNames.k; // Use %K as default
      }
    }
    
    if (expr.daysAgo) {
      // Historical indicator value
      return getHistoricalFieldValue(candles, currentIndex, fieldName, expr.daysAgo);
    } else {
      // Current indicator value
      return getFieldValue(candle, prevCandle, fieldName, candles, currentIndex);
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

// Parse indicator parameters based on indicator type
function parseIndicatorParams(indicatorName, params) {
  const result = {};
  
  switch (indicatorName) {
    case 'bb':
    case 'bollinger':
      result.stdDev = params[1] ? parseFloat(params[1]) : 2;
      break;
    case 'supertrend':
      result.multiplier = params[1] ? parseFloat(params[1]) : 3;
      break;
    case 'macd':
      result.fast = params[0] ? parseInt(params[0]) : 12;
      result.slow = params[1] ? parseInt(params[1]) : 26;
      result.signal = params[2] ? parseInt(params[2]) : 9;
      break;
    case 'stochastic':
      result.k = params[0] ? parseInt(params[0]) : 14;
      result.d = params[1] ? parseInt(params[1]) : 3;
      break;
  }
  
  return result;
}

function evaluateCondition(condition, candle, prevCandle, candles, currentIndex) {
  // Handle crossed above/below operators
  if (condition.operator === 'crossed above' || condition.operator === 'crossed below') {
    // Get current values
    const leftValue = evaluateExpression(condition.left, candle, prevCandle, candles, currentIndex);
    const rightValue = evaluateExpression(condition.right, candle, prevCandle, candles, currentIndex);
    
    if (leftValue === null || rightValue === null || currentIndex === 0) return false;
    
    // Get previous values
    const prevLeftValue = evaluateExpression(condition.left, prevCandle, candles[currentIndex - 2], candles, currentIndex - 1);
    const prevRightValue = evaluateExpression(condition.right, prevCandle, candles[currentIndex - 2], candles, currentIndex - 1);
    
    if (prevLeftValue === null || prevRightValue === null) return false;
    
    if (condition.operator === 'crossed above') {
      return prevLeftValue <= prevRightValue && leftValue > rightValue;
    } else {
      return prevLeftValue >= prevRightValue && leftValue < rightValue;
    }
  }
  
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
    } else if (expr.type === 'indicator') {
      const fieldNames = generateIndicatorFieldName({
        name: expr.name,
        period: parseInt(expr.params[0]) || getDefaultPeriod(expr.name),
        params: parseIndicatorParams(expr.name, expr.params)
      });
      
      if (typeof fieldNames === 'object') {
        // Add all fields for complex indicators
        Object.values(fieldNames).forEach(field => requiredFields.add(field));
      } else {
        requiredFields.add(fieldNames);
      }
      
      if (expr.daysAgo) {
        maxDaysAgo = Math.max(maxDaysAgo, expr.daysAgo);
      }
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
  getQueryExamples,
  extractIndicatorsFromQuery,
  processStocksWithIndicatorsInMemory,
  processStocksWithIndicators,
  generateIndicatorFieldName,
  evaluateAllConditions
};