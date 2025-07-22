const express = require('express');
const axios = require('axios');
const fs = require('fs');
const path = require('path');
const cors = require('cors');
const qs = require('qs');
const multer = require('multer');
const { parse } = require('csv-parse');

// Configure axios defaults for better connection handling
axios.defaults.timeout = 45000; // 45 seconds default timeout
axios.defaults.httpsAgent = new (require('https').Agent)({
  keepAlive: true,
  keepAliveMsecs: 1000,
  maxSockets: 50,
  maxFreeSockets: 10,
  timeout: 60000, // active socket keepalive for 60 seconds
  freeSocketTimeout: 30000, // free socket keepalive for 30 seconds
});

// Axios retry interceptor for handling connection resets
axios.interceptors.response.use(
  response => response,
  async error => {
    const config = error.config;
    
    // Check if this is a retryable error
    const isRetryableError = 
      error.code === 'ECONNRESET' ||
      error.code === 'ETIMEDOUT' ||
      error.code === 'ECONNABORTED' ||
      error.code === 'ENOTFOUND' ||
      error.code === 'EAI_AGAIN' ||
      (error.response && error.response.status >= 500);
    
    // Set default retry count
    config.__retryCount = config.__retryCount || 0;
    const maxRetries = config.maxRetries || 3;
    
    if (isRetryableError && config.__retryCount < maxRetries) {
      config.__retryCount++;
      
      // Calculate exponential backoff delay
      const delay = Math.min(1000 * Math.pow(2, config.__retryCount - 1), 10000);
      
      console.log(`Retrying request (${config.__retryCount}/${maxRetries}) after ${delay}ms for error: ${error.code || error.message}`);
      
      // Wait for the delay
      await new Promise(resolve => setTimeout(resolve, delay));
      
      // Retry the request
      return axios(config);
    }
    
    return Promise.reject(error);
  }
);
const { parseQuery, findMatchingCandles, getQueryExamples, extractIndicatorsFromQuery, processStocksWithIndicators } = require('./services/queryService');
const { STOCK_SYMBOLS, TOTAL_SYMBOLS } = require('./stockSymbols.constants');
const { clearCache } = require('./services/indicatorCache');

const app = express();
app.use(cors());
app.use(express.json())

// Configure multer for file uploads
const upload = multer({
  dest: 'uploads/', // temporary upload directory
  limits: {
    fileSize: 10 * 1024 * 1024 // 10MB limit
  },
  fileFilter: (req, file, cb) => {
    // Accept only CSV files
    if (file.mimetype === 'text/csv' || file.originalname.endsWith('.csv')) {
      cb(null, true);
    } else {
      cb(new Error('Only CSV files are allowed'), false);
    }
  }
});

// Ensure uploads directory exists
const uploadsDir = path.join(__dirname, 'uploads');
if (!fs.existsSync(uploadsDir)) {
  fs.mkdirSync(uploadsDir, { recursive: true });
}

const port = 3000;

process.on('uncaughtException', (err) => {
  console.error('Uncaught Exception:', err);
});
process.on('unhandledRejection', (reason, promise) => {
  console.error('Unhandled Rejection:', reason);
});

// Enum for days of the week
const DayOfWeek = Object.freeze({
  0: 'Sunday',
  1: 'Monday',
  2: 'Tuesday',
  3: 'Wednesday',
  4: 'Thursday',
  5: 'Friday',
  6: 'Saturday',
});

function getDayOfWeekName(timestamp) {
  if (!timestamp) return null;
  const date = new Date(Number(timestamp));
  return DayOfWeek[date.getUTCDay()];
}

function getNextDayTimestamp(dateString) {
  try {
    if (typeof dateString !== 'number') {
      const parsed = Number(dateString);
      if (isNaN(parsed)) return null;
      return parsed + 19800000;
    }
    return dateString + 19800000;
  } catch (err) {
    console.error("Error in getNextDayTimestamp:", err);
    return null;
  }
}

// ENDPOINTS START HERE

// Chartink API endpoint
app.post('/chartink-api', async (req, res) => {
  try {
    const { payload } = req.body;
    const size = 2000; // Hardcoded size
    if (!payload || !Array.isArray(payload) || payload.length === 0) {
      return res.status(400).json({ error: "Invalid or missing payload" });
    }
    // Ensure the directory exists
    const dirPath = path.join(__dirname, 'db');
    if (!fs.existsSync(dirPath)) {
      fs.mkdirSync(dirPath, { recursive: true });
    }
    // For each symbol, fetch data, map it, and save to JSON file if not already present
    const promises = payload.map(async (arr) => {
      try {
        const symbol = arr && arr[1];
        const dateStr = arr && arr[0];
        if (!symbol) throw new Error("Invalid symbol in payload");
        const fileName = `${symbol}.json`;
        const filePath = path.join(dirPath, fileName);
        if (fs.existsSync(filePath)) {
          fs.unlinkSync(filePath);
        }
        const queryString = "select high, low, open, close, volume";
        const data = qs.stringify({
          query: queryString,
          use_live: 1,
          limit: 1,
          size: size * 10,
          widget_id: -1,
          end_time: -1,
          timeframe: "Daily",
          symbol: symbol,
          scan_link: "scanlink:b6b0c6620714e44ab63d271d0ddbd498"
        });
        const response = await axios.post('https://chartink.com/oapi', data, {
          headers: {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8,la;q=0.7',
            'content-type': 'application/x-www-form-urlencoded',
            'cookie': '_ga=GA1.2.827081830.1738516382; _gid=GA1.2.158232909.1738612317; XSRF-TOKEN=eyJpdiI6IjVrL2dLek8rSVE4aGFTWWllazd6cHc9PSIsInZhbHVlIjoiQmVUcmlLb0Z2dk9uYVlPeUpJL3d1OTQ0MTdvcUpWZGt6V2tEaHpEeUJidGJVOENDeFpYbnJiaVgxV3NielhMbjBGUzlTVmNuektCaHhTb0V3MFVnS1VUbWZRVCtEYXFxYlhrYzZ4eWpnY2RuZjltSlJJd1NaUkE4dlFTbVA5aDkiLCJtYWMiOiJkYzM1YzY2YTIwOTM5NTQzODNjMzNkMDZiNWMwY2NkNzc5MDQ5OTFmOGJlMTgwMzJmYjM1NDdmNTFjNzAyOGY2IiwidGFnIjoiIn0%3D; ci_session=eyJpdiI6InVrKzF5dXE4b2lzazMxU2lQWkJMN0E9PSIsInZhbHVlIjoiTzdMOHNsZDFJZ1dYd0JxT2EyQ0NVZGIvNUZUdmJsOHFtSXZuc002bnBrck5RSmVpS1NIRTZUUTZjWU9NVTNOcmM0SmtOSnF5UVI0cGVlU2VrNGJCM3Y2NkhKdTBvdWJlVEZzS3k2VDdtNGRDbzJqemo5M3gzbVFWaXEzQWFkbjAiLCJtYWMiOiI2YjYzMzI5N2UwOTZmYTM3OTNlNWMwNzk1NmFjY2E4MTdlMzQxNGVjYzIxMDUxOWE1ODkyYTg1MTM1NTU2NjJjIiwidGFnIjoiIn0%3D',
            'dnt': '1',
            'origin': 'https://chartink.com',
            'priority': 'u=1, i',
            'referer': 'https://chartink.com/screener/copy-double-volume-563',
            'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
            'x-xsrf-token': 'eyJpdiI6IjVrL2dLek8rSVE4aGFTWWllazd6cHc9PSIsInZhbHVlIjoiQmVUcmlLb0Z2dk9uYVlPeUpJL3d1OTQ0MTdvcUpWZGt6V2tEaHpEeUJidGJVOENDeFpYbnJiaVgxV3NielhMbjBGUzlTVmNuektCaHhTb0V3MFVnS1VUbWZRVCtEYXFxYlhrYzZ4eWpnY2RuZjltSlJJd1NaUkE4dlFTbVA5aDkiLCJtYWMiOiJkYzM1YzY2YTIwOTM5NTQzODNjMzNkMDZiNWMwY2NkNzc5MDQ5OTFmOGJlMTgwMzJmYjM1NDdmNTFjNzAyOGY2IiwidGFnIjoiIn0=',
          },
          timeout: 45000, // 45 second timeout
          maxRetries: 3, // Enable retries for this request
        });
        // Map the data as in the original logic, but with the required structure
        const groupData = response?.data?.groupData?.[0]?.results;
        const metaData = response?.data?.metaData?.[0]?.tradeTimes;
        let mappedData = [];
        if (groupData && metaData) {
          const highs = groupData[0]?.high || [];
          const lows = groupData[1]?.low || [];
          const opens = groupData[2]?.open || [];
          const closes = groupData[3]?.close || [];
          const volumes = groupData[4]?.volume || [];
          highs.forEach((element, idx) => {
            if(idx < metaData.length){
              mappedData.push( {
                open: opens[idx] !== undefined && opens[idx] !== null ? String(opens[idx]) : '',
                low: lows[idx] !== undefined && lows[idx] !== null ? String(lows[idx]) : '',
                high: highs[idx] !== undefined && highs[idx] !== null ? String(highs[idx]) : '',
                close: closes[idx] !== undefined && closes[idx] !== null ? String(closes[idx]) : '',
                volume: volumes[idx] !== undefined && volumes[idx] !== null ? String(volumes[idx]) : null,
                date: metaData[idx] !== undefined && metaData[idx] !== null ? String(getNextDayTimestamp(metaData[idx])) : '',
                day: metaData[idx] !== undefined && metaData[idx] !== null ? getDayOfWeekName(getNextDayTimestamp(metaData[idx])) : ''
              })
            }
          });
        }
        fs.writeFileSync(filePath, JSON.stringify({ data: mappedData }, null, 2), 'utf8');
      } catch (err) {
        // Optionally log error, but continue
        console.error(`Error processing symbol: ${arr && arr[1]}`, err.message);
      }
    });
    await Promise.all(promises);
    res.json({ success: true });
  } catch (error) {
    console.error("Error:", error);
    res.status(500).json({ error: "Internal server error", details: error.message });
  }
});

// Global progress state for the current query

let currentProgress = {
  isRunning: false,
  phase: 'idle',
  message: '',
  processed: 0,
  total: TOTAL_SYMBOLS, // Total stocks to process
  matches: 0,
  percentage: 0,
  startTime: null
};

// Query abortion mechanism
let currentQueryAbortController = null;
let isQueryAborted = false;


// Test endpoint
app.get('/test', (req, res) => {
  console.log('Test endpoint called');
  res.json({ message: 'Test endpoint working', timestamp: new Date().toISOString() });
});


