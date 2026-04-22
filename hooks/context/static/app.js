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
    // 排除 'prune-dot' 自身, 只匹配 prune-high / prune-mid / prune-low
    const matched = Array.from(dot.classList).find(c => c === 'prune-high' || c === 'prune-mid' || c === 'prune-low');
    if (!matched) return;
    const bucket = matched.replace('prune-', '');
    const current = card.dataset.pruneFilter || '';
    if (current === bucket) {
      // 再次點擊 → 取消篩選
      delete card.dataset.pruneFilter;
      card.querySelectorAll('.prune-dot.active-filter').forEach(d => d.classList.remove('active-filter'));
    } else {
      // 套用新篩選
      card.dataset.pruneFilter = bucket;
      card.querySelectorAll('.prune-dot.active-filter').forEach(d => d.classList.remove('active-filter'));
      card.querySelectorAll(`.prune-dot.prune-${bucket}`).forEach(d => d.classList.add('active-filter'));
    }
  });

  // 整張卡點擊翻面 (排除卡片內互動元素)
  const FLIP_EXCLUDE_SELECTOR = 'a, input, select, textarea, button:not(.flip-btn), .archive-btn, .pill, .owner-chip, .owner-tag, .open-link, .sheet-btn, .summary-meter, .prune-dot';
  document.addEventListener('click', e => {
    const card = e.target.closest('.flip-card');
    if (!card) return;
    // 排除互動元素 (除非點的就是 .flip-btn 翻面按鈕本身)
    if (e.target.closest('.flip-btn')) {
      e.preventDefault();
      e.stopPropagation();
      flipCard(card, !card.classList.contains('flipped'));
      return;
    }
    if (e.target.closest(FLIP_EXCLUDE_SELECTOR)) return;
    e.preventDefault();
    flipCard(card, !card.classList.contains('flipped'));
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
