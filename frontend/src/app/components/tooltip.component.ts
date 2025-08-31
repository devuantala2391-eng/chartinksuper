import { Component, Input, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface TooltipData {
  [key: string]: number | string;
}

@Component({
  selector: 'app-tooltip',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="tooltip-container" [ngClass]="{'visible': visible}">
      <div class="tooltip-content">
        <div class="tooltip-header">Parameter Values</div>
        <div class="tooltip-body">
          <div class="parameter-row" *ngFor="let item of parameterList">
            <span class="parameter-name">{{ item.name }}:</span>
            <span class="parameter-value">{{ item.value }}</span>
          </div>
        </div>
      </div>
    </div>
  `,
  styleUrl: './tooltip.component.scss'
})
export class TooltipComponent implements OnInit {
  @Input() visible: boolean = false;
  @Input() data: TooltipData = {};
  @Input() scanType: string = 'Values';
  
  parameterList: { name: string; value: string }[] = [];

  ngOnInit() {
    this.updateParameterList();
  }

  ngOnChanges() {
    this.updateParameterList();
  }

  private updateParameterList() {
    this.parameterList = Object.entries(this.data).map(([key, value]) => ({
      name: this.formatParameterName(key),
      value: this.formatParameterValue(value)
    }));
  }

  private formatParameterName(key: string): string {
    // Convert keys like 'indicator_param' to 'INDICATOR(param)'
    const parts = key.split('_');
    if (parts.length >= 2) {
      const indicator = parts[0].toUpperCase();
      const params = parts.slice(1);
      return `${indicator}(${params.join(', ')})`;
    }
    return key.toUpperCase();
  }

  private formatParameterValue(value: number | string): string {
    if (typeof value === 'number') {
      return value.toFixed(2);
    }
    return value.toString();
  }
}