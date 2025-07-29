import { Injectable, NgZone } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, interval, Subject, Subscription } from 'rxjs';
import { takeUntil } from 'rxjs/operators';

export interface SchedulerState {
  isRunning: boolean;
  isMarketHours: boolean;
  forceRun: boolean;
  updateInterval: number;
  lastUpdateTime: Date | null;
  nextUpdateTime: Date | null;
  timeToNextUpdate: number;
  progressPercentage: number;
  updateStats: {
    total: number;
    updated: number;
    unchanged: number;
    errors: number;
  } | null;
  isUpdating: boolean;
}

@Injectable({
  providedIn: 'root'
})
export class SchedulerService {
  private apiUrl = 'http://127.0.0.1:8001';
  private destroy$ = new Subject<void>();
  private sseConnection?: EventSource;
  private timerSubscription?: Subscription;
  
  // Observable state
  private stateSubject = new BehaviorSubject<SchedulerState>({
    isRunning: false,
    isMarketHours: false,
    forceRun: true,
    updateInterval: 2,
    lastUpdateTime: null,
    nextUpdateTime: null,
    timeToNextUpdate: 0,
    progressPercentage: 0,
    updateStats: null,
    isUpdating: false
  });
  
  state$ = this.stateSubject.asObservable();
  
  constructor(
    private http: HttpClient,
    private ngZone: NgZone
  ) {
    this.initializeService();
  }
  
  private initializeService() {
    // Check initial status
    this.checkStatus();
    
    // Start timer for countdown
    this.startTimer();
    
    // Setup SSE connection
    this.setupSSEConnection();
  }
  
  private startTimer() {
    this.timerSubscription = interval(1000)
      .pipe(takeUntil(this.destroy$))
      .subscribe(() => {
        this.ngZone.run(() => {
          this.updateTimerState();
        });
      });
  }
  
  private updateTimerState() {
    const state = this.stateSubject.value;
    const now = new Date();
    
    // Check market hours
    const hours = now.getHours();
    const minutes = now.getMinutes();
    const day = now.getDay();
    
    const isMarketHours = day >= 1 && day <= 5 && 
      ((hours === 9 && minutes >= 15) || (hours > 9 && hours < 15) || 
       (hours === 15 && minutes <= 30));
    
    // Calculate time to next update
    let timeToNextUpdate = 0;
    let progressPercentage = 0;
    
    if (state.isRunning && state.lastUpdateTime) {
      const nextUpdate = new Date(state.lastUpdateTime);
      nextUpdate.setMinutes(nextUpdate.getMinutes() + state.updateInterval);
      
      const timeLeft = Math.max(0, nextUpdate.getTime() - now.getTime());
      timeToNextUpdate = Math.floor(timeLeft / 1000);
      
      const totalInterval = state.updateInterval * 60;
      const elapsed = totalInterval - timeToNextUpdate;
      progressPercentage = Math.min(100, Math.round((elapsed / totalInterval) * 100));
    }
    
    this.stateSubject.next({
      ...state,
      isMarketHours,
      timeToNextUpdate,
      progressPercentage
    });
  }
  
  private setupSSEConnection() {
    this.sseConnection = new EventSource(`${this.apiUrl}/api/scheduler-updates-stream`);
    
    this.sseConnection.onmessage = (event) => {
      this.ngZone.run(() => {
        try {
          const data = JSON.parse(event.data);
          const currentState = this.stateSubject.value;
          
          this.stateSubject.next({
            ...currentState,
            isRunning: data.is_running,
            isMarketHours: data.is_market_hours,
            forceRun: data.force_run ?? currentState.forceRun,
            updateInterval: data.update_interval ?? currentState.updateInterval,
            lastUpdateTime: data.last_update_time ? new Date(data.last_update_time) : currentState.lastUpdateTime,
            updateStats: data.update_stats ?? currentState.updateStats,
            timeToNextUpdate: data.next_update_seconds ?? currentState.timeToNextUpdate
          });
        } catch (error) {
          console.error('SSE data parse error:', error);
        }
      });
    };
    
    this.sseConnection.onerror = (error) => {
      console.error('SSE connection error:', error);
      
      // Reconnect after 5 seconds
      setTimeout(() => {
        this.sseConnection?.close();
        this.setupSSEConnection();
      }, 5000);
    };
  }
  
  checkStatus() {
    this.http.get<any>(`${this.apiUrl}/api/periodic-updates-status`).subscribe(
      status => {
        const currentState = this.stateSubject.value;
        this.stateSubject.next({
          ...currentState,
          isRunning: status.is_running,
          isMarketHours: status.is_market_hours,
          forceRun: status.force_run ?? currentState.forceRun,
          updateInterval: status.update_interval ?? currentState.updateInterval,
          lastUpdateTime: status.last_update_time ? new Date(status.last_update_time) : null
        });
      },
      error => console.error('Failed to check scheduler status:', error)
    );
  }
  
  startScheduler(interval: number = 2, forceRun: boolean = true): Promise<any> {
    const url = `${this.apiUrl}/api/start-periodic-updates?interval_minutes=${interval}&force_run=${forceRun}`;
    
    return this.http.post<any>(url, {}).toPromise().then(response => {
      const currentState = this.stateSubject.value;
      this.stateSubject.next({
        ...currentState,
        isRunning: true,
        updateInterval: interval,
        forceRun: forceRun,
        lastUpdateTime: new Date()
      });
      return response;
    });
  }
  
  stopScheduler(): Promise<any> {
    return this.http.post<any>(`${this.apiUrl}/api/stop-periodic-updates`, {}).toPromise().then(response => {
      const currentState = this.stateSubject.value;
      this.stateSubject.next({
        ...currentState,
        isRunning: false,
        timeToNextUpdate: 0,
        progressPercentage: 0
      });
      return response;
    });
  }
  
  manualUpdate(): Promise<any> {
    const currentState = this.stateSubject.value;
    this.stateSubject.next({
      ...currentState,
      isUpdating: true
    });
    
    return this.http.post<any>(`${this.apiUrl}/api/update-latest-candles`, {}).toPromise().then(response => {
      const currentState = this.stateSubject.value;
      this.stateSubject.next({
        ...currentState,
        isUpdating: false,
        lastUpdateTime: new Date(),
        updateStats: response.summary
      });
      return response;
    }).catch(error => {
      const currentState = this.stateSubject.value;
      this.stateSubject.next({
        ...currentState,
        isUpdating: false
      });
      throw error;
    });
  }
  
  destroy() {
    this.destroy$.next();
    this.destroy$.complete();
    this.sseConnection?.close();
    this.timerSubscription?.unsubscribe();
  }
}