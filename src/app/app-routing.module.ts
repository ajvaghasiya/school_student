import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { ChangePasswordComponent } from './change-password/change-password.component';
import { HomeComponent } from './home/home.component';
import { LoginComponent } from './login/login.component';
import { NodataFoundComponent } from './nodata-found/nodata-found.component';
import {AuthGuard} from './guard/auth.guard';

import { ForgetPasswordComponent } from './forget-password/forget-password.component';
import { ResultComponent } from './result/result.component';

const routes: Routes = [
  { 
    path:'',
    component:HomeComponent 
  },
  { 
    path:'login',
    component:LoginComponent
  },
  { 
    path:'change-password',
    component:ChangePasswordComponent,
    canActivate: [AuthGuard],
  },
  { 
    path:'forget-password',
    component:ForgetPasswordComponent,
  },
  { 
    path:'result',
    component:ResultComponent,
  },
  {
    path:"**",
    component:NodataFoundComponent
  },
];

@NgModule({
  imports: [RouterModule.forRoot(routes)],
  exports: [RouterModule]
})
export class AppRoutingModule { }
