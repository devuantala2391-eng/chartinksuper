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
  daysAgo?: number;
  timeUnit: 'day' | 'week' | 'month';
  leftMultiplier?: number;
  valueType: 'number' | 'field';
  valueField?: string;
  valueDaysAgo?: number;
  valueTimeUnit?: 'day' | 'week' | 'month';
  multiplier?: number;
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
    { value: 'current close', label: 'Current Close' },
    { value: 'yesterday\'s close', label: 'Yesterday\'s Close' },
    { value: 'weekly volume', label: 'Weekly Volume' },
    // Parameterized indicators
    { value: 'rsi', label: 'RSI (with params)' },
    { value: 'sma', label: 'SMA (with params)' },
    { value: 'ema', label: 'EMA (with params)' },
    { value: 'bb', label: 'Bollinger Bands (with params)' },
    { value: 'supertrend', label: 'SuperTrend (with params)' },
    { value: 'macd', label: 'MACD (with params)' },
    { value: 'stochastic', label: 'Stochastic (with params)' },
    { value: 'williamsr', label: 'Williams %R (with params)' },
    // Legacy fields for backward compatibility
    { value: 'daily rsi', label: 'Daily RSI (legacy)' },
    { value: 'weekly rsi', label: 'Weekly RSI (legacy)' },
    { value: 'daily sma', label: 'Daily SMA (legacy)' },
    { value: 'weekly sma', label: 'Weekly SMA (legacy)' },
    { value: 'daily ema', label: 'Daily EMA (legacy)' },
    { value: 'weekly ema', label: 'Weekly EMA (legacy)' },
    { value: 'daily upper bollinger band', label: 'Daily Upper Bollinger Band (legacy)' },
    { value: 'daily lower bollinger band', label: 'Daily Lower Bollinger Band (legacy)' },
    { value: 'weekly upper bollinger band', label: 'Weekly Upper Bollinger Band (legacy)' },
    { value: 'weekly lower bollinger band', label: 'Weekly Lower Bollinger Band (legacy)' },
    { value: 'daily supertrend', label: 'Daily Supertrend (legacy)' },
    { value: 'weekly supertrend', label: 'Weekly Supertrend (legacy)' },
    { value: 'daily percent change', label: 'Daily % Change (legacy)' },
    { value: 'weekly percent change', label: 'Weekly % Change (legacy)' }
  ];
  
  // Parameterized indicators
  parameterizedIndicators = [
    'rsi', 'sma', 'ema', 'bb', 'supertrend', 'macd', 'stochastic', 'williamsr'
  ];
  
  // Default parameters for indicators
  indicatorDefaults: { [key: string]: string[] } = {
    'rsi': ['14'],
    'sma': ['20'],
    'ema': ['20'],
    'bb': ['20', '2'],
    'supertrend': ['10', '3'],
    'macd': ['12', '26', '9'],
    'stochastic': ['14', '3'],
    'williamsr': ['14']
  };

  operators = [
    { value: '>', label: 'Greater than' },
    { value: '<', label: 'Less than' },
    { value: '>=', label: 'Greater than or equal' },
    { value: '<=', label: 'Less than or equal' },
    { value: '=', label: 'Equal to' },
    { value: '!=', label: 'Not equal to' }
  ];

  conditions: Condition[] = [
    { 
      id: 1, 
      field: 'rsi', 
      operator: '>', 
      value: '60', 
      logicalOperator: 'and', 
      daysAgo: 0, 
      timeUnit: 'day', 
      leftMultiplier: 1, 
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
      daysAgo: 0,
      timeUnit: 'day',
      leftMultiplier: 1,
      valueType: 'number',
      valueField: 'rsi',
      valueDaysAgo: 0,
      valueTimeUnit: 'day',
      multiplier: 1,
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

  buildQuery(): string {
    return this.conditions.map((condition, index) => {
      // Build left side
      let field = this.buildFieldString(condition.field, condition.indicatorType, condition.indicatorName, condition.indicatorParams);
      
      if (condition.daysAgo !== null && condition.daysAgo !== undefined && condition.daysAgo > 0) {
        let unit = condition.timeUnit;
        const plural = condition.daysAgo === 1 ? unit : unit + 's';
        field = `${condition.daysAgo} ${plural} ago ${field}`;
      }
      if (condition.leftMultiplier && condition.leftMultiplier !== 1) {
        field = `${field} * ${condition.leftMultiplier}`;
      }
      
      // Build right side
      let value = condition.value;
      if (condition.valueType === 'field' && condition.valueField) {
        value = this.buildFieldString(condition.valueField, condition.valueIndicatorType, condition.valueIndicatorName, condition.valueIndicatorParams);
        
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
          field: 'supertrend',
          operator: '>',
          value: '',
          logicalOperator: 'and',
          daysAgo: 1,
          timeUnit: 'day',
          leftMultiplier: 1,
          valueType: 'field',
          valueField: 'supertrend',
          valueDaysAgo: 0,
          valueTimeUnit: 'day',
          multiplier: 1,
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
          daysAgo: 0,
          timeUnit: 'day',
          leftMultiplier: 1,
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
      'supertrend': ['Period', 'Multiplier'],
      'macd': ['Fast', 'Slow', 'Signal'],
      'stochastic': ['%K', '%D'],
      'williamsr': ['Period']
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
