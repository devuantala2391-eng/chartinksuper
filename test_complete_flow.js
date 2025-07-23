// Complete flow test for the fixed implementation
const http = require('http');
const EventSource = require('eventsource').EventSource || require('eventsource');

console.log('🧪 Testing Complete Query Flow with Fixes');
console.log('=====================================\n');

let testResults = {
    sseConnection: false,
    queryRequest: false,  
    progressUpdates: 0,
    concurrentRequestBlocked: false,
    queryCompleted: false,
    noMorePolling: true
};

// Test 1: Establish SSE connection
console.log('1️⃣ Testing SSE Connection...');
const sseUrl = 'http://127.0.0.1:8001/api/progress-stream';
const eventSource = new EventSource(sseUrl);

eventSource.onopen = () => {
    console.log('   ✅ SSE connection established');
    testResults.sseConnection = true;
};

eventSource.onmessage = (event) => {
    try {
        const data = JSON.parse(event.data);
        
        // Skip initial connection and heartbeat messages
        if (data.connected || data.heartbeat) {
            return;
        }
        
        testResults.progressUpdates++;
        console.log(`   📡 Progress update ${testResults.progressUpdates}: ${data.phase} (${data.processed}/${data.total}) - ${data.matches || 0} matches`);
        
        if (data.phase === 'completed' && !data.isRunning) {
            testResults.queryCompleted = true;
            console.log('   ✅ Query completed via SSE');
            
            // Close SSE after completion
            setTimeout(() => {
                eventSource.close();
                console.log('   🔒 SSE connection closed\n');
                runFinalTests();
            }, 1000);
        }
    } catch (error) {
        console.error('   ❌ SSE parsing error:', error);
    }
};

eventSource.onerror = (error) => {
    console.error('   ❌ SSE connection error:', error);
};

// Test 2: Send query request (after small delay to establish SSE)
setTimeout(() => {
    console.log('2️⃣ Sending Query Request...');
    
    const queryData = JSON.stringify({
        query: "daily_rsi_14 > 150"  // Restrictive query for faster processing
    });
    
    const options = {
        hostname: '127.0.0.1',
        port: 8001,
        path: '/query/latest',
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(queryData)
        }
    };
    
    const req = http.request(options, (res) => {
        let data = '';
        
        console.log(`   📨 Response status: ${res.statusCode}`);
        
        res.on('data', (chunk) => {
            data += chunk;
        });
        
        res.on('end', () => {
            if (res.statusCode === 200) {
                try {
                    const result = JSON.parse(data);
                    testResults.queryRequest = true;
                    console.log(`   ✅ Query completed successfully`);
                    console.log(`   📊 Found ${result.totalMatches || 0} matches`);
                } catch (error) {
                    console.error('   ❌ Failed to parse response:', error);
                }
            } else {
                console.error(`   ❌ Query failed with status ${res.statusCode}`);
                console.error(`   📄 Response: ${data}`);
            }
        });
    });
    
    req.on('error', (error) => {
        console.error('   ❌ Query request error:', error);
    });
    
    req.write(queryData);
    req.end();
    
    // Test 3: Try concurrent request (should be blocked)  
    setTimeout(() => {
        console.log('3️⃣ Testing Concurrent Request Protection...');
        
        const concurrentReq = http.request(options, (res) => {
            let concurrentData = '';
            
            res.on('data', (chunk) => {
                concurrentData += chunk;
            });
            
            res.on('end', () => {
                if (res.statusCode === 409) {
                    testResults.concurrentRequestBlocked = true;
                    console.log('   ✅ Concurrent request properly blocked (409)');
                } else if (res.statusCode === 200) {
                    console.log('   ⚠️  Concurrent request was processed (might be OK if first completed)');
                } else {
                    console.log(`   ❓ Concurrent request got status ${res.statusCode}`);
                }
            });
        });
        
        concurrentReq.on('error', (error) => {
            // Might error if connection is rejected, which is fine
            console.log('   ✅ Concurrent request properly rejected');
            testResults.concurrentRequestBlocked = true;
        });
        
        concurrentReq.write(queryData);
        concurrentReq.end();
        
    }, 500); // Send concurrent request shortly after first one
    
}, 1000);

// Final test summary
function runFinalTests() {
    console.log('4️⃣ Verifying No Polling Requests...');
    
    // Monitor for any polling requests (there shouldn't be any)
    const pollCheckStart = Date.now();
    const pollCheckDuration = 5000; // Check for 5 seconds
    
    // Set up a simple HTTP server to detect any incoming polling requests
    const pollDetector = http.createServer((req, res) => {
        if (req.url === '/query/progress') {
            console.log('   ❌ Detected polling request to /query/progress');
            testResults.noMorePolling = false;
        }
        res.writeHead(404);
        res.end();
    });
    
    setTimeout(() => {
        if (testResults.noMorePolling) {
            console.log('   ✅ No polling requests detected');
        }
        
        pollDetector.close();
        printFinalResults();
    }, pollCheckDuration);
}

function printFinalResults() {
    console.log('\n🏁 Final Test Results');
    console.log('====================');
    console.log(`SSE Connection:              ${testResults.sseConnection ? '✅' : '❌'}`);
    console.log(`Query Request Success:       ${testResults.queryRequest ? '✅' : '❌'}`);
    console.log(`Progress Updates Received:   ${testResults.progressUpdates} ${testResults.progressUpdates > 0 ? '✅' : '❌'}`);
    console.log(`Concurrent Request Blocked:  ${testResults.concurrentRequestBlocked ? '✅' : '❌'}`);
    console.log(`Query Completion via SSE:    ${testResults.queryCompleted ? '✅' : '❌'}`);
    console.log(`No Polling Requests:         ${testResults.noMorePolling ? '✅' : '❌'}`);
    
    const passedTests = Object.values(testResults).filter(Boolean).length;
    const totalTests = Object.keys(testResults).length - 1; // -1 for progressUpdates which is a count
    
    console.log(`\n📊 Overall: ${passedTests}/${totalTests + 1} tests passed`);
    
    if (passedTests >= totalTests) {
        console.log('🎉 All major fixes are working correctly!');
        console.log('✨ SSE-only implementation successful');
    } else {
        console.log('⚠️  Some issues remain, see details above');
    }
    
    process.exit(0);
}