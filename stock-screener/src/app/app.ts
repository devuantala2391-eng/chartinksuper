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
  // Left side expression support
  leftExpressionType?: 'simple' | 'complex' | 'avg';
  leftExpression?: ComplexExpression;
  // Time period handling
  timePeriod: 'daily' | '1-day' | '2-days' | '3-days' | '4-days' | '5-days' | 'n-days' | 
              'weekly' | '1-week' | '2-weeks' | '3-weeks' | 'n-weeks' |
              'monthly' | '1-month' | '2-months' | '3-months' | 'n-months';
  customDaysAgo?: number;
  customWeeksAgo?: number;
  customMonthsAgo?: number;
  timeUnit?: 'day' | 'week' | 'month'; // This is now derived from timePeriod
  valueType: 'number' | 'field' | 'expression';
  valueField?: string;
  valueTimePeriod?: 'daily' | '1-day' | '2-days' | '3-days' | '4-days' | '5-days' | 'n-days' | 
                    'weekly' | '1-week' | '2-weeks' | '3-weeks' | 'n-weeks' |
                    'monthly' | '1-month' | '2-months' | '3-months' | 'n-months';
  valueCustomDaysAgo?: number;
  valueCustomWeeksAgo?: number;
  valueCustomMonthsAgo?: number;
  valueTimeUnit?: 'day' | 'week' | 'month';
  // Arithmetic expression support
  arithmeticOperator?: '+' | '-' | '*' | '/' | 'avg' | '';
  arithmeticValue?: string;
  arithmeticExpression?: ArithmeticExpression;
  // Indicator parameters
  indicatorType?: 'simple' | 'parameterized';
  indicatorName?: string;
  indicatorParams?: string[];
  valueIndicatorType?: 'simple' | 'parameterized';
  valueIndicatorName?: string;
  valueIndicatorParams?: string[];
}

interface ComplexExpression {
  type: 'arithmetic' | 'avg';
  terms: ExpressionTerm[];
  operator?: '+' | '-' | '*' | '/';
}

interface ExpressionTerm {
  field: string;
  timePeriod: string;
  indicatorType?: 'simple' | 'parameterized';
  indicatorName?: string;
  indicatorParams?: string[];
  customDaysAgo?: number;
  customWeeksAgo?: number;
  customMonthsAgo?: number;
}

interface ArithmeticExpression {
  type: 'field' | 'number' | 'operator' | 'function';
  value?: string;
  field?: string;
  timePeriod?: string;
  indicatorParams?: string[];
  operator?: '+' | '-' | '*' | '/' | 'avg';
  operands?: ArithmeticExpression[];
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
  scanType?: string;
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
  
  // Available fields for conditions - organized by category
  fields = [
    // All available indicators
    { value: 'open', label: 'Open' },
    { value: 'high', label: 'High' },
    { value: 'low', label: 'Low' },
    { value: 'close', label: 'Close' },
    { value: 'volume', label: 'Volume' },
    { value: 'sma', label: 'SMA' },
    { value: 'ema', label: 'EMA' },
    { value: 'wma', label: 'WMA' },
    { value: 'vwap', label: 'VWAP' },
    { value: 'rsi', label: 'RSI' },
    { value: 'macd', label: 'MACD' },
    { value: 'stochastic', label: 'Stochastic' },
    { value: 'cci', label: 'CCI' },
    { value: 'mfi', label: 'MFI' },
    { value: 'roc', label: 'ROC' },
    { value: 'bb', label: 'Bollinger Bands' },
    { value: 'atr', label: 'ATR' },
    { value: 'keltner', label: 'Keltner Channel' },
    { value: 'supertrend', label: 'SuperTrend' },
    { value: 'adx', label: 'ADX' },
    { value: 'psar', label: 'Parabolic SAR' },
    { value: 'ichimoku', label: 'Ichimoku' },
    { value: 'obv', label: 'OBV' },
    { value: 'vpt', label: 'VPT' },
    { value: 'ad', label: 'A/D Line' }
  ];
  
  // Parameterized indicators
  parameterizedIndicators = [
    'rsi', 'sma', 'ema', 'wma', 'bb', 'supertrend', 'macd', 'stochastic',
    'cci', 'mfi', 'roc', 'atr', 'keltner', 'adx', 'psar', 'ichimoku'
  ];
  
