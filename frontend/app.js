const $ = (selector) => document.querySelector(selector);
let selectedTask = null;
let pollTimer = null;

const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
const short = (value, length=12) => value ? String(value).slice(0,length) : "—";
const badge = (value) => `<span class="badge ${escapeHtml(value)}">${escapeHtml(value)}</span>`;

async function api(url, options={}) {
  const response = await fetch(url, {headers:{"Content-Type":"application/json", ...(options.headers||{})}, ...options});
  if (!response.ok) { const body = await response.json().catch(()=>({})); throw new Error(body.detail || `请求失败 (${response.status})`); }
  return response.json();
}

async function loadTasks() {
  const data = await api('/api/tasks?limit=50');
  $('#task-list').innerHTML = data.items.length ? data.items.map((task) => `
    <button class="task" data-id="${task.task_id}"><span class="task-top"><strong>${escapeHtml(task.repo_url.replace(/^https:\/\//,''))}</strong>${badge(task.status)}</span><span class="meta"><span>${escapeHtml(task.requested_ref)}</span><span>${escapeHtml(task.stage)}</span><span>${new Date(task.created_at).toLocaleString()}</span></span></button>`).join('') : '<div class="empty">还没有审查任务</div>';
  document.querySelectorAll('.task').forEach((item) => item.addEventListener('click', () => loadTask(item.dataset.id)));
}

function renderFindings(task) {
  const filter = $('#severity-filter').value;
  const findings = (task.result?.findings || []).filter((item) => filter === 'all' || item.severity === filter);
  $('#findings').innerHTML = findings.length ? findings.map((item) => `
    <article class="finding severity-${escapeHtml(item.severity)}"><div class="task-top"><h3>${escapeHtml(item.title)}</h3>${badge(item.severity)}</div><p><code>${escapeHtml(item.rule_id)}</code> · ${escapeHtml(item.file || 'repository')}${item.line ? `:${item.line}` : ''}</p><p>${escapeHtml(item.message)}</p>${item.remediation ? `<p><strong>建议：</strong>${escapeHtml(item.remediation)}</p>` : ''}</article>`).join('') : '<div class="empty">当前筛选条件下没有风险项</div>';
}

async function loadTask(id) {
  selectedTask = await api(`/api/tasks/${id}`);
  const task = selectedTask; const decision = task.result?.decision?.decision || '等待结论';
  $('#detail-panel').classList.remove('hidden');
  $('#task-overview').innerHTML = `<div class="metric"><span>任务状态</span><strong>${badge(task.status)} ${escapeHtml(task.stage)}</strong></div><div class="metric"><span>最终结论</span><strong>${escapeHtml(decision)}</strong></div><div class="metric"><span>提交版本</span><strong>${escapeHtml(short(task.resolved_commit))}</strong></div><div class="metric"><span>风险数量</span><strong>${task.result?.summary?.total_findings ?? 0}</strong></div>`;
  $('#download-md').href = `/api/tasks/${id}/report?format=markdown`; $('#download-json').href = `/api/tasks/${id}/report?format=json`;
  $('#retry').classList.toggle('hidden', task.status !== 'failed'); renderFindings(task);
  clearTimeout(pollTimer); if (['pending','running'].includes(task.status)) pollTimer = setTimeout(() => { loadTask(id); loadTasks(); }, 2500);
}

$('#review-form').addEventListener('submit', async (event) => { event.preventDefault(); const button = event.submitter; button.disabled=true; $('#form-message').textContent='正在创建任务…'; try { const body={repo_url:$('#repo-url').value.trim(),ref:$('#repo-ref').value.trim(),deploy_type:$('#deploy-type').value,description:$('#description').value.trim()}; const task=await api('/api/submit',{method:'POST',body:JSON.stringify(body)}); $('#form-message').textContent=`任务已创建：${task.task_id}`; await loadTasks(); await loadTask(task.task_id); } catch(error) { $('#form-message').textContent=error.message; } finally { button.disabled=false; } });
$('#refresh').addEventListener('click', loadTasks); $('#severity-filter').addEventListener('change', () => selectedTask && renderFindings(selectedTask));
$('#retry').addEventListener('click', async () => { if (!selectedTask) return; await api(`/api/tasks/${selectedTask.task_id}/retry`,{method:'POST'}); await loadTask(selectedTask.task_id); await loadTasks(); });
loadTasks().catch((error) => { $('#task-list').innerHTML=`<div class="empty">${escapeHtml(error.message)}</div>`; });
