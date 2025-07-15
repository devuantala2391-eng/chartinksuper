// services/indicatorCalculator.js

/**
 * Technical Indicator Calculator Service
 * Calculates various technical indicators dynamically based on user parameters
 */

const { sanitizeNumericValue, filterValidValues } = require('./dataUtils');

// Simple Moving Average
function calculateSMA(data, period) {
  const result = [];
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      result.push(null);
    } else {
      const slice = data.slice(i - period + 1, i + 1);
      const validValues = slice.map(v => sanitizeNumericValue(v)).filter(v => v !== null);
      
      if (validValues.length === 0) {
        result.push(null);
      } else {
        const sum = validValues.reduce((a, b) => a + b, 0);
        result.push(sum / validValues.length);
      }
    }
  }
  return result;
}

// Exponential Moving Average
function calculateEMA(data, period) {
  const result = [];
  const multiplier = 2 / (period + 1);
  
  let lastValidEMA = null;
  
  for (let i = 0; i < data.length; i++) {
    const currentVal = sanitizeNumericValue(data[i]);
    
    if (currentVal === null) {
      result.push(null);
    } else if (lastValidEMA === null) {
      // First valid value becomes the starting EMA
      lastValidEMA = currentVal;
      result.push(currentVal);
    } else {
      const ema = (currentVal - lastValidEMA) * multiplier + lastValidEMA;
      lastValidEMA = ema;
      result.push(ema);
    }
  }
  return result;
}

// Relative Strength Index
function calculateRSI(data, period = 14) {
  const result = [];
  const gains = [];
  const losses = [];
  
  for (let i = 0; i < data.length; i++) {
    if (i === 0) {
      gains.push(0);
      losses.push(0);
      result.push(null);
    } else {
      const currentVal = sanitizeNumericValue(data[i]);
      const prevVal = sanitizeNumericValue(data[i - 1]);
      
      if (currentVal === null || prevVal === null) {
        gains.push(0);
        losses.push(0);
        result.push(null);
      } else {
        const change = currentVal - prevVal;
        gains.push(change > 0 ? change : 0);
        losses.push(change < 0 ? Math.abs(change) : 0);
        
        if (i < period) {
          result.push(null);
        } else {
          const avgGain = gains.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0) / period;
          const avgLoss = losses.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0) / period;
          
          if (avgLoss === 0) {
            result.push(100);
          } else {
            const rs = avgGain / avgLoss;
            const rsi = 100 - (100 / (1 + rs));
            result.push(rsi);
          }
        }
      }
    }
  }
  return result;
}

// Bollinger Bands
function calculateBollingerBands(data, period = 20, standardDeviations = 2) {
  const sma = calculateSMA(data, period);
  const upperBand = [];
  const lowerBand = [];
  
  for (let i = 0; i < data.length; i++) {
    if (i < period - 1) {
      upperBand.push(null);
      lowerBand.push(null);
    } else {
      const slice = data.slice(i - period + 1, i + 1);
      const mean = sma[i];
      const variance = slice.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / period;
      const stdDev = Math.sqrt(variance);
      
      upperBand.push(mean + (standardDeviations * stdDev));
      lowerBand.push(mean - (standardDeviations * stdDev));
    }
  }
  
  return {
    upper: upperBand,
    middle: sma,
    lower: lowerBand
  };
}

// SuperTrend
function calculateSuperTrend(highs, lows, closes, period = 10, multiplier = 3) {
  const result = [];
  const trend = [];
  const atr = calculateATR(highs, lows, closes, period);
  
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) {
      result.push(null);
      trend.push(null);
    } else {
      const hl2 = (highs[i] + lows[i]) / 2;
      const upperBand = hl2 + (multiplier * atr[i]);
      const lowerBand = hl2 - (multiplier * atr[i]);
      
      let superTrend = null;
      let currentTrend = null;
      
      if (i === period - 1) {
        superTrend = lowerBand;
        currentTrend = 1;
      } else {
        const prevSuperTrend = result[i - 1];
        const prevTrend = trend[i - 1];
        
        if (closes[i] > prevSuperTrend && prevTrend === 1) {
          superTrend = lowerBand;
          currentTrend = 1;
        } else if (closes[i] < prevSuperTrend && prevTrend === -1) {
          superTrend = upperBand;
          currentTrend = -1;
        } else if (closes[i] <= prevSuperTrend && prevTrend === 1) {
          superTrend = upperBand;
          currentTrend = -1;
        } else {
          superTrend = lowerBand;
          currentTrend = 1;
        }
      }
      
      result.push(superTrend);
      trend.push(currentTrend);
    }
  }
  
  return result;
}

