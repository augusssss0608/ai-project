// usage/static/app.js — 工具使用 tab 特有交互
(function(){
  // 引用 base 导出的共享状态
  const D = (window.__dashboard = window.__dashboard||{});
  const showToast = (...a) => D.showToast && D.showToast(...a);
  const flipOpenOrder = D.flipOpenOrder || [];

  // ===== 纯客户端 owner 过滤 (瞬时, 无 fetch, 无闪烁) =====
  function applyFilter(owner) {
    currentOwner = owner;
    // 過濾條件變化時自動復原所有翻開卡片, 避免背面數據與前面 owner 不一致
    if (typeof flipOpenOrder !== 'undefined' && flipOpenOrder.length > 0) {
      flipOpenOrder.forEach(c => c.classList.remove('flipped'));
      flipOpenOrder.length = 0;
    }
    // chip 高亮
    document.querySelectorAll('.owner-chip').forEach(c => {
      c.classList.toggle('active', (c.dataset.owner || '') === owner);
    });
    // 过滤 active rows
    document.querySelectorAll('.active-card').forEach(card => {
      const rows = card.querySelectorAll('.row');
      let visible = 0;
      rows.forEach(r => {
        const match = !owner || r.dataset.owner === owner;
        r.style.display = match ? '' : 'none';
        if (match) visible++;
      });
      // 更新 count
      const cnt = card.querySelector('.active-count');
      if (cnt) cnt.textContent = visible + ' 个';
      // 空状态提示
      const emptyNote = card.querySelector('.empty-note');
      if (visible === 0 && !emptyNote) {
        const note = document.createElement('div');
        note.className = 'empty-note js-empty';
        note.textContent = '(此范围内无数据)';
        card.appendChild(note);
      } else if (visible > 0) {
        const js = card.querySelector('.js-empty');
        if (js) js.remove();
      }
    });
    // 过滤 cold items
    document.querySelectorAll('.risk').forEach(risk => {
      const items = risk.querySelectorAll('.risk-list li[data-owner]');
      let visible = 0;
      items.forEach(li => {
        const match = !owner || li.dataset.owner === owner;
        li.dataset.visible = match ? '1' : '0';
        if (match) visible++;
      });
      // 更新 risk-count
      const rc = risk.querySelector('.risk-count');
      if (rc) {
        const total = items.length;
        rc.textContent = visible + ' / ' + total;
      }
      // 更新 risk-bar 宽度
      const bar = risk.querySelector('.risk-bar-fill');
      if (bar && items.length > 0) {
        const pct = (visible / items.length) * 100;
        bar.style.width = pct.toFixed(0) + '%';
      }
      // 更新严重度 class
      if (items.length > 0) {
        const ratio = visible / items.length;
        risk.classList.remove('high','mid','low');
        if (ratio >= 0.7) risk.classList.add('high');
        else if (ratio >= 0.3) risk.classList.add('mid');
        else risk.classList.add('low');
      }
      // 直接显示/隐藏匹配项 (cold list 是 scroll 容器, 无 expand 概念)
      items.forEach(li => {
        li.style.display = li.dataset.visible === '1' ? '' : 'none';
      });
    });
    // URL 更新由调用方决定 (chip click vs popstate vs init)
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

  // chip 点击: 整页 reload 让 server 端重算 back face (前端 hide 不夠, 翻面數據需要 server 過濾)
  document.querySelectorAll('.owner-chip').forEach(chip => {
    chip.addEventListener('click', e => {
      e.preventDefault();
      const owner = chip.dataset.owner || '';
      const u = new URL(location.href);
      if (owner) u.searchParams.set('owner', owner);
      else u.searchParams.delete('owner');
      // 保留當前 tab hash; URL 物件處理 hash, 不要再字串拼接以免重複
      if (!u.hash) u.hash = '#usage';
      location.href = u.toString();
    });
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

  // ===== 禁用/启用按钮点击 =====
  async function toggleArchive(btn) {
    const action = btn.dataset.action || 'archive';
    const type = btn.dataset.type;
    const name = btn.dataset.name;
    const scope = btn.dataset.scope;
    if (!type || !name || !scope) return;
    const verb = action === 'archive' ? '禁用' : '启用';
    if (!confirm(`确认${verb} ${type}: ${name} [${scope}]?`)) return;
    const body = new URLSearchParams({ type, name, scope }).toString();
    const origLabel = btn.textContent;
    btn.disabled = true;
    btn.textContent = '处理中...';
    try {
      const res = await fetch('/' + action, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      });
      const data = await res.json();
      if (data.ok) {
        // 成功: 切换按钮状态, li 保留
        if (action === 'archive') {
          btn.dataset.action = 'restore';
          btn.textContent = '启用';
          btn.classList.add('restored');
          btn.closest('li').classList.add('disabled-item');
          showToast(`✓ ${name} 已禁用`, 'success');
        } else {
          btn.dataset.action = 'archive';
          btn.textContent = '禁用';
          btn.classList.remove('restored');
          btn.closest('li').classList.remove('disabled-item');
          showToast(`✓ ${name} 已启用`, 'success');
        }
        btn.disabled = false;
      } else {
        btn.disabled = false;
        btn.textContent = origLabel;
        showToast(`✗ ${data.error || data.message}`, 'error');
      }
    } catch (err) {
      btn.disabled = false;
      btn.textContent = origLabel;
      showToast(`✗ 网络错误: ${err.message}`, 'error');
    }
  }

  // (showToast 迁到 shared/static/base.js, 通过 window.__dashboard.showToast 访问)

  // 事件委托: 捕获所有 .archive-btn 点击
  document.addEventListener('click', e => {
    const btn = e.target.closest('.archive-btn');
    if (btn) {
      e.preventDefault();
      toggleArchive(btn);
    }
  });

  // ===== 行 name 溢出时 hover 触发跑马灯 =====
  document.addEventListener('pointerover', e => {
    const row = e.target.closest && e.target.closest('.active-card .row');
    if (!row) return;
    const name = row.querySelector('.name');
    if (!name || name.classList.contains('marquee')) return;
    if (name.scrollWidth > name.clientWidth + 2) {
      const shift = -(name.scrollWidth - name.clientWidth + 12);
      name.style.setProperty('--marquee-shift', shift + 'px');
      name.classList.add('marquee');
    }
  });
  document.addEventListener('pointerout', e => {
    const row = e.target.closest && e.target.closest('.active-card .row');
    if (!row) return;
    // 离开整行才停, 否则在 row 内子元素间移动会闪
    if (e.relatedTarget && row.contains(e.relatedTarget)) return;
    const name = row.querySelector('.name');
    if (name) {
      name.classList.remove('marquee');
      name.style.removeProperty('--marquee-shift');
    }
  });

  // ===== 一键批量禁用 (背面操作按钮) =====
  document.addEventListener('click', async e => {
    const btn = e.target.closest('[data-bulk-disable]');
    if (!btn) return;
    e.preventDefault();
    if (!confirm('确认一键禁用此分类下所有冷藏项? 此操作可逆 (.disabled/ 目录)')) return;
    showToast('批量禁用功能开发中', 'error');
    // TODO: 后端 endpoint 实现, 当前只做 UI 占位
  });

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

})();
