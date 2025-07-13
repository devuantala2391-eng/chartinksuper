// mapper.js

/**
 * Aggregates daily candles into weekly or monthly candles.
 * @param {Array} dailyData - Array of daily candle objects.
 * @param {'weekly'|'monthly'} timeframe - The aggregation timeframe.
 * @returns {Array} Aggregated candles.
 */
function aggregateCandles(dailyData, timeframe) {
  if (timeframe === 'daily') return dailyData;
  const grouped = [];
  let current = null;
  for (const candle of dailyData) {
    const date = new Date(Number(candle.date));
    let groupKey;
    if (timeframe === 'weekly') {
      // Week starts on Monday (ISO week)
      const year = date.getUTCFullYear();
      const week = getISOWeek(date);
      groupKey = `${year}-W${week}`;
    } else if (timeframe === 'monthly') {
      groupKey = `${date.getUTCFullYear()}-${date.getUTCMonth() + 1}`;
    }
    if (!current || current.groupKey !== groupKey) {
      if (current) grouped.push(current);
      current = {
        groupKey,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
        volume: Number(candle.volume),
        date: candle.date,
        day: candle.day,
        lastDate: candle.date,
      };
    } else {
      current.high = String(Math.max(Number(current.high), Number(candle.high)));
      current.low = String(Math.min(Number(current.low), Number(candle.low)));
      current.close = candle.close;
      current.volume += Number(candle.volume);
      current.lastDate = candle.date;
    }
  }
  if (current) grouped.push(current);
  // Use the last date in the group as the candle's date
  return grouped.map(c => ({
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    volume: String(c.volume),
    date: c.lastDate,
    day: c.day,
  }));
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

/**
 * Pure function: Calculates the SMA for the given candle data and timeframe.
 * If timeframe is 'daily', computes a simple SMA over daily candles.
 * If timeframe is 'weekly', computes a rolling weekly SMA over daily candles.
 * If timeframe is 'monthly', computes a simple SMA over monthly-aggregated candles.
 * @param {Array} candles - Array of candle objects.
 * @param {'daily'|'weekly'|'monthly'} timeframe - The timeframe for SMA calculation.
 * @param {number} period - Number of candles for SMA.
 * @param {string} [outputKey='sma'] - The key to store the SMA value in each candle.
 * @returns {Array} New array of candles with an added SMA field (outputKey).
 */
function calculateSMA(candles, timeframe, period, outputKey = 'sma') {
  if (!Array.isArray(candles)) return [];

  if (timeframe === 'weekly') {
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
    function getWeekKey(date) {
      const d = new Date(Number(date));
      const year = d.getUTCFullYear();
      const week = getISOWeek(d);
      return `${year}-W${week}`;
    }
    // Build a map: weekKey -> { lastClose, lastIdx }
    const weekMap = new Map();
    candles.forEach((candle, idx) => {
      const weekKey = getWeekKey(candle.date);
      if (!weekMap.has(weekKey) || Number(candle.date) > Number(candles[weekMap.get(weekKey).lastIdx].date)) {
        weekMap.set(weekKey, { lastClose: candle.close, lastIdx: idx });
      }
    });
    const weekKeys = Array.from(weekMap.keys());
    return candles.map((candle, idx) => {
      const currentWeekKey = getWeekKey(candle.date);
      const currentWeekIdx = weekKeys.indexOf(currentWeekKey);
      if (currentWeekIdx < period - 1) {
        return { ...candle, [outputKey]: null };
      }
      const relevantWeekKeys = weekKeys.slice(currentWeekIdx - period + 1, currentWeekIdx + 1);
      const closes = relevantWeekKeys.map(wk => weekMap.get(wk).lastClose).map(Number);
      const isLastOfWeek = weekMap.get(currentWeekKey).lastIdx === idx;
      if (!isLastOfWeek) {
        closes[closes.length - 1] = Number(candle.close);
      }
      const sma = closes.reduce((a, b) => a + b, 0) / period;
      return { ...candle, [outputKey]: sma };
    });
  }

  if (timeframe === 'monthly') {
    const tfCandles = aggregateCandles(candles, 'monthly');
    return tfCandles.map((candle, idx, arr) => {
      if (idx < period - 1) {
        return { ...candle, [outputKey]: null };
      }
      const sum = arr.slice(idx - period + 1, idx + 1).reduce((acc, c) => acc + Number(c.close), 0);
      const sma = sum / period;
      return { ...candle, [outputKey]: sma };
    });
  }

  // Default: simple SMA on daily candles
  return candles.map((candle, idx, arr) => {
    if (idx < period - 1) {
      return { ...candle, [outputKey]: null };
    }
    const sum = arr.slice(idx - period + 1, idx + 1).reduce((acc, c) => acc + Number(c.close), 0);
    const sma = sum / period;
    return { ...candle, [outputKey]: sma };
  });
}

/**
 * Factory to create a SMA calculation function for piping.
 * @param {'daily'|'weekly'|'monthly'} timeframe
 * @param {number} period
 * @param {string} [outputKey='sma']
 * @returns {function(Array): Array}
 */
function calculateSMAFactory(timeframe, period, outputKey = 'sma') {
  return (candles) => calculateSMA(candles, timeframe, period, outputKey);
}

/**
 * Calculates the EMA for the given candle data and timeframe.
 * @param {Array} candles
 * @param {'daily'|'weekly'|'monthly'} timeframe
 * @param {number} period
 * @param {string} [outputKey='ema']
 * @returns {Array}
 */
function calculateEMA(candles, timeframe, period, outputKey = 'ema') {
  if (!Array.isArray(candles)) return [];

  if (timeframe === 'weekly') {
    // Aggregate to weekly candles first
    const weeklyCandles = aggregateCandles(candles, 'weekly');
    let emaPrev = null;
    const k = 2 / (period + 1);
    const weeklyResults = weeklyCandles.map((candle, idx, arr) => {
      const close = Number(candle.close);
      if (idx < period - 1) {
        emaPrev = emaPrev === null ? close : emaPrev;
        return { ...candle, [outputKey]: null };
      }
      if (idx === period - 1) {
        const sma = arr.slice(0, period).reduce((acc, c) => acc + Number(c.close), 0) / period;
        emaPrev = sma;
        return { ...candle, [outputKey]: sma };
      }
      const ema = (close - emaPrev) * k + emaPrev;
      emaPrev = ema;
      return { ...candle, [outputKey]: ema };
    });
    
    // Map weekly results back to daily candles
    function getWeekKey(date) {
      const d = new Date(Number(date));
      const year = d.getUTCFullYear();
      const week = getISOWeek(d);
      return `${year}-W${week}`;
    }
    
    return candles.map((candle) => {
      const weekKey = getWeekKey(candle.date);
      const weeklyCandle = weeklyResults.find(wc => {
        const wcWeekKey = getWeekKey(wc.date);
        return wcWeekKey === weekKey;
      });
      return { ...candle, [outputKey]: weeklyCandle ? weeklyCandle[outputKey] : null };
    });
  }

  if (timeframe === 'monthly') {
    const tfCandles = aggregateCandles(candles, 'monthly');
    let emaPrev = null;
    const k = 2 / (period + 1);
    return tfCandles.map((candle, idx, arr) => {
      const close = Number(candle.close);
      if (idx < period - 1) {
        emaPrev = emaPrev === null ? close : emaPrev;
        return { ...candle, [outputKey]: null };
      }
      if (idx === period - 1) {
        const sma = arr.slice(0, period).reduce((acc, c) => acc + Number(c.close), 0) / period;
        emaPrev = sma;
        return { ...candle, [outputKey]: sma };
      }
      const ema = (close - emaPrev) * k + emaPrev;
      emaPrev = ema;
      return { ...candle, [outputKey]: ema };
    });
  }

  // Default: simple EMA on daily candles
  let emaPrev = null;
  const k = 2 / (period + 1);
  return candles.map((candle, idx, arr) => {
    const close = Number(candle.close);
    if (idx < period - 1) {
      emaPrev = emaPrev === null ? close : emaPrev;
      return { ...candle, [outputKey]: null };
    }
    if (idx === period - 1) {
      const sma = arr.slice(0, period).reduce((acc, c) => acc + Number(c.close), 0) / period;
      emaPrev = sma;
      return { ...candle, [outputKey]: sma };
    }
    const ema = (close - emaPrev) * k + emaPrev;
    emaPrev = ema;
    return { ...candle, [outputKey]: ema };
  });
}

function calculateEMAFactory(timeframe, period, outputKey = 'ema') {
  return (candles) => calculateEMA(candles, timeframe, period, outputKey);
}

/**
 * Calculates the RSI for the given candle data and timeframe.
 * @param {Array} candles
 * @param {'daily'|'weekly'|'monthly'} timeframe
 * @param {number} period
 * @param {string} [outputKey='rsi']
 * @returns {Array}
 */
function calculateRSI(candles, timeframe, period, outputKey = 'rsi') {
  if (!Array.isArray(candles)) return [];

  if (timeframe === 'weekly') {
    // Aggregate to weekly candles first
    const weeklyCandles = aggregateCandles(candles, 'weekly');
    let avgGain = 0, avgLoss = 0;
    const weeklyResults = weeklyCandles.map((candle, idx, arr) => {
      if (idx === 0) {
        return { ...candle, [outputKey]: null };
      }
      const change = Number(candle.close) - Number(arr[idx - 1].close);
      const gain = Math.max(change, 0);
      const loss = Math.max(-change, 0);
      if (idx < period) {
        avgGain += gain;
        avgLoss += loss;
        return { ...candle, [outputKey]: null };
      }
      if (idx === period) {
        avgGain = avgGain / period;
        avgLoss = avgLoss / period;
      } else {
        avgGain = (avgGain * (period - 1) + gain) / period;
        avgLoss = (avgLoss * (period - 1) + loss) / period;
      }
      const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
      const rsi = avgLoss === 0 ? 100 : 100 - 100 / (1 + rs);
      return { ...candle, [outputKey]: rsi };
    });
    
    // Map weekly results back to daily candles
    function getWeekKey(date) {
      const d = new Date(Number(date));
      const year = d.getUTCFullYear();
      const week = getISOWeek(d);
      return `${year}-W${week}`;
    }
    
    return candles.map((candle) => {
      const weekKey = getWeekKey(candle.date);
      const weeklyCandle = weeklyResults.find(wc => {
        const wcWeekKey = getWeekKey(wc.date);
        return wcWeekKey === weekKey;
      });
      return { ...candle, [outputKey]: weeklyCandle ? weeklyCandle[outputKey] : null };
    });
  }

  if (timeframe === 'monthly') {
    const tfCandles = aggregateCandles(candles, 'monthly');
    let avgGain = 0, avgLoss = 0;
    return tfCandles.map((candle, idx, arr) => {
      if (idx === 0) {
        return { ...candle, [outputKey]: null };
      }
      const change = Number(candle.close) - Number(arr[idx - 1].close);
      const gain = Math.max(change, 0);
      const loss = Math.max(-change, 0);
      if (idx < period) {
        avgGain += gain;
        avgLoss += loss;
        return { ...candle, [outputKey]: null };
      }
      if (idx === period) {
        avgGain = avgGain / period;
        avgLoss = avgLoss / period;
      } else {
        avgGain = (avgGain * (period - 1) + gain) / period;
        avgLoss = (avgLoss * (period - 1) + loss) / period;
      }
      const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
      const rsi = avgLoss === 0 ? 100 : 100 - 100 / (1 + rs);
      return { ...candle, [outputKey]: rsi };
    });
  }

  // Default: simple RSI on daily candles
  let avgGain = 0, avgLoss = 0;
  return candles.map((candle, idx, arr) => {
    if (idx === 0) {
      return { ...candle, [outputKey]: null };
    }
    const change = Number(candle.close) - Number(arr[idx - 1].close);
    const gain = Math.max(change, 0);
    const loss = Math.max(-change, 0);
    if (idx < period) {
      avgGain += gain;
      avgLoss += loss;
      return { ...candle, [outputKey]: null };
    }
    if (idx === period) {
      avgGain = avgGain / period;
      avgLoss = avgLoss / period;
    } else {
      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;
    }
    const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
    const rsi = avgLoss === 0 ? 100 : 100 - 100 / (1 + rs);
    return { ...candle, [outputKey]: rsi };
  });
}

function calculateRSIFactory(timeframe, period, outputKey = 'rsi') {
  return (candles) => calculateRSI(candles, timeframe, period, outputKey);
}

/**
 * Calculates the percent change for the given candle data and timeframe.
 * @param {Array} candles
 * @param {'daily'|'weekly'|'monthly'} timeframe
 * @param {number} period
 * @param {string} [outputKey='%change']
 * @returns {Array}
 */
function calculatePercentChange(candles, timeframe, period, outputKey = '%change') {
  if (!Array.isArray(candles)) return [];

  if (timeframe === 'weekly') {
    // Aggregate to weekly candles first
    const weeklyCandles = aggregateCandles(candles, 'weekly');
    const weeklyResults = weeklyCandles.map((candle, idx, arr) => {
      if (idx < period) {
        return { ...candle, [outputKey]: null };
      }
      const prevClose = Number(arr[idx - period].close);
      const currClose = Number(candle.close);
      const pct = ((currClose - prevClose) / prevClose) * 100;
      return { ...candle, [outputKey]: pct };
    });
    
    // Map weekly results back to daily candles
    function getWeekKey(date) {
      const d = new Date(Number(date));
      const year = d.getUTCFullYear();
      const week = getISOWeek(d);
      return `${year}-W${week}`;
    }
    
    return candles.map((candle) => {
      const weekKey = getWeekKey(candle.date);
      const weeklyCandle = weeklyResults.find(wc => {
        const wcWeekKey = getWeekKey(wc.date);
        return wcWeekKey === weekKey;
      });
      return { ...candle, [outputKey]: weeklyCandle ? weeklyCandle[outputKey] : null };
    });
  }

  if (timeframe === 'monthly') {
    const tfCandles = aggregateCandles(candles, 'monthly');
    return tfCandles.map((candle, idx, arr) => {
      if (idx < period) {
        return { ...candle, [outputKey]: null };
      }
      const prevClose = Number(arr[idx - period].close);
      const currClose = Number(candle.close);
      const pct = ((currClose - prevClose) / prevClose) * 100;
      return { ...candle, [outputKey]: pct };
    });
  }

  // Default: simple percent change on daily candles
  return candles.map((candle, idx, arr) => {
    if (idx < period) {
      return { ...candle, [outputKey]: null };
    }
    const prevClose = Number(arr[idx - period].close);
    const currClose = Number(candle.close);
    const pct = ((currClose - prevClose) / prevClose) * 100;
    return { ...candle, [outputKey]: pct };
  });
}

function calculatePercentChangeFactory(timeframe, period, outputKey = '%change') {
  return (candles) => calculatePercentChange(candles, timeframe, period, outputKey);
}

/**
 * Calculates the SuperTrend indicator for the given candle data and timeframe.
 * @param {Array} candles
 * @param {'daily'|'weekly'|'monthly'} timeframe
 * @param {number} period
 * @param {number} multiplier
 * @param {string} [outputKey='supertrend']
 * @returns {Array}
 */
function calculateSuperTrend(candles, timeframe, period, multiplier, outputKey = 'supertrend') {
  if (!Array.isArray(candles)) return [];

  if (timeframe === 'weekly') {
    // Aggregate to weekly candles first
    const weeklyCandles = aggregateCandles(candles, 'weekly');
    
    // Calculate ATR first
    let atrArr = [];
    for (let i = 0; i < weeklyCandles.length; i++) {
      const curr = weeklyCandles[i];
      const prev = weeklyCandles[i - 1];
      const high = Number(curr.high);
      const low = Number(curr.low);
      const close = Number(curr.close);
      const prevClose = prev ? Number(prev.close) : close;
      const tr = Math.max(
        high - low,
        Math.abs(high - prevClose),
        Math.abs(low - prevClose)
      );
      if (i === 0) {
        atrArr.push(tr);
      } else if (i < period) {
        atrArr.push(tr);
      } else if (i === period) {
        const atr = atrArr.slice(1, period + 1).reduce((a, b) => a + b, 0) / period;
        atrArr.push(atr);
      } else {
        const atr = (atrArr[atrArr.length - 1] * (period - 1) + tr) / period;
        atrArr.push(atr);
      }
    }
    
    // SuperTrend calculation
    let supertrend = [];
    let inUptrend = true;
    const weeklyResults = weeklyCandles.map((candle, idx) => {
      const atr = atrArr[idx];
      const hl2 = (Number(candle.high) + Number(candle.low)) / 2;
      const upperBand = hl2 + multiplier * atr;
      const lowerBand = hl2 - multiplier * atr;
      let st;
      if (idx === 0) {
        st = upperBand;
        inUptrend = true;
      } else {
        const prev = supertrend[idx - 1];
        if (candle.close > prev.st) {
          st = Math.max(lowerBand, prev.st);
          inUptrend = true;
        } else if (candle.close < prev.st) {
          st = Math.min(upperBand, prev.st);
          inUptrend = false;
        } else {
          st = prev.st;
        }
      }
      supertrend.push({ st, inUptrend });
      return {
        ...candle,
        [outputKey]: idx < period ? null : st,
        [`${outputKey}_trend`]: idx < period ? null : (inUptrend ? 'up' : 'down'),
      };
    });
    
    // Map weekly results back to daily candles
    function getWeekKey(date) {
      const d = new Date(Number(date));
      const year = d.getUTCFullYear();
      const week = getISOWeek(d);
      return `${year}-W${week}`;
    }
    
    return candles.map((candle) => {
      const weekKey = getWeekKey(candle.date);
      const weeklyCandle = weeklyResults.find(wc => {
        const wcWeekKey = getWeekKey(wc.date);
        return wcWeekKey === weekKey;
      });
      return {
        ...candle,
        [outputKey]: weeklyCandle ? weeklyCandle[outputKey] : null,
        [`${outputKey}_trend`]: weeklyCandle ? weeklyCandle[`${outputKey}_trend`] : null,
      };
    });
  }

  if (timeframe === 'monthly') {
    const tfCandles = aggregateCandles(candles, 'monthly');
    // Calculate ATR first
    let atrArr = [];
    for (let i = 0; i < tfCandles.length; i++) {
      const curr = tfCandles[i];
      const prev = tfCandles[i - 1];
      const high = Number(curr.high);
      const low = Number(curr.low);
      const close = Number(curr.close);
      const prevClose = prev ? Number(prev.close) : close;
      const tr = Math.max(
        high - low,
        Math.abs(high - prevClose),
        Math.abs(low - prevClose)
      );
      if (i === 0) {
        atrArr.push(tr);
      } else if (i < period) {
        atrArr.push(tr);
      } else if (i === period) {
        const atr = atrArr.slice(1, period + 1).reduce((a, b) => a + b, 0) / period;
        atrArr.push(atr);
      } else {
        const atr = (atrArr[atrArr.length - 1] * (period - 1) + tr) / period;
        atrArr.push(atr);
      }
    }
    // SuperTrend calculation
    let supertrend = [];
    let inUptrend = true;
    for (let i = 0; i < tfCandles.length; i++) {
      const curr = tfCandles[i];
      const atr = atrArr[i];
      const hl2 = (Number(curr.high) + Number(curr.low)) / 2;
      const upperBand = hl2 + multiplier * atr;
      const lowerBand = hl2 - multiplier * atr;
      let st;
      if (i === 0) {
        st = upperBand;
        inUptrend = true;
      } else {
        const prev = supertrend[i - 1];
        if (curr.close > prev.st) {
          st = Math.max(lowerBand, prev.st);
          inUptrend = true;
        } else if (curr.close < prev.st) {
          st = Math.min(upperBand, prev.st);
          inUptrend = false;
        } else {
          st = prev.st;
        }
      }
      supertrend.push({ st, inUptrend });
    }
    return tfCandles.map((candle, idx) => ({
      ...candle,
      [outputKey]: idx < period ? null : supertrend[idx].st,
      [`${outputKey}_trend`]: idx < period ? null : supertrend[idx].inUptrend ? 'up' : 'down',
    }));
  }

  // Default: simple SuperTrend on daily candles
  // Calculate ATR first
  let atrArr = [];
  for (let i = 0; i < candles.length; i++) {
    const curr = candles[i];
    const prev = candles[i - 1];
    const high = Number(curr.high);
    const low = Number(curr.low);
    const close = Number(curr.close);
    const prevClose = prev ? Number(prev.close) : close;
    const tr = Math.max(
      high - low,
      Math.abs(high - prevClose),
      Math.abs(low - prevClose)
    );
    if (i === 0) {
      atrArr.push(tr);
    } else if (i < period) {
      atrArr.push(tr);
    } else if (i === period) {
      const atr = atrArr.slice(1, period + 1).reduce((a, b) => a + b, 0) / period;
      atrArr.push(atr);
    } else {
      const atr = (atrArr[atrArr.length - 1] * (period - 1) + tr) / period;
      atrArr.push(atr);
    }
  }
  // SuperTrend calculation
  let supertrend = [];
  let inUptrend = true;
  for (let i = 0; i < candles.length; i++) {
    const curr = candles[i];
    const atr = atrArr[i];
    const hl2 = (Number(curr.high) + Number(curr.low)) / 2;
    const upperBand = hl2 + multiplier * atr;
    const lowerBand = hl2 - multiplier * atr;
    let st;
    if (i === 0) {
      st = upperBand;
      inUptrend = true;
    } else {
      const prev = supertrend[i - 1];
      if (curr.close > prev.st) {
        st = Math.max(lowerBand, prev.st);
        inUptrend = true;
      } else if (curr.close < prev.st) {
        st = Math.min(upperBand, prev.st);
        inUptrend = false;
      } else {
        st = prev.st;
      }
    }
    supertrend.push({ st, inUptrend });
  }
  return candles.map((candle, idx) => ({
    ...candle,
    [outputKey]: idx < period ? null : supertrend[idx].st,
    [`${outputKey}_trend`]: idx < period ? null : supertrend[idx].inUptrend ? 'up' : 'down',
  }));
}

function calculateSuperTrendFactory(timeframe, period, multiplier, outputKey = 'supertrend') {
  return (candles) => calculateSuperTrend(candles, timeframe, period, multiplier, outputKey);
}

/**
 * Pipeable function: applies a sequence of functions to the data.
 * @param {Array} data - The initial array of candles.
 * @param  {...function} fns - Functions to apply in sequence.
 * @returns {Array} The transformed data after all functions are applied.
 */
function pipe(data, ...fns) {
  return fns.reduce((acc, fn) => fn(acc), data);
}

module.exports = {
  calculateSMA,
  calculateSMAFactory,
  calculateEMA,
  calculateEMAFactory,
  calculateRSI,
  calculateRSIFactory,
  calculatePercentChange,
  calculatePercentChangeFactory,
  calculateSuperTrend,
  calculateSuperTrendFactory,
  pipe,
  aggregateCandles,
}; 