import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpClientModule, HttpErrorResponse } from '@angular/common/http';
import { ProgressBarComponent } from '../progress-bar.component';
import { TooltipComponent, TooltipData } from '../components/tooltip.component';
import { Observable, retry, timer, catchError, throwError } from 'rxjs';
import Swal from 'sweetalert2';

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
  indicatorComponent?: string; // For multi-component indicators like BB (upper/middle/lower)
  valueIndicatorType?: 'simple' | 'parameterized';
  valueIndicatorName?: string;
  valueIndicatorParams?: string[];
  valueIndicatorComponent?: string; // For multi-component indicators in value field
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
  indicatorComponent?: string; // For multi-component indicators
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
  selector: 'app-screener',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule, ProgressBarComponent, TooltipComponent],
  templateUrl: './screener.component.html',
  styleUrl: './screener.component.scss'
})
export class ScreenerComponent implements OnInit {
  expandedDates: Set<string> = new Set();
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
  
  // Multi-component indicators - indicators that have multiple output values
  multiComponentIndicators: { [key: string]: string[] } = {
    'bb': ['upper', 'middle', 'lower'],
    'bollinger': ['upper', 'middle', 'lower'],
    'macd': ['macd', 'signal', 'histogram'],
    'stochastic': ['k', 'd'],
    'keltner': ['upper', 'middle', 'lower'],
    'ichimoku': ['tenkan', 'kijun', 'senkou_a', 'senkou_b', 'chikou']
  };

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
  
  // Paste query functionality
  pasteQueryText = '';
  pasteQueryStatus = '';
  pasteQuerySuccess = false;
  
  // UI State for popup selectors
  activePopup: { type: string; conditionId: number; field?: string } | null = null;
  
  // Progress tracking
  showProgress = false;
  progressPhase = 'initializing';
  progressMessage = 'Starting...';
  progressProcessed = 0;
  progressTotal = 100;
  progressMatches?: number;
  private progressInterval?: any;
  
