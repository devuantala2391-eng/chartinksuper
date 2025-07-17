// Test script to verify ECONNRESET error handling
const axios = require('axios');

// Test the retry mechanism
async function testConnectionHandling() {
  console.log('Testing connection handling and retry logic...');
  
  try {
    // Test with a quick query that should work
    const response = await axios.post('http://localhost:3000/query/latest', {
      query: 'daily_volume > 1000000'
    }, {
      timeout: 10000,
      maxRetries: 2
    });
    
    console.log('✅ Connection test passed!');
    console.log(`Response status: ${response.status}`);
    console.log(`Matches found: ${response.data?.totalMatches || 'N/A'}`);
    
  } catch (error) {
    console.log('❌ Connection test failed:');
    console.log(`Error code: ${error.code}`);
    console.log(`Error message: ${error.message}`);
    
    if (error.code === 'ECONNRESET') {
      console.log('✨ ECONNRESET error detected - this should now be handled with retries');
    }
    
    if (error.code === 'ECONNREFUSED') {
      console.log('💡 Server might not be running. Start with: node server.js');
    }
  }
}

// Run the test
testConnectionHandling();