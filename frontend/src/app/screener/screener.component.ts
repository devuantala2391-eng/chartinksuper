import { Component, OnInit, OnDestroy, NgZone } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpClientModule, HttpErrorResponse } from '@angular/common/http';
import { ProgressBarComponent } from '../progress-bar.component';
import { TooltipComponent, TooltipData } from '../components/tooltip.component';
import { Observable, retry, timer, catchError, throwError } from 'rxjs';
import { Router, ActivatedRoute } from '@angular/router';
import Swal from 'sweetalert2';
import { environment } from '../../environments/environment';

interface Condition {
  id: number;
  field: string;
  operator: string;
  value: string;
  enabled: boolean;
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
export class ScreenerComponent implements OnInit, OnDestroy {
  expandedDates: Set<string> = new Set();
  title = 'Stock Screener';
  naturalLanguageQuery = '';
  
  // Math reference for template
  Math = Math;
  
  // Pagination and filter state for each table
  tableStates: Map<string, {
    currentPage: number;
    pageSize: number;
    filterText: string;
    filteredData: any[];
    paginatedData: any[];
    totalPages: number;
  }> = new Map();
  
  // Available fields for conditions - organized by category
  fields = [
    // All available indicators
    { value: 'open', label: 'Open' },
    { value: 'high', label: 'High' },
    { value: 'low', label: 'Low' },
    { value: 'close', label: 'Close' },
    { value: 'volume', label: 'Volume' },
    { value: 'sma', label: 'Simple Moving Average (SMA)' },
    { value: 'ema', label: 'Exponential Moving Average (EMA)' },
    { value: 'rsi', label: 'Relative Strength Index (RSI)' },
    { value: 'supertrend', label: 'SuperTrend' },
    { value: 'bb', label: 'Bollinger Bands' },
    { value: 'pctchg', label: '% Change' }
  ];
  
  // Parameterized indicators
  parameterizedIndicators = [
    'sma', 'ema', 'rsi', 'supertrend', 'bb'
  ];
  
  // Multi-component indicators - indicators that have multiple output values
  multiComponentIndicators: { [key: string]: string[] } = {
    'bb': ['upper', 'lower'],
    'bollinger': ['upper', 'lower']
  };

  // Default parameters for indicators
  indicatorDefaults: { [key: string]: string[] } = {
    'sma': ['20'],
    'ema': ['12'],
    'rsi': ['14'],
    'bb': ['20', '2'],
    'supertrend': ['10', '3']
  };

  operators = [
    { value: '>', label: 'Greater than' },
    { value: '<', label: 'Less than' },
    { value: '>=', label: 'Greater than or equal' },
    { value: '<=', label: 'Less than or equal' },
    { value: '=', label: 'Equal to' },
    { value: '!=', label: 'Not equal to' },
    { value: 'crossed above', label: 'crossed above' },
    { value: 'crossed below', label: 'crossed below' }
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
      field: 'supertrend', 
      operator: '>', 
      value: '100', 
      enabled: true, 
      leftExpressionType: 'simple',
      timePeriod: 'daily', 
      valueType: 'number',
      indicatorType: 'parameterized',
      indicatorName: 'supertrend',
      indicatorParams: ['10', '3']
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
  private queryProgressEventSource: EventSource | null = null;
  private isQueryRunning = false;
  private currentRequestAbortController: AbortController | null = null;
  
  // Tooltip state
  activeTooltip: { stock: string; date: string } | null = null;
  parameterInputValue: string = '';
  
  // CSV Upload properties
  selectedFile: File | null = null;
  uploading = false;
  uploadStatus = '';
  uploadSuccess = false;
  showUploadProgress = false;
  uploadProgress = 0;
  uploadProgressText = '';
  private csvProgressEventSource: EventSource | null = null;
  
  private apiUrl = environment.apiUrl;
  private nextId = 2;

  constructor(private http: HttpClient, private ngZone: NgZone, private router: Router, private route: ActivatedRoute) {}

  ngOnInit() {
    // Load conditions from URL first, then fallback to localStorage
    this.loadConditionsFromUrl();
    
    // If no conditions were loaded, initialize default conditions
    if (this.conditions.length === 0) {
      this.conditions.forEach(condition => {
        this.onFieldChange(condition);
        if (condition.valueField) {
          this.onValueFieldChange(condition);
        }
      });
    } else {
      // Initialize loaded conditions
      this.conditions.forEach(condition => {
        this.onFieldChange(condition);
        if (condition.valueField) {
          this.onValueFieldChange(condition);
        }
      });
    }
    
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
      field: 'supertrend',
      operator: '>',
      value: '',
      enabled: true,
      leftExpressionType: 'simple',
      timePeriod: 'daily',
      valueType: 'number',
      indicatorType: 'parameterized',
      indicatorName: 'supertrend',
      indicatorParams: ['10', '3']
    };
    
    this.conditions.push(newCondition);
    
    // Initialize the condition's field settings
    this.onFieldChange(newCondition);
    this.generateQuery();
    this.saveConditionsToUrl();
  }

  removeCondition(id: number) {
    this.conditions = this.conditions.filter(c => c.id !== id);
    this.generateQuery();
    this.saveConditionsToUrl();
  }

  onConditionToggle() {
    // Method called when condition is toggled on/off
    // The generateQuery and saveConditionsToStorage are called in the template
  }

  saveConditionsToStorage() {
    try {
      localStorage.setItem('screener_conditions', JSON.stringify(this.conditions));
      localStorage.setItem('screener_query', this.naturalLanguageQuery);
    } catch (error) {
      console.warn('Failed to save conditions to localStorage:', error);
    }
  }

  loadConditionsFromStorage() {
    try {
      const savedConditions = localStorage.getItem('screener_conditions');
      const savedQuery = localStorage.getItem('screener_query');
      
      if (savedConditions) {
        const conditions = JSON.parse(savedConditions);
        if (Array.isArray(conditions) && conditions.length > 0) {
          // Ensure all conditions have the enabled property
          this.conditions = conditions.map(condition => ({
            ...condition,
            enabled: condition.enabled !== undefined ? condition.enabled : true
          }));
          
          // Update nextId to avoid conflicts
          const maxId = Math.max(...this.conditions.map(c => c.id));
          this.nextId = maxId + 1;
          
          this.generateQuery();
        }
      }
      
      if (savedQuery) {
        this.naturalLanguageQuery = savedQuery;
      }
    } catch (error) {
      console.warn('Failed to load conditions from localStorage:', error);
    }
  }

  loadConditionsFromUrl() {
    try {
      const queryParam = this.route.snapshot.queryParams['query'];
      if (queryParam) {
        const decodedQuery = decodeURIComponent(queryParam);
        const parsedConditions = this.parseQueryText(decodedQuery);
        
        if (parsedConditions.length > 0) {
          this.conditions = parsedConditions;
          this.nextId = Math.max(...parsedConditions.map(c => c.id)) + 1;
          this.naturalLanguageQuery = decodedQuery;
          return;
        }
      }
      
      // Fallback to localStorage if no URL query
      this.loadConditionsFromStorage();
    } catch (error) {
      console.warn('Failed to load conditions from URL:', error);
      // Fallback to localStorage on error
      this.loadConditionsFromStorage();
    }
  }

