import{store}from'../stores/business.js';import{esc,num}from'../utils/format.js';import{resultPanel}from'../components/common/report.js';import{badge,calcBadge}from'../components/common/status.js';import{notice}from'../components/common/notice.js';import{table}from'../components/common/table.js';import{GROUPS,ACTUAL_GROUPS}from'../constants/enums.js';
export function selectedPlanId(){const saved=+sessionStorage.getItem('tutor-wb-plan');return store.plans.some(p=>p.id===saved)?saved:store.plans[0]?.id;}
const latestCalc=pid=>store.calculations.find(c=>c.plan_id===pid);
const usableCalc=pid=>store.calculations.find(c=>c.plan_id===pid&&c.status==='available'&&!c.stale);
export const detailCalcFor=pid=>store.calculations.find(c=>c.plan_id===pid&&c.status==='available');
export function workbenchPage(){
 const pid=selectedPlanId(),plan=store.plans.find(p=>p.id===pid),calc=latestCalc(pid),usable=usableCalc(pid);
 const planOptions=store.plans.map(p=>`<option value=${p.id} ${p.id===pid?'selected':''}>${esc(p.title)} · ${esc(p.campus)}</option>`).join('');
 return `<header class=page-head><div><span class=eyebrow>04 / STATISTICAL WORKBENCH</span><h1>检验工作台</h1><p>先按观察期核算签到时长并划分实际辅导组，再按实际辅导量发起 Welch 检验。</p></div></header>
<div class=run-bar><form id=plan-pick><label>研究方案<select id=workbench-plan>${planOptions}</select></label></form><div><span class=eyebrow>分析约定</span><p>双侧检验 · 95% 置信区间<br>有效样本每组至少 2 条</p></div></div>
<div class=section-title><h2>① 时长核算</h2><span>${plan?`观察期 ${esc(plan.obs_start_date||'未登记')} 至 ${esc(plan.obs_end_date||'')} · 门槛 ≥ ${plan.threshold_minutes} 分钟`:''}</span></div>
<div class=run-bar><form id=calc-form><label>按当前签到与成绩重算时长，划分实际辅导组。重试为全量重算，不会重复计时。</label><button class=primary ${store.user.role==='viewer'?'disabled':''}>发起时长核算 →</button></form><div>${calc?calcStatusCard(calc):'<p class=muted>该方案尚未核算。</p>'}</div></div>
<div id=calc-detail>${calc?'<p class=muted>正在载入有效时段与分组依据…</p>':''}</div>
<div class=section-title><h2>② 按实际辅导量的检验</h2><span>${usable?`依据核算 № ${usable.id} · 源数据版本 v${usable.source_version}`:'需要一份可用核算'}</span></div>
<div class=run-bar><form id=run-form><label>${usable?`以核算 № ${usable.id} 的实际辅导组 / 实际对照组执行 Welch 检验。`:'当前没有可用核算：请先完成时长核算，或等待进行中的核算完成。'}</label><button class=primary ${store.user.role==='viewer'||!usable?'disabled':''}>发起检验 →</button></form><div><span class=eyebrow>失效约定</span><p>签到、成绩或方案口径更新后<br>检验失效并拒绝签核，重算后恢复</p></div></div>
<section id=latest-result class=result-sheet>${resultPanel(store.reports.find(r=>r.plan_id===pid)||null)}</section>
<div class=section-title><h2>计算记录</h2><span>结果快照不随源数据修订而改变，但会标记失效</span></div>
<div class=run-history>${store.reports.map(r=>`<button class=history-entry data-report=${r.id}>№ ${r.id}　${esc(store.plans.find(p=>p.id===r.plan_id)?.title||'方案')} ${badge(r.status,r.stale)}${r.calculation_id?`<small>核算 № ${r.calculation_id}</small>`:'<small>报名分组口径</small>'}<small>${esc(r.created_at.slice(0,19).replace('T',' '))} UTC</small></button>`).join('')}</div>
${notice('失败任务保留原因。核算或检验失效时，重新核算后再发起检验即可恢复签核。')}`;
}
function calcStatusCard(calc){
 const s=calc.summary||{};
 return `<div class=calc-status>${calcBadge(calc.status,calc.stale)} <b>核算 № ${calc.id}</b> <small>${esc(calc.created_at.slice(0,19).replace('T',' '))} UTC</small>${calc.status==='available'?`<div class=calc-grid><div><label>实际辅导组</label><strong>${s.actual_intervention??'—'}</strong></div><div><label>实际对照组</label><strong>${s.actual_control??'—'}</strong></div><div><label>覆盖学员</label><strong>${s.with_time??'—'} / ${s.total_students??'—'}</strong></div><div><label>累计分钟</label><strong>${num(s.total_minutes,0)}</strong></div><div><label>源数据版本</label><strong>v${calc.source_version} / v${calc.current_version}</strong></div></div>`:''}${calc.status==='failed'?`<p class=muted>${esc(calc.error)}</p>`:''}${calc.status==='available'?`<button class=text-btn data-export-calc=${calc.id}>导出可复算核算 JSON ↓</button>`:''}</div>`;
}
export function calcDetailTable(calc){
 if(!calc||!calc.result)return '';
 const r=calc.result;
 const rows=r.students.map(s=>[`<b>${esc(s.code)}</b><small>${esc(s.name)}</small>`,esc(s.campus),esc(GROUPS[s.reg_group]||s.reg_group),num(s.minutes,1),`<span class="badge ${s.actual_group==='actual_intervention'?'available':''}">${ACTUAL_GROUPS[s.actual_group]}</span>`,s.intervals.length?`<details class=intervals><summary>${s.intervals.length} 段有效时段</summary><ul>${s.intervals.map(i=>`<li>${esc(i.start.slice(0,16).replace('T',' '))} → ${esc(i.end.slice(0,16).replace('T',' '))}（${num(i.minutes,1)} 分钟，来源记录 ${i.sources.map(id=>'№'+id).join('/')}）</li>`).join('')}</ul></details>`:'<span class=muted>观察期内无有效时段</span>']);
 return `<div class=section-title><h2>有效时段与分组依据</h2><span>核算 № ${calc.id} · ${calc.stale?'已失效 · 源数据已更新':'当前可用'} · 校验码 ${esc(r.checksum.slice(0,16))}…</span></div><p class=method>${esc(r.method)}</p>${table(['学号 / 姓名','教学点','报名分组','有效分钟','实际分组','有效时段（观察期内）'],rows)}`;
}
