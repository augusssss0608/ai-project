// overview/static/app.js — 总览 tab 特有交互 (count-up 数字动画)
(function(){
  // ===== count-up 动画 =====
  document.querySelectorAll('[data-countup]').forEach(el => {
    const target = parseInt(el.dataset.countup, 10) || 0;
    const duration = 800;
    const start = performance.now();
    function tick(now) {
      const p = Math.min((now - start) / duration, 1);
      el.textContent = Math.floor(easeOut(p) * target).toLocaleString();
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  });

  // 当前激活的 owner
  let currentOwner = '';

  // (".risk-more" 已移除: cold list 改用 scroll, 不再展开)

})();
