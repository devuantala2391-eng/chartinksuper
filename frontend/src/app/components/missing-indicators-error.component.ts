import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-missing-indicators-error',
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <div class="missing-indicators-error">
      <div class="error-header">
        <span class="error-icon">⚠️</span>
        <h3>Missing Precalculated Indicators</h3>
      </div>
      
      <div class="error-content">
        <p class="error-message">
          Your query requires the following indicators to be precalculated:
        </p>
        
        <div class="missing-indicators-list">
          <div class="indicator-item" *ngFor="let indicator of missingIndicators">
            <span class="indicator-badge">{{ indicator }}</span>
          </div>
        </div>
        
        <div class="error-actions">
          <a routerLink="/indicators" class="btn btn-primary">
            <span class="btn-icon">📊</span>
            Go to Indicators
          </a>
          <p class="help-text">
            Add these indicators in the Indicators tab and calculate them before running your query.
          </p>
        </div>
      </div>
    </div>
  `,
  styleUrl: './missing-indicators-error.component.scss'
})
export class MissingIndicatorsErrorComponent {
  @Input() missingIndicators: string[] = [];
  @Input() details: string = '';
}