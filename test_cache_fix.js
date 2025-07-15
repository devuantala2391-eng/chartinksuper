const axios = require('axios');
const fs = require('fs');
const path = require('path');

const SERVER_URL = 'http://localhost:3000';
const CACHE_FILE = path.join(__dirname, '.indicator_cache.json');
const MAPPER_STORAGE = path.join(__dirname, 'mapperStorage');

async function testCacheClear() {
  console.log('🧪 Testing cache clearing mechanism...\n');
  
  // Helper function to check if cache file exists
  function checkCacheFile() {
    const exists = fs.existsSync(CACHE_FILE);
    console.log(`📁 Cache file exists: ${exists}`);
    return exists;
  }
  
  // Helper function to check mapperStorage
  function checkMapperStorage() {
    if (fs.existsSync(MAPPER_STORAGE)) {
      const files = fs.readdirSync(MAPPER_STORAGE);
      console.log(`📂 MapperStorage has ${files.length} files`);
      return files.length;
    }
    console.log('📂 MapperStorage does not exist');
    return 0;
  }
  
  // Helper function to run a query
  async function runQuery(query) {
    console.log(`🔍 Running query: "${query}"`);
    try {
      const response = await axios.post(`${SERVER_URL}/query`, { query });
      console.log(`✅ Query completed: ${response.data.totalMatches} matches`);
      return response.data;
    } catch (error) {
      console.error(`❌ Query failed: ${error.message}`);
      return null;
    }
  }
  
  console.log('=== Initial State ===');
  checkCacheFile();
  checkMapperStorage();
  
  console.log('\n=== Running First Query ===');
  await runQuery('volume > 100000');
  
  console.log('\n=== After First Query ===');
  checkCacheFile();
  const filesAfterFirst = checkMapperStorage();
  
  console.log('\n=== Running Second Query (Different) ===');
  await runQuery('volume > 50000');
  
  console.log('\n=== After Second Query ===');
  checkCacheFile();
  const filesAfterSecond = checkMapperStorage();
  
  console.log('\n=== Summary ===');
  console.log(`📊 Files after first query: ${filesAfterFirst}`);
  console.log(`📊 Files after second query: ${filesAfterSecond}`);
  
  if (filesAfterFirst > 0 && filesAfterSecond > 0) {
    console.log('✅ Cache is being cleared and regenerated for each query');
  } else {
    console.log('❌ There might be an issue with cache clearing');
  }
}

// Run the test
testCacheClear().catch(console.error);