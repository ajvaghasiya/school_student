import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators, FormArray, FormControl,AbstractControl} from '@angular/forms';
import { Router, ActivatedRoute } from '@angular/router';

// SERVICES
import {LoginService} from '../providers/auth/login.service';

@Component({
  selector: 'app-change-password',
  templateUrl: './change-password.component.html',
  styleUrls: ['./change-password.component.css']
})
export class ChangePasswordComponent implements OnInit {
  passwordForm:FormGroup;
  submitted: boolean = false;
  token = localStorage.getItem('token');
  showmsg: any;
  constructor(
    private formBuilder: FormBuilder,
    private router: Router,
    private route: ActivatedRoute,
    public loginService: LoginService,
  ) 
  { 
    this.passwordForm = this.formBuilder.group({
      old_password: ['',Validators.required],
      new_password: ['',Validators.required],
      confirm_password: ['',Validators.required],
      token:[this.token]
    });
  }
  
  public hasError = (controlName: string, errorName: string) => {
    return this.passwordForm.controls[controlName].hasError(errorName);
  };

  ngOnInit(): void {
  }

  onSubmit()
  {
    this.submitted = true;
    let obj = this.passwordForm.value;
    if (this.passwordForm.invalid) {
      return;
    }

    this.loginService.changePassword(obj).subscribe(
      (response) => {
        if (response.code == 200) 
        {
          this.showmsg = response.message;
        }
        else if(response.code == 400)
        {
          this.showmsg = response.message;
        }
      },
    );

  }

}
