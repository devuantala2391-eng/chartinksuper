import { HttpInterceptorFn } from '@angular/common/http';

export const ngrokHeaderInterceptor: HttpInterceptorFn = (req, next) => {
  const modifiedReq = req.clone({
    setHeaders: {
      'ngrok-skip-browser-warning': '69420'
    }
  });
  
  return next(modifiedReq);
};