// Average True Range (helper for SuperTrend)
function calculateATR(highs, lows, closes, period = 14) {
  const trueRanges = [];
  
  for (let i = 0; i < highs.length; i++) {
    if (i === 0) {
      trueRanges.push(highs[i] - lows[i]);
    } else {
      const tr1 = highs[i] - lows[i];
      const tr2 = Math.abs(highs[i] - closes[i - 1]);
      const tr3 = Math.abs(lows[i] - closes[i - 1]);
      trueRanges.push(Math.max(tr1, tr2, tr3));
    }
  }
  
  return calculateSMA(trueRanges, period);
}

// MACD (Moving Average Convergence Divergence)
function calculateMACD(data, fastPeriod = 12, slowPeriod = 26, signalPeriod = 9) {
  const fastEMA = calculateEMA(data, fastPeriod);
  const slowEMA = calculateEMA(data, slowPeriod);
  const macdLine = [];
  
  for (let i = 0; i < data.length; i++) {
    if (fastEMA[i] !== null && slowEMA[i] !== null) {
      macdLine.push(fastEMA[i] - slowEMA[i]);
    } else {
      macdLine.push(null);
    }
  }
  
  const signalLine = calculateEMA(macdLine.filter(val => val !== null), signalPeriod);
  const histogram = [];
  
  let signalIndex = 0;
  for (let i = 0; i < macdLine.length; i++) {
    if (macdLine[i] !== null) {
      if (signalIndex < signalLine.length) {
        histogram.push(macdLine[i] - signalLine[signalIndex]);
        signalIndex++;
      } else {
        histogram.push(null);
      }
    } else {
      histogram.push(null);
    }
  }
  
  return {
    macd: macdLine,
    signal: signalLine,
    histogram: histogram
  };
}

// Stochastic Oscillator
function calculateStochastic(highs, lows, closes, kPeriod = 14, dPeriod = 3) {
  const kPercent = [];
  
  for (let i = 0; i < closes.length; i++) {
    if (i < kPeriod - 1) {
      kPercent.push(null);
    } else {
      const highestHigh = Math.max(...highs.slice(i - kPeriod + 1, i + 1));
      const lowestLow = Math.min(...lows.slice(i - kPeriod + 1, i + 1));
      const k = ((closes[i] - lowestLow) / (highestHigh - lowestLow)) * 100;
      kPercent.push(k);
    }
  }
  
  const dPercent = calculateSMA(kPercent.filter(val => val !== null), dPeriod);
  
  return {
    k: kPercent,
    d: dPercent
  };
}

// Williams %R
function calculateWilliamsR(highs, lows, closes, period = 14) {
  const result = [];
  
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) {
      result.push(null);
    } else {
      const highestHigh = Math.max(...highs.slice(i - period + 1, i + 1));
      const lowestLow = Math.min(...lows.slice(i - period + 1, i + 1));
      const williamsR = ((highestHigh - closes[i]) / (highestHigh - lowestLow)) * -100;
      result.push(williamsR);
    }
  }
  
  return result;
}