// Simple progress endpoint - truly non-blocking
app.get('/query/progress', async (req, res) => {
  try {
    // Calculate percentage based on processed stocks (22 stocks = 1%)
    const percentage = currentProgress.total > 0 ? 
      Math.floor((currentProgress.processed / 22)) : 0;
    
    const response = {
      ...currentProgress,
      percentage: Math.min(percentage, 100) // Cap at 100%
    };
    
    console.log('Progress endpoint called, current progress:', response);
    
    // Set CORS headers explicitly
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Methods', 'GET');
    res.header('Access-Control-Allow-Headers', 'Content-Type');
    
    res.json(response);
  } catch (error) {
    console.error('Progress endpoint error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Store SSE connections for progress updates
const sseConnections = new Set();

// Helper function to update progress
function updateProgress(updates) {
  currentProgress = { ...currentProgress, ...updates };
  
  // Don't auto-calculate percentage here - it's calculated in the progress endpoint
  // using the formula: 22 stocks = 1%
  
  // Send progress updates to all SSE connections
  const progressData = {
    ...currentProgress,
    percentage: currentProgress.total > 0 ? 
      Math.floor((currentProgress.processed / currentProgress.total) * 100) : 0
  };
  
  const message = `data: ${JSON.stringify(progressData)}\n\n`;
  sseConnections.forEach(res => {
    res.write(message);
  });
}

// Make updateProgress globally accessible for queryService
global.updateProgress = updateProgress;


// Function to delete mappedStorage directory completely (DEPRECATED - no longer used)
// We now overwrite files instead of deleting the directory to avoid file handle issues
function deleteMappedStorageDir() {
  console.log('deleteMappedStorageDir called but no longer used - files are overwritten instead');
}

// Synchronous version for use at end of request (DEPRECATED - no longer used)  
// We now overwrite files instead of deleting the directory to avoid file handle issues
function deleteMappedStorageDirSync() {
  console.log('deleteMappedStorageDirSync called but no longer used - files are overwritten instead');
}

// Function to abort current query
function abortCurrentQuery() {
  if (currentQueryAbortController) {
    currentQueryAbortController.abort();
    console.log('Previous query aborted');
  }
  isQueryAborted = true;
}

// Function to generate JSON for a single stock with indicators
async function generateStockJSON(stock, requiredIndicators, requiredTimeframes = ['daily']) {
  try {
    // This function will process a single stock and generate its JSON with indicators
    // Pass the new format with indicators and timeframes
    await processStocksWithIndicators({
      indicators: requiredIndicators,
      timeframes: requiredTimeframes
    }, [stock]);
  } catch (error) {
    console.error(`Error generating JSON for ${stock}:`, error);
    throw error;
  }
}


// Function to check if indicators are precalculated
function checkPrecalculatedIndicators(requiredIndicators, requiredTimeframes) {
  if (precalculatedIndicators.status !== 'completed') {
    return {
      available: false,
      reason: `Precalculated indicators status: ${precalculatedIndicators.status}`,
      missing: requiredIndicators.map(i => `${requiredTimeframes[0] || 'daily'}_${i.name}_${i.period}`)
    };
  }
  
  // Check if all required indicators are available in precalculated storage
  const missing = [];
  const precalculatedDir = path.join(__dirname, 'precalculatedStorage');
  
  if (!fs.existsSync(precalculatedDir)) {
    return {
      available: false,
      reason: 'Precalculated storage directory not found',
      missing: requiredIndicators.map(i => `${requiredTimeframes[0] || 'daily'}_${i.name}_${i.period}`)
    };
  }
  
  // Define basic OHLC and volume fields that are always available
  const basicFields = [
    'open', 'high', 'low', 'close', 'volume', 
    'weekly_open', 'weekly_high', 'weekly_low', 'weekly_close', 'weekly_volume',
    'monthly_open', 'monthly_high', 'monthly_low', 'monthly_close', 'monthly_volume'
  ];
  
  // Check if precalculated indicators include all required ones
  for (const indicator of requiredIndicators) {
    for (const timeframe of requiredTimeframes) {
      const indicatorKey = `${timeframe}_${indicator.name}_${indicator.period}`;
      
      // Skip checking basic OHLC fields as they are always available
      if (basicFields.includes(indicator.name)) {
        continue;
      }
      
      const found = precalculatedIndicators.indicators.some(pi => {
        const piKey = `${pi.timeframe}_${pi.name}_${pi.params.period || 14}`;
        return piKey === indicatorKey;
      });
      
      if (!found) {
        missing.push(indicatorKey);
      }
    }
  }
  
  return {
    available: missing.length === 0,
    reason: missing.length === 0 ? 'All indicators available' : 'Some indicators missing',
    missing: missing
  };
}

// Query endpoint for searching stocks based on conditions
app.post('/query',  async (req, res) => {
  try {
    const { query, stocks } = req.body;
    
    if (!query) {
      return res.status(400).json({ error: 'Query is required' });
    }

    // Abort any existing query
    abortCurrentQuery();
    
    // Create new abort controller for this query
    currentQueryAbortController = new AbortController();
    isQueryAborted = false;
    
    // Reset progress for new query
    updateProgress({
      isRunning: true,
      phase: 'initializing',
      message: 'Starting query processing...',
      processed: 0,
      total: TOTAL_SYMBOLS,
      matches: 0,
      startTime: Date.now()
    });
    
    console.log(`Processing query: ${query}`);
    
    // Parse the query
    let parsedQuery;
    try {
      parsedQuery = parseQuery(query);
    } catch (error) {
      updateProgress({ isRunning: false, phase: 'error', message: 'Invalid query format' });
      return res.status(400).json({ 
        error: 'Invalid query format', 
        details: error.message,
        hint: 'Example: "rsi(14) > 70 and sma(20) < close"'
      });
    }
    
    // Extract indicators from the query
    let indicatorsData = extractIndicatorsFromQuery(parsedQuery);
    let requiredIndicators = indicatorsData.indicators;
    let requiredTimeframes = indicatorsData.timeframes;
    console.log('Parsed query conditions:', JSON.stringify(parsedQuery.conditions, null, 2));
    console.log('Required indicators:', requiredIndicators);
    console.log('Required timeframes:', requiredTimeframes);
    console.log('Number of required indicators:', requiredIndicators.length);
    
    // Ensure we always have indicators for precalculatedStorage generation
    if (requiredIndicators.length === 0) {
      console.log('No indicators found by extraction, manually parsing query conditions...');
      
      // Extract required fields from the parsed query conditions
      const requiredFields = new Set();
      for (const condition of parsedQuery.conditions) {
        if (condition.left.type === 'field') {
          requiredFields.add(condition.left.field);
        }
        if (condition.right.type === 'field') {
          requiredFields.add(condition.right.field);
        }
        if (condition.left.type === 'indicator') {
          requiredFields.add(condition.left.name);
        }
        if (condition.right.type === 'indicator') {
          requiredFields.add(condition.right.name);
        }
        // Handle dynamic_indicator type (e.g., daily_rsi_14)
        if (condition.left.type === 'dynamic_indicator') {
          requiredIndicators.push({
            name: condition.left.name,
            period: parseInt(condition.left.params[0]) || 14,
            params: {}
          });
          if (!requiredTimeframes.includes(condition.left.timeframe)) {
            requiredTimeframes.push(condition.left.timeframe);
          }
        }
        if (condition.right.type === 'dynamic_indicator') {
          requiredIndicators.push({
            name: condition.right.name,
            period: parseInt(condition.right.params[0]) || 14,
            params: {}
          });
          if (!requiredTimeframes.includes(condition.right.timeframe)) {
            requiredTimeframes.push(condition.right.timeframe);
          }
        }
      }
      
      // Convert fields to indicators
      requiredIndicators = Array.from(requiredFields).map(field => ({
        name: field,
        period: 1,
        params: {}
      }));
      requiredTimeframes = ['daily']; // Default to daily if no indicators found
      
      console.log('Manually extracted indicators:', requiredIndicators);
    }
    
    // Check if indicators are precalculated
    const precalculatedCheck = checkPrecalculatedIndicators(requiredIndicators, requiredTimeframes);
    
    if (!precalculatedCheck.available) {
      updateProgress({ isRunning: false, phase: 'error', message: 'Missing precalculated indicators' });
      return res.status(400).json({ 
        error: 'Missing precalculated indicators', 
        details: precalculatedCheck.reason,
        missingIndicators: precalculatedCheck.missing,
        hint: 'Please go to the precalculated indicators screen and add the missing indicators, then regenerate before running this query.'
      });
    }
    
    console.log('✅ All required indicators are precalculated, proceeding with query...');
    
    // Process stocks with real-time progress tracking
    const allMatches = [];
    const errors = [];
    let processedCount = 0;
    const processingStart = Date.now();
    
    // Get stock list from constants
    let stockList = stocks || STOCK_SYMBOLS;
    const totalStocks = TOTAL_SYMBOLS;
    
    console.log(`Processing ${stockList.length} stocks with indicators and analyzing...`);
    
    updateProgress({ 
      phase: 'processing_and_analyzing', 
      message: 'Processing indicators and analyzing...', 
      processed: 0, 
      total: totalStocks 
    });
    
    // Process each stock: generate JSON → analyze → update progress
    for (const stock of stockList) {
      if (isQueryAborted) {
        console.log('Query was aborted during processing');
        return res.status(400).json({ error: 'Query was aborted' });
      }
      
      try {
        // First check if stock data exists in db folder
        const dbFilePath = path.join(__dirname, 'db', `${stock}.json`);
        if (!fs.existsSync(dbFilePath)) {
          errors.push({ stock, error: 'Stock data not found in db' });
          processedCount++;
          updateProgress({ 
            phase: 'processing_and_analyzing', 
            message: `Processing: ${processedCount}/${totalStocks} stocks, ${allMatches.length} matches found`, 
            processed: processedCount, 
            total: totalStocks,
            matches: allMatches.length
          });
          continue;
        }
        
        // Use precalculated storage instead of generating new indicators
        console.log(`Using precalculated indicators for ${stock}`);
        
        // Read the precalculated mapped data from precalculatedStorage
        const precalculatedFilePath = path.join(__dirname, 'precalculatedStorage', `${stock}_piped.json`);
        let candles;
        
        if (fs.existsSync(precalculatedFilePath)) {
          const mappedData = JSON.parse(fs.readFileSync(precalculatedFilePath, 'utf8'));
          candles = mappedData.data;
        } else {
          errors.push({ stock, error: 'Precalculated data not found for this stock' });
          continue;
        }
        
        if (candles && candles.length > 0) {
          // Find matching candles for backtesting
          const matches = findMatchingCandles(candles, parsedQuery, stock);
          allMatches.push(...matches);
        } else {
          errors.push({ stock, error: 'No candle data available' });
        }
        
        processedCount++;
        
        // Update progress for each stock
        updateProgress({ 
          phase: 'processing_and_analyzing', 
          message: `Processing: ${processedCount}/${totalStocks} stocks, ${allMatches.length} matches found`, 
          processed: processedCount, 
          total: totalStocks,
          matches: allMatches.length
        });
        
        // Yield control to event loop every 5 stocks
        if (processedCount % 5 === 0) {
          await new Promise(resolve => setImmediate(resolve));
        }
        
        // Log progress every 100 stocks
        if (processedCount % 100 === 0) {
          console.log(`Processed ${processedCount}/${stockList.length} stocks, found ${allMatches.length} matches so far...`);
        }
        
      } catch (error) {
        errors.push({ stock, error: error.message });
        processedCount++;
        
        // Update progress even for errors
        updateProgress({ 
          phase: 'processing_and_analyzing', 
          message: `Processing: ${processedCount}/${stockList.length} stocks, ${allMatches.length} matches found`, 
          processed: processedCount, 
          total: stockList.length,
          matches: allMatches.length
        });
      }
    }
    
    if (isQueryAborted) {
      console.log('Query was aborted during processing');
      return res.status(400).json({ error: 'Query was aborted' });
    }
    
    // Sort matches by date (most recent first)
    allMatches.sort((a, b) => parseInt(b.date) - parseInt(a.date));
    
    const processingTime = Date.now() - processingStart;
    console.log(`Query processing completed in ${processingTime}ms. Found ${allMatches.length} matches across ${processedCount} stocks.`);
    
    // Update completion progress
    updateProgress({ 
      phase: 'completed', 
      message: `Completed: Found ${allMatches.length} matches`, 
      processed: processedCount, 
      total: totalStocks,
      matches: allMatches.length,
      isRunning: false
    });
    
    // Note: We no longer delete the precalculatedStorage directory
    // Files are overwritten on each query for fresh calculations
    
    res.json({
      success: true,
      query: query,
      parsedQuery: {
        conditions: parsedQuery.conditions.map(c => ({
          left: c.left,
          operator: c.operator,
          right: c.right
        })),
        logicalOperators: parsedQuery.logicalOperators
      },
      requiredIndicators: requiredIndicators,
      totalMatches: allMatches.length,
      matches: allMatches,
      errors: errors.length > 0 ? errors : undefined,
      processedStocks: processedCount
    });
    
  } catch (error) {
    console.error('Query endpoint error:', error);
    
    // Update progress to show error state
    updateProgress({ 
      phase: 'error', 
      message: 'Query processing failed', 
      isRunning: false
    });
    
    // Note: We no longer delete the precalculatedStorage directory on error
    // Files are overwritten on each query for fresh calculations
    
    res.status(500).json({ 
      error: 'Internal server error', 
      details: error.message 
    });
  }
});

// Latest day scan endpoint - only checks the most recent candle
app.post('/query/latest',  async (req, res) => {
  try {
    const { query, stocks } = req.body;
    
    if (!query) {
      return res.status(400).json({ error: 'Query is required' });
    }

    // Abort any existing query
    abortCurrentQuery();
    
    // Create new abort controller for this query
    currentQueryAbortController = new AbortController();
    isQueryAborted = false;
    
    // Reset progress for new query
    updateProgress({
      isRunning: true,
      phase: 'initializing',
      message: 'Starting latest day scan...',
      processed: 0,
      total: TOTAL_SYMBOLS,
      matches: 0,
      startTime: Date.now()
    });
    
    console.log(`Processing latest day scan: ${query}`);
    
    // Parse the query
    let parsedQuery;
    try {
      parsedQuery = parseQuery(query);
    } catch (error) {
      updateProgress({ isRunning: false, phase: 'error', message: 'Invalid query format' });
      return res.status(400).json({ 
        error: 'Invalid query format', 
        details: error.message,
        hint: 'Example: "rsi(14) > 70 and sma(20) < close"'
      });
    }
    
    // Extract indicators from the query
    let indicatorsData = extractIndicatorsFromQuery(parsedQuery);
    let requiredIndicators = indicatorsData.indicators;
    let requiredTimeframes = indicatorsData.timeframes;
    console.log('Required indicators for latest day scan:', requiredIndicators);
    console.log('Required timeframes:', requiredTimeframes);
    
    // Ensure we always have indicators for precalculatedStorage generation
    if (requiredIndicators.length === 0) {
      console.log('No indicators found by extraction, manually parsing query conditions...');
      
      // Extract required fields from the parsed query conditions
      const requiredFields = new Set();
      for (const condition of parsedQuery.conditions) {
        if (condition.left.type === 'field') {
          requiredFields.add(condition.left.field);
        }
        if (condition.right.type === 'field') {
          requiredFields.add(condition.right.field);
        }
        if (condition.left.type === 'indicator') {
          requiredFields.add(condition.left.name);
        }
        if (condition.right.type === 'indicator') {
          requiredFields.add(condition.right.name);
        }
        // Handle dynamic_indicator type (e.g., daily_rsi_14)
        if (condition.left.type === 'dynamic_indicator') {
          requiredIndicators.push({
            name: condition.left.name,
            period: parseInt(condition.left.params[0]) || 14,
            params: {}
          });
          if (!requiredTimeframes.includes(condition.left.timeframe)) {
            requiredTimeframes.push(condition.left.timeframe);
          }
        }
        if (condition.right.type === 'dynamic_indicator') {
          requiredIndicators.push({
            name: condition.right.name,
            period: parseInt(condition.right.params[0]) || 14,
            params: {}
          });
          if (!requiredTimeframes.includes(condition.right.timeframe)) {
            requiredTimeframes.push(condition.right.timeframe);
          }
        }
      }
      
      // Convert fields to indicators
      requiredIndicators = Array.from(requiredFields).map(field => ({
        name: field,
        period: 1,
        params: {}
      }));
    }
    
    // Check if indicators are precalculated
    const precalculatedCheck = checkPrecalculatedIndicators(requiredIndicators, requiredTimeframes);
    
    if (!precalculatedCheck.available) {
      updateProgress({ isRunning: false, phase: 'error', message: 'Missing precalculated indicators' });
      return res.status(400).json({ 
        error: 'Missing precalculated indicators', 
        details: precalculatedCheck.reason,
        missingIndicators: precalculatedCheck.missing,
        hint: 'Please go to the precalculated indicators screen and add the missing indicators, then regenerate before running this query.'
      });
    }
    
    console.log('✅ All required indicators are precalculated, proceeding with latest day scan...');
    
    // Process stocks for latest day only
    const allMatches = [];
    const errors = [];
    let processedCount = 0;
    const processingStart = Date.now();
    
    // Get stock list from constants
    let stockList = stocks || STOCK_SYMBOLS;
    const totalStocks = TOTAL_SYMBOLS;
    
    console.log(`Processing ${stockList.length} stocks for latest day scan...`);
    
    updateProgress({ 
      phase: 'processing_and_analyzing', 
      message: 'Scanning latest day...', 
      processed: 0, 
      total: totalStocks 
    });
    
    // Process each stock but only check the latest candle
    for (const stock of stockList) {
      if (isQueryAborted) {
        console.log('Query was aborted during processing');
        return res.status(400).json({ error: 'Query was aborted' });
      }
      
      try {
        // First check if stock data exists in db folder
        const dbFilePath = path.join(__dirname, 'db', `${stock}.json`);
        if (!fs.existsSync(dbFilePath)) {
          errors.push({ stock, error: 'Stock data not found in db' });
          processedCount++;
          updateProgress({ 
            phase: 'processing_and_analyzing', 
            message: `Scanning: ${processedCount}/${totalStocks} stocks, ${allMatches.length} matches found`, 
            processed: processedCount, 
            total: totalStocks,
            matches: allMatches.length
          });
          continue;
        }
        
        // Use precalculated storage for latest day scan
        console.log(`Using precalculated indicators for latest day scan: ${stock}`);
        
        // Read the precalculated mapped data from precalculatedStorage
        const precalculatedFilePath = path.join(__dirname, 'precalculatedStorage', `${stock}_piped.json`);
        let candles;
        
        if (fs.existsSync(precalculatedFilePath)) {
          const mappedData = JSON.parse(fs.readFileSync(precalculatedFilePath, 'utf8'));
          candles = mappedData.data;
        } else {
          errors.push({ stock, error: 'Precalculated data not found for this stock' });
          continue;
        }
        
        if (candles && candles.length > 0) {
          // Only check the latest candle
          const latestCandle = candles[candles.length - 1];
          const prevCandle = candles[candles.length - 2];
          
          if (latestCandle.close) {
            try {
              // Import the evaluation functions
              const { evaluateAllConditions } = require('./services/queryService');
              
              if (evaluateAllConditions(parsedQuery, latestCandle, prevCandle, candles, candles.length - 1)) {
                // Extract indicator values for tooltip display
                const indicatorValues = {};
                
                // Get all fields used in the query
                const allFields = new Set();
                function extractFields(conditions) {
                  if (Array.isArray(conditions)) {
                    conditions.forEach(condition => {
                      if (condition.left && condition.left.fieldKey) {
                        allFields.add(condition.left.fieldKey);
                      }
                      if (condition.right && condition.right.fieldKey) {
                        allFields.add(condition.right.fieldKey);
                      }
                      if (condition.conditions) extractFields(condition.conditions);
                    });
                  }
                }
                extractFields(parsedQuery.conditions);
                
                // Add all indicator values that exist in the candle data
                for (const field of allFields) {
                  if (latestCandle[field] !== undefined && latestCandle[field] !== null) {
                    indicatorValues[field] = latestCandle[field];
                  }
                }
                
                // Also include common indicators
                const commonIndicators = [
                  'daily_rsi_14', 'weekly_rsi_14', 'monthly_rsi_14',
                  'daily_sma_20', 'weekly_sma_20', 'monthly_sma_20',
                  'daily_ema_20', 'weekly_ema_20', 'monthly_ema_20'
                ];
                
                commonIndicators.forEach(indicator => {
                  if (latestCandle[indicator] !== undefined && latestCandle[indicator] !== null) {
                    indicatorValues[indicator] = latestCandle[indicator];
                  }
                });
                
                allMatches.push({
                  date: latestCandle.date,
                  day: latestCandle.day,
                  timestamp: new Date(parseInt(latestCandle.date)).toISOString(),
                  stock: stock,
                  close: latestCandle.close,
                  matchedConditions: query,
                  indicators: indicatorValues // Include actual calculated values
                });
              }
            } catch (error) {
              console.error(`Error evaluating latest candle for ${stock}:`, error.message);
            }
          }
        } else {
          errors.push({ stock, error: 'No candle data available' });
        }
        
        processedCount++;
        
        // Update progress for each stock
        updateProgress({ 
          phase: 'processing_and_analyzing', 
          message: `Scanning: ${processedCount}/${totalStocks} stocks, ${allMatches.length} matches found`, 
          processed: processedCount, 
          total: totalStocks,
          matches: allMatches.length
        });
        
        // Yield control to event loop every 10 stocks
        if (processedCount % 10 === 0) {
          await new Promise(resolve => setImmediate(resolve));
        }
        
        // Log progress every 100 stocks
        if (processedCount % 100 === 0) {
          console.log(`Scanned ${processedCount}/${stockList.length} stocks, found ${allMatches.length} matches so far...`);
        }
        
      } catch (error) {
        errors.push({ stock, error: error.message });
        processedCount++;
        
        // Update progress even for errors
        updateProgress({ 
          phase: 'processing_and_analyzing', 
          message: `Scanning: ${processedCount}/${stockList.length} stocks, ${allMatches.length} matches found`, 
          processed: processedCount, 
          total: stockList.length,
          matches: allMatches.length
        });
      }
    }
    
    if (isQueryAborted) {
      console.log('Query was aborted during processing');
      return res.status(400).json({ error: 'Query was aborted' });
    }
    
    // Sort matches by stock name for consistent ordering
    allMatches.sort((a, b) => a.stock.localeCompare(b.stock));
    
    const processingTime = Date.now() - processingStart;
    console.log(`Latest day scan completed in ${processingTime}ms. Found ${allMatches.length} matches across ${processedCount} stocks.`);
    
    // Update completion progress
    updateProgress({ 
      phase: 'completed', 
      message: `Completed: Found ${allMatches.length} matches for latest day`, 
      processed: processedCount, 
      total: totalStocks,
      matches: allMatches.length,
      isRunning: false
    });
    
    res.json({
      success: true,
      query: query,
      scanType: 'latest_day',
      parsedQuery: {
        conditions: parsedQuery.conditions.map(c => ({
          left: c.left,
          operator: c.operator,
          right: c.right
        })),
        logicalOperators: parsedQuery.logicalOperators
      },
      requiredIndicators: requiredIndicators,
      totalMatches: allMatches.length,
      matches: allMatches,
      errors: errors.length > 0 ? errors : undefined,
      processedStocks: processedCount
    });
    
  } catch (error) {
    console.error('Latest day scan endpoint error:', error);
    
    // Update progress to show error state
    updateProgress({ 
      phase: 'error', 
      message: 'Latest day scan failed', 
      isRunning: false
    });
    
    res.status(500).json({ 
      error: 'Internal server error', 
      details: error.message 
    });
  }
});

// Health check endpoint
app.get('/health', async (req, res) => {
  res.json({ status: 'ok', message: 'Server is running' });
});

// Query examples endpoint
app.get('/query/examples', async (req, res) => {
  res.json(getQueryExamples());
});

// ==================== PRECALCULATED INDICATORS ENDPOINTS ====================

// Precalculated indicators storage
let precalculatedIndicators = {
  indicators: [],
  lastUpdated: null,
  status: 'idle' // idle, processing, completed, error
};

// File path for persisting precalculated indicators configuration
const PRECALCULATED_CONFIG_FILE = path.join(__dirname, 'precalculatedIndicators.json');

// Function to load precalculated indicators from file
function loadPrecalculatedIndicators() {
  try {
    if (fs.existsSync(PRECALCULATED_CONFIG_FILE)) {
      const data = fs.readFileSync(PRECALCULATED_CONFIG_FILE, 'utf8');
      const config = JSON.parse(data);
      precalculatedIndicators = {
        indicators: config.indicators || [],
        lastUpdated: config.lastUpdated || null,
        status: config.status || 'idle'
      };
      console.log(`📊 Loaded ${precalculatedIndicators.indicators.length} precalculated indicators from file`);
    } else {
      console.log('📊 No precalculated indicators file found, starting with empty configuration');
    }
  } catch (error) {
    console.error('Error loading precalculated indicators:', error);
    precalculatedIndicators = {
      indicators: [],
      lastUpdated: null,
      status: 'idle'
    };
  }
}

// Function to save precalculated indicators to file
function savePrecalculatedIndicators() {
  try {
    const data = JSON.stringify(precalculatedIndicators, null, 2);
    fs.writeFileSync(PRECALCULATED_CONFIG_FILE, data, 'utf8');
    console.log(`💾 Saved ${precalculatedIndicators.indicators.length} precalculated indicators to file`);
  } catch (error) {
    console.error('Error saving precalculated indicators:', error);
  }
}

// Load precalculated indicators on server startup
loadPrecalculatedIndicators();

// POST /api/precalculate-indicators - Calculate and store indicators
app.post('/api/precalculate-indicators', async (req, res) => {
  try {
    const { indicators } = req.body;
    
    if (!Array.isArray(indicators) || indicators.length === 0) {
      return res.status(400).json({ 
        error: 'Invalid indicators array. Expected array with at least one indicator configuration.' 
      });
    }
    
    // Validate indicator format
    for (const indicator of indicators) {
      if (!indicator.timeframe || !indicator.name || !indicator.params) {
        return res.status(400).json({ 
          error: 'Invalid indicator format. Each indicator must have timeframe, name, and params.' 
        });
      }
    }
    
    console.log('🔄 Starting precalculation for indicators:', indicators);
    
    // Update status
    precalculatedIndicators.status = 'processing';
    precalculatedIndicators.indicators = indicators;
    precalculatedIndicators.lastUpdated = new Date().toISOString();
    
    // Save to file
    savePrecalculatedIndicators();
    
    // Send immediate response
    res.json({
      success: true,
      message: 'Precalculation started',
      indicators: indicators,
      status: 'processing'
    });
    
    // Initialize progress state for precalculation
    updateProgress({
      isRunning: true,
      phase: 'processing_indicators',
      message: 'Starting indicator processing...',
      processed: 0,
      total: 0,
      matches: 0,
      startTime: Date.now()
    });
    
    // Process indicators in background
    processPrecalculatedIndicators(indicators);
    
  } catch (error) {
    console.error('Precalculate indicators error:', error);
    precalculatedIndicators.status = 'error';
    precalculatedIndicators.lastUpdated = new Date().toISOString();
    
    // Save to file
    savePrecalculatedIndicators();
    
    res.status(500).json({ 
      error: 'Internal server error', 
      details: error.message 
    });
  }
});

// GET /api/get-precalculated-indicators - Get current precalculated indicators
app.get('/api/get-precalculated-indicators', async (req, res) => {
  try {
    res.json({
      success: true,
      indicators: precalculatedIndicators.indicators,
      status: precalculatedIndicators.status,
      lastUpdated: precalculatedIndicators.lastUpdated
    });
  } catch (error) {
    console.error('Get precalculated indicators error:', error);
    res.status(500).json({ 
      error: 'Internal server error', 
      details: error.message 
    });
  }
});

// SSE endpoint for real-time progress updates
app.get('/api/progress-stream', (req, res) => {
  // Set headers for SSE
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Access-Control-Allow-Origin': '*'
  });

  // Send initial connection message
  res.write('data: {"connected": true}\n\n');

  // Add to active connections
  sseConnections.add(res);

  // Send current progress immediately
  const progressData = {
    ...currentProgress,
    percentage: currentProgress.total > 0 ? 
      Math.floor((currentProgress.processed / currentProgress.total) * 100) : 0
  };
  res.write(`data: ${JSON.stringify(progressData)}\n\n`);

  // Handle client disconnect
  req.on('close', () => {
    sseConnections.delete(res);
  });
});

// Background function to process precalculated indicators
async function processPrecalculatedIndicators(indicators) {
  try {
    console.log('📊 Processing precalculated indicators for all stocks...');
    
    // Create dedicated precalculated storage directory
    const precalculatedDir = path.join(__dirname, 'precalculatedStorage');
    if (!fs.existsSync(precalculatedDir)) {
      fs.mkdirSync(precalculatedDir, { recursive: true });
    }
    
    // Convert indicators to the format expected by processStocksWithIndicators
    const formattedIndicators = indicators.map(indicator => {
      const params = indicator.params || {};
      
      // Handle different indicator types
      switch(indicator.name.toLowerCase()) {
        case 'sma':
          return {
            name: 'sma',
            period: params.period || 20,
            params: {},
            timeframe: indicator.timeframe
          };
        case 'ema':
          return {
            name: 'ema', 
            period: params.period || 20,
            params: {},
            timeframe: indicator.timeframe
          };
        case 'rsi':
          return {
            name: 'rsi',
            period: params.period || 14,
            params: {},
            timeframe: indicator.timeframe
          };
        case 'bollinger':
        case 'bb':
          return {
            name: 'bollinger',
            period: params.period || 20,
            params: {
              stdDev: params.stdDev || 2
            },
            timeframe: indicator.timeframe
          };
        case 'volume':
          return {
            name: 'volume',
            period: 1,
            params: {},
            timeframe: indicator.timeframe
          };
        case 'pctchg':
        case 'percent_change':
        case 'pct_change':
        case '%_change':
          return {
            name: 'pctchg',
            period: params.period || 1,
            params: {},
            timeframe: indicator.timeframe
          };
        default:
          return {
            name: indicator.name,
            period: params.period || 14,
            params: params,
            timeframe: indicator.timeframe
          };
      }
    });
    
    // Extract unique timeframes
    const timeframes = [...new Set(indicators.map(i => i.timeframe))];
    
    console.log(`Processing ${formattedIndicators.length} indicators across ${timeframes.length} timeframes for ${STOCK_SYMBOLS.length} stocks...`);
    
    // Process all stocks with the required indicators
    await processStocksWithIndicators({
      indicators: formattedIndicators,
      timeframes: timeframes
    }, STOCK_SYMBOLS);
    
    console.log(`✅ Processed ${formattedIndicators.length} indicator files directly to precalculatedStorage`);
    console.log(`📂 Storage location: ${precalculatedDir}`);
    
    // Update status
    precalculatedIndicators.status = 'completed';
    precalculatedIndicators.lastUpdated = new Date().toISOString();
    
    // Save to file
    savePrecalculatedIndicators();
    
    // Reset progress state
    updateProgress({
      isRunning: false,
      phase: 'idle',
      message: '',
      processed: 0,
      total: 0,
      matches: 0,
      percentage: 0,
      startTime: null
    });
    
    // Send completion status through SSE
    const completionMessage = `data: ${JSON.stringify({
      status: 'completed',
      phase: 'completed',
      isRunning: false,
      percentage: 100,
      message: 'Precalculation completed successfully'
    })}\n\n`;
    sseConnections.forEach(res => {
      res.write(completionMessage);
    });
    
    console.log('✅ Precalculated indicators processing completed successfully');
    
  } catch (error) {
    console.error('Error processing precalculated indicators:', error);
    precalculatedIndicators.status = 'error';
    precalculatedIndicators.lastUpdated = new Date().toISOString();
    
    // Save to file
    savePrecalculatedIndicators();
    
    // Reset progress state
    updateProgress({
      isRunning: false,
      phase: 'idle',
      message: '',
      processed: 0,
      total: 0,
      matches: 0,
      percentage: 0,
      startTime: null
    });
    
    // Send error status through SSE
    const errorMessage = `data: ${JSON.stringify({
      status: 'error',
      phase: 'error',
      isRunning: false,
      percentage: 0,
      message: 'Error processing indicators: ' + error.message
    })}\n\n`;
    sseConnections.forEach(res => {
      res.write(errorMessage);
    });
  }
}

// ==================== END PRECALCULATED INDICATORS ENDPOINTS ====================

// Refresh DB endpoint with progress streaming
app.post('/refreshdb', async (req, res) => {
  try {
    const { totalResults = 2000 } = req.body;
    
    console.log(`Starting database refresh for ${STOCK_SYMBOLS.length} symbols with ${totalResults} results each...`);
    
    // Set up SSE headers for streaming progress
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'Access-Control-Allow-Origin': '*'
    });
    
    // Send initial progress
    res.write(`data: ${JSON.stringify({
      status: 'starting',
      total: STOCK_SYMBOLS.length,
      processed: 0,
      successful: 0,
      failed: 0,
      percentage: 0,
      message: 'Initializing database refresh...'
    })}\n\n`);
    
    // Ensure the db directory exists
    const dbPath = path.join(__dirname, 'db');
    if (!fs.existsSync(dbPath)) {
      fs.mkdirSync(dbPath, { recursive: true });
    }
    
    // Track progress
    let processed = 0;
    let successful = 0;
    let failed = 0;
    const errors = [];
    const startTime = Date.now();
    
    // Function to send progress updates
    const sendProgress = (extraData = {}) => {
      const percentage = Math.round((processed / STOCK_SYMBOLS.length) * 100);
      const elapsedTime = Date.now() - startTime;
      const avgTimePerSymbol = processed > 0 ? elapsedTime / processed : 0;
      const remainingSymbols = STOCK_SYMBOLS.length - processed;
      const estimatedTimeRemaining = avgTimePerSymbol * remainingSymbols;
      
      const progressData = {
        status: 'processing',
        total: STOCK_SYMBOLS.length,
        processed,
        successful,
        failed,
        percentage,
        estimatedTimeRemaining: Math.round(estimatedTimeRemaining / 1000), // in seconds
        currentSymbol: extraData.currentSymbol || null,
        message: `Processing ${processed}/${STOCK_SYMBOLS.length} symbols (${percentage}%)`,
        ...extraData
      };
      
      res.write(`data: ${JSON.stringify(progressData)}\n\n`);
    };
    
    // Process in batches to avoid overwhelming the API
    const batchSize = 10; // Process 10 symbols at a time
    const batches = [];
    
    for (let i = 0; i < STOCK_SYMBOLS.length; i += batchSize) {
      batches.push(STOCK_SYMBOLS.slice(i, i + batchSize));
    }
    
    // Process each batch
    for (let batchIndex = 0; batchIndex < batches.length; batchIndex++) {
      const batch = batches[batchIndex];
      const batchPromises = batch.map(async (symbol) => {
        try {
          const queryString = "select high, low, open, close, volume";
          const data = qs.stringify({
            query: queryString,
            use_live: 1,
            limit: 1,
            size: totalResults,
            widget_id: -1,
            end_time: -1,
            timeframe: "Daily",
            symbol: symbol,
            scan_link: "scanlink:b6b0c6620714e44ab63d271d0ddbd498"
          });
          
          const response = await axios.post('https://chartink.com/oapi', data, {
            headers: {
              'accept': 'application/json, text/plain, */*',
              'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8,la;q=0.7',
              'content-type': 'application/x-www-form-urlencoded',
              'cookie': '_ga=GA1.2.827081830.1738516382; _gid=GA1.2.158232909.1738612317; XSRF-TOKEN=eyJpdiI6IjVrL2dLek8rSVE4aGFTWWllazd6cHc9PSIsInZhbHVlIjoiQmVUcmlLb0Z2dk9uYVlPeUpJL3d1OTQ0MTdvcUpWZGt6V2tEaHpEeUJidGJVOENDeFpYbnJiaVgxV3NielhMbjBGUzlTVmNuektCaHhTb0V3MFVnS1VUbWZRVCtEYXFxYlhrYzZ4eWpnY2RuZjltSlJJd1NaUkE4dlFTbVA5aDkiLCJtYWMiOiJkYzM1YzY2YTIwOTM5NTQzODNjMzNkMDZiNWMwY2NkNzc5MDQ5OTFmOGJlMTgwMzJmYjM1NDdmNTFjNzAyOGY2IiwidGFnIjoiIn0%3D; ci_session=eyJpdiI6InVrKzF5dXE4b2lzazMxU2lQWkJMN0E9PSIsInZhbHVlIjoiTzdMOHNsZDFJZ1dYd0JxT2EyQ0NVZGIvNUZUdmJsOHFtSXZuc002bnBrck5RSmVpS1NIRTZUUTZjWU9NVTNOcmM0SmtOSnF5UVI0cGVlU2VrNGJCM3Y2NkhKdTBvdWJlVEZzS3k2VDdtNGRDbzJqemo5M3gzbVFWaXEzQWFkbjAiLCJtYWMiOiI2YjYzMzI5N2UwOTZmYTM3OTNlNWMwNzk1NmFjY2E4MTdlMzQxNGVjYzIxMDUxOWE1ODkyYTg1MTM1NTU2NjJjIiwidGFnIjoiIn0%3D',
              'dnt': '1',
              'origin': 'https://chartink.com',
              'priority': 'u=1, i',
              'referer': 'https://chartink.com/screener/copy-double-volume-563',
              'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
              'sec-ch-ua-mobile': '?0',
              'sec-ch-ua-platform': '"Windows"',
              'sec-fetch-dest': 'empty',
              'sec-fetch-mode': 'cors',
              'sec-fetch-site': 'same-origin',
              'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
              'x-xsrf-token': 'eyJpdiI6IjVrL2dLek8rSVE4aGFTWWllazd6cHc9PSIsInZhbHVlIjoiQmVUcmlLb0Z2dk9uYVlPeUpJL3d1OTQ0MTdvcUpWZGt6V2tEaHpEeUJidGJVOENDeFpYbnJiaVgxV3NielhMbjBGUzlTVmNuektCaHhTb0V3MFVnS1VUbWZRVCtEYXFxYlhrYzZ4eWpnY2RuZjltSlJJd1NaUkE4dlFTbVA5aDkiLCJtYWMiOiJkYzM1YzY2YTIwOTM5NTQzODNjMzNkMDZiNWMwY2NkNzc5MDQ5OTFmOGJlMTgwMzJmYjM1NDdmNTFjNzAyOGY2IiwidGFnIjoiIn0=',
            },
            timeout: 30000 // 30 second timeout
          });
          
          // Map the data
          const groupData = response?.data?.groupData?.[0]?.results;
          const metaData = response?.data?.metaData?.[0]?.tradeTimes;
          let mappedData = [];
          
          if (groupData && metaData) {
            const highs = groupData[0]?.high || [];
            const lows = groupData[1]?.low || [];
            const opens = groupData[2]?.open || [];
            const closes = groupData[3]?.close || [];
            const volumes = groupData[4]?.volume || [];
            
            highs.forEach((element, idx) => {
              if(idx < metaData.length){
                mappedData.push({
                  open: opens[idx] !== undefined && opens[idx] !== null ? String(opens[idx]) : '',
                  low: lows[idx] !== undefined && lows[idx] !== null ? String(lows[idx]) : '',
                  high: highs[idx] !== undefined && highs[idx] !== null ? String(highs[idx]) : '',
                  close: closes[idx] !== undefined && closes[idx] !== null ? String(closes[idx]) : '',
                  volume: volumes[idx] !== undefined && volumes[idx] !== null ? String(volumes[idx]) : null,
                  date: metaData[idx] !== undefined && metaData[idx] !== null ? String(getNextDayTimestamp(metaData[idx])) : '',
                  day: metaData[idx] !== undefined && metaData[idx] !== null ? getDayOfWeekName(getNextDayTimestamp(metaData[idx])) : ''
                });
              }
            });
          }
          
          // Save to file
          const fileName = `${symbol}.json`;
          const filePath = path.join(dbPath, fileName);
          fs.writeFileSync(filePath, JSON.stringify({ data: mappedData }, null, 2), 'utf8');
          
          successful++;
          console.log(`✓ ${symbol} - ${mappedData.length} records saved`);
          
        } catch (error) {
          failed++;
          errors.push({ symbol, error: error.message });
          console.error(`✗ ${symbol} - Error: ${error.message}`);
        }
        
        processed++;
        
        // Send progress update for each symbol
        sendProgress({ currentSymbol: symbol });
      });
      
      // Wait for batch to complete
      await Promise.all(batchPromises);
      
      // Send batch completion update
      sendProgress({ 
        batchCompleted: batchIndex + 1,
        totalBatches: batches.length,
        message: `Completed batch ${batchIndex + 1}/${batches.length}`
      });
      
      // Add a small delay between batches to avoid rate limiting
      if (batchIndex < batches.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 1000)); // 1 second delay
      }
    }
    
    console.log(`Database refresh completed! Processed: ${processed}, Successful: ${successful}, Failed: ${failed}`);
    
    // Send final completion message
    res.write(`data: ${JSON.stringify({
      status: 'completed',
      total: STOCK_SYMBOLS.length,
      processed,
      successful,
      failed,
      percentage: 100,
      errors: errors.length > 0 ? errors : undefined,
      message: `Database refresh completed. ${successful} symbols updated successfully.`
    })}\n\n`);
    
    // Close the SSE connection
    res.end();
    
  } catch (error) {
    console.error('Database refresh error:', error);
    
    // Send error message if headers not sent
    if (!res.headersSent) {
      res.status(500).json({ 
        error: 'Internal server error', 
        details: error.message 
      });
    } else {
      res.write(`data: ${JSON.stringify({
        status: 'error',
        error: error.message,
        message: 'Database refresh failed'
      })}\n\n`);
      res.end();
    }
  }
});

