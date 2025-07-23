import { Component, OnInit, OnDestroy, ChangeDetectorRef, NgZone } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient, HttpClientModule } from '@angular/common/http';

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
  imports: [CommonModule, FormsModule, HttpClientModule],
  templateUrl: './indicators.component.html',
  styleUrl: './indicators.component.scss'
})
export class IndicatorsComponent implements OnInit, OnDestroy {
  indicators: PrecalculatedIndicator[] = [];
  newIndicator: PrecalculatedIndicator = {
    timeframe: 'daily',
    name: 'rsi',
    params: { period: 14 }
  };
  loading = false;
  error: string | null = null;
  status: string = 'idle';
  lastUpdated: string | null = null;
  progressPercentage: number = 0;
  progressMessage: string = '';
  progressProcessed: number = 0;
  progressTotal: number = 0;
  private statusInterval: any;
  private progressInterval: any;
  private eventSource: EventSource | null = null;

  private apiUrl = 'http://localhost:8001/api';

  availableIndicators = [
    { value: 'rsi', label: 'Relative Strength Index (RSI)' },
    { value: 'supertrend', label: 'SuperTrend' },
    { value: 'bb', label: 'Bollinger Bands' },
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
  }

  ngOnDestroy() {
    this.clearIntervals();
    this.closeEventSource();
  }

  private clearIntervals() {
    if (this.statusInterval) {
      clearInterval(this.statusInterval);
      this.statusInterval = null;
    }
    if (this.progressInterval) {
      clearInterval(this.progressInterval);
      this.progressInterval = null;
    }
  }

