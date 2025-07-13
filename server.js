const express = require('express');
const axios = require('axios');
const fs = require('fs');
const path = require('path');
const cors = require('cors');
const qs = require('qs');
const { parseQuery, findMatchingCandles, getQueryExamples } = require('./services/queryService');
const { STOCK_SYMBOLS } = require('./stockSymbols.constants');

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
        const queryString = "select high, low, open, close, volume, Upper Bollinger band(  20 ,  2 ) as 'ubb', Lower Bollinger band(  20 ,  2 ) as 'lbb', Sma(  Close ,  20 ) as 'sma'";
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
          const ubbs = groupData[5]?.ubb || [];
          const lbbs = groupData[6]?.lbb || [];
          const sma20s = groupData[7]?.sma || [];
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

// Query endpoint for searching stocks based on conditions
app.post('/query', async (req, res) => {
  try {
    const { query, stocks } = req.body;
    
    if (!query) {
      return res.status(400).json({ error: 'Query is required' });
    }
    
    // Parse the query
    let parsedQuery;
    try {
      parsedQuery = parseQuery(query);
    } catch (error) {
      return res.status(400).json({ 
        error: 'Invalid query format', 
        details: error.message,
        hint: 'Example: "daily upper bollinger band > daily close and weekly rsi > 60"'
      });
    }
    
    // If no stocks specified, get all available stocks from mapperStorage
    let stockList = stocks;
    if (!stockList || stockList.length === 0) {
      const mapperStorageDir = path.join(__dirname, 'mapperStorage');
      if (fs.existsSync(mapperStorageDir)) {
        const files = fs.readdirSync(mapperStorageDir);
        stockList = files
          .filter(file => file.endsWith('_piped.json'))
          .map(file => file.replace('_piped.json', ''));
      }
    }
    
    if (!stockList || stockList.length === 0) {
      return res.status(400).json({ 
        error: 'No stocks available for analysis',
        hint: 'Run test.js to generate mapped data first'
      });
    }
    
    const allMatches = [];
    const errors = [];
    
    // Process each stock
    for (const stock of stockList) {
      try {
        const mappedFilePath = path.join(__dirname, 'mapperStorage', `${stock}_piped.json`);
        
        if (!fs.existsSync(mappedFilePath)) {
          errors.push({ stock, error: 'Mapped data not found' });
          continue;
        }
        
        const mappedData = JSON.parse(fs.readFileSync(mappedFilePath, 'utf8'));
        const candles = mappedData.data;
        
        if (!candles || candles.length === 0) {
          errors.push({ stock, error: 'No candle data available' });
          continue;
        }
        
        // Find matching candles - the function handles data availability internally
        const matches = findMatchingCandles(candles, parsedQuery, stock);
        
        allMatches.push(...matches);
        
      } catch (error) {
        errors.push({ stock, error: error.message });
      }
    }
    
    // Sort matches by date (most recent first)
    allMatches.sort((a, b) => parseInt(b.date) - parseInt(a.date));
    
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
      totalMatches: allMatches.length,
      matches: allMatches,
      errors: errors.length > 0 ? errors : undefined,
      processedStocks: stockList.length
    });
    
  } catch (error) {
    console.error('Query endpoint error:', error);
    res.status(500).json({ 
      error: 'Internal server error', 
      details: error.message 
    });
  }
});

// Query examples endpoint
app.get('/query/examples', (req, res) => {
  res.json(getQueryExamples());
});

// Refresh DB endpoint - fetches data for all symbols and saves to db folder
app.post('/refreshdb', async (req, res) => {
  try {
    const { totalResults = 2000 } = req.body;
    
    console.log(`Starting database refresh for ${STOCK_SYMBOLS.length} symbols with ${totalResults} results each...`);
    
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
    
    // Process in batches to avoid overwhelming the API
    const batchSize = 10; // Process 10 symbols at a time
    const batches = [];
    
    for (let i = 0; i < STOCK_SYMBOLS.length; i += batchSize) {
      batches.push(STOCK_SYMBOLS.slice(i, i + batchSize));
    }
    
    // Process each batch
    for (const batch of batches) {
      const batchPromises = batch.map(async (symbol) => {
        try {
          const queryString = "select high, low, open, close, volume, Upper Bollinger band(  20 ,  2 ) as 'ubb', Lower Bollinger band(  20 ,  2 ) as 'lbb', Sma(  Close ,  20 ) as 'sma'";
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
            const ubbs = groupData[5]?.ubb || [];
            const lbbs = groupData[6]?.lbb || [];
            const sma20s = groupData[7]?.sma || [];
            
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
                  ubb: ubbs[idx] !== undefined && ubbs[idx] !== null ? String(ubbs[idx]) : '',
                  lbb: lbbs[idx] !== undefined && lbbs[idx] !== null ? String(lbbs[idx]) : '',
                  sma20: sma20s[idx] !== undefined && sma20s[idx] !== null ? String(sma20s[idx]) : ''
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
        
        // Send progress update every 50 symbols
        if (processed % 50 === 0) {
          console.log(`Progress: ${processed}/${STOCK_SYMBOLS.length} (${successful} successful, ${failed} failed)`);
        }
      });
      
      // Wait for batch to complete
      await Promise.all(batchPromises);
      
      // Add a small delay between batches to avoid rate limiting
      if (batches.indexOf(batch) < batches.length - 1) {
        await new Promise(resolve => setTimeout(resolve, 1000)); // 1 second delay
      }
    }
    
    console.log(`Database refresh completed! Processed: ${processed}, Successful: ${successful}, Failed: ${failed}`);
    
    res.json({
      success: true,
      totalSymbols: STOCK_SYMBOLS.length,
      processed,
      successful,
      failed,
      errors: errors.length > 0 ? errors : undefined,
      message: `Database refresh completed. ${successful} symbols updated successfully.`
    });
    
  } catch (error) {
    console.error('Database refresh error:', error);
    res.status(500).json({ 
      error: 'Internal server error', 
      details: error.message 
    });
  }
});

// Start server
app.listen(port, () => {
  console.log(`Server is running on http://localhost:${port}`);
});