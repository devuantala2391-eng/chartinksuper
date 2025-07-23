// services/dataUtils.js

/**
 * Data utility functions for handling invalid values
 */

/**
 * Sanitizes numeric values, converting infinity values (1.7e+308) to null
 * @param {*} value - The value to sanitize
 * @returns {number|null} - The sanitized value or null if invalid
 */
function sanitizeNumericValue(value) {
  // Convert to number if it's a string
  const numValue = typeof value === 'string' ? parseFloat(value) : value;
  
  // Check for invalid values
  if (value === null || value === undefined || value === '') {
    return null;
  }
  
  // Check for NaN
  if (isNaN(numValue)) {
    return null;
  }
  
  // Check for infinity values (1.7e+308 is close to JavaScript's Number.MAX_VALUE)
  if (!isFinite(numValue) || numValue >= 1.7e+308 || numValue <= -1.7e+308) {
    return null;
  }
  
  return numValue;
}

/**
 * Sanitizes a candle object, converting all numeric fields
 * @param {Object} candle - The candle object to sanitize
 * @returns {Object} - The sanitized candle object
 */
function sanitizeCandle(candle) {
  const sanitized = { ...candle };
  
  // Sanitize OHLCV values
  const numericFields = ['open', 'high', 'low', 'close', 'volume'];
  
  numericFields.forEach(field => {
    if (field in sanitized) {
      sanitized[field] = sanitizeNumericValue(sanitized[field]);
    }
  });
  
  // Sanitize any indicator fields (they typically contain underscores)
  Object.keys(sanitized).forEach(key => {
    if (key.includes('_') || key.includes('rsi') || key.includes('sma') || 
        key.includes('ema') || key.includes('bb') || key.includes('macd') ||
        key.includes('stoch') || key.includes('williams') || key.includes('supertrend')) {
      sanitized[key] = sanitizeNumericValue(sanitized[key]);
    }
  });
  
  return sanitized;
}

/**
 * Sanitizes an array of candles
 * @param {Array} candles - Array of candle objects
 * @returns {Array} - Array of sanitized candle objects
 */
function sanitizeCandleArray(candles) {
  if (!Array.isArray(candles)) {
    return [];
  }
  
  return candles.map(candle => sanitizeCandle(candle));
}

/**
 * Filters out invalid values from a numeric array (used in indicator calculations)
 * @param {Array} values - Array of numeric values
 * @returns {Array} - Array with valid numeric values only
 */
function filterValidValues(values) {
  return values.map(v => sanitizeNumericValue(v)).filter(v => v !== null);
}

module.exports = {
  sanitizeNumericValue,
  sanitizeCandle,
  sanitizeCandleArray,
  filterValidValues
};