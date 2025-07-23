import { Injectable, ApplicationRef, ComponentRef, createComponent, EnvironmentInjector } from '@angular/core';
import { PopupComponent } from './popup.component';

export interface PopupConfig {
  type: 'field' | 'operator' | 'value' | 'timeframe' | 'indicator-params';
  options?: any[];
  value?: any;
  position: { x: number, y: number };
  callback: (value: any) => void;
}

@Injectable({
  providedIn: 'root'
})
export class PopupService {
  private popupRef: ComponentRef<PopupComponent> | null = null;

  constructor(
    private appRef: ApplicationRef,
    private injector: EnvironmentInjector
  ) {}

  open(config: PopupConfig) {
    this.close(); // Close any existing popup
    
    // Create component
    this.popupRef = createComponent(PopupComponent, {
      environmentInjector: this.injector
    });
    
    // Set config
    this.popupRef.instance.config = config;
    this.popupRef.instance.closed.subscribe(() => this.close());
    
    // Attach to DOM
    this.appRef.attachView(this.popupRef.hostView);
    document.body.appendChild(this.popupRef.location.nativeElement);
    
    // Position popup
    const element = this.popupRef.location.nativeElement;
    element.style.position = 'absolute';
    element.style.left = `${config.position.x}px`;
    element.style.top = `${config.position.y}px`;
    element.style.zIndex = '9999';
  }

  close() {
    if (this.popupRef) {
      this.appRef.detachView(this.popupRef.hostView);
      this.popupRef.destroy();
      this.popupRef = null;
    }
  }
}