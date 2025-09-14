import { Component, OnInit, OnDestroy, ChangeDetectorRef, NgZone } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpClientModule } from '@angular/common/http';
import { SimpleLoaderComponent } from '../simple-loader.component';
import { environment } from '../../environments/environment';
import Swal from 'sweetalert2';

interface PrecalculatedIndicator {
  timeframe: string;
  name: string;
  params: {
    period?: number;
    stdDev?: number;
    [key: string]: any;
  };
  description?: string;
  id?: string;
}

interface IndicatorResponse {
  success: boolean;
  indicators: PrecalculatedIndicator[];
  status: string;
  lastUpdated: string;
}

@Component({
  selector: 'app-indicators',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule, SimpleLoaderComponent],
  templateUrl: './indicators.component.html',
  styleUrl: './indicators.component.scss'
})
export class IndicatorsComponent implements OnInit, OnDestroy {
  indicators: PrecalculatedIndicator[] = [];
  newIndicator: PrecalculatedIndicator = {
    timeframe: 'daily',
    name: 'supertrend',
    params: { period: 10, multiplier: 3 }
  };
  loading = false;
  error: string | null = null;
  status: string = 'idle';
  lastUpdated: string | null = null;
  // Simple loader properties
  showLoader = false;
  loaderTitle = 'Loading...';
  loaderMessage = 'Please wait while we process your request.';
  private statusInterval: any;

  private apiUrl = environment.apiUrl;

  availableIndicators = [
    { value: 'supertrend', label: 'SuperTrend' },
    { value: 'bb', label: 'Bollinger Bands' },
    { value: 'sma', label: 'Simple Moving Average (SMA)' },
    { value: 'ema', label: 'Exponential Moving Average (EMA)' },
    { value: 'rsi', label: 'Relative Strength Index (RSI)' },
    { value: 'atr', label: 'Average True Range (ATR)' },
    { value: 'pctchg', label: '% Change' },
    { value: 'volume', label: 'Volume' }
  ];

  availableTimeframes = [
    { value: 'daily', label: 'Daily' },
    { value: 'weekly', label: 'Weekly' },
    { value: 'monthly', label: 'Monthly' }
  ];

  constructor(
    private http: HttpClient,
    private cdr: ChangeDetectorRef,
    private ngZone: NgZone
  ) {}

  ngOnInit() {
    this.loadIndicators();
    // Ensure initial parameters are set correctly
    this.onIndicatorTypeChange();
  }

  ngOnDestroy() {
    this.clearIntervals();
  }

  private clearIntervals() {
    if (this.statusInterval) {
      clearInterval(this.statusInterval);
      this.statusInterval = null;
    }
  }

  loadIndicators() {
    this.loading = true;
    this.error = null;
    
    this.http.get<IndicatorResponse>(`${this.apiUrl}/get-precalculated-indicators`, {
      headers: {
        'ngrok-skip-browser-warning': '69420'
      }
    })
      .subscribe({
        next: (response) => {
          this.indicators = response.indicators || [];
          this.status = response.status;
          this.lastUpdated = response.lastUpdated;
          this.loading = false;
        },
        error: (error) => {
          this.error = 'Failed to load indicators: ' + error.message;
          this.loading = false;
        }
      });
  }

  addIndicator() {
    // Ensure numeric parameters are properly typed
    if (this.newIndicator.name === 'supertrend') {
      // Ensure multiplier is a number (not string) and preserve decimals
      if (this.newIndicator.params['multiplier'] !== undefined) {
        this.newIndicator.params['multiplier'] = Number(this.newIndicator.params['multiplier']);
      }
    }
    
    // Validate the indicator before adding
    const validationError = this.validateIndicator(this.newIndicator);
    if (validationError) {
      this.error = validationError;
      return;
    }

    // Check for duplicates
    const isDuplicate = this.indicators.some(existing => 
      existing.timeframe === this.newIndicator.timeframe &&
      existing.name === this.newIndicator.name &&
      JSON.stringify(existing.params) === JSON.stringify(this.newIndicator.params)
    );

    if (isDuplicate) {
      this.error = 'This indicator configuration already exists.';
      return;
    }

    // Create a copy of the new indicator with a unique ID
    const indicatorToAdd = {
      ...this.newIndicator,
      id: Date.now().toString(),
      description: this.getIndicatorDescription(this.newIndicator)
    };

    this.indicators.push(indicatorToAdd);
    this.error = null; // Clear any previous errors
    
    // Reset form
    this.newIndicator = {
      timeframe: 'daily',
      name: 'supertrend',
      params: { period: 10, multiplier: 3 }
    };
  }

  validateIndicator(indicator: PrecalculatedIndicator): string | null {
    // Basic validation
    if (!indicator.timeframe || !indicator.name) {
      return 'Please select both timeframe and indicator type.';
    }

    // Parameter validation for indicators that require a period
    if (!['volume', 'pctchg'].includes(indicator.name)) {
      const period = indicator.params['period'];
      if (!period || isNaN(Number(period)) || Number(period) < 0.1) {
        return 'Period must be a positive number (minimum 0.1).';
      }
    }

    // Bollinger Bands specific validation
    if (indicator.name === 'bb') {
      const stdDev = indicator.params['stdDev'];
      if (!stdDev || isNaN(Number(stdDev)) || Number(stdDev) < 0.1) {
        return 'Standard deviation must be a positive number (minimum 0.1).';
      }
    }

    // SuperTrend specific validation
    if (indicator.name === 'supertrend') {
      const multiplier = indicator.params['multiplier'];
      if (!multiplier || isNaN(Number(multiplier)) || Number(multiplier) < 0.1) {
        return 'Multiplier must be a positive number (minimum 0.1).';
      }
    }

    return null;
  }

