// Performance test script to compare old vs new bulk processing
const axios = require('axios');

const SERVER_URL = 'http://localhost:3000';

async function testRefreshPerformance() {
  console.log('🏁 Testing RefreshDB Performance\n');
  
  try {
    console.log('Starting refresh with BULK processing...');
    const startTime = Date.now();
    
    // Start refresh
    const refreshResponse = await axios.post(`${SERVER_URL}/refreshdb`, {
      totalResults: 1000 // Smaller dataset for testing
    });
    
    console.log('✅ Refresh started:', refreshResponse.data.message);
    console.log(`📊 Total symbols to process: ${refreshResponse.data.total}\n`);
    
    // Monitor progress
    let isCompleted = false;
    let lastProcessed = 0;
    let lastTime = startTime;
    
    while (!isCompleted) {
      await new Promise(resolve => setTimeout(resolve, 2000)); // Check every 2 seconds
      
      try {
        const progressResponse = await axios.get(`${SERVER_URL}/refreshdb-progress`);
        const progress = progressResponse.data;
        
        if (progress.status === 'idle') {
          console.log('❌ No refresh in progress');
          break;
        }
        
        const currentTime = Date.now();
        const timeDiff = (currentTime - lastTime) / 1000; // seconds
        const processedDiff = progress.processed - lastProcessed;
        const ratePerSecond = processedDiff / timeDiff;
        
        console.log(`📈 Progress: ${progress.processed}/${progress.total} (${progress.percentage}%)`);
        console.log(`📊 Success: ${progress.successful}, Failed: ${progress.failed}`);
        console.log(`⚡ Rate: ${ratePerSecond.toFixed(1)} symbols/sec`);
        console.log(`🔄 Current: ${progress.currentSymbol}`);
        console.log('---');
        
        lastProcessed = progress.processed;
        lastTime = currentTime;
        
        if (progress.status === 'completed' || progress.status === 'error' || progress.status === 'cancelled') {
          isCompleted = true;
          
          const totalTime = (Date.now() - startTime) / 1000;
          const avgRate = progress.processed / totalTime;
          
          console.log(`\n🎯 FINAL RESULTS:`);
          console.log(`⏱️  Total time: ${totalTime.toFixed(1)} seconds`);
          console.log(`📊 Processed: ${progress.processed} symbols`);
          console.log(`✅ Successful: ${progress.successful}`);
          console.log(`❌ Failed: ${progress.failed}`);
          console.log(`⚡ Average rate: ${avgRate.toFixed(1)} symbols/sec`);
          console.log(`🚀 Status: ${progress.status}`);
          
          if (progress.status === 'completed') {
            console.log(`\n🎉 ${progress.message}`);
            
            // Performance comparison
            console.log(`\n📈 PERFORMANCE COMPARISON:`);
            console.log(`🐌 Old method (10 per batch + 1s delay): ~${(progress.processed * 1.1).toFixed(0)} seconds`);
            console.log(`🚀 New BULK method: ${totalTime.toFixed(1)} seconds`);
            console.log(`📊 Speed improvement: ${((progress.processed * 1.1) / totalTime).toFixed(1)}x faster!`);
          }
        }
        
      } catch (progressError) {
        console.error('❌ Error checking progress:', progressError.message);
        break;
      }
    }
    
  } catch (error) {
    console.error('❌ Test failed:', error.message);
    
    if (error.code === 'ECONNREFUSED') {
      console.log('\n💡 Make sure the server is running: node server.js');
    }
  }
}

// Configuration test
console.log('🔧 BULK Processing Configuration:');
console.log(`📊 Concurrent limit: ${process.env.CONCURRENT_LIMIT || '100 (default)'}`);
console.log(`🔄 Connection retries: 3`);
console.log(`⏱️  Request timeout: 45 seconds`);
console.log(`🔗 Keep-alive connections: enabled\n`);

// Run the test
testRefreshPerformance();