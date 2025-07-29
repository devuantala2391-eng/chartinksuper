import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { SchedulerService, SchedulerState } from '../services/scheduler.service';
import { Observable } from 'rxjs';
import Swal from 'sweetalert2';

@Component({
  selector: 'app-scheduler-control',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="scheduler-control" *ngIf="state$ | async as state">
      <!-- Compact Timer Display -->
      <div class="timer-section" [class.running]="state.isRunning">
        <div class="timer-icon" [class.active]="state.isRunning">
          <span>🕒</span>
        </div>
        
        <div class="timer-info">
          <div class="timer-status">
            <span class="status-dot" [class.active]="state.isRunning"></span>
            <span class="status-text">{{ state.isRunning ? 'Running' : 'Stopped' }}</span>
          </div>
          
          <div class="timer-countdown" *ngIf="state.isRunning && state.timeToNextUpdate > 0">
            Next: {{ formatTime(state.timeToNextUpdate) }}
            <span class="progress-mini">({{ state.progressPercentage }}%)</span>
          </div>
        </div>
      </div>

      <!-- Control Buttons -->
      <div class="control-buttons">
        <button 
          class="control-btn start" 
          *ngIf="!state.isRunning"
          (click)="start()"
          [disabled]="isLoading"
          title="Start scheduler">
          <span>▶️</span>
        </button>
        
        <button 
          class="control-btn stop" 
          *ngIf="state.isRunning"
          (click)="stop()"
          [disabled]="isLoading"
          title="Stop scheduler">
          <span>⏹️</span>
        </button>
        
        <button 
          class="control-btn refresh" 
          (click)="update()"
          [disabled]="isLoading || state.isUpdating"
          [class.updating]="state.isUpdating"
          title="Update now">
          <span [class.spin]="state.isUpdating">🔄</span>
        </button>
      </div>

      <!-- Quick Settings -->
      <div class="quick-settings">
        <select 
          [(ngModel)]="updateInterval" 
          (change)="onIntervalChange()"
          [disabled]="state.isRunning"
          class="interval-select"
          title="Update interval">
          <option [value]="1">1m</option>
          <option [value]="2">2m</option>
          <option [value]="5">5m</option>
          <option [value]="10">10m</option>
          <option [value]="15">15m</option>
        </select>
        
        <label class="force-toggle" title="Force run (ignore market hours)">
          <input 
            type="checkbox" 
            [(ngModel)]="forceRun"
            [disabled]="state.isRunning">
          <span class="toggle-slider"></span>
        </label>
      </div>

      <!-- Stats Badge -->
      <div class="stats-badge" *ngIf="state.updateStats">
        <span class="stat updated" title="Updated">{{ state.updateStats.updated }}</span>
        <span class="stat unchanged" title="Unchanged">{{ state.updateStats.unchanged }}</span>
        <span class="stat errors" *ngIf="state.updateStats.errors > 0" title="Errors">{{ state.updateStats.errors }}</span>
      </div>
    </div>
  `,
  styles: [`
    .scheduler-control {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 8px 16px;
      background: rgba(255, 255, 255, 0.05);
      border-radius: 12px;
      backdrop-filter: blur(10px);
    }

    /* Timer Section */
    .timer-section {
      display: flex;
      align-items: center;
      gap: 12px;
      padding-right: 16px;
      border-right: 1px solid rgba(255, 255, 255, 0.1);
    }

    .timer-icon {
      font-size: 24px;
      opacity: 0.5;
      transition: all 0.3s ease;
    }

    .timer-icon.active {
      opacity: 1;
      animation: pulse 2s infinite;
    }

    @keyframes pulse {
      0%, 100% { transform: scale(1); }
      50% { transform: scale(1.1); }
    }

    .timer-info {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .timer-status {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      opacity: 0.8;
    }

    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #e57373;
      transition: all 0.3s ease;
    }

    .status-dot.active {
      background: #4caf50;
      animation: blink 1s infinite;
    }

    @keyframes blink {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.3; }
    }

    .timer-countdown {
      font-size: 14px;
      font-weight: 700;
      color: #2196f3;
    }

    .progress-mini {
      font-size: 11px;
      opacity: 0.7;
      margin-left: 4px;
    }

    /* Control Buttons */
    .control-buttons {
      display: flex;
      gap: 8px;
    }

    .control-btn {
      width: 32px;
      height: 32px;
      border: none;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      transition: all 0.3s ease;
      font-size: 16px;
      background: rgba(255, 255, 255, 0.1);
    }

    .control-btn:hover:not(:disabled) {
      transform: translateY(-2px);
      background: rgba(255, 255, 255, 0.2);
    }

    .control-btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    .control-btn.start {
      background: rgba(76, 175, 80, 0.2);
    }

    .control-btn.start:hover:not(:disabled) {
      background: rgba(76, 175, 80, 0.3);
    }

    .control-btn.stop {
      background: rgba(244, 67, 54, 0.2);
    }

    .control-btn.stop:hover:not(:disabled) {
      background: rgba(244, 67, 54, 0.3);
    }

    .control-btn.refresh {
      background: rgba(33, 150, 243, 0.2);
    }

    .control-btn.refresh:hover:not(:disabled) {
      background: rgba(33, 150, 243, 0.3);
    }

    .spin {
      display: inline-block;
      animation: spin 1s linear infinite;
    }

    @keyframes spin {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }

    /* Quick Settings */
    .quick-settings {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .interval-select {
      padding: 6px 10px;
      border: 1px solid rgba(255, 255, 255, 0.2);
      border-radius: 6px;
      background: rgba(0, 0, 0, 0.2);
      color: inherit;
      font-size: 12px;
      cursor: pointer;
      transition: all 0.3s ease;
    }

    .interval-select:hover:not(:disabled) {
      border-color: rgba(255, 255, 255, 0.3);
    }

    .interval-select:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    /* Toggle Switch */
    .force-toggle {
      position: relative;
      display: inline-block;
      width: 40px;
      height: 20px;
    }

    .force-toggle input {
      opacity: 0;
      width: 0;
      height: 0;
    }

    .toggle-slider {
      position: absolute;
      cursor: pointer;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background-color: rgba(255, 255, 255, 0.2);
      transition: .4s;
      border-radius: 20px;
    }

    .toggle-slider:before {
      position: absolute;
      content: "";
      height: 14px;
      width: 14px;
      left: 3px;
      bottom: 3px;
      background-color: white;
      transition: .4s;
      border-radius: 50%;
    }

    input:checked + .toggle-slider {
      background-color: #2196f3;
    }

    input:checked + .toggle-slider:before {
      transform: translateX(20px);
    }

    input:disabled + .toggle-slider {
      opacity: 0.5;
      cursor: not-allowed;
    }

    /* Stats Badge */
    .stats-badge {
      display: flex;
      gap: 8px;
      padding-left: 16px;
      border-left: 1px solid rgba(255, 255, 255, 0.1);
    }

    .stat {
      padding: 4px 8px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 600;
      background: rgba(255, 255, 255, 0.1);
    }

    .stat.updated {
      background: rgba(76, 175, 80, 0.2);
      color: #81c784;
    }

    .stat.unchanged {
      background: rgba(255, 235, 59, 0.2);
      color: #fff59d;
    }

    .stat.errors {
      background: rgba(244, 67, 54, 0.2);
      color: #ef5350;
    }

    /* Responsive */
    @media (max-width: 768px) {
      .scheduler-control {
        flex-wrap: wrap;
        gap: 12px;
        padding: 12px;
      }

      .timer-section {
        padding-right: 12px;
        margin-right: 0;
        border-right: none;
        width: 100%;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        padding-bottom: 12px;
      }

      .stats-badge {
        display: none;
      }
    }
  `]
})
export class SchedulerControlComponent implements OnInit {
  state$: Observable<SchedulerState>;
  isLoading = false;
  updateInterval = 2;
  forceRun = true;

  constructor(private schedulerService: SchedulerService) {
    this.state$ = this.schedulerService.state$;
  }

  ngOnInit() {
    // Subscribe to state to sync local settings
    this.state$.subscribe(state => {
      this.updateInterval = state.updateInterval;
      this.forceRun = state.forceRun;
    });
  }

  formatTime(seconds: number): string {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  }

  async start() {
    this.isLoading = true;
    try {
      const response = await this.schedulerService.startScheduler(this.updateInterval, this.forceRun);
      Swal.fire({
        icon: 'success',
        title: 'Scheduler Started',
        text: response.message || 'Periodic updates started successfully',
        timer: 2000,
        showConfirmButton: false,
        position: 'top-end',
        toast: true
      });
    } catch (error: any) {
      Swal.fire({
        icon: 'error',
        title: 'Failed to Start',
        text: error.error?.detail || 'Could not start the scheduler',
        confirmButtonColor: '#f44336'
      });
    } finally {
      this.isLoading = false;
    }
  }

  async stop() {
    this.isLoading = true;
    try {
      const response = await this.schedulerService.stopScheduler();
      Swal.fire({
        icon: 'success',
        title: 'Scheduler Stopped',
        text: response.message || 'Periodic updates stopped successfully',
        timer: 2000,
        showConfirmButton: false,
        position: 'top-end',
        toast: true
      });
    } catch (error: any) {
      Swal.fire({
        icon: 'error',
        title: 'Failed to Stop',
        text: error.error?.detail || 'Could not stop the scheduler',
        confirmButtonColor: '#f44336'
      });
    } finally {
      this.isLoading = false;
    }
  }

  async update() {
    try {
      const response = await this.schedulerService.manualUpdate();
      Swal.fire({
        icon: 'success',
        title: 'Update Complete',
        html: `
          <div style="text-align: left;">
            <p><strong>Total:</strong> ${response.summary.total} symbols</p>
            <p><strong>Updated:</strong> ${response.summary.updated}</p>
            <p><strong>Unchanged:</strong> ${response.summary.unchanged}</p>
            ${response.summary.errors > 0 ? `<p><strong>Errors:</strong> ${response.summary.errors}</p>` : ''}
          </div>
        `,
        confirmButtonColor: '#4caf50'
      });
    } catch (error: any) {
      Swal.fire({
        icon: 'error',
        title: 'Update Failed',
        text: error.error?.detail || 'Could not update candles',
        confirmButtonColor: '#f44336'
      });
    }
  }

  onIntervalChange() {
    // Settings will be applied when scheduler is started next time
  }
}