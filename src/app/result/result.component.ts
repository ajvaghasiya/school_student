import { Component, OnInit } from '@angular/core';
import { Router, ActivatedRoute } from '@angular/router';

// SERVICES
import {ResultService} from '../providers/result/result.service';

declare var jQuery: any;
declare var $: any;
@Component({
  selector: 'app-result',
  templateUrl: './result.component.html',
  styleUrls: ['./result.component.css']
})
export class ResultComponent implements OnInit {
  examData: any;
  token: any;
  element:any;
  constructor(
    private router: Router,
    private resultService:ResultService,
  )
  { 
    this.token = localStorage.getItem('token');
  }

  ngOnInit(): void {
    this.get_examdata();
  }

  clickSub(element:any){
    jQuery(document).ready(function () {   
      jQuery(".gapcls").removeClass("tableshow");
      jQuery("."+element).addClass("tableshow");
      
     });
  }

  get_examdata()
  { 
    this.resultService.getexamDetails({token:this.token}).subscribe(
        (response)=> {
          if (response.code == 200) 
          {
            this.examData = response.result;   
          }
        },
      );
  }


}
