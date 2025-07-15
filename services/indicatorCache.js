// Simple cache mechanism for indicator calculations
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const CACHE_FILE = path.join(__dirname, '..', '.indicator_cache.json');

// Generate a unique key for the set of indicators
function generateCacheKey(indicators) {
  const sorted = [...indicators].sort((a, b) => {
    const nameCompare = a.name.localeCompare(b.name);
    if (nameCompare !== 0) return nameCompare;
    return a.period - b.period;
  });
  
  const keyString = sorted.map(ind => 
    `${ind.name}_${ind.period}_${JSON.stringify(ind.params)}`
  ).join('|');
  
  return crypto.createHash('md5').update(keyString).digest('hex');
}

// Load cache
function loadCache() {
  try {
    if (fs.existsSync(CACHE_FILE)) {
      return JSON.parse(fs.readFileSync(CACHE_FILE, 'utf8'));
    }
  } catch (error) {
    console.warn('Failed to load cache:', error.message);
  }
  return {};
}

// Save cache
function saveCache(cache) {
  try {
    fs.writeFileSync(CACHE_FILE, JSON.stringify(cache, null, 2));
  } catch (error) {
    console.warn('Failed to save cache:', error.message);
  }
}

// Check if indicators are already processed
function isCached(indicators) {
  const cache = loadCache();
  const key = generateCacheKey(indicators);
  
  if (cache[key]) {
    const mapperStoragePath = path.join(__dirname, '..', 'mapperStorage');
    // Verify mapperStorage exists and has files
    if (fs.existsSync(mapperStoragePath)) {
      const files = fs.readdirSync(mapperStoragePath);
      if (files.length > 0) {
        console.log('Using cached indicator calculations');
        return true;
      }
    }
  }
  
  return false;
}

// Mark indicators as cached
function markAsCached(indicators) {
  const cache = loadCache();
  const key = generateCacheKey(indicators);
  cache[key] = {
    timestamp: Date.now(),
    indicators: indicators
  };
  saveCache(cache);
}

// Clear cache
function clearCache() {
  try {
    if (fs.existsSync(CACHE_FILE)) {
      fs.unlinkSync(CACHE_FILE);
    }
  } catch (error) {
    console.warn('Failed to clear cache:', error.message);
  }
}

module.exports = {
  isCached,
  markAsCached,
  clearCache
};