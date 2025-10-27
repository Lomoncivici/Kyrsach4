(() => {
  const $  = (sel, root=document) => root.querySelector(sel);
  const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));

  function initHeroSlider(opts = {}) {
    const slider = $(opts.root || '#heroSlider');
    if (!slider) return null;

    const slides = $$('.hero-slide', slider);
    const dotsWrap = $(opts.dots || '#heroDots');
    const dots = dotsWrap ? $$('.hero-dot', dotsWrap) : [];
    if (!slides.length) return null;

    const autoplay = ((slider.dataset.autoplay || '').toLowerCase() === 'true') || !!opts.autoplay;
    const interval = parseInt(slider.dataset.interval || opts.interval || 6000, 10);

    let current = 0;
    let timer = null;

    slides.forEach((s, idx) => s.style.display = idx === 0 ? 'block' : 'none');
    slides[0].classList.add('is-active');
    if (dots[0]) dots[0].classList.add('is-active');

    function setActive(i) {
      if (i === current) return;
      if (i < 0) i = slides.length - 1;
      if (i >= slides.length) i = 0;

      slides[current].classList.remove('is-active');
      slides[current].style.display = 'none';
      if (dots[current]) dots[current].classList.remove('is-active');

      current = i;

      slides[current].style.display = 'block';
      slides[current].classList.add('is-active');
      if (dots[current]) dots[current].classList.add('is-active');
    }

    function startAuto() {
      if (!autoplay) return;
      stopAuto();
      timer = setInterval(() => setActive(current + 1), interval);
    }
    function stopAuto() {
      if (timer) clearInterval(timer);
      timer = null;
    }

    dots.forEach(d => d.addEventListener('click', () => {
      const i = parseInt(d.dataset.index || '0', 10);
      setActive(i);
    }));

    window.addEventListener('keydown', (e) => {
      if (e.key === 'ArrowLeft')  setActive(current - 1);
      if (e.key === 'ArrowRight') setActive(current + 1);
    });

    $$('.hero-more').forEach(btn => {
      btn.addEventListener('click', () => {
        const id    = btn.getAttribute('data-target');
        const full  = btn.getAttribute('data-full');
        const short = btn.getAttribute('data-short');
        const p     = document.getElementById(id);
        const opened = btn.getAttribute('data-opened') === '1';
        if (p) p.textContent = opened ? short : full;
        btn.textContent = opened ? 'Раскрыть' : 'Свернуть';
        btn.setAttribute('data-opened', opened ? '0' : '1');
      });
    });

    startAuto();
    return { setActive, startAuto, stopAuto };
  }

  window.initHeroSlider = initHeroSlider;
  document.addEventListener('DOMContentLoaded', () => initHeroSlider());
})();