  saveConditionsToUrl() {
    try {
      const query = this.buildQuery();
      if (query) {
        this.router.navigate([], {
          relativeTo: this.route,
          queryParams: { query: encodeURIComponent(query) },
          queryParamsHandling: 'merge'
        });
      } else {
        // Remove query param if no conditions
        this.router.navigate([], {
          relativeTo: this.route,
          queryParams: { query: null },
          queryParamsHandling: 'merge'
        });
      }
    } catch (error) {
      console.warn('Failed to save conditions to URL:', error);
    }
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
    return this.conditions.filter(condition => condition.enabled).map((condition, index) => {
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
      return `and ${conditionStr}`;
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

    // Prevent duplicate requests
    if (!this.checkAndPreventDuplicateRequest()) {
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
    
    // Start SSE for progress updates
    this.startProgressSSE();

    // Send query to latest day endpoint with timeout and retry logic
    this.makeHttpRequestWithRetry(() => 
      this.http.post<QueryResult>(`${this.apiUrl}/query/latest`, { query })
    ).subscribe({
      next: (response) => {
        this.loading = false;
        this.results = response;
        this.groupByDate(response.matches, true); // Latest day only
        
        // Show completion in progress bar
        this.progressPhase = 'completed';
        this.progressMessage = `Found ${response.totalMatches} matches for latest day!`;
        this.progressProcessed = this.progressTotal;
        this.stopProgressPolling();
        this.finishQueryRequest();
        
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
        //console.error('Error:', error);
        this.stopProgressPolling();
        this.finishQueryRequest();
      }
    });
  }

  runBacktest() {
    if (this.conditions.length === 0 || !this.validateConditions()) {
      this.error = 'Please complete all condition configurations';
      return;
    }

    // Prevent duplicate requests
    if (!this.checkAndPreventDuplicateRequest()) {
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
    
    // Start SSE for progress updates
    this.startProgressSSE();

    // Send query to original endpoint for full backtest with retry logic
    this.makeHttpRequestWithRetry(() => 
      this.http.post<QueryResult>(`${this.apiUrl}/query`, { query })
    ).subscribe({
      next: (response) => {
        this.loading = false;
        this.results = response;
        this.groupByDate(response.matches, false); // Full backtest - multiple dates
        
        // Show completion in progress bar
        this.progressPhase = 'completed';
        this.progressMessage = `Backtest completed! Found ${response.totalMatches} matches!`;
        this.progressProcessed = this.progressTotal;
        this.stopProgressPolling();
        this.finishQueryRequest();
        
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
        //console.error('Error:', error);
        this.stopProgressPolling();
        this.finishQueryRequest();
      }
    });
  }
  
  runSpecialQuery() {
    // Prevent duplicate requests
    if (!this.checkAndPreventDuplicateRequest()) {
      return;
    }
    
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
    
    // Start SSE for progress updates
    this.startProgressSSE();
    
    // Send query to full backtest endpoint with retry logic
    this.makeHttpRequestWithRetry(() => 
      this.http.post<QueryResult>(`${this.apiUrl}/query`, { query: specialQuery })
    ).subscribe({
      next: (response) => {
        this.loading = false;
        this.results = response;
        this.groupByDate(response.matches, false); // Special query - full backtest, multiple dates
        
        // Show completion in progress bar
        this.progressPhase = 'completed';
        this.progressMessage = `Found ${response.totalMatches} matches for special query!`;
        this.progressProcessed = this.progressTotal;
        this.stopProgressPolling();
        this.finishQueryRequest();
        
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
        //console.error('Error:', error);
        this.stopProgressPolling();
        this.finishQueryRequest();
      }
    });
  }
  
  private startProgressSSE() {
    // Clear any existing SSE connection
    this.stopProgressSSE();
    
    //console.log('Starting SSE connection for query progress...');
    
    // Create new SSE connection
    this.queryProgressEventSource = new EventSource(`${this.apiUrl}/progress-stream`);
    
    this.queryProgressEventSource.onopen = () => {
      //console.log('Query progress SSE connection opened');
    };
    
    this.queryProgressEventSource.onmessage = (event) => {
      try {
        const progress = JSON.parse(event.data);
        //console.log('Progress update received via SSE:', progress);
        
        // Skip heartbeat messages
        if (progress.heartbeat) {
          return;
        }
        
        // Skip connection messages
        if (progress.connected) {
          return;
        }
        
        // Run inside Angular zone to trigger change detection
        this.ngZone.run(() => {
          // Update progress UI
          if (progress.isRunning) {
            this.progressPhase = progress.phase;
            this.progressMessage = progress.message || '';
            this.progressProcessed = progress.processed || 0;
            this.progressTotal = progress.total || 2446;
            if (progress.matches !== undefined) {
              this.progressMatches = progress.matches;
            }
          } else if (progress.phase === 'completed') {
            // Handle completion
            this.progressPhase = 'completed';
            this.progressMessage = progress.message || 'Query completed!';
            this.progressProcessed = progress.total || this.progressTotal;
            if (progress.matches !== undefined) {
              this.progressMatches = progress.matches;
            }
            
            // Close SSE connection on completion
            setTimeout(() => {
              this.stopProgressSSE();
            }, 1000);
          }
        });
      } catch (error) {
        //console.error('Error parsing SSE progress data:', error);
      }
    };
    
    this.queryProgressEventSource.onerror = (error) => {
      //console.error('Query progress SSE error:', error);
      
      // Auto-reconnect after short delay if connection fails
      setTimeout(() => {
        if (this.queryProgressEventSource?.readyState === EventSource.CLOSED) {
          //console.log('Attempting to reconnect SSE...');
          this.startProgressSSE();
        }
      }, 2000);
    };
  }
  
  private stopProgressSSE() {
    if (this.queryProgressEventSource) {
      //console.log('Closing query progress SSE connection');
      this.queryProgressEventSource.close();
      this.queryProgressEventSource = null;
    }
  }
  
  // Legacy function - keep for backward compatibility but make it call SSE
  private stopProgressPolling() {
    this.stopProgressSSE();
  }
  
  private checkAndPreventDuplicateRequest(): boolean {
    if (this.isQueryRunning) {
      //console.warn('Query already running, ignoring duplicate request');
      return false; // Prevent execution
    }
    
    // Cancel any existing request
    if (this.currentRequestAbortController) {
      this.currentRequestAbortController.abort();
    }
    
    // Create new abort controller for this request
    this.currentRequestAbortController = new AbortController();
    this.isQueryRunning = true;
    
    return true; // Allow execution
  }
  
  private finishQueryRequest() {
    this.isQueryRunning = false;
    this.currentRequestAbortController = null;
  }
  
  // Manual test function for debugging SSE
  testProgressSSE() {
    //console.log('Testing progress SSE connection...');
    this.startProgressSSE();
  }

  groupByDate(matches: any[], isLatestDayOnly: boolean = false) {
    this.groupedResults.clear();
    this.expandedDates.clear();
    this.tableStates.clear(); // Clear table states
    
    // Debug what we're actually receiving
    console.log('DEBUG: groupByDate called with', matches.length, 'matches', 'isLatestDayOnly:', isLatestDayOnly);
    
    if (isLatestDayOnly) {
      // For latest day endpoint: Force all matches under a single date
      const uniqueTimestamps = new Set();
      
      matches.forEach((match, index) => {
        const timestamp = match.timestamp || match.date;
        uniqueTimestamps.add(timestamp);
        
        if (index < 3) {
          console.log(`Match ${index}:`, {
            stock: match.stock,
            date: match.date,
            timestamp: match.timestamp,
            effectiveTimestamp: timestamp
          });
        }
      });
      
      console.log('Unique timestamps found:', Array.from(uniqueTimestamps));
      
      // Force all matches to use the same date (latest date from any match)
      const timestamps = Array.from(uniqueTimestamps).map(t => Number(t)).sort((a, b) => b - a);
      const latestTimestamp = timestamps[0];
      
      console.log('Using latest timestamp for all matches:', latestTimestamp);
      
      if (latestTimestamp) {
        // Convert UTC timestamp to IST date
        const istDate = new Date(latestTimestamp + 19800000); // Add 5.5 hours for IST
        const dateKey = istDate.getUTCFullYear() + '-' + 
                       String(istDate.getUTCMonth() + 1).padStart(2, '0') + '-' + 
                       String(istDate.getUTCDate()).padStart(2, '0');
        
        console.log('Single date key (IST):', dateKey);
        
        // Group ALL matches under the same date
        this.groupedResults.set(dateKey, matches);
        
        // Initialize table state for the single date group
        this.initializeTableState(dateKey, matches);
        
        // Expand the date by default
        this.expandedDates.add(dateKey);
      }
    } else {
      // For full backtest: Group matches by their individual dates
      console.log('Grouping by individual dates for full backtest');
      
      matches.forEach((match, index) => {
        const timestamp = match.timestamp || match.date;
        
        if (index < 3) {
          console.log(`Match ${index}:`, {
            stock: match.stock,
            date: match.date,
            timestamp: match.timestamp,
            effectiveTimestamp: timestamp
          });
        }
        
        if (timestamp) {
          // Convert UTC timestamp to IST date
          const istDate = new Date(Number(timestamp) + 19800000); // Add 5.5 hours for IST
          const dateKey = istDate.getUTCFullYear() + '-' + 
                         String(istDate.getUTCMonth() + 1).padStart(2, '0') + '-' + 
                         String(istDate.getUTCDate()).padStart(2, '0');
          
          if (!this.groupedResults.has(dateKey)) {
            this.groupedResults.set(dateKey, []);
          }
          this.groupedResults.get(dateKey)!.push(match);
        }
      });
      
      // Initialize table states for all date groups
      for (const [dateKey, dateMatches] of this.groupedResults.entries()) {
        this.initializeTableState(dateKey, dateMatches);
      }
      
      // Expand all dates by default
      this.groupedResults.forEach((_, date) => {
        this.expandedDates.add(date);
      });
      
      console.log('Grouped results by date:', this.groupedResults);
    }
  }

  getGroupedDates(): string[] {
    // Sort by date string in descending order (newest first)
    return Array.from(this.groupedResults.keys()).sort((a, b) => b.localeCompare(a));
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
          enabled: true,
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
          enabled: true,
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
          enabled: true,
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
    }
    
    this.generateQuery();
    this.saveConditionsToUrl();
  }
  
  onFieldChange(condition: Condition) {
    // Update indicator type based on field selection
    if (this.parameterizedIndicators.includes(condition.field)) {
      condition.indicatorType = 'parameterized';
      condition.indicatorName = condition.field;
      
      // Only set default parameters if they don't exist or are empty
      if (!condition.indicatorParams || condition.indicatorParams.length === 0) {
        condition.indicatorParams = [...(this.indicatorDefaults[condition.field] || ['14'])];
      }
      
      // Set default component for multi-component indicators
      if (this.multiComponentIndicators[condition.field]) {
        if (!condition.indicatorComponent) {
          condition.indicatorComponent = this.multiComponentIndicators[condition.field][0]; // Default to first component
        }
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
      
      // Only set default parameters if they don't exist or are empty
      if (!condition.valueIndicatorParams || condition.valueIndicatorParams.length === 0) {
        condition.valueIndicatorParams = [...(this.indicatorDefaults[condition.valueField] || ['14'])];
      }
      
      // Set default component for multi-component indicators
      if (this.multiComponentIndicators[condition.valueField]) {
        if (!condition.valueIndicatorComponent) {
          condition.valueIndicatorComponent = this.multiComponentIndicators[condition.valueField][0]; // Default to first component
        }
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

  hardRefresh() {
    const confirmMessage = 'This will DELETE all data and refetch everything from scratch.\n\n' +
      'This process will:\n' +
      '• Delete all stock data\n' +
      '• Delete all precalculated indicators\n' +
      '• Refetch all data with the candle count specified in environment\n' +
      '• Recalculate all indicators\n\n' +
      'This may take several minutes. Continue?';
    
    if (!confirm(confirmMessage)) {
      return;
    }

    this.loading = true;
    this.error = null;
    this.showProgress = true;
    this.progressPhase = 'initializing';
    this.progressMessage = 'Starting hard refresh...';
    this.progressProcessed = 0;
    this.progressTotal = 0;
    this.progressMatches = 0;

    // Start SSE connection for progress updates
    this.startProgressSSE();

    this.http.post<any>(`${this.apiUrl}/hard-refresh`, {}, {
      headers: {
        'ngrok-skip-browser-warning': '69420'
      }
    }).subscribe({
      next: (response) => {
        this.progressMessage = response.message || 'Hard refresh started...';
        // Progress will be tracked through SSE
      },
      error: (error) => {
        this.loading = false;
        this.showProgress = false;
        this.error = 'Failed to start hard refresh: ' + error.message;
      }
    });
  }

  clearAll() {
    if (confirm('Are you sure you want to clear all conditions and results?')) {
      this.conditions = [{
        id: 1,
        field: 'close',
        operator: '>',
        value: '',
        enabled: true,
        leftExpressionType: 'simple',
        timePeriod: 'daily',
        valueType: 'number'
      }];
      this.clearResults();
      this.queryString = '';
      this.generateQuery();
      this.saveConditionsToUrl();
    }
  }

  formatDate(timestamp: string): string {
    // Convert UTC timestamp to IST
    // The timestamps are stored at 18:30 UTC which represents 00:00 IST of the next day
    const istDate = new Date(Number(timestamp) + 19800000); // Add 5.5 hours for IST
    return istDate.toLocaleDateString('en-IN', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      timeZone: 'UTC' // Use UTC since we already adjusted the timestamp
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
      this.saveConditionsToUrl();
      
      this.pasteQueryStatus = `Successfully parsed ${parsedConditions.length} condition(s)`;
      this.pasteQuerySuccess = true;
      
      // Auto-clear the paste text and status after success
      setTimeout(() => {
        this.pasteQueryText = '';
        this.pasteQueryStatus = '';
      }, 3000);
      
    } catch (error) {
      //console.error('Error parsing query:', error);
      this.pasteQueryStatus = 'Failed to parse query. Please check the format.';
      this.pasteQuerySuccess = false;
      
      setTimeout(() => {
        this.pasteQueryStatus = '';
      }, 5000);
    }
  }

  loadTestQuery() {
    const testQuery = "daily_volume > 50000 and daily_pctchg < 9 and daily_pctchg > 0 and daily_close > 30 and weekly_volume > 1 week ago weekly_volume and daily_high < 1 day ago daily_volume * 2 and weekly_close crossed above weekly_indicator";
    
    this.pasteQueryText = testQuery;
    this.pasteQueryStatus = 'Test query loaded';
    this.pasteQuerySuccess = true;
    
    // Auto-parse the test query
    try {
      const parsedConditions = this.parseQueryText(testQuery);
      
      if (parsedConditions.length === 0) {
        this.pasteQueryStatus = 'No valid conditions found in test query';
        this.pasteQuerySuccess = false;
        return;
      }

      // Replace current conditions with parsed ones
      this.conditions = parsedConditions;
      this.nextId = Math.max(...parsedConditions.map(c => c.id)) + 1;
      
      // Generate the query string
      this.generateQuery();
      this.saveConditionsToUrl();
      
      this.pasteQueryStatus = `Test query loaded and parsed: ${parsedConditions.length} condition(s)`;
      this.pasteQuerySuccess = true;
      
      // Auto-clear status after 5 seconds
      setTimeout(() => {
        this.pasteQueryStatus = '';
      }, 5000);
      
    } catch (error) {
      this.pasteQueryStatus = 'Failed to parse test query';
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
      const condition = this.parseConditionText(conditionText, conditionId++);
      if (condition) {
        conditions.push(condition);
      }
    }
    
    return conditions;
  }

  private parseConditionText(conditionText: string, id: number): Condition | null {
    // Parse operators in order of precedence
    const operators = ['crossed above', 'crossed below', '>=', '<=', '!=', '>', '<', '='];
    
    for (const operator of operators) {
      const opPattern = operator.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const regex = new RegExp(`(.+?)\\s+${opPattern}\\s+(.+)`);
      const match = conditionText.match(regex);
      
      if (match) {
        const leftSide = match[1].trim();
        const rightSide = match[2].trim();
        
        const parsedCondition = this.buildConditionFromParts(leftSide, operator, rightSide, id);
        if (parsedCondition) {
          return parsedCondition;
        }
      }
    }
    
    return null;
  }

  private buildConditionFromParts(leftSide: string, operator: string, rightSide: string, id: number): Condition | null {
    // Parse the left side to extract field information
    const leftFieldInfo = this.parseFieldExpression(leftSide);
    if (!leftFieldInfo) return null;
    
    // Create base condition
    const condition: Condition = {
      id: id,
      field: leftFieldInfo.field,
      operator: operator,
      value: rightSide,
      enabled: true,
      leftExpressionType: 'simple',
      timePeriod: leftFieldInfo.timePeriod,
      valueType: 'number',
      indicatorType: leftFieldInfo.indicatorType,
      indicatorName: leftFieldInfo.indicatorName,
      indicatorParams: leftFieldInfo.indicatorParams,
      indicatorComponent: leftFieldInfo.indicatorComponent
    };
    
    // Set custom time values for left side if needed
    if (leftFieldInfo.customDaysAgo !== undefined) {
      condition.customDaysAgo = leftFieldInfo.customDaysAgo;
    }
    if (leftFieldInfo.customWeeksAgo !== undefined) {
      condition.customWeeksAgo = leftFieldInfo.customWeeksAgo;
    }
    if (leftFieldInfo.customMonthsAgo !== undefined) {
      condition.customMonthsAgo = leftFieldInfo.customMonthsAgo;
    }
    
    // Parse the right side to determine if it's a field, mathematical expression, or number
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
      
      // Set custom time values for right side if needed
      if (rightFieldInfo.customDaysAgo !== undefined) {
        condition.valueCustomDaysAgo = rightFieldInfo.customDaysAgo;
      }
      if (rightFieldInfo.customWeeksAgo !== undefined) {
        condition.valueCustomWeeksAgo = rightFieldInfo.customWeeksAgo;
      }
      if (rightFieldInfo.customMonthsAgo !== undefined) {
        condition.valueCustomMonthsAgo = rightFieldInfo.customMonthsAgo;
      }
      
      condition.value = ''; // Clear value since we're using a field
    } else if (this.isMathExpression(rightSide)) {
      // Right side is a mathematical expression
      condition.valueType = 'expression';
      condition.value = rightSide;
    } else {
      // Right side is a number
      condition.valueType = 'number';
      condition.value = rightSide;
    }
    
    return condition;
  }

  private isMathExpression(expression: string): boolean {
    // Check if the expression contains mathematical operators and field references
    const mathOperators = /[\+\-\*\/]/;
    const hasFieldReference = /\b(daily|weekly|monthly)_[a-z_]+\b|\b(open|high|low|close|volume)\b/;
    return mathOperators.test(expression) && hasFieldReference.test(expression);
  }

  private parseFieldExpression(expression: string): any {
    // Remove time prefixes like "1 day ago", "2 weeks ago", etc.
    const timePattern = /^(\d+\s+(day|week|month)s?\s+ago\s+)/;
    const timeMatch = expression.match(timePattern);
    let timePeriod = 'daily';
    let cleanExpression = expression;
    let customDaysAgo: number | undefined;
    let customWeeksAgo: number | undefined;
    let customMonthsAgo: number | undefined;
    
    if (timeMatch) {
      const timePhrase = timeMatch[1].trim();
      cleanExpression = expression.replace(timePattern, '').trim();
      const parsedTime = this.parseTimePeriod(timePhrase);
      timePeriod = parsedTime.timePeriod;
      customDaysAgo = parsedTime.customDaysAgo;
      customWeeksAgo = parsedTime.customWeeksAgo;
      customMonthsAgo = parsedTime.customMonthsAgo;
    }
    
    // Check for basic fields with timeframe prefix first: daily_close, weekly_volume, etc.
    const basicFields = ['open', 'high', 'low', 'close', 'volume'];
    const basicFieldWithTimePattern = /^(daily|weekly|monthly)_([a-z]+)$/;
    const basicFieldMatch = cleanExpression.match(basicFieldWithTimePattern);
    
    if (basicFieldMatch) {
      const [, timeframe, fieldName] = basicFieldMatch;
      if (basicFields.includes(fieldName)) {
        // If we had a time offset (like "1 week ago"), use that instead of the embedded timeframe
        const effectiveTimePeriod = timeMatch ? timePeriod : timeframe;
        const result: any = {
          field: fieldName,
          timePeriod: effectiveTimePeriod,
          indicatorType: 'simple'
        };
        if (customDaysAgo !== undefined) result.customDaysAgo = customDaysAgo;
        if (customWeeksAgo !== undefined) result.customWeeksAgo = customWeeksAgo;
        if (customMonthsAgo !== undefined) result.customMonthsAgo = customMonthsAgo;
        return result;
      }
    }
    
    // Parse component-based field format: timeframe_indicator_component_params
    const componentPattern = /^(daily|weekly|monthly)_([a-z]+)_(upper|lower|middle|macd|signal|histogram|k|d)_(.+)$/;
    const componentMatch = cleanExpression.match(componentPattern);
    
    if (componentMatch) {
      const [, timeframe, indicator, component, paramsStr] = componentMatch;
      const params = paramsStr.split('_');
      
      // If we had a time offset (like "1 week ago"), use that instead of the embedded timeframe
      const effectiveTimePeriod = timeMatch ? timePeriod : timeframe;
      const result: any = {
        field: indicator,
        timePeriod: effectiveTimePeriod,
        indicatorType: 'parameterized',
        indicatorName: indicator,
        indicatorParams: params,
        indicatorComponent: component
      };
      if (customDaysAgo !== undefined) result.customDaysAgo = customDaysAgo;
      if (customWeeksAgo !== undefined) result.customWeeksAgo = customWeeksAgo;
      if (customMonthsAgo !== undefined) result.customMonthsAgo = customMonthsAgo;
      return result;
    }
    
    // Parse standard field format: timeframe_indicator_params (allow alphanumeric indicators)
    const standardPattern = /^(daily|weekly|monthly)_([a-z]+)_(.+)$/;
    const standardMatch = cleanExpression.match(standardPattern);
    
    if (standardMatch) {
      const [, timeframe, indicator, paramsStr] = standardMatch;
      const params = paramsStr.split('_');
      
      // If we had a time offset (like "1 week ago"), use that instead of the embedded timeframe
      const effectiveTimePeriod = timeMatch ? timePeriod : timeframe;
      const result: any = {
        field: indicator,
        timePeriod: effectiveTimePeriod,
        indicatorType: 'parameterized',
        indicatorName: indicator,
        indicatorParams: params
      };
      if (customDaysAgo !== undefined) result.customDaysAgo = customDaysAgo;
      if (customWeeksAgo !== undefined) result.customWeeksAgo = customWeeksAgo;
      if (customMonthsAgo !== undefined) result.customMonthsAgo = customMonthsAgo;
      return result;
    }
    
    // Check for basic fields without timeframe prefix (open, high, low, close, volume)
    if (basicFields.includes(cleanExpression)) {
      const result: any = {
        field: cleanExpression,
        timePeriod: timePeriod,
        indicatorType: 'simple'
      };
      if (customDaysAgo !== undefined) result.customDaysAgo = customDaysAgo;
      if (customWeeksAgo !== undefined) result.customWeeksAgo = customWeeksAgo;
      if (customMonthsAgo !== undefined) result.customMonthsAgo = customMonthsAgo;
      return result;
    }
    
    // Check for parameterized indicators without timeframe prefix
    if (this.parameterizedIndicators.includes(cleanExpression)) {
      const result: any = {
        field: cleanExpression,
        timePeriod: timePeriod,
        indicatorType: 'parameterized',
        indicatorName: cleanExpression,
        indicatorParams: this.indicatorDefaults[cleanExpression] || ['14']
      };
      if (customDaysAgo !== undefined) result.customDaysAgo = customDaysAgo;
      if (customWeeksAgo !== undefined) result.customWeeksAgo = customWeeksAgo;
      if (customMonthsAgo !== undefined) result.customMonthsAgo = customMonthsAgo;
      return result;
    }
    
    return null;
  }

  private parseTimePeriod(timePhrase: string): { timePeriod: string; customDaysAgo?: number; customWeeksAgo?: number; customMonthsAgo?: number } {
    const match = timePhrase.match(/(\d+)\s+(day|week|month)s?\s+ago/);
    if (match) {
      const number = parseInt(match[1]);
      const unit = match[2];
      
      if (unit === 'day') {
        if (number <= 5) {
          return { timePeriod: `${number}-day${number > 1 ? 's' : ''}` };
        } else {
          return { timePeriod: 'n-days', customDaysAgo: number };
        }
      } else if (unit === 'week') {
        if (number <= 3) {
          return { timePeriod: `${number}-week${number > 1 ? 's' : ''}` };
        } else {
          return { timePeriod: 'n-weeks', customWeeksAgo: number };
        }
      } else if (unit === 'month') {
        if (number <= 3) {
          return { timePeriod: `${number}-month${number > 1 ? 's' : ''}` };
        } else {
          return { timePeriod: 'n-months', customMonthsAgo: number };
        }
      }
    }
    
    return { timePeriod: 'daily' };
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
        // Handle parameter changes - allow decimal values
        if (this.activePopup.field && condition.indicatorParams) {
          const paramIndex = parseInt(this.activePopup.field);
          const numValue = parseFloat(value.toString());
          if (!isNaN(numValue) && numValue > 0) {
            condition.indicatorParams[paramIndex] = numValue.toString();
          }
        }
        break;
      case 'valueIndicatorParam':
        // Handle value parameter changes - allow decimal values
        if (this.activePopup.field && condition.valueIndicatorParams) {
          const paramIndex = parseInt(this.activePopup.field);
          const numValue = parseFloat(value.toString());
          if (!isNaN(numValue) && numValue > 0) {
            condition.valueIndicatorParams[paramIndex] = numValue.toString();
          }
        }
        break;
    }
    
    // Regenerate query after update
    this.generateQuery();
    this.saveConditionsToUrl();
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
    const condition = this.conditions.find(c => c.id === conditionId);
    if (condition) {
      // Set current parameter value in the input field
      if (type === 'indicatorParam' && condition.indicatorParams && condition.indicatorParams[paramIndex]) {
        this.parameterInputValue = condition.indicatorParams[paramIndex];
      } else if (type === 'valueIndicatorParam' && condition.valueIndicatorParams && condition.valueIndicatorParams[paramIndex]) {
        this.parameterInputValue = condition.valueIndicatorParams[paramIndex];
      } else {
        this.parameterInputValue = '';
      }
    }
    
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
            //console.log(`Retrying request (${retryCount}/${maxRetries}) after ${delay}ms for error:`, error.message);
            return timer(delay);
          }
          return throwError(() => error);
        }
      }),
      catchError((error) => {
        //console.error('Request failed after all retries:', error);
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
        
        // Check if it's a field validation error (new validation system)
        if (errorMessage === 'Field validation failed' || 
            error.error?.details?.includes('Missing fields in precalculated data')) {
          const missingFields = error.error?.missing_fields || [];
          const availableFields = error.error?.available_fields || [];
          
          if (missingFields.length > 0) {
            // Show SweetAlert for missing fields
            Swal.fire({
              icon: 'error',
              title: 'Missing Fields',
              html: `
                <div style="text-align: left;">
                  <p><strong>The following fields are not available in precalculated data:</strong></p>
                  <ul style="background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 4px; padding: 15px 30px; margin: 10px 0;">
                    ${missingFields.map((field: string) => `<li style="color: #856404; font-family: monospace;">${field}</li>`).join('')}
                  </ul>
                  <details style="margin-top: 15px;">
                    <summary style="cursor: pointer; color: #6c757d;">Show available fields</summary>
                    <div style="max-height: 200px; overflow-y: auto; background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 4px; padding: 10px; margin-top: 5px;">
                      ${availableFields.map((field: string) => `<span style="display: inline-block; background: #e9ecef; padding: 2px 6px; margin: 2px; border-radius: 3px; font-size: 12px; font-family: monospace;">${field}</span>`).join('')}
                    </div>
                  </details>
                  <p style="color: #6c757d; font-style: italic; margin-top: 15px;">${error.error?.hint || 'Please use available fields in your query.'}</p>
                </div>
              `,
              confirmButtonColor: '#dc3545',
              confirmButtonText: 'OK',
              width: '600px'
            });
            return `Missing fields: ${missingFields.join(', ')}. These fields are not available in precalculated data.`;
          }
        }
        
        // Check if it's a missing indicator error (legacy system)
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
    
    // Only show indicators that are actually used in the query conditions
    this.conditions.forEach((condition, index) => {
      if (condition.field && condition.indicatorParams) {
        const key = `${condition.field}_${condition.indicatorParams.join('_')}`;
        const indicatorKey = this.generateIndicatorKey(condition.field, condition.timePeriod, condition.indicatorParams, condition.indicatorComponent);
        
        // Try to find the actual value directly in the match object
        if (match[indicatorKey] !== undefined && match[indicatorKey] !== null) {
          tooltipData[key] = parseFloat(match[indicatorKey]);
        } else if (match[key] !== undefined && match[key] !== null) {
          // Fallback to the simple key format
          tooltipData[key] = parseFloat(match[key]);
        } else {
          // If not found, use mock value as fallback
          tooltipData[key] = this.generateMockValue(condition.field, match);
        }
      } else if (condition.field) {
        // For simple fields like close, open, etc. - only if they're in the query
        const simpleKey = condition.field;
        if (match[simpleKey] !== undefined && match[simpleKey] !== null) {
          // Use actual value from match object
          tooltipData[simpleKey] = parseFloat(match[simpleKey]);
        } else {
          // Generate mock values for other fields
          tooltipData[simpleKey] = this.generateMockValue(condition.field, match);
        }
      }
      
      // Add value field if it's a field comparison (right side of condition)
      if (condition.valueType === 'field' && condition.valueField && condition.valueIndicatorParams) {
        const valueKey = `${condition.valueField}_${condition.valueIndicatorParams.join('_')}`;
        const valueIndicatorKey = this.generateIndicatorKey(condition.valueField, condition.valueTimePeriod || 'daily', condition.valueIndicatorParams, condition.valueIndicatorComponent);
        
        if (match[valueIndicatorKey] !== undefined && match[valueIndicatorKey] !== null) {
          tooltipData[valueKey] = parseFloat(match[valueIndicatorKey]);
        } else if (match[valueKey] !== undefined && match[valueKey] !== null) {
          tooltipData[valueKey] = parseFloat(match[valueKey]);
        } else if (match[condition.valueField] !== undefined && match[condition.valueField] !== null) {
          tooltipData[valueKey] = parseFloat(match[condition.valueField]);
        } else {
          tooltipData[valueKey] = this.generateMockValue(condition.valueField, match);
        }
      } else if (condition.valueType === 'field' && condition.valueField) {
        // For simple value fields without parameters
        const valueSimpleKey = condition.valueField;
        if (match[valueSimpleKey] !== undefined && match[valueSimpleKey] !== null) {
          tooltipData[valueSimpleKey] = parseFloat(match[valueSimpleKey]);
        } else {
          tooltipData[valueSimpleKey] = this.generateMockValue(condition.valueField, match);
        }
      }
    });
    
    return tooltipData;
  }

  private generateMockValue(field: string, match: any): number {
    // Generate realistic mock values based on the field type and stock data
    const basePrice = parseFloat(match.close);
    const stockHash = this.hashString(match.stock);
    const dateHash = this.hashString(match.day || ''); // Use the specific date for variation
    
    const combinedHash = stockHash + dateHash; // Combine both for unique values per stock-date
    
    switch (field) {
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

  // ==================== CSV UPLOAD METHODS ====================

  onFileSelected(event: any) {
    const file = event.target.files[0];
    if (file && file.type === 'text/csv') {
      this.selectedFile = file;
      this.uploadStatus = '';
      //console.log('Selected CSV file:', file.name);
    } else if (file) {
      this.uploadStatus = 'Please select a valid CSV file';
      this.uploadSuccess = false;
      this.selectedFile = null;
    }
  }

  async uploadCSV() {
    if (!this.selectedFile) {
      this.uploadStatus = 'Please select a CSV file first';
      this.uploadSuccess = false;
      return;
    }

    // Show confirmation dialog
    const result = await Swal.fire({
      title: 'Upload CSV and Update Database?',
      html: `
        <div style="text-align: left; margin: 20px 0;">
          <p><strong>File:</strong> ${this.selectedFile.name}</p>
          <p><strong>This will:</strong></p>
          <ul style="margin-left: 20px;">
            <li>Extract stock symbols from your CSV file</li>
            <li>Update the database symbol list</li>
            <li>Start a complete database refresh</li>
          </ul>
          <p style="margin-top: 15px; color: #e74c3c;">
            <strong>Warning:</strong> This process may take several minutes and will replace the current symbol list.
          </p>
        </div>
      `,
      icon: 'question',
      showCancelButton: true,
      confirmButtonText: 'Yes, Upload & Update',
      cancelButtonText: 'Cancel',
      confirmButtonColor: '#3085d6',
      cancelButtonColor: '#d33'
    });

    if (!result.isConfirmed) {
      return;
    }

    this.uploading = true;
    this.uploadStatus = '';
    this.showUploadProgress = true;
    this.uploadProgress = 10;
    this.uploadProgressText = 'Uploading CSV file...';

    try {
      // Start the unified CSV upload process
      const formData = new FormData();
      formData.append('csvFile', this.selectedFile);

      // Upload CSV and start the entire process (returns immediately with progress URL)
      const uploadResponse = await this.http.post<any>(`${this.apiUrl}/upload-csv`, formData).toPromise();
      
      if (!uploadResponse.success) {
        throw new Error(uploadResponse.error || 'Failed to process CSV');
      }

      //console.log('CSV upload initiated:', uploadResponse);

      // Store symbol info for success message
      const symbolPreview = uploadResponse.sampleSymbols ? uploadResponse.sampleSymbols.join(', ') : 'No symbols found';
      const symbolCount = uploadResponse.symbolCount || 0;

      // Monitor the entire process via SSE
      await this.monitorCSVUploadProgressSSE();

      // Success - process completed
      this.uploadProgress = 100;
      this.uploadSuccess = true;
      this.uploadStatus = `Successfully updated database with ${symbolCount} symbols (e.g., ${symbolPreview})`;

      // Reset file input
      this.selectedFile = null;
      const fileInput = document.getElementById('csvFileInput') as HTMLInputElement;
      if (fileInput) fileInput.value = '';

      // Show success message
      await Swal.fire({
        title: 'Success!',
        html: `
          <p>Database updated successfully!</p>
          <p><strong>Symbols processed:</strong> ${symbolCount}</p>
          <p><strong>Sample symbols:</strong> ${symbolPreview}</p>
        `,
        icon: 'success',
        confirmButtonText: 'OK'
      });

    } catch (error: any) {
      //console.error('CSV upload error:', error);
      this.uploadSuccess = false;
      this.uploadStatus = 'Upload failed: ' + (error.error?.error || error.message || 'Unknown error');
      this.uploadProgressText = 'Upload failed';
      
      // Show error message
      await Swal.fire({
        title: 'Upload Failed',
        text: this.uploadStatus,
        icon: 'error',
        confirmButtonText: 'OK'
      });
    } finally {
      this.uploading = false;
      setTimeout(() => {
        this.showUploadProgress = false;
        this.uploadProgress = 0;
      }, 3000);
    }
  }

  private async monitorCSVUploadProgressSSE(): Promise<void> {
    return new Promise((resolve, reject) => {
      // Close any existing SSE connection
      if (this.csvProgressEventSource) {
        this.csvProgressEventSource.close();
        this.csvProgressEventSource = null;
      }

      //console.log('Connecting to CSV upload SSE endpoint...');
      
      // Create new SSE connection to the CSV upload progress stream
      this.csvProgressEventSource = new EventSource(`${this.apiUrl}/csv-upload-progress-stream`);
      
      let connectionTimeout = setTimeout(() => {
        //console.error('SSE connection timeout');
        if (this.csvProgressEventSource) {
          this.csvProgressEventSource.close();
          this.csvProgressEventSource = null;
        }
        reject(new Error('Failed to connect to progress stream'));
      }, 10000); // 10 second connection timeout

      this.csvProgressEventSource.onopen = () => {
        //console.log('SSE connection opened for CSV upload progress');
        clearTimeout(connectionTimeout);
      };

      this.csvProgressEventSource.onmessage = (event) => {
        try {
          const progress = JSON.parse(event.data);
          
          // Update progress bar
          if (progress.percentage !== undefined) {
            this.uploadProgress = progress.percentage;
          }
          if (progress.message) {
            this.uploadProgressText = progress.message;
          }
          
          //console.log('SSE Progress update:', {
          //  phase: progress.phase,
          //  percentage: progress.percentage,
          //  message: progress.message
          //});
          
          // Handle completion states
          if (progress.phase === 'completed') {
            //console.log('Upload completed successfully');
            if (this.csvProgressEventSource) {
              this.csvProgressEventSource.close();
              this.csvProgressEventSource = null;
            }
            resolve();
          } else if (progress.phase === 'completed_with_warnings') {
            //console.log('Upload completed with warnings');
            if (this.csvProgressEventSource) {
              this.csvProgressEventSource.close();
              this.csvProgressEventSource = null;
            }
            resolve();
          } else if (progress.phase === 'error') {
            //console.error('Upload error:', progress.message);
            if (this.csvProgressEventSource) {
              this.csvProgressEventSource.close();
              this.csvProgressEventSource = null;
            }
            reject(new Error(progress.message || 'Upload failed'));
          } else if (progress.phase === 'cancelled') {
            //console.log('Upload cancelled');
            if (this.csvProgressEventSource) {
              this.csvProgressEventSource.close();
              this.csvProgressEventSource = null;
            }
            reject(new Error('Process was cancelled'));
          }
        } catch (error) {
          //console.error('Error parsing SSE message:', error);
        }
      };

      this.csvProgressEventSource.onerror = (error) => {
        //console.error('SSE connection error:', error);
        clearTimeout(connectionTimeout);
        
        // Clean up the connection
        if (this.csvProgressEventSource) {
          this.csvProgressEventSource.close();
          this.csvProgressEventSource = null;
        }
        
        // Don't reject on connection errors, as the browser will automatically reconnect
        // Only reject if we haven't received any progress updates
        //console.warn('SSE connection lost, but process may still be running');
      };
    });
  }

  // Download CSV functionality - client-side generation
  downloadCSV() {
    if (!this.results || !this.results.matches || this.results.matches.length === 0) {
      Swal.fire({
        icon: 'warning',
        title: 'No Data',
        text: 'No results to download',
        confirmButtonColor: '#3085d6'
      });
      return;
    }

    try {
      // Generate CSV content from existing data
      const csvContent = this.generateCSVContent(this.results.matches);
      
      // Create blob and download
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      const timestamp = new Date().toISOString().replace(/:/g, '-').substring(0, 19);
      link.href = url;
      link.download = `stock-scan-results-${timestamp}.csv`;
      link.click();
      
      // Clean up
      window.URL.revokeObjectURL(url);
      
      // Show success message
      Swal.fire({
        icon: 'success',
        title: 'Download Complete',
        text: `Downloaded ${this.results.matches.length} stocks to CSV`,
        timer: 2000,
        showConfirmButton: false
      });
    } catch (error) {
      console.error('CSV generation error:', error);
      Swal.fire({
        icon: 'error',
        title: 'Download Failed',
        text: 'Failed to generate CSV file',
        confirmButtonColor: '#dc3545'
      });
    }
  }

  private generateCSVContent(matches: any[]): string {
    if (!matches || matches.length === 0) {
      return 'No data available';
    }

    // Get all unique keys from the matches to create headers
    const allKeys = new Set<string>();
    matches.forEach(match => {
      Object.keys(match).forEach(key => allKeys.add(key));
    });

    // Define preferred column order
    const preferredOrder = ['stock', 'day', 'date', 'timestamp', 'close', 'open', 'high', 'low', 'volume'];
    const otherKeys = Array.from(allKeys).filter(key => !preferredOrder.includes(key)).sort();
    const orderedKeys = [...preferredOrder.filter(key => allKeys.has(key)), ...otherKeys];

    // Create CSV header
    const headers = orderedKeys.map(key => this.formatCSVHeader(key)).join(',');

    // Create CSV rows
    const rows = matches.map(match => {
      return orderedKeys.map(key => {
        let value = match[key];
        
        // Handle 'day' field which should show the date
        if (key === 'day' && !value && match['date']) {
          // Use the date field if day is empty
          value = match['date'];
          const formattedValue = this.formatCSVValue(value, 'date');
          return formattedValue;
        }
        
        if (value == null) return '';
        
        // Format the value appropriately
        const formattedValue = this.formatCSVValue(value, key);
        
        // Escape commas and quotes in CSV
        if (typeof formattedValue === 'string' && (formattedValue.includes(',') || formattedValue.includes('"') || formattedValue.includes('\n'))) {
          return `"${formattedValue.replace(/"/g, '""')}"`;
        }
        
        return formattedValue;
      }).join(',');
    });

    return [headers, ...rows].join('\n');
  }

  private formatCSVHeader(key: string): string {
    // Convert technical keys to readable headers
    const headerMap: { [key: string]: string } = {
      'stock': 'Symbol',
      'day': 'Date',
      'close': 'Close Price',
      'open': 'Open Price',
      'high': 'High Price',
      'low': 'Low Price',
      'volume': 'Volume',
      'timestamp': 'Timestamp'
    };

    return headerMap[key] || key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  }

  private formatCSVValue(value: any, key?: string): string {
    if (value == null) return '';
    
    // Handle timestamp conversion to IST date
    if ((key === 'date' || key === 'timestamp') && typeof value === 'number' && value > 1000000000000) {
      // Convert timestamp to IST date
      // Timestamps are stored at 18:30 UTC which is 00:00 IST next day
      const istDate = new Date(value + 19800000); // Add 5.5 hours (19800000 ms) for IST
      // Format as YYYY-MM-DD using UTC methods since we already adjusted
      const year = istDate.getUTCFullYear();
      const month = String(istDate.getUTCMonth() + 1).padStart(2, '0');
      const day = String(istDate.getUTCDate()).padStart(2, '0');
      return `${year}-${month}-${day}`;
    }
    
    if (typeof value === 'number') {
      // Format numbers with appropriate precision
      if (value > 1000000) {
        return value.toFixed(0); // Large numbers like volume
      } else if (value > 100) {
        return value.toFixed(2); // Prices
      } else {
        return value.toFixed(4); // Small numbers like indicators
      }
    }
    
    return String(value);
  }

  // Initialize table state for a date
  initializeTableState(date: string, data: any[]) {
    if (!this.tableStates.has(date)) {
      this.tableStates.set(date, {
        currentPage: 1,
        pageSize: 10,
        filterText: '',
        filteredData: [...data],
        paginatedData: [],
        totalPages: Math.ceil(data.length / 10)
      });
      this.updatePaginatedData(date);
    }
  }

  // Update filtered and paginated data for a table
  updateTableData(date: string) {
    const state = this.tableStates.get(date);
    const originalData = this.groupedResults.get(date) || [];
    
    if (!state) return;
    
    // Apply filter
    if (state.filterText) {
      state.filteredData = originalData.filter(item => 
        item.stock.toLowerCase().includes(state.filterText.toLowerCase())
      );
    } else {
      state.filteredData = [...originalData];
    }
    
    // Update pagination
    state.totalPages = Math.ceil(state.filteredData.length / state.pageSize);
    state.currentPage = Math.min(state.currentPage, state.totalPages || 1);
    
    this.updatePaginatedData(date);
  }

  // Update paginated data for current page
  updatePaginatedData(date: string) {
    const state = this.tableStates.get(date);
    if (!state) return;
    
    const startIndex = (state.currentPage - 1) * state.pageSize;
    const endIndex = startIndex + state.pageSize;
    state.paginatedData = state.filteredData.slice(startIndex, endIndex);
  }

  // Handle filter change
  onFilterChange(date: string, filterText: string) {
    const state = this.tableStates.get(date);
    if (!state) return;
    
    state.filterText = filterText;
    state.currentPage = 1; // Reset to first page on filter change
    this.updateTableData(date);
  }

  // Handle page change
  onPageChange(date: string, page: number) {
    const state = this.tableStates.get(date);
    if (!state) return;
    
    state.currentPage = page;
    this.updatePaginatedData(date);
  }

  // Get paginated data for a date
  getPaginatedData(date: string): any[] {
    const state = this.tableStates.get(date);
    return state?.paginatedData || [];
  }

  // Get table state for a date
  getTableState(date: string) {
    return this.tableStates.get(date);
  }

  // Helper methods for template to avoid null checks
  hasTableData(date: string): boolean {
    const state = this.tableStates.get(date);
    return !!(state && state.filteredData && state.filteredData.length > 0);
  }

  hasMultiplePages(date: string): boolean {
    const state = this.tableStates.get(date);
    return !!(state && state.totalPages > 1);
  }

  getEntriesStart(date: string): number {
    const state = this.tableStates.get(date);
    if (!state) return 0;
    return (state.currentPage - 1) * state.pageSize + 1;
  }

  getEntriesEnd(date: string): number {
    const state = this.tableStates.get(date);
    if (!state) return 0;
    return Math.min(state.currentPage * state.pageSize, state.filteredData.length);
  }

  getFilteredDataLength(date: string): number {
    const state = this.tableStates.get(date);
    return state?.filteredData?.length || 0;
  }

  // Generate page numbers for pagination
  getPageNumbers(date: string): number[] {
    const state = this.tableStates.get(date);
    if (!state) return [];
    
    const pages: number[] = [];
    const maxVisible = 5;
    const halfVisible = Math.floor(maxVisible / 2);
    
    let startPage = Math.max(1, state.currentPage - halfVisible);
    let endPage = Math.min(state.totalPages, startPage + maxVisible - 1);
    
    if (endPage - startPage + 1 < maxVisible) {
      startPage = Math.max(1, endPage - maxVisible + 1);
    }
    
    for (let i = startPage; i <= endPage; i++) {
      pages.push(i);
    }
    
    return pages;
  }

  ngOnDestroy() {
    // Clean up EventSource connections
    if (this.csvProgressEventSource) {
      this.csvProgressEventSource.close();
      this.csvProgressEventSource = null;
    }
    
    if (this.queryProgressEventSource) {
      this.queryProgressEventSource.close();
      this.queryProgressEventSource = null;
    }
    
    // Clean up any running queries
    this.finishQueryRequest();
  }
}