// Global refresh state
let globalRefreshState = {
  isRunning: false,
  cancelToken: null,
  progress: null
};

// Simple refresh DB endpoint
app.post('/refreshdb', async (req, res) => {
  try {
    const { totalResults = 2000 } = req.body;
    
    // Cancel any existing refresh
    if (globalRefreshState.isRunning && globalRefreshState.cancelToken) {
      globalRefreshState.cancelToken.cancel = true;
      console.log('Cancelling previous refresh...');
      
      // Wait a moment for cancellation to take effect
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
    
    // Delete existing db folder
    const dbPath = path.join(__dirname, 'db');
    if (fs.existsSync(dbPath)) {
      console.log('Deleting existing db folder...');
      fs.rmSync(dbPath, { recursive: true, force: true });
    }
    
    // Create fresh db folder
    fs.mkdirSync(dbPath, { recursive: true });
    
    // Reset progress
    globalRefreshState = {
      isRunning: true,
      cancelToken: { cancel: false },
      progress: {
        status: 'processing',
        total: STOCK_SYMBOLS.length,
        processed: 0,
        successful: 0,
        failed: 0,
        percentage: 0,
        errors: [],
        startTime: Date.now(),
        currentSymbol: null
      }
    };
    
    console.log(`Starting fresh database refresh for ${STOCK_SYMBOLS.length} symbols with ${totalResults} results each...`);
    
    // Return immediate response
    res.json({
      message: 'Database refresh started. Check progress at /refreshdb-progress',
      total: STOCK_SYMBOLS.length
    });
    
    // Process in background
    processSimpleRefreshInBackground(totalResults);
    
  } catch (error) {
    console.error('Database refresh error:', error);
    res.status(500).json({ 
      error: 'Internal server error', 
      details: error.message 
    });
  }
});

// Single endpoint to check refresh progress
app.get('/refreshdb-progress', (req, res) => {
  if (!globalRefreshState.progress) {
    return res.json({
      status: 'idle',
      message: 'No refresh in progress'
    });
  }
  
  const progress = globalRefreshState.progress;
  const elapsedTime = Date.now() - progress.startTime;
  const avgTimePerSymbol = progress.processed > 0 ? elapsedTime / progress.processed : 0;
  const remainingSymbols = progress.total - progress.processed;
  const estimatedTimeRemaining = avgTimePerSymbol * remainingSymbols;
  
  res.json({
    ...progress,
    estimatedTimeRemaining: Math.round(estimatedTimeRemaining / 1000), // in seconds
    elapsedTime: Math.round(elapsedTime / 1000) // in seconds
  });
});

// Simplified background processing function
async function processSimpleRefreshInBackground(totalResults) {
  const cancelToken = globalRefreshState.cancelToken || { cancel: false };
  const progress = globalRefreshState.progress;
  
  try {
    const dbPath = path.join(__dirname, 'db');
    
    console.log(`🚀 Starting BULK processing for ${STOCK_SYMBOLS.length} symbols...`);
    
    // Create a function to process a single symbol
    const processSymbol = async (symbol) => {
      try {
        const queryString = "select high, low, open, close, volume";
        const data = qs.stringify({
          query: queryString,
          use_live: 1,
          limit: 1,
          size: totalResults,
          widget_id: -1,
          end_time: -1,
          timeframe: "Daily",
          symbol: symbol,
          scan_link: "scanlink:b6b0c6620714e44ab63d271d0ddbd498"
        });
        
        const response = await axios.post('https://chartink.com/oapi', data, {
          headers: {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8,la;q=0.7',
            'content-type': 'application/x-www-form-urlencoded',
            'cookie': '_ga=GA1.2.827081830.1738516382; _gid=GA1.2.158232909.1738612317; XSRF-TOKEN=eyJpdiI6IjVrL2dLek8rSVE4aGFTWWllazd6cHc9PSIsInZhbHVlIjoiQmVUcmlLb0Z2dk9uYVlPeUpJL3d1OTQ0MTdvcUpWZGt6V2tEaHpEeUJidGJVOENDeFpYbnJiaVgxV3NielhMbjBGUzlTVmNuektCaHhTb0V3MFVnS1VUbWZRVCtEYXFxYlhrYzZ4eWpnY2RuZjltSlJJd1NaUkE4dlFTbVA5aDkiLCJtYWMiOiJkYzM1YzY2YTIwOTM5NTQzODNjMzNkMDZiNWMwY2NkNzc5MDQ5OTFmOGJlMTgwMzJmYjM1NDdmNTFjNzAyOGY2IiwidGFnIjoiIn0%3D; ci_session=eyJpdiI6InVrKzF5dXE4b2lzazMxU2lQWkJMN0E9PSIsInZhbHVlIjoiTzdMOHNsZDFJZ1dYd0JxT2EyQ0NVZGIvNUZUdmJsOHFtSXZuc002bnBrck5RSmVpS1NIRTZUUTZjWU9NVTNOcmM0SmtOSnF5UVI0cGVlU2VrNGJCM3Y2NkhKdTBvdWJlVEZzS3k2VDdtNGRDbzJqemo5M3gzbVFWaXEzQWFkbjAiLCJtYWMiOiI2YjYzMzI5N2UwOTZmYTM3OTNlNWMwNzk1NmFjY2E4MTdlMzQxNGVjYzIxMDUxOWE1ODkyYTg1MTM1NTU2NjJjIiwidGFnIjoiIn0%3D',
            'dnt': '1',
            'origin': 'https://chartink.com',
            'priority': 'u=1, i',
            'referer': 'https://chartink.com/screener/copy-double-volume-563',
            'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
            'x-xsrf-token': 'eyJpdiI6IjVrL2dLek8rSVE4aGFTWWllazd6cHc9PSIsInZhbHVlIjoiQmVUcmlLb0Z2dk9uYVlPeUpJL3d1OTQ0MTdvcUpWZGt6V2tEaHpEeUJidGJVOENDeFpYbnJiaVgxV3NielhMbjBGUzlTVmNuektCaHhTb0V3MFVnS1VUbWZRVCtEYXFxYlhrYzZ4eWpnY2RuZjltSlJJd1NaUkE4dlFTbVA5aDkiLCJtYWMiOiJkYzM1YzY2YTIwOTM5NTQzODNjMzNkMDZiNWMwY2NkNzc5MDQ5OTFmOGJlMTgwMzJmYjM1NDdmNTFjNzAyOGY2IiwidGFnIjoiIn0=',
          },
          timeout: 45000, // Increased timeout
          maxRetries: 3 // Enable retries
        });
        
        // Map the data
        const groupData = response?.data?.groupData?.[0]?.results;
        const metaData = response?.data?.metaData?.[0]?.tradeTimes;
        let mappedData = [];
        
        if (groupData && metaData) {
          const highs = groupData[0]?.high || [];
          const lows = groupData[1]?.low || [];
          const opens = groupData[2]?.open || [];
          const closes = groupData[3]?.close || [];
          const volumes = groupData[4]?.volume || [];
          
          highs.forEach((element, idx) => {
            if(idx < metaData.length){
              mappedData.push({
                open: opens[idx] !== undefined && opens[idx] !== null ? String(opens[idx]) : '',
                low: lows[idx] !== undefined && lows[idx] !== null ? String(lows[idx]) : '',
                high: highs[idx] !== undefined && highs[idx] !== null ? String(highs[idx]) : '',
                close: closes[idx] !== undefined && closes[idx] !== null ? String(closes[idx]) : '',
                volume: volumes[idx] !== undefined && volumes[idx] !== null ? String(volumes[idx]) : null,
                date: metaData[idx] !== undefined && metaData[idx] !== null ? String(getNextDayTimestamp(metaData[idx])) : '',
                day: metaData[idx] !== undefined && metaData[idx] !== null ? getDayOfWeekName(getNextDayTimestamp(metaData[idx])) : '',
              });
            }
          });
        }
        
        // Save to file
        const fileName = `${symbol}.json`;
        const filePath = path.join(dbPath, fileName);
        fs.writeFileSync(filePath, JSON.stringify({ data: mappedData }, null, 2), 'utf8');
        
        return { symbol, success: true, records: mappedData.length };
        
      } catch (error) {
        return { symbol, success: false, error: error.message };
      }
    };

    // SUPER FAST BULK PROCESSING with controlled concurrency
    const CONCURRENT_LIMIT = process.env.CONCURRENT_LIMIT || 100; // Default 100 concurrent requests
    console.log(`📡 Sending requests with ${CONCURRENT_LIMIT} concurrent limit for ${STOCK_SYMBOLS.length} symbols...`);
    
    // Function to process symbols with concurrency control
    const processConcurrently = async (symbols, limit) => {
      const results = [];
      
      for (let i = 0; i < symbols.length; i += limit) {
        // Check for cancellation
        if (cancelToken.cancel) {
          throw new Error('Cancelled');
        }
        
        const batch = symbols.slice(i, i + limit);
        console.log(`🔄 Processing batch ${Math.floor(i/limit) + 1}/${Math.ceil(symbols.length/limit)} (${batch.length} symbols)`);
        
        const batchPromises = batch.map(async (symbol) => {
          const result = await processSymbol(symbol);
          
          // Update progress atomically
          if (result.success) {
            progress.successful++;
            console.log(`✓ ${result.symbol} - ${result.records} records saved`);
          } else {
            progress.failed++;
            progress.errors.push({ symbol: result.symbol, error: result.error });
            console.error(`✗ ${result.symbol} - Error: ${result.error}`);
          }
          
          progress.processed++;
          progress.percentage = Math.round((progress.processed / progress.total) * 100);
          progress.currentSymbol = result.symbol;
          
          return result;
        });
        
        const batchResults = await Promise.allSettled(batchPromises);
        results.push(...batchResults);
        
        // Small delay between batches to prevent overwhelming the API
        if (i + limit < symbols.length) {
          await new Promise(resolve => setTimeout(resolve, 100)); // 100ms delay
        }
      }
      
      return results;
    };
    
    // Process with controlled concurrency
    console.log(`⏳ Processing all ${STOCK_SYMBOLS.length} requests with ${CONCURRENT_LIMIT} concurrent limit...`);
    const results = await processConcurrently(STOCK_SYMBOLS, CONCURRENT_LIMIT);
    
    // Check for cancellation
    if (cancelToken.cancel) {
      console.log('Refresh cancelled by user');
      progress.status = 'cancelled';
      progress.message = 'Refresh cancelled by user';
      globalRefreshState.isRunning = false;
      return;
    }
    
    // Calculate final stats
    const fulfilled = results.filter(r => r.status === 'fulfilled').length;
    const rejected = results.filter(r => r.status === 'rejected').length;
    
    console.log(`🎯 BULK Database refresh completed!`);
    console.log(`📊 Stats: Processed: ${progress.processed}, Successful: ${progress.successful}, Failed: ${progress.failed}`);
    console.log(`⚡ Performance: ${fulfilled} fulfilled, ${rejected} rejected promises`);
    
    // Check if we have precalculated indicators to process
    if (precalculatedIndicators.indicators && precalculatedIndicators.indicators.length > 0) {
      console.log('🔄 Starting precalculation after DB refresh...');
      
      // Update progress to precalculation phase
      progress.status = 'precalculating';
      progress.message = `🧮 Starting precalculation for ${precalculatedIndicators.indicators.length} indicators...`;
      progress.phase = 'precalculation';
      
      // Start precalculation process
      try {
        await processPrecalculatedIndicatorsForRefresh(precalculatedIndicators.indicators, progress);
        
        // Final completion
        progress.status = 'completed';
        progress.message = `🎉 Database refresh and precalculation completed! ${progress.successful} symbols updated successfully!`;
      } catch (error) {
        console.error('Precalculation error:', error);
        progress.status = 'completed_with_warnings';
        progress.message = `🎉 Database refresh completed, but precalculation failed: ${error.message}`;
      }
    } else {
      progress.status = 'completed';
      progress.message = `🎉 BULK refresh completed! ${progress.successful} symbols updated successfully in record time!`;
    }
    
    globalRefreshState.isRunning = false;
    
  } catch (error) {
    progress.status = 'error';
    progress.error = error.message;
    globalRefreshState.isRunning = false;
    console.error('Database refresh error:', error);
  }
}

// Modified precalculation function for refresh process with progress tracking
async function processPrecalculatedIndicatorsForRefresh(indicators, progress) {
  try {
    console.log('📊 Processing precalculated indicators for all stocks during refresh...');
    console.log('🔍 Input indicators:', JSON.stringify(indicators, null, 2));
    
    // Create dedicated precalculated storage directory
    const precalculatedDir = path.join(__dirname, 'precalculatedStorage');
    if (!fs.existsSync(precalculatedDir)) {
      fs.mkdirSync(precalculatedDir, { recursive: true });
    }
    
    // Convert indicators to the format expected by processStocksWithIndicators
    const formattedIndicators = indicators.map(indicator => {
      const params = indicator.params || {};
      
      // Handle different indicator types
      switch(indicator.name.toLowerCase()) {
        case 'sma':
          return {
            name: 'sma',
            period: params.period || 20,
            params: {},
            timeframe: indicator.timeframe
          };
        case 'ema':
          return {
            name: 'ema', 
            period: params.period || 20,
            params: {},
            timeframe: indicator.timeframe
          };
        case 'rsi':
          return {
            name: 'rsi',
            period: params.period || 14,
            params: {},
            timeframe: indicator.timeframe
          };
        case 'bollinger':
        case 'bb':
          return {
            name: 'bollinger',
            period: params.period || 20,
            params: {
              stdDev: params.stdDev || 2
            },
            timeframe: indicator.timeframe
          };
        case 'volume':
          return {
            name: 'volume',
            period: 1,
            params: {},
            timeframe: indicator.timeframe
          };
        case 'pctchg':
        case 'percent_change':
        case 'pct_change':
        case '%_change':
          return {
            name: 'pctchg',
            period: 1,
            params: {},
            timeframe: indicator.timeframe
          };
        default:
          return {
            name: indicator.name,
            period: params.period || 20,
            params: params,
            timeframe: indicator.timeframe
          };
      }
    });
    
    // Update progress
    progress.message = `🧮 Processing indicators for ${STOCK_SYMBOLS.length} stocks...`;
    progress.precalcTotal = STOCK_SYMBOLS.length;
    progress.precalcProcessed = 0;
    
    // Import queryService to use processStocksWithIndicators
    const { processStocksWithIndicators } = require('./services/queryService');
    
    // Extract unique timeframes
    const timeframes = [...new Set(indicators.map(i => i.timeframe))];
    
    console.log(`🚀 Processing ${formattedIndicators.length} indicators across ${timeframes.length} timeframes for ${STOCK_SYMBOLS.length} stocks...`);
    console.log('📈 Formatted indicators:', formattedIndicators);
    console.log('🕐 Using timeframes:', timeframes);
    
    // Process all stocks with the required indicators
    await processStocksWithIndicators({
      indicators: formattedIndicators,
      timeframes: timeframes
    }, STOCK_SYMBOLS);
    
    console.log(`✅ Processed ${formattedIndicators.length} indicator files directly to precalculatedStorage`);
    console.log(`📂 Storage location: ${precalculatedDir}`);
    
    // Update precalculated indicators status
    precalculatedIndicators.status = 'completed';
    precalculatedIndicators.lastUpdated = new Date().toISOString();
    savePrecalculatedIndicators();
    
    console.log('✅ Precalculated indicators processing completed successfully during refresh');
    
  } catch (error) {
    console.error('Error processing precalculated indicators during refresh:', error);
    throw error;
  }
}

// ==================== CSV UPLOAD ENDPOINTS ====================

// Global state for CSV upload progress
let csvUploadProgress = {
  isRunning: false,
  phase: 'idle',
  message: '',
  processed: 0,
  total: 0,
  percentage: 0,
  symbolCount: 0,
  sseClients: []
};

// Helper function to send SSE updates to all connected clients
function sendCSVProgressUpdate(data) {
  console.log(`📡 SSE Update: ${data.phase} - ${data.percentage}% - ${data.message}`);
  console.log(`📡 Connected clients: ${csvUploadProgress.sseClients.length}`);
  
  // Update local state
  csvUploadProgress.isRunning = data.isRunning !== false;
  csvUploadProgress.phase = data.phase;
  csvUploadProgress.message = data.message;
  csvUploadProgress.processed = data.processed || 0;
  csvUploadProgress.total = data.total || 100;
  csvUploadProgress.percentage = data.percentage || 0;
  
  csvUploadProgress.sseClients.forEach((client, index) => {
    try {
      client.write(`data: ${JSON.stringify(data)}\n\n`);
    } catch (error) {
      console.log(`❌ Failed to send to client ${index}, removing:`, error.message);
      // Remove disconnected clients
      const clientIndex = csvUploadProgress.sseClients.indexOf(client);
      if (clientIndex > -1) {
        csvUploadProgress.sseClients.splice(clientIndex, 1);
      }
    }
  });
}

// SSE endpoint for CSV upload progress
app.get('/csv-upload-progress', (req, res) => {
  console.log('🔗 New SSE client connected for CSV upload progress');
  
  // Set up SSE headers
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Access-Control-Allow-Origin': '*'
  });

  // Add client to the list
  csvUploadProgress.sseClients.push(res);
  console.log(`📊 Total connected clients: ${csvUploadProgress.sseClients.length}`);

  // Send current progress immediately
  const initialProgress = {
    isRunning: csvUploadProgress.isRunning,
    phase: csvUploadProgress.phase,
    message: csvUploadProgress.message,
    processed: csvUploadProgress.processed,
    total: csvUploadProgress.total,
    percentage: csvUploadProgress.percentage,
    symbolCount: csvUploadProgress.symbolCount
  };
  
  console.log('📤 Sending initial progress:', initialProgress);
  res.write(`data: ${JSON.stringify(initialProgress)}\n\n`);

  // Clean up on client disconnect
  req.on('close', () => {
    console.log('❌ SSE client disconnected');
    const index = csvUploadProgress.sseClients.indexOf(res);
    if (index > -1) {
      csvUploadProgress.sseClients.splice(index, 1);
      console.log(`📊 Remaining connected clients: ${csvUploadProgress.sseClients.length}`);
    }
  });
});