  // Default parameters for indicators
  indicatorDefaults: { [key: string]: string[] } = {
    'rsi': ['14'],
    'sma': ['20'],
    'ema': ['20'],
    'wma': ['20'],
    'bb': ['20', '2'],
    'supertrend': ['10', '3'],
    'macd': ['12', '26', '9'],
    'stochastic': ['14', '3', '3'],
    'cci': ['20'],
    'mfi': ['14'],
    'roc': ['10'],
    'atr': ['14'],
    'keltner': ['20', '2'],
    'adx': ['14'],
    'psar': ['0.02', '0.2'],
    'ichimoku': ['9', '26', '52']
  };

  operators = [
    { value: '>', label: 'Greater than' },
    { value: '<', label: 'Less than' },
    { value: '>=', label: 'Greater than or equal' },
    { value: '<=', label: 'Less than or equal' },
    { value: '=', label: 'Equal to' },
    { value: '!=', label: 'Not equal to' },
    { value: 'crosses_above', label: 'crosses above' },
    { value: 'crosses_below', label: 'crosses below' },
    { value: 'increased_by', label: 'increased by %' },
    { value: 'decreased_by', label: 'decreased by %' }
  ];

  // Time period options
  timePeriodOptions = [
    // Daily options
    { value: 'daily', label: 'Daily' },
    { value: '1-day', label: '1 day ago' },
    { value: '2-days', label: '2 days ago' },
    { value: '3-days', label: '3 days ago' },
    { value: '4-days', label: '4 days ago' },
    { value: '5-days', label: '5 days ago' },
    { value: 'n-days', label: 'n days ago' },
    // Weekly options
    { value: 'weekly', label: 'Weekly' },
    { value: '1-week', label: '1 week ago' },
    { value: '2-weeks', label: '2 weeks ago' },
    { value: '3-weeks', label: '3 weeks ago' },
    { value: 'n-weeks', label: 'n weeks ago' },
    // Monthly options
    { value: 'monthly', label: 'Monthly' },
    { value: '1-month', label: '1 month ago' },
    { value: '2-months', label: '2 months ago' },
    { value: '3-months', label: '3 months ago' },
    { value: 'n-months', label: 'n months ago' }
  ];

  // Arithmetic operators
  arithmeticOperators = [
    { value: '+', label: '+' },
    { value: '-', label: '-' },
    { value: '*', label: '×' },
    { value: '/', label: '÷' },
    { value: 'avg', label: 'AVG' }
  ];

