import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpClientModule } from '@angular/common/http';

interface Condition {
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
}

interface QueryResult {
  success: boolean;
  totalMatches: number;
  matches: Array<{
    date: string;
    timestamp: string;
    stock: string;
    close: string;
    day: string;
  }>;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App {
  title = 'Stock Screener';
  
  // Available fields for conditions
  fields = [
    { value: 'daily rsi', label: 'Daily RSI' },
    { value: 'weekly rsi', label: 'Weekly RSI' },
    { value: 'daily sma', label: 'Daily SMA' },
    { value: 'weekly sma', label: 'Weekly SMA' },
    { value: 'daily ema', label: 'Daily EMA' },
    { value: 'weekly ema', label: 'Weekly EMA' },
    { value: 'close', label: 'Close' },
    { value: 'open', label: 'Open' },
    { value: 'high', label: 'High' },
    { value: 'low', label: 'Low' },
    { value: 'volume', label: 'Volume' },
    { value: 'daily upper bollinger band', label: 'Daily Upper Bollinger Band' },
    { value: 'daily lower bollinger band', label: 'Daily Lower Bollinger Band' },
    { value: 'weekly upper bollinger band', label: 'Weekly Upper Bollinger Band' },
    { value: 'weekly lower bollinger band', label: 'Weekly Lower Bollinger Band' },
    { value: 'daily supertrend', label: 'Daily Supertrend' },
    { value: 'weekly supertrend', label: 'Weekly Supertrend' },
    { value: 'daily percent change', label: 'Daily % Change' },
    { value: 'weekly percent change', label: 'Weekly % Change' },
    { value: 'current close', label: 'Current Close' },
    { value: 'yesterday\'s close', label: 'Yesterday\'s Close' },
    { value: 'weekly volume', label: 'Weekly Volume' }
  ];

  operators = [
    { value: '>', label: 'Greater than' },
    { value: '<', label: 'Less than' },
    { value: '>=', label: 'Greater than or equal' },
    { value: '<=', label: 'Less than or equal' },
    { value: '=', label: 'Equal to' },
    { value: '!=', label: 'Not equal to' }
  ];

  conditions: Condition[] = [
    { id: 1, field: 'daily rsi', operator: '>', value: '60', logicalOperator: 'and', daysAgo: 0, timeUnit: 'day', leftMultiplier: 1, valueType: 'number' }
  ];
  
  queryString = '';
  loading = false;
  results: QueryResult | null = null;
  groupedResults: Map<string, any[]> = new Map();
  error: string | null = null;
  
  private apiUrl = 'http://localhost:3000';
  private nextId = 2;

  constructor(private http: HttpClient) {}

  addCondition() {
    this.conditions.push({
      id: this.nextId++,
      field: 'daily rsi',
      operator: '>',
      value: '',
      logicalOperator: 'and',
      daysAgo: 0,
      timeUnit: 'day',
      leftMultiplier: 1,
      valueType: 'number',
      valueField: 'daily rsi',
      valueDaysAgo: 0,
      valueTimeUnit: 'day',
      multiplier: 1
    });
  }

  removeCondition(id: number) {
    this.conditions = this.conditions.filter(c => c.id !== id);
  }

  buildQuery(): string {
    return this.conditions.map((condition, index) => {
      // Build left side
      let field = condition.field;
      if (condition.daysAgo !== null && condition.daysAgo !== undefined && condition.daysAgo > 0) {
        let unit = condition.timeUnit;
        const plural = condition.daysAgo === 1 ? unit : unit + 's';
        field = `${condition.daysAgo} ${plural} ago ${condition.field}`;
      }
      if (condition.leftMultiplier && condition.leftMultiplier !== 1) {
        field = `${field} * ${condition.leftMultiplier}`;
      }
      
      // Build right side
      let value = condition.value;
      if (condition.valueType === 'field' && condition.valueField) {
        value = condition.valueField;
        if (condition.valueDaysAgo && condition.valueDaysAgo > 0) {
          let unit = condition.valueTimeUnit;
          const plural = condition.valueDaysAgo === 1 ? unit : unit + 's';
          value = `${condition.valueDaysAgo} ${plural} ago ${value}`;
        }
        if (condition.multiplier && condition.multiplier !== 1) {
          value = `${value} * ${condition.multiplier}`;
        }
      }
      
      const conditionStr = `${field} ${condition.operator} ${value}`;
      if (index === 0) {
        return conditionStr;
      }
      return `${condition.logicalOperator} ${conditionStr}`;
    }).join(' ');
  }

  generateQuery() {
    this.queryString = this.buildQuery();
  }

  runScan() {
    if (this.conditions.length === 0 || !this.conditions.every(c => c.value)) {
      this.error = 'Please fill all condition values';
      return;
    }

    this.loading = true;
    this.error = null;
    this.results = null;
    this.groupedResults.clear();

    const query = this.buildQuery();
    this.queryString = query;

    this.http.post<QueryResult>(`${this.apiUrl}/query`, { query })
      .subscribe({
        next: (response) => {
          this.loading = false;
          this.results = response;
          this.groupByDate(response.matches);
        },
        error: (error) => {
          this.loading = false;
          this.error = error.error?.error || 'An error occurred while fetching results';
          console.error('Error:', error);
        }
      });
  }

  groupByDate(matches: any[]) {
    this.groupedResults.clear();
    
    matches.forEach(match => {
      const date = new Date(match.timestamp).toLocaleDateString();
      if (!this.groupedResults.has(date)) {
        this.groupedResults.set(date, []);
      }
      this.groupedResults.get(date)?.push(match);
    });
  }

  getGroupedDates(): string[] {
    return Array.from(this.groupedResults.keys()).sort((a, b) => 
      new Date(b).getTime() - new Date(a).getTime()
    );
  }

  clearResults() {
    this.results = null;
    this.groupedResults.clear();
    this.queryString = '';
    this.error = null;
  }

  copyScan() {
    navigator.clipboard.writeText(this.queryString);
    alert('Query copied to clipboard!');
  }

  loadPreset(preset: string) {
    this.conditions = [];
    this.nextId = 1;
    
    switch(preset) {
      case 'volume-surge':
        this.conditions.push({
          id: this.nextId++,
          field: 'volume',
          operator: '>',
          value: '',
          logicalOperator: 'and',
          daysAgo: 1,
          timeUnit: 'day',
          leftMultiplier: 1,
          valueType: 'field',
          valueField: 'volume',
          valueDaysAgo: 1,
          valueTimeUnit: 'week',
          multiplier: 1.2
        });
        break;
      case 'price-breakout':
        this.conditions.push({
          id: this.nextId++,
          field: 'close',
          operator: '>',
          value: '',
          logicalOperator: 'and',
          daysAgo: 0,
          timeUnit: 'day',
          leftMultiplier: 1,
          valueType: 'field',
          valueField: 'sma',
          valueDaysAgo: 0,
          valueTimeUnit: 'day',
          multiplier: 1.05
        });
        break;
      case 'trend-reversal':
        this.conditions.push({
          id: this.nextId++,
          field: 'super trend',
          operator: '>',
          value: '',
          logicalOperator: 'and',
          daysAgo: 1,
          timeUnit: 'day',
          leftMultiplier: 1,
          valueType: 'field',
          valueField: 'weekly super trend',
          valueDaysAgo: 0,
          valueTimeUnit: 'day',
          multiplier: 1
        });
        break;
    }
    
    this.generateQuery();
  }
}
