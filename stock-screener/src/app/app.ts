import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpClientModule } from '@angular/common/http';
import { ProgressBarComponent } from './progress-bar.component';

interface Condition {
  id: number;
  field: string;
  operator: string;
  value: string;
  logicalOperator: 'and' | 'or';
  // Simplified time period handling
  timePeriod: 'today' | '1-day' | '2-days' | '3-days' | '4-days' | '5-days' | 'n-days';
  customDaysAgo?: number;
  timeUnit: 'day' | 'week' | 'month';
  valueType: 'number' | 'field';
  valueField?: string;
  valueTimePeriod?: 'today' | '1-day' | '2-days' | '3-days' | '4-days' | '5-days' | 'n-days';
  valueCustomDaysAgo?: number;
  valueTimeUnit?: 'day' | 'week' | 'month';
  // Arithmetic operators for right side
  arithmeticOperator?: '+' | '-' | '*' | '/';
  arithmeticValue?: string;
  // New fields for indicator parameters
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
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule, ProgressBarComponent],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App implements OnInit {
  title = 'Stock Screener';
  naturalLanguageQuery = '';
  
  // Available fields for conditions
  fields = [
    // Price fields
    { value: 'close', label: 'Close' },
    { value: 'open', label: 'Open' },
    { value: 'high', label: 'High' },
    { value: 'low', label: 'Low' },
    { value: 'volume', label: 'Volume' },
    // Working parameterized indicators
    { value: 'rsi', label: 'RSI' },
    { value: 'sma', label: 'SMA' },
    { value: 'ema', label: 'EMA' },
    { value: 'bb', label: 'Bollinger Bands' },
    { value: 'supertrend', label: 'SuperTrend' }
  ];
  
  // Parameterized indicators
  parameterizedIndicators = [
    'rsi', 'sma', 'ema', 'bb', 'supertrend'
  ];
  
  // Default parameters for indicators
  indicatorDefaults: { [key: string]: string[] } = {
    'rsi': ['14'],
    'sma': ['20'],
    'ema': ['20'],
    'bb': ['20', '2'],
    'supertrend': ['10', '3']
  };

  operators = [
    { value: '>', label: 'Greater than' },
    { value: '<', label: 'Less than' },
    { value: '>=', label: 'Greater than or equal' },
    { value: '<=', label: 'Less than or equal' },
    { value: '=', label: 'Equal to' },
    { value: '!=', label: 'Not equal to' }
  ];

  // Time period options
  timePeriodOptions = [
    { value: 'today', label: "Today's" },
    { value: '1-day', label: '1 day ago' },
    { value: '2-days', label: '2 days ago' },
    { value: '3-days', label: '3 days ago' },
    { value: '4-days', label: '4 days ago' },
    { value: '5-days', label: '5 days ago' },
    { value: 'n-days', label: 'n days ago' }
  ];

  // Arithmetic operators
  arithmeticOperators = [
    { value: '+', label: '+' },
    { value: '-', label: '-' },
    { value: '*', label: '×' },
    { value: '/', label: '÷' }
  ];

  conditions: Condition[] = [
    { 
      id: 1, 
      field: 'rsi', 
      operator: '>', 
      value: '60', 
      logicalOperator: 'and', 
      timePeriod: 'today', 
      timeUnit: 'day', 
      valueType: 'number',
      indicatorType: 'parameterized',
      indicatorName: 'rsi',
      indicatorParams: ['14']
    }
  ];
  
  queryString = '';
  loading = false;
  results: QueryResult | null = null;
  groupedResults: Map<string, any[]> = new Map();
  error: string | null = null;
  
  // Progress tracking
  showProgress = false;
  progressPhase = 'initializing';
  progressMessage = 'Starting...';
  progressProcessed = 0;
  progressTotal = 100;
  progressMatches?: number;
  private progressInterval?: any;
  
  private apiUrl = 'http://localhost:3000';
  private nextId = 2;

  constructor(private http: HttpClient) {}

  ngOnInit() {
    this.conditions.forEach(condition => {
      this.onFieldChange(condition);
      if (condition.valueField) {
        this.onValueFieldChange(condition);
      }
    });
  }

  addCondition() {
    this.conditions.push({
      id: this.nextId++,
      field: 'rsi',
      operator: '>',
      value: '',
      logicalOperator: 'and',
      timePeriod: 'today',
      timeUnit: 'day',
      valueType: 'number',
      valueField: 'rsi',
      valueTimePeriod: 'today',
      valueTimeUnit: 'day',
      indicatorType: 'parameterized',
      indicatorName: 'rsi',
      indicatorParams: ['14'],
      valueIndicatorType: 'parameterized',
      valueIndicatorName: 'rsi',
      valueIndicatorParams: ['14']
    });
  }

  removeCondition(id: number) {
    this.conditions = this.conditions.filter(c => c.id !== id);
  }

  private buildFieldString(field: string, indicatorType?: string, indicatorName?: string, indicatorParams?: string[]): string {
    if (indicatorType === 'parameterized' && indicatorName && indicatorParams && indicatorParams.length > 0) {
      return `${indicatorName}(${indicatorParams.join(', ')})`;
    }
    return field;
  }

  // Helper method to convert time period to days ago
  private getTimePeriodDays(timePeriod: string, customDaysAgo?: number): number {
    switch (timePeriod) {
      case 'today': return 0;
      case '1-day': return 1;
      case '2-days': return 2;
      case '3-days': return 3;
      case '4-days': return 4;
      case '5-days': return 5;
      case 'n-days': return customDaysAgo || 0;
      default: return 0;
    }
  }

  buildQuery(): string {
    return this.conditions.map((condition, index) => {
      // Build left side
      let field = this.buildFieldString(condition.field, condition.indicatorType, condition.indicatorName, condition.indicatorParams);
      
      const daysAgo = this.getTimePeriodDays(condition.timePeriod, condition.customDaysAgo);
      if (daysAgo > 0) {
        let unit = condition.timeUnit;
        const plural = daysAgo === 1 ? unit : unit + 's';
        field = `${daysAgo} ${plural} ago ${field}`;
      }
      
      // Build right side
      let value = condition.value;
      if (condition.valueType === 'field' && condition.valueField) {
        value = this.buildFieldString(condition.valueField, condition.valueIndicatorType, condition.valueIndicatorName, condition.valueIndicatorParams);
        
        const valueDaysAgo = this.getTimePeriodDays(condition.valueTimePeriod || 'today', condition.valueCustomDaysAgo);
        if (valueDaysAgo > 0) {
          let unit = condition.valueTimeUnit;
          const plural = valueDaysAgo === 1 ? unit : unit + 's';
          value = `${valueDaysAgo} ${plural} ago ${value}`;
        }
        
        // Add arithmetic operation if specified
        if (condition.arithmeticOperator && condition.arithmeticValue) {
          value = `${value} ${condition.arithmeticOperator} ${condition.arithmeticValue}`;
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
    this.showProgress = true;
    this.progressPhase = 'initializing';
    this.progressMessage = 'Starting scan...';
    this.progressProcessed = 0;
    this.progressTotal = 100;
    this.progressMatches = undefined;

    const query = this.buildQuery();
    this.queryString = query;
    
    // Start polling for progress updates
    this.startProgressPolling();

    // Send query
    this.http.post<QueryResult>(`${this.apiUrl}/query`, { query })
      .subscribe({
        next: (response) => {
          this.loading = false;
          this.results = response;
          this.groupByDate(response.matches);
          
          // Show completion in progress bar
          this.progressPhase = 'completed';
          this.progressMessage = `Found ${response.totalMatches} matches!`;
          this.progressProcessed = this.progressTotal;
          
          // Hide progress after delay
          setTimeout(() => {
            this.showProgress = false;
            this.stopProgressPolling();
          }, 2000);
        },
        error: (error) => {
          this.loading = false;
          this.showProgress = false;
          this.error = error.error?.error || 'An error occurred while fetching results';
          console.error('Error:', error);
          this.stopProgressPolling();
        }
      });
  }
  
  private startProgressPolling() {
    // Clear any existing interval
    this.stopProgressPolling();
    
    // Make an immediate call to test the endpoint
    this.http.get<any>(`${this.apiUrl}/query/progress`)
      .subscribe({
        next: (progress) => {
          console.log('Initial progress check:', progress);
        },
        error: (error) => {
          console.error('Initial progress check failed:', error);
        }
      });
    
    // Poll every 2 seconds for progress updates
    this.progressInterval = setInterval(() => {
      this.http.get<any>(`${this.apiUrl}/query/progress`)
        .subscribe({
          next: (progress) => {
            console.log('Progress update received:', progress);
            if (progress.isRunning) {
              this.progressPhase = progress.phase;
              this.progressMessage = progress.message || '';
              this.progressProcessed = progress.processed || 0;
              this.progressTotal = progress.total || 2446;
              if (progress.matches !== undefined) {
                this.progressMatches = progress.matches;
              }
            }
          },
          error: (error) => {
            console.error('Progress polling error:', error);
            console.error('Error details:', error.error);
          }
        });
    }, 2000); // Poll every 2 seconds
  }
  
  private stopProgressPolling() {
    if (this.progressInterval) {
      clearInterval(this.progressInterval);
      this.progressInterval = undefined;
    }
  }
  
  // Manual test function for debugging
  testProgressEndpoint() {
    console.log('Testing progress endpoint...');
    this.http.get<any>(`${this.apiUrl}/query/progress`)
      .subscribe({
        next: (progress) => {
          console.log('Progress endpoint working:', progress);
        },
        error: (error) => {
          console.error('Progress endpoint failed:', error);
          console.error('Status:', error.status);
          console.error('URL:', error.url);
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
          timePeriod: '1-day',
          timeUnit: 'day',
          valueType: 'field',
          valueField: 'volume',
          valueTimePeriod: '1-day',
          valueTimeUnit: 'week',
          arithmeticOperator: '*',
          arithmeticValue: '1.2'
        });
        break;
      case 'price-breakout':
        this.conditions.push({
          id: this.nextId++,
          field: 'close',
          operator: '>',
          value: '',
          logicalOperator: 'and',
          timePeriod: 'today',
          timeUnit: 'day',
          valueType: 'field',
          valueField: 'sma',
          valueTimePeriod: 'today',
          valueTimeUnit: 'day',
          arithmeticOperator: '*',
          arithmeticValue: '1.05'
        });
        break;
      case 'trend-reversal':
        this.conditions.push({
          id: this.nextId++,
          field: 'supertrend',
          operator: '>',
          value: '',
          logicalOperator: 'and',
          timePeriod: '1-day',
          timeUnit: 'day',
          valueType: 'field',
          valueField: 'supertrend',
          valueTimePeriod: 'today',
          valueTimeUnit: 'day',
          indicatorType: 'parameterized',
          indicatorName: 'supertrend',
          indicatorParams: ['10', '3'],
          valueIndicatorType: 'parameterized',
          valueIndicatorName: 'supertrend',
          valueIndicatorParams: ['10', '3']
        });
        break;
      case 'rsi-oversold':
        this.conditions.push({
          id: this.nextId++,
          field: 'rsi',
          operator: '<',
          value: '30',
          logicalOperator: 'and',
          timePeriod: 'today',
          timeUnit: 'day',
          valueType: 'number',
          indicatorType: 'parameterized',
          indicatorName: 'rsi',
          indicatorParams: ['14']
        });
        break;
    }
    
    this.generateQuery();
  }
  
  onFieldChange(condition: Condition) {
    // Update indicator type based on field selection
    if (this.parameterizedIndicators.includes(condition.field)) {
      condition.indicatorType = 'parameterized';
      condition.indicatorName = condition.field;
      condition.indicatorParams = [...(this.indicatorDefaults[condition.field] || ['14'])];
    } else {
      condition.indicatorType = 'simple';
      condition.indicatorName = undefined;
      condition.indicatorParams = undefined;
    }
  }
  
  onValueFieldChange(condition: Condition) {
    // Update value indicator type based on field selection
    if (condition.valueField && this.parameterizedIndicators.includes(condition.valueField)) {
      condition.valueIndicatorType = 'parameterized';
      condition.valueIndicatorName = condition.valueField;
      condition.valueIndicatorParams = [...(this.indicatorDefaults[condition.valueField] || ['14'])];
    } else {
      condition.valueIndicatorType = 'simple';
      condition.valueIndicatorName = undefined;
      condition.valueIndicatorParams = undefined;
    }
  }
  
  
  getIndicatorParamLabels(indicatorName: string): string[] {
    const labels: { [key: string]: string[] } = {
      'rsi': ['Period'],
      'sma': ['Period'],
      'ema': ['Period'],
      'bb': ['Period', 'Std Dev'],
      'supertrend': ['Period', 'Multiplier']
    };
    return labels[indicatorName] || ['Period'];
  }
  
  // New methods for compact view
  updateCondition(condition: Condition) {
    const index = this.conditions.findIndex(c => c.id === condition.id);
    if (index !== -1) {
      this.conditions[index] = condition;
    }
  }
  
  parseNaturalLanguage() {
    // Simple natural language parsing (can be enhanced with NLP)
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
    }
  }
  
  copyQuery() {
    navigator.clipboard.writeText(this.queryString);
    
    // Show a temporary success message
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
