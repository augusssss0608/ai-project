// context/static/app.js — 上下文 tab 特有交互 (CLAUDE.md prune 工具)
(function(){
  const D = (window.__dashboard = window.__dashboard||{});
  const showToast = (...a) => D.showToast && D.showToast(...a);

  // ===== Prune dot 點擊篩選 (CLAUDE.md sections) =====
  document.addEventListener('click', e => {
    const dot = e.target.closest('.prune-dot');
    if (!dot) return;
    e.preventDefault();
    e.stopPropagation();
    const card = dot.closest('.claude-md-card');
    if (!card) return;
    const matched = Array.from(dot.classList).find(c => c === 'prune-high' || c === 'prune-mid' || c === 'prune-low');
    if (!matched) return;
    const bucket = matched.replace('prune-', '');
    const current = card.dataset.pruneFilter || '';
    if (current === bucket) {
      delete card.dataset.pruneFilter;
      card.querySelectorAll('.prune-dot.active-filter').forEach(d => d.classList.remove('active-filter'));
    } else {
      card.dataset.pruneFilter = bucket;
      card.querySelectorAll('.prune-dot.active-filter').forEach(d => d.classList.remove('active-filter'));
      card.querySelectorAll(`.prune-dot.prune-${bucket}`).forEach(d => d.classList.add('active-filter'));
    }
  });

  // ===== 路由 owner chip 点击过滤事件时间线 =====
  document.addEventListener('click', e => {
    const chip = e.target.closest('.owner-tag-clickable[data-owner-filter]');
    if (!chip) return;
    e.preventDefault();
    e.stopPropagation();  // 防止冒泡触发 details summary toggle
    const session = chip.closest('.routing-session');
    if (!session) return;
    const owner = chip.dataset.ownerFilter;
    const current = session.dataset.ownerFilter || '';
    const allChips = session.querySelectorAll('.owner-tag-clickable');
    const allRows = session.querySelectorAll('.routing-event');
    if (current === owner){
      // 取消过滤
      delete session.dataset.ownerFilter;
      allChips.forEach(c => c.setAttribute('aria-pressed','false'));
      allRows.forEach(r => { delete r.dataset.hidden; });
    } else {
      session.dataset.ownerFilter = owner;
      allChips.forEach(c => c.setAttribute('aria-pressed',
        c.dataset.ownerFilter === owner ? 'true' : 'false'));
      allRows.forEach(r => {
        r.dataset.hidden = (r.dataset.owner === owner) ? 'false' : 'true';
      });
    }
  });

  // ===== 切到路由 tab 时强制折叠所有 details =====
  function collapseAllRoutingDetails(){
    const ctx = document.querySelector('.tab-content[data-tab="context"]');
    if (!ctx) return;
    ctx.querySelectorAll('details.routing-session, details.routing-prompts')
       .forEach(d => { d.open = false; });
    // 同时清掉 chip 过滤状态
    ctx.querySelectorAll('.routing-session').forEach(s => {
      delete s.dataset.ownerFilter;
    });
    ctx.querySelectorAll('.owner-tag-clickable').forEach(c => {
      c.setAttribute('aria-pressed','false');
    });
    ctx.querySelectorAll('.routing-event[data-hidden]').forEach(r => {
      delete r.dataset.hidden;
    });
  }
  document.addEventListener('app:tabchange', e => {
    if (e.detail && e.detail.tabId === 'context') collapseAllRoutingDetails();
  });
  // 初次加载若 hash 直接进入 #context，也折叠（base.js 切换 tab 后会派 app:tabchange，
  // 但页面刷新前用户上次展开状态保存在 DOM 里——服务端 HTML 永远不带 open，所以已是折叠的）
  // 这里仅处理 SPA tab 切换场景，其他场景 server-side 渲染保证默认折叠

  // ===== 复制可删减清单 (CLAUDE.md 背面) =====
  document.addEventListener('click', async e => {
    const btn = e.target.closest('[data-copy-prune]');
    if (!btn) return;
    e.preventDefault();
    const path = btn.dataset.copyPrune;
    try {
      const res = await fetch('/prune-list?path=' + encodeURIComponent(path));
      const data = await res.json();
      if (data.ok && data.markdown) {
        await navigator.clipboard.writeText(data.markdown);
        showToast(`✓ 已复制 ${data.count} 个高收益段标题`, 'success');
      } else {
        showToast(`✗ ${data.error || '生成失败'}`, 'error');
      }
    } catch (err) {
      showToast(`✗ ${err.message}`, 'error');
    }
  });

})();
