import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { PopupService } from './popup.service';

interface CompactCondition {
  id: number;
  field: string;
  operator: string;
  value: string;
  logicalOperator: 'and' | 'or';
  daysAgo?: number;
  timeUnit: 'day' | 'week' | 'month';
  leftMultiplier?: number;
  valueType: 'number' | 'field';
  valueField?: string;
  valueDaysAgo?: number;
  valueTimeUnit?: 'day' | 'week' | 'month';
  multiplier?: number;
  indicatorType?: 'simple' | 'parameterized';
  indicatorName?: string;
  indicatorParams?: string[];
  valueIndicatorType?: 'simple' | 'parameterized';
  valueIndicatorName?: string;
  valueIndicatorParams?: string[];
}

@Component({
  selector: 'app-condition-compact',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="compact-condition-row">
      <div class="logical-operator" *ngIf="showLogicalOperator">
        <span class="operator-text" (click)="editLogicalOperator($event)">{{ condition.logicalOperator.toUpperCase() }}</span>
      </div>
      
      <div class="condition-sentence">
        <!-- Timeframe -->
        <span class="clickable timeframe" (click)="editTimeframe($event)" *ngIf="hasTimeframe()">
          {{ formatTimeframe() }}
        </span>
        
        <!-- Field -->
        <span class="clickable field" (click)="editField($event)">
          {{ formatField() }}
        </span>
        
        <!-- Indicator params -->
        <span class="clickable params" (click)="editIndicatorParams($event)" *ngIf="hasIndicatorParams()">
          ({{ condition.indicatorParams?.join(', ') }})
        </span>
        
        <!-- Operator -->
        <span class="clickable operator" (click)="editOperator($event)">
          {{ formatOperator() }}
        </span>
        
        <!-- Value -->
        <span class="clickable value" (click)="editValue($event)">
          {{ formatValue() }}
        </span>
        
        <!-- Value indicator params -->
        <span class="clickable params" (click)="editValueIndicatorParams($event)" *ngIf="hasValueIndicatorParams()">
          ({{ condition.valueIndicatorParams?.join(', ') }})
        </span>
        
        <!-- Action buttons -->
        <span class="action-buttons">
          <button class="icon-btn copy" (click)="copyCondition()" title="Copy condition">
            📋
          </button>
          <button class="icon-btn remove" (click)="removeCondition()" title="Remove condition" *ngIf="showRemove">
            ❌
          </button>
        </span>
      </div>
    </div>
  `,
  styles: [`
    .compact-condition-row {
      margin-bottom: 12px;
      font-size: 15px;
      line-height: 1.6;
    }
    
    .logical-operator {
      margin-bottom: 6px;
      
      .operator-text {
        display: inline-block;
        padding: 4px 12px;
        background: #e8e6ff;
        color: #6c63ff;
        border-radius: 4px;
        font-weight: 600;
        font-size: 12px;
        cursor: pointer;
        transition: all 0.2s;
        
        &:hover {
          background: #6c63ff;
          color: white;
        }
      }
    }
    
    .condition-sentence {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 6px;
      padding: 8px 0;
    }
    
    .clickable {
      padding: 6px 10px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.2s;
      border: 1px solid transparent;
      font-weight: 500;
      white-space: nowrap;
      
      &:hover {
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
      }
      
      &.timeframe {
        background: #fff3cd;
        color: #856404;
        border-color: #ffeaa7;
        
        &:hover {
          background: #ffeaa7;
        }
      }
      
      &.field {
        background: #d1ecf1;
        color: #0c5460;
        border-color: #bee5eb;
        
        &:hover {
          background: #bee5eb;
        }
      }
      
      &.operator {
        background: #f8d7da;
        color: #721c24;
        border-color: #f5c6cb;
        font-weight: 600;
        
        &:hover {
          background: #f5c6cb;
        }
      }
      
      &.value {
        background: #d4edda;
        color: #155724;
        border-color: #c3e6cb;
        font-weight: 600;
        
        &:hover {
          background: #c3e6cb;
        }
      }
      
      &.params {
        background: #e2e3e5;
        color: #383d41;
        border-color: #d6d8db;
        font-size: 13px;
        padding: 4px 8px;
        
        &:hover {
          background: #d6d8db;
        }
      }
    }
    
    .action-buttons {
      margin-left: auto;
      display: flex;
      gap: 8px;
      padding-left: 16px;
    }
    
    .icon-btn {
      width: 32px;
      height: 32px;
      border: none;
      background: transparent;
      cursor: pointer;
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 14px;
      transition: all 0.2s;
      
      &:hover {
        background: #f0f0f0;
        transform: scale(1.1);
      }
      
      &.copy {
        &:hover {
          background: #e3f2fd;
        }
      }
      
      &.remove {
        &:hover {
          background: #ffebee;
        }
      }
    }
    
    @media (max-width: 768px) {
      .condition-sentence {
        font-size: 14px;
      }
      
      .clickable {
        padding: 4px 8px;
        font-size: 13px;
      }
    }
  `]
})
export class ConditionCompactComponent {
  @Input() condition!: CompactCondition;
  @Input() showLogicalOperator = false;
  @Input() showRemove = true;
  @Output() conditionChange = new EventEmitter<CompactCondition>();
  @Output() remove = new EventEmitter<void>();
  
  fieldOptions = [
    { value: 'close', label: 'Close', hint: 'Daily closing price' },
    { value: 'open', label: 'Open', hint: 'Daily opening price' },
    { value: 'high', label: 'High', hint: 'Daily high' },
    { value: 'low', label: 'Low', hint: 'Daily low' },
    { value: 'volume', label: 'Volume', hint: 'Trading volume' },
    { value: 'rsi', label: 'RSI', hint: 'Relative Strength Index' },
    { value: 'sma', label: 'SMA', hint: 'Simple Moving Average' },
    { value: 'ema', label: 'EMA', hint: 'Exponential Moving Average' },
    { value: 'bb', label: 'Bollinger Bands', hint: 'BB upper/middle/lower' },
    { value: 'supertrend', label: 'SuperTrend', hint: 'Trend indicator' },
    { value: 'macd', label: 'MACD', hint: 'Moving Average Convergence' },
    { value: 'stochastic', label: 'Stochastic', hint: 'Momentum indicator' },
    { value: 'williamsr', label: 'Williams %R', hint: 'Overbought/oversold' }
  ];
  
  constructor(private popupService: PopupService) {}
  
  hasTimeframe(): boolean {
    return (this.condition.daysAgo !== undefined && this.condition.daysAgo > 0) ||
           this.condition.timeUnit !== 'day';
  }
  
  formatTimeframe(): string {
    const days = this.condition.daysAgo || 0;
    const unit = this.condition.timeUnit || 'day';
    
    if (days === 0 && unit === 'day') return 'Daily';
    if (days === 1 && unit === 'day') return '1 day ago';
    if (days === 1 && unit === 'week') return '1 week ago';
    
    return `${days} ${unit}${days > 1 ? 's' : ''} ago`;
  }
  
  formatField(): string {
    const field = this.fieldOptions.find(f => f.value === this.condition.field);
    return field?.label || this.condition.field;
  }
  
  formatOperator(): string {
    const operators: { [key: string]: string } = {
      '>': 'Greater than',
      '<': 'Less than',
      '>=': 'Greater or equal',
      '<=': 'Less or equal',
      '=': 'Equal to',
      '!=': 'Not equal to',
      'crossed above': 'Crossed above',
      'crossed below': 'Crossed below'
    };
    
    return operators[this.condition.operator] || this.condition.operator;
  }
  
  formatValue(): string {
    if (this.condition.valueType === 'field') {
      let value = '';
      if (this.condition.multiplier && this.condition.multiplier !== 1) {
        value += `${this.condition.multiplier} × `;
      }
      if (this.condition.valueDaysAgo && this.condition.valueDaysAgo > 0) {
        value += `${this.condition.valueDaysAgo} ${this.condition.valueTimeUnit || 'day'}${this.condition.valueDaysAgo > 1 ? 's' : ''} ago `;
      }
      
      const field = this.fieldOptions.find(f => f.value === this.condition.valueField);
      value += field?.label || this.condition.valueField || 'Field';
      
      return value;
    }
    
    return this.condition.value || '0';
  }
  
  hasIndicatorParams(): boolean {
    return this.condition.indicatorType === 'parameterized' && 
           !!this.condition.indicatorParams && 
           this.condition.indicatorParams.length > 0;
  }
  
  hasValueIndicatorParams(): boolean {
    return this.condition.valueIndicatorType === 'parameterized' && 
           !!this.condition.valueIndicatorParams && 
           this.condition.valueIndicatorParams.length > 0;
  }
  
  editTimeframe(event: MouseEvent) {
    event.stopPropagation();
    const rect = (event.target as HTMLElement).getBoundingClientRect();
    
    this.popupService.open({
      type: 'timeframe',
      value: {
        value: this.condition.daysAgo || 0,
        unit: this.condition.timeUnit || 'day'
      },
      position: { x: rect.left, y: rect.bottom + 5 },
      callback: (value) => {
        this.condition.daysAgo = value.value;
        this.condition.timeUnit = value.unit;
        this.conditionChange.emit(this.condition);
      }
    });
  }
  
  editField(event: MouseEvent) {
    event.stopPropagation();
    const rect = (event.target as HTMLElement).getBoundingClientRect();
    
    this.popupService.open({
      type: 'field',
      options: this.fieldOptions,
      value: this.condition.field,
      position: { x: rect.left, y: rect.bottom + 5 },
      callback: (value) => {
        this.condition.field = value;
        this.updateIndicatorInfo();
        this.conditionChange.emit(this.condition);
      }
    });
  }
  
  editOperator(event: MouseEvent) {
    event.stopPropagation();
    const rect = (event.target as HTMLElement).getBoundingClientRect();
    
    this.popupService.open({
      type: 'operator',
      value: this.condition.operator,
      position: { x: rect.left, y: rect.bottom + 5 },
      callback: (value) => {
        this.condition.operator = value;
        this.conditionChange.emit(this.condition);
      }
    });
  }
  
  editValue(event: MouseEvent) {
    event.stopPropagation();
    const rect = (event.target as HTMLElement).getBoundingClientRect();
    
    this.popupService.open({
      type: 'value',
      value: this.condition.valueType === 'field' 
        ? { type: 'field', field: this.condition.valueField }
        : this.condition.value,
      position: { x: rect.left, y: rect.bottom + 5 },
      callback: (value) => {
        if (typeof value === 'object' && value.type === 'field') {
          this.condition.valueType = 'field';
          this.condition.valueField = value.field;
          this.updateValueIndicatorInfo();
        } else {
          this.condition.valueType = 'number';
          this.condition.value = value;
        }
        this.conditionChange.emit(this.condition);
      }
    });
  }
  
  editIndicatorParams(event: MouseEvent) {
    event.stopPropagation();
    const rect = (event.target as HTMLElement).getBoundingClientRect();
    
    this.popupService.open({
      type: 'indicator-params',
      value: {
        name: this.condition.indicatorName,
        params: this.condition.indicatorParams
      },
      position: { x: rect.left, y: rect.bottom + 5 },
      callback: (params) => {
        this.condition.indicatorParams = params;
        this.conditionChange.emit(this.condition);
      }
    });
  }
  
  editValueIndicatorParams(event: MouseEvent) {
    event.stopPropagation();
    const rect = (event.target as HTMLElement).getBoundingClientRect();
    
    this.popupService.open({
      type: 'indicator-params',
      value: {
        name: this.condition.valueIndicatorName,
        params: this.condition.valueIndicatorParams
      },
      position: { x: rect.left, y: rect.bottom + 5 },
      callback: (params) => {
        this.condition.valueIndicatorParams = params;
        this.conditionChange.emit(this.condition);
      }
    });
  }
  
  editLogicalOperator(event: MouseEvent) {
    event.stopPropagation();
    this.condition.logicalOperator = this.condition.logicalOperator === 'and' ? 'or' : 'and';
    this.conditionChange.emit(this.condition);
  }
  
  updateIndicatorInfo() {
    const parameterizedIndicators = ['rsi', 'sma', 'ema', 'bb', 'supertrend', 'macd', 'stochastic', 'williamsr'];
    
    if (parameterizedIndicators.includes(this.condition.field)) {
      this.condition.indicatorType = 'parameterized';
      this.condition.indicatorName = this.condition.field;
      
      // Set default params if not already set
      if (!this.condition.indicatorParams) {
        const defaults: { [key: string]: string[] } = {
          'rsi': ['14'],
          'sma': ['20'],
          'ema': ['20'],
          'bb': ['20', '2'],
          'supertrend': ['10', '3'],
          'macd': ['12', '26', '9'],
          'stochastic': ['14', '3', '3'],
          'williamsr': ['14']
        };
        this.condition.indicatorParams = defaults[this.condition.field] || [];
      }
    } else {
      this.condition.indicatorType = 'simple';
      this.condition.indicatorName = undefined;
      this.condition.indicatorParams = undefined;
    }
  }
  
  updateValueIndicatorInfo() {
    const parameterizedIndicators = ['rsi', 'sma', 'ema', 'bb', 'supertrend', 'macd', 'stochastic', 'williamsr'];
    
    if (this.condition.valueField && parameterizedIndicators.includes(this.condition.valueField)) {
      this.condition.valueIndicatorType = 'parameterized';
      this.condition.valueIndicatorName = this.condition.valueField;
      
      // Set default params if not already set
      if (!this.condition.valueIndicatorParams) {
        const defaults: { [key: string]: string[] } = {
          'rsi': ['14'],
          'sma': ['20'],
          'ema': ['20'],
          'bb': ['20', '2'],
          'supertrend': ['10', '3'],
          'macd': ['12', '26', '9'],
          'stochastic': ['14', '3', '3'],
          'williamsr': ['14']
        };
        this.condition.valueIndicatorParams = defaults[this.condition.valueField] || [];
      }
    } else {
      this.condition.valueIndicatorType = 'simple';
      this.condition.valueIndicatorName = undefined;
      this.condition.valueIndicatorParams = undefined;
    }
  }
  
  copyCondition() {
    // Emit copy event
    console.log('Copy condition:', this.condition);
  }
  
  removeCondition() {
    this.remove.emit();
  }
}