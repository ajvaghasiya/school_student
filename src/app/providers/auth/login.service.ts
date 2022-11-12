import { Injectable } from '@angular/core';
import { catchError } from 'rxjs/operators';
import { HttpClient } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';

import { environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class LoginService {

  constructor(private http: HttpClient){}

  validateLogin = (moreData:any): Observable<any> => {
    const endpoint = environment.baseUrl+'/api/users/frountuserlogin';
    return this.http
      .post(endpoint, moreData, { observe: 'response' as 'body' })
      .pipe(
        catchError((err) => {
          return throwError(err);
        })
      );
  };

  changePassword = (moreData:any): Observable<any> => {
    let endpoint = environment.baseUrl+'/users/changepassword';
    return this.http.post(endpoint, moreData).pipe(
      catchError((err) => {
        return throwError(err);
      })
    );
  };

  forgetPassword = (moreData:any): Observable<any> => {
    let endpoint = environment.baseUrl+'/api/users/forgetpass';
    return this.http.post(endpoint, moreData).pipe(
      catchError((err) => {
        return throwError(err);
      })
    );
  };

}
