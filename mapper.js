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
 * Calculates the SMA for the given candle data and timeframe.
 * @param {Object} jsonData - The JSON object from the db (with a 'data' array).
 * @param {'daily'|'weekly'|'monthly'} timeframe - The timeframe for SMA calculation.
 * @param {number} period - Number of candles for SMA.
 * @returns {Array} New array of candles with an added 'sma' field.
 */
function calculateSMA(jsonData, timeframe, period) {
  const candles = Array.isArray(jsonData.data) ? jsonData.data : [];
  const tfCandles = aggregateCandles(candles, timeframe);
  const result = tfCandles.map((candle, idx, arr) => {
    if (idx < period - 1) {
      return { ...candle, sma: null };
    }
    const sum = arr.slice(idx - period + 1, idx + 1).reduce((acc, c) => acc + Number(c.close), 0);
    const sma = sum / period;
    return { ...candle, sma: sma };
  });
  return result;
}

/**
 * Calculates a rolling weekly SMA for each daily candle, using the last close of each of the previous (period-1) weeks plus the last close so far this week (up to the current day).
 * If there are fewer than `period` weeks, SMA is null.
 * @param {Array} dailyData - Array of daily candle objects.
 * @param {number} period - Number of weeks for the SMA.
 * @returns {Array} New array of daily candles with an added 'weeklySMA' field.
 */
function calculateRollingWeeklySMA(dailyData, period) {
  // Helper to get ISO week key
  function getWeekKey(date) {
    const d = new Date(Number(date));
    const year = d.getUTCFullYear();
    const week = getISOWeek(d);
    return `${year}-W${week}`;
  }

  // Build a map: weekKey -> { lastClose, lastIdx }
  const weekMap = new Map();
  dailyData.forEach((candle, idx) => {
    const weekKey = getWeekKey(candle.date);
    if (!weekMap.has(weekKey) || Number(candle.date) > Number(dailyData[weekMap.get(weekKey).lastIdx].date)) {
      weekMap.set(weekKey, { lastClose: candle.close, lastIdx: idx });
    }
  });
  // Build an array of weekKeys in order
  const weekKeys = Array.from(weekMap.keys());

  // For each daily candle, find the last close for the current week up to that day, and the last closes of previous (period-1) weeks
  return dailyData.map((candle, idx) => {
    const currentWeekKey = getWeekKey(candle.date);
    // Find all weekKeys up to and including the current week
    const currentWeekIdx = weekKeys.indexOf(currentWeekKey);
    if (currentWeekIdx < period - 1) {
      return { ...candle, weeklySMA: null };
    }
    // Get the last close for each of the last `period` weeks (including current)
    const relevantWeekKeys = weekKeys.slice(currentWeekIdx - period + 1, currentWeekIdx + 1);
    const closes = relevantWeekKeys.map(wk => weekMap.get(wk).lastClose).map(Number);
    // For the current week, if this candle is not the last of the week, use this candle's close instead of the week's last close
    const isLastOfWeek = weekMap.get(currentWeekKey).lastIdx === idx;
    if (!isLastOfWeek) {
      closes[closes.length - 1] = Number(candle.close);
    }
    const sma = closes.reduce((a, b) => a + b, 0) / period;
    return { ...candle, weeklySMA: sma };
  });
}

module.exports = {
  calculateSMA,
  aggregateCandles,
  calculateRollingWeeklySMA,
}; 