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

  // 已看过的 URL 集合: 后端 ai-news-feedback.json 的 seen 段裁剪到当前榜单后, item.is_new 透传.
  // 前端启动时把 is_new === false (服务端确认已 seen) 反推回 seenUrls.
  // 用 `=== false` 而非 `!it.is_new`: 老 payload 里 undefined 不进 initSeen, 与 markSeen 守卫呼应.
  const initSeen = new Set();
  for (const s of (DATA.sources||[])) {
    for (const it of (s.items||[])) {
      if (it && it.url && it.is_new === false) initSeen.add(it.url);
    }
  }

  const state = {
    votes: DATA.votes || {},
    favorites: DATA.favorites || {},   // {url: {title, source, ts}}
    seenUrls: initSeen,                 // 已看过的 URL Set (前端本地缓存, 与后端 seen 同步)
    viewMode: 'sources',                // 'sources' | 'favorites'
    srcIdx: 0,
    pageIdx: 0,
    favFoldedSources: new Set(),        // 收藏模式下折叠的源 id 集合
    githubSortBy: 'daily',              // github 源排序: daily | weekly | monthly | total
  };
  let pendingWrapSnap = null;

  const modeToggleEl = document.querySelector('.news-mode-toggle');
  const srcListEl = root.querySelector('#news-src-list');
  const vpEl      = root.querySelector('#news-viewport');
  const trackEl   = root.querySelector('#news-track');
  const pagEl     = root.querySelector('#news-pagination');

  const GITHUB_SORT_CYCLE = ['daily', 'weekly', 'monthly', 'total'];

  function esc(s){return String(s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
  function isFav(url){ return !!state.favorites[url]; }
  function getScore(url){ return (state.votes[url]||{}).score || ''; }

  // 把"已看过"标记 POST 到后端 + 更新本地 set + 抹掉对应 NEW 徽标/页码橙.
  // 失败静默 (不影响阅读), 下次 render 时 is_new 仍为 true 会再次尝试.
  // 守卫 `it.is_new !== true`: 跳过已知非 new 条目 (含老 payload undefined / 收藏 stub / 服务端已 seen).
  function markSeen(it, srcId){
    if (!it || !it.url || state.seenUrls.has(it.url) || it.is_new !== true) return;
    state.seenUrls.add(it.url);
    // 抹当前 slide 的 NEW 徽标 (currentSlide 在 renderSlides 后是 track 的第 pageIdx+1 个子)
    const slide = trackEl.children[state.pageIdx + 1];
    if (slide){
      slide.querySelectorAll('.news-new-badge').forEach(b => {
        // 同时把紧跟其后的分隔点 (·) 也移掉
        const next = b.nextElementSibling;
        if (next && next.tagName === 'SPAN' && next.textContent.trim() === '·') next.remove();
        b.remove();
      });
    }
    // 抹页码橙
    const pageBtn = pagEl.querySelector(`.news-page-btn[data-go='${state.pageIdx}']`);
    if (pageBtn) pageBtn.classList.remove('news-page-btn--new');

    fetch('/news/seen', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url: it.url, source: srcId || ''}),
    }).catch(err => console.error('[news seen]', err));
  }

  function markCurrentSeen(){
    const items = curItems();
    if (!items.length || state.pageIdx < 0) return;
    const it = items[state.pageIdx];
    if (!it) return;
    const srcId = (it._sourceId) || curSource().id;
    markSeen(it, srcId);
  }

  // threads 源: 低分条目过滤 (ai_score <= THREADS_MIN_SCORE 不展示)
  const THREADS_MIN_SCORE = 5;
  function isThreadsSource(srcId){ return srcId === 'threads'; }
  function filterThreadsByScore(items){
    return items.filter(it => {
      const s = it && it.ai_score;
      return typeof s === 'number' ? s > THREADS_MIN_SCORE : true;
    });
  }

  // github 源相关
  function isGithubSource(srcId){ return srcId === 'github_trending'; }
  function hasGithubStars(it){
    return it && ('daily_stars' in it || 'weekly_stars' in it || 'monthly_stars' in it || 'total_stars_int' in it);
  }
  function fmtStarNum(n){
    n = Number(n) || 0;
    if (n >= 1000) return (n/1000).toFixed(n >= 10000 ? 0 : 1) + 'k';
    return String(n);
  }
  function renderGithubStars(it, activeKey){
    if (!hasGithubStars(it)) return '';
    const t = it.total_stars_int || 0;
    // trending 数据源无"本期新增 star", 日/周/月展示真实 trending 名次 (#rank); 总展示总 star
    const dimVal = (k) => {
      const r = it[k + '_rank'] || 0;
      if (r) return '#' + r;
      const g = it[k + '_stars'] || 0;   // 老数据兼容: 有增量则显示 +N⭐
      return g ? '+' + fmtStarNum(g) + '⭐' : '—';
    };
    const rows = [
      ['daily',   '日', dimVal('daily')],
      ['weekly',  '周', dimVal('weekly')],
      ['monthly', '月', dimVal('monthly')],
      ['total',   '总', fmtStarNum(t) + '⭐'],
    ];
    return rows.map(([k, label, v]) => {
      const active = k === activeKey ? 'active' : '';
      return `<span class='github-star ${active}'><span class='lbl'>${label}</span><span class='val'>${v}</span></span>`;
    }).join('');
  }
  function githubSortKey(it, k){
    if (k === 'total') return it.total_stars_int || 0;
    const r = it[k + '_rank'] || 0;
    if (r) return -r;                    // 名次升序: #1 最前 (降序排序下 -1 > -2)
    return it[k + '_stars'] || 0;        // 老数据兼容: 按增量降序
  }
  const GITHUB_PER_DIM_DISPLAY = 15;
  // 按维度过滤: 仅保留 item.dimension === 维度 的条目, 按对应 star 降序, 截 top 15
  function filterGithubByDim(items, dim){
    const subset = items.filter(it => it.dimension === dim);
    return subset
      .slice()
      .sort((a, b) => githubSortKey(b, dim) - githubSortKey(a, dim))
      .slice(0, GITHUB_PER_DIM_DISPLAY);
  }
  // 兼容老数据 (没有 dimension 字段): 回退到原"合并后排序"行为
  function sortGithubItems(items, sortBy){
    return items.slice().sort((a, b) => githubSortKey(b, sortBy) - githubSortKey(a, sortBy));
  }

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
  function curItems(){
    const src = curSource();
    const items = src.items || [];
    if (isGithubSource(src.id)) {
      // 新数据带 dimension 字段: 按维度过滤出各榜单独立 top N
      const hasDim = items.some(it => it && it.dimension);
      if (hasDim) return filterGithubByDim(items, state.githubSortBy);
      // 老数据 fallback: 同一池子按字段排序
      return sortGithubItems(items, state.githubSortBy);
    }
    if (isThreadsSource(src.id)) return filterThreadsByScore(items);
    return items;
  }

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
    const GITHUB_SORT_LABEL = {daily:'日', weekly:'周', monthly:'月', total:'总'};
    const items = sources.map((s, i) => {
      const active = i === state.srcIdx ? 'active' : '';
      const isGh = isGithubSource(s.id);
      const sortTag = (isGh && active) ? `<span class='gh-sort-tag'>${GITHUB_SORT_LABEL[state.githubSortBy]||''}</span>` : '';
      // github 源 count: 当前维度的条数 (新数据) / 兼容老数据时回退到全部
      // 与右侧显示对齐: 单维度最多展示 GITHUB_PER_DIM_DISPLAY 条, 超过时左侧 count 也截到上限
      let cnt = (s.items || []).length;
      if (isGh) {
        const hasDim = (s.items || []).some(it => it && it.dimension);
        if (hasDim) {
          const dimCnt = (s.items || []).filter(it => it.dimension === state.githubSortBy).length;
          cnt = Math.min(dimCnt, GITHUB_PER_DIM_DISPLAY);
        } else {
          cnt = Math.min(cnt, GITHUB_PER_DIM_DISPLAY);
        }
      } else if (isThreadsSource(s.id)) {
        cnt = filterThreadsByScore(s.items || []).length;
      }
      return `<button class='news-src-item src-${esc(s.id)} ${active}' data-idx='${i}' title='${isGh?"再次点击循环切换 日→周→月→总":""}'>
        <div class='label'>
          <span class='name'>${esc(s.label || s.id)}</span>
          <span class='stage'>${sortTag}${STAGE_EMOJI[s.stage]||''} ${STAGE_LABEL[s.stage]||''}</span>
        </div>
        <span class='count'>${cnt}</span>
      </button>`;
    }).join('');
    srcListEl.innerHTML = headHtml + items;
    srcListEl.querySelectorAll('.news-src-item').forEach(b => {
      b.addEventListener('click', () => {
        const idx = parseInt(b.dataset.idx, 10);
        const targetSrc = sources[idx];
        const isGithub = targetSrc && isGithubSource(targetSrc.id);
        if (idx === state.srcIdx){
          // 再次点击当前选中源: 仅 github 源支持循环切换时间维度
          if (!isGithub) return;
          const curPos = GITHUB_SORT_CYCLE.indexOf(state.githubSortBy);
          state.githubSortBy = GITHUB_SORT_CYCLE[(curPos + 1) % GITHUB_SORT_CYCLE.length];
          state.pageIdx = 0;
          renderSrcList();
          renderSlides();
          renderPagination();
          return;
        }
        state.srcIdx = idx;
        state.pageIdx = 0;
        if (isGithub) state.githubSortBy = 'daily';  // 进 github 时重置时间维度
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
    // threads 源: 直接渲染原贴文 (it.desc), 不走 AI 摘要; 其他源用 news-summary 生成的 it.summary
    const isThreads = srcId === 'threads';
    const bodyRaw = isThreads ? (it.desc || it.summary || '') : (it.summary || '');
    // viewport 高度按 MAX_LIMITS.summary=150 计算, threads desc 上限 300, 截到 150 防破容器
    const body = (isThreads ? bodyRaw.slice(0, 150) + (bodyRaw.length > 150 ? '…' : '') : bodyRaw) || '(暂无摘要)';
    const bodyLabel = isThreads ? '原文' : '摘要';
    const safeTitle = esc(title.slice(0, 160));  // vote 按钮 data-title 不截, 后端原样收
    const starsHtml = isGithubSource(srcId) ? renderGithubStars(it, state.githubSortBy) : '';
    // 所有源: 用户未在 dashboard 滑到过该 url 时显示 NEW 徽标 (后端 seen 段标 is_new)
    const isNewNow = it.is_new && !state.seenUrls.has(it.url);
    const newBadge = isNewNow ? `<span class='news-new-badge'>NEW</span><span>·</span>` : '';
    return `
    <div class='news-slide src-${esc(srcId)} ${score?'voted-'+score:''} ${fav?'is-fav':''}'>
      <article>
        <div class='news-art-meta'>
          <span class='src'>${esc(srcLabelFull)}</span>
          <span>·</span>
          ${newBadge}
          <span>${fmtTime(it.ts)}</span>
          ${it.ai_score!=null?`<span>·</span><span>💡 AI ${it.ai_score}</span>`:''}
          ${it.reason?(()=>{
            const cs = it.content_status || 'not_attempted';
            const badgeText = cs === 'fetched' ? '正文确认' : cs === 'failed' ? '正文待补' : '仅标题';
            const badgeCls = cs === 'fetched' ? 'fetched' : cs === 'failed' ? 'failed' : 'title-only';
            return `<span class='news-reason-wrap'><span>·</span><button class='news-reason-toggle' type='button' title='查看 scorer 评分线索'>线索</button>
              <div class='news-reason-pop' hidden>
                <div class='news-reason-head'>
                  <span class='news-reason-label'>评分线索，不是事实证明</span>
                  <span class='news-reason-badge ${badgeCls}'>${badgeText}</span>
                </div>
                <p class='news-reason-text'>${esc(it.reason)}</p>
              </div>
            </span>`;
          })():''}
          ${badge?`<span class='news-vote-badge'>${badge}</span>`:`<span class='ord'>${String(ordN).padStart(2,'0')} / ${String(total).padStart(2,'0')}</span>`}
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
          ${starsHtml?`<span class='news-art-stars news-art-stars--inline'>${starsHtml}</span>`:''}
          <a class='open-ext' href='${esc(it.url)}' target='_blank' rel='noopener'>原文 ↗</a>
        </div>
        <div class='news-art-section-label'>${bodyLabel}</div>
        <p class='news-art-summary'>${esc(body)}</p>
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
    // 当前 slide 进入视野 → 标已看过 (初次加载 / 切源 / 收藏模式选条)
    markCurrentSeen();
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
    trackEl.querySelectorAll('.news-reason-toggle').forEach(b => {
      b.addEventListener('click', e => {
        e.stopPropagation();
        const wrap = b.closest('.news-reason-wrap');
        const pop = wrap && wrap.querySelector('.news-reason-pop');
        if (!pop) return;
        const opening = pop.hasAttribute('hidden');
        // 关闭其他已打开的 popover
        document.querySelectorAll('.news-reason-pop:not([hidden])').forEach(p => p.setAttribute('hidden', ''));
        document.querySelectorAll('.news-reason-toggle.open').forEach(btn => btn.classList.remove('open'));
        if (opening) {
          pop.removeAttribute('hidden');
          b.classList.add('open');
        }
      });
    });
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
    // 所有源: 未看过 (is_new && !seenUrls) 的页码挂 --new (橙色)
    const pageItems = curItems();
    for (let i = 0; i < total; i++){
      const active = i === state.pageIdx ? 'active' : '';
      const it = pageItems[i];
      const isNewNow = it && it.is_new && it.url && !state.seenUrls.has(it.url);
      const newCls = isNewNow ? 'news-page-btn--new' : '';
      parts.push(`<button class='news-page-btn ${active} ${newCls}' data-go='${i}' aria-label='第 ${i+1} 篇${newCls?' (NEW)':''}'>${String(i+1).padStart(2,'0')}</button>`);
      if (i < total - 1) parts.push(`<span class='news-page-sep'>·</span>`);
    }
    pagEl.innerHTML = parts.join('');
    pagEl.querySelectorAll('.news-page-btn').forEach(b => {
      b.addEventListener('click', () => gotoPage(parseInt(b.dataset.go, 10)));
    });
    // 数字多到横向滚动时, 把 active 数字滚到可视区中间
    const activeBtn = pagEl.querySelector('.news-page-btn.active');
    if (activeBtn && pagEl.scrollWidth > pagEl.clientWidth){
      const target = activeBtn.offsetLeft - (pagEl.clientWidth / 2) + (activeBtn.offsetWidth / 2);
      pagEl.scrollTo({left: Math.max(0, target), behavior: 'smooth'});
    }
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
    // 翻到新页 → 标已看过 (键盘 / 点页码 / 拖拽 / wrap 均经此入口)
    markCurrentSeen();
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

  // 切换到 news tab 时, 默认重置为 sources 模式 (避免上次离开停在收藏)
  const newsTab = document.querySelector('.tab-bar .tab[data-tab="news"]');
  if (newsTab){
    newsTab.addEventListener('click', () => {
      if (state.viewMode !== 'favorites') return;
      state.viewMode = 'sources';
      state.pageIdx = 0;
      if (modeToggleEl){
        modeToggleEl.dataset.modeCurrent = 'sources';
        modeToggleEl.classList.remove('active');
      }
      renderSrcList();
      renderSlides();
      renderPagination();
    });
  }

  // 监听 tab 切换: 激活 'news' tab 时, 侧栏回到第一个源 + github 时间维度重置为日
  function resetOnEnterNews(){
    state.srcIdx = 0;
    state.pageIdx = 0;
    state.githubSortBy = 'daily';
    state.viewMode = 'sources';
    if (modeToggleEl){
      modeToggleEl.dataset.modeCurrent = 'sources';
      modeToggleEl.classList.remove('active');
    }
    renderSrcList();
    renderSlides();
    renderPagination();
  }
  document.addEventListener('app:tabchange', e => {
    if (e && e.detail && e.detail.tabId === 'news') resetOnEnterNews();
  });

  // 点 reason popover 之外的任何位置关闭已打开的 popover
  document.addEventListener('click', e => {
    if (e.target.closest('.news-reason-wrap')) return;
    document.querySelectorAll('.news-reason-pop:not([hidden])').forEach(p => p.setAttribute('hidden', ''));
    document.querySelectorAll('.news-reason-toggle.open').forEach(btn => btn.classList.remove('open'));
  });

  renderSrcList();
  renderSlides();
  renderPagination();
})();