// CSV Upload and Symbol Extraction endpoint
app.post('/upload-csv', upload.single('csvFile'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ 
        success: false, 
        error: 'No file uploaded' 
      });
    }

    // Initialize progress tracking
    csvUploadProgress.isRunning = true;
    csvUploadProgress.phase = 'parsing';
    csvUploadProgress.message = 'Parsing CSV file...';
    csvUploadProgress.processed = 0;
    csvUploadProgress.total = 100;
    csvUploadProgress.percentage = 5;

    // Send initial progress update
    sendCSVProgressUpdate({
      isRunning: true,
      phase: 'parsing',
      message: 'Parsing CSV file...',
      processed: 0,
      total: 100,
      percentage: 5
    });

    console.log('📁 Processing CSV file:', req.file.originalname);

    // Read and parse CSV file
    const csvData = fs.readFileSync(req.file.path, 'utf8');
    const symbols = new Set(); // Use Set to avoid duplicates

    // Parse CSV
    parse(csvData, {
      columns: true, // Use first row as column headers
      skip_empty_lines: true,
      trim: true
    }, (err, records) => {
      if (err) {
        console.error('CSV parsing error:', err);
        // Clean up uploaded file
        fs.unlinkSync(req.file.path);
        return res.status(400).json({
          success: false,
          error: 'Failed to parse CSV file: ' + err.message
        });
      }

      try {
        // Extract symbols from CSV records
        // Look for common column names that might contain symbols
        const symbolColumns = ['symbol', 'Symbol', 'SYMBOL', 'stock', 'Stock', 'STOCK', 
                              'ticker', 'Ticker', 'TICKER', 'name', 'Name', 'NAME'];
        
        records.forEach(record => {
          // Try to find symbol in any of the possible columns
          for (const colName of symbolColumns) {
            if (record[colName]) {
              const symbol = record[colName].toString().trim().toUpperCase();
              if (symbol && symbol.length > 0) {
                symbols.add(symbol);
                break; // Found symbol, no need to check other columns
              }
            }
          }
        });

        // Clean up uploaded file
        fs.unlinkSync(req.file.path);

        const extractedSymbols = Array.from(symbols).sort();
        
        console.log(`✅ Extracted ${extractedSymbols.length} unique symbols from CSV`);
        
        // Update progress after extraction
        csvUploadProgress.symbolCount = extractedSymbols.length;
        sendCSVProgressUpdate({
          isRunning: true,
          phase: 'extracted',
          message: `Extracted ${extractedSymbols.length} symbols from CSV`,
          processed: 20,
          total: 100,
          percentage: 20,
          symbolCount: extractedSymbols.length
        });
        
        // Send immediate response with basic info
        res.json({
          success: true,
          message: 'CSV processing started',
          symbolCount: extractedSymbols.length,
          sampleSymbols: extractedSymbols.slice(0, 10), // Show first 10 as preview
          progressUrl: '/csv-upload-progress'
        });

        // Continue processing in background
        processCSVSymbolsInBackground(extractedSymbols);

      } catch (error) {
        console.error('Symbol extraction error:', error);
        // Clean up uploaded file
        fs.unlinkSync(req.file.path);
        
        // Send error update via SSE
        sendCSVProgressUpdate({
          isRunning: false,
          phase: 'error',
          message: 'Failed to extract symbols: ' + error.message,
          processed: 0,
          total: 100,
          percentage: 0
        });
        
        res.status(500).json({
          success: false,
          error: 'Failed to extract symbols: ' + error.message
        });
      }
    });

  } catch (error) {
    console.error('CSV upload error:', error);
    // Clean up uploaded file if it exists
    if (req.file && fs.existsSync(req.file.path)) {
      fs.unlinkSync(req.file.path);
    }
    
    // Send error update via SSE
    sendCSVProgressUpdate({
      isRunning: false,
      phase: 'error',
      message: 'Upload failed: ' + error.message,
      processed: 0,
      total: 100,
      percentage: 0
    });
    
    res.status(500).json({
      success: false,
      error: 'Upload failed: ' + error.message
    });
  }
});

