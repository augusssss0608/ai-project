// overview/static/app.js — 总览 tab 特有交互 (count-up 数字动画)
(function(){
  const easeOut = t => 1 - Math.pow(1 - t, 3);

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

  // ===== Owner Bay → Event Stream 过滤 =====
  const slots = document.querySelectorAll('.owner-slot');
  const rows = document.querySelectorAll('.stream-row');
  let activeOwner = '';

  function applyFilter(owner){
    rows.forEach(r => {
      const match = !owner || r.dataset.owner === owner;
      r.dataset.hidden = match ? 'false' : 'true';
    });
    slots.forEach(s => {
      const on = s.dataset.owner === owner;
      s.classList.toggle('active', on);
      s.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }

  slots.forEach(slot => {
    slot.addEventListener('click', e => {
      e.preventDefault();
      const owner = slot.dataset.owner;
      activeOwner = (activeOwner === owner) ? '' : owner;
      applyFilter(activeOwner);
    });
  });

  // (".risk-more" 已移除: cold list 改用 scroll, 不再展开)

})();
