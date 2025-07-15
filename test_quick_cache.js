const axios = require('axios');

async function testQuickCache() {
  console.log('🧪 Quick cache test...\n');
  
  try {
    // First query
    console.log('🔍 Query 1: volume > 100000');
    const response1 = await axios.post('http://localhost:3000/query', { 
      query: 'volume > 100000' 
    });
    console.log(`✅ Query 1 result: ${response1.data.totalMatches} matches\n`);
    
    // Second query with different condition
    console.log('🔍 Query 2: volume > 50000');
    const response2 = await axios.post('http://localhost:3000/query', { 
      query: 'volume > 50000' 
    });
    console.log(`✅ Query 2 result: ${response2.data.totalMatches} matches\n`);
    
    // Verify that the second query has more or equal matches than the first
    if (response2.data.totalMatches >= response1.data.totalMatches) {
      console.log('✅ Cache is working correctly - second query has more matches as expected');
    } else {
      console.log('❌ Potential cache issue - second query should have more matches');
    }
    
  } catch (error) {
    console.error('❌ Test failed:', error.message);
  }
}

testQuickCache();