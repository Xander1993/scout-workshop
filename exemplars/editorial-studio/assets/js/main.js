/* =============================================================
   Quire — motion
   GSAP + ScrollTrigger + Lenis. Techniques: photographic parallax
   hero + mouse-tilt, scroll grade, word reveals, velocity skew,
   clip-path plate reveals, animated counters, magnetic CTA.
   Fail-safe: if anything throws, all content is shown.
   ============================================================= */

(function () {
  'use strict';

  const root = document.documentElement;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- 0. fail-safe settle ---------- */
  const settle = () => {
    document.querySelectorAll('.word').forEach(el => { el.style.transform = 'translateY(0)'; el.style.opacity = '1'; });
    document.querySelectorAll('.plate__frame').forEach(el => { el.style.clipPath = 'inset(0 0 0 0)'; });
    document.querySelectorAll('.plate__frame img').forEach(el => { el.style.transform = 'scale(1)'; });
    document.querySelectorAll('[data-counter]').forEach(el => { if (el.textContent.trim() === '0') el.textContent = (+el.dataset.to).toLocaleString(); });
  };
  let settleTimer = setTimeout(settle, 4200);
  // independent hard backstop: nothing stays hidden past 6s no matter what
  setTimeout(() => {
    document.querySelectorAll('.field__h, .closing__line, .plate, .strip__slab').forEach(n => n.classList.add('is-in'));
  }, 6000);

  /* ---------- 1. wait for libs ---------- */
  const ready = () => {
    if (!window.gsap || !window.ScrollTrigger || !window.Lenis) return setTimeout(ready, 60);
    try { boot(); } catch (e) { console.error('[quire]', e); settle(); }
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready);
  else ready();

  function boot () {
    const { gsap } = window;
    gsap.registerPlugin(window.ScrollTrigger);
    const ST = window.ScrollTrigger;

    /* ---------- Lenis <-> ScrollTrigger bridge ---------- */
    let lenis = null;
    if (!reduced) {
      lenis = new window.Lenis({
        duration: 0.9,
        easing: t => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
        wheelMultiplier: 1.2,
        smoothWheel: true
      });
      lenis.on('scroll', ST.update);
      gsap.ticker.add(t => lenis.raf(t * 1000));
      gsap.ticker.lagSmoothing(0);
    }
    clearTimeout(settleTimer);

    /* ---------- 2. word reveals (manifesto + closing) ---------- */
    gsap.utils.toArray('.field__h, .closing__line').forEach(node => {
      const words = node.querySelectorAll('.word');
      if (!words.length) return;
      ST.create({
        trigger: node, start: 'top 84%', once: true,
        onEnter: () => { node.classList.add('is-in'); gsap.to(words, { yPercent: 0, duration: 1.0, ease: 'expo.out', stagger: 0.04 }); }
      });
    });

    /* ---------- 3. HERO — gentle scroll grade + parallax + tilt ---------- */
    const stage = document.querySelector('.stage');
    if (stage && !reduced) {
      ST.create({
        trigger: stage, start: 'top top', end: 'bottom bottom', scrub: 0.6,
        onUpdate: (self) => {
          const p = self.progress;
          root.style.setProperty('--sun-sat', (1 - p * 0.10).toFixed(3));
          root.style.setProperty('--sun-bri', (1 - p * 0.22).toFixed(3));
          root.style.setProperty('--sun-hue', (-p * 6).toFixed(2) + 'deg');
        }
      });

      const layers = document.querySelectorAll('[data-layer]');
      layers.forEach(layer => {
        ST.create({
          trigger: stage, start: 'top top', end: 'bottom bottom', scrub: true,
          onUpdate: self => { layer._scrollY = (self.progress - 0.5) * (parseFloat(layer.dataset.depth) || 20) * 4; applyLayer(layer); }
        });
      });

      const diorama = document.querySelector('[data-diorama]');
      let mx = 0, my = 0, tx = 0, ty = 0;
      window.addEventListener('mousemove', (e) => { mx = (e.clientX / window.innerWidth - 0.5); my = (e.clientY / window.innerHeight - 0.5); }, { passive: true });
      gsap.ticker.add(() => {
        tx += (mx - tx) * 0.06; ty += (my - ty) * 0.06;
        if (diorama) diorama.style.transform = 'rotateX(' + (-ty * 2).toFixed(2) + 'deg) rotateY(' + (tx * 2.6).toFixed(2) + 'deg)';
        layers.forEach(l => { l._mouseX = tx * (parseFloat(l.dataset.depth) || 0) * 0.5; l._mouseY = ty * (parseFloat(l.dataset.depth) || 0) * 0.35; applyLayer(l); });
      });
      function applyLayer (l) {
        const sx = l._mouseX || 0; const sy = (l._scrollY || 0) + (l._mouseY || 0);
        l.style.transform = 'translate3d(' + sx.toFixed(2) + 'px,' + sy.toFixed(2) + 'px,0)';
      }
    }

    /* ---------- 4. process cards tone-in on enter ---------- */
    gsap.utils.toArray('.strip__slab').forEach(slab => {
      ST.create({ trigger: slab, start: 'top 72%', end: 'bottom 28%',
        onEnter: () => slab.classList.add('is-in'), onLeave: () => slab.classList.remove('is-in'),
        onEnterBack: () => slab.classList.add('is-in'), onLeaveBack: () => slab.classList.remove('is-in') });
    });

    /* ---------- 5. velocity skew on the manifesto heading ---------- */
    if (lenis) lenis.on('scroll', ({ velocity }) => {
      const v = Math.max(-1.4, Math.min(1.4, (velocity || 0) / 22));
      root.style.setProperty('--scroll-vel', v.toFixed(3));
    });
    function loop () {
      const v = parseFloat(root.style.getPropertyValue('--scroll-vel') || 0);
      // decay velocity toward 0 so the skew settles
      root.style.setProperty('--scroll-vel', (v * 0.9).toFixed(3));
      requestAnimationFrame(loop);
    }
    if (!reduced) requestAnimationFrame(loop);

    /* ---------- 6. specimens — clip-path reveals ---------- */
    gsap.utils.toArray('[data-plate]').forEach(plate => {
      ST.create({ trigger: plate, start: 'top 80%', once: true, onEnter: () => plate.classList.add('is-in') });
    });

    /* ---------- 7. ledger — counters (fire on first pass, never stuck at 0) ---------- */
    gsap.utils.toArray('[data-counter]').forEach(el => {
      const to = parseFloat(el.dataset.to || '0'); const obj = { v: 0 };
      ST.create({ trigger: el, start: 'top bottom', once: true,
        onEnter: () => gsap.to(obj, { v: to, duration: 2.0, ease: 'power3.out', onUpdate: () => { el.textContent = Math.round(obj.v).toLocaleString(); } }) });
    });

    /* ---------- 8. magnetic CTAs ---------- */
    gsap.utils.toArray('[data-magnetic]').forEach(el => {
      let mxL = 0, myL = 0, txL = 0, tyL = 0; const r = 70;
      el.addEventListener('mousemove', (e) => { const b = el.getBoundingClientRect(); mxL = Math.max(-r, Math.min(r, e.clientX - (b.left + b.width / 2))) * 0.22; myL = Math.max(-r, Math.min(r, e.clientY - (b.top + b.height / 2))) * 0.22; });
      el.addEventListener('mouseleave', () => { mxL = 0; myL = 0; });
      gsap.ticker.add(() => { txL += (mxL - txL) * 0.16; tyL += (myL - tyL) * 0.16; el.style.transform = 'translate3d(' + txL.toFixed(2) + 'px,' + tyL.toFixed(2) + 'px,0)'; });
    });

    /* ---------- 9. masthead fades over the hero ---------- */
    const mast = document.querySelector('[data-mast]');
    if (mast && stage) {
      ST.create({ trigger: stage, start: 'top top', end: 'bottom bottom',
        onUpdate: self => { mast.style.opacity = (1 - Math.min(1, self.progress * 1.5)).toFixed(2); },
        onLeave: () => mast.style.opacity = '1', onLeaveBack: () => mast.style.opacity = '1' });
    }

    /* ---------- 10. masthead gains a translucent bar once past the hero ---------- */
    if (mast) {
      const onScroll = () => { mast.classList.toggle('is-stuck', window.scrollY > window.innerHeight * 0.62); };
      window.addEventListener('scroll', onScroll, { passive: true });
      if (lenis) lenis.on('scroll', onScroll);
      onScroll();
    }

    ST.refresh();
    window.addEventListener('load', () => ST.refresh());
  }
})();
