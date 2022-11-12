import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators, FormArray, FormControl,AbstractControl} from '@angular/forms';
import { Router, ActivatedRoute } from '@angular/router';

// SERVICES
import {LoginService} from '../providers/auth/login.service';

@Component({
  selector: 'app-forget-password',
  templateUrl: './forget-password.component.html',
  styleUrls: ['./forget-password.component.css']
})
export class ForgetPasswordComponent implements OnInit {
  forgetpasswordForm:FormGroup;
  submitted: boolean = false;
  response_msg:any;
  constructor(
    private formBuilder: FormBuilder,
    private router: Router,
    private route: ActivatedRoute,
    public loginService: LoginService,
  )
  {
    this.forgetpasswordForm = this.formBuilder.group({
      email: ['',Validators.required],
    });
  }

  public hasError = (controlName: string, errorName: string) => {
    return this.forgetpasswordForm.controls[controlName].hasError(errorName);
  };

  ngOnInit(): void {
  }

  onSubmit()
  {
    this.submitted = true;
    let obj = this.forgetpasswordForm.value;
    if (this.forgetpasswordForm.invalid) {
      return;
    }

    this.loginService.forgetPassword(obj).subscribe(
      (response) => {
        if (response.code == 200) 
        {
          this.response_msg = 'Please Check Mail';
        }
        else if(response.code == 400)
        {
          
        }
      },
    );

  }

}
