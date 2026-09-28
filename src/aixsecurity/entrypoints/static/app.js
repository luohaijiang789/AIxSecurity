'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const state = {projects: [], scans: [], profiles: [], project: null, scan: null, report: null, refreshing: false, page: 'overview', registering: false, scanning: false, loaded: false};
  const signatures = new Map(), retryRequests = new Map();
  let registrationRequest = null, scanRequest = null;
  const labels = {READY: '已就绪', ready: '已就绪', FAILED: '准备失败', failed: '失败', queued: '等待处理', running: '处理中', completed: '已完成', cancelled: '已取消', CANCELLED: '已取消', suspicious: '待确认', rejected: '已排除', confirmed: '已确认', unreviewed: '尚未复核', static_review: '已静态复核', PARTIAL: '部分完成', PREPARING: '准备中', partial: '部分覆盖', complete_candidate_review: '已完成候选复核'};
  const ready = p => p.preparation_status === 'READY' && Boolean(p.current_snapshot_id);
  const display = value => typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  function el(tag, text, cls) { const node = document.createElement(tag); if (text !== undefined) node.textContent = String(text); if (cls) node.className = cls; return node; }
  function badge(status) { const cls = ['READY', 'ready', 'completed'].includes(status) ? 'good' : ['FAILED', 'failed'].includes(status) ? 'bad' : ['queued', 'running', 'PREPARING', 'unreviewed'].includes(status) ? 'busy' : ''; return el('span', labels[status] || status || '未知', `badge ${cls}`); }
  function feedback(id, text, error = false) { $(id).textContent = text; $(id).classList.toggle('error', error); }
  function fail(error) { $('global-error').hidden = false; $('global-error').textContent = error.message || '请求失败，请刷新重试。'; }
  // Only changed data redraws. Keyboard focus and evidence disclosure survive polling.
  function stable(id, data, render) {
    const signature = JSON.stringify(data); if (signatures.get(id) === signature) return;
    const container = $(id), focus = container.contains(document.activeElement) ? document.activeElement.dataset.focus : null;
    const expanded = new Set([...container.querySelectorAll('details[open]')].map(n => n.dataset.disclosure));
    container.replaceChildren(); render(container);
    for (const node of container.querySelectorAll('details')) { if (expanded.has(node.dataset.disclosure)) node.open = true; const summary = node.querySelector('summary'); if (summary) summary.dataset.focus = `disclosure-${node.dataset.disclosure}`; }
    if (focus) [...container.querySelectorAll('[data-focus]')].find(n => n.dataset.focus === focus)?.focus({preventScroll: true});
    signatures.set(id, signature);
  }
  function action(text, key, callback) { const b = el('button', text, 'text-button'); b.dataset.focus = key; b.addEventListener('click', callback); return b; }
  function link(text, hash) { const a = el('a', text, 'text-button'); a.href = hash; a.dataset.focus = `${hash}:${text}`; return a; }
  function key() { return crypto.randomUUID(); }
  async function api(path, body) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(path, {method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', signal: controller.signal, headers: body === undefined ? {} : {'Content-Type': 'application/json', 'X-AIxSecurity-Request': '1'}, body: body === undefined ? undefined : JSON.stringify(body)});
      const data = await response.json().catch(() => null);
      if (!response.ok) { const error = new Error(typeof data?.error === 'string' ? data.error : `请求未完成（HTTP ${response.status}）`); error.uncertain = response.status >= 500; throw error; }
      if (data === null) throw new Error('服务响应不是有效的 JSON。'); return data;
    } catch (error) { if (error.name === 'AbortError') throw new Error('请求超时，结果可能已被服务接收。再次提交将复用请求标识。'); if (error.uncertain === undefined) error.uncertain = true; throw error; }
    finally { clearTimeout(timer); }
  }
  function route() {
    const previousPage = state.page;
    const parts = location.hash.slice(1).split('/');
    state.page = ['overview', 'assets', 'scans', 'reports', 'profiles'].includes(parts[0]) ? parts[0] : 'overview';
    for (const page of ['overview', 'assets', 'scans', 'reports', 'profiles']) $(`page-${page}`).hidden = page !== state.page;
    document.querySelectorAll('[data-page]').forEach(node => { const active = node.dataset.page === state.page; node.classList.toggle('active', active); if (active) node.setAttribute('aria-current', 'page'); else node.removeAttribute('aria-current'); });
    if (previousPage !== state.page) { window.scrollTo(0, 0); const heading = $(`page-${state.page}`).querySelector('h1'); if (heading) { heading.tabIndex = -1; heading.focus({preventScroll:true}); } }
    if (state.page === 'reports' && parts[1]) { try { showScan(decodeURIComponent(parts[1])); } catch { fail(new Error('报告地址格式不正确。')); } }
    else if (state.page === 'reports') { state.scan = null; state.report = null; $('scan-detail').hidden = true; $('download-report').disabled = true; }
    refresh();
  }
  function profileTitle(id) { return state.profiles.find(p => p.id === id)?.title || id || 'SQL 注入'; }
  function projectName(id) { return state.projects.find(p => p.id === id)?.name || id || '未提供项目'; }
  function scanLink(id) { return '#reports/' + encodeURIComponent(id); }
  function metric(label, value, note) { const node = el('div', undefined, 'metric'); node.append(el('span', label), el('strong', value), el('small', note)); return node; }
  function renderOverview() {
    stable('overview-metrics', [state.projects, state.scans], node => {
      node.append(metric('项目资产', state.projects.length, `${state.projects.filter(ready).length} 个已就绪`), metric('正在处理', state.scans.filter(s => ['queued', 'running'].includes(s.status)).length + state.projects.filter(p => p.preparation_active).length, '资产准备与审计任务'), metric('已生成报告', state.scans.filter(s => s.report).length, '结论以复核状态为准'), metric('需关注准备', state.projects.filter(p => ['failed', 'cancelled'].includes(p.task_status)).length, '失败或已取消的资产准备'));
    });
    stable('overview-attention', state.projects, node => {
      const attention = state.projects.filter(p => !ready(p) || p.preparation_active || ['failed','cancelled'].includes(p.task_status));
      if (!attention.length) { node.append(el('p', state.projects.length ? '当前没有未就绪项目。可前往扫描工作台发起专项。' : '尚未接入项目。先在资产中心登记 Java 仓库。', 'subtle')); return; }
      for (const project of attention.slice(0, 6)) { const row = el('div', undefined, 'activity'); row.append(el('strong', project.name), badge(project.task_status === 'failed' ? 'failed' : project.preparation_active ? project.task_status : project.preparation_status)); node.append(row); }
      if (attention.length > 6) node.append(el('p', `另有 ${attention.length - 6} 个项目，请前往资产中心查看。`, 'subtle'));
    });
    stable('overview-recent', [state.scans, state.projects], node => {
      if (!state.scans.length) { node.append(el('p', '尚无审计任务。资产就绪后，由你选择专项并启动。', 'subtle')); return; }
      for (const scan of state.scans.slice(0, 5)) { const row = el('div', undefined, 'activity'); row.append(link(`${projectName(scan.project_id)} / ${profileTitle(scan.profile_id)}`, scanLink(scan.id)), badge(scan.status)); node.append(row); }
    });
  }
  function renderProjects() {
    $('projects-empty').hidden = state.projects.length !== 0; $('project-count').textContent = `${state.projects.length} 个项目`;
    stable('projects', state.projects, node => {
      for (const project of state.projects) {
        const row = el('tr'), name = el('td'), status = el('td'), actions = el('td'); name.append(el('div', project.name, 'row-title'));
        for (const repo of project.repositories || []) name.append(el('div', repo, 'repo'));
        status.append(badge(project.preparation_status)); if (project.preparation_active) status.append(el('p', ready(project) ? '新版本准备中，当前就绪版本仍可审计' : '正在准备资产版本', 'subtle')); if (project.error) status.append(el('p', display(project.error), 'feedback error'));
        actions.append(action('查看详情', `project-${project.id}`, () => showProject(project.id)));
        if (ready(project) || ['FAILED', 'CANCELLED'].includes(project.preparation_status)) {
          const prepare = action(project.preparation_active ? '新版本准备中' : '重新准备', `prepare-${project.id}`, async event => {
            const button = event.currentTarget; button.disabled = true;
            if (!retryRequests.has(project.id)) retryRequests.set(project.id, key());
            try { await api(`/api/projects/${encodeURIComponent(project.id)}/prepare`, {idempotency_key: retryRequests.get(project.id)}); retryRequests.delete(project.id); await refresh(); }
            catch (error) { fail(error); button.disabled = false; }
          }); prepare.disabled = Boolean(project.preparation_active); actions.append(prepare);
        }
        row.append(name, status, el('td', project.current_snapshot_id ? String(project.current_snapshot_id).slice(0, 12) : '尚未发布', 'mono'), actions); node.append(row);
      }
    });
    const options = state.projects.map(p => [p.id, p.name, p.preparation_status, p.current_snapshot_id]);
    const previous = $('scan-project').value;
    stable('scan-project', options, node => { const first = el('option', state.projects.some(ready) ? '请选择就绪项目' : '暂无就绪项目，请先完成准备'); first.value = ''; node.append(first); for (const p of state.projects) { const option = el('option', `${p.name} — ${labels[p.preparation_status] || p.preparation_status}`); option.value = p.id; option.disabled = !ready(p); node.append(option); } if (state.projects.some(p => p.id === previous && ready(p))) node.value = previous; });
    renderProfileOptions();
  }
  function renderProfileOptions() {
    const project = state.projects.find(p => p.id === $('scan-project').value);
    const selected = document.querySelector('input[name="profile"]:checked')?.value;
    stable('scan-profiles', [state.profiles, project?.id, project?.capabilities, project?.current_snapshot_id], node => {
      if (!state.profiles.length) { node.append(el('p', '服务端尚未提供可用专项能力。', 'subtle')); return; }
      for (const profile of state.profiles) {
        const available = Boolean(project && ready(project) && Array.isArray(project.capabilities) && project.capabilities.includes(profile.capability));
        const label = el('label', undefined, `mode ${available ? '' : 'unavailable'}`), input = el('input'); input.type = 'radio'; input.name = 'profile'; input.value = profile.id; input.disabled = !available; input.dataset.focus = `profile-${profile.id}`; input.checked = available && profile.id === selected;
        const text = el('span'); text.append(el('strong', profile.title), el('small', available ? profile.description : project ? '该资产版本不支持，请重新准备后选择' : '先选择就绪项目'));
        input.addEventListener('change', selectionChanged); label.append(input, text); node.append(label);
      }
      if (!node.querySelector(':checked')) { const first = node.querySelector('input:not(:disabled)'); if (first) first.checked = true; }
    }); selectionChanged();
  }
  function selectionChanged() {
    const project = state.projects.find(p => p.id === $('scan-project').value), radio = document.querySelector('input[name="profile"]:checked');
    const profile = state.profiles.find(p => p.id === radio?.value), enabled = project && ready(project) && profile && project.capabilities?.includes(profile.capability);
    $('scan-submit').disabled = (!enabled && !scanRequest) || state.scanning;
    $('scan-submit').textContent = scanRequest && !state.scanning ? '重试原审计请求' : '启动专项审计';
    if ($('discard-scan')) $('discard-scan').hidden = !scanRequest || state.scanning;
    $('scan-selection').textContent = enabled ? `固定资产版本：${project.current_snapshot_id}；专项：${profile.title}` : '请选择已就绪的项目及该版本支持的专项能力。';
    document.querySelectorAll('#scan-profiles .mode').forEach(node => node.classList.toggle('selected', Boolean(node.querySelector(':checked'))));
  }
  function details(container, values) { const dl = el('dl', undefined, 'detail-grid'); for (const [name, value] of values) dl.append(el('dt', name), el('dd', value === undefined || value === null ? '未提供' : display(value))); container.append(dl); }
  async function showProject(id, quiet = false) {
    state.project = id;
    try { const project = await api(`/api/projects/${encodeURIComponent(id)}`); if (state.project !== id) return;
      stable('project-detail-content', project, node => { details(node, [['项目名称', project.name], ['准备状态', labels[project.preparation_status] || project.preparation_status], ['新版本任务', project.preparation_active ? (labels[project.task_status] || project.task_status) : '无运行中的准备任务'], ['资产版本', project.current_snapshot_id], ['固定提交', project.commit], ['已提取能力', project.capabilities], ['错误信息', project.error || '无']]); const evidence = el('details'); evidence.dataset.disclosure = 'assets'; evidence.append(el('summary', '查看资产摘要'), el('pre', display(project.assets || {}))); node.append(evidence); }); $('project-detail').hidden = false; if (!quiet) $('project-detail').scrollIntoView({block: 'nearest'});
    } catch (error) { fail(error); }
  }
  function renderScans() {
    $('scans-empty').hidden = state.scans.length !== 0; $('scan-count').textContent = `${state.scans.length} 个任务`;
    stable('scans', [state.scans, state.projects], node => { for (const scan of state.scans) { const row = el('tr'), name = el('td'), status = el('td'), actionCell = el('td'); name.append(el('div', projectName(scan.project_id), 'row-title'), el('div', profileTitle(scan.profile_id), 'subtle'), el('div', scan.id, 'mono')); status.append(badge(scan.status)); actionCell.append(link('详情与报告', scanLink(scan.id))); row.append(name, status, actionCell); node.append(row); } });
    $('report-count').textContent = `${state.scans.filter(s => s.report).length} 份报告 / ${state.scans.length} 个任务`;
    stable('report-list', [state.scans, state.projects], node => {
      if (!state.scans.length) { const empty = el('div', undefined, 'empty'); empty.append(el('h3', '暂无审计报告'), el('p', '创建专项审计后，可在这里查看报告和未完成任务。'), link('前往扫描工作台', '#scans')); node.append(empty); return; }
      for (const scan of state.scans) { const row = el('div', undefined, 'report-row'), text = el('div'); text.append(link(projectName(scan.project_id), scanLink(scan.id)), el('div', profileTitle(scan.profile_id), 'subtle'), el('div', scan.id, 'mono')); const status = el('div'); status.append(badge(scan.status)); if (scan.report) status.append(el('small', labels[scan.report.coverage] || scan.report.coverage || '覆盖范围未提供', 'subtle')); else status.append(el('small', '尚未生成报告', 'subtle')); row.append(text, status); node.append(row); }
    });
  }
  function renderCatalog() {
    stable('profile-catalog', [state.profiles, state.projects], node => {
      if (!state.profiles.length) { node.append(el('p', '服务端尚未提供专项能力。', 'empty')); return; }
      for (const profile of state.profiles) { const card = el('article', undefined, 'panel profile-card'); card.append(el('h2', profile.title), el('p', profile.description)); details(card, [['类别', profile.category], ['所需能力', profile.capability], ['就绪资产', `${state.projects.filter(p => ready(p) && p.capabilities?.includes(profile.capability)).length} 个项目`]]); card.append(link('前往扫描工作台', '#scans')); node.append(card); }
    });
  }
  function renderReport(scan) {
    state.report = scan.report && typeof scan.report === 'object' ? scan.report : null; $('download-report').disabled = !state.report;
    stable('scan-detail-content', [scan, projectName(scan.project_id), profileTitle(scan.profile_id)], container => {
      details(container, [['所属项目', projectName(scan.project_id)], ['专项能力', profileTitle(scan.profile_id)], ['任务标识', scan.id], ['运行状态', labels[scan.status] || scan.status], ['资产版本', scan.snapshot_id], ['错误信息', scan.error || '无']]);
      const report = state.report; if (!report) { container.append(el('p', '报告尚未生成。任务完成后将显示发现、证据和分析局限。', 'subtle')); return; }
      const markdown = link('下载 Markdown 报告', `/api/scans/${encodeURIComponent(scan.id)}/report.md`); markdown.download = `aixsecurity-${scan.id}.md`; container.append(markdown);
      const summary = el('section', undefined, 'report-section'); summary.append(el('h3', '结果摘要'), badge(report.coverage));
      if (report.coverage === 'partial') summary.append(el('p', '本次仅完成部分候选复核；未处理或未复核的问题不能视为已排除。', 'notice'));
      const counts = report.summary || {}, metrics = el('div', undefined, 'report-metrics');
      for (const [label, field] of [['候选总数', 'candidate_count'], ['尝试调查', 'attempted'], ['完成复核', 'reviewed'], ['已确认', 'confirmed']]) metrics.append(metric(label, typeof counts[field] === 'number' ? counts[field] : '未提供', ''));
      summary.append(metrics); container.append(summary);
      const findings = el('section', undefined, 'report-section'); findings.append(el('h3', '问题与证据'));
      if (!Array.isArray(report.findings) || !report.findings.length) findings.append(el('p', '本次报告没有问题记录，不代表代码不存在其他安全问题。', 'subtle'));
      else report.findings.forEach((finding, index) => { const article = el('article', undefined, 'finding'); article.append(el('h3', finding.title || finding.kind || `问题 ${index + 1}`)); const statuses = el('div', undefined, 'status-group'); statuses.append(badge(finding.status), badge(finding.verification_method)); article.append(statuses);
        details(article, [['仓库', finding.repository_url || finding.repo_url || finding.repository || finding.repo_id], ['位置', `${finding.path || '未提供'}:${finding.line || '—'}`], ['固定提交', finding.commit]]);
        article.append(el('p', finding.reason || '未提供判断理由。')); if (finding.verification_method === 'unreviewed') article.append(el('p', '此项尚未完成复核，保留为待确认问题。', 'notice'));
        const evidence = el('details'); evidence.dataset.disclosure = `${scan.id}-${finding.id || index}`; evidence.append(el('summary', '展开程序证据与评审记录'), el('pre', display(finding))); article.append(evidence); findings.append(article);
      }); container.append(findings);
      const limits = el('section', undefined, 'report-section'); limits.append(el('h3', '分析局限与未覆盖范围')); const list = el('ul'); for (const item of Array.isArray(report.limitations) && report.limitations.length ? report.limitations : ['报告未列出局限，请以实际启用的分析能力为准。']) list.append(el('li', display(item))); limits.append(list); container.append(limits);
    }); $('scan-detail').hidden = false;
  }
  async function showScan(id, quiet = false) { if (state.scan !== id) { state.report = null; $('download-report').disabled = true; $('scan-detail').hidden = true; } state.scan = id;
    try { const scan = await api(`/api/scans/${encodeURIComponent(id)}`); if (state.scan !== id) return; renderReport(scan); if (!quiet) $('scan-detail').scrollIntoView({block: 'nearest'}); } catch (error) { fail(error); }
  }
  async function refresh() {
    if (state.refreshing || document.hidden) return; state.refreshing = true;
    try { const [projects, scans, profiles] = await Promise.all([api('/api/projects'), api('/api/scans'), api('/api/profiles')]); if (![projects.projects, scans.scans, profiles.profiles].every(Array.isArray)) throw new Error('服务列表响应格式不符合契约。');
      state.projects = projects.projects; state.scans = scans.scans; state.profiles = profiles.profiles; state.loaded = true;
      renderProjects(); renderScans(); renderOverview(); renderCatalog(); $('connection').textContent = '本地服务已连接'; $('global-error').hidden = true;
      if (state.project && state.page === 'assets') await showProject(state.project, true); if (state.scan && state.page === 'reports') await showScan(state.scan, true);
    } catch (error) { $('connection').textContent = '连接异常，请检查服务'; fail(error); } finally { state.refreshing = false; }
  }
  $('register-form').addEventListener('submit', async event => { event.preventDefault(); if (state.registering) return;
    const payload = {name: $('project-name').value.trim(), repositories: $('repo-urls').value.split(/\r?\n/).map(v => v.trim()).filter(Boolean)}, fingerprint = JSON.stringify(payload);
    if (!registrationRequest || registrationRequest.fingerprint !== fingerprint) registrationRequest = {fingerprint, key: key()}; state.registering = true; $('register-submit').disabled = true; feedback('register-feedback', '正在登记项目…');
    try { await api('/api/projects', {...payload, idempotency_key: registrationRequest.key}); feedback('register-feedback', '项目已接入，资产准备已进入队列。'); $('register-form').reset(); registrationRequest = null; await refresh(); } catch (error) { feedback('register-feedback', error.message, true); } finally { state.registering = false; $('register-submit').disabled = false; }
  });
  $('scan-form').addEventListener('submit', async event => { event.preventDefault(); if (state.scanning) return; const project = state.projects.find(p => p.id === $('scan-project').value), profile = state.profiles.find(p => p.id === document.querySelector('input[name="profile"]:checked')?.value);
    if (!scanRequest && (!project || !ready(project) || !profile || !project.capabilities?.includes(profile.capability))) { feedback('scan-feedback', '请选择就绪项目及支持的专项。旧资产需要重新准备。', true); return; }
    if (!scanRequest) scanRequest = {payload: {project_id:project.id, profile_id:profile.id, expected_snapshot_id:project.current_snapshot_id, idempotency_key:key()}}; state.scanning = true; selectionChanged(); feedback('scan-feedback', '正在创建审计任务…');
    try { const scan = await api('/api/scans', scanRequest.payload); scanRequest = null; feedback('scan-feedback', '审计任务已创建。'); await refresh(); location.hash = scanLink(scan.id); } catch (error) { if (error.uncertain === false) scanRequest = null; feedback('scan-feedback', error.message + (scanRequest ? ' 待确认请求已保留；重试将使用原项目、版本、专项和请求标识。' : ''), true); } finally { state.scanning = false; selectionChanged(); }
  });
  const discard = el('button', '放弃未决请求，允许新任务（旧任务可能已创建）', 'text-button'); discard.id = 'discard-scan'; discard.type = 'button'; discard.hidden = true; discard.addEventListener('click', () => { scanRequest = null; feedback('scan-feedback', '已放弃本地等待；未取消服务端可能已经创建的任务，请先查看任务列表。'); selectionChanged(); }); $('scan-form').append(discard);
  $('download-report').addEventListener('click', () => { if (!state.report) return; const url = URL.createObjectURL(new Blob([JSON.stringify(state.report, null, 2)], {type: 'application/json'})), a = el('a'); a.href = url; a.download = `aixsecurity-report-${String(state.scan).replace(/[^a-zA-Z0-9_-]/g, '_')}.json`; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000); });
  document.querySelectorAll('.refresh').forEach(button => button.addEventListener('click', refresh)); $('scan-project').addEventListener('change', renderProfileOptions); $('close-project').addEventListener('click', () => { state.project = null; $('project-detail').hidden = true; }); $('page-reports').insertBefore($('scan-detail'), $('page-reports').querySelector('.panel')); window.addEventListener('hashchange', route); document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); }); route(); setInterval(refresh, 2000);
})();