// Calculate all indicators for a stock's candle data
function calculateAllIndicators(candles, indicators) {
  const result = [...candles];
  
  // Extract and sanitize price arrays
  const opens = candles.map(c => sanitizeNumericValue(c.open));
  const highs = candles.map(c => sanitizeNumericValue(c.high));
  const lows = candles.map(c => sanitizeNumericValue(c.low));
  const closes = candles.map(c => sanitizeNumericValue(c.close));
  const volumes = candles.map(c => sanitizeNumericValue(c.volume));
  
  // Calculate each requested indicator
  for (const indicator of indicators) {
    const { name, period, params } = indicator;
    
    try {
      switch (name.toLowerCase()) {
        case 'sma':
          const smaValues = calculateSMA(closes, period);
          result.forEach((candle, i) => {
            candle[`sma_${period}`] = smaValues[i] !== null ? smaValues[i].toString() : null;
          });
          break;
          
        case 'ema':
          const emaValues = calculateEMA(closes, period);
          result.forEach((candle, i) => {
            candle[`ema_${period}`] = emaValues[i] !== null ? emaValues[i].toString() : null;
          });
          break;
          
        case 'rsi':
          const rsiValues = calculateRSI(closes, period);
          result.forEach((candle, i) => {
            candle[`rsi_${period}`] = rsiValues[i] !== null ? rsiValues[i].toString() : null;
          });
          break;
          
        case 'bb':
        case 'bollinger':
          const bbPeriod = period || 20;
          const bbStdDev = params?.stdDev || 2;
          const bbValues = calculateBollingerBands(closes, bbPeriod, bbStdDev);
          result.forEach((candle, i) => {
            candle[`bb_upper_${bbPeriod}_${bbStdDev}`] = bbValues.upper[i] !== null ? bbValues.upper[i].toString() : null;
            candle[`bb_middle_${bbPeriod}_${bbStdDev}`] = bbValues.middle[i] !== null ? bbValues.middle[i].toString() : null;
            candle[`bb_lower_${bbPeriod}_${bbStdDev}`] = bbValues.lower[i] !== null ? bbValues.lower[i].toString() : null;
          });
          break;
          
        case 'supertrend':
          const stPeriod = period || 10;
          const stMultiplier = params?.multiplier || 3;
          const stValues = calculateSuperTrend(highs, lows, closes, stPeriod, stMultiplier);
          result.forEach((candle, i) => {
            candle[`supertrend_${stPeriod}_${stMultiplier}`] = stValues[i] !== null ? stValues[i].toString() : null;
          });
          break;
          
        case 'macd':
          const macdFast = params?.fast || 12;
          const macdSlow = params?.slow || 26;
          const macdSignal = params?.signal || 9;
          const macdValues = calculateMACD(closes, macdFast, macdSlow, macdSignal);
          result.forEach((candle, i) => {
            candle[`macd_${macdFast}_${macdSlow}_${macdSignal}`] = macdValues.macd[i] !== null ? macdValues.macd[i].toString() : null;
            candle[`macd_signal_${macdFast}_${macdSlow}_${macdSignal}`] = macdValues.signal[i] !== null ? macdValues.signal[i].toString() : null;
            candle[`macd_histogram_${macdFast}_${macdSlow}_${macdSignal}`] = macdValues.histogram[i] !== null ? macdValues.histogram[i].toString() : null;
          });
          break;
          
        case 'stochastic':
          const stochK = params?.k || 14;
          const stochD = params?.d || 3;
          const stochValues = calculateStochastic(highs, lows, closes, stochK, stochD);
          result.forEach((candle, i) => {
            candle[`stoch_k_${stochK}_${stochD}`] = stochValues.k[i] !== null ? stochValues.k[i].toString() : null;
            candle[`stoch_d_${stochK}_${stochD}`] = stochValues.d[i] !== null ? stochValues.d[i].toString() : null;
          });
          break;
          
        case 'williamsr':
          const wrPeriod = period || 14;
          const wrValues = calculateWilliamsR(highs, lows, closes, wrPeriod);
          result.forEach((candle, i) => {
            candle[`williamsr_${wrPeriod}`] = wrValues[i] !== null ? wrValues[i].toString() : null;
          });
          break;
      }
    } catch (error) {
      console.error(`Error calculating ${name}(${period}):`, error.message);
    }
  }
  
  return result;
}

module.exports = {
  calculateSMA,
  calculateEMA,
  calculateRSI,
  calculateBollingerBands,
  calculateSuperTrend,
  calculateATR,
  calculateMACD,
  calculateStochastic,
  calculateWilliamsR,
  calculateAllIndicators
};