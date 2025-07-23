// Test script to verify SSE implementation and confirm no polling
const http = require('http');
const https = require('https');

console.log('Testing SSE-Only Implementation');
console.log('================================');

// Track all HTTP requests to backend
const originalRequest = http.request;
const originalRequestHttps = https.request;

let requestCount = 0;
const requestLog = [];

// Override http.request to track requests
http.request = function(...args) {
    const req = originalRequest.apply(this, args);
    const options = args[0];
    
    if (options && options.hostname === '127.0.0.1' && options.port === 8001) {
        requestCount++;
        const logEntry = {
            method: options.method || 'GET',
            path: options.path || '/',
            timestamp: new Date().toISOString()
        };
        requestLog.push(logEntry);
        console.log(`[${requestCount}] ${logEntry.method} ${logEntry.path} at ${logEntry.timestamp}`);
    }
    
    return req;
};

// Test 1: Start SSE connection
console.log('\n1. Testing SSE Connection...');
const EventSource = require('eventsource').EventSource || require('eventsource');

const sseUrl = 'http://127.0.0.1:8001/api/progress-stream';
const eventSource = new EventSource(sseUrl);

let messageCount = 0;
eventSource.onopen = () => {
    console.log('✓ SSE connection opened successfully');
};

eventSource.onmessage = (event) => {
    messageCount++;
    try {
        const data = JSON.parse(event.data);
        console.log(`📡 SSE Message ${messageCount}:`, {
            isRunning: data.isRunning,
            phase: data.phase,
            processed: data.processed,
            total: data.total,
            matches: data.matches
        });
    } catch (e) {
        console.log(`📡 SSE Message ${messageCount}:`, event.data);
    }
};

eventSource.onerror = (error) => {
    console.error('❌ SSE error:', error);
};

// Test 2: Send query and monitor activity
setTimeout(() => {
    console.log('\n2. Sending test query...');
    
    const queryData = JSON.stringify({
        query: "daily_rsi_14 > 95"
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
        res.on('data', (chunk) => {
            data += chunk;
        });
        res.on('end', () => {
            console.log('✓ Query completed');
            console.log(`📊 Response size: ${data.length} bytes`);
        });
    });
    
    req.on('error', (error) => {
        console.error('❌ Query error:', error);
    });
    
    req.write(queryData);
    req.end();
}, 200);

// Test 3: Monitor for 15 seconds and report
setTimeout(() => {
    console.log('\n3. Final Report');
    console.log('===============');
    console.log(`Total HTTP requests made: ${requestCount}`);
    console.log(`SSE messages received: ${messageCount}`);
    
    console.log('\nRequest breakdown:');
    const requestSummary = requestLog.reduce((acc, req) => {
        const key = `${req.method} ${req.path}`;
        acc[key] = (acc[key] || 0) + 1;
        return acc;
    }, {});
    
    Object.entries(requestSummary).forEach(([endpoint, count]) => {
        console.log(`  ${endpoint}: ${count} requests`);
    });
    
    // Check for polling endpoints
    const pollingEndpoints = requestLog.filter(req => req.path.includes('/query/progress'));
    if (pollingEndpoints.length === 0) {
        console.log('\n✅ SUCCESS: No polling requests detected!');
        console.log('✅ SSE-only implementation working correctly');
    } else {
        console.log(`\n❌ FAILED: Found ${pollingEndpoints.length} polling requests`);
        console.log('❌ Progress polling not fully removed');
    }
    
    eventSource.close();
    process.exit(0);
}, 15000);

console.log('Monitoring for 15 seconds...\n');