  conditions: Condition[] = [
    { 
      id: 1, 
      field: 'rsi', 
      operator: '>', 
      value: '60', 
      logicalOperator: 'and', 
      leftExpressionType: 'simple',
      timePeriod: 'daily', 
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

  // Helper method to get timeframe from time period
  getTimeframe(timePeriod: string): 'daily' | 'weekly' | 'monthly' {
    if (timePeriod.includes('week')) return 'weekly';
    if (timePeriod.includes('month')) return 'monthly';
    return 'daily';
  }

  // Generate dynamic indicator key based on timeframe and parameters
  generateIndicatorKey(field: string, timePeriod: string, params?: string[]): string {
    const timeframe = this.getTimeframe(timePeriod);
    const isIndicator = this.parameterizedIndicators.includes(field);
    
    if (isIndicator && params && params.length > 0) {
      // For indicators with parameters: timeframe_indicator_param1_param2
      return `${timeframe}_${field}_${params.join('_')}`;
    } else if (isIndicator) {
      // For indicators without specified params, use defaults
      const defaultParams = this.indicatorDefaults[field] || [];
      return `${timeframe}_${field}_${defaultParams.join('_')}`;
    } else {
      // For basic fields: timeframe_field
      return `${timeframe}_${field}`;
    }
  }

  addCondition() {
    const newCondition: Condition = {
      id: this.nextId++,
      field: 'rsi',
      operator: '>',
      value: '',
      logicalOperator: 'and',
      leftExpressionType: 'simple',
      timePeriod: 'daily',
      valueType: 'number',
      indicatorType: 'parameterized',
      indicatorName: 'rsi',
      indicatorParams: ['14']
    };
    
    this.conditions.push(newCondition);
    
    // Initialize the condition's field settings
    this.onFieldChange(newCondition);
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
      let field: string;
      
      // Build left side based on expression type
      if (condition.leftExpressionType === 'complex' || condition.leftExpressionType === 'avg') {
        // Build complex expression
        if (condition.leftExpression) {
          field = this.buildComplexExpressionString(condition.leftExpression);
        } else {
          field = ''; // Fallback
        }
      } else {
        // Build simple field with dynamic key
        const leftKey = this.generateIndicatorKey(condition.field, condition.timePeriod, condition.indicatorParams);
        field = this.buildFieldStringWithKey(leftKey, condition.field, condition.indicatorType, condition.indicatorName, condition.indicatorParams);
        
        // Handle time period for left side
        const timeOffset = this.getTimeOffset(condition.timePeriod, condition.customDaysAgo, condition.customWeeksAgo, condition.customMonthsAgo);
        if (timeOffset) {
          field = `${timeOffset} ${field}`;
        }
      }
      
      // Build right side
      let value = condition.value;
      if (condition.valueType === 'field' && condition.valueField) {
        const rightKey = this.generateIndicatorKey(condition.valueField, condition.valueTimePeriod || 'daily', condition.valueIndicatorParams);
        value = this.buildFieldStringWithKey(rightKey, condition.valueField, condition.valueIndicatorType, condition.valueIndicatorName, condition.valueIndicatorParams);
        
        const valueTimeOffset = this.getTimeOffset(condition.valueTimePeriod || 'daily', condition.valueCustomDaysAgo, condition.valueCustomWeeksAgo, condition.valueCustomMonthsAgo);
        if (valueTimeOffset) {
          value = `${valueTimeOffset} ${value}`;
        }
        
        // Add arithmetic operation if specified
        if (condition.arithmeticOperator && condition.arithmeticValue) {
          value = `${value} ${condition.arithmeticOperator} ${condition.arithmeticValue}`;
        }
      } else if (condition.valueType === 'expression' && condition.arithmeticExpression) {
        // Handle complex arithmetic expressions
        value = this.buildArithmeticExpression(condition.arithmeticExpression);
      }
      
      const conditionStr = `${field} ${condition.operator} ${value}`;
      if (index === 0) {
        return conditionStr;
      }
      return `${condition.logicalOperator} ${conditionStr}`;
    }).join(' ');
  }

  // Build field string with dynamic key
  buildFieldStringWithKey(key: string, field: string, indicatorType?: string, indicatorName?: string, params?: string[]): string {
    if (indicatorType === 'parameterized' && indicatorName && params) {
      // Use the dynamic key for the indicator
      return key;
    }
    // For simple fields, also use the key which includes timeframe
    return key;
  }

  // Get time offset string based on time period
  getTimeOffset(timePeriod: string, customDays?: number, customWeeks?: number, customMonths?: number): string {
    if (timePeriod === 'daily' || timePeriod === 'weekly' || timePeriod === 'monthly') {
      return ''; // No offset for current period
    }
    
    // Handle days
    if (timePeriod.includes('day')) {
      if (timePeriod === 'n-days' && customDays) {
        const plural = customDays === 1 ? 'day' : 'days';
        return `${customDays} ${plural} ago`;
      }
      const match = timePeriod.match(/(\d+)-day/);
      if (match) {
        const days = parseInt(match[1]);
        const plural = days === 1 ? 'day' : 'days';
        return `${days} ${plural} ago`;
      }
    }
    
    // Handle weeks
    if (timePeriod.includes('week')) {
      if (timePeriod === 'n-weeks' && customWeeks) {
        const plural = customWeeks === 1 ? 'week' : 'weeks';
        return `${customWeeks} ${plural} ago`;
      }
      const match = timePeriod.match(/(\d+)-week/);
      if (match) {
        const weeks = parseInt(match[1]);
        const plural = weeks === 1 ? 'week' : 'weeks';
        return `${weeks} ${plural} ago`;
      }
    }
    
    // Handle months
    if (timePeriod.includes('month')) {
      if (timePeriod === 'n-months' && customMonths) {
        const plural = customMonths === 1 ? 'month' : 'months';
        return `${customMonths} ${plural} ago`;
      }
      const match = timePeriod.match(/(\d+)-month/);
      if (match) {
        const months = parseInt(match[1]);
        const plural = months === 1 ? 'month' : 'months';
        return `${months} ${plural} ago`;
      }
    }
    
    return '';
  }

