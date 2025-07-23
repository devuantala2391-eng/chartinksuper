import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpClientModule } from '@angular/common/http';
import { ConditionCompactComponent } from './condition-compact.component';
import { PopupService } from './popup.service';

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
  indicatorType?: 'simple' | 'parameterized';
  indicatorName?: string;
  indicatorParams?: string[];
  valueIndicatorType?: 'simple' | 'parameterized';
  valueIndicatorName?: string;
  valueIndicatorParams?: string[];
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
  processedStocks?: number;
}

@Component({
  selector: 'app-compact',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule, ConditionCompactComponent],
  templateUrl: './app-compact.html',
  styleUrl: './app-compact.scss',
  providers: [PopupService]
})
export class AppCompact implements OnInit {
  title = 'Stock Screener';
  naturalLanguageQuery = '';
  
  conditions: Condition[] = [];
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
  
  loading = false;
  error: string | null = null;
  results: QueryResult | null = null;
  queryString = '';
  groupedResults = new Map<string, any[]>();
  
  private nextId = 1;
  private apiUrl = 'http://localhost:8001';
  
  constructor(private http: HttpClient) {}
  
  ngOnInit() {
    this.addCondition();
  }
  
  addCondition() {
    const newCondition: Condition = {
      id: this.nextId++,
      field: 'close',
      operator: '>',
      value: '1000',
      logicalOperator: 'and',
      daysAgo: 0,
      timeUnit: 'day',
      leftMultiplier: 1,
      valueType: 'number',
      multiplier: 1
    };
    
    this.conditions.push(newCondition);
  }
  
  removeCondition(id: number) {
    this.conditions = this.conditions.filter(c => c.id !== id);
    if (this.conditions.length === 0) {
      this.addCondition();
    }
  }
  
  updateCondition(condition: Condition) {
    const index = this.conditions.findIndex(c => c.id === condition.id);
    if (index !== -1) {
      this.conditions[index] = condition;
    }
  }
  
  buildQuery(): string {
    let query = '';
    
    this.conditions.forEach((condition, index) => {
      if (index > 0) {
        query += ` ${condition.logicalOperator} `;
      }
      
      // Build left side
      let leftSide = this.buildFieldString(condition.field, condition.indicatorType, 
                                          condition.indicatorName, condition.indicatorParams);
      
      if (condition.daysAgo && condition.daysAgo > 0) {
        const unit = condition.timeUnit === 'day' ? 'day' : 
                     condition.timeUnit === 'week' ? 'week' : 'month';
        leftSide = `${condition.daysAgo} ${unit}${condition.daysAgo > 1 ? 's' : ''} ago ${leftSide}`;
      }
      
      if (condition.leftMultiplier && condition.leftMultiplier !== 1) {
        leftSide = `( ${leftSide} * ${condition.leftMultiplier} )`;
      }
      
      // Build right side
      let rightSide = '';
      if (condition.valueType === 'field') {
        rightSide = this.buildFieldString(condition.valueField || '', condition.valueIndicatorType,
                                        condition.valueIndicatorName, condition.valueIndicatorParams);
        
        if (condition.valueDaysAgo && condition.valueDaysAgo > 0) {
          const unit = condition.valueTimeUnit === 'day' ? 'day' : 
                       condition.valueTimeUnit === 'week' ? 'week' : 'month';
          rightSide = `${condition.valueDaysAgo} ${unit}${condition.valueDaysAgo > 1 ? 's' : ''} ago ${rightSide}`;
        }
        
        if (condition.multiplier && condition.multiplier !== 1) {
          rightSide = `( ${rightSide} * ${condition.multiplier} )`;
        }
      } else {
        rightSide = condition.value;
      }
      
      query += `${leftSide} ${condition.operator} ${rightSide}`;
    });
    
    this.queryString = query;
    return query;
  }
  
  private buildFieldString(field: string, indicatorType?: string, indicatorName?: string, indicatorParams?: string[]): string {
    if (indicatorType === 'parameterized' && indicatorName && indicatorParams && indicatorParams.length > 0) {
      return `${indicatorName}(${indicatorParams.join(', ')})`;
    }
    return field;
  }
  
  async runScan() {
    if (this.conditions.length === 0) return;
    
    this.loading = true;
    this.error = null;
    const query = this.buildQuery();
    
    try {
      const response = await this.http.post<QueryResult>(`${this.apiUrl}/query`, { query }).toPromise();
      
      if (response) {
        this.results = response;
        this.groupResults();
      }
    } catch (err: any) {
      this.error = err.error?.error || 'An error occurred while running the scan';
      //console.error('Scan error:', err);
    } finally {
      this.loading = false;
    }
  }
  
