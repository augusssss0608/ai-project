// ===== AI 大事 reader: 左侧源 + 右侧单篇滑页 + 底部页码 + infinite wrap =====
(function setupNewsReader(){
  const root = document.querySelector('.news-reader[data-news-reader]');
  if (!root) return;
  const dataEl = document.getElementById('news-data');
  if (!dataEl) return;
  let DATA;
  try { DATA = JSON.parse(dataEl.textContent); } catch(e){ console.error('[news] bad data', e); return; }
  const sources = DATA.sources || [];
  if (!sources.length) return;

  const STAGE_EMOJI = {cold:'🥶', mid:'🌡️', hot:'🔥'};
  const STAGE_LABEL = {cold:'COLD', mid:'MID', hot:'HOT'};

  const state = {
    votes: DATA.votes || {},
    favorites: DATA.favorites || {},   // {url: {title, source, ts}}
    viewMode: 'sources',                // 'sources' | 'favorites'
    srcIdx: 0,
    pageIdx: 0,
    favFoldedSources: new Set(),        // 收藏模式下折叠的源 id 集合
  };
  let pendingWrapSnap = null;

  const modeToggleEl = document.querySelector('.news-mode-toggle');
  const srcListEl = root.querySelector('#news-src-list');
  const vpEl      = root.querySelector('#news-viewport');
  const trackEl   = root.querySelector('#news-track');
  const pagEl     = root.querySelector('#news-pagination');

  function esc(s){return String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
  function isFav(url){ return !!state.favorites[url]; }
  function getScore(url){ return (state.votes[url]||{}).score || ''; }

  // 收藏模式下: 构造虚拟 source, 按原 sources 顺序分组, 组内按收藏 ts desc
  function getFavoriteItems(){
    const byUrl = {};
    for (const s of sources){
      for (const it of (s.items||[])){
        byUrl[it.url] = {...it, _sourceId: s.id, _sourceLabel: s.label};
      }
    }
    const favUrls = new Set(Object.keys(state.favorites));
    const out = [];
    for (const url of favUrls){
      if (byUrl[url]){
        // 补 fav ts 用于排序
        out.push({...byUrl[url], _favTs: state.favorites[url].ts || ''});
      } else {
        // 原数据缺失, stub 占位
        const meta = state.favorites[url];
        const srcObj = sources.find(s => s.id === meta.source);
        out.push({
          url, title: meta.title || url, summary: '(原文已从源中移除)',
          workspace_help: '无相关', claude_usage: '无相关', ts: meta.ts,
          _sourceId: meta.source || 'unknown',
          _sourceLabel: (srcObj && srcObj.label) || meta.source || '未知源',
          _favTs: meta.ts || '',
        });
      }
    }
    // 按 (源顺序, 组内 favTs desc) 排序
    const srcOrder = {};
    sources.forEach((s, i) => srcOrder[s.id] = i);
    out.sort((a, b) => {
      const ai = srcOrder[a._sourceId] ?? 999;
      const bi = srcOrder[b._sourceId] ?? 999;
      if (ai !== bi) return ai - bi;
      return String(b._favTs || '').localeCompare(String(a._favTs || ''));
    });
    return out;
  }

  function curSource(){
    if (state.viewMode === 'favorites'){
      return { id: '_favorites', label: '收藏', items: getFavoriteItems() };
    }
    return sources[state.srcIdx] || {items:[]};
  }
  function curItems(){ return curSource().items || []; }

  function fmtTime(iso){
    if(!iso) return '';
    const s = String(iso).replace(/Z/,'+00:00');
    const d = new Date(s.includes('T')?s:s.replace(/\s+/,'T'));
    if(isNaN(d)) return String(iso).slice(0,16);
    const pad = n => String(n).padStart(2,'0');
    return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  }

  function updateSlideWidth(){
    const w = vpEl.clientWidth || 0;
    if (w > 0) document.documentElement.style.setProperty('--news-slide-w', w + 'px');
    return w;
  }

  // === viewport 高度固定: 按字段上限模板渲染, 与实际数据无关 ===
  // 这些数字是 UI 约定的最大字数信封, 对应 agent md 契约的硬顶:
  //   title 120 / summary 150 / workspace 80 / claude 80
  // real 文章只要 ≤ 这些值就必然装进容器, > 这些值由 agent 端修短
  const MAX_LIMITS = { title: 120, summary: 150, workspace_help: 80, claude_usage: 80 };
  let globalMaxH = 0;

  function computeMaxLimitHeight(){
    const vpW = vpEl.clientWidth || 1000;
    updateSlideWidth();
    const ghost = document.createElement('div');
    ghost.style.cssText = `position:absolute;left:-99999px;top:0;visibility:hidden;pointer-events:none;width:${vpW}px;overflow:hidden;`;
    const ghostTrack = document.createElement('div');
    ghostTrack.className = 'news-slide-track';
    ghostTrack.style.cssText = 'display:flex;align-items:flex-start;';
    ghost.appendChild(ghostTrack);
    document.body.appendChild(ghost);
    const ch = (n) => '字'.repeat(n);
    const maxItem = {
      title: ch(MAX_LIMITS.title),
      summary: ch(MAX_LIMITS.summary),
      workspace_help: ch(MAX_LIMITS.workspace_help),
      claude_usage: ch(MAX_LIMITS.claude_usage),
      ts: '2026-04-22T00:00:00Z',
      ai_score: 10,
      url: 'https://example.com/max-template',
    };
    const sid = (sources[0] && sources[0].id) || 'hackernews';
    ghostTrack.innerHTML = renderSlideHtml(maxItem, sid, 1, 1);
    const firstChild = ghostTrack.firstElementChild;
    const h = firstChild ? firstChild.scrollHeight : 0;
    document.body.removeChild(ghost);
    return h;
  }

  // viewport 高度: 一次性按 MAX_LIMITS 模板算出 upper bound, 之后永不变 (翻页/换源/投票都不动)
  function updateViewportHeight(){
    requestAnimationFrame(() => {
      if (!globalMaxH){
        globalMaxH = computeMaxLimitHeight();
      }
      if (globalMaxH > 0) vpEl.style.height = globalMaxH + 'px';
    });
  }

  function renderSrcList(){
    if (state.viewMode === 'favorites'){
      renderFavList();
      return;
    }
    const headHtml = `<div class='head'>SOURCES</div>`;
    const items = sources.map((s, i) => {
      const active = i === state.srcIdx ? 'active' : '';
      return `<button class='news-src-item src-${esc(s.id)} ${active}' data-idx='${i}'>
        <div class='label'>
          <span class='name'>${esc(s.label || s.id)}</span>
          <span class='stage'>${STAGE_EMOJI[s.stage]||''} ${STAGE_LABEL[s.stage]||''}</span>
        </div>
        <span class='count'>${(s.items||[]).length}</span>
      </button>`;
    }).join('');
    srcListEl.innerHTML = headHtml + items;
    srcListEl.querySelectorAll('.news-src-item').forEach(b => {
      b.addEventListener('click', () => {
        const idx = parseInt(b.dataset.idx, 10);
        if (idx === state.srcIdx) return;
        state.srcIdx = idx;
        state.pageIdx = 0;
        renderSrcList();
        renderSlides();
        renderPagination();
      });
    });
  }

  // 收藏模式: 左侧栏按源分组 + 可折叠
  function renderFavList(){
    const items = getFavoriteItems();
    let html = `<div class='head'>❤️ FAVORITES · ${items.length}</div>`;
    if (!items.length){
      srcListEl.innerHTML = html + `<div class='news-fav-empty'>// 暂无收藏<br>点击文章右上 ❤️ 加收藏</div>`;
      return;
    }
    // 按 _sourceId 分组, 保持 getFavoriteItems 已排序的顺序
    const groups = [];
    const groupByIdx = {};
    items.forEach((it, idx) => {
      const sid = it._sourceId || 'unknown';
      if (!groupByIdx[sid]){
        const g = { id: sid, label: it._sourceLabel || sid, items: [] };
        groupByIdx[sid] = g;
        groups.push(g);
      }
      groupByIdx[sid].items.push({ ...it, _favIdx: idx });
    });
    for (const grp of groups){
      const folded = state.favFoldedSources.has(grp.id);
      html += `<div class='news-fav-group src-${esc(grp.id)} ${folded?'folded':''}'>`;
      html += `<button class='news-fav-group-head' data-fold='${esc(grp.id)}' aria-expanded='${folded?"false":"true"}'>`;
      html += `<span class='chev'>▾</span>`;
      html += `<span class='name'>${esc(grp.label)}</span>`;
      html += `<span class='count'>${grp.items.length}</span>`;
      html += `</button>`;
      html += `<div class='news-fav-group-body'>`;
      for (const it of grp.items){
        const active = it._favIdx === state.pageIdx ? 'active' : '';
        html += `<button class='news-src-item news-fav-item src-${esc(grp.id)} ${active}' data-idx='${it._favIdx}' title='${esc(it.title||'')}'>`;
        html += `<div class='label'><span class='name'>${esc(it.title||'').slice(0, 60)}</span></div>`;
        html += `</button>`;
      }
      html += `</div></div>`;
    }
    srcListEl.innerHTML = html;
    // 折叠切换
    srcListEl.querySelectorAll('.news-fav-group-head').forEach(b => {
      b.addEventListener('click', () => {
        const sid = b.dataset.fold;
        if (state.favFoldedSources.has(sid)) state.favFoldedSources.delete(sid);
        else state.favFoldedSources.add(sid);
        renderFavList();
      });
    });
    // 选择收藏项
    srcListEl.querySelectorAll('.news-fav-item').forEach(b => {
      b.addEventListener('click', () => {
        const idx = parseInt(b.dataset.idx, 10);
        if (idx === state.pageIdx) return;
        state.pageIdx = idx;
        renderSlides();
        renderPagination();
        renderFavList();
      });
    });
  }

  function renderSlideHtml(it, srcId, ordN, total){
    const score = getScore(it.url);
    const fav = isFav(it.url);
    const ws = it.workspace_help || '无相关';
    const cu = it.claude_usage || '无相关';
    const wsNA = ws === '无相关';
    const cuNA = cu === '无相关';
    const badge = score==='star' ? '⭐ STAR' : score==='up' ? '👍 USEFUL' : score==='down' ? '👎 SKIP' : '';
    const srcLabelFull = (sources.find(s=>s.id===srcId)||{}).label || it._sourceLabel || srcId;
    const title = it.title || '(no title)';
    const summary = it.summary || '(暂无摘要)';
    const safeTitle = esc(title.slice(0, 160));  // vote 按钮 data-title 不截, 后端原样收
    return `
    <div class='news-slide src-${esc(srcId)} ${score?'voted-'+score:''} ${fav?'is-fav':''}'>
      <article>
        ${badge?`<span class='news-vote-badge'>${badge}</span>`:''}
        <div class='news-art-meta'>
          <span class='src'>${esc(srcLabelFull)}</span>
          <span>·</span>
          <span>${fmtTime(it.ts)}</span>
          ${it.ai_score!=null?`<span>·</span><span>💡 AI ${it.ai_score}</span>`:''}
          <span class='ord'>${String(ordN).padStart(2,'0')} / ${String(total).padStart(2,'0')}</span>
        </div>
        <div class='news-art-title-row'>
          <h3 class='news-art-title'><a href='${esc(it.url)}' target='_blank' rel='noopener'>${esc(title)}</a></h3>
          <button class='news-fav-btn ${fav?'faved':''}' data-fav-url='${esc(it.url)}' data-fav-title='${safeTitle}' data-fav-source='${esc(srcId)}' title='${fav?"已收藏, 点击取消":"加入收藏"}'>${fav?'❤️':'🤍'}</button>
        </div>
        <div class='news-art-actions'>
          <span class='lbl'>反馈</span>
          <span class='news-vote-group'>
            <button class='news-vote-btn ${score==='down'?'voted':''}' data-vote-url='${esc(it.url)}' data-vote-title='${safeTitle}' data-vote-source='${esc(srcId)}' data-vote-score='down' title='没兴趣 / 过滤同类'>👎</button>
            <button class='news-vote-btn ${score==='up'?'voted':''}' data-vote-url='${esc(it.url)}' data-vote-title='${safeTitle}' data-vote-source='${esc(srcId)}' data-vote-score='up' title='有用'>👍</button>
            <button class='news-vote-btn ${score==='star'?'voted':''}' data-vote-url='${esc(it.url)}' data-vote-title='${safeTitle}' data-vote-source='${esc(srcId)}' data-vote-score='star' title='超赞'>⭐</button>
          </span>
          <a class='open-ext' href='${esc(it.url)}' target='_blank' rel='noopener'>原文 ↗</a>
        </div>
        <div class='news-art-section-label'>摘要</div>
        <p class='news-art-summary'>${esc(summary)}</p>
        <div class='news-art-section-label'>相关度分析</div>
        <div class='news-art-analysis'>
          <span class='k ${wsNA?'na':''}'>工作区</span><span class='v ${wsNA?'na':''}'>${esc(ws)}</span>
          <span class='k ${cuNA?'na':''}'>Claude</span><span class='v ${cuNA?'na':''}'>${esc(cu)}</span>
        </div>
      </article>
    </div>`;
  }

  function renderSlides(){
    const items = curItems();
    // 空源 / 收藏模式默认未选 (pageIdx<0): 显示占位
    if (!items.length || state.pageIdx < 0){
      const msg = !items.length ? '// 暂无数据' : '// 从左侧选一条收藏文章';
      trackEl.innerHTML = `<div class='news-slide'><div class='news-art-empty'>${msg}</div></div>`;
      trackEl.style.transform = 'translateX(0)';
      updateViewportHeight();
      return;
    }
    const n = items.length;
    const sid = curSource().id;
    updateSlideWidth();
    const vpW = vpEl.clientWidth || 1;
    const html = [];
    html.push(renderSlideHtml(items[n-1], sid, n, n));
    items.forEach((it,i) => html.push(renderSlideHtml(it, sid, i+1, n)));
    html.push(renderSlideHtml(items[0], sid, 1, n));
    trackEl.innerHTML = html.join('');
    trackEl.style.transition = 'none';
    trackEl.style.transform = `translateX(${-(state.pageIdx + 1) * vpW}px)`;
    trackEl.offsetHeight;
    requestAnimationFrame(() => {
      trackEl.style.transition = 'transform .45s cubic-bezier(.22,1,.36,1)';
    });
    // 收藏模式 / 单条源 / 未选中: 隐藏 grab cursor (拖拽已禁, 视觉也同步)
    vpEl.style.cursor = (state.viewMode === 'favorites' || items.length <= 1 || state.pageIdx < 0) ? 'default' : '';
    bindVoteButtons();
    updateViewportHeight();
  }

  function bindVoteButtons(){
    trackEl.querySelectorAll('.news-vote-btn').forEach(b => {
      b.addEventListener('click', async e => {
        e.stopPropagation();
        const url = b.dataset.voteUrl;
        const title = b.dataset.voteTitle || '';
        const source = b.dataset.voteSource || '';
        const score = b.dataset.voteScore;
        if (!url || !score) return;
        const current = getScore(url);
        const next = current === score ? null : score;
        if (next) state.votes[url] = {score:next, title, source, ts:new Date().toISOString()};
        else delete state.votes[url];
        renderSlides();
        renderPagination();
        try {
          const resp = await fetch('/news/vote', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({url, title, source, score: next}),
          });
          const data = await resp.json();
          if (!data.ok) throw new Error(data.error || 'vote failed');
          const countEl = document.querySelector('.news-vote-count');
          if (countEl && data.totals_by_score){
            const t = data.totals_by_score;
            countEl.textContent = `👎 ${t.down||0} · 👍 ${t.up||0} · ⭐ ${t.star||0}`;
          }
        } catch(err){
          console.error('[news vote]', err);
          if (current) state.votes[url] = {score:current, title, source};
          else delete state.votes[url];
          renderSlides();
          renderPagination();
        }
      });
    });
    // 收藏按钮
    trackEl.querySelectorAll('.news-fav-btn').forEach(b => {
      b.addEventListener('click', async e => {
        e.stopPropagation();
        const url = b.dataset.favUrl;
        const title = b.dataset.favTitle || '';
        const source = b.dataset.favSource || '';
        if (!url) return;
        const currently = isFav(url);
        const next = !currently;
        if (next) state.favorites[url] = {title, source, ts:new Date().toISOString()};
        else delete state.favorites[url];
        renderSlides();
        if (state.viewMode === 'favorites') renderFavList();
        updateModeToggleCount();
        try {
          const resp = await fetch('/news/favorite', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({url, title, source, fav: next}),
          });
          const data = await resp.json();
          if (!data.ok) throw new Error(data.error || 'fav failed');
        } catch(err){
          console.error('[news fav]', err);
          if (currently) state.favorites[url] = {title, source};
          else delete state.favorites[url];
          renderSlides();
          if (state.viewMode === 'favorites') renderFavList();
          updateModeToggleCount();
        }
      });
    });
  }

  function updateModeToggleCount(){
    if (!modeToggleEl) return;
    const cnt = modeToggleEl.querySelector('.fav-count');
    if (cnt) cnt.textContent = Object.keys(state.favorites).length;
  }

  function toggleViewMode(){
    state.viewMode = state.viewMode === 'sources' ? 'favorites' : 'sources';
    // 进收藏模式默认无选中, 进源模式回到第一篇
    state.pageIdx = state.viewMode === 'favorites' ? -1 : 0;
    if (modeToggleEl){
      modeToggleEl.dataset.modeCurrent = state.viewMode;
      modeToggleEl.classList.toggle('active', state.viewMode === 'favorites');
    }
    renderSrcList();
    renderSlides();
    renderPagination();
  }

  function renderPagination(){
    // 收藏模式完全隐藏 pagination
    if (state.viewMode === 'favorites'){
      pagEl.hidden = true;
      pagEl.innerHTML = '';
      return;
    }
    pagEl.hidden = false;  // 源模式: 永远保留空间, 单条源也占位 (保持 reader 整体高度一致)
    const total = curItems().length;
    // 单条源 / 未选中 (pageIdx<0): 保留空 pagination 占位, 不渲染数字
    if (total <= 1 || state.pageIdx < 0){
      pagEl.innerHTML = '';
      return;
    }
    const parts = [];
    for (let i = 0; i < total; i++){
      const active = i === state.pageIdx ? 'active' : '';
      parts.push(`<button class='news-page-btn ${active}' data-go='${i}' aria-label='第 ${i+1} 篇'>${String(i+1).padStart(2,'0')}</button>`);
      if (i < total - 1) parts.push(`<span class='news-page-sep'>·</span>`);
    }
    pagEl.innerHTML = parts.join('');
    pagEl.querySelectorAll('.news-page-btn').forEach(b => {
      b.addEventListener('click', () => gotoPage(parseInt(b.dataset.go, 10)));
    });
  }

  function gotoPage(i){
    if (state.viewMode === 'favorites') return;  // 收藏模式: 禁翻页/滑动 (只能点左栏切换)
    const total = curItems().length;
    if (total <= 1) return;  // 单条 / 空源: 不翻页
    if (state.pageIdx < 0) return;
    const prevIdx = state.pageIdx;
    const vpW = vpEl.clientWidth || 1;

    if (pendingWrapSnap){
      trackEl.removeEventListener('transitionend', pendingWrapSnap);
      pendingWrapSnap = null;
    }

    const isWrapNext = prevIdx === total - 1 && (i % total + total) % total === 0 && i > prevIdx;
    const isWrapPrev = prevIdx === 0 && (i % total + total) % total === total - 1 && i < prevIdx;

    if (isWrapNext){
      trackEl.style.transition = 'transform .45s cubic-bezier(.22,1,.36,1)';
      trackEl.style.transform = `translateX(${-(total + 1) * vpW}px)`;
      state.pageIdx = 0;
      const onEnd = () => {
        trackEl.removeEventListener('transitionend', onEnd);
        pendingWrapSnap = null;
        if (state.pageIdx !== 0) return;
        trackEl.style.transition = 'none';
        trackEl.style.transform = `translateX(${-1 * vpW}px)`;
        trackEl.offsetHeight;
        requestAnimationFrame(() => trackEl.style.transition = 'transform .45s cubic-bezier(.22,1,.36,1)');
      };
      pendingWrapSnap = onEnd;
      trackEl.addEventListener('transitionend', onEnd, {once:true});
    } else if (isWrapPrev){
      trackEl.style.transition = 'transform .45s cubic-bezier(.22,1,.36,1)';
      trackEl.style.transform = `translateX(0px)`;
      state.pageIdx = total - 1;
      const onEnd = () => {
        trackEl.removeEventListener('transitionend', onEnd);
        pendingWrapSnap = null;
        if (state.pageIdx !== total - 1) return;
        trackEl.style.transition = 'none';
        trackEl.style.transform = `translateX(${-total * vpW}px)`;
        trackEl.offsetHeight;
        requestAnimationFrame(() => trackEl.style.transition = 'transform .45s cubic-bezier(.22,1,.36,1)');
      };
      pendingWrapSnap = onEnd;
      trackEl.addEventListener('transitionend', onEnd, {once:true});
    } else {
      const newIdx = ((i % total) + total) % total;
      state.pageIdx = newIdx;
      trackEl.style.transition = 'transform .45s cubic-bezier(.22,1,.36,1)';
      trackEl.style.transform = `translateX(${-(state.pageIdx + 1) * vpW}px)`;
    }
    renderPagination();
    // 高度在源切换时已锁定为该源最长 slide 的高度, 翻页不动
    // 收藏模式: 翻页后同步左栏 active
    if (state.viewMode === 'favorites') renderFavList();
  }

  document.addEventListener('keydown', e => {
    if (e.target && ['INPUT','TEXTAREA'].includes(e.target.tagName)) return;
    const activeTab = document.querySelector('.tab-content.active')?.dataset.tab;
    if (activeTab !== 'news') return;
    if (e.key === 'ArrowLeft')  { e.preventDefault(); gotoPage(state.pageIdx - 1); }
    if (e.key === 'ArrowRight') { e.preventDefault(); gotoPage(state.pageIdx + 1); }
  });

  // 鼠标 / 触屏拖拽
  (function setupDrag(){
    let startX=null, startY=null, curDx=0, dragging=false, axisLocked=null;
    const THRESHOLD = 60, AXIS_LOCK = 10;
    function baseTx(){ return -(state.pageIdx + 1) * (vpEl.clientWidth || 1); }
    function onStart(x, y){
      // 收藏模式 / 单条 / 空源 / 未选中: 不启用拖拽
      if (state.viewMode === 'favorites') return;
      if (curItems().length <= 1 || state.pageIdx < 0) return;
      if (pendingWrapSnap){
        trackEl.removeEventListener('transitionend', pendingWrapSnap);
        pendingWrapSnap = null;
      }
      startX = x; startY = y; curDx = 0; dragging = true; axisLocked = null;
      trackEl.style.transition = 'none';
      vpEl.classList.add('grabbing');
    }
    function onMove(x, y){
      if (!dragging || startX===null) return false;
      const dx = x - startX, dy = y - startY;
      if (axisLocked === null){
        if (Math.abs(dx) > AXIS_LOCK || Math.abs(dy) > AXIS_LOCK){
          axisLocked = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y';
        }
      }
      if (axisLocked === 'x'){
        curDx = dx;
        trackEl.style.transform = `translateX(${baseTx() + dx}px)`;
        return true;
      }
      return false;
    }
    function onEnd(){
      if (!dragging) return;
      dragging = false;
      vpEl.classList.remove('grabbing');
      trackEl.style.transition = 'transform .45s cubic-bezier(.22,1,.36,1)';
      if (axisLocked === 'x' && Math.abs(curDx) > THRESHOLD){
        gotoPage(state.pageIdx + (curDx < 0 ? 1 : -1));
      } else {
        trackEl.style.transform = `translateX(${baseTx()}px)`;
      }
      startX = startY = null; curDx = 0; axisLocked = null;
    }
    vpEl.addEventListener('mousedown', e => {
      if (e.target.closest('button,a,input,textarea')) return;
      onStart(e.clientX, e.clientY);
      e.preventDefault();
    });
    document.addEventListener('mousemove', e => { if (dragging) onMove(e.clientX, e.clientY); });
    document.addEventListener('mouseup', onEnd);
    vpEl.addEventListener('mouseleave', () => { if (dragging) onEnd(); });
    vpEl.addEventListener('touchstart', e => {
      if (e.target.closest('button,a,input,textarea')) return;
      const t = e.touches[0];
      onStart(t.clientX, t.clientY);
    }, {passive:true});
    vpEl.addEventListener('touchmove', e => {
      const t = e.touches[0];
      const needPrevent = onMove(t.clientX, t.clientY);
      if (needPrevent && e.cancelable) e.preventDefault();
    }, {passive:false});
    vpEl.addEventListener('touchend', onEnd);
    vpEl.addEventListener('touchcancel', onEnd);
  })();

  // resize / tab 切换 viewport 尺寸变 → 重新 layout + 重新量全局最大高度
  if (window.ResizeObserver){
    let lastW = 0;
    const ro = new ResizeObserver(() => {
      const w = vpEl.clientWidth;
      if (w > 0 && w !== lastW){
        lastW = w;
        updateSlideWidth();
        trackEl.style.transition = 'none';
        trackEl.style.transform = `translateX(${-(state.pageIdx + 1) * w}px)`;
        trackEl.offsetHeight;
        requestAnimationFrame(() => trackEl.style.transition = 'transform .45s cubic-bezier(.22,1,.36,1)');
        globalMaxH = 0;        // 宽度变了换行点变, 旧 max 作废
        updateViewportHeight();
      }
    });
    ro.observe(vpEl);
  }

  // 顶部模式切换按钮
  if (modeToggleEl){
    modeToggleEl.addEventListener('click', e => {
      e.preventDefault();
      toggleViewMode();
    });
  }

  renderSrcList();
  renderSlides();
  renderPagination();
})();