  // Tooltip state
  activeTooltip: { stock: string; date: string } | null = null;
  
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
    // Generate initial query
    this.generateQuery();
  }

  // Helper method to get timeframe from time period
  getTimeframe(timePeriod: string): 'daily' | 'weekly' | 'monthly' {
    if (timePeriod.includes('week')) return 'weekly';
    if (timePeriod.includes('month')) return 'monthly';
    return 'daily';
  }

  // Generate dynamic indicator key based on timeframe, parameters, and component
  generateIndicatorKey(field: string, timePeriod: string, params?: string[], component?: string): string {
    const timeframe = this.getTimeframe(timePeriod);
    const isIndicator = this.parameterizedIndicators.includes(field);
    
    if (isIndicator && params && params.length > 0) {
      // For indicators with parameters: timeframe_indicator_param1_param2
      let baseKey = `${timeframe}_${field}_${params.join('_')}`;
      
      // Add component if it's a multi-component indicator
      if (component && this.multiComponentIndicators[field]) {
        baseKey = `${timeframe}_${field}_${component}_${params.join('_')}`;
      }
      
      return baseKey;
    } else if (isIndicator) {
      // For indicators without specified params, use defaults
      const defaultParams = this.indicatorDefaults[field] || [];
      let baseKey = `${timeframe}_${field}_${defaultParams.join('_')}`;
      
      // Add component if it's a multi-component indicator
      if (component && this.multiComponentIndicators[field]) {
        baseKey = `${timeframe}_${field}_${component}_${defaultParams.join('_')}`;
      }
      
      return baseKey;
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
        const leftKey = this.generateIndicatorKey(condition.field, condition.timePeriod, condition.indicatorParams, condition.indicatorComponent);
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
        const rightKey = this.generateIndicatorKey(condition.valueField, condition.valueTimePeriod || 'daily', condition.valueIndicatorParams, condition.valueIndicatorComponent);
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
    if (this.conditions.length === 0 || !this.validateConditions()) {
      this.error = 'Please complete all condition configurations';
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

    // Send query to latest day endpoint with timeout and retry logic
    this.makeHttpRequestWithRetry(() => 
      this.http.post<QueryResult>(`${this.apiUrl}/query/latest`, { query })
    ).subscribe({
      next: (response) => {
        this.loading = false;
        this.results = response;
        this.groupByDate(response.matches);
        
        // Show completion in progress bar
        this.progressPhase = 'completed';
        this.progressMessage = `Found ${response.totalMatches} matches for latest day!`;
        this.progressProcessed = this.progressTotal;
        this.stopProgressPolling();
        
        // Auto-hide progress after delay, but allow manual close
        setTimeout(() => {
          if (this.progressPhase === 'completed') {
            this.showProgress = false;
          }
        }, 1000);
      },
      error: (error) => {
        this.loading = false;
        this.showProgress = false;
        this.error = this.getErrorMessage(error);
        console.error('Error:', error);
        this.stopProgressPolling();
      }
    });
  }

  runBacktest() {
    if (this.conditions.length === 0 || !this.validateConditions()) {
      this.error = 'Please complete all condition configurations';
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

    // Send query to original endpoint for full backtest with retry logic
    this.makeHttpRequestWithRetry(() => 
      this.http.post<QueryResult>(`${this.apiUrl}/query`, { query })
    ).subscribe({
      next: (response) => {
        this.loading = false;
        this.results = response;
        this.groupByDate(response.matches);
        
        // Show completion in progress bar
        this.progressPhase = 'completed';
        this.progressMessage = `Backtest completed! Found ${response.totalMatches} matches!`;
        this.progressProcessed = this.progressTotal;
        this.stopProgressPolling();
        
        // Auto-hide progress after delay, but allow manual close
        setTimeout(() => {
          if (this.progressPhase === 'completed') {
            this.showProgress = false;
          }
        }, 1000);
      },
      error: (error) => {
        this.loading = false;
        this.showProgress = false;
        this.error = this.getErrorMessage(error);
        console.error('Error:', error);
        this.stopProgressPolling();
      }
    });
  }
  
  runSpecialQuery() {
    // Hardcoded query as specified
    const specialQuery = `weekly volume crossed above 1 week ago volume * 1.5 and weekly close crossed above weekly supertrend(10,2) and weekly close crossed above weekly sma(20)`;
    
    this.loading = true;
    this.error = null;
    this.results = null;
    this.groupedResults.clear();
    this.showProgress = true;
    this.progressPhase = 'initializing';
    this.progressMessage = 'Starting special query scan...';
    this.progressProcessed = 0;
    this.progressTotal = 100;
    this.progressMatches = undefined;
    
    // Set the query string for display
    this.queryString = specialQuery;
    
    // Start polling for progress updates
    this.startProgressPolling();
    
    // Send query to full backtest endpoint with retry logic
    this.makeHttpRequestWithRetry(() => 
      this.http.post<QueryResult>(`${this.apiUrl}/query`, { query: specialQuery })
    ).subscribe({
      next: (response) => {
        this.loading = false;
        this.results = response;
        this.groupByDate(response.matches);
        
        // Show completion in progress bar
        this.progressPhase = 'completed';
        this.progressMessage = `Found ${response.totalMatches} matches for special query!`;
        this.progressProcessed = this.progressTotal;
        this.stopProgressPolling();
        
        // Auto-hide progress after delay, but allow manual close
        setTimeout(() => {
          if (this.progressPhase === 'completed') {
            this.showProgress = false;
          }
        }, 1000);
      },
      error: (error) => {
        this.loading = false;
        this.showProgress = false;
        this.error = this.getErrorMessage(error);
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
    this.expandedDates.clear();
    
    matches.forEach(match => {
      const date = new Date(match.timestamp).toLocaleDateString();
      if (!this.groupedResults.has(date)) {
        this.groupedResults.set(date, []);
      }
      this.groupedResults.get(date)?.push(match);
    });
    
    // Expand the latest date by default
    const sortedDates = this.getGroupedDates();
    if (sortedDates.length > 0) {
      this.expandedDates.add(sortedDates[0]);
    }
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
      
      // Set default component for multi-component indicators
      if (this.multiComponentIndicators[condition.field]) {
        condition.indicatorComponent = this.multiComponentIndicators[condition.field][0]; // Default to first component
      } else {
        condition.indicatorComponent = undefined;
      }
    } else {
      condition.indicatorType = 'simple';
      condition.indicatorName = undefined;
      condition.indicatorParams = undefined;
      condition.indicatorComponent = undefined;
    }
  }
  
  onValueFieldChange(condition: Condition) {
    // Update value indicator type based on field selection
    if (condition.valueField && this.parameterizedIndicators.includes(condition.valueField)) {
      condition.valueIndicatorType = 'parameterized';
      condition.valueIndicatorName = condition.valueField;
      condition.valueIndicatorParams = [...(this.indicatorDefaults[condition.valueField] || ['14'])];
      
      // Set default component for multi-component indicators
      if (this.multiComponentIndicators[condition.valueField]) {
        condition.valueIndicatorComponent = this.multiComponentIndicators[condition.valueField][0]; // Default to first component
      } else {
        condition.valueIndicatorComponent = undefined;
      }
    } else {
      condition.valueIndicatorType = 'simple';
      condition.valueIndicatorName = undefined;
      condition.valueIndicatorParams = undefined;
      condition.valueIndicatorComponent = undefined;
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

  toggleDateExpansion(date: string): void {
    if (this.expandedDates.has(date)) {
      this.expandedDates.delete(date);
    } else {
      this.expandedDates.add(date);
    }
  }

  isDateExpanded(date: string): boolean {
    return this.expandedDates.has(date);
  }

  getStockCountForDate(date: string): number {
    return this.groupedResults.get(date)?.length || 0;
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
      
      // Set default component for multi-component indicators
      if (this.multiComponentIndicators[term.field]) {
        term.indicatorComponent = this.multiComponentIndicators[term.field][0]; // Default to first component
      } else {
        term.indicatorComponent = undefined;
      }
    } else {
      term.indicatorType = 'simple';
      term.indicatorName = undefined;
      term.indicatorParams = undefined;
      term.indicatorComponent = undefined;
    }
  }
  
  buildComplexExpressionString(expr: ComplexExpression): string {
    if (!expr || !expr.terms || expr.terms.length === 0) return '';
    
    if (expr.type === 'avg') {
      const termStrings = expr.terms.map(term => {
        const key = this.generateIndicatorKey(term.field, term.timePeriod, term.indicatorParams, term.indicatorComponent);
        return key;
      });
      return `avg(${termStrings.join(', ')})`;
    } else if (expr.type === 'arithmetic' && expr.operator) {
      const termStrings = expr.terms.map(term => {
        const key = this.generateIndicatorKey(term.field, term.timePeriod, term.indicatorParams, term.indicatorComponent);
        return key;
      });
      // Add parentheses for complex expressions
      return `(${termStrings.join(` ${expr.operator} `)})`;
    }
    
    return '';
  }

  // Paste query functionality methods
  async pasteFromClipboard() {
    try {
      const text = await navigator.clipboard.readText();
      this.pasteQueryText = text;
      this.pasteQueryStatus = 'Query pasted from clipboard';
      this.pasteQuerySuccess = true;
      
      // Auto-clear status after 3 seconds
      setTimeout(() => {
        this.pasteQueryStatus = '';
      }, 3000);
    } catch (error) {
      this.pasteQueryStatus = 'Failed to access clipboard. Please paste manually.';
      this.pasteQuerySuccess = false;
      
      setTimeout(() => {
        this.pasteQueryStatus = '';
      }, 3000);
    }
  }

  parseAndPopulateQuery() {
    if (!this.pasteQueryText.trim()) {
      this.pasteQueryStatus = 'Please enter a query to parse';
      this.pasteQuerySuccess = false;
      return;
    }

    try {
      const parsedConditions = this.parseQueryText(this.pasteQueryText);
      
      if (parsedConditions.length === 0) {
        this.pasteQueryStatus = 'No valid conditions found in query';
        this.pasteQuerySuccess = false;
        return;
      }

      // Replace current conditions with parsed ones
      this.conditions = parsedConditions;
      this.nextId = Math.max(...parsedConditions.map(c => c.id)) + 1;
      
      // Generate the query string
      this.generateQuery();
      
      this.pasteQueryStatus = `Successfully parsed ${parsedConditions.length} condition(s)`;
      this.pasteQuerySuccess = true;
      
      // Auto-clear the paste text and status after success
      setTimeout(() => {
        this.pasteQueryText = '';
        this.pasteQueryStatus = '';
      }, 3000);
      
    } catch (error) {
      console.error('Error parsing query:', error);
      this.pasteQueryStatus = 'Failed to parse query. Please check the format.';
      this.pasteQuerySuccess = false;
      
      setTimeout(() => {
        this.pasteQueryStatus = '';
      }, 5000);
    }
  }

  private parseQueryText(queryText: string): Condition[] {
    const conditions: Condition[] = [];
    let conditionId = 1;
    
    // Clean and normalize the query text
    const cleanQuery = queryText.trim().toLowerCase();
    
    // Split by 'and' and 'or' to get individual conditions
    const parts = cleanQuery.split(/\s+(and|or)\s+/);
    
    // Process each condition part
    for (let i = 0; i < parts.length; i += 2) {
      const conditionText = parts[i].trim();
      const logicalOperator = (i + 1 < parts.length) ? (parts[i + 1] as 'and' | 'or') : 'and';
      
      const condition = this.parseConditionText(conditionText, conditionId++, logicalOperator);
      if (condition) {
        conditions.push(condition);
      }
    }
    
    return conditions;
  }

  private parseConditionText(conditionText: string, id: number, logicalOperator: 'and' | 'or'): Condition | null {
    // Parse operators in order of precedence
    const operators = ['crosses_above', 'crosses_below', '>=', '<=', '!=', '>', '<', '='];
    
    for (const operator of operators) {
      const opPattern = operator.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const regex = new RegExp(`(.+?)\\s+${opPattern}\\s+(.+)`);
      const match = conditionText.match(regex);
      
      if (match) {
        const leftSide = match[1].trim();
        const rightSide = match[2].trim();
        
        const parsedCondition = this.buildConditionFromParts(leftSide, operator, rightSide, id, logicalOperator);
        if (parsedCondition) {
          return parsedCondition;
        }
      }
    }
    
    return null;
  }

  private buildConditionFromParts(leftSide: string, operator: string, rightSide: string, id: number, logicalOperator: 'and' | 'or'): Condition | null {
    // Parse the left side to extract field information
    const leftFieldInfo = this.parseFieldExpression(leftSide);
    if (!leftFieldInfo) return null;
    
    // Create base condition
    const condition: Condition = {
      id: id,
      field: leftFieldInfo.field,
      operator: operator,
      value: rightSide,
      logicalOperator: logicalOperator,
      leftExpressionType: 'simple',
      timePeriod: leftFieldInfo.timePeriod,
      valueType: 'number',
      indicatorType: leftFieldInfo.indicatorType,
      indicatorName: leftFieldInfo.indicatorName,
      indicatorParams: leftFieldInfo.indicatorParams,
      indicatorComponent: leftFieldInfo.indicatorComponent
    };
    
    // Parse the right side to determine if it's a field or number
    const rightFieldInfo = this.parseFieldExpression(rightSide);
    if (rightFieldInfo) {
      // Right side is a field
      condition.valueType = 'field';
      condition.valueField = rightFieldInfo.field;
      condition.valueTimePeriod = rightFieldInfo.timePeriod;
      condition.valueIndicatorType = rightFieldInfo.indicatorType;
      condition.valueIndicatorName = rightFieldInfo.indicatorName;
      condition.valueIndicatorParams = rightFieldInfo.indicatorParams;
      condition.valueIndicatorComponent = rightFieldInfo.indicatorComponent;
      condition.value = ''; // Clear value since we're using a field
    } else {
      // Right side is a number
      condition.valueType = 'number';
      condition.value = rightSide;
    }
    
    return condition;
  }

  private parseFieldExpression(expression: string): any {
    // Remove time prefixes like "1 day ago", "2 weeks ago", etc.
    const timePattern = /^(\d+\s+(day|week|month)s?\s+ago\s+)/;
    const timeMatch = expression.match(timePattern);
    let timePeriod = 'daily';
    let cleanExpression = expression;
    
    if (timeMatch) {
      const timePhrase = timeMatch[1].trim();
      cleanExpression = expression.replace(timePattern, '').trim();
      timePeriod = this.parseTimePeriod(timePhrase);
    }
    
    // Parse component-based field format: timeframe_indicator_component_params
    const componentPattern = /^(daily|weekly|monthly)_([a-z]+)_(upper|lower|middle|macd|signal|histogram|k|d)_(.+)$/;
    const componentMatch = cleanExpression.match(componentPattern);
    
    if (componentMatch) {
      const [, timeframe, indicator, component, paramsStr] = componentMatch;
      const params = paramsStr.split('_');
      
      return {
        field: indicator,
        timePeriod: timeframe,
        indicatorType: 'parameterized',
        indicatorName: indicator,
        indicatorParams: params,
        indicatorComponent: component
      };
    }
    
    // Parse standard field format: timeframe_indicator_params
    const standardPattern = /^(daily|weekly|monthly)_([a-z]+)_(.+)$/;
    const standardMatch = cleanExpression.match(standardPattern);
    
    if (standardMatch) {
      const [, timeframe, indicator, paramsStr] = standardMatch;
      const params = paramsStr.split('_');
      
      return {
        field: indicator,
        timePeriod: timeframe,
        indicatorType: 'parameterized',
        indicatorName: indicator,
        indicatorParams: params
      };
    }
    
    // Check for basic fields (open, high, low, close, volume)
    const basicFields = ['open', 'high', 'low', 'close', 'volume'];
    if (basicFields.includes(cleanExpression)) {
      return {
        field: cleanExpression,
        timePeriod: timePeriod,
        indicatorType: 'simple'
      };
    }
    
    // Check for parameterized indicators without timeframe prefix
    if (this.parameterizedIndicators.includes(cleanExpression)) {
      return {
        field: cleanExpression,
        timePeriod: timePeriod,
        indicatorType: 'parameterized',
        indicatorName: cleanExpression,
        indicatorParams: this.indicatorDefaults[cleanExpression] || ['14']
      };
    }
    
    return null;
  }

  private parseTimePeriod(timePhrase: string): string {
    const match = timePhrase.match(/(\d+)\s+(day|week|month)s?\s+ago/);
    if (match) {
      const number = parseInt(match[1]);
      const unit = match[2];
      
      if (unit === 'day') {
        if (number <= 5) {
          return `${number}-day${number > 1 ? 's' : ''}`;
        } else {
          return 'n-days';
        }
      } else if (unit === 'week') {
        if (number <= 3) {
          return `${number}-week${number > 1 ? 's' : ''}`;
        } else {
          return 'n-weeks';
        }
      } else if (unit === 'month') {
        if (number <= 3) {
          return `${number}-month${number > 1 ? 's' : ''}`;
        } else {
          return 'n-months';
        }
      }
    }
    
    return 'daily';
  }

  // Validation method for conditions
  validateConditions(): boolean {
    return this.conditions.every(condition => {
      // Check if the condition has a valid operator and field
      if (!condition.field || !condition.operator) {
        return false;
      }
      
      // For number value type, check if value is provided
      if (condition.valueType === 'number') {
        return condition.value && condition.value.trim() !== '';
      }
      
      // For field value type, check if valueField is provided
      if (condition.valueType === 'field') {
        return condition.valueField && condition.valueField.trim() !== '';
      }
      
      return true;
    });
  }

  // Popup management methods
  openPopup(type: string, conditionId: number, field?: string) {
    this.activePopup = { type, conditionId, field };
  }

  closePopup() {
    this.activePopup = null;
  }

  selectPopupValue(value: any, updateField?: string) {
    if (!this.activePopup) return;
    
    const condition = this.conditions.find(c => c.id === this.activePopup!.conditionId);
    if (!condition) return;

    // Update the condition based on the popup type
    switch (this.activePopup.type) {
      case 'timePeriod':
        condition.timePeriod = value;
        break;
      case 'field':
        condition.field = value;
        this.onFieldChange(condition);
        break;
      case 'operator':
        condition.operator = value;
        break;
      case 'valueType':
        condition.valueType = value;
        break;
      case 'valueField':
        condition.valueField = value;
        this.onValueFieldChange(condition);
        break;
      case 'valueTimePeriod':
        condition.valueTimePeriod = value;
        break;
      case 'logicalOperator':
        condition.logicalOperator = value;
        break;
      case 'indicatorComponent':
        condition.indicatorComponent = value;
        break;
      case 'valueIndicatorComponent':
        condition.valueIndicatorComponent = value;
        break;
      case 'arithmeticOperator':
        condition.arithmeticOperator = value;
        break;
      case 'indicatorParam':
        // Handle parameter changes
        if (this.activePopup.field && condition.indicatorParams) {
          const paramIndex = parseInt(this.activePopup.field);
          condition.indicatorParams[paramIndex] = value.toString();
        }
        break;
      case 'valueIndicatorParam':
        // Handle value parameter changes
        if (this.activePopup.field && condition.valueIndicatorParams) {
          const paramIndex = parseInt(this.activePopup.field);
          condition.valueIndicatorParams[paramIndex] = value.toString();
        }
        break;
    }
    
    // Regenerate query after update
    this.generateQuery();
    this.closePopup();
  }

  // Helper methods for display text
  getDisplayText(value: any, type: string): string {
    switch (type) {
      case 'timePeriod':
        const period = this.timePeriodOptions.find(p => p.value === value);
        return period ? period.label : value;
      case 'field':
        const field = this.fields.find(f => f.value === value);
        return field ? field.label : value;
      case 'operator':
        const operator = this.operators.find(o => o.value === value);
        return operator ? operator.label : value;
      case 'valueType':
        return value === 'number' ? 'Number' : 'Field';
      case 'logicalOperator':
        return value === 'and' ? 'AND' : 'OR';
      case 'arithmeticOperator':
        return value || 'None';
      default:
        return value || '';
    }
  }

  // Helper to get options for popup
  getPopupOptions(type: string): any[] {
    switch (type) {
      case 'timePeriod':
      case 'valueTimePeriod':
        return this.timePeriodOptions;
      case 'field':
      case 'valueField':
        return this.fields;
      case 'operator':
        return this.operators;
      case 'valueType':
        return [
          { value: 'number', label: 'Number' },
          { value: 'field', label: 'Field' }
        ];
      case 'logicalOperator':
        return [
          { value: 'and', label: 'AND' },
          { value: 'or', label: 'OR' }
        ];
      case 'arithmeticOperator':
        return [
          { value: '', label: 'None' },
          { value: '+', label: '+' },
          { value: '-', label: '-' },
          { value: '*', label: '×' },
          { value: '/', label: '÷' }
        ];
      case 'indicatorParam':
      case 'valueIndicatorParam':
        // Generate common parameter values
        const commonValues = [5, 10, 14, 20, 21, 26, 50, 100, 200];
        const options = commonValues.map(val => ({ 
          value: val.toString(), 
          label: val.toString() 
        }));
        // Add range 1-30 for other common values
        for (let i = 1; i <= 30; i++) {
          if (!commonValues.includes(i)) {
            options.push({ value: i.toString(), label: i.toString() });
          }
        }
        return options.sort((a, b) => parseInt(a.value) - parseInt(b.value));
      default:
        return [];
    }
  }

  // Method to open parameter popup
  openParameterPopup(type: 'indicatorParam' | 'valueIndicatorParam', conditionId: number, paramIndex: number) {
    this.activePopup = { 
      type: type, 
      conditionId: conditionId, 
      field: paramIndex.toString() 
    };
  }

  // Helper to get component options for multi-component indicators
  getComponentOptions(popup: any): string[] {
    if (!popup) return [];
    
    const condition = this.conditions.find(c => c.id === popup.conditionId);
    if (!condition) return [];
    
    const field = popup.type === 'valueIndicatorComponent' ? condition.valueField : condition.field;
    if (!field || !this.multiComponentIndicators[field]) return [];
    
    return this.multiComponentIndicators[field];
  }

  // HTTP request retry logic with exponential backoff
  private makeHttpRequestWithRetry<T>(requestFn: () => Observable<T>, maxRetries: number = 3): Observable<T> {
    return requestFn().pipe(
      retry({
        count: maxRetries,
        delay: (error, retryCount) => {
          // Only retry on network errors and server errors
          if (this.isRetryableError(error)) {
            const delay = Math.min(1000 * Math.pow(2, retryCount - 1), 10000);
            console.log(`Retrying request (${retryCount}/${maxRetries}) after ${delay}ms for error:`, error.message);
            return timer(delay);
          }
          return throwError(() => error);
        }
      }),
      catchError((error) => {
        console.error('Request failed after all retries:', error);
        return throwError(() => error);
      })
    );
  }

  // Check if error is retryable
  private isRetryableError(error: any): boolean {
    if (error instanceof HttpErrorResponse) {
      // Retry on network errors and 5xx server errors
      return error.status === 0 || error.status >= 500;
    }
    // Retry on connection errors
    return error.code === 'ECONNRESET' || 
           error.code === 'ETIMEDOUT' || 
           error.code === 'ECONNABORTED' ||
           error.message?.includes('timeout') ||
           error.message?.includes('connection');
  }

  // Get user-friendly error message
  private getErrorMessage(error: any): string {
    if (error instanceof HttpErrorResponse) {
      if (error.status === 0) {
        Swal.fire({
          icon: 'error',
          title: 'Connection Failed',
          text: 'Please check your internet connection and try again.',
          confirmButtonColor: '#dc3545'
        });
        return 'Connection failed. Please check your internet connection and try again.';
      }
      
      // Handle 400 errors specifically for missing indicators
      if (error.status === 400) {
        const errorMessage = error.error?.error || error.error?.message || '';
        
        // Check if it's a missing indicator error
        if (errorMessage.includes('Missing required indicators') || 
            errorMessage.includes('not available in precalculated storage')) {
          const missingIndicators = error.error?.missing || [];
          if (missingIndicators.length > 0) {
            // Show SweetAlert for missing indicators
            Swal.fire({
              icon: 'error',
              title: 'Missing Indicators',
              html: `
                <div style="text-align: left;">
                  <p>The following indicators are not precalculated:</p>
                  <ul style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 4px; padding: 15px 30px; margin: 10px 0;">
                    ${missingIndicators.map((ind: string) => `<li style="color: #856404; font-family: monospace;">${ind}</li>`).join('')}
                  </ul>
                  <p style="color: #6c757d; font-style: italic; margin-top: 15px;">Please contact the administrator to add these indicators.</p>
                </div>
              `,
              confirmButtonColor: '#dc3545',
              confirmButtonText: 'OK',
              width: '500px'
            });
            return `Missing indicators: ${missingIndicators.join(', ')}. These indicators need to be precalculated before running this query.`;
          }
          // Show SweetAlert for generic missing indicator error
          Swal.fire({
            icon: 'error',
            title: 'Query Error',
            text: errorMessage,
            confirmButtonColor: '#dc3545'
          });
          return errorMessage;
        }
        
        // Show SweetAlert for other 400 errors
        Swal.fire({
          icon: 'error',
          title: 'Query Error',
          text: errorMessage,
          confirmButtonColor: '#dc3545'
        });
        return errorMessage;
      }
      
      if (error.status >= 500) {
        return 'Server error occurred. The request will be retried automatically.';
      }
      
      return error.error?.error || error.message || 'An unexpected error occurred';
    }
    
    if (error.code === 'ECONNRESET' || error.message?.includes('ECONNRESET')) {
      return 'Connection was reset. Retrying automatically...';
    }
    
    if (error.code === 'ETIMEDOUT' || error.message?.includes('timeout')) {
      return 'Request timed out. Retrying with longer timeout...';
    }
    
    return error.error?.error || error.message || 'An unexpected error occurred';
  }

  // Progress bar close method
  closeProgress() {
    this.showProgress = false;
    this.stopProgressPolling();
  }

  // Tooltip methods
  showTooltip(match: any, event: MouseEvent) {
    this.activeTooltip = { stock: match.stock, date: match.day };
  }

  hideTooltip() {
    this.activeTooltip = null;
  }

  getScanTypeLabel(): string {
    if (!this.results || !this.results.scanType) {
      return 'Values';
    }
    return this.results.scanType === 'latest_day' ? 'Latest' : 'Historical';
  }

  getTooltipData(match: any): TooltipData {
    const tooltipData: TooltipData = {};
    
    
    // Use actual indicator values from the backend if available
    if (match.indicators) {
      // First, try to get values from the actual indicators data
      this.conditions.forEach((condition, index) => {
        if (condition.field && condition.indicatorParams) {
          const key = `${condition.field}_${condition.indicatorParams.join('_')}`;
          const indicatorKey = this.generateIndicatorKey(condition.field, condition.timePeriod, condition.indicatorParams, condition.indicatorComponent);
          
          // Try to find the actual value in the indicators
          if (match.indicators[indicatorKey] !== undefined && match.indicators[indicatorKey] !== null) {
            tooltipData[key] = parseFloat(match.indicators[indicatorKey]);
          } else {
            // If not found, use mock value as fallback
            tooltipData[key] = this.generateMockValue(condition.field, match);
          }
        } else if (condition.field) {
          // For simple fields like close, open, etc.
          if (condition.field === 'close') {
            tooltipData[condition.field] = parseFloat(match.close);
          } else if (match.indicators[condition.field] !== undefined && match.indicators[condition.field] !== null) {
            // Use actual value from indicators
            tooltipData[condition.field] = parseFloat(match.indicators[condition.field]);
          } else {
            // Generate mock values for other fields
            tooltipData[condition.field] = this.generateMockValue(condition.field, match);
          }
        }
        
        // Add value field if it's a field comparison
        if (condition.valueType === 'field' && condition.valueField && condition.valueIndicatorParams) {
          const valueKey = `${condition.valueField}_${condition.valueIndicatorParams.join('_')}`;
          const valueIndicatorKey = this.generateIndicatorKey(condition.valueField, condition.valueTimePeriod || 'daily', condition.valueIndicatorParams, condition.valueIndicatorComponent);
          
          if (match.indicators[valueIndicatorKey] !== undefined && match.indicators[valueIndicatorKey] !== null) {
            tooltipData[valueKey] = parseFloat(match.indicators[valueIndicatorKey]);
          } else if (match.indicators[condition.valueField] !== undefined && match.indicators[condition.valueField] !== null) {
            tooltipData[valueKey] = parseFloat(match.indicators[condition.valueField]);
          } else {
            tooltipData[valueKey] = this.generateMockValue(condition.valueField, match);
          }
        }
      });
      
      // Also include any other relevant indicators that were calculated
      Object.keys(match.indicators).forEach(key => {
        if (!tooltipData[key] && match.indicators[key] !== undefined && match.indicators[key] !== null) {
          tooltipData[key] = parseFloat(match.indicators[key]);
        }
      });
    } else {
      // Fallback to mock data if no indicators are provided (backward compatibility)
      this.conditions.forEach((condition, index) => {
        if (condition.field && condition.indicatorParams) {
          const key = `${condition.field}_${condition.indicatorParams.join('_')}`;
          tooltipData[key] = this.generateMockValue(condition.field, match);
        } else if (condition.field) {
          if (condition.field === 'close') {
            tooltipData[condition.field] = parseFloat(match.close);
          } else {
            tooltipData[condition.field] = this.generateMockValue(condition.field, match);
          }
        }
        
        if (condition.valueType === 'field' && condition.valueField && condition.valueIndicatorParams) {
          const valueKey = `${condition.valueField}_${condition.valueIndicatorParams.join('_')}`;
          tooltipData[valueKey] = this.generateMockValue(condition.valueField, match);
        }
      });
    }
    
    return tooltipData;
  }

  private generateMockValue(field: string, match: any): number {
    // Generate realistic mock values based on the field type and stock data
    const basePrice = parseFloat(match.close);
    const stockHash = this.hashString(match.stock);
    const dateHash = this.hashString(match.day || ''); // Use the specific date for variation
    
    const combinedHash = stockHash + dateHash; // Combine both for unique values per stock-date
    
    switch (field) {
      case 'rsi':
        return Math.min(100, Math.max(0, 30 + (combinedHash % 40)));
      case 'sma':
      case 'ema':
      case 'wma':
        return basePrice * (0.95 + (combinedHash % 10) / 100);
      case 'volume':
        return Math.floor(100000 + (combinedHash % 500000));
      case 'macd':
        return ((combinedHash % 20) - 10);
      case 'bb':
        return basePrice * (1 + (combinedHash % 5) / 100);
      case 'supertrend':
        return basePrice * (0.98 + (combinedHash % 4) / 100);
      case 'atr':
        return basePrice * (0.02 + (combinedHash % 3) / 100);
      case 'open':
        return basePrice * (0.99 + (combinedHash % 2) / 100);
      case 'high':
        return basePrice * (1.01 + (combinedHash % 2) / 100);
      case 'low':
        return basePrice * (0.98 + (combinedHash % 2) / 100);
      default:
        return basePrice;
    }
  }

  private hashString(str: string): number {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    return Math.abs(hash);
  }
}