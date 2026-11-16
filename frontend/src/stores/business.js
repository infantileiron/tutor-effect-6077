import{getStudents}from'../api/students.js';import{getPlans}from'../api/plans.js';import{getReports}from'../api/reports.js';import{getCheckins}from'../api/checkins.js';import{getCalculations}from'../api/calculations.js';
export const store={students:[],plans:[],reports:[],checkins:[],calculations:[],calcDetails:{},user:null};
export async function refresh(){[store.students,store.plans,store.reports,store.checkins,store.calculations]=await Promise.all([getStudents(),getPlans(),getReports(),getCheckins(),getCalculations()]);}
