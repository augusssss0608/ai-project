// shared/static/base.js — 跨 tab 共享基础设施
(function(){
  const flipOpenOrder = [];  // 翻开卡片的记录, 切 tab/filter 时统一复原

  function showToast(msg, kind) {
    let toast = document.querySelector('.toast');
    if (!toast) {
      toast = document.createElement('div');
      toast.className = 'toast';
      document.body.appendChild(toast);
    }
    toast.textContent = msg;
    toast.className = 'toast ' + (kind || '');
    toast.style.display = 'block';
    setTimeout(() => { toast.style.display = 'none'; }, 2500);
  }

  // ===== Tab 切换 =====
  function activateTab(tabId, pushHistory) {
    if (!tabId) return;
    // 切 tab 前復原所有翻開的卡片
    if (typeof resetAllFlips === 'function') resetAllFlips();
    const tabs = document.querySelectorAll('.tab-bar .tab');
    const contents = document.querySelectorAll('.tab-content');
    let found = false;
    tabs.forEach(t => {
      const match = t.dataset.tab === tabId;
      t.classList.toggle('active', match);
      if (match) found = true;
    });
    if (!found) return;
    contents.forEach(c => {
      const match = c.dataset.tab === tabId;
      c.classList.toggle('active', match);
      if (match) {
        c.querySelectorAll('details.section.collapsible[data-default-open]').forEach(d => {
          d.open = true;
        });
      }
    });
    // URL hash: 用戶點擊時推歷史棧, 初始化/popstate 只替換
    if (location.hash !== '#' + tabId) {
      if (pushHistory) {
        history.pushState({ tab: tabId }, '', '#' + tabId);
      } else {
        history.replaceState({ tab: tabId }, '', '#' + tabId);
      }
    }
    // 通知各 tab 内部模块 (如 ai_news/app.js): 本次激活了哪个 tab
    document.dispatchEvent(new CustomEvent('app:tabchange', { detail: { tabId } }));
  }

  document.querySelectorAll('.tab-bar .tab').forEach(tab => {
    tab.addEventListener('click', e => {
      e.preventDefault();
      activateTab(tab.dataset.tab, true);
    });
  });

  // 支持浏览器前进后退 (popstate 不再推歷史, 否則會無限循環)
  window.addEventListener('popstate', () => {
    const id = location.hash.replace('#', '');
    if (id) activateTab(id, false);
  });

  // 初始化: 从 URL hash 读取当前 tab (不推歷史)
  const initialTab = location.hash.replace('#', '');
  if (initialTab) activateTab(initialTab, false);

  // 時間 pills 是 <a href>, 會整頁刷新 — 點擊時保留當前 tab hash
  document.addEventListener('click', e => {
    const pill = e.target.closest('.time-pills .pill');
    if (!pill || !location.hash) return;
    e.preventDefault();
    location.href = pill.getAttribute('href') + location.hash;
  });

  // ===== 卡片翻面 controller (Phase 0) - 無上限 =====
  function flipCard(card, on) {
    if (on) {
      if (card.classList.contains('flipped')) return;
      card.classList.add('flipped');
      flipOpenOrder.push(card);
    } else {
      card.classList.remove('flipped');
      const idx = flipOpenOrder.indexOf(card);
      if (idx !== -1) flipOpenOrder.splice(idx, 1);
    }
  }

  function resetAllFlips() {
    flipOpenOrder.forEach(c => c.classList.remove('flipped'));
    flipOpenOrder.length = 0;
  }

  // 整张卡点击翻面 (任何 tab 的 .flip-card 都生效)
  const FLIP_EXCLUDE_SELECTOR = 'a, input, select, textarea, button:not(.flip-btn), .archive-btn, .pill, .owner-chip, .owner-tag, .open-link, .sheet-btn, .summary-meter, .prune-dot';
  document.addEventListener('click', e => {
    const card = e.target.closest('.flip-card');
    if (!card) return;
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

  // ===== Sheet 抽屜 (Memory/Compact 統計) =====
  // 啟動時把 .sheet 移到 body, 逃離 .tab-content 的 transform context (否則 position:fixed 失效)
  document.querySelectorAll('.sheet').forEach(s => document.body.appendChild(s));

  let sheetOverlay = null;
  function ensureOverlay() {
    if (sheetOverlay) return sheetOverlay;
    sheetOverlay = document.createElement('div');
    sheetOverlay.className = 'sheet-overlay';
    document.body.appendChild(sheetOverlay);
    sheetOverlay.addEventListener('click', closeAllSheets);
    return sheetOverlay;
  }
  function closeAllSheets() {
    document.querySelectorAll('.sheet.open').forEach(s => s.classList.remove('open'));
    if (sheetOverlay) sheetOverlay.classList.remove('show');
  }
  document.addEventListener('click', e => {
    const sb = e.target.closest('.sheet-btn');
    if (sb) {
      e.preventDefault();
      const target = document.getElementById(sb.dataset.sheetTarget);
      if (target) {
        closeAllSheets();
        ensureOverlay().classList.add('show');
        target.classList.add('open');
      }
      return;
    }
    if (e.target.closest('.sheet-close')) {
      closeAllSheets();
    }
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeAllSheets();
  });

  // ===== open-link 點擊在後台調用 /open, 不跳頁 =====
  document.addEventListener('click', async e => {
    const a = e.target.closest('a.open-link');
    if (!a) return;
    e.preventDefault();
    e.stopPropagation();
    const url = a.getAttribute('href');
    const name = a.textContent || '';
    try {
      const res = await fetch(url, { method: 'GET' });
      if (res.ok) {
        showToast(`✓ 已在 Mac 打开 ${name}`, 'success');
      } else {
        const text = await res.text().catch(() => '');
        showToast(`✗ 打开失败: ${text || res.status}`, 'error');
      }
    } catch (err) {
      showToast(`✗ 网络错误: ${err.message}`, 'error');
    }
  });

  // ===== 全域浮動 tooltip (逃離 overflow 裁剪) =====
  const tooltip = document.createElement('div');
  tooltip.id = 'global-tooltip';
  document.body.appendChild(tooltip);

  // session 內存緩存: path -> summary (避免同一 hover 元素重複 fetch)
  const summaryMemCache = new Map();

  let activeTarget = null;
  let activeSummaryPath = null;
  let hoverDelayTimer = null;
  const HOVER_DELAY_MS = 400;
  function positionTooltip(evt) {
    const pad = 12;
    const rect = tooltip.getBoundingClientRect();
    let x = evt.clientX + pad;
    let y = evt.clientY + pad;
    if (x + rect.width + pad > window.innerWidth) x = evt.clientX - rect.width - pad;
    if (y + rect.height + pad > window.innerHeight) y = evt.clientY - rect.height - pad;
    if (x < pad) x = pad;
    if (y < pad) y = pad;
    tooltip.style.transform = `translate(${x}px,${y}px)`;
  }

  function updateFooterStatus(quota, cacheSize) {
    if (quota) {
      const c = document.getElementById('summary-count');
      if (c) c.textContent = quota.count;
      const l = document.getElementById('summary-limit');
      if (l && quota.limit) l.textContent = quota.limit;
    }
    if (typeof cacheSize === 'number') {
      const cs = document.getElementById('summary-cache-size');
      if (cs) cs.textContent = cacheSize;
    }
  }

  async function refreshSummaryStatus() {
    try {
      const res = await fetch('/summary-status');
      const s = await res.json();
      updateFooterStatus({count: s.count, limit: s.limit}, s.cache_size);
    } catch (e) {}
  }

  // 頁面可見時每 5 秒輪詢狀態, 看不見就停 (省資源)
  let statusPollTimer = null;
  function startStatusPoll() {
    if (statusPollTimer) return;
    statusPollTimer = setInterval(refreshSummaryStatus, 3000);
  }
  function stopStatusPoll() {
    if (statusPollTimer) {
      clearInterval(statusPollTimer);
      statusPollTimer = null;
    }
  }
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stopStatusPoll();
    else { refreshSummaryStatus(); startStatusPoll(); }
  });
  startStatusPoll();
  // 頁面打開後立刻拉一次, 處理「reload 時 generation 還在跑」的狀態
  refreshSummaryStatus();

  async function fetchSummary(path) {
    if (summaryMemCache.has(path)) return summaryMemCache.get(path);
    const url = '/summary?path=' + encodeURIComponent(path);
    try {
      const res = await fetch(url);
      const data = await res.json();
      if (data.quota) updateFooterStatus(data.quota);
      if (data.ok && data.summary) {
        summaryMemCache.set(path, data.summary);
        // 只有 server 真的 cache miss (新生成) 才 +1; cache hit 不變
        if (data.cached === false) {
          const cs = document.getElementById('summary-cache-size');
          if (cs) cs.textContent = (parseInt(cs.textContent, 10) || 0) + 1;
        }
        return data.summary;
      }
      return data.error ? `(生成失败: ${data.error})` : '(无摘要)';
    } catch (err) {
      return `(网络错误: ${err.message})`;
    }
  }

  // 清理缓存按钮
  const clearBtn = document.getElementById('clear-summary-cache-btn');
  if (clearBtn) {
    clearBtn.addEventListener('click', async () => {
      if (!confirm('确认清空 AI 摘要缓存? 下次 hover 会重新生成')) return;
      clearBtn.disabled = true;
      try {
        const res = await fetch('/clear-summary-cache', {method: 'POST'});
        const data = await res.json();
        if (data.ok) {
          summaryMemCache.clear();
          const cs = document.getElementById('summary-cache-size');
          if (cs) cs.textContent = '0';
          showToast(`✓ 已清空 ${data.cleared} 项缓存`, 'success');
        } else {
          showToast(`✗ 清空失败: ${data.error || ''}`, 'error');
        }
      } catch (err) {
        showToast(`✗ 网络错误: ${err.message}`, 'error');
      }
      clearBtn.disabled = false;
    });
  }

  document.addEventListener('mouseover', e => {
    const el = e.target.closest('[data-tip],[data-summary]');
    if (!el) return;
    activeTarget = el;
    const summaryPath = el.getAttribute('data-summary');
    if (summaryPath) {
      activeSummaryPath = summaryPath;
      // 已有緩存 → 立刻顯示, 跳過 delay
      if (summaryMemCache.has(summaryPath)) {
        tooltip.textContent = summaryMemCache.get(summaryPath);
        tooltip.classList.add('show');
        positionTooltip(e);
        return;
      }
      // 無緩存 → 等 400ms 確認 hover 意圖, 再觸發 fetch
      tooltip.textContent = '⋯';
      tooltip.classList.add('show');
      positionTooltip(e);
      if (hoverDelayTimer) clearTimeout(hoverDelayTimer);
      hoverDelayTimer = setTimeout(async () => {
        if (activeTarget !== el || activeSummaryPath !== summaryPath) return;
        tooltip.textContent = '⋯ 正在生成摘要';
        positionTooltip(e);
        const summary = await fetchSummary(summaryPath);
        if (activeTarget === el && activeSummaryPath === summaryPath) {
          tooltip.textContent = summary;
          positionTooltip(e);
        }
      }, HOVER_DELAY_MS);
    } else {
      activeSummaryPath = null;
      tooltip.textContent = el.getAttribute('data-tip') || '';
      tooltip.classList.add('show');
      positionTooltip(e);
    }
  });
  document.addEventListener('mousemove', e => {
    if (activeTarget && tooltip.classList.contains('show')) positionTooltip(e);
  });
  document.addEventListener('mouseout', e => {
    const el = e.target.closest('[data-tip],[data-summary]');
    if (el && el === activeTarget) {
      activeTarget = null;
      activeSummaryPath = null;
      if (hoverDelayTimer) {
        clearTimeout(hoverDelayTimer);
        hoverDelayTimer = null;
      }
      tooltip.classList.remove('show');
    }
  });

  // 对外暴露共享 API
  window.__dashboard = Object.assign(window.__dashboard||{}, {
    flipOpenOrder,
    showToast,
    flipCard,
  });
})();
