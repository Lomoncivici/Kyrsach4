(function(){
  let last = window.scrollY || 0; const hb=document.getElementById('hotbar');
  window.addEventListener('scroll',()=>{
    const y=window.scrollY; if(!hb) return;
    if(y>last && y>80){hb.classList.add('hide')} else {hb.classList.remove('hide')} last=y;
  });

  const slider=document.querySelector('.hero__slider');
  if(slider){
    const slides=[...slider.querySelectorAll('.hero__slide')];
    let i=0; slides[0]?.classList.add('active');
    let timer; const play=()=>{timer=setInterval(()=>{slides[i].classList.remove('active');i=(i+1)%slides.length;slides[i].classList.add('active')}, 7000)};
    const stop=()=>{clearInterval(timer)}; play();
    slider.addEventListener('mouseenter',stop); slider.addEventListener('mouseleave',play);
  }

  const open=document.getElementById('openSupport'); const modal=document.getElementById('supportModal');
  if(open && modal){
    open.addEventListener('click',()=>modal.classList.add('open'));
    modal.querySelector('[data-close]')?.addEventListener('click',()=>modal.classList.remove('open'));
    modal.addEventListener('click',(e)=>{ if(e.target===modal) modal.classList.remove('open'); });
  }
})();

document.addEventListener("DOMContentLoaded", () => {
  const userMenu = document.querySelector(".user-menu");
  if (!userMenu) return;

  const dropdown = userMenu.querySelector(".user-menu__dropdown");
  let hideTimeout;

  userMenu.addEventListener("mouseenter", () => {
    clearTimeout(hideTimeout);
    dropdown.classList.add("show");
  });

  userMenu.addEventListener("mouseleave", () => {
    hideTimeout = setTimeout(() => {
      dropdown.classList.remove("show");
    }, 400);
  });
});