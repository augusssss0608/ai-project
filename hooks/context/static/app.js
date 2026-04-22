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
