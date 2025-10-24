/* ===== helpers ===== */
function isYouTube(u){ return /(youtu\.be|youtube\.com)/i.test(u||''); }
function isRutube(u){ return /rutube\.ru/i.test(u||''); }

function mountIntoBox(hostOrBox, mediaEl){
  const box = (typeof hostOrBox === 'string') ? document.getElementById(hostOrBox) : hostOrBox;
  if (!box) return mediaEl;
  // если передали старый <video>, берём его родителя .player-box
  const container = box.classList?.contains('player-box')
    ? box
    : (box.parentElement?.classList?.contains('player-box') ? box.parentElement : box);
  container.innerHTML = '';
  container.appendChild(mediaEl);
  return mediaEl;
}

/* ===== Встраивание плееров ===== */
function mountYouTubeIframe(urlOrId, hostOrBox){
  const u = String(urlOrId || '');
  const m = u.match(/(?:v=|youtu\.be\/|embed\/|shorts\/)([A-Za-z0-9_-]{6,})/);
  const id = m ? m[1] : u;

  const src =
    `https://www.youtube-nocookie.com/embed/${id}` +
    `?playsinline=1&rel=0&modestbranding=1&autoplay=1&mute=0&origin=${encodeURIComponent(location.origin)}`;

  const iframe = document.createElement('iframe');
  iframe.src = src;
  iframe.allow = 'accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share';
  iframe.referrerPolicy = 'strict-origin-when-cross-origin';
  iframe.allowFullscreen = true;
  Object.assign(iframe.style, { width:'100%', aspectRatio:'16/9', border:'0', borderRadius:'12px' });

  return mountIntoBox(hostOrBox, iframe);
}

function mountRutubeIframe(url, hostOrBox){
  const u = String(url || '');
  const m = u.match(/rutube\.ru\/(?:video|play\/embed)\/([a-f0-9]{32})/i);
  const id = m ? m[1] : null;
  const base = id ? `https://rutube.ru/play/embed/${id}` :
              (u.includes('/play/embed/') ? u : u.replace('/video/','/play/embed/'));
  const iframe = document.createElement('iframe');
  iframe.src = base + (base.includes('?') ? '&' : '?') + 'autoplay=1';
  iframe.allow = 'autoplay; fullscreen; picture-in-picture';
  iframe.allowFullscreen = true;
  Object.assign(iframe.style, { width:'100%', aspectRatio:'16/9', border:'0', borderRadius:'12px' });

  return mountIntoBox(hostOrBox, iframe);
}

function mountFileVideo(src, hostOrBox){
  const v = document.createElement('video');
  v.controls = true; v.autoplay = true; v.preload = 'metadata';
  v.className = 'player';
  Object.assign(v.style, { width:'100%', borderRadius:'12px', background:'#000' });
  v.innerHTML = `<source src="${src}">`;
  return mountIntoBox(hostOrBox, v);
}

function csrftoken(){
  return document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
}

