import{STATUS,CALC_STATUS}from'../../constants/enums.js';
export const badge=(status,stale=false)=>`<span class="badge ${stale?'stale':status}">${STATUS[stale?'stale':status]||status}</span>`;
export const calcBadge=(status,stale=false)=>`<span class="badge ${stale?'stale':status}">${CALC_STATUS[stale?'stale':status]||status}</span>`;