// Background function to process CSV symbols and trigger refresh
async function processCSVSymbolsInBackground(extractedSymbols) {
  try {
    // Update progress - updating constants
    sendCSVProgressUpdate({
      isRunning: true,
      phase: 'updating_constants',
      message: 'Updating symbol constants...',
      processed: 30,
      total: 100,
      percentage: 30
    });

    // Read the current constants file
    const constantsPath = path.join(__dirname, 'stockSymbols.constants.js');
    let constantsContent = fs.readFileSync(constantsPath, 'utf8');
    
    // Replace the STOCK_SYMBOLS array
    const newSymbolsArray = `const STOCK_SYMBOLS = [\n  '${extractedSymbols.join("',\n  '")}'\n];`;
    const updatedContent = constantsContent.replace(
      /const STOCK_SYMBOLS = \[[^\]]*\];/s,
      newSymbolsArray
    );
    
    // Write the updated content back to the file
    fs.writeFileSync(constantsPath, updatedContent, 'utf8');
    console.log(`📝 Updated stockSymbols.constants.js with ${extractedSymbols.length} symbols`);

    // Reload the constants (clear require cache and require again)
    delete require.cache[require.resolve('./stockSymbols.constants.js')];
    const { STOCK_SYMBOLS: UPDATED_SYMBOLS } = require('./stockSymbols.constants.js');
    
    console.log(`✅ Constants reloaded. New symbol count: ${UPDATED_SYMBOLS.length}`);

    // Update progress - starting refresh
    sendCSVProgressUpdate({
      isRunning: true,
      phase: 'starting_refresh',
      message: 'Starting database refresh...',
      processed: 40,
      total: 100,
      percentage: 40
    });

    // Start refresh DB process with updated symbols
    if (globalRefreshState.isRunning) {
      throw new Error('A refresh process is already running. Please wait for it to complete.');
    }

    globalRefreshState.isRunning = true;
    globalRefreshState.cancelToken = { cancel: false };
    globalRefreshState.progress = {
      status: 'starting',
      processed: 0,
      successful: 0,
      failed: 0,
      total: UPDATED_SYMBOLS.length,
      message: 'Initializing refresh with updated symbols...'
    };

    // Start the refresh process in background with progress integration
    processSimpleRefreshInBackgroundWithCSV();

  } catch (error) {
    console.error('Background CSV processing error:', error);
    sendCSVProgressUpdate({
      isRunning: false,
      phase: 'error',
      message: 'Failed to process symbols: ' + error.message,
      processed: 0,
      total: 100,
      percentage: 0
    });
  }
}

