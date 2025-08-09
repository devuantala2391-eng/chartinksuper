import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: '/screener', pathMatch: 'full' },
  { path: 'screener', loadComponent: () => import('./screener/screener.component').then(m => m.ScreenerComponent) },
  { path: '**', redirectTo: '/screener' }
];
