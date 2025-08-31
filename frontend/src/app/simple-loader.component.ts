import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-simple-loader',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="loader-overlay" *ngIf="show">
      <div class="loader-container">
        <div class="loader-content">
          <div class="spinner">
            <div class="spinner-ring"></div>
            <div class="spinner-ring"></div>
            <div class="spinner-ring"></div>
            <div class="spinner-ring"></div>
          </div>
          <div class="loader-text">
            <div class="loader-title">{{ title }}</div>
            <div class="loader-message">{{ message }}</div>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .loader-overlay {
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

    .loader-container {
      background: white;
      border-radius: 12px;
      padding: 32px;
      text-align: center;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
      animation: slideUp 0.3s ease-out;
      min-width: 300px;
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

    .loader-content {
      display: flex;
      flex-direction: column;
      align-items: center;
    }

    .spinner {
      position: relative;
      width: 60px;
      height: 60px;
      margin-bottom: 20px;
    }

    .spinner-ring {
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      border: 3px solid transparent;
      border-top-color: #6c63ff;
      border-radius: 50%;
      animation: spin 1.5s linear infinite;
    }

    .spinner-ring:nth-child(2) {
      animation-delay: 0.1s;
      border-top-color: #5952d4;
    }

    .spinner-ring:nth-child(3) {
      animation-delay: 0.2s;
      border-top-color: #4844b8;
    }

    .spinner-ring:nth-child(4) {
      animation-delay: 0.3s;
      border-top-color: #37359c;
    }

    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }

    .loader-text {
      .loader-title {
        font-size: 18px;
        font-weight: 600;
        color: #333;
        margin-bottom: 8px;
      }

      .loader-message {
        font-size: 14px;
        color: #666;
        line-height: 1.4;
      }
    }

    @media (max-width: 480px) {
      .loader-container {
        min-width: 90%;
        margin: 0 16px;
        padding: 24px;
      }

      .spinner {
        width: 48px;
        height: 48px;
      }
    }
  `]
})
export class SimpleLoaderComponent {
  @Input() show = false;
  @Input() title = 'Loading...';
  @Input() message = 'Please wait while we process your request.';
}