/* ===== Рейтинг (0.5 шага) ===== */
(function ratingInit(){
  const bar = document.getElementById('ratingBar'); 
  if (!bar) return;

  const avgEl = document.getElementById('avgRating');
  const fill  = bar.querySelector('.rating-bar__fill');
  const steps = bar.querySelectorAll('.rating-bar__step');
  const contentId = bar.dataset.contentId || bar.dataset.content_id; // ожидаем data-content-id

  const setFillByHalf = (half)=> { fill.style.width = (half * 10) + '%'; };
  const resetFill = ()=>{
    const avg = parseFloat(String(avgEl.textContent || '0').replace(',', '.')) || 0;
    setFillByHalf(Math.round(avg * 2));
  };
  resetFill();

  let busy = false;

  steps.forEach((btn, i)=>{
    const half = i + 1;

    btn.addEventListener('mouseenter', ()=> { if (!busy) setFillByHalf(half); });
    btn.addEventListener('mouseleave', ()=> { if (!busy) resetFill(); });

    btn.addEventListener('click', async ()=>{
      if (busy || !contentId) return;
      busy = true; bar.classList.add('is-loading');

      const value = Math.round(half / 2);

      try{
        const res = await fetch(`/api/v1/content/${contentId}/rate/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': csrftoken(),
            'X-Requested-With': 'fetch',
          },
          body: `value=${encodeURIComponent(value)}`
        });

        if (res.status === 401 || res.status === 403) {
          // при необходимости — редирект на логин
          location.href = `/accounts/login/?next=${encodeURIComponent(location.pathname + location.search)}`;
          return;
        }

        const data = await res.json();
        if (data?.ok) {
          avgEl.textContent = Number(data.avg).toFixed(1).replace('.', ',');
          resetFill();
        }
      } catch(e) {
        // можно добавить показ ошибки пользователю
      } finally {
        busy = false; bar.classList.remove('is-loading');
      }
    });
  });
})();

/* ===== Трейлер (модалка) ===== */
(function trailerModalInit(){
  const ctx = window.CONTENT_CTX || {};
  const url = ctx.trailerUrl;
  const openBtn = document.getElementById('openTrailer');
  const modal = document.getElementById('trailerModal');
  const closeBtn = document.getElementById('closeTrailer');
  const container = document.getElementById('trailerContainer');
  if(!openBtn || !modal) return;

  function open(){
    modal.classList.add('show');
    const mountHost = container.appendChild(document.createElement('div'));
    if(isYouTube(url))      mountYouTubeIframe(url, mountHost);
    else if(isRutube(url))  mountRutubeIframe(url, mountHost);
    else {
      const vid=document.createElement('video');
      vid.controls=true; vid.autoplay=true; vid.preload='metadata';
      Object.assign(vid.style, {width:'100%', height:'100%'});
      vid.innerHTML = `<source src="${url}">`;
      container.innerHTML=''; container.appendChild(vid);
    }
  }
  function close(){ modal.classList.remove('show'); container.innerHTML=''; }

  openBtn.addEventListener('click', open);
  closeBtn.addEventListener('click', close);
  modal.querySelector('.modal__backdrop')?.addEventListener('click', close);
})();

/* ===== Основной плеер (фильмы) ===== */
(function movieAutoLoad(){
  const ctx = window.CONTENT_CTX || {};
  const boxId = 'moviePlayerBox';
  if (ctx.type !== 'movie' || !ctx.canWatch) return;

  (async ()=>{
    try{
      const data = await API.get(`/content/${ctx.id}/source/`);
      if (!data.ok) return;
      if (data.kind === 'youtube'){
        const ifr = mountYouTubeIframe(data.url, boxId);
        attachYouTubeProgress(ifr, {contentId: ctx.id});
      } else if (data.kind === 'rutube'){
        mountRutubeIframe(data.url, boxId); // прогресс для Rutube можно добавить позже
      } else {
        const v = mountFileVideo(data.url, boxId);
        attachHtml5Progress(v, {contentId: ctx.id});
      }
    }catch(e){}
  })();
})();

/* ===== СЕРИАЛ: сезоны -> серии (панель остаётся на месте) ===== */
(function seriesSelector(){
  const panel = document.getElementById('seriesPanel');
  if (!panel) return;

  // читаем JSON из <script id="seasons-data">
  let raw = [];
  try { raw = JSON.parse(document.getElementById('seasons-data')?.textContent || '[]'); } catch(_) {}

  // нормализуем структуру ключей, т.к. в БД могут называться по-разному
  const seasons = (Array.isArray(raw) ? raw : []).map((s, si) => {
    const sn = Number(s.season_num ?? s.season ?? s.number ?? s.index ?? (si + 1));
    const episodes = (s.episodes || []).map((e, ei) => ({
      en: Number(e.episode_num ?? e.number ?? e.episode ?? e.index ?? (ei + 1)),
      title: e.title ?? e.name ?? '',
      video_url: e.video_url || ''
    }));
    return { sn, episodes };
  });

  const seasonsView  = panel.querySelector('#seasonsView');
  const episodesView = panel.querySelector('#episodesView');
  const seasonsGrid  = panel.querySelector('#seasonsGrid');
  const episodesList = panel.querySelector('#episodesList');
  const backBtn      = panel.querySelector('#backToSeasons');
  const playerEl     = document.getElementById('seriesPlayer');
  const ctx          = window.CONTENT_CTX || {};

  if (!seasons.length) {
    seasonsGrid.innerHTML = '<div style="opacity:.7">Нет данных по сезонам</div>';
    return;
  }

  // перерисуем грид по нормализованным данным
  seasonsGrid.innerHTML = seasons.map(s =>
    `<button class="season-btn" data-sn="${s.sn}"
       style="padding:10px 12px;border-radius:10px;border:1px solid #2a2f3a;background:#111522;color:#e6eaf0;">
       Сезон ${s.sn}</button>`
  ).join('');

  backBtn.addEventListener('click', ()=>{
    episodesView.classList.add('hidden');
    seasonsView.classList.remove('hidden');
  });

  seasonsGrid.addEventListener('click', (e)=>{
    const btn = e.target.closest('.season-btn'); if(!btn) return;
    const sn  = Number(btn.dataset.sn);
    const season = seasons.find(s => s.sn === sn);
    if(!season) return;

    episodesList.innerHTML = season.episodes.map(ep => `
      <button class="episode-btn"
              data-sn="${season.sn}"
              data-en="${ep.en}"
              ${ep.video_url ? `data-url="${ep.video_url}"` : ''}>
        Серия ${ep.en} — ${ep.title}
      </button>
    `).join('');

    seasonsView.classList.add('hidden');
    episodesView.classList.remove('hidden');
  });

  episodesList.addEventListener('click', async (e)=>{
  const btn = e.target.closest('.episode-btn'); if(!btn) return;
  const sn  = btn.dataset.sn, en = btn.dataset.en;
  try{
    const data = await API.get(`/content/${ctx.id}/episode-source/?sn=${sn}&en=${en}`);
    if (!data.ok) return;
    if (data.kind === 'youtube'){
      const ifr = mountYouTubeIframe(data.url, 'seriesPlayerBox');
      attachYouTubeProgress(ifr, {contentId: ctx.id, sn, en});
    } else if (data.kind === 'rutube'){
      mountRutubeIframe(data.url, 'seriesPlayerBox');
    } else {
      const v = mountFileVideo(data.url, 'seriesPlayerBox');
      attachHtml5Progress(v, {contentId: ctx.id, sn, en});
    }
  }catch(_){}
});

function csrftoken(){
  return document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
}
const API = {
  base: '/api/v1',
  url(p){ return `${this.base}${p}`; },
  async get(p){
    const r = await fetch(this.url(p), { headers:{'X-Requested-With':'fetch'} });
    if (!r.ok) throw new Error('API GET failed');
    return r.json();
  },
  async postForm(p, data){
    const body = new URLSearchParams(data);
    const r = await fetch(this.url(p), {
      method:'POST',
      headers:{
        'Content-Type':'application/x-www-form-urlencoded',
        'X-CSRFToken': csrftoken(),
        'X-Requested-With':'fetch'
      },
      body: body.toString()
    });
    if (!r.ok) throw new Error('API POST failed');
    return r.json();
  }
};

const ProgressAPI = {
  url(id, sn=0, en=0){ return API.url(`/content/${id}/progress/?sn=${sn}&en=${en}`); },
  async get(id, sn=0, en=0){
    const r = await fetch(this.url(id,sn,en), { headers:{'X-Requested-With':'fetch'} });
    if (!r.ok) return { position_sec:0 };
    return r.json();
  },
  async post(id, {sn=0, en=0, position=0, duration=0, completed=false}){
    return API.postForm(`/content/${id}/progress/`, {
      sn, en,
      position: Math.floor(position||0),
      duration: duration==null ? '' : Math.floor(duration||0),
      completed: completed ? '1' : '0'
    });
  }
};

(function purchaseInit(){
  const ctx = window.CONTENT_CTX || {};
  const btn = document.getElementById('buyBtn');
  if (!btn) return;
  btn.addEventListener('click', async ()=>{
    try{
      const res = await API.postForm(`/purchases/`, { content_id: ctx.id });
      if (res.ok){
        // после покупки просто перезагрузим страницу (canWatch станет true)
        location.reload();
      } else {
        alert('Не удалось оформить покупку');
      }
    }catch(e){
      alert('Ошибка покупки');
    }
  });
})();
