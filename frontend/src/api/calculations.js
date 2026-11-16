import{request,post}from'./client.js';
export const getCalculations=()=>request('/calculations');
export const getCalculation=id=>request('/calculations/'+id);
export const runCalculation=plan_id=>post('/calculations',{plan_id:+plan_id});
