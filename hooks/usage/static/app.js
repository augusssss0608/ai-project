// usage/static/app.js — 工具使用 tab 特有交互
(function(){
  // 引用 base 导出的共享状态
  const D = (window.__dashboard = window.__dashboard||{});
  const showToast = (...a) => D.showToast && D.showToast(...a);
  const flipOpenOrder = D.flipOpenOrder || [];

  // ===== 纯客户端 owner 过滤（F 方案：只过 funnel-row） =====
  function applyFilter(owner) {
    // 过滤所有 funnel-row
    document.querySelectorAll('.funnel-row[data-owner]').forEach(row => {
      const match = !owner || row.dataset.owner === owner;
      row.style.display = match ? '' : 'none';
    });
    // 高亮当前激活的 owner tag
    document.querySelectorAll('.owner-filter-trigger').forEach(t => {
      t.classList.toggle('owner-filter-active',
        !!owner && t.dataset.ownerFilter === owner);
    });
    updateActiveChip(owner);
  }

  function updateActiveChip(owner) {
    let chip = document.querySelector('.owner-active-chip');
    if (owner) {
      if (!chip) {
        const row = document.querySelector('.tab-controls .control-row');
        if (!row) return;
        chip = document.createElement('a');
        chip.className = 'owner-active-chip';
        chip.href = '#';
        chip.innerHTML = '筛选: <b></b><span class="owner-active-clear">✕</span>';
        row.appendChild(chip);
      }
      chip.querySelector('b').textContent = owner;
    } else if (chip) {
      chip.remove();
    }
  }

  function setOwnerFilter(owner) {
    const u = new URL(location.href);
    if (owner) u.searchParams.set('owner', owner);
    else u.searchParams.delete('owner');
    if (!u.hash) u.hash = '#usage';
    history.replaceState({owner}, '', u.toString());
    applyFilter(owner);
  }

  // URL 状态管理 (pushState + popstate 支持浏览器前进后退)
  function updateUrl(owner, pushHistory) {
    const u = new URL(location.href);
    if (owner) u.searchParams.set('owner', owner);
    else u.searchParams.delete('owner');
    const next = u.toString();
    if (pushHistory && next !== location.href) {
      history.pushState({ owner }, '', next);
    } else {
      history.replaceState({ owner }, '', next);
    }
  }

  // spark-row 内的 owner-tag 点击 = 设置筛选；再次点击同一 owner = 清除（纯客户端，不刷新）
  document.addEventListener('click', e => {
    // 顶部「筛选 X ✕」chip 点击清除
    if (e.target.closest('.owner-active-chip')) {
      e.preventDefault();
      setOwnerFilter('');
      return;
    }
    const tag = e.target.closest('.owner-filter-trigger[data-owner-filter]');
    if (!tag) return;
    e.preventDefault();
    e.stopPropagation();
    const owner = tag.dataset.ownerFilter || '';
    const cur = new URL(location.href).searchParams.get('owner') || '';
    setOwnerFilter(cur === owner ? '' : owner);
  });

  // 浏览器后退/前进: 从 URL 读取 owner 重新应用 (不再推历史)
  window.addEventListener('popstate', () => {
    const u = new URL(location.href);
    const owner = u.searchParams.get('owner') || '';
    applyFilter(owner);
  });

  // 初始化: 优先从 URL 读取, 否则从 body data-owner (SSR 注入)
  const urlOwner = new URL(location.href).searchParams.get('owner') || '';
  const initialOwner = urlOwner || document.body.dataset.initialOwner || '';
  applyFilter(initialOwner);

  // ===== owner-tag 點擊複製完整路徑 =====
  document.addEventListener('click', async e => {
    const tag = e.target.closest('.owner-tag[data-tip]');
    if (!tag) return;
    e.preventDefault();
    e.stopPropagation();
    const path = tag.getAttribute('data-tip');
    if (!path) return;
    try {
      await navigator.clipboard.writeText(path);
      showToast('✓ 已复制路径', 'success');
    } catch (err) {
      // fallback: 老瀏覽器或非 HTTPS 環境
      const ta = document.createElement('textarea');
      ta.value = path;
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand('copy');
        showToast('✓ 已复制路径', 'success');
      } catch (e2) {
        showToast('✗ 复制失败', 'error');
      }
      document.body.removeChild(ta);
    }
  });

  // ===== F 方案：概览表交互（状态 chip + 行展开 + 表头数字快捷） =====
  const ovTable = document.getElementById('overview-table');
  const ovFilter = document.getElementById('overview-status-filter');

  function setStatusFilter(target) {
    target = target || '';
    if (ovFilter) {
      ovFilter.querySelectorAll('.pill[data-funnel-status]').forEach(c => {
        c.classList.toggle('active', (c.dataset.funnelStatus || '') === target);
      });
    }
    // 过滤所有 funnel-row
    document.querySelectorAll('.funnel-row').forEach(row => {
      const rowStatus = row.dataset.funnelStatus || '';
      // "全部"(空 target) 不含停用项; 选定状态时精确匹配(含"停用")
      const matchStatus = target ? (target === rowStatus) : (rowStatus !== 'disabled');
      row.classList.toggle('row-funnel-hidden', !matchStatus);
    });
    // 概览表：每个类别根据该状态命中数更新 dim 状态；有命中的自动展开
    if (ovTable) {
      ovTable.querySelectorAll('tr.ov-summary-row').forEach(row => {
        const kind = row.dataset.kind;
        let hits;
        if (!target) {
          hits = parseInt(row.dataset.paired||0) + parseInt(row.dataset.readOnly||0)
               + parseInt(row.dataset.explicitOnly||0) + parseInt(row.dataset.cold||0);
        } else {
          // dataset 名: read-only -> readOnly, explicit-only -> explicitOnly
          const key = target.replace(/-([a-z])/g, (_,c)=>c.toUpperCase());
          hits = parseInt(row.dataset[key]||0);
        }
        row.classList.toggle('ov-dim', !!target && hits === 0);
        const detail = row.nextElementSibling;
        if (!detail || !detail.classList.contains('ov-detail-row')) return;
        if (target && hits > 0) {
          // 自动展开有命中的类别
          detail.style.display = '';
          row.classList.add('ov-expanded');
          const chevron = row.querySelector('.ov-chevron');
          if (chevron) chevron.textContent = '▼';
        } else if (!target) {
          // 取消过滤回到默认全折叠（不主动收起，保留用户已展开的）
          // → 不改 detail.display
        } else {
          // 该状态命中=0，折叠
          detail.style.display = 'none';
          row.classList.remove('ov-expanded');
          const chevron = row.querySelector('.ov-chevron');
          if (chevron) chevron.textContent = '▶';
        }
      });
    }
  }

  if (ovFilter) {
    ovFilter.addEventListener('click', e => {
      const chip = e.target.closest('.pill[data-funnel-status]');
      if (!chip) return;
      e.preventDefault();
      setStatusFilter(chip.dataset.funnelStatus || '');
    });
    // 初始应用"全部"过滤, 让停用项默认不出现在列表里
    setStatusFilter('');
  }

  // 行展开 / 折叠：点击 ov-summary-row 任意位置（除非点的是可点数字）
  if (ovTable) {
    ovTable.addEventListener('click', e => {
      // 表头数字快捷：点 used / cold 数字 = 切换到对应状态 chip
      const numCell = e.target.closest('td.ov-clickable[data-jump-status]');
      if (numCell) {
        e.preventDefault();
        e.stopPropagation();
        setStatusFilter(numCell.dataset.jumpStatus);
        return;
      }
      const row = e.target.closest('tr.ov-summary-row');
      if (!row) return;
      const detail = row.nextElementSibling;
      if (!detail || !detail.classList.contains('ov-detail-row')) return;
      const willOpen = detail.style.display === 'none';
      detail.style.display = willOpen ? '' : 'none';
      row.classList.toggle('ov-expanded', willOpen);
      const chevron = row.querySelector('.ov-chevron');
      if (chevron) chevron.textContent = willOpen ? '▼' : '▶';
    });
  }

  // ===== 列头排序：3 态循环 none → asc → desc → none，每个 spark-list 独立维护 =====
  function sortList(list, key, dir) {
    const rows = Array.from(list.querySelectorAll('.spark-row'));
    const cmp = (a, b) => {
      let va, vb;
      if (dir === 'none' || !key) {
        va = parseInt(a.dataset.origIdx || '0', 10);
        vb = parseInt(b.dataset.origIdx || '0', 10);
        return va - vb;
      }
      if (key === 'status') {
        va = parseInt(a.dataset.statusSev || '9', 10);
        vb = parseInt(b.dataset.statusSev || '9', 10);
      } else if (key === 'total') {
        va = parseInt(a.dataset.total || '0', 10);
        vb = parseInt(b.dataset.total || '0', 10);
      } else if (key === 'last') {
        va = a.dataset.lastTs || '';
        vb = b.dataset.lastTs || '';
      } else if (key === 'name') {
        va = a.dataset.name || '';
        vb = b.dataset.name || '';
      } else if (key === 'owner') {
        va = a.dataset.owner || '';
        vb = b.dataset.owner || '';
      } else {
        return 0;
      }
      if (va < vb) return dir === 'asc' ? -1 : 1;
      if (va > vb) return dir === 'asc' ? 1 : -1;
      return 0;
    };
    rows.sort(cmp);
    const frag = document.createDocumentFragment();
    rows.forEach(r => frag.appendChild(r));
    list.appendChild(frag);
  }

  document.addEventListener('click', e => {
    const hdr = e.target.closest('.spark-header .sortable');
    if (!hdr) return;
    e.preventDefault();
    const headerEl = hdr.parentElement;
    const list = headerEl.nextElementSibling;
    if (!list || !list.classList.contains('spark-list')) return;
    const key = hdr.dataset.sort;
    // 3 态循环：none → asc → desc → none
    const cur = hdr.classList.contains('sort-asc') ? 'asc'
              : hdr.classList.contains('sort-desc') ? 'desc'
              : 'none';
    const nextDir = cur === 'none' ? 'asc'
                  : cur === 'asc'  ? 'desc'
                  :                  'none';
    // 重置同 header 内所有 sortable 的状态
    headerEl.querySelectorAll('.sortable').forEach(s => {
      s.classList.remove('sort-asc', 'sort-desc');
      const ind = s.querySelector('.sort-ind');
      if (ind) ind.textContent = '⇅';
    });
    if (nextDir !== 'none') {
      hdr.classList.add('sort-' + nextDir);
      const ind = hdr.querySelector('.sort-ind');
      if (ind) ind.textContent = nextDir === 'asc' ? '▲' : '▼';
    }
    sortList(list, key, nextDir);
  });

  // ===== 详细按钮：点击切换弹出面板（一次只开一个） =====
  function closeAllDetailPops() {
    document.querySelectorAll('.spark-detail-pop.show').forEach(p => p.classList.remove('show'));
    document.querySelectorAll('.spark-detail-btn.active').forEach(b => b.classList.remove('active'));
  }
  document.addEventListener('click', e => {
    const btn = e.target.closest('.spark-detail-btn');
    if (btn) {
      e.preventDefault();
      e.stopPropagation();
      const pop = btn.parentElement.querySelector('.spark-detail-pop');
      const isOpen = pop && pop.classList.contains('show');
      closeAllDetailPops();
      if (!isOpen && pop) {
        pop.classList.add('show');
        btn.classList.add('active');
      }
      return;
    }
    // 点击面板内部不关闭
    if (e.target.closest('.spark-detail-pop')) return;
    // 点击其它地方关闭
    closeAllDetailPops();
  });

})();
