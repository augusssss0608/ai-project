(function(){
  const easeOut = t => 1 - Math.pow(1 - t, 3);

  // ===== 翻面卡片狀態 (提前聲明避免 TDZ) =====
  const flipOpenOrder = [];  // 記錄翻開順序, 切 tab/filter 時統一復原

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

  // 事件委托: 捕获所有 .archive-btn 点击
  document.addEventListener('click', e => {
    const btn = e.target.closest('.archive-btn');
    if (btn) {
      e.preventDefault();
      toggleArchive(btn);
    }
  });

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

  // ===== 一键批量禁用 (背面操作按钮) =====
  document.addEventListener('click', async e => {
    const btn = e.target.closest('[data-bulk-disable]');
    if (!btn) return;
    e.preventDefault();
    if (!confirm('确认一键禁用此分类下所有冷藏项? 此操作可逆 (.disabled/ 目录)')) return;
    showToast('批量禁用功能开发中', 'error');
    // TODO: 后端 endpoint 实现, 当前只做 UI 占位
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
})();

// ===== 每日 AI 大事 tab: 展开/折叠 =====
(function setupNewsExpand(){
  document.querySelectorAll('.news-expand-btn').forEach(btn => {
    const hiddenCount = btn.dataset.newsExpand;
    btn.addEventListener('click', () => {
      const card = btn.closest('.news-card');
      if (!card) return;
      const isOpen = card.classList.toggle('expanded');
      btn.textContent = isOpen ? '收起' : `展开剩余 ${hiddenCount} 条`;
    });
  });
})();

// ===== 每日 AI 大事 tab: 三档投票 (👎/👍/⭐) =====
(function setupNewsVote(){
  document.querySelectorAll('.news-vote-btn').forEach(btn => {
    btn.addEventListener('click', async e => {
      e.preventDefault();
      const url = btn.dataset.voteUrl;
      const title = btn.dataset.voteTitle || '';
      const source = btn.dataset.voteSource || '';
      const score = btn.dataset.voteScore; // 'down' | 'up' | 'star'
      if (!url || !score) return;
      const item = btn.closest('.news-item');
      const group = btn.closest('.news-vote-group');
      if (!item || !group) return;
      // 当前激活按钮 = 同 group 里有 .voted 的那个
      const currentBtn = group.querySelector('.news-vote-btn.voted');
      const currentScore = currentBtn?.dataset.voteScore || null;
      // 点同一个按钮 → 取消; 点不同按钮 → 切换
      const newScore = (currentScore === score) ? null : score;
      // 乐观 UI: 清同 group 所有 voted, 再按 newScore 加
      group.querySelectorAll('.news-vote-btn').forEach(b => b.classList.remove('voted'));
      if (newScore) {
        const target = group.querySelector(`.news-vote-btn[data-vote-score='${newScore}']`);
        target?.classList.add('voted');
      }
      // item 外层状态 class: voted-down / voted-up / voted-star / 无
      item.classList.remove('voted-down', 'voted-up', 'voted-star');
      if (newScore) item.classList.add(`voted-${newScore}`);
      try {
        const resp = await fetch('/news/vote', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url, title, source, score: newScore }),
        });
        const data = await resp.json();
        if (!data.ok) throw new Error(data.error || 'vote failed');
        // 更新顶部计数: 显示三档分别数量
        const countEl = document.querySelector('.news-vote-count');
        if (countEl && data.totals_by_score) {
          const t = data.totals_by_score;
          countEl.textContent = `👎 ${t.down||0} · 👍 ${t.up||0} · ⭐ ${t.star||0}`;
        }
      } catch (err) {
        console.error('[news vote]', err);
        // 回滚
        group.querySelectorAll('.news-vote-btn').forEach(b => b.classList.remove('voted'));
        if (currentScore) {
          const target = group.querySelector(`.news-vote-btn[data-vote-score='${currentScore}']`);
          target?.classList.add('voted');
          item.classList.remove('voted-down', 'voted-up', 'voted-star');
          item.classList.add(`voted-${currentScore}`);
        } else {
          item.classList.remove('voted-down', 'voted-up', 'voted-star');
        }
      }
    });
  });
})();

