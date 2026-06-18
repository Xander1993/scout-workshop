/* =============================================================
   Latten -motion
   GSAP + ScrollTrigger + Lenis + SplitType (all CDN, all optional).

   The signature ("Aperture Wordmark"): the solid-brass object is
   masked INSIDE the letterforms. On load the mask sweeps once so
   the hero visibly moves at rest; on scroll the same background
   position is handed to ScrollTrigger, so the object rises through
   the counters letter-by-letter as the pinned scene travels.

   Fail-safe: if any library is missing or anything throws, every
   section is shown fully legible and static. The masked words paint
   from CSS (--mask) regardless, so nothing depends on JS to read.
   ============================================================= */

(function () {
  'use strict';

  const root = document.documentElement;
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- keep each masked word in sync with its real plate img ---------- */
  function syncMasks () {
    document.querySelectorAll('[data-scene]').forEach(scene => {
      const img = scene.querySelector('.plate__src');
      const word = scene.querySelector('.maskword');
      if (!img || !word) return;
      const apply = () => {
        const src = img.currentSrc || img.getAttribute('src');
        if (src) word.style.setProperty('--mask', "url('" + src + "')");
      };
      if (img.complete) apply();
      img.addEventListener('load', apply, { once: false });
    });
  }
  syncMasks();

  /* ---------- 0. settle: reveal everything (the static, legible state) ---------- */
  const settle = () => {
    document.querySelectorAll('[data-rise]').forEach(el => el.classList.add('is-in'));
    document.querySelectorAll('[data-plate]').forEach(el => el.classList.add('is-in'));
    document.querySelectorAll('.statement__line').forEach(el => el.classList.add('is-in'));
  };

  /* Fast finalize so a non-scrolled static capture never strands a reveal at
     opacity:0. We DO NOT clear this -even when motion boots, any reveal the
     scroll never reached is played in by ~1100ms. ScrollTrigger's own onEnter
     simply wins first for elements the user actually scrolls past. */
  setTimeout(settle, 1100);

  /* ---------- 1. wait briefly for libs, then boot or settle ---------- */
  const ready = (tries) => {
    tries = tries || 0;
    if (window.gsap && window.ScrollTrigger) {
      try { boot(); } catch (e) { console.error('[latten]', e); settle(); }
      return;
    }
    if (tries > 28) { settle(); return; }   // ~1.7s of 60ms polls, then give up gracefully
    setTimeout(() => ready(tries + 1), 60);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => ready(0));
  else ready(0);

  function boot () {
    const { gsap } = window;
    gsap.registerPlugin(window.ScrollTrigger);
    const ST = window.ScrollTrigger;

    /* reduced motion: reveal, paint masks at a settled position, stop */
    if (reduced) { settle(); return; }

    /* ---------- Lenis <-> ScrollTrigger bridge ---------- */
    if (window.Lenis) {
      const lenis = new window.Lenis({
        duration: 1.05,
        easing: t => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
        wheelMultiplier: 1.05, smoothWheel: true
      });
      lenis.on('scroll', ST.update);
      gsap.ticker.add(t => lenis.raf(t * 1000));
      gsap.ticker.lagSmoothing(0);
    }

    /* ---------- 2. THE SIGNATURE -masked aperture reveal ----------
       Each pinned scene is a 200vh spacer with a sticky 100vh stick.
       As the scene travels, background-position-y slides 78% -> 14%,
       so the object rises through the letters; the plate drifts the
       opposite way for parallax depth. */
    gsap.utils.toArray('[data-scene]').forEach(scene => {
      const word  = scene.querySelector('.maskword');
      const plate = scene.querySelector('.plate__src');
      if (!word) return;

      let scrollDriven = false;   // once the user scrolls, the intro sweep yields

      ST.create({
        trigger: scene,
        start: 'top top',
        end: 'bottom bottom',
        scrub: true,
        onUpdate: self => {
          scrollDriven = true;
          const y = 78 - self.progress * 64;            // 78% -> 14%
          word.style.backgroundPosition = 'center ' + y.toFixed(2) + '%';
          if (plate) {
            const drift = -8 + self.progress * 22;       // plate drifts opposite
            plate.style.transform = 'translate3d(0,' + drift.toFixed(2) + '%,0) scale(1.08)';
          }
        }
      });

      /* at-rest intro sweep on the FIRST scene only: the hero visibly moves on
         load, then hands the mask back to scroll the moment the user scrolls. */
      if (scene === document.querySelector('[data-scene]')) {
        const o = { y: 64 };
        gsap.to(o, {
          y: 78, duration: 1.6, ease: 'power2.out', delay: 0.15,
          onUpdate: () => { if (!scrollDriven) word.style.backgroundPosition = 'center ' + o.y.toFixed(2) + '%'; }
        });
      }
    });

    /* ---------- 3. standalone parallax plates (non-pinned bg images) ---------- */
    gsap.utils.toArray('[data-plate]').forEach(layer => {
      const img = layer.querySelector('img');
      if (!img) { layer.classList.add('is-in'); return; }
      ST.create({
        trigger: layer, start: 'top bottom', end: 'bottom top', scrub: true,
        onUpdate: self => { img.style.transform = 'translate3d(0,' + (-6 + self.progress * 12).toFixed(2) + '%,0) scale(1.12)'; }
      });
      ST.create({ trigger: layer, start: 'top 88%', once: true, onEnter: () => layer.classList.add('is-in') });
    });

    /* ---------- 4. line-stack reveals (statement) ---------- */
    gsap.utils.toArray('.statement__line').forEach(line => {
      ST.create({ trigger: line, start: 'top 86%', once: true, onEnter: () => line.classList.add('is-in') });
    });

    /* ---------- 5. hierarchical fade-up (rows, channels, captions) ---------- */
    gsap.utils.toArray('[data-rise]').forEach((el, i) => {
      ST.create({
        trigger: el, start: 'top 90%', once: true,
        onEnter: () => gsap.delayedCall((i % 5) * 0.04, () => el.classList.add('is-in'))
      });
    });

    /* ---------- 6. masthead contrast -ink text over light plates ----------
       Probe the element sitting under the nav band; if it resolves to a light
       background, switch the masthead to ink text (no dark scrim). */
    const mast = document.querySelector('[data-mast]');
    if (mast) {
      const lightSelector = '.manifesto,.band,.spec,.work,.channels,.foot';
      const lights = Array.from(document.querySelectorAll(lightSelector))
        .filter(el => !el.classList.contains('foot'));  // foot is dark
      const probeY = 30;
      const navContrast = () => {
        let overLight = false;
        for (const el of lights) {
          const r = el.getBoundingClientRect();
          if (r.top <= probeY && r.bottom >= probeY) { overLight = true; break; }
        }
        mast.classList.toggle('mast--light', overLight);
      };
      navContrast();
      ST.create({ trigger: 'body', start: 'top top', end: 'bottom bottom', onUpdate: navContrast });
      window.addEventListener('resize', navContrast);
    }

    /* ---------- 7. magnetic single primary CTA ---------- */
    gsap.utils.toArray('[data-magnetic]').forEach(el => {
      let mx = 0, my = 0, tx = 0, ty = 0; const r = 70;
      el.addEventListener('mousemove', e => {
        const b = el.getBoundingClientRect();
        mx = Math.max(-r, Math.min(r, e.clientX - (b.left + b.width / 2))) * 0.26;
        my = Math.max(-r, Math.min(r, e.clientY - (b.top + b.height / 2))) * 0.26;
      });
      el.addEventListener('mouseleave', () => { mx = 0; my = 0; });
      gsap.ticker.add(() => {
        tx += (mx - tx) * 0.16; ty += (my - ty) * 0.16;
        el.style.transform = 'translate3d(' + tx.toFixed(2) + 'px,' + ty.toFixed(2) + 'px,0)';
      });
    });

    /* keep masks in sync after late image loads, then settle layout */
    syncMasks();
    ST.refresh();
    window.addEventListener('load', () => { syncMasks(); ST.refresh(); });
  }
})();
