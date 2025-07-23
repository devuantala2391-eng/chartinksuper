import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-error-modal',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="modal-overlay" *ngIf="visible" (click)="onOverlayClick()">
      <div class="modal-content" (click)="$event.stopPropagation()">
        <div class="modal-header">
          <h3 class="modal-title">
            <svg class="error-icon" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            {{ title }}
          </h3>
          <button class="close-button" (click)="close()">&times;</button>
        </div>
        <div class="modal-body">
          <p class="error-message">{{ message }}</p>
          <div class="missing-items" *ngIf="missingItems && missingItems.length > 0">
            <p class="missing-label">Missing indicators:</p>
            <ul class="missing-list">
              <li *ngFor="let item of missingItems">{{ item }}</li>
            </ul>
          </div>
          <p class="help-text" *ngIf="helpText">{{ helpText }}</p>
        </div>
        <div class="modal-footer">
          <button class="btn-close" (click)="close()">Close</button>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .modal-overlay {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background-color: rgba(0, 0, 0, 0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 9999;
      animation: fadeIn 0.2s ease-out;
    }

    .modal-content {
      background: white;
      border-radius: 8px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
      max-width: 500px;
      width: 90%;
      max-height: 80vh;
      display: flex;
      flex-direction: column;
      animation: slideIn 0.3s ease-out;
    }

    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 20px;
      border-bottom: 1px solid #e9ecef;
    }

    .modal-title {
      margin: 0;
      font-size: 20px;
      font-weight: 600;
      color: #dc3545;
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .error-icon {
      color: #dc3545;
      flex-shrink: 0;
    }

    .close-button {
      background: none;
      border: none;
      font-size: 28px;
      cursor: pointer;
      color: #6c757d;
      padding: 0;
      width: 30px;
      height: 30px;
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 4px;
      transition: all 0.2s;

      &:hover {
        background: #f8f9fa;
        color: #000;
      }
    }

    .modal-body {
      padding: 20px;
      overflow-y: auto;
      flex: 1;
    }

    .error-message {
      margin: 0 0 16px 0;
      font-size: 16px;
      color: #212529;
      line-height: 1.5;
    }

    .missing-items {
      background: #fff3cd;
      border: 1px solid #ffeaa7;
      border-radius: 6px;
      padding: 16px;
      margin-bottom: 16px;
    }

    .missing-label {
      margin: 0 0 8px 0;
      font-weight: 600;
      color: #856404;
    }

    .missing-list {
      margin: 0;
      padding-left: 20px;
      
      li {
        color: #856404;
        margin-bottom: 4px;
        font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
        font-size: 14px;
      }
    }

    .help-text {
      margin: 0;
      font-size: 14px;
      color: #6c757d;
      font-style: italic;
    }

    .modal-footer {
      display: flex;
      justify-content: flex-end;
      padding: 16px 20px;
      border-top: 1px solid #e9ecef;
    }

    .btn-close {
      padding: 8px 24px;
      background: #dc3545;
      color: white;
      border: none;
      border-radius: 6px;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.2s;

      &:hover {
        background: #c82333;
        transform: translateY(-1px);
      }

      &:active {
        transform: translateY(0);
      }
    }

    @keyframes fadeIn {
      from {
        opacity: 0;
      }
      to {
        opacity: 1;
      }
    }

    @keyframes slideIn {
      from {
        transform: translateY(-20px);
        opacity: 0;
      }
      to {
        transform: translateY(0);
        opacity: 1;
      }
    }

    @media (max-width: 768px) {
      .modal-content {
        width: 95%;
        max-height: 90vh;
      }

      .modal-title {
        font-size: 18px;
      }

      .error-message {
        font-size: 14px;
      }
    }
  `]
})
export class ErrorModalComponent {
  @Input() visible: boolean = false;
  @Input() title: string = 'Error';
  @Input() message: string = '';
  @Input() missingItems: string[] = [];
  @Input() helpText: string = '';
  @Output() closeModal = new EventEmitter<void>();

  close() {
    this.closeModal.emit();
  }

  onOverlayClick() {
    this.close();
  }
}