  groupResults() {
    if (!this.results || !this.results.matches) return;
    
    this.groupedResults.clear();
    
    this.results.matches.forEach(match => {
      const dateStr = new Date(parseInt(match.timestamp)).toDateString();
      
      if (!this.groupedResults.has(dateStr)) {
        this.groupedResults.set(dateStr, []);
      }
      
      this.groupedResults.get(dateStr)?.push(match);
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
  
  loadPreset(preset: string) {
    this.conditions = [];
    this.nextId = 1;
    
    switch(preset) {
      case 'volume-surge':
        this.conditions.push({
          id: this.nextId++,
          field: 'volume',
          operator: '>',
          value: '1.2',
          valueType: 'field',
          valueField: 'volume',
          valueDaysAgo: 7,
          valueTimeUnit: 'day',
          multiplier: 1.2,
          logicalOperator: 'and',
          daysAgo: 1,
          timeUnit: 'day'
        });
        break;
        
      case 'price-breakout':
        this.conditions.push({
          id: this.nextId++,
          field: 'close',
          operator: '>',
          value: '1.05',
          valueType: 'field',
          valueField: 'sma',
          multiplier: 1.05,
          logicalOperator: 'and',
          indicatorType: 'simple',
          valueIndicatorType: 'parameterized',
          valueIndicatorName: 'sma',
          valueIndicatorParams: ['20'],
          timeUnit: 'day',
          daysAgo: 0,
          leftMultiplier: 1
        });
        break;
        
      case 'rsi-oversold':
        this.conditions.push({
          id: this.nextId++,
          field: 'rsi',
          operator: '<',
          value: '30',
          logicalOperator: 'and',
          indicatorType: 'parameterized',
          indicatorName: 'rsi',
          indicatorParams: ['14'],
          timeUnit: 'day',
          valueType: 'number',
          daysAgo: 0,
          leftMultiplier: 1
        });
        break;
    }
  }
  
  // UI Helper Methods
  parseNaturalLanguage() {
    if (this.naturalLanguageQuery.toLowerCase().includes('volume surge')) {
      this.loadPreset('volume-surge');
    } else if (this.naturalLanguageQuery.toLowerCase().includes('price breakout')) {
      this.loadPreset('price-breakout');
    } else if (this.naturalLanguageQuery.toLowerCase().includes('rsi oversold')) {
      this.loadPreset('rsi-oversold');
    }
  }
  
  saveQuery() {
    const query = {
      name: prompt('Enter a name for this query:') || 'Untitled Query',
      conditions: this.conditions,
      created: new Date().toISOString()
    };
    
    const savedQueries = JSON.parse(localStorage.getItem('savedQueries') || '[]');
    savedQueries.push(query);
    localStorage.setItem('savedQueries', JSON.stringify(savedQueries));
    
    alert('Query saved successfully!');
  }
  
  exportQuery() {
    const queryData = {
      conditions: this.conditions,
      query: this.queryString,
      exported: new Date().toISOString()
    };
    
    const blob = new Blob([JSON.stringify(queryData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `stock-query-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  
  clearAll() {
    if (confirm('Are you sure you want to clear all conditions?')) {
      this.conditions = [];
      this.clearResults();
      this.addCondition();
    }
  }
  
  copyQuery() {
    navigator.clipboard.writeText(this.queryString);
    
    const btn = document.querySelector('.copy-btn') as HTMLElement;
    if (btn) {
      const originalText = btn.textContent;
      btn.textContent = '✓ Copied!';
      setTimeout(() => {
        btn.textContent = originalText;
      }, 2000);
    }
  }
  
  formatDate(dateStr: string): string {
    const date = new Date(parseInt(dateStr));
    return date.toLocaleDateString('en-IN', { 
      weekday: 'long', 
      year: 'numeric', 
      month: 'long', 
      day: 'numeric' 
    });
  }
  
  formatNumber(value: string): string {
    return parseFloat(value).toLocaleString('en-IN', { maximumFractionDigits: 2 });
  }
  
  getChange(match: any): number {
    // This would ideally calculate the actual change percentage
    // For now, returning a mock value
    return Math.random() * 10 - 5;
  }
  
  formatChange(match: any): string {
    const change = this.getChange(match);
    return (change > 0 ? '+' : '') + change.toFixed(2);
  }
}