  private closeEventSource() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }

  loadIndicators() {
    this.loading = true;
    this.error = null;
    
    this.http.get<IndicatorResponse>(`${this.apiUrl}/get-precalculated-indicators`)
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
      name: 'rsi',
      params: { period: 14 }
    };
  }

  validateIndicator(indicator: PrecalculatedIndicator): string | null {
    // Basic validation
    if (!indicator.timeframe || !indicator.name) {
      return 'Please select both timeframe and indicator type.';
    }

    // Parameter validation
    if (indicator.name !== 'volume') {
      if (!indicator.params['period'] || indicator.params['period'] < 1) {
        return 'Period must be a positive number.';
      }
      if (indicator.params['period'] > 200) {
        return 'Period cannot exceed 200.';
      }
    }

    // Bollinger Bands specific validation
    if (indicator.name === 'bb') {
      if (!indicator.params['stdDev'] || indicator.params['stdDev'] < 0.1 || indicator.params['stdDev'] > 5) {
        return 'Standard deviation must be between 0.1 and 5.';
      }
    }

    // SuperTrend specific validation
    if (indicator.name === 'supertrend') {
      if (!indicator.params['multiplier'] || indicator.params['multiplier'] < 0.1 || indicator.params['multiplier'] > 10) {
        return 'Multiplier must be between 0.1 and 10.';
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

  recalculateIndicators() {
    if (this.indicators.length === 0) {
      this.error = 'No indicators to calculate. Please add at least one indicator.';
      return;
    }

    this.loading = true;
    this.error = null;
    this.status = 'processing';
    this.progressPercentage = 0;
    this.progressMessage = 'Starting calculation...';
    this.progressProcessed = 0;
    this.progressTotal = 0;
    this.clearIntervals(); // Clear any existing intervals

    const payload = {
      indicators: this.indicators
    };

    this.http.post<any>(`${this.apiUrl}/precalculate-indicators`, payload)
      .subscribe({
        next: (response) => {
          if (response.success) {
            this.status = response.status;
            this.pollStatus();
          } else {
            this.error = 'Failed to start calculation: ' + response.message;
            this.loading = false;
          }
        },
        error: (error) => {
          let errorMessage = 'Failed to start calculation: ';
          if (error.status === 400) {
            errorMessage += error.error?.error || 'Invalid request. Please check your indicators configuration.';
          } else {
            errorMessage += error.message || 'Unknown error occurred';
          }
          this.error = errorMessage;
          this.loading = false;
          this.status = 'error';
          alert(errorMessage); // Show alert to user
        }
      });
  }

  pollStatus() {
    // Clear any existing intervals and SSE connections
    this.clearIntervals();
    this.closeEventSource();
    
    // Set up Server-Sent Events for real-time progress
    this.eventSource = new EventSource(`${this.apiUrl}/progress-stream`);
    
    this.eventSource.onmessage = (event) => {
      // Run inside Angular zone to ensure change detection works
      this.ngZone.run(() => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.connected) {
            //console.log('SSE connection established');
            return;
          }
          
          // Update progress whenever we receive data
          if (data.phase === 'processing_indicators' || (data.isRunning && this.status === 'processing')) {
            this.progressPercentage = data.percentage || 0;
            this.progressMessage = data.message || 'Processing indicators...';
            this.progressProcessed = data.processed || 0;
            this.progressTotal = data.total || 0;
            //console.log('Progress update:', { 
            //  percentage: this.progressPercentage, 
            //  processed: this.progressProcessed, 
            //  total: this.progressTotal 
            //});
          }
        
        // Handle completion status through SSE
        if (data.status === 'completed' && data.phase === 'completed') {
          this.status = 'completed';
          this.loading = false;
          this.progressPercentage = 100;
          this.progressMessage = 'Calculation completed successfully';
          this.lastUpdated = new Date().toISOString();
          this.clearIntervals();
          this.closeEventSource();
          // Reload indicators to get the updated list
          this.loadIndicators();
        }
        
        // Handle error status through SSE
        if (data.status === 'error' && data.phase === 'error') {
          this.status = 'error';
          this.loading = false;
          this.error = data.message || 'Calculation failed. Please try again.';
          this.clearIntervals();
          this.closeEventSource();
        }
      } catch (error) {
        //console.error('Error parsing SSE data:', error);
      }
      });
    };
    
    this.eventSource.onerror = (error) => {
      //console.error('SSE connection error:', error);
      // Fall back to polling if SSE fails
      this.closeEventSource();
      this.setupPollingFallback();
    };
    
    // No need for status polling - we get everything through SSE
    // Only use polling as a fallback if SSE fails
  }

  private setupPollingFallback() {
    // Fallback to polling if SSE fails
    //console.log('SSE failed, falling back to polling');
    
    // Poll for status updates
    this.statusInterval = setInterval(() => {
      this.http.get<IndicatorResponse>(`${this.apiUrl}/get-precalculated-indicators`)
        .subscribe({
          next: (response) => {
            this.status = response.status;
            this.lastUpdated = response.lastUpdated;
            
            if (response.status === 'completed') {
              this.loading = false;
              this.progressPercentage = 100;
              this.progressMessage = 'Calculation completed successfully';
              this.clearIntervals();
              this.loadIndicators();
            } else if (response.status === 'error') {
              this.loading = false;
              this.error = 'Calculation failed. Please try again.';
              this.clearIntervals();
            }
          },
          error: (error) => {
            this.loading = false;
            this.error = 'Failed to get status: ' + error.message;
            this.clearIntervals();
          }
        });
    }, 3000);
    
    // Poll for progress updates
    this.progressInterval = setInterval(() => {
      if (this.status === 'processing') {
        this.http.get<any>('http://localhost:8001/query/progress')
          .subscribe({
            next: (progress) => {
              if (progress.isRunning && progress.phase === 'processing_indicators') {
                this.progressPercentage = Math.min(Math.floor((progress.processed / progress.total) * 100), 100);
                this.progressMessage = progress.message || 'Processing indicators...';
                this.progressProcessed = progress.processed || 0;
                this.progressTotal = progress.total || 0;
              }
            },
            error: (error) => {
              //console.warn('Progress polling error:', error);
            }
          });
      }
    }, 1000);
  }

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
    // Reset params when indicator type changes
    switch (this.newIndicator.name) {
      case 'rsi':
        this.newIndicator.params = { period: 14 };
        break;
      case 'supertrend':
        this.newIndicator.params = { period: 10, multiplier: 3 };
        break;
      case 'bb':
        this.newIndicator.params = { period: 20, stdDev: 2 };
        break;
      case 'pctchg':
        this.newIndicator.params = { period: 1 };
        break;
      case 'volume':
        this.newIndicator.params = {};
        break;
      default:
        this.newIndicator.params = { period: 14 };
    }
  }
}