  // Build arithmetic expression (for complex expressions)
  buildArithmeticExpression(expr: ArithmeticExpression): string {
    if (!expr) return '';
    
    switch (expr.type) {
      case 'number':
        return expr.value || '0';
      
      case 'field':
        if (expr.field && expr.timePeriod) {
          const key = this.generateIndicatorKey(expr.field, expr.timePeriod, expr.indicatorParams);
          return key;
        }
        return expr.field || '';
      
      case 'function':
        if (expr.operator === 'avg' && expr.operands) {
          const operandStrings = expr.operands.map(op => this.buildArithmeticExpression(op));
          return `avg(${operandStrings.join(', ')})`;
        }
        return '';
      
      case 'operator':
        if (expr.operator && expr.operands && expr.operands.length >= 2) {
          const left = this.buildArithmeticExpression(expr.operands[0]);
          const right = this.buildArithmeticExpression(expr.operands[1]);
          return `(${left} ${expr.operator} ${right})`;
        }
        return '';
      
      default:
        return '';
    }
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
    this.progressMessage = 'Starting latest day scan...';
    this.progressProcessed = 0;
    this.progressTotal = 100;
    this.progressMatches = undefined;

    const query = this.buildQuery();
    this.queryString = query;
    
    // Start polling for progress updates
    this.startProgressPolling();

    // Send query to latest day endpoint
    this.http.post<QueryResult>(`${this.apiUrl}/query/latest`, { query })
      .subscribe({
        next: (response) => {
          this.loading = false;
          this.results = response;
          this.groupByDate(response.matches);
          
          // Show completion in progress bar
          this.progressPhase = 'completed';
          this.progressMessage = `Found ${response.totalMatches} matches for latest day!`;
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

  runBacktest() {
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
    this.progressMessage = 'Starting backtest...';
    this.progressProcessed = 0;
    this.progressTotal = 100;
    this.progressMatches = undefined;

    const query = this.buildQuery();
    this.queryString = query;
    
    // Start polling for progress updates
    this.startProgressPolling();

    // Send query to original endpoint for full backtest
    this.http.post<QueryResult>(`${this.apiUrl}/query`, { query })
      .subscribe({
        next: (response) => {
          this.loading = false;
          this.results = response;
          this.groupByDate(response.matches);
          
          // Show completion in progress bar
          this.progressPhase = 'completed';
          this.progressMessage = `Backtest completed! Found ${response.totalMatches} matches!`;
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
          leftExpressionType: 'simple',
          timePeriod: '1-day',
          valueType: 'field',
          valueField: 'volume',
          valueTimePeriod: '1-week',
          arithmeticOperator: '*',
          arithmeticValue: '1.2',
          indicatorType: 'simple',
          valueIndicatorType: 'simple'
        });
        break;
      case 'price-breakout':
        this.conditions.push({
          id: this.nextId++,
          field: 'close',
          operator: '>',
          value: '',
          logicalOperator: 'and',
          leftExpressionType: 'simple',
          timePeriod: 'daily',
          valueType: 'field',
          valueField: 'sma',
          valueTimePeriod: 'daily',
          arithmeticOperator: '*',
          arithmeticValue: '1.05',
          indicatorType: 'simple',
          valueIndicatorType: 'parameterized',
          valueIndicatorName: 'sma',
          valueIndicatorParams: ['20']
        });
        break;
      case 'trend-reversal':
        this.conditions.push({
          id: this.nextId++,
          field: 'supertrend',
          operator: '>',
          value: '',
          logicalOperator: 'and',
          leftExpressionType: 'simple',
          timePeriod: '1-day',
          valueType: 'field',
          valueField: 'supertrend',
          valueTimePeriod: 'daily',
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
          leftExpressionType: 'simple',
          timePeriod: 'daily',
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
    if (!indicatorName) {
      return ['Period'];
    }
    
    const labels: { [key: string]: string[] } = {
      'rsi': ['Period'],
      'sma': ['Period'],
      'ema': ['Period'],
      'wma': ['Period'],
      'bb': ['Period', 'Std Dev'],
      'supertrend': ['Period', 'Multiplier'],
      'macd': ['Fast', 'Slow', 'Signal'],
      'stochastic': ['%K Period', '%D Period', 'Smooth'],
      'cci': ['Period'],
      'mfi': ['Period'],
      'roc': ['Period'],
      'atr': ['Period'],
      'keltner': ['Period', 'Multiplier'],
      'adx': ['Period'],
      'psar': ['Start', 'Max'],
      'ichimoku': ['Tenkan', 'Kijun', 'Senkou']
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

  showGuide() {
    // Open guide or show modal with instructions
    alert('Scanner Guide:\n\n' +
          '1. Select time period (Today, 1 day ago, etc.)\n' +
          '2. Choose an indicator or field\n' +
          '3. Select comparison operator\n' +
          '4. Enter a value or compare with another field\n' +
          '5. Add more conditions as needed\n' +
          '6. Click "Run Scan" for latest day or "Run Full Backtest" for historical data');
  }

  clearAll() {
    if (confirm('Are you sure you want to clear all conditions and results?')) {
      this.conditions = [{
        id: 1,
        field: 'close',
        operator: '>',
        value: '',
        logicalOperator: 'and',
        leftExpressionType: 'simple',
        timePeriod: 'daily',
        valueType: 'number'
      }];
      this.clearResults();
      this.queryString = '';
    }
  }

  formatDate(timestamp: string): string {
    const date = new Date(timestamp);
    return date.toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric'
    });
  }

  getGroupedResults(): any[] {
    // Return all results as a flat array for table display
    return this.results?.matches || [];
  }
  
  // Complex expression methods
  initializeComplexExpression(condition: Condition, type: 'arithmetic' | 'avg') {
    condition.leftExpression = {
      type: type,
      terms: [{
        field: condition.field || 'close',
        timePeriod: condition.timePeriod || 'daily',
        indicatorType: condition.indicatorType,
        indicatorName: condition.indicatorName,
        indicatorParams: condition.indicatorParams ? [...condition.indicatorParams] : undefined
      }],
      operator: type === 'arithmetic' ? '+' : undefined
    };
    
    // Add a second term for arithmetic expressions
    if (type === 'arithmetic') {
      condition.leftExpression.terms.push({
        field: 'open',
        timePeriod: 'daily',
        indicatorType: 'simple'
      });
    }
  }
  
  addExpressionTerm(condition: Condition) {
    if (!condition.leftExpression) return;
    
    condition.leftExpression.terms.push({
      field: 'close',
      timePeriod: 'daily',
      indicatorType: 'simple'
    });
  }
  
  removeExpressionTerm(condition: Condition, index: number) {
    if (!condition.leftExpression) return;
    
    if (condition.leftExpression.terms.length > 1) {
      condition.leftExpression.terms.splice(index, 1);
    }
  }
  
  onExpressionTypeChange(condition: Condition) {
    if (condition.leftExpressionType === 'simple') {
      condition.leftExpression = undefined;
    } else if (condition.leftExpressionType === 'complex' || condition.leftExpressionType === 'avg') {
      this.initializeComplexExpression(condition, condition.leftExpressionType === 'avg' ? 'avg' : 'arithmetic');
    }
  }
  
  onExpressionFieldChange(term: ExpressionTerm) {
    // Update indicator type based on field selection
    if (this.parameterizedIndicators.includes(term.field)) {
      term.indicatorType = 'parameterized';
      term.indicatorName = term.field;
      term.indicatorParams = [...(this.indicatorDefaults[term.field] || ['14'])];
    } else {
      term.indicatorType = 'simple';
      term.indicatorName = undefined;
      term.indicatorParams = undefined;
    }
  }
  
  buildComplexExpressionString(expr: ComplexExpression): string {
    if (!expr || !expr.terms || expr.terms.length === 0) return '';
    
    if (expr.type === 'avg') {
      const termStrings = expr.terms.map(term => {
        const key = this.generateIndicatorKey(term.field, term.timePeriod, term.indicatorParams);
        return key;
      });
      return `avg(${termStrings.join(', ')})`;
    } else if (expr.type === 'arithmetic' && expr.operator) {
      const termStrings = expr.terms.map(term => {
        const key = this.generateIndicatorKey(term.field, term.timePeriod, term.indicatorParams);
        return key;
      });
      // Add parentheses for complex expressions
      return `(${termStrings.join(` ${expr.operator} `)})`;
    }
    
    return '';
  }
}
