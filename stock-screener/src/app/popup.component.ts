import { Component, EventEmitter, Output, HostListener, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PopupConfig } from './popup.service';

@Component({
  selector: 'app-popup',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="popup-container" [ngClass]="'popup-' + config.type">
      <!-- Field selector -->
      <div *ngIf="config.type === 'field'" class="popup-content">
        <div class="popup-search">
          <input 
            type="text" 
            [(ngModel)]="searchTerm" 
            placeholder="Search fields..."
            class="search-input"
            (keyup)="filterOptions()"
            #searchInput
          />
        </div>
        <div class="popup-options">
          <div 
            *ngFor="let option of filteredOptions" 
            class="popup-option"
            [class.selected]="option.value === config.value"
            (click)="selectOption(option)"
          >
            <span class="option-label">{{ option.label }}</span>
            <span class="option-hint" *ngIf="option.hint">{{ option.hint }}</span>
          </div>
        </div>
      </div>

      <!-- Operator selector -->
      <div *ngIf="config.type === 'operator'" class="popup-content compact">
        <div 
          *ngFor="let op of operators" 
          class="popup-option operator"
          [class.selected]="op.value === config.value"
          (click)="selectValue(op.value)"
        >
          {{ op.label }}
        </div>
      </div>

      <!-- Value input -->
      <div *ngIf="config.type === 'value'" class="popup-content value-input">
        <div class="value-type-selector">
          <button 
            class="type-btn"
            [class.active]="valueType === 'number'"
            (click)="setValueType('number')"
          >
            Number
          </button>
          <button 
            class="type-btn"
            [class.active]="valueType === 'field'"
            (click)="setValueType('field')"
          >
            Field
          </button>
        </div>
        
        <div *ngIf="valueType === 'number'" class="number-input">
          <input 
            type="text" 
            [(ngModel)]="numberValue"
            placeholder="Enter value"
            class="value-field"
            (keyup.enter)="submitValue()"
            #numberInput
          />
          <button class="submit-btn" (click)="submitValue()">✓</button>
        </div>
        
        <div *ngIf="valueType === 'field'" class="field-selector">
          <select [(ngModel)]="fieldValue" class="field-select">
            <option *ngFor="let field of fields" [value]="field.value">
              {{ field.label }}
            </option>
          </select>
          <button class="submit-btn" (click)="submitFieldValue()">✓</button>
        </div>
      </div>

      <!-- Timeframe selector -->
      <div *ngIf="config.type === 'timeframe'" class="popup-content compact">
        <div class="timeframe-input">
          <input 
            type="number" 
            [(ngModel)]="timeValue"
            min="0"
            class="time-input"
          />
          <select [(ngModel)]="timeUnit" class="time-unit">
            <option value="day">day(s) ago</option>
            <option value="week">week(s) ago</option>
            <option value="month">month(s) ago</option>
          </select>
          <button class="submit-btn" (click)="submitTimeframe()">✓</button>
        </div>
      </div>

      <!-- Indicator parameters -->
      <div *ngIf="config.type === 'indicator-params'" class="popup-content params">
        <h4>{{ config.value?.name }} Parameters</h4>
        <div class="param-inputs">
          <div *ngFor="let param of config.value?.params; let i = index" class="param-row">
            <label>{{ getParamLabel(config.value?.name, i) }}:</label>
            <input 
              type="text" 
              [value]="param"
              (input)="updateParam(i, $any($event.target).value)"
              class="param-input"
            />
          </div>
        </div>
        <button class="submit-btn primary" (click)="submitParams()">Apply</button>
      </div>
    </div>
  `,
  styles: [`
    .popup-container {
      background: white;
      border: 1px solid #ddd;
      border-radius: 8px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.15);
      min-width: 200px;
      max-width: 400px;
      animation: popIn 0.2s ease-out;
    }

    @keyframes popIn {
      from {
        opacity: 0;
        transform: scale(0.95) translateY(-10px);
      }
      to {
        opacity: 1;
        transform: scale(1) translateY(0);
      }
    }

    .popup-content {
      padding: 8px;
      max-height: 300px;
      overflow-y: auto;
      
      &.compact {
        padding: 4px;
      }
      
      &.value-input {
        padding: 12px;
      }
      
      &.params {
        padding: 16px;
      }
    }

    .popup-search {
      padding: 8px;
      border-bottom: 1px solid #eee;
    }

    .search-input {
      width: 100%;
      padding: 8px 12px;
      border: 1px solid #ddd;
      border-radius: 4px;
      font-size: 14px;
      
      &:focus {
        outline: none;
        border-color: #6c63ff;
      }
    }

    .popup-options {
      padding: 4px 0;
    }

    .popup-option {
      padding: 10px 16px;
      cursor: pointer;
      transition: background 0.2s;
      display: flex;
      justify-content: space-between;
      align-items: center;
      
      &:hover {
        background: #f5f5f5;
      }
      
      &.selected {
        background: #e8e6ff;
        color: #6c63ff;
        font-weight: 500;
      }
      
      &.operator {
        padding: 8px 16px;
        text-align: center;
        font-weight: 500;
      }
    }

    .option-label {
      font-size: 14px;
    }

    .option-hint {
      font-size: 12px;
      color: #888;
      margin-left: 8px;
    }

    .value-type-selector {
      display: flex;
      gap: 8px;
      margin-bottom: 12px;
    }

    .type-btn {
      flex: 1;
      padding: 8px 16px;
      border: 1px solid #ddd;
      background: white;
      border-radius: 4px;
      cursor: pointer;
      font-size: 14px;
      transition: all 0.2s;
      
      &.active {
        background: #6c63ff;
        color: white;
        border-color: #6c63ff;
      }
      
      &:hover:not(.active) {
        background: #f5f5f5;
      }
    }

    .number-input, .field-selector {
      display: flex;
      gap: 8px;
    }

    .value-field, .field-select {
      flex: 1;
      padding: 8px 12px;
      border: 1px solid #ddd;
      border-radius: 4px;
      font-size: 14px;
      
      &:focus {
        outline: none;
        border-color: #6c63ff;
      }
    }

    .timeframe-input {
      display: flex;
      gap: 8px;
      padding: 8px;
      align-items: center;
    }

    .time-input {
      width: 60px;
      padding: 8px;
      border: 1px solid #ddd;
      border-radius: 4px;
      font-size: 14px;
      text-align: center;
    }

    .time-unit {
      flex: 1;
      padding: 8px;
      border: 1px solid #ddd;
      border-radius: 4px;
      font-size: 14px;
    }

    .param-inputs {
      margin: 16px 0;
    }

    .param-row {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 12px;
      
      label {
        min-width: 80px;
        font-size: 14px;
        color: #666;
      }
      
      .param-input {
        flex: 1;
        padding: 8px 12px;
        border: 1px solid #ddd;
        border-radius: 4px;
        font-size: 14px;
      }
    }

    .submit-btn {
      padding: 8px 16px;
      background: #6c63ff;
      color: white;
      border: none;
      border-radius: 4px;
      cursor: pointer;
      font-size: 14px;
      transition: background 0.2s;
      
      &:hover {
        background: #5952d4;
      }
      
      &.primary {
        width: 100%;
        padding: 10px;
        font-weight: 500;
      }
    }
  `]
})
export class PopupComponent implements OnInit {
  @Output() closed = new EventEmitter<void>();
  
  config!: PopupConfig;
  searchTerm = '';
  filteredOptions: any[] = [];
  
  // Value input
  valueType: 'number' | 'field' = 'number';
  numberValue = '';
  fieldValue = '';
  
  // Timeframe
  timeValue = 0;
  timeUnit: 'day' | 'week' | 'month' = 'day';
  
  // Temp params
  tempParams: string[] = [];
  
  operators = [
    { value: '>', label: 'Greater than' },
    { value: '<', label: 'Less than' },
    { value: '>=', label: 'Greater or equal' },
    { value: '<=', label: 'Less or equal' },
    { value: '=', label: 'Equal to' },
    { value: '!=', label: 'Not equal to' },
    { value: 'crossed above', label: 'Crossed above' },
    { value: 'crossed below', label: 'Crossed below' }
  ];
  
  fields = [
    { value: 'open', label: 'Open' },
    { value: 'high', label: 'High' },
    { value: 'low', label: 'Low' },
    { value: 'close', label: 'Close' },
    { value: 'volume', label: 'Volume' },
    { value: 'rsi', label: 'RSI' },
    { value: 'supertrend', label: 'SuperTrend' },
    { value: 'bb', label: 'Bollinger Bands' },
    { value: 'pctchg', label: '% Change' }
  ];
  
  ngOnInit() {
    if (this.config.type === 'field' && this.config.options) {
      this.filteredOptions = [...this.config.options];
    }
    
    if (this.config.type === 'value' && this.config.value) {
      if (typeof this.config.value === 'object') {
        this.valueType = 'field';
        this.fieldValue = this.config.value.field || '';
      } else {
        this.valueType = 'number';
        this.numberValue = this.config.value.toString();
      }
    }
    
    if (this.config.type === 'timeframe' && this.config.value) {
      this.timeValue = this.config.value.value || 0;
      this.timeUnit = this.config.value.unit || 'day';
    }
    
    if (this.config.type === 'indicator-params' && this.config.value?.params) {
      this.tempParams = [...this.config.value.params];
    }
    
    // Auto-focus inputs
    setTimeout(() => {
      const input = document.querySelector('.search-input, .value-field') as HTMLInputElement;
      if (input) input.focus();
    });
  }
  
  filterOptions() {
    if (!this.config.options) return;
    
    const term = this.searchTerm.toLowerCase();
    this.filteredOptions = this.config.options.filter(option => 
      option.label.toLowerCase().includes(term)
    );
  }
  
  selectOption(option: any) {
    this.config.callback(option.value);
    this.closed.emit();
  }
  
  selectValue(value: any) {
    this.config.callback(value);
    this.closed.emit();
  }
  
  submitValue() {
    if (this.numberValue) {
      this.config.callback(this.numberValue);
      this.closed.emit();
    }
  }
  
  submitFieldValue() {
    if (this.fieldValue) {
      this.config.callback({ type: 'field', field: this.fieldValue });
      this.closed.emit();
    }
  }
  
  submitTimeframe() {
    this.config.callback({ value: this.timeValue, unit: this.timeUnit });
    this.closed.emit();
  }
  
  setValueType(type: 'number' | 'field') {
    this.valueType = type;
  }
  
  updateParam(index: number, value: string) {
    this.tempParams[index] = value;
  }
  
  submitParams() {
    this.config.callback(this.tempParams);
    this.closed.emit();
  }
  
  getParamLabel(indicator: string, index: number): string {
    const labels: { [key: string]: string[] } = {
      'rsi': ['Period'],
      'bb': ['Period', 'Std Dev'],
      'supertrend': ['Period', 'Multiplier'],
      'pctchg': ['Period']
    };
    
    return labels[indicator]?.[index] || `Param ${index + 1}`;
  }
  
  @HostListener('document:click', ['$event'])
  onClickOutside(event: MouseEvent) {
    if (!(event.target as HTMLElement).closest('.popup-container')) {
      this.closed.emit();
    }
  }
  
  @HostListener('document:keydown', ['$event'])
  onKeyDown(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      this.closed.emit();
    }
  }
}