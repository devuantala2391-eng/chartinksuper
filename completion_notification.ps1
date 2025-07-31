Write-Host ""
Write-Host "========================================"
Write-Host "         TASK COMPLETED!"
Write-Host "========================================"
Write-Host ""

# Log to file for debugging
$logFile = "D:\chartinksuper\hook_debug.log"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $logFile -Value "$timestamp - Hook triggered"

# Play LOUD bell sequence - multiple rounds
for ($i = 1; $i -le 3; $i++) {
    [console]::beep(1000,300)  # High pitch
    [console]::beep(800,300)   # Medium pitch  
    [console]::beep(1200,400)  # Very high pitch
    Start-Sleep -Milliseconds 100
}

# Additional system bell sounds
[console]::beep(1500,500)  # Very loud high beep
[console]::beep(500,500)   # Low beep
[console]::beep(1500,500)  # Very loud high beep again

# Show balloon notification if possible
try {
    Add-Type -AssemblyName System.Windows.Forms
    $notification = New-Object System.Windows.Forms.NotifyIcon
    $notification.Icon = [System.Drawing.SystemIcons]::Information
    $notification.BalloonTipTitle = "Claude Task Complete"
    $notification.BalloonTipText = "Your requested task has been completed!"
    $notification.Visible = $true
    $notification.ShowBalloonTip(3000)
    Start-Sleep -Seconds 4
    $notification.Dispose()
    Add-Content -Path $logFile -Value "$timestamp - Notification shown successfully"
} catch {
    Add-Content -Path $logFile -Value "$timestamp - Notification failed: $($_.Exception.Message)"
}