// Modified refresh function that integrates with CSV upload progress
async function processSimpleRefreshInBackgroundWithCSV() {
  const cancelToken = globalRefreshState.cancelToken || { cancel: false };
  const progress = globalRefreshState.progress;
  
  try {
    const dbPath = path.join(__dirname, 'db');
    
    // Delete existing db folder
    if (fs.existsSync(dbPath)) {
      console.log('Deleting existing db folder...');
      fs.rmSync(dbPath, { recursive: true, force: true });
    }
    
    // Create fresh db folder
    fs.mkdirSync(dbPath, { recursive: true });
    
    console.log(`🚀 Starting BULK processing for ${STOCK_SYMBOLS.length} symbols...`);
    
    // Update CSV progress - database refresh started
    sendCSVProgressUpdate({
      isRunning: true,
      phase: 'refreshing_database',
      message: `Refreshing database for ${STOCK_SYMBOLS.length} stocks...`,
      processed: 50,
      total: 100,
      percentage: 50
    });
    
    // Process stocks with controlled concurrency (similar to original logic)
    const CONCURRENT_LIMIT = 50;
    const DELAY_BETWEEN_REQUESTS = 10;
    
    let processed = 0;
    let successful = 0;
    let failed = 0;
    
    const processConcurrently = async (symbols, limit) => {
      const results = [];
      for (let i = 0; i < symbols.length; i += limit) {
        // Check for cancellation
        if (cancelToken.cancel) break;
        
        const batch = symbols.slice(i, i + limit);
        const batchPromises = batch.map(symbol => 
          processStockWithDelay(symbol, DELAY_BETWEEN_REQUESTS)
        );
        
        const batchResults = await Promise.allSettled(batchPromises);
        results.push(...batchResults);
        
        // Update progress
        processed += batch.length;
        successful = results.filter(r => r.status === 'fulfilled' && r.value?.success === true).length;
        failed = results.filter(r => r.status === 'rejected' || (r.status === 'fulfilled' && r.value?.success === false)).length;
        
        // Update both global refresh state and CSV progress
        progress.processed = processed;
        progress.successful = successful;
        progress.failed = failed;
        progress.percentage = Math.round((processed / STOCK_SYMBOLS.length) * 100);
        
        // Calculate CSV progress (50% to 85% for database refresh)
        const dbProgress = (processed / STOCK_SYMBOLS.length) * 35; // 35% of total
        sendCSVProgressUpdate({
          isRunning: true,
          phase: 'refreshing_database',
          message: `Database refresh: ${processed}/${STOCK_SYMBOLS.length} (${successful} successful)`,
          processed: 50 + dbProgress,
          total: 100,
          percentage: 50 + dbProgress,
          dbStats: { processed, successful, failed, total: STOCK_SYMBOLS.length }
        });
        
        console.log(`📊 Processed ${processed}/${STOCK_SYMBOLS.length} symbols (✅ ${successful} success, ❌ ${failed} failed)`);
      }
      
      return results;
    };
    
    const processStockWithDelay = (symbol, delay) => {
      return new Promise((resolve) => {
        setTimeout(async () => {
          try {
            const result = await processStockData(symbol);
            resolve(result);
          } catch (error) {
            resolve({ symbol, success: false, error: error.message });
          }
        }, delay);
      });
    };
    
    const processStockData = async (symbol) => {
      const symbolPath = path.join(dbPath, `${symbol}.json`);
      
      try {
        console.log(`🔄 Fetching data for ${symbol}...`);
        
        // Use the same API endpoint and format as the working refresh endpoint
        const queryString = "select high, low, open, close, volume";
        const data = qs.stringify({
          query: queryString,
          use_live: 1,
          limit: 1,
          size: 2000, // Default size like the working version
          widget_id: -1,
          end_time: -1,
          timeframe: "Daily",
          symbol: symbol,
          scan_link: "scanlink:b6b0c6620714e44ab63d271d0ddbd498"
        });
        
        const response = await axios.post('https://chartink.com/oapi', data, {
          headers: {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8,la;q=0.7',
            'content-type': 'application/x-www-form-urlencoded',
            'cookie': '_ga=GA1.2.827081830.1738516382; _gid=GA1.2.158232909.1738612317; XSRF-TOKEN=eyJpdiI6IjVrL2dLek8rSVE4aGFTWWllazd6cHc9PSIsInZhbHVlIjoiQmVUcmlLb0Z2dk9uYVlPeUpJL3d1OTQ0MTdvcUpWZGt6V2tEaHpEeUJidGJVOENDeFpYbnJiaVgxV3NielhMbjBGUzlTVmNuektCaHhTb0V3MFVnS1VUbWZRVCtEYXFxYlhrYzZ4eWpnY2RuZjltSlJJd1NaUkE4dlFTbVA5aDkiLCJtYWMiOiJkYzM1YzY2YTIwOTM5NTQzODNjMzNkMDZiNWMwY2NkNzc5MDQ5OTFmOGJlMTgwMzJmYjM1NDdmNTFjNzAyOGY2IiwidGFnIjoiIn0%3D; ci_session=eyJpdiI6InVrKzF5dXE4b2lzazMxU2lQWkJMN0E9PSIsInZhbHVlIjoiTzdMOHNsZDFJZ1dYd0JxT2EyQ0NVZGIvNUZUdmJsOHFtSXZuc002bnBrck5RSmVpS1NIRTZUUTZjWU9NVTNOcmM0SmtOSnF5UVI0cGVlU2VrNGJCM3Y2NkhKdTBvdWJlVEZzS3k2VDdtNGRDbzJqemo5M3gzbVFWaXEzQWFkbjAiLCJtYWMiOiI2YjYzMzI5N2UwOTZmYTM3OTNlNWMwNzk1NmFjY2E4MTdlMzQxNGVjYzIxMDUxOWE1ODkyYTg1MTM1NTU2NjJjIiwidGFnIjoiIn0%3D',
            'dnt': '1',
            'origin': 'https://chartink.com',
            'priority': 'u=1, i',
            'referer': 'https://chartink.com/screener/copy-double-volume-563',
            'sec-ch-ua': '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
            'x-requested-with': 'XMLHttpRequest'
          }
        });
        
        // Extract data using the same logic as the working refresh endpoint
        const groupData = response?.data?.groupData?.[0]?.results;
        const metaData = response?.data?.metaData?.[0]?.tradeTimes;
        let mappedData = [];
        
        if (groupData && metaData) {
          const highs = groupData[0]?.high || [];
          const lows = groupData[1]?.low || [];
          const opens = groupData[2]?.open || [];
          const closes = groupData[3]?.close || [];
          const volumes = groupData[4]?.volume || [];
          
          highs.forEach((element, idx) => {
            if(idx < metaData.length){
              mappedData.push({
                open: opens[idx] !== undefined && opens[idx] !== null ? String(opens[idx]) : '',
                low: lows[idx] !== undefined && lows[idx] !== null ? String(lows[idx]) : '',
                high: highs[idx] !== undefined && highs[idx] !== null ? String(highs[idx]) : '',
                close: closes[idx] !== undefined && closes[idx] !== null ? String(closes[idx]) : '',
                volume: volumes[idx] !== undefined && volumes[idx] !== null ? String(volumes[idx]) : null,
                date: metaData[idx] !== undefined && metaData[idx] !== null ? String(getNextDayTimestamp(metaData[idx])) : '',
                day: metaData[idx] !== undefined && metaData[idx] !== null ? getDayOfWeekName(getNextDayTimestamp(metaData[idx])) : '',
              });
            }
          });
          
          // Save in the same format as the working version
          fs.writeFileSync(symbolPath, JSON.stringify({ data: mappedData }, null, 2), 'utf8');
          console.log(`✅ Saved ${symbol}.json (${mappedData.length} records)`);
          return { symbol, success: true };
        } else {
          // This is expected for symbols with no data - don't treat as error
          console.log(`⚠️ No data available for ${symbol} (might be delisted or invalid)`);
          return { symbol, success: false, error: 'No data available' };
        }
      } catch (error) {
        console.log(`❌ Failed to fetch ${symbol}:`, error.message);
        throw new Error(`Failed to fetch data for ${symbol}: ${error.message}`);
      }
    };
    
    // Process with controlled concurrency
    console.log(`⏳ Processing all ${STOCK_SYMBOLS.length} requests with ${CONCURRENT_LIMIT} concurrent limit...`);
    const results = await processConcurrently(STOCK_SYMBOLS, CONCURRENT_LIMIT);
    
    // Check for cancellation
    if (cancelToken.cancel) {
      console.log('Refresh cancelled by user');
      progress.status = 'cancelled';
      progress.message = 'Refresh cancelled by user';
      globalRefreshState.isRunning = false;
      sendCSVProgressUpdate({
        isRunning: false,
        phase: 'cancelled',
        message: 'Process cancelled by user',
        processed: 0,
        total: 100,
        percentage: 0
      });
      return;
    }
    
    // Calculate final stats
    const fulfilled = results.filter(r => r.status === 'fulfilled').length;
    const rejected = results.filter(r => r.status === 'rejected').length;
    
    console.log(`🎯 BULK Database refresh completed!`);
    console.log(`📊 Stats: Processed: ${progress.processed}, Successful: ${progress.successful}, Failed: ${progress.failed}`);
    console.log(`⚡ Performance: ${fulfilled} fulfilled, ${rejected} rejected promises`);
    
    // Check if we have precalculated indicators to process
    if (precalculatedIndicators.indicators && precalculatedIndicators.indicators.length > 0) {
      console.log('🔄 Starting precalculation after DB refresh...');
      
      // Update CSV progress to precalculation phase
      sendCSVProgressUpdate({
        isRunning: true,
        phase: 'precalculating',
        message: `Starting precalculation for ${precalculatedIndicators.indicators.length} indicators...`,
        processed: 85,
        total: 100,
        percentage: 85
      });
      
      // Start precalculation process
      try {
        await processPrecalculatedIndicatorsForRefreshWithCSV(precalculatedIndicators.indicators, progress);
        
        // Final completion
        sendCSVProgressUpdate({
          isRunning: false,
          phase: 'completed',
          message: `✅ Database refresh and precalculation completed! ${progress.successful} symbols updated successfully!`,
          processed: 100,
          total: 100,
          percentage: 100
        });
      } catch (error) {
        console.error('Precalculation error:', error);
        sendCSVProgressUpdate({
          isRunning: false,
          phase: 'completed_with_warnings',
          message: `✅ Database refresh completed, but precalculation failed: ${error.message}`,
          processed: 100,
          total: 100,
          percentage: 100
        });
      }
    } else {
      // Final completion without precalculation
      sendCSVProgressUpdate({
        isRunning: false,
        phase: 'completed',
        message: `✅ Database refresh completed! ${progress.successful} symbols updated successfully!`,
        processed: 100,
        total: 100,
        percentage: 100
      });
    }
    
    globalRefreshState.isRunning = false;
    
  } catch (error) {
    progress.status = 'error';
    progress.error = error.message;
    globalRefreshState.isRunning = false;
    console.error('Database refresh error:', error);
    
    sendCSVProgressUpdate({
      isRunning: false,
      phase: 'error',
      message: 'Database refresh failed: ' + error.message,
      processed: 0,
      total: 100,
      percentage: 0
    });
  }
}

