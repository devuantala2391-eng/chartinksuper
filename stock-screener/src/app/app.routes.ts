import { Routes } from '@angular/router';
import { IndicatorsComponent } from './indicators/indicators.component';

export const routes: Routes = [
  { path: '', redirectTo: '/screener', pathMatch: 'full' },
  { path: 'screener', loadComponent: () => import('./screener/screener.component').then(m => m.ScreenerComponent) },
  { path: 'indicators', component: IndicatorsComponent },
  { path: '**', redirectTo: '/screener' }
];
