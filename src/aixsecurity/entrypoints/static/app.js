'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const state = {projects: [], scans: [], project: null, scan: null, report: null, refreshing: false, page: 'assets', registering: false, scanning: false};
  let registrationRequest = null;
  let scanRequest = null;
  const retryRequests = new Map();
  const labels = {READY: '已就绪', ready: '已就绪', FAILED: '准备失败', failed: '失败', queued: '等待处理', running: '处理中', completed: '已完成', cancelled: '已取消', suspicious: '待确认', rejected: '已排除', confirmed: '已确认', PARTIAL: '部分完成', PREPARING: '准备中'};
  const ready = p => p.preparation_status === 'READY' && Boolean(p.current_snapshot_id);
  const display = value => typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  function el(tag, text, cls) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = String(text);
    if (cls) node.className = cls;
    return node;
  }
  function badge(status) {
    const cls = ['READY', 'ready', 'completed'].includes(status) ? 'good' : ['FAILED', 'failed'].includes(status) ? 'bad' : ['queued', 'running', 'PREPARING'].includes(status) ? 'busy' : '';
    return el('span', labels[status] || status || '未知', `badge ${cls}`);
  }
  function feedback(id, text, error = false) { $(id).textContent = text; $(id).classList.toggle('error', error); }
  function fail(error) { $('global-error').hidden = false; $('global-error').textContent = error.message || '请求失败，请稍后刷新重试。'; }
  async function api(path, body) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', signal: controller.signal,
        headers: body === undefined ? {} : {'Content-Type': 'application/json', 'X-AIxSecurity-Request': '1'},
        body: body === undefined ? undefined : JSON.stringify(body)});
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(typeof data?.error === 'string' ? data.error : `请求未完成（HTTP ${response.status}）`);
      if (data === null) throw new Error('服务响应不是有效的 JSON，请检查本地服务。');
      return data;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('请求超时，结果可能已被服务接收。再次提交会复用同一请求标识。');
      throw error;
    } finally { clearTimeout(timer); }
  }
  function key() { return crypto.randomUUID(); }
  function go(page) {
    state.page = page;
    $('page-assets').hidden = page !== 'assets'; $('page-scans').hidden = page !== 'scans';
    document.querySelectorAll('[data-page]').forEach(button => {
      const active = button.dataset.page === page; button.classList.toggle('active', active);
      if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
    });
  }
  function renderProjects() {
    $('projects').replaceChildren(); $('projects-empty').hidden = state.projects.length !== 0;
    $('project-count').textContent = `${state.projects.length} 个项目`;
    for (const project of state.projects) {
      const row = el('tr'); const name = el('td'); name.append(el('div', project.name, 'row-title'));
      for (const repo of project.repositories || []) name.append(el('div', repo, 'repo'));
      const status = el('td'); status.append(badge(project.preparation_status));
      if (project.error) status.append(el('p', display(project.error), 'feedback error'));
      const version = el('td', project.current_snapshot_id || '尚未发布', 'mono');
      const action = el('td'); const button = el('button', '查看详情', 'text-button');
      button.addEventListener('click', () => showProject(project.id)); action.append(button);
      if (['FAILED', 'CANCELLED'].includes(project.preparation_status)) {
        const retry = el('button', '重试准备', 'text-button');
        if (!retryRequests.has(project.id)) retryRequests.set(project.id, key());
        const requestKey = retryRequests.get(project.id);
        retry.addEventListener('click', async () => { retry.disabled = true; try {
          await api(`/api/projects/${project.id}/retry`, {idempotency_key: requestKey}); retryRequests.delete(project.id); await refresh();
        } catch (error) { fail(error); retry.disabled = false; } }); action.append(retry);
      }
      row.append(name, status, version, action); $('projects').append(row);
    }
    const previous = $('scan-project').value;
    $('scan-project').replaceChildren(el('option', state.projects.some(ready) ? '请选择就绪项目' : '暂无就绪项目，请先完成资产准备'));
    $('scan-project').firstChild.value = '';
    for (const project of state.projects) {
      const option = el('option', `${project.name} — ${labels[project.preparation_status] || project.preparation_status}`);
      option.value = project.id; option.disabled = !ready(project); $('scan-project').append(option);
    }
    if (state.projects.some(p => p.id === previous && ready(p))) $('scan-project').value = previous;
    selectionChanged();
  }
  function selectionChanged() {
    const project = state.projects.find(p => p.id === $('scan-project').value);
    const enabled = project && ready(project);
    $('scan-submit').disabled = !enabled || state.scanning;
    $('scan-selection').textContent = enabled ? `固定资产版本：${project.current_snapshot_id}` : '请选择已经就绪的项目。未就绪资产不会进入扫描。';
  }
  function details(container, values) {
    const dl = el('dl', undefined, 'detail-grid');
    for (const [name, value] of values) { dl.append(el('dt', name), el('dd', value === undefined || value === null ? '未提供' : display(value))); }
    container.append(dl);
  }
  async function showProject(id, quiet = false) {
    state.project = id;
    try {
      const project = await api(`/api/projects/${encodeURIComponent(id)}`);
      if (state.project !== id) return;
      const container = $('project-detail-content'); container.replaceChildren();
      details(container, [['项目名称', project.name], ['项目标识', project.id], ['准备状态', labels[project.preparation_status] || project.preparation_status], ['已发布版本', project.current_snapshot_id], ['固定提交', project.commit], ['已提取能力', project.capabilities], ['资产摘要', project.assets], ['错误信息', project.error || '无']]);
      $('project-detail').hidden = false;
      if (!quiet) $('project-detail').scrollIntoView({block: 'nearest'});
    } catch (error) { fail(error); }
  }
  function renderScans() {
    $('scans').replaceChildren(); $('scans-empty').hidden = state.scans.length !== 0; $('scan-count').textContent = `${state.scans.length} 个任务`;
    for (const scan of state.scans) {
      const row = el('tr'); const name = el('td');
      const project = state.projects.find(p => p.id === scan.project_id);
      name.append(el('div', project?.name || scan.project_id || '项目未提供', 'row-title'), el('div', scan.id, 'mono'));
      const status = el('td'); status.append(badge(scan.status));
      const action = el('td'); const button = el('button', '详情与报告', 'text-button');
      button.addEventListener('click', () => showScan(scan.id)); action.append(button); row.append(name, status, action); $('scans').append(row);
    }
  }
  function renderReport(scan) {
    const container = $('scan-detail-content'); container.replaceChildren();
    details(container, [['任务标识', scan.id], ['运行状态', labels[scan.status] || scan.status], ['资产版本', scan.snapshot_id], ['错误信息', scan.error || '无']]);
    const report = scan.report; state.report = report && typeof report === 'object' ? report : null;
    $('download-report').disabled = !state.report;
    if (!state.report) { container.append(el('p', '报告尚未生成。任务完成后将显示发现、证据和分析局限。', 'subtle')); return; }
    const markdown = el('a', '下载 Markdown 报告', 'text-button'); markdown.href = `/api/scans/${scan.id}/report.md`; markdown.download = `aixsecurity-${scan.id}.md`; container.append(markdown);
    const summary = el('section', undefined, 'report-section'); summary.append(el('h3', '结果摘要'));
    summary.append(el('p', `覆盖完整性：${report.coverage || '未提供'}；复核完成不代表所有候选已处理。`));
    summary.append(el('p', report.summary === undefined ? '请结合问题状态、程序证据和分析局限阅读结果。' : display(report.summary))); container.append(summary);
    const findings = el('section', undefined, 'report-section'); findings.append(el('h3', '问题与证据'));
    if (!Array.isArray(report.findings)) findings.append(el('p', '服务未提供结构化问题列表。', 'subtle'));
    else if (!report.findings.length) findings.append(el('p', '本次报告没有问题记录。这不代表代码不存在其他安全问题。', 'subtle'));
    else for (const finding of report.findings) {
      const article = el('article', undefined, 'finding'); article.append(el('h3', finding.title || finding.kind || finding.id || '问题记录'));
      if (finding.status) article.append(badge(finding.status));
      article.append(el('p', `${finding.repository_url || ''} · ${finding.path || ''}:${finding.line || ''}`, 'mono'));
      article.append(el('p', finding.reason || '尚无完整判断。'));
      article.append(el('p', `复核方式：${finding.verification_method || 'unreviewed'}`, 'subtle'));
      const evidence = el('details'); evidence.append(el('summary', '展开程序证据与 Agent 调用记录'), el('pre', display(finding)));
      article.append(evidence); findings.append(article);
    }
    container.append(findings);
    const limits = el('section', undefined, 'report-section'); limits.append(el('h3', '分析局限与未覆盖范围'));
    const list = el('ul'); for (const item of Array.isArray(report.limitations) ? report.limitations : ['服务未提供局限说明。']) list.append(el('li', display(item)));
    if (!list.childNodes.length) list.append(el('li', '报告未列出局限，请以实际启用的分析能力为准。')); limits.append(list); container.append(limits);
  }
  async function showScan(id, quiet = false) {
    state.scan = id;
    if (!quiet) { state.report = null; $('download-report').disabled = true; }
    try {
      const scan = await api(`/api/scans/${encodeURIComponent(id)}`);
      if (state.scan !== id) return;
      renderReport(scan); $('scan-detail').hidden = false;
      if (!quiet) $('scan-detail').scrollIntoView({block: 'nearest'});
    } catch (error) { fail(error); }
  }
  async function refresh() {
    if (state.refreshing || document.hidden) return;
    state.refreshing = true;
    try {
      const [projects, scans] = await Promise.all([api('/api/projects'), api('/api/scans')]);
      if (!Array.isArray(projects.projects) || !Array.isArray(scans.scans)) throw new Error('服务数据格式不符合项目 / 扫描列表契约。');
      state.projects = projects.projects; state.scans = scans.scans;
      renderProjects(); renderScans(); $('connection').textContent = '本地服务已连接'; $('global-error').hidden = true;
      if (state.project && state.page === 'assets') await showProject(state.project, true);
      if (state.scan && state.page === 'scans') await showScan(state.scan, true);
    } catch (error) { $('connection').textContent = '连接异常，请检查服务'; fail(error); }
    finally { state.refreshing = false; }
  }
  $('register-form').addEventListener('submit', async event => {
    event.preventDefault(); if (state.registering) return;
    const payload = {name: $('project-name').value.trim(), repositories: $('repo-urls').value.split(/\r?\n/).map(v => v.trim()).filter(Boolean)};
    const fingerprint = JSON.stringify(payload);
    if (!registrationRequest || registrationRequest.fingerprint !== fingerprint) registrationRequest = {fingerprint, key: key()};
    state.registering = true; $('register-submit').disabled = true; feedback('register-feedback', '正在登记项目…');
    try {
      await api('/api/projects', {...payload, idempotency_key: registrationRequest.key});
      feedback('register-feedback', '项目已接入，资产准备已进入队列。'); $('register-form').reset(); registrationRequest = null; await refresh();
    } catch (error) { feedback('register-feedback', error.message, true); }
    finally { state.registering = false; $('register-submit').disabled = false; }
  });
  $('scan-form').addEventListener('submit', async event => {
    event.preventDefault(); if (state.scanning) return;
    const project = state.projects.find(p => p.id === $('scan-project').value);
    if (!project || !ready(project)) { feedback('scan-feedback', '所选项目尚未就绪，请刷新资产状态。', true); return; }
    const fingerprint = `${project.id}:${project.current_snapshot_id}`;
    if (!scanRequest || scanRequest.fingerprint !== fingerprint) scanRequest = {fingerprint, key: key()};
    state.scanning = true; selectionChanged(); feedback('scan-feedback', '正在创建审计任务…');
    try {
      const scan = await api('/api/scans', {project_id: project.id, idempotency_key: scanRequest.key});
      scanRequest = null; feedback('scan-feedback', '审计任务已创建。'); await refresh(); await showScan(scan.id);
    } catch (error) { feedback('scan-feedback', error.message, true); }
    finally { state.scanning = false; selectionChanged(); }
  });
  $('download-report').addEventListener('click', () => {
    if (!state.report) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(state.report, null, 2)], {type: 'application/json'}));
    const link = el('a'); link.href = url; link.download = `aixsecurity-report-${String(state.scan).replace(/[^a-zA-Z0-9_-]/g, '_')}.json`;
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  document.querySelectorAll('[data-page]').forEach(button => button.addEventListener('click', () => { go(button.dataset.page); refresh(); }));
  document.querySelectorAll('.refresh').forEach(button => button.addEventListener('click', refresh));
  $('scan-project').addEventListener('change', selectionChanged);
  $('close-project').addEventListener('click', () => { state.project = null; $('project-detail').hidden = true; });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
  go('assets'); refresh(); setInterval(refresh, 2000);
})();