// Modified precalculation function for CSV upload process
async function processPrecalculatedIndicatorsForRefreshWithCSV(indicators, progress) {
  try {
    console.log('📊 Processing precalculated indicators during CSV upload process...');
    
    // Create dedicated precalculated storage directory
    const precalculatedDir = path.join(__dirname, 'precalculatedStorage');
    if (!fs.existsSync(precalculatedDir)) {
      fs.mkdirSync(precalculatedDir, { recursive: true });
    }
    
    // Convert indicators to the format expected by processStocksWithIndicators
    const formattedIndicators = indicators.map(indicator => {
      const params = indicator.params || {};
      
      // Handle different indicator types (same logic as before)
      switch(indicator.name.toLowerCase()) {
        case 'sma':
          return { name: 'sma', period: params.period || 20, params: {}, timeframe: indicator.timeframe };
        case 'ema':
          return { name: 'ema', period: params.period || 20, params: {}, timeframe: indicator.timeframe };
        case 'rsi':
          return { name: 'rsi', period: params.period || 14, params: {}, timeframe: indicator.timeframe };
        case 'bollinger':
        case 'bb':
          return { name: 'bollinger', period: params.period || 20, params: { stdDev: params.stdDev || 2 }, timeframe: indicator.timeframe };
        case 'volume':
          return { name: 'volume', period: 1, params: {}, timeframe: indicator.timeframe };
        case 'pctchg':
        case 'percent_change':
        case 'pct_change':
        case '%_change':
          return { name: 'pctchg', period: 1, params: {}, timeframe: indicator.timeframe };
        default:
          return { name: indicator.name, period: params.period || 20, params: params, timeframe: indicator.timeframe };
      }
    });
    
    // Extract unique timeframes
    const timeframes = [...new Set(indicators.map(i => i.timeframe))];
    
    console.log(`🚀 Processing ${formattedIndicators.length} indicators across ${timeframes.length} timeframes for ${STOCK_SYMBOLS.length} stocks...`);
    
    // Import queryService to use processStocksWithIndicators
    const { processStocksWithIndicators } = require('./services/queryService');
    
    // Set up a global progress handler to capture precalculation progress
    const originalUpdateProgress = global.updateProgress;
    global.updateProgress = (progressData) => {
      if (progressData.phase === 'processing_indicators') {
        const precalcProgress = Math.round((progressData.processed / progressData.total) * 100);
        const overallProgress = 85 + (precalcProgress * 0.15); // 85-100%
        
        sendCSVProgressUpdate({
          isRunning: true,
          phase: 'precalculating',
          message: `Precalculating indicators: ${progressData.processed}/${progressData.total} stocks`,
          processed: overallProgress,
          total: 100,
          percentage: overallProgress,
          precalcStats: {
            processed: progressData.processed,
            total: progressData.total,
            percentage: precalcProgress
          }
        });
      }
    };
    
    try {
      // Process all stocks with the required indicators
      await processStocksWithIndicators({
        indicators: formattedIndicators,
        timeframes: timeframes
      }, STOCK_SYMBOLS);
    } finally {
      // Restore the original updateProgress function
      global.updateProgress = originalUpdateProgress;
    }
    
    console.log(`✅ Processed ${formattedIndicators.length} indicator files directly to precalculatedStorage`);
    console.log(`📂 Storage location: ${precalculatedDir}`);
    
    // Update precalculated indicators status
    precalculatedIndicators.status = 'completed';
    precalculatedIndicators.lastUpdated = new Date().toISOString();
    savePrecalculatedIndicators();
    
    console.log('✅ Precalculated indicators processing completed successfully during CSV upload');
    
  } catch (error) {
    console.error('Error processing precalculated indicators during CSV upload:', error);
    throw error;
  }
}

