#!/usr/bin/env node
/**
 * Claude hook for task completion notifications
 * This hook runs when Claude completes tasks
 */

const { exec } = require('child_process');
const os = require('os');

// Function to make notification sound
function notifyCompletion(message) {
    console.log('\n🔔 TASK COMPLETED! 🔔');
    console.log('=' + '='.repeat(50));
    console.log(message || 'All tasks have been completed successfully!');
    console.log('=' + '='.repeat(50));
    
    // Platform-specific notification commands
    if (os.platform() === 'win32') {
        // Windows: PowerShell beep
        exec('powershell -c "[console]::beep(523,200); [console]::beep(659,200); [console]::beep(784,400)"');
        
        // Windows notification
        exec(`msg "%username%" /TIME:10 "Claude Task Completed! ${message}"`);
        
    } else if (os.platform() === 'darwin') {
        // macOS: System sound and notification
        exec('afplay /System/Library/Sounds/Glass.aiff');
        exec(`osascript -e 'display notification "${message}" with title "Claude Task Completed"'`);
        
    } else {
        // Linux: Terminal bell
        console.log('\x07\x07\x07');
        exec(`notify-send "Claude Task Completed" "${message}"`);
    }
}

// Check if this is a completion event
const args = process.argv.slice(2);
const eventType = args[0];

if (eventType === 'task-complete' || eventType === 'response-end') {
    notifyCompletion(args[1] || 'Task completed!');
}

// Export for use in other hooks
module.exports = { notifyCompletion };