(() => {

  const root = document.getElementById('content-root');
  if (!root) return;

  const coverImg = document.getElementById('coverImg');
  const openTrailerBtn = document.getElementById('openTrailerBtn');
  const openMainBtn = document.getElementById('openMainBtn');
  const playerFrame = document.getElementById('playerFrame');
  const IS_AUTH = (typeof window !== 'undefined' && window.IS_AUTH === true);
  const trailerUrl = root.dataset.trailerUrl || "";
  const mainUrl = root.dataset.mainUrl || "";
  const canWatch = root.dataset.canWatch === "1";

  function hideInlinePlayer(){
    if (playerFrame){
      try { playerFrame.removeAttribute('src'); } catch(e){}
      playerFrame.style.display = 'none';
    }
    if (coverImg) coverImg.style.display = '';
  }

  if (!IS_AUTH) {
    const bar = document.getElementById('ratingBar');
    if (bar) bar.remove();
    window.ratingInit = () => {};
  }

  function setPosterRatio(){
    if (!coverImg) return;
    if (coverImg.naturalWidth && coverImg.naturalHeight){
      const ratio = coverImg.naturalWidth / coverImg.naturalHeight;
      const art = coverImg.closest('.art');
      if (art) art.style.setProperty('--img-ratio', ratio);
    }
  }
  if (coverImg){
    if (coverImg.complete) setPosterRatio();
    coverImg.addEventListener('load', setPosterRatio);
  }

  if (openTrailerBtn){
    openTrailerBtn.addEventListener('click', () => {
      if (!playerFrame) return;
      if (!trailerUrl){
        alert('Трейлер недоступен');
        return;
      }
      playerFrame.src = trailerUrl;
      playerFrame.style.display = 'block';
      playerFrame.scrollIntoView({behavior:'smooth', block:'start'});
    });
  }

  const $  = (sel, root=document) => root.querySelector(sel);
  const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));

  function getCookie(name){
    const m = document.cookie.match('(^|;)\\s*'+name+'\\s*=\\s*([^;]+)');
    return m ? m.pop() : '';
  }
  function toEmbed(u){
    if(!u) return "";
    const s = String(u);
    const origin = encodeURIComponent(location.origin);

    if (s.includes("youtube.com/watch")) {
      try{
        const url = new URL(s);
        const v = url.searchParams.get("v") || "";
        if (!v) return s;
        return `https://www.youtube-nocookie.com/embed/${v}?rel=0&modestbranding=1&playsinline=1&iv_load_policy=3&fs=1&origin=${origin}`;
      }catch{ return s; }
    }
    if (s.includes("youtu.be/")) {
      const vid = s.split("/").pop();
      return `https://www.youtube-nocookie.com/embed/${vid}?rel=0&modestbranding=1&playsinline=1&iv_load_policy=3&fs=1&origin=${origin}`;
    }

    if (s.includes("rutube.ru")) {
      if (s.includes("/video/") && !s.includes("/play/embed/")) {
        const match = s.match(/rutube\.ru\/video\/([a-f0-9]{32})/i);
        if (match && match[1]) {
          return `https://rutube.ru/play/embed/${match[1]}/?autoplay=1&mute=0`;
        }
      }
      if (s.includes("/play/embed/")) {
        const baseUrl = s.split('?')[0];
        const params = new URLSearchParams(s.split('?')[1] || '');
        params.set('autoplay', '1');
        params.set('mute', '0');
        return baseUrl + '?' + params.toString();
      }
    }
    return s;
  }
  function getContentId(){
    if (window.ctx && (ctx.id || (window.ctx && window.ctx.id))) return String(window.ctx.id || ctx.id);
    const host = $("#content-root,[data-content-id]"); if(host?.dataset?.contentId) return host.dataset.contentId;
    const last = location.pathname.split("/").filter(Boolean).pop() || ""; return last.length >= 32 ? last : null;
  }

  function getCSRF(){
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? m[1] : '';
  }
  function setFavUI(btn, isFav){
    btn.classList.toggle('is-fav', !!isFav);
    btn.setAttribute('aria-pressed', !!isFav);
    btn.textContent = (isFav ? '★ В избранном' : '☆ Добавить в избранное');
  }

  async function apiJson(url, opts={}){
    const resp = await fetch(url, { credentials: 'include', ...opts });
    let data = {};
    try{ data = await resp.json(); }catch{}
    if(!resp.ok){ throw new Error(data.detail || data.reason || `HTTP ${resp.status}`); }
    return data;
  }

  async function postProgress(contentId, position=0, duration=null, sn=0, en=0, completed=false){
    try{
      await apiJson(`/api/v1/content/${contentId}/progress/`, {
        method:'POST',
        headers:{
          'Content-Type':'application/json',
          'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({ position, duration, sn, en, completed })
      });
    }catch(_e){}
  }

  function ensurePlayerIframe(){
    let iframe = $("#playerFrame");
    if(iframe) return iframe;
    let host = $(".player") || $(".player-block") || $("#content-root") || document.body;
    iframe = document.createElement("iframe");
    iframe.id = "playerFrame";
    iframe.setAttribute("frameborder","0"); iframe.setAttribute("allowfullscreen","");
    iframe.setAttribute("allow", "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share");
    iframe.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
    iframe.style.display = "none"; iframe.style.width="100%"; iframe.style.aspectRatio="16/9";
    host.appendChild(iframe);
    return iframe;
  }
  function ensureCover(){
    let img = $("#coverImg");
    if(img) return img;
    const host = $(".player") || $(".art") || $("#content-root") || document.body;
    img = document.createElement("img"); img.id = "coverImg"; img.style.maxWidth="100%";
    host.appendChild(img); return img;
  }
  function ensureTrailerButton(){
    let btn = $("#openTrailerBtn") || $$(".btn").find(b => /трейлер/i.test(b.textContent||""));
    if(btn) return btn;
    const host = $(".controls-row") || $(".info") || $("#content-root") || document.body;
    btn = document.createElement("button"); btn.type="button"; btn.id="openTrailerBtn"; btn.className="btn"; btn.textContent="Трейлер";
    host.appendChild(btn); return btn;
  }

  function mountSeriesPanelHost(){
    const controls = document.querySelector('.controls-row') || document.querySelector('.info') || document.getElementById('content-root') || document.body;
    let panel = document.getElementById('seriesPanel');
    if(panel) { panel.style.display = ''; return panel; }
    panel = document.createElement('div');
    panel.id = 'seriesPanel';
    panel.className = 'card';
    panel.style.marginTop = '12px';
    panel.innerHTML = `
      <div class="card__header" style="display:flex;align-items:center;justify-content:space-between;">
        <div class="card__title">Сезоны</div>
        <button id="seriesBackBtn" class="btn" type="button" style="display:none;">Вернуться к сезонам</button>
      </div>
      <div class="card__body" id="seriesPanelBody"></div>
    `;
    panel.style.display = '';
    const trailerBtn = document.getElementById('openTrailerBtn');
    if(trailerBtn && trailerBtn.parentElement){
      trailerBtn.parentElement.insertBefore(panel, trailerBtn.nextSibling);
    }else{
      controls.appendChild(panel);
    }
    return panel;
  }
  
  function makeSeasonLabel(s, idx){
    const num = Number(s.season_num ?? s.number ?? s.num ?? (idx + 1));
    if (s.display_title && s.display_title.trim()) return s.display_title.trim();
    if (s.title && String(s.title).trim()) return String(s.title).trim();
    return `Сезон ${isFinite(num) && num > 0 ? num : (idx + 1)}`;
  }
  function getSeasonNumber(s, idx){
    const n = Number(s.season_num ?? s.number ?? s.num ?? (idx + 1));
    return isFinite(n) && n > 0 ? n : (idx + 1);
  }

  function renderSeasonsList(tree){
    const body = document.getElementById('seriesPanelBody');
    const back = document.getElementById('seriesBackBtn');
    const titleEl = document.querySelector('#seriesPanel .card__title');
    if(titleEl) titleEl.textContent = 'Сезоны';
    if(!body) return;
    back.style.display = 'none';
    body.innerHTML = `<div class="season-list"></div>`;
    const box = body.querySelector('.season-list');
    tree.forEach((s, idx) => {
      const b = document.createElement('button');
      b.className = 'btn';
      b.textContent = makeSeasonLabel(s, idx);
      b.dataset.sn = String(getSeasonNumber(s, idx));
      b.style.margin = '6px 8px 0 0';
      box.appendChild(b);
    });
  }

  function renderEpisodesList(tree, sn){
    const season = tree.find(x => String(x.season_num ?? x.number ?? x.num) === String(sn));
    const body = document.getElementById('seriesPanelBody');
    const back = document.getElementById('seriesBackBtn');
    const titleEl = document.querySelector('#seriesPanel .card__title');
    if(titleEl) titleEl.textContent = 'Серии';
    if(!season || !body) return;
    back.style.display = '';
    body.innerHTML = `<div class="episode-list" style="display:flex;flex-wrap:wrap;"></div>`;
    const box = body.querySelector('.episode-list');
    (season.episodes || []).forEach(e=>{
      const b = document.createElement('button');
      b.className = 'btn';
      b.textContent = e.title || `Серия ${e.number}`;
      b.dataset.sn = String(season.season_num ?? season.number ?? season.num ?? 1);
      b.dataset.en = String(e.number);
      b.style.margin = '6px 8px 0 0';
      box.appendChild(b);
    });
  }

  function ensureWatchButton(){
    let btn = document.getElementById('openMainBtn')
          || Array.from(document.querySelectorAll('.btn')).find(b => /смотреть/i.test(b.textContent||''));
    if(btn){ btn.id = 'openMainBtn'; return btn; }
    const host = document.querySelector('.controls-row') || document.querySelector('.info') || document.getElementById('content-root') || document.body;
    btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'openMainBtn';
    btn.className = 'btn';
    btn.textContent = 'Смотреть';
    host.appendChild(btn);
    return btn;
  }

  function openMainPlayer(kind, url, contentId, contentType){
    const origin = encodeURIComponent(location.origin);
    let inner = '';
    if (kind === 'youtube' || kind === 'rutube'){
      const src = (toEmbed(url) + (url.includes('?') ? '&' : '?') + 'autoplay=1');
      inner = `<iframe src="${src}" frameborder="0" allowfullscreen
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                referrerpolicy="strict-origin-when-cross-origin"
                style="width:100%;height:100%;display:block;"></iframe>`;
    } else {
      inner = `<video controls autoplay style="width:100%;height:100%;display:block;">
                <source src="${url}">
              </video>`;
    }
    const wrap = document.createElement('div');
    wrap.className = 'overlay';
    wrap.innerHTML = `
      <div class="overlay__inner">
        <div class="card">
          <div class="card__header" style="display:flex;align-items:center;justify-content:space-between;padding:10px 12px;">
            <div class="card__title">${(typeof detail!=='undefined' && detail && detail.title) ? detail.title : 'Просмотр'}</div>
            <button class="btn overlay__close" type="button" aria-label="Закрыть">×</button>
          </div>
          <div class="card__body" style="padding:0">
            <div class="player" style="aspect-ratio:16/9;">${inner}</div>
          </div>
        </div>
      </div>`;
    document.body.appendChild(wrap);
    const v = wrap.querySelector('video');
    if(v){
      let lastSent = 0;
      const tick = () => {
        const pos = Math.floor(v.currentTime || 0);
        if(pos - lastSent >= 30){
          lastSent = pos;
          postProgress(
            contentId,
            pos,
            isNaN(v.duration) ? null : Math.floor(v.duration),
            (contentType === 'series' ? 1 : 0),
            (contentType === 'series' ? 1 : 0),
            false
          );
        }
      };
      v.addEventListener('timeupdate', tick);
      v.addEventListener('ended', () => {
        postProgress(
          contentId,
          Math.floor(v.duration || 0),
          Math.floor(v.duration || 0),
          (contentType === 'series' ? 1 : 0),
          (contentType === 'series' ? 1 : 0),
          true
        );
      });
    }
    const close = wrap.querySelector('.overlay__close');
    const esc = (e)=>{ if(e.key==='Escape'){ wrap.remove(); document.removeEventListener('keydown', esc);} };
    close.addEventListener('click', ()=>{ wrap.remove(); document.removeEventListener('keydown', esc); });
    document.addEventListener('keydown', esc);
  }

  function ensureRatingBar(){
    if (!IS_AUTH) return null;
    let bar = $("#ratingBar");
    if(!bar){
      const host = $(".meta-row") || $(".info") || $("#content-root") || document.body;
      bar = document.createElement("div");
      bar.id="ratingBar";
      bar.className="rating-bar";
      bar.innerHTML = `<div class="rating-bar__fill"></div><div class="rating-bar__steps"></div><span id="avgRating">-</span>`;
      host.appendChild(bar);
    }

    const contentId = root.dataset.contentId;
    if(contentId){
      bar.dataset.postUrl = `/api/v1/content/${contentId}/rate/`;
    }

    const steps = $(".rating-bar__steps", bar);
    if(steps && steps.children.length < 10){
      steps.innerHTML = "";
      for(let i=0;i<10;i++){
        const s=document.createElement("span");
        s.className="rating-bar__step";
        s.dataset.half = (i+1);
        steps.appendChild(s);
      }
    }
    return bar;
}

  function initRating(bar) {
    if (!bar) return;

    const fill  = bar.querySelector('.rating-bar__fill');
    const steps = bar.querySelectorAll('.rating-bar__step');
    const avgEl = document.getElementById('avgRating');

    const setFillByHalf = (half) => {
        if(fill) fill.style.width = Math.min(Math.max(half*10,0),100)+'%';
    };

    const resetFill = () => {
        const avg = parseFloat(String(avgEl?.textContent || '0').replace(',', '.')) || 0;
        setFillByHalf(avg*2);
    };

    resetFill();

    const root = document.getElementById('content-root');
    if (!root) return;

    const contentId = root.dataset.contentId;
    if (!contentId) return;

    const postUrl = `/api/v1/content/${contentId}/rate/`;
    const getUrl  = `/api/v1/content/${contentId}/`;
    bar.dataset.postUrl = postUrl;

    steps.forEach((el, i) => {
        const half = i + 1;

        el.addEventListener('mouseenter', () => setFillByHalf(half));
        el.addEventListener('mouseleave', resetFill);

        el.addEventListener('click', async () => {
            const value = Math.round(half / 2);
            setFillByHalf(half);

            try {
                const resp = await fetch(postUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRFToken': getCSRF()
                    },
                    body: JSON.stringify({ value }),
                    credentials: 'same-origin'
                });
                if (!resp.ok) throw new Error('Ошибка сервера при отправке рейтинга');

                const dataResp = await fetch(getUrl, { credentials: 'same-origin' });
                if (!dataResp.ok) throw new Error('Ошибка сервера при получении рейтинга');


                const data = await resp.json();
                if (data.avg !== undefined && avgEl) {
                    const avg = parseFloat(String(data.avg).replace(',', '.')) || 0;
                    avgEl.textContent = avg.toFixed(1);
                    setFillByHalf(avg*2);
                }

            } catch (err) {
                console.error(err);
                alert('Не удалось обновить рейтинг');
                resetFill();
            }
        });
    });
 }

  async function ensureFavoriteButton(contentId){
    const btn = document.getElementById('favBtn');
    if (!btn) return;

    try{
      if (btn.dataset.checkUrl){
        const res = await fetch(btn.dataset.checkUrl, { credentials:'same-origin' });
        if (res.ok){
          const data = await res.json();
          if (typeof data.is_favorite === 'boolean'){
            setFavUI(btn, data.is_favorite);
          }
        }
      }
    }catch{}

    btn.addEventListener('click', async (e)=>{
      e.preventDefault();
      if (btn.disabled) return;
      btn.disabled = true;

      const wasFav = btn.classList.contains('is-fav');
      setFavUI(btn, !wasFav);

      try{
        const res = await fetch(btn.dataset.postUrl, {
          method: 'POST',
          headers: { 'X-CSRFToken': getCSRF() },
          credentials: 'same-origin'
        });
        if (!res.ok){
          setFavUI(btn, wasFav);
          alert('Не удалось обновить избранное');
        }
      }catch{
        setFavUI(btn, wasFav);
        alert('Сеть недоступна');
      }finally{
        btn.disabled = false;
      }
    });
  }

  async function startMovieOverlay(contentId){
    try{
      const s = await apiJson(`/api/v1/content/${contentId}/source/`);
      if (s.ok && s.url){
        await postProgress(contentId, 0, null, 0, 0, false);
        openMainPlayer(s.kind, s.url, contentId, 'movie');
      } else {
        alert('Источник недоступен');
      }
    }catch{ alert('Источник недоступен'); }
  }


  document.addEventListener('DOMContentLoaded', async () => {
    const cid = getContentId(); 
    if (!cid) return;

    hideInlinePlayer();

    const iframe = ensurePlayerIframe();
    const cover  = ensureCover();

    const bar = ensureRatingBar();
    initRating(bar);

    ensureFavoriteButton(cid);

    let ctype='movie', trailerUrl='', posterUrl='', isFree=false, detail=null;
    try{
      detail = await apiJson(`/api/v1/content/${cid}/`);
      ctype = detail.type || 'movie';
      trailerUrl = detail.trailer_url || '';
      posterUrl = detail.poster_url || '';
      isFree = !!detail.is_free;
      if(posterUrl) cover.src = posterUrl;
      let seriesTree = null;
      let seriesAllowed = false;

      const avgEl = document.getElementById('avgRating');

      if (ctype === 'series') {
        const watchBtn = document.getElementById('openMainBtn');
        if (watchBtn) watchBtn.style.display = 'none';

        seriesAllowed = !!isFree;
        if (!seriesAllowed) {
          try {
            const cw = await apiJson(`/api/v1/content/${cid}/can_watch/`);
            seriesAllowed = !!cw.can_watch;
          } catch (_) { seriesAllowed = false; }
        }

        const panel = document.getElementById('seriesPanel') || mountSeriesPanelHost();

        if (!seriesAllowed) {
          if (panel) panel.style.display = 'none';
        } else {
          if (panel) panel.style.display = '';
          const wbtn = document.getElementById('openMainBtn');
          if (wbtn) wbtn.style.display = 'none';
          try{
            const t = await apiJson(`/api/v1/content/${cid}/series-tree/`);
            if(t.ok){
              seriesTree = t.seasons || [];
              renderSeasonsList(seriesTree);
            }
          }catch{}
        }
      }

      const bg = document.querySelector('.page-bg');
      const bgUrl = detail.backdrop_url || detail.logo_wide_url || null;
      if (bg && bgUrl){
        bg.style.setProperty('--bg', `url('${bgUrl}')`);
        bg.classList.remove('page-bg--empty');
      }
      
      document.getElementById('seriesPanel')?.addEventListener('click', async (e)=>{
        const el = e.target.closest('button');
        if(!el) return;

        if(el.id === 'seriesBackBtn'){
          if(seriesTree) renderSeasonsList(seriesTree);
          return;
        }
        if(el.dataset.sn && !el.dataset.en){
          renderEpisodesList(seriesTree || [], el.dataset.sn);
          return;
        }
        if(el.dataset.sn && el.dataset.en){
          if(!seriesAllowed){
            alert('Контент доступен только после покупки или по подписке.');
            return;
          }

          const sn = parseInt(el.dataset.sn, 10) || 1;
          const en = parseInt(el.dataset.en, 10) || 1;
          try{
            const s  = await apiJson(`/api/v1/content/${cid}/episode-source/?sn=${sn}&en=${en}`);
            if(s.ok && s.url){
              await postProgress(cid, 0, null, sn, en, false);
              openMainPlayer(s.kind, s.url, cid, 'series');
            }else{
              alert('Источник недоступен');
            }
          }catch{ alert('Источник недоступен'); }
        }
      });
      if(avgEl && typeof detail.avg_rating !== 'undefined'){ avgEl.textContent = Number(detail.avg_rating||0).toFixed(1); }
    }catch{}

    if (!isFree) {
      let allowed = false;
      try {
        const cw = await apiJson(`/api/v1/content/${cid}/can_watch/`);
        allowed = !!cw.can_watch;
      } catch { allowed = false; }

      if (ctype === 'movie') {
        const mainBtn = ensureWatchButton();
        if (allowed) {
          mainBtn.style.display = '';
          mainBtn.onclick = async (e) => { e.preventDefault(); await startMovieOverlay(cid); };
        } else {
          mainBtn.style.display = 'none';
        }
      }
    } else if (ctype === 'movie') {
      const mainBtn = ensureWatchButton();
      mainBtn.style.display = '';
      mainBtn.onclick = async (e) => { e.preventDefault(); await startMovieOverlay(cid); };
    }

    const trailerBtn = ensureTrailerButton();
    trailerBtn.addEventListener('click', () => {
      let src = trailerUrl ? toEmbed(trailerUrl) : '';
      if(!src && detail){ src = detail.trailer_url ? toEmbed(detail.trailer_url) : ''; }
      if(!src){ alert('Трейлер недоступен'); return; }

      src += (src.includes('?') ? '&' : '?') + 'autoplay=1';

      const wrap = document.createElement('div');
      wrap.className = 'overlay';

      wrap.innerHTML = `
        <div class="overlay__inner">
          <div class="card">
            <div class="card__header" style="display:flex;align-items:center;justify-content:space-between;padding:10px 12px;">
              <div class="card__title">${(detail && detail.title) ? detail.title : 'Трейлер'}</div>
              <button class="btn overlay__close" type="button" aria-label="Закрыть">×</button>
            </div>
            <div class="card__body" style="padding:0">
              <div class="player" style="aspect-ratio:16/9;">
                <iframe src="${src}" frameborder="0" allowfullscreen
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                        referrerpolicy="strict-origin-when-cross-origin"
                        style="width:100%; height:100%; display:block;"></iframe>
              </div>
            </div>
          </div>
        </div>`;

      document.body.appendChild(wrap);

      const close = wrap.querySelector('.overlay__close');
      const onClose = () => { wrap.remove(); document.removeEventListener('keydown', esc); };
      const esc = (e) => { if(e.key === 'Escape') onClose(); };
      close.addEventListener('click', onClose);
      document.addEventListener('keydown', esc);
    });
    ensureFavoriteButton();
  });
})();