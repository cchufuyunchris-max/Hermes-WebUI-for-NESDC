(function(){
  'use strict';

  const $ = (id) => document.getElementById(id);
  let state = { policy: null, meta: {}, connectorTypes: [], skills: [], selectedSkill: null, users: [], userMeta: {}, selectedUser: null };

  function headers() {
    const h = { 'Content-Type': 'application/json' };
    const csrf = (window.__HERMES_ADMIN_CONFIG__ || {}).csrfToken || '';
    if (csrf) h['X-Hermes-CSRF-Token'] = csrf;
    const token = $('adminToken').value.trim();
    if (token) h['X-Hermes-Admin-Token'] = token;
    return h;
  }

  async function api(path, opts) {
    const res = await fetch(path, Object.assign({ headers: headers() }, opts || {}));
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  function setStatus(text, kind) {
    const el = $('statusBar');
    el.textContent = text;
    el.className = `status-bar ${kind || ''}`.trim();
  }

  function asList(value) {
    if (Array.isArray(value)) return value;
    return String(value || '').split(',').map(s => s.trim()).filter(Boolean);
  }

  function formatBytes(bytes) {
    const n = Number(bytes || 0);
    if (!Number.isFinite(n) || n <= 0) return '0 B';
    const units = ['B','KB','MB','GB','TB'];
    let value = n;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) {
      value /= 1024;
      unit += 1;
    }
    return `${value >= 10 || unit === 0 ? value.toFixed(0) : value.toFixed(1)} ${units[unit]}`;
  }

  function usageLabel(user) {
    const quota = Number(user.disk_quota_bytes || (user.effective_resources || {}).disk_quota_bytes || 0);
    const usage = Number(user.usage_bytes || 0);
    const percent = user.usage_percent == null ? null : Number(user.usage_percent);
    if (!quota) return `已用 ${formatBytes(usage)} / 未设置配额`;
    return `已用 ${formatBytes(usage)} / ${formatBytes(quota)}${percent == null ? '' : ` · ${percent.toFixed(percent >= 10 ? 0 : 1)}%`}`;
  }

  function usageStatusText(status) {
    if (status === 'critical') return '高风险';
    if (status === 'warn') return '接近配额';
    if (status === 'no-quota') return '无配额';
    return '正常';
  }

  function effectiveResource(user, key) {
    const res = user.resources || {};
    const eff = user.effective_resources || {};
    return res[key] ?? eff[key] ?? '';
  }

  function userUsagePercentText(user) {
    if (user.usage_percent == null) return '-';
    const pct = Number(user.usage_percent);
    return `${pct.toFixed(pct >= 10 ? 0 : 1)}%`;
  }

  function csv(id) {
    return asList($(id).value);
  }

  function ensurePolicyShape(policy) {
    policy.enabled = policy.enabled !== false;
    policy.resources = policy.resources || {};
    policy.model_policy = policy.model_policy || {};
    policy.model_policy.tiers = policy.model_policy.tiers || {};
    policy.model_policy.local_model = policy.model_policy.local_model || {};
    policy.data_connectors = policy.data_connectors || {};
    policy.data_connectors.audit = policy.data_connectors.audit || {};
    policy.data_connectors.connectors = Array.isArray(policy.data_connectors.connectors)
      ? policy.data_connectors.connectors
      : [];
    policy.dify_knowledge = policy.dify_knowledge || {};
    policy.dify_knowledge.stations = Array.isArray(policy.dify_knowledge.stations)
      ? policy.dify_knowledge.stations
      : [];
    return policy;
  }

  function renderAll() {
    const policy = ensurePolicyShape(state.policy);
    const mp = policy.model_policy;
    const dc = policy.data_connectors;
    const res = policy.resources;
    const dk = policy.dify_knowledge;

    $('policyPath').textContent = state.meta.path || 'Policy';
    $('enabled').checked = policy.enabled !== false;
    $('runtimePrivacyGuard').checked = mp.runtime_privacy_guard_enabled !== false;
    $('allowTerminalNetwork').checked = !!mp.allow_terminal_network;
    $('allowCodeNetwork').checked = !!mp.allow_code_network;
    $('allowUserModelSettings').checked = !!mp.allow_user_model_settings;
    $('allowUserOnlineKey').checked = !!mp.allow_user_online_model_api_key;

    $('localProvider').value = mp.local_model.provider || mp.gateway_provider || 'openai-compatible';
    $('localBaseUrl').value = mp.local_model.base_url || '';
    $('localApiKey').value = mp.local_model.api_key || '';
    $('localModelId').value = mp.local_model.model || mp.tiers.safe || '';
    $('modelMode').value = mp.mode || 'privacy-router';
    $('defaultTier').value = mp.default_tier || 'safe';
    $('gatewayProvider').value = mp.gateway_provider || mp.local_model.provider || 'openai-compatible';
    $('allowedTiers').value = (mp.allowed_tiers || ['safe','quality','fast']).join(',');
    $('tierSafe').value = mp.tiers.safe || '';
    $('tierQuality').value = mp.tiers.quality || '';
    $('tierFast').value = mp.tiers.fast || '';
    $('onlineAllowedToolsets').value = (mp.online_allowed_toolsets || []).join(',');

    $('cpuLimit').value = res.cpu_limit ?? '';
    $('memoryLimit').value = res.memory_limit || '';
    $('diskQuota').value = res.disk_quota_bytes ?? '';

    $('auditEnabled').checked = dc.audit.enabled !== false;
    $('auditPath').value = dc.audit.log_path || '/home/hermes/data/audit/data-tools.jsonl';
    $('enforceManagedMcp').checked = dc.enforce_managed_mcp_servers !== false;
    $('difyKnowledgeEnabled').checked = dk.enabled === true;
    $('difyKnowledgeBaseUrl').value = dk.base_url || '';
    $('difyKnowledgeApiKey').value = dk.api_key || '';
    $('difyKnowledgePrivacyLevel').value = dk.privacy_level || 'public';
    $('difyKnowledgeTopK').value = dk.top_k ?? '';

    $('metricEnabled').textContent = policy.enabled === false ? '禁用' : '启用';
    $('metricDefaultTier').textContent = mp.default_tier || 'safe';
    $('metricConnectors').textContent = String(dc.connectors.length);
    $('metricAudit').textContent = dc.audit.enabled === false ? '关闭' : '开启';

    renderConnectors();
    renderDifyStations();
    $('rawJson').value = JSON.stringify(policy, null, 2);
  }

  function readFormIntoPolicy() {
    const policy = ensurePolicyShape(state.policy || {});
    const mp = policy.model_policy;
    const res = policy.resources;
    const dc = policy.data_connectors;
    const dk = policy.dify_knowledge;

    policy.enabled = $('enabled').checked;
    mp.runtime_privacy_guard_enabled = $('runtimePrivacyGuard').checked;
    mp.allow_terminal_network = $('allowTerminalNetwork').checked;
    mp.allow_code_network = $('allowCodeNetwork').checked;
    mp.allow_user_model_settings = $('allowUserModelSettings').checked;
    mp.allow_user_online_model_api_key = $('allowUserOnlineKey').checked;
    mp.local_model = mp.local_model || {};
    mp.local_model.provider = $('localProvider').value.trim() || 'openai-compatible';
    mp.local_model.base_url = $('localBaseUrl').value.trim();
    mp.local_model.api_key = $('localApiKey').value.trim();
    mp.local_model.model = $('localModelId').value.trim();
    mp.mode = $('modelMode').value;
    mp.default_tier = $('defaultTier').value;
    mp.gateway_provider = $('gatewayProvider').value.trim() || mp.local_model.provider;
    mp.allowed_tiers = csv('allowedTiers').length ? csv('allowedTiers') : ['safe','quality','fast'];
    mp.online_allowed_toolsets = csv('onlineAllowedToolsets').length ? csv('onlineAllowedToolsets') : ['web','vision','clarify','todo','image_gen'];
    const safeTier = $('tierSafe').value.trim();
    mp.tiers.safe = (!safeTier || safeTier === 'local-private-default')
      ? (mp.local_model.model || 'local-private-default')
      : safeTier;
    mp.tiers.quality = $('tierQuality').value.trim();
    mp.tiers.fast = $('tierFast').value.trim();

    const cpuLimit = $('cpuLimit').value.trim();
    const diskQuota = $('diskQuota').value.trim();
    res.cpu_limit = cpuLimit ? Number(cpuLimit) : 2;
    res.memory_limit = $('memoryLimit').value.trim() || '4g';
    res.disk_quota_bytes = diskQuota ? Number(diskQuota) : 21474836480;

    dc.audit.enabled = $('auditEnabled').checked;
    dc.audit.log_path = $('auditPath').value.trim() || '/home/hermes/data/audit/data-tools.jsonl';
    dc.enforce_managed_mcp_servers = $('enforceManagedMcp').checked;
    dc.connectors = readConnectors();
    dk.enabled = $('difyKnowledgeEnabled').checked;
    dk.base_url = $('difyKnowledgeBaseUrl').value.trim();
    dk.api_key = $('difyKnowledgeApiKey').value.trim();
    dk.privacy_level = $('difyKnowledgePrivacyLevel').value || 'public';
    dk.access_mode = 'read-only';
    const topK = $('difyKnowledgeTopK').value.trim();
    if (topK) dk.top_k = Number(topK) || topK;
    else delete dk.top_k;
    dk.stations = readDifyStations();
    return policy;
  }

  function typeOptions(selected) {
    const types = state.connectorTypes.length ? state.connectorTypes : ['dify','clickhouse','postgres','mysql','sqlite','mcp','other'];
    return types.map(t => `<option value="${escapeHtml(t)}"${t === selected ? ' selected' : ''}>${escapeHtml(t)}</option>`).join('');
  }

  function connectorTitle(conn) {
    return conn.id || conn.type || '未命名连接';
  }

  function renderConnectors() {
    const list = $('connectorsList');
    list.innerHTML = '';
    const tmpl = $('connectorTemplate');
    const connectors = state.policy.data_connectors.connectors;
    connectors.forEach((conn, index) => {
      const node = tmpl.content.firstElementChild.cloneNode(true);
      node.dataset.index = String(index);
      node.querySelector('.connector-title').textContent = connectorTitle(conn);
      node.querySelector('.connector-sub').textContent = `${conn.type || 'other'} · ${conn.privacy_level || 'private'} · ${conn.access_mode || 'read-only'}`;
      node.querySelector('[data-field="type"]').innerHTML = typeOptions(conn.type || 'other');
      setField(node, 'enabled', conn.enabled !== false);
      setField(node, 'id', conn.id || '');
      setField(node, 'type', conn.type || 'other');
      setField(node, 'privacy_level', conn.privacy_level || 'private');
      setField(node, 'access_mode', conn.access_mode || 'read-only');
      setField(node, 'host_or_base_url', conn.base_url || conn.host || '');
      setField(node, 'port', conn.port || '');
      setField(node, 'database_or_app_id', conn.app_id || conn.database || '');
      setField(node, 'user', conn.user || '');
      setField(node, 'secret', conn.api_key || conn.password || '');
      const mcp = conn.mcp || {};
      setField(node, 'mcp_enabled', !!mcp.enabled);
      setField(node, 'mcp_server_name', mcp.server_name || conn.id || '');
      setField(node, 'mcp_command', mcp.command || '');
      setField(node, 'mcp_args', Array.isArray(mcp.args) ? mcp.args.join(' ') : '');
      setField(node, 'mcp_env', JSON.stringify(mcp.env || {}, null, 2));
      node.querySelector('[data-action="remove"]').addEventListener('click', () => {
        state.policy.data_connectors.connectors.splice(index, 1);
        renderAll();
      });
      node.addEventListener('input', () => {
        state.policy.data_connectors.connectors = readConnectors();
        $('rawJson').value = JSON.stringify(state.policy, null, 2);
        renderMetricsOnly();
      });
      node.addEventListener('change', () => {
        state.policy.data_connectors.connectors = readConnectors();
        $('rawJson').value = JSON.stringify(state.policy, null, 2);
        renderConnectors();
        renderMetricsOnly();
      });
      list.appendChild(node);
    });
    if (!connectors.length) {
      const empty = document.createElement('div');
      empty.className = 'status-bar';
      empty.textContent = '还没有数据连接。点击“新增连接”创建 Dify、数据库或 MCP connector。';
      list.appendChild(empty);
    }
  }

  function renderMetricsOnly() {
    const policy = ensurePolicyShape(state.policy);
    $('metricConnectors').textContent = String(policy.data_connectors.connectors.length);
    $('metricAudit').textContent = policy.data_connectors.audit.enabled === false ? '关闭' : '开启';
  }

  function setField(root, name, value) {
    const el = root.querySelector(`[data-field="${name}"]`);
    if (!el) return;
    if (el.type === 'checkbox') el.checked = !!value;
    else el.value = value == null ? '' : String(value);
  }

  function getField(root, name) {
    const el = root.querySelector(`[data-field="${name}"]`);
    if (!el) return '';
    return el.type === 'checkbox' ? el.checked : el.value.trim();
  }

  function readConnectors() {
    return Array.from(document.querySelectorAll('.connector-card')).map(card => {
      const type = getField(card, 'type') || 'other';
      const conn = {
        id: getField(card, 'id'),
        type,
        enabled: getField(card, 'enabled'),
        privacy_level: getField(card, 'privacy_level') || 'private',
        access_mode: getField(card, 'access_mode') || 'read-only'
      };
      const hostOrBase = getField(card, 'host_or_base_url');
      if (type === 'dify' || type === 'knowledge_base') conn.base_url = hostOrBase;
      else conn.host = hostOrBase;
      const port = getField(card, 'port');
      if (port) conn.port = Number(port) || port;
      const dbOrApp = getField(card, 'database_or_app_id');
      if (type === 'dify' || type === 'knowledge_base') conn.app_id = dbOrApp;
      else conn.database = dbOrApp;
      const user = getField(card, 'user');
      if (user) conn.user = user;
      const secret = getField(card, 'secret');
      if (secret) {
        if (type === 'dify' || type === 'knowledge_base') conn.api_key = secret;
        else conn.password = secret;
      }
      if (isDatabaseType(type)) {
        conn.readonly = true;
        conn.access_mode = conn.access_mode || 'read-only';
      }
      const mcpEnabled = getField(card, 'mcp_enabled');
      const mcpCommand = getField(card, 'mcp_command');
      const mcpServer = getField(card, 'mcp_server_name');
      const mcpArgs = getField(card, 'mcp_args');
      const mcpEnvRaw = getField(card, 'mcp_env');
      if (mcpEnabled || mcpCommand || mcpServer || mcpEnvRaw) {
        let env = {};
        if (mcpEnvRaw) {
          try { env = JSON.parse(mcpEnvRaw); }
          catch (_) { env = {}; }
        }
        conn.mcp = {
          enabled: !!mcpEnabled,
          server_name: mcpServer || conn.id,
          command: mcpCommand,
          args: mcpArgs ? mcpArgs.split(/\s+/).filter(Boolean) : [],
          env
        };
      }
      return conn;
    });
  }

  function renderDifyStations() {
    const list = $('difyStationsList');
    list.innerHTML = '';
    const tmpl = $('difyStationTemplate');
    const stations = ensurePolicyShape(state.policy).dify_knowledge.stations;
    stations.forEach((station, index) => {
      const node = tmpl.content.firstElementChild.cloneNode(true);
      node.dataset.index = String(index);
      node.querySelector('.station-title').textContent = station.station_name || station.station_id || `站点 ${index + 1}`;
      setField(node, 'enabled', station.enabled !== false);
      setField(node, 'station_id', station.station_id || '');
      setField(node, 'station_name', station.station_name || '');
      setField(node, 'dataset_id', station.dataset_id || '');
      setField(node, 'tags', Array.isArray(station.tags) ? station.tags.join(',') : (station.tags || ''));
      node.querySelector('[data-action="remove"]').addEventListener('click', () => {
        state.policy.dify_knowledge.stations.splice(index, 1);
        renderAll();
      });
      node.addEventListener('input', () => {
        state.policy.dify_knowledge.stations = readDifyStations();
        $('rawJson').value = JSON.stringify(state.policy, null, 2);
      });
      node.addEventListener('change', () => {
        state.policy.dify_knowledge.stations = readDifyStations();
        $('rawJson').value = JSON.stringify(state.policy, null, 2);
        renderDifyStations();
      });
      list.appendChild(node);
    });
    if (!stations.length) {
      const empty = document.createElement('div');
      empty.className = 'status-bar';
      empty.textContent = '还没有 Dify Knowledge 站点映射。点击“新增站点”后填写站点名称和 dataset_id。';
      list.appendChild(empty);
    }
  }

  function readDifyStations() {
    return Array.from(document.querySelectorAll('.station-card')).map(card => {
      const station = {
        enabled: getField(card, 'enabled'),
        station_id: getField(card, 'station_id'),
        station_name: getField(card, 'station_name'),
        dataset_id: getField(card, 'dataset_id')
      };
      const tags = asList(getField(card, 'tags'));
      if (tags.length) station.tags = tags;
      return station;
    }).filter(station => station.station_id || station.station_name || station.dataset_id);
  }

  function isDatabaseType(type) {
    return ['clickhouse','postgres','postgresql','mysql','mariadb','sqlite','duckdb','mongo','mongodb','redis','database'].includes(String(type || '').toLowerCase());
  }

  async function loadPolicy() {
    setStatus('正在加载策略...', '');
    const data = await api('api/admin/policy');
    state.policy = ensurePolicyShape(data.policy);
    state.meta = data;
    state.connectorTypes = data.connector_types || [];
    renderAll();
    setStatus(data.token_required ? '策略已加载。生产环境已启用 Admin Token。' : '策略已加载。本地开发模式未要求 Admin Token。', 'ok');
  }

  async function reloadAdminData() {
    await loadPolicy();
    await Promise.all([loadAdminSkills(), loadAdminUsers()]);
  }

  async function savePolicy() {
    try {
      if (!state.policy) {
        setStatus('策略尚未成功加载，已阻止保存。请先输入 Admin Token 并点击刷新。', 'err');
        return;
      }
      state.policy = readFormIntoPolicy();
      const rawActive = document.querySelector('#section-json.active');
      if (rawActive) state.policy = ensurePolicyShape(JSON.parse($('rawJson').value));
      setStatus('正在保存策略...', '');
      const data = await api('api/admin/policy/save', {
        method: 'POST',
        body: JSON.stringify({ policy: state.policy })
      });
      state.policy = ensurePolicyShape(data.policy);
      state.meta = data;
      renderAll();
      setStatus('全局 Hermes Agent 模型策略已保存。新建或重建的用户容器会同步到 config.yaml；已运行用户需要重新 Spawn 后生效。', 'ok');
    } catch (err) {
      setStatus(err.message || String(err), 'err');
    }
  }

  async function loadAudit() {
    try {
      const data = await api('api/admin/audit?limit=100');
      renderAudit(data.events || []);
      setStatus(`审计已加载：${data.path}`, 'ok');
    } catch (err) {
      setStatus(err.message || String(err), 'err');
    }
  }

  async function loadAdminSkills() {
    try {
      const data = await api('api/admin/skills');
      state.skills = data.skills || [];
      renderAdminSkills();
    } catch (err) {
      setStatus(err.message || String(err), 'err');
    }
  }

  async function loadAdminUsers() {
    try {
      const data = await api('api/admin/users');
      state.users = data.users || [];
      state.userMeta = data || {};
      renderAdminUsers();
    } catch (err) {
      const list = $('adminUserList');
      if (list) list.innerHTML = `<div class="status-bar err">用户列表加载失败：${escapeHtml(err.message || String(err))}</div>`;
      setStatus(err.message || String(err), 'err');
    }
  }

  function renderAdminUsers() {
    const list = $('adminUserList');
    if (!list) return;
    list.innerHTML = '';
    const totalUsers = state.userMeta.count ?? state.users.length;
    $('metricUsers').textContent = `${totalUsers} 个`;
    $('metricUserUsage').textContent = formatBytes(state.userMeta.total_usage_bytes || 0);
    $('metricUserWarnings').textContent = `${state.userMeta.warn_count || 0} 个`;
    $('metricUserRoot').textContent = state.userMeta.user_data_root || '未配置';
    if (!state.users.length) {
      list.innerHTML = '<div class="status-bar">暂无用户数据。用户首次登录并 Spawn 后会出现在这里。</div>';
      return;
    }
    const table = document.createElement('div');
    table.className = 'user-table';
    table.innerHTML = [
      '<div class="user-row user-row-head">',
      '<span>用户</span><span>策略</span><span>CPU</span><span>内存</span><span>磁盘配额</span><span>已用空间</span><span>状态</span><span>操作</span>',
      '</div>'
    ].join('');
    state.users.forEach(user => {
      const mode = user.has_override ? '有覆盖' : '默认资源';
      const pct = Math.max(0, Math.min(100, Number(user.usage_percent || 0)));
      const row = document.createElement('div');
      row.className = `user-row ${user.usage_status || 'ok'}`;
      row.innerHTML = [
        `<span class="user-cell-main"><strong>${escapeHtml(user.user_id)}</strong><small>${escapeHtml(user.has_data ? '已创建目录' : '暂无目录')}</small></span>`,
        `<span>${escapeHtml(mode)}</span>`,
        `<span>${escapeHtml(effectiveResource(user, 'cpu_limit') || '-')}</span>`,
        `<span>${escapeHtml(effectiveResource(user, 'memory_limit') || '-')}</span>`,
        `<span>${escapeHtml(effectiveResource(user, 'disk_quota_bytes') ? formatBytes(effectiveResource(user, 'disk_quota_bytes')) : '-')}</span>`,
        `<span class="usage-cell"><b>${escapeHtml(formatBytes(user.usage_bytes || 0))}</b><small>${escapeHtml(userUsagePercentText(user))}</small><div class="usage-bar"><i style="width:${pct}%"></i></div></span>`,
        `<span><em class="status-pill ${escapeHtml(user.usage_status || 'ok')}">${escapeHtml(usageStatusText(user.usage_status))}</em></span>`,
        '<span class="row-actions"></span>'
      ].join('');
      row.addEventListener('click', () => openAdminUser(user.user_id));
      const actions = row.querySelector('.row-actions');
      const edit = document.createElement('button');
      edit.type = 'button';
      edit.className = 'ghost-btn small-btn';
      edit.textContent = '编辑';
      edit.addEventListener('click', (ev) => {
        ev.stopPropagation();
        openAdminUser(user.user_id);
      });
      const rebuild = document.createElement('button');
      rebuild.type = 'button';
      rebuild.className = 'ghost-btn small-btn';
      rebuild.textContent = '重建容器';
      rebuild.addEventListener('click', (ev) => {
        ev.stopPropagation();
        rebuildUserRuntime(user.user_id);
      });
      const wipe = document.createElement('button');
      wipe.type = 'button';
      wipe.className = 'ghost-btn danger-btn small-btn';
      wipe.textContent = '删除数据';
      wipe.addEventListener('click', (ev) => {
        ev.stopPropagation();
        deleteAdminUserData(user.user_id);
      });
      actions.append(edit, rebuild, wipe);
      table.appendChild(row);
    });
    list.appendChild(table);
  }

  function newAdminUser() {
    state.selectedUser = null;
    $('userPolicyId').value = '';
    $('userPolicyEnabled').value = 'true';
    $('userCpuLimit').value = '';
    $('userMemoryLimit').value = '';
    $('userDiskQuota').value = '';
    $('userUsageSummary').innerHTML = '新建覆盖只会写入资源策略；用户目录会在首次登录/Spawn 后出现。';
  }

  async function openAdminUser(userId) {
    try {
      const data = await api(`api/admin/users/detail?user_id=${encodeURIComponent(userId)}`);
      const policy = data.policy || {};
      const res = policy.resources || {};
      state.selectedUser = data;
      $('userPolicyId').value = data.user_id || userId || '';
      $('userPolicyEnabled').value = policy.enabled === false ? 'false' : 'true';
      $('userCpuLimit').value = res.cpu_limit ?? '';
      $('userMemoryLimit').value = res.memory_limit || '';
      $('userDiskQuota').value = res.disk_quota_bytes ?? '';
      renderUserUsageSummary(data);
      setStatus(`已加载用户覆盖：${data.user_id || userId}`, 'ok');
    } catch (err) {
      setStatus(err.message || String(err), 'err');
    }
  }

  function renderUserUsageSummary(data) {
    const usage = data.usage || {};
    const eff = data.effective_resources || {};
    const quota = usage.disk_quota_bytes || eff.disk_quota_bytes || 0;
    const pct = Math.max(0, Math.min(100, Number(usage.usage_percent || 0)));
    $('userUsageSummary').innerHTML = [
      `<strong>${escapeHtml(data.user_id || '')}</strong>`,
      `<span>${escapeHtml(usageStatusText(usage.usage_status))} · 已用 ${escapeHtml(formatBytes(usage.usage_bytes || 0))}${quota ? ` / ${escapeHtml(formatBytes(quota))}` : ' / 未设置配额'}</span>`,
      `<div class="usage-bar ${escapeHtml(usage.usage_status || 'ok')}"><i style="width:${pct}%"></i></div>`,
      `<small>${escapeHtml(usage.data_path || '用户数据目录未配置')}</small>`
    ].join('');
  }

  async function saveAdminUser() {
    const userId = $('userPolicyId').value.trim();
    if (!userId) {
      setStatus('请先填写用户 ID。', 'err');
      return;
    }
    const resources = {};
    const cpu = $('userCpuLimit').value.trim();
    const memory = $('userMemoryLimit').value.trim();
    const disk = $('userDiskQuota').value.trim();
    if (cpu) resources.cpu_limit = Number(cpu);
    if (memory) resources.memory_limit = memory;
    if (disk) resources.disk_quota_bytes = Number(disk);
    try {
      await api('api/admin/users/save', {
        method: 'POST',
        body: JSON.stringify({
          user_id: userId,
          policy: {
            enabled: $('userPolicyEnabled').value !== 'false',
            resources
          }
        })
      });
      setStatus(`用户覆盖已保存：${userId}。该用户需要重新 Spawn 后生效。`, 'ok');
      await loadAdminUsers();
      await openAdminUser(userId);
    } catch (err) {
      setStatus(err.message || String(err), 'err');
    }
  }

  async function rebuildUserRuntime(userIdArg) {
    const userId = String(userIdArg || $('userPolicyId').value || '').trim();
    if (!userId) {
      setStatus('请先选择或填写用户 ID。', 'err');
      return;
    }
    const ok = window.confirm(`重建 ${userId} 的用户容器？\n\n这会停止并删除 jupyter-${userId} 容器，但不会删除用户数据。用户下次 Launch/Spawn 时会按最新策略重新创建。`);
    if (!ok) return;
    try {
      const data = await api('api/admin/users/rebuild-runtime', {
        method: 'POST',
        body: JSON.stringify({ user_id: userId })
      });
      setStatus(`${userId} 容器已处理：${data.removed ? '已删除旧容器' : '未发现旧容器'}。用户下次 Launch/Spawn 会应用最新策略。`, 'ok');
      await loadAdminUsers();
      if ($('userPolicyId').value.trim() === userId) {
        await openAdminUser(userId);
      }
    } catch (err) {
      setStatus(err.message || String(err), 'err');
    }
  }

  async function rebuildAllUserRuntimes() {
    const ok = window.confirm('将重建所有用户容器？\n\n这会停止并删除所有 jupyter-{user} 容器，但不会删除用户数据。用户下次 Launch/Spawn 时会按最新策略重新创建。');
    if (!ok) return;
    try {
      const data = await api('api/admin/users/rebuild-all-runtimes', {
        method: 'POST',
        body: JSON.stringify({})
      });
      const failed = Number(data.failed_count || 0);
      setStatus(`已处理 ${data.count || 0} 个用户容器${failed ? `，失败 ${failed} 个，请查看用户列表或服务日志。` : '，用户下次 Launch/Spawn 会应用最新策略。'}`, failed ? 'err' : 'ok');
      await loadAdminUsers();
    } catch (err) {
      setStatus(err.message || String(err), 'err');
    }
  }

  async function deleteAdminUser(userIdArg) {
    const userId = String(userIdArg || $('userPolicyId').value || '').trim();
    if (!userId) return;
    try {
      await api('api/admin/users/delete', {
        method: 'POST',
        body: JSON.stringify({ user_id: userId })
      });
      setStatus(`用户覆盖已删除：${userId}`, 'ok');
      newAdminUser();
      await loadAdminUsers();
    } catch (err) {
      setStatus(err.message || String(err), 'err');
    }
  }

  async function deleteAdminUserData(userIdArg) {
    const userId = String(userIdArg || $('userPolicyId').value || '').trim();
    if (!userId) {
      setStatus('请先选择或填写用户 ID。', 'err');
      return;
    }
    const confirmUserId = window.prompt(`删除 ${userId} 的 Hermes 用户目录和覆盖配置。这个操作不可恢复。\n请输入用户 ID 确认：`);
    if (confirmUserId !== userId) {
      setStatus('已取消删除：确认文本不匹配。', 'err');
      return;
    }
    try {
      const data = await api('api/admin/users/delete-data', {
        method: 'POST',
        body: JSON.stringify({ user_id: userId, confirm_user_id: confirmUserId })
      });
      setStatus(`已删除用户 ${userId}：释放 ${formatBytes(data.usage_bytes_before_delete || 0)}。如果该用户容器正在运行，请先在 JupyterHub 停止该用户服务。`, 'ok');
      newAdminUser();
      await loadAdminUsers();
    } catch (err) {
      setStatus(err.message || String(err), 'err');
    }
  }

  function renderAdminSkills() {
    const list = $('adminSkillList');
    if (!list) return;
    list.innerHTML = '';
    if (!state.skills.length) {
      list.innerHTML = '<div class="status-bar">暂无推荐 Skill。点击“新建 Skill”发布第一个。</div>';
      return;
    }
    state.skills.forEach(skill => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'admin-skill-item';
      btn.innerHTML = `<strong>${escapeHtml(skill.title || skill.name || skill.id)}</strong><span>${escapeHtml(skill.description || skill.version || '')}</span>`;
      btn.addEventListener('click', () => openAdminSkill(skill.id || skill.name));
      list.appendChild(btn);
    });
  }

  function newAdminSkill() {
    state.selectedSkill = null;
    $('skillId').value = '';
    $('skillName').value = '';
    $('skillVersion').value = '1.0.0';
    $('skillTags').value = '';
    $('skillDescription').value = '';
    $('skillContent').value = [
      '---',
      'name: new-skill',
      'description: 描述这个 Skill 适合解决什么任务',
      '---',
      '',
      '# 使用说明',
      '',
      '在这里写给 Hermes 的技能说明。'
    ].join('\n');
  }

  async function openAdminSkill(id) {
    try {
      const data = await api(`api/admin/skills/detail?id=${encodeURIComponent(id)}`);
      const skill = data.skill || {};
      const manifest = skill.manifest || {};
      state.selectedSkill = skill;
      $('skillId').value = skill.id || id || '';
      $('skillName').value = skill.name || manifest.name || '';
      $('skillVersion').value = skill.version || manifest.version || '';
      $('skillTags').value = (skill.tags || manifest.tags || []).join(',');
      $('skillDescription').value = skill.description || manifest.description || '';
      $('skillContent').value = skill.content || '';
      setStatus(`已加载 Skill：${skill.name || id}`, 'ok');
    } catch (err) {
      setStatus(err.message || String(err), 'err');
    }
  }

  async function saveAdminSkill() {
    try {
      const payload = {
        id: $('skillId').value.trim(),
        name: $('skillName').value.trim(),
        version: $('skillVersion').value.trim(),
        tags: $('skillTags').value.trim(),
        description: $('skillDescription').value.trim(),
        content: $('skillContent').value
      };
      const data = await api('api/admin/skills/save', {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      const skill = data.skill || {};
      setStatus(`推荐 Skill 已保存：${skill.name || payload.name}`, 'ok');
      await loadAdminSkills();
      if (skill.id) await openAdminSkill(skill.id);
    } catch (err) {
      setStatus(err.message || String(err), 'err');
    }
  }

  async function importGithubSkills() {
    const url = $('githubSkillUrl').value.trim();
    if (!url) {
      setStatus('请先填写 GitHub 仓库 URL。', 'err');
      return;
    }
    const resultBox = $('githubImportResult');
    resultBox.hidden = false;
    resultBox.textContent = '正在从 GitHub 下载并扫描 Skill...';
    resultBox.className = 'import-result';
    try {
      const data = await api('api/admin/skills/import-github', {
        method: 'POST',
        body: JSON.stringify({
          url,
          ref: $('githubSkillRef').value.trim(),
          subdir: $('githubSkillSubdir').value.trim(),
          prefix: $('githubSkillPrefix').value.trim(),
          overwrite: $('githubSkillOverwrite').checked
        })
      });
      const imported = data.imported || [];
      const skipped = data.skipped || [];
      resultBox.className = 'import-result ok';
      resultBox.innerHTML = [
        `<strong>导入完成：${escapeHtml(imported.length)} 个，跳过 ${escapeHtml(skipped.length)} 个</strong>`,
        imported.length ? `<span>已导入：${escapeHtml(imported.map(s => s.title || s.name || s.id).join('、'))}</span>` : '',
        skipped.length ? `<span>已跳过：${escapeHtml(skipped.map(s => s.id).join('、'))}</span>` : ''
      ].filter(Boolean).join('');
      setStatus(`GitHub Skill 导入完成：${imported.length} 个。`, 'ok');
      await loadAdminSkills();
      if (imported[0] && imported[0].id) await openAdminSkill(imported[0].id);
    } catch (err) {
      resultBox.className = 'import-result err';
      resultBox.textContent = err.message || String(err);
      setStatus(err.message || String(err), 'err');
    }
  }

  async function deleteAdminSkill() {
    const id = $('skillId').value.trim();
    if (!id) return;
    try {
      await api('api/admin/skills/delete', {
        method: 'POST',
        body: JSON.stringify({ id })
      });
      setStatus(`推荐 Skill 已删除：${id}`, 'ok');
      newAdminSkill();
      await loadAdminSkills();
    } catch (err) {
      setStatus(err.message || String(err), 'err');
    }
  }

  function renderAudit(events) {
    const table = $('auditTable');
    table.innerHTML = '<div class="audit-row head"><span>时间</span><span>用户</span><span>工具</span><span>档位</span><span>连接 / 意图</span><span>状态</span></div>';
    if (!events.length) {
      table.insertAdjacentHTML('beforeend', '<div class="audit-row"><span>暂无审计事件</span><span></span><span></span><span></span><span></span><span></span></div>');
      return;
    }
    events.slice().reverse().forEach(ev => {
      const profile = ev.data_profile || {};
      const privacy = (profile.privacy_levels || [])[0] || '';
      const row = document.createElement('div');
      row.className = 'audit-row';
      row.innerHTML = [
        ev.ts || '',
        ev.user_id || '',
        ev.tool_name || '',
        ev.model_tier || '',
        `${(profile.connector_ids || []).join(', ') || profile.category || ''} · ${profile.intent || 'unknown'}`,
        ev.status || ''
      ].map(v => `<span title="${escapeHtml(v)}">${escapeHtml(v)}</span>`).join('');
      if (privacy) row.children[4].innerHTML += ` <span class="pill ${privacy === 'public' ? 'public' : 'private'}">${escapeHtml(privacy)}</span>`;
      table.appendChild(row);
    });
  }

  function addConnector() {
    state.policy = readFormIntoPolicy();
    state.policy.data_connectors.connectors.push({
      id: `connector-${state.policy.data_connectors.connectors.length + 1}`,
      type: 'clickhouse',
      enabled: true,
      privacy_level: 'private',
      access_mode: 'read-only',
      readonly: true,
      host: '',
      port: '',
      database: '',
      user: 'readonly',
      password: '',
      mcp: { enabled: false, server_name: '', command: '', args: [], env: { CLICKHOUSE_READONLY: '1' } }
    });
    renderAll();
  }

  function addDifyStation() {
    state.policy = readFormIntoPolicy();
    state.policy.dify_knowledge.stations.push({
      enabled: true,
      station_id: '',
      station_name: '',
      dataset_id: '',
      tags: []
    });
    renderAll();
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  function bind() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
        btn.classList.add('active');
        $(`section-${btn.dataset.section}`).classList.add('active');
      });
    });
    $('reloadBtn').addEventListener('click', () => reloadAdminData().catch(err => setStatus(err.message, 'err')));
    $('saveBtn').addEventListener('click', savePolicy);
    $('applyAllBtn').addEventListener('click', rebuildAllUserRuntimes);
    $('addConnectorBtn').addEventListener('click', addConnector);
    $('addDifyStationBtn').addEventListener('click', addDifyStation);
    $('reloadSkillsBtn').addEventListener('click', loadAdminSkills);
    $('newSkillBtn').addEventListener('click', newAdminSkill);
    $('saveSkillBtn').addEventListener('click', saveAdminSkill);
    $('deleteSkillBtn').addEventListener('click', deleteAdminSkill);
    $('importGithubSkillBtn').addEventListener('click', importGithubSkills);
    $('reloadUsersBtn').addEventListener('click', loadAdminUsers);
    $('newUserBtn').addEventListener('click', newAdminUser);
    $('saveUserBtn').addEventListener('click', saveAdminUser);
    $('rebuildUserRuntimeBtn').addEventListener('click', () => rebuildUserRuntime());
    $('deleteUserBtn').addEventListener('click', deleteAdminUser);
    $('deleteUserDataBtn').addEventListener('click', deleteAdminUserData);
    $('loadAuditBtn').addEventListener('click', loadAudit);
    $('formatJsonBtn').addEventListener('click', () => {
      try {
        $('rawJson').value = JSON.stringify(JSON.parse($('rawJson').value), null, 2);
        setStatus('JSON 已格式化。', 'ok');
      } catch (err) {
        setStatus(`JSON 格式错误：${err.message}`, 'err');
      }
    });
    document.querySelectorAll('input,select').forEach(el => {
      if (el.closest('#connectorsList') || el.id === 'adminToken') return;
      el.addEventListener('change', () => {
        if (!state.policy) return;
        state.policy = readFormIntoPolicy();
        $('rawJson').value = JSON.stringify(state.policy, null, 2);
        renderMetricsOnly();
      });
    });
    const savedToken = sessionStorage.getItem('hermes-admin-token') || '';
    if (savedToken) $('adminToken').value = savedToken;
    $('adminToken').addEventListener('change', () => {
      sessionStorage.setItem('hermes-admin-token', $('adminToken').value.trim());
      reloadAdminData().catch(err => setStatus(err.message, 'err'));
    });
  }

  bind();
  reloadAdminData().catch(err => setStatus(err.message || String(err), 'err'));
})();