// Update symbols and refresh DB endpoint
app.post('/update-symbols-and-refresh', async (req, res) => {
  try {
    const { symbols } = req.body;
    
    if (!symbols || !Array.isArray(symbols) || symbols.length === 0) {
      return res.status(400).json({
        success: false,
        error: 'No symbols provided'
      });
    }

    console.log(`🔄 Updating symbol list with ${symbols.length} symbols...`);

    // Update the constants file
    const constantsPath = path.join(__dirname, 'stockSymbols.constants.js');
    const newConstantsContent = `const STOCK_SYMBOLS = ${JSON.stringify(symbols, null, 2)};

const TOTAL_SYMBOLS = STOCK_SYMBOLS.length;

module.exports = {
  STOCK_SYMBOLS,
  TOTAL_SYMBOLS
};
`;

    // Write updated constants file
    fs.writeFileSync(constantsPath, newConstantsContent, 'utf8');
    
    console.log('📝 Updated stockSymbols.constants.js');

    // Reload the constants (clear require cache and require again)
    delete require.cache[require.resolve('./stockSymbols.constants.js')];
    const { STOCK_SYMBOLS: UPDATED_SYMBOLS } = require('./stockSymbols.constants.js');
    
    console.log(`✅ Constants reloaded. New symbol count: ${UPDATED_SYMBOLS.length}`);

    // Start refresh DB process with updated symbols
    if (globalRefreshState.isRunning) {
      return res.status(409).json({
        success: false,
        error: 'A refresh process is already running. Please wait for it to complete.'
      });
    }

    globalRefreshState.isRunning = true;
    globalRefreshState.cancelToken = { cancel: false };
    globalRefreshState.progress = {
      status: 'starting',
      processed: 0,
      successful: 0,
      failed: 0,
      total: UPDATED_SYMBOLS.length,
      message: 'Initializing refresh with updated symbols...'
    };

    // Start the refresh process in background
    processSimpleRefreshInBackground(2000); // Default to 2000 total results

    res.json({
      success: true,
      message: 'Symbols updated and database refresh started',
      symbolCount: UPDATED_SYMBOLS.length,
      progressUrl: '/refreshdb-progress'
    });

  } catch (error) {
    console.error('Update symbols and refresh error:', error);
    globalRefreshState.isRunning = false;
    res.status(500).json({
      success: false,
      error: 'Failed to update symbols and refresh: ' + error.message
    });
  }
});

// ==================== END CSV UPLOAD ENDPOINTS ====================

// Start server
app.listen(port, () => {
  console.log(`Server is running on http://localhost:${port}`);
  console.log('Available endpoints:');
  console.log('  GET /query/progress - Get current query progress');
  console.log('  POST /query - Execute stock query');
  console.log('  POST /upload-csv - Upload CSV and extract symbols');
  console.log('  POST /update-symbols-and-refresh - Update symbol list and refresh DB');
  console.log('  GET /health - Server health check');
});