// ===== AI 大事轮播: 每源一页, prev/next + dots + 键盘 + 触屏 =====
// 自动轮播接口已预留 (AUTO_MS), 默认关闭; 开启改成 >0 毫秒即可, 配合 pause-on-hover.
(function setupNewsCarousel(){
  const root = document.querySelector('.news-carousel[data-news-carousel]');
  if (!root) return;
  const track = root.querySelector('.news-carousel-track');
  const slides = track ? Array.from(track.children) : [];
  const dots = Array.from(root.querySelectorAll('.news-carousel-dot'));
  const prevBtn = root.querySelector('.news-carousel-btn.prev');
  const nextBtn = root.querySelector('.news-carousel-btn.next');
  if (slides.length <= 1) {
    // 单源 / 空: 隐藏导航
    prevBtn?.setAttribute('hidden', '');
    nextBtn?.setAttribute('hidden', '');
    root.querySelector('.news-carousel-dots')?.setAttribute('hidden', '');
    return;
  }
  const AUTO_MS = 0; // 轮播间隔 (毫秒), 0 关闭; 想开启改 > 0 数值
  let idx = 0;
  let autoTimer = null;

  function refresh(){
    if (track) track.style.transform = `translateX(-${idx * 100}%)`;
    dots.forEach((d, di) => d.classList.toggle('active', di === idx));
    if (prevBtn) prevBtn.disabled = (idx === 0);
    if (nextBtn) nextBtn.disabled = (idx === slides.length - 1);
  }
  function goto(i, opts){
    const wrap = !!(opts && opts.wrap);
    if (wrap) {
      idx = (i + slides.length) % slides.length;
    } else {
      idx = Math.max(0, Math.min(slides.length - 1, i));
    }
    refresh();
  }
  function startAuto(){
    if (!AUTO_MS) return;
    stopAuto();
    autoTimer = setInterval(() => goto(idx + 1, {wrap: true}), AUTO_MS);
  }
  function stopAuto(){
    if (autoTimer) { clearInterval(autoTimer); autoTimer = null; }
  }

  prevBtn?.addEventListener('click', () => goto(idx - 1));
  nextBtn?.addEventListener('click', () => goto(idx + 1));
  dots.forEach((d, di) => d.addEventListener('click', () => goto(di)));

  // 键盘: 只在 news tab active 时响应 ← →
  document.addEventListener('keydown', (e) => {
    if (e.target && ['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return;
    const activeTab = document.querySelector('.tab-content.active')?.dataset.tab;
    if (activeTab !== 'news') return;
    if (e.key === 'ArrowLeft')  { e.preventDefault(); goto(idx - 1); }
    if (e.key === 'ArrowRight') { e.preventDefault(); goto(idx + 1); }
  });

  // 触屏 / 鼠标拖拽: 超过 60px 触发切页
  const vp = root.querySelector('.news-carousel-viewport');
  let startX = null;
  let startY = null;
  let dragging = false;
  function onStart(x, y){ startX = x; startY = y; dragging = true; }
  function onEnd(x){
    if (!dragging || startX === null) return;
    const dx = x - startX;
    dragging = false;
    if (Math.abs(dx) > 60) goto(idx + (dx < 0 ? 1 : -1));
    startX = null; startY = null;
  }
  vp?.addEventListener('touchstart', e => onStart(e.touches[0].clientX, e.touches[0].clientY), {passive: true});
  vp?.addEventListener('touchmove',  e => {
    if (!dragging) return;
    const dx = e.touches[0].clientX - startX;
    const dy = e.touches[0].clientY - startY;
    if (Math.abs(dx) > Math.abs(dy) && e.cancelable) e.preventDefault();
  }, {passive: false});
  vp?.addEventListener('touchend', e => onEnd(e.changedTouches[0].clientX));
  vp?.addEventListener('mousedown', e => onStart(e.clientX, e.clientY));
  vp?.addEventListener('mouseup',   e => onEnd(e.clientX));
  vp?.addEventListener('mouseleave', () => { dragging = false; startX = null; });

  // 暂停自动播放 on hover (即使 AUTO_MS=0 也无害)
  root.addEventListener('mouseenter', stopAuto);
  root.addEventListener('mouseleave', startAuto);

  refresh();
  startAuto();
})();