  removeIndicator(index: number) {
    this.indicators.splice(index, 1);
  }

  getIndicatorDescription(indicator: PrecalculatedIndicator): string {
    const timeframe = indicator.timeframe.charAt(0).toUpperCase() + indicator.timeframe.slice(1);
    const indicatorName = this.availableIndicators.find(i => i.value === indicator.name)?.label || indicator.name;
    
    let paramStr = '';
    if (indicator.params['period']) {
      paramStr += ` ${indicator.params['period']}`;
    }
    if (indicator.params['stdDev']) {
      paramStr += `,${indicator.params['stdDev']}`;
    }
    if (indicator.params['multiplier']) {
      paramStr += `,${indicator.params['multiplier']}`;
    }
    
    return `${timeframe} ${indicatorName}${paramStr}`;
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
    this.showLoader = true;
    this.loaderTitle = 'Hard Refresh';
    this.loaderMessage = 'Refreshing all indicator data...';

    this.http.post<any>(`${this.apiUrl}/api/hard-refresh`, {}, {
      headers: {
        'ngrok-skip-browser-warning': '69420'
      }
    }).subscribe({
      next: (response) => {
        this.loading = false;
        this.showLoader = false;
        this.status = 'idle';
        
        Swal.fire({
          title: 'Hard Refresh Complete!',
          text: response.message || 'Database has been refreshed successfully',
          icon: 'success',
          timer: 3000,
          showConfirmButton: false
        });
        
        // Reload indicators to get fresh data
        this.loadIndicators();
      },
      error: (error) => {
        this.loading = false;
        this.showLoader = false;
        this.status = 'error';
        this.error = 'Failed to complete hard refresh: ' + error.message;
      }
    });
  }

  recalculateIndicators() {
    if (this.indicators.length === 0) {
      this.error = 'No indicators to calculate. Please add at least one indicator.';
      return;
    }

    this.loading = true;
    this.error = null;
    this.showLoader = true;
    this.loaderTitle = 'Calculating Indicators';
    this.loaderMessage = 'Processing indicator calculations...';

    const payload = {
      indicators: this.indicators
    };

    this.http.post<any>(`${this.apiUrl}/precalculate-indicators`, payload, {
      headers: {
        'ngrok-skip-browser-warning': '69420'
      }
    }).subscribe({
        next: (response) => {
          this.loading = false;
          this.showLoader = false;
          this.status = 'idle';
          
          if (response.success) {
            Swal.fire({
              title: 'Calculation Complete!',
              text: 'All indicators have been calculated successfully',
              icon: 'success',
              timer: 3000,
              showConfirmButton: false
            });
            
            // Reload indicators to get fresh data
            this.loadIndicators();
          } else {
            this.error = 'Failed to complete calculation: ' + response.message;
          }
        },
        error: (error) => {
          this.loading = false;
          this.showLoader = false;
          this.status = 'error';
          
          let errorMessage = 'Failed to complete calculation: ';
          if (error.status === 400) {
            errorMessage += error.error?.error || 'Invalid request. Please check your indicators configuration.';
          } else {
            errorMessage += error.message || 'Unknown error occurred';
          }
          this.error = errorMessage;
          
          Swal.fire({
            title: 'Calculation Failed',
            text: errorMessage,
            icon: 'error',
            confirmButtonText: 'OK'
          });
        }
      });
  }

  // Progress polling methods removed - using simple loaders now

  // Polling fallback methods removed - using simple loaders now

  getStatusColor(): string {
    switch (this.status) {
      case 'completed': return 'success';
      case 'processing': return 'warning';
      case 'error': return 'danger';
      default: return 'secondary';
    }
  }

  getStatusText(): string {
    switch (this.status) {
      case 'completed': return 'Completed';
      case 'processing': return 'Processing...';
      case 'error': return 'Error';
      case 'idle': return 'Not Started';
      default: return this.status;
    }
  }

  onIndicatorTypeChange() {
    // Reset params when indicator type changes - completely clear and rebuild
    this.newIndicator.params = {};
    
    switch (this.newIndicator.name) {
      case 'supertrend':
        this.newIndicator.params = { period: 10, multiplier: 3 };
        break;
      case 'bb':
        this.newIndicator.params = { period: 20, stdDev: 2 };
        break;
      case 'sma':
        this.newIndicator.params = { period: 20 };
        break;
      case 'ema':
        this.newIndicator.params = { period: 12 };
        break;
      case 'rsi':
        this.newIndicator.params = { period: 14 };
        break;
      case 'atr':
        this.newIndicator.params = { period: 14 };
        break;
      case 'pctchg':
        this.newIndicator.params = {}; // No parameters needed
        break;
      case 'volume':
        this.newIndicator.params = {}; // No parameters needed
        break;
      default:
        this.newIndicator.params = { period: 14 };
    }
    
    // Force change detection to update the UI
    this.cdr.detectChanges();
  }

  // Helper methods for template logic
  shouldShowPeriod(): boolean {
    return !['volume', 'pctchg'].includes(this.newIndicator.name);
  }

  shouldShowStdDev(): boolean {
    return this.newIndicator.name === 'bb';
  }

  shouldShowMultiplier(): boolean {
    return this.newIndicator.name === 'supertrend';
  }

  getRequiredParameterCount(): number {
    switch (this.newIndicator.name) {
      case 'supertrend':
        return 2; // period + multiplier
      case 'bb':
        return 2; // period + stdDev
      case 'sma':
      case 'ema':
      case 'rsi':
        return 1; // period only
      case 'pctchg':
      case 'volume':
        return 0; // no parameters
      default:
        return 1;
    }
  }
}