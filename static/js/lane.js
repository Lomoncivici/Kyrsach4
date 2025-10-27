(() => {
  const $$ = (s, r=document)=>Array.from(r.querySelectorAll(s));

  function outerGap(track){
    const st = getComputedStyle(track);
    const gap = parseFloat(st.columnGap || st.gap || '0') || 0;
    return gap;
  }

  function cardFullWidth(card){
    const st = getComputedStyle(card);
    const ml = parseFloat(st.marginLeft || '0') || 0;
    const mr = parseFloat(st.marginRight || '0') || 0;
    return card.getBoundingClientRect().width + ml + mr;
  }

  function throttle(fn, ms){
    let t=0; return (...a)=>{ const now=Date.now(); if(now-t>=ms){ t=now; fn(...a); } };
  }

  function setupLane(lane){
    const viewport = lane.querySelector('.lane-viewport');
    const track    = lane.querySelector('.lane-track');
    const prev     = lane.querySelector('.lane-prev');
    const next     = lane.querySelector('.lane-next');
    const pageSize = parseInt(lane.dataset.pageSize, 10) || 4;

    if(!viewport || !track || !prev || !next) return;

    const getStep = () => {
      const cards = Array.from(track.children).filter(el => el.nodeType===1);
      if(!cards.length) return viewport.clientWidth;
      const w = cardFullWidth(cards[0]);
      const gap = outerGap(track);
      return (w * pageSize) + (gap * (pageSize - 1));
    };

    const scrollByStep = (dir) => {
      const step = getStep() * dir;
      viewport.scrollBy({ left: step, behavior: 'smooth' });
    };

    const updateNav = () => {
      const maxScroll = track.scrollWidth - viewport.clientWidth;
      const sl = viewport.scrollLeft;
      prev.style.display = sl > 2 ? '' : 'none';
      next.style.display = sl < (maxScroll - 2) ? '' : 'none';
    };

    prev.addEventListener('click', () => scrollByStep(-1));
    next.addEventListener('click', () => scrollByStep(1));
    viewport.addEventListener('scroll', throttle(updateNav, 100));
    window.addEventListener('resize', throttle(updateNav, 150));

    updateNav();
  }

  document.addEventListener('DOMContentLoaded', () => {
    $$('.lane').forEach(setupLane);
  });
})();
