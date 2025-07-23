import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

interface QueryError {
  type: 'missing_indicators' | 'validation' | 'server' | 'network';
  message: string;
  details?: string;
  missingIndicators?: string[];
  timestamp?: Date;
}

@Injectable({
  providedIn: 'root'
})
export class QueryErrorService {
  private errorSubject = new BehaviorSubject<QueryError | null>(null);
  public error$ = this.errorSubject.asObservable();

  constructor() {}

  setError(error: QueryError) {
    this.errorSubject.next({
      ...error,
      timestamp: new Date()
    });
  }

  clearError() {
    this.errorSubject.next(null);
  }

  setMissingIndicatorsError(missingIndicators: string[], details?: string) {
    this.setError({
      type: 'missing_indicators',
      message: 'Missing precalculated indicators required for this query',
      details: details || 'Please go to the Indicators tab and add the missing indicators, then calculate them before running this query.',
      missingIndicators: missingIndicators
    });
  }

  setValidationError(message: string, details?: string) {
    this.setError({
      type: 'validation',
      message: message,
      details: details
    });
  }

  setServerError(message: string, details?: string) {
    this.setError({
      type: 'server',
      message: message,
      details: details
    });
  }

  setNetworkError(message: string, details?: string) {
    this.setError({
      type: 'network',
      message: message,
      details: details
    });
  }

  getCurrentError(): QueryError | null {
    return this.errorSubject.value;
  }
}