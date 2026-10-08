/* ==========================================================================
   uppjs.com · 外观层 v2 的脚本
   --------------------------------------------------------------------------
   只做三件事，全部可降级：顶栏滚动态、hero 打字机、内容入场动效。
   不依赖任何外部库，不请求任何网络资源。原有脚本一行都不动。
   ========================================================================== */
(function () {
  'use strict';

  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var hd = document.querySelector('header, nav.topnav');

  /* ---------- 0. 把顶栏的真实高度写回 --hh ----------
     手机上顶栏会自动换行、变高，写死一个 58px 的话，
     下面的分类条、目录栏、锚点跳转全会错位。 */
  function syncHH() {
    if (!hd) return;
    var h = Math.round(hd.getBoundingClientRect().height);
    if (h > 0) document.documentElement.style.setProperty('--hh', h + 'px');
  }
  syncHH();
  window.addEventListener('resize', syncHH, { passive: true });
  window.addEventListener('load', syncHH);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(syncHH);
  /* 外观面板换个主题后，文字尺寸会变，顶栏高度可能跟着变 —— 对外暴露一个重测入口。 */
  window.UPPJS_REMEASURE = syncHH;

  /* ---------- 1. 顶栏：滚动后加底色 ---------- */
  if (hd) {
    var onScroll = function () {
      if (window.scrollY > 12) hd.classList.add('scrolled');
      else hd.classList.remove('scrolled');
    };
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
  }

  /* ---------- 2. hero 文案：直接显示 ----------
     —— 原来是打字机逐字蹦（带闪烁光标），2026-10-08 按用户要求改成一次性显示。
     HTML 里 data-typer-* 的属性名保留没动，省得模板跟着改；
     「本站态度」那个小标签仍然由这里渲染。
     顺带修了个原有小问题：旧代码在「减少动态效果」偏好下引言卡直接空白。 */
  function fillText(el, text) {
    if (!el) return;
    el.textContent = text;
  }

  var en = document.querySelector('[data-typer-en]');
  if (en) fillText(en, en.getAttribute('data-typer-en'));

  var q = document.querySelector('[data-typer-quote]');
  if (q) {
    var raw = q.getAttribute('data-typer-quote');
    q.innerHTML = '';
    var lab = document.createElement('span');
    lab.className = 'lab';
    lab.textContent = q.getAttribute('data-quote-label') || '本站态度';
    q.appendChild(lab);
    var holder = document.createElement('div');
    holder.textContent = raw;
    q.appendChild(holder);
  }

  /* ---------- 3. 入场动效：进入视口才播，逐个错开 ---------- */
  var items = [].slice.call(document.querySelectorAll('.reveal'));
  if (!items.length) return;

  if (reduce || !('IntersectionObserver' in window)) {
    items.forEach(function (el) { el.classList.add('in'); });
    return;
  }

  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      var el = e.target;
      var idx = parseInt(el.getAttribute('data-i') || '0', 10);
      el.style.animationDelay = Math.min(idx * 70, 420) + 'ms';
      el.classList.add('in');
      io.unobserve(el);
    });
  }, { rootMargin: '0px 0px -8% 0px', threshold: 0.06 });

  items.forEach(function (el, i) {
    if (el.hasAttribute('data-i') === false) el.setAttribute('data-i', String(i % 8));
    io.observe(el);
  });
})();
