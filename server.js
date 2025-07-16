const express = require('express');
const axios = require('axios');
const fs = require('fs');
const path = require('path');
const cors = require('cors');
const qs = require('qs');
const { parseQuery, findMatchingCandles, getQueryExamples, extractIndicatorsFromQuery, processStocksWithIndicators } = require('./services/queryService');
const { STOCK_SYMBOLS, TOTAL_SYMBOLS } = require('./stockSymbols.constants');
const { clearCache } = require('./services/indicatorCache');

const app = express();
app.use(cors());
app.use(express.json())
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
    const dirPath = path.join(__dirname, 'db', 'jsonfile');
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
          }
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

// Function to clear mapperStorage directory
function clearMapperStorage() {
  try {
    const mapperStorageDir = path.join(__dirname, 'mapperStorage');
    if (fs.existsSync(mapperStorageDir)) {
      const files = fs.readdirSync(mapperStorageDir);
      files.forEach(file => {
        const filePath = path.join(mapperStorageDir, file);
        fs.unlinkSync(filePath);
      });
      console.log(`🗑️  Cleared ${files.length} files from mapperStorage`);
    } else {
      console.log('🗑️  MapperStorage directory does not exist - nothing to clear');
    }
  } catch (error) {
    console.error('Error clearing mapperStorage:', error);
  }
}

// Function to create mapperStorage directory
function createMapperStorageDir() {
  try {
    const mapperStorageDir = path.join(__dirname, 'mapperStorage');
    if (!fs.existsSync(mapperStorageDir)) {
      fs.mkdirSync(mapperStorageDir, { recursive: true });
      console.log('Created mapperStorage directory');
    }
  } catch (error) {
    console.error('Error creating mapperStorage directory:', error);
  }
}

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

// Helper function to update progress
function updateProgress(updates) {
  currentProgress = { ...currentProgress, ...updates };
  
  // Don't auto-calculate percentage here - it's calculated in the progress endpoint
  // using the formula: 22 stocks = 1%
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


// Query endpoint for searching stocks based on conditions
app.post('/query',  async (req, res) => {
  try {
    const { query, stocks } = req.body;
    
    if (!query) {
      return res.status(400).json({ error: 'Query is required' });
    }

    // Abort any existing query
    abortCurrentQuery();
    
    // Clear mapperStorage directory and create it fresh
    clearMapperStorage();
    createMapperStorageDir();
    
    // Clear indicator cache to ensure fresh processing for new queries
    console.log('🧹 Clearing indicator cache for new query...');
    clearCache();
    
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
    
    // Ensure we always have indicators for mapperStorage generation
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
        
        // Always generate mapperStorage files for any query (includes basic fields and indicators)
        console.log(`Generating mapperStorage for ${stock} with indicators:`, requiredIndicators);
        console.log(`Using timeframes:`, requiredTimeframes);
        await generateStockJSON(stock, requiredIndicators, requiredTimeframes);
        
        // Read the generated mapped data from mapperStorage
        const mapperFilePath = path.join(__dirname, 'mapperStorage', `${stock}_piped.json`);
        let candles;
        
        if (fs.existsSync(mapperFilePath)) {
          const mappedData = JSON.parse(fs.readFileSync(mapperFilePath, 'utf8'));
          candles = mappedData.data;
        } else {
          errors.push({ stock, error: 'Mapped data not found in mapperStorage' });
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
    
    // Note: We no longer delete the mapperStorage directory
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
    
    // Note: We no longer delete the mapperStorage directory on error
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
    
    // Clear mapperStorage directory and create it fresh
    clearMapperStorage();
    createMapperStorageDir();
    
    // Clear indicator cache to ensure fresh processing for new queries
    console.log('🧹 Clearing indicator cache for latest day scan...');
    clearCache();
    
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
    
    // Ensure we always have indicators for mapperStorage generation
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
        
        // Generate mapperStorage files with indicators
        await generateStockJSON(stock, requiredIndicators, requiredTimeframes);
        
        // Read the generated mapped data from mapperStorage
        const mapperFilePath = path.join(__dirname, 'mapperStorage', `${stock}_piped.json`);
        let candles;
        
        if (fs.existsSync(mapperFilePath)) {
          const mappedData = JSON.parse(fs.readFileSync(mapperFilePath, 'utf8'));
          candles = mappedData.data;
        } else {
          errors.push({ stock, error: 'Mapped data not found in mapperStorage' });
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
                allMatches.push({
                  date: latestCandle.date,
                  day: latestCandle.day,
                  timestamp: new Date(parseInt(latestCandle.date)).toISOString(),
                  stock: stock,
                  close: latestCandle.close,
                  matchedConditions: query
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
  const cancelToken = globalRefreshState.cancelToken;
  const progress = globalRefreshState.progress;
  
  try {
    const dbPath = path.join(__dirname, 'db');
    
    // Process in batches
    const batchSize = 10;
    const batches = [];
    
    for (let i = 0; i < STOCK_SYMBOLS.length; i += batchSize) {
      batches.push(STOCK_SYMBOLS.slice(i, i + batchSize));
    }
    
    for (let batchIndex = 0; batchIndex < batches.length; batchIndex++) {
      // Check for cancellation
      if (cancelToken.cancel) {
        console.log('Refresh cancelled by user');
        progress.status = 'cancelled';
        progress.message = 'Refresh cancelled by user';
        globalRefreshState.isRunning = false;
        return;
      }
      
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
            timeout: 30000
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
          
          progress.successful++;
          console.log(`✓ ${symbol} - ${mappedData.length} records saved`);
          
        } catch (error) {
          progress.failed++;
          progress.errors.push({ symbol, error: error.message });
          console.error(`✗ ${symbol} - Error: ${error.message}`);
        }
        
        progress.processed++;
        progress.percentage = Math.round((progress.processed / progress.total) * 100);
        progress.currentSymbol = symbol;
      });
      
      // Wait for batch to complete
      await Promise.all(batchPromises);
      
      // Add delay between batches
      if (batchIndex < batches.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
    }
    
    progress.status = 'completed';
    progress.message = `Database refresh completed. ${progress.successful} symbols updated successfully.`;
    globalRefreshState.isRunning = false;
    console.log(`Database refresh completed! Processed: ${progress.processed}, Successful: ${progress.successful}, Failed: ${progress.failed}`);
    
  } catch (error) {
    progress.status = 'error';
    progress.error = error.message;
    globalRefreshState.isRunning = false;
    console.error('Database refresh error:', error);
  }
}

// Start server
app.listen(port, () => {
  console.log(`Server is running on http://localhost:${port}`);
  console.log('Available endpoints:');
  console.log('  GET /query/progress - Get current query progress');
  console.log('  POST /query - Execute stock query');
  console.log('  GET /health - Server health check');
});