import{request,post}from'./client.js';
export const getCheckins=()=>request('/checkins');
export const saveCheckin=(data,id)=>id?request('/checkins/'+id,{method:'PUT',body:JSON.stringify(data)}):post('/checkins',data);
export const revokeCheckin=id=>post(`/checkins/${id}/revoke`,{});
export const restoreCheckin=id=>post(`/checkins/${id}/restore`,{});
