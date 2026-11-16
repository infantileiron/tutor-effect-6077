export async function downloadJson(path,filename,token){
 const response=await fetch(`/api${path}`,{headers:{Authorization:`Bearer ${token}`}});
 if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.detail||'导出失败，请确认任务已完成');}
 const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export const downloadReport=(id,token)=>downloadJson(`/reports/${id}/export`,`tutor-effect-report-${id}.json`,token);
export const downloadCalculation=(id,token)=>downloadJson(`/calculations/${id}/export`,`tutoring-time-calculation-${id}.json`,token);
