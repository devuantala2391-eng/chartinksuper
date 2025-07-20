import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-progress-bar',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="progress-overlay" *ngIf="show">
      <div class="progress-container">
        <div class="progress-header">
          <h3>🔍 Scanning Stocks</h3>
          <button class="close-btn" (click)="onClose()" *ngIf="canClose">×</button>
        </div>
        
        <div class="progress-info">
          <div class="progress-phase">{{ phase }}</div>
          <div class="progress-message">{{ message }}</div>
        </div>
        
        <div class="progress-bar-wrapper">
          <div class="progress-bar">
            <div 
              class="progress-fill" 
              [style.width.%]="percentage"
              [class.completed]="phase === 'completed'"
            ></div>
          </div>
          <div class="progress-text">
            <span class="progress-numbers">{{ processed }} / {{ total }}</span>
            <span class="progress-percent">{{ percentage }}%</span>
          </div>
        </div>
        
        <div class="progress-stats" *ngIf="matches !== undefined">
          <div class="stat-item">
            <span class="stat-label">Matches Found:</span>
            <span class="stat-value">{{ matches }}</span>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .progress-overlay {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.7);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10000;
      animation: fadeIn 0.3s ease-out;
    }

    @keyframes fadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }

    .progress-container {
      background: white;
      border-radius: 12px;
      padding: 24px;
      min-width: 400px;
      max-width: 500px;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
      animation: slideUp 0.3s ease-out;
    }

    @keyframes slideUp {
      from { 
        opacity: 0;
        transform: translateY(20px);
      }
      to { 
        opacity: 1;
        transform: translateY(0);
      }
    }

    .progress-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      
      h3 {
        margin: 0;
        font-size: 1.5rem;
        color: #333;
      }
      
      .close-btn {
        background: none;
        border: none;
        font-size: 24px;
        cursor: pointer;
        color: #666;
        width: 32px;
        height: 32px;
        display: flex;
        align-items: center;
        justify-content: center;
        border-radius: 4px;
        transition: all 0.2s;
        
        &:hover {
          background: #f0f0f0;
          color: #333;
        }
      }
    }

    .progress-info {
      margin-bottom: 20px;
      
      .progress-phase {
        font-size: 12px;
        color: #666;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 4px;
      }
      
      .progress-message {
        font-size: 16px;
        color: #333;
        font-weight: 500;
      }
    }

    .progress-bar-wrapper {
      margin-bottom: 20px;
    }

    .progress-bar {
      height: 20px;
      background: #f0f0f0;
      border-radius: 10px;
      overflow: hidden;
      position: relative;
    }

    .progress-fill {
      height: 100%;
      background: linear-gradient(90deg, #6c63ff 0%, #5952d4 100%);
      border-radius: 10px;
      transition: width 0.3s ease-out;
      position: relative;
      overflow: hidden;
      
      &::after {
        content: '';
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: linear-gradient(
          90deg,
          transparent 0%,
          rgba(255, 255, 255, 0.3) 50%,
          transparent 100%
        );
        animation: shimmer 1.5s infinite;
      }
      
      &.completed {
        background: linear-gradient(90deg, #28a745 0%, #218838 100%);
      }
    }

    @keyframes shimmer {
      0% { transform: translateX(-100%); }
      100% { transform: translateX(100%); }
    }

    .progress-text {
      display: flex;
      justify-content: space-between;
      margin-top: 8px;
      font-size: 14px;
      color: #666;
      
      .progress-percent {
        font-weight: 600;
        color: #6c63ff;
      }
    }

    .progress-stats {
      border-top: 1px solid #eee;
      padding-top: 16px;
      
      .stat-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        
        .stat-label {
          font-size: 14px;
          color: #666;
        }
        
        .stat-value {
          font-size: 18px;
          font-weight: 600;
          color: #28a745;
        }
      }
    }

    @media (max-width: 480px) {
      .progress-container {
        min-width: 90%;
        margin: 0 16px;
      }
    }
  `]
})
export class ProgressBarComponent {
  @Input() show = false;
  @Input() phase = 'initializing';
  @Input() message = 'Starting...';
  @Input() processed = 0;
  @Input() total = 100;
  @Input() matches?: number;
  @Input() canClose = false;
  
  @Output() close = new EventEmitter<void>();
  
  get percentage(): number {
    if (this.total === 0) return 0;
    return Math.round((this.processed / this.total) * 100);
  }
  
  onClose() {
    this.close.emit();
  }
}