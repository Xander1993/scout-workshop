/* SOLANO. Motion only enhances; it never hides.
   Drives a single CSS custom property (--hero-zoom) from the hero's scroll
   progress for a slow parallax on the full-bleed photograph. SplitType
   settles the wordmark and manifesto on entry. All content is visible at
   rest, so the static render and no-JS fallback are complete.
*/

(function(){
  'use strict';

  // ---- helpers ------------------------------------------------------------
  const ready = (fn) => {
    if (document.readyState !== 'loading') fn();
    else document.addEventListener('DOMContentLoaded', fn);
  };
  const waitFor = (cond, timeout = 4000) => new Promise((resolve) => {
    const t0 = Date.now();
    (function tick(){
      if (cond()) return resolve(true);
      if (Date.now() - t0 > timeout) return resolve(false);
      requestAnimationFrame(tick);
    })();
  });
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ---- main ---------------------------------------------------------------
  ready(async function init(){

    // SplitType wordmark + manifesto (chars/words). Manual fallback if lib missing.
    const wordmark = document.querySelector('[data-split-chars]');
    const manifestoLine = document.querySelector('[data-split-words]');

    const hasSplit = await waitFor(() => typeof window.SplitType !== 'undefined', 3000);
    if (hasSplit){
      try {
        if (wordmark)      new window.SplitType(wordmark, { types:'chars', tagName:'span' });
        if (manifestoLine) new window.SplitType(manifestoLine, { types:'words', tagName:'span' });
      } catch(_){ /* swallow */ }
    } else {
      // tiny manual split so the settle still works
      if (wordmark && !wordmark.dataset.manualSplit){
        const text = wordmark.textContent;
        wordmark.textContent = '';
        [...text].forEach(ch => {
          const s = document.createElement('span');
          s.className = 'char';
          s.textContent = ch === ' ' ? '\u00A0' : ch;
          wordmark.appendChild(s);
        });
        wordmark.dataset.manualSplit = '1';
      }
      if (manifestoLine && !manifestoLine.dataset.manualSplit){
        const words = manifestoLine.textContent.trim().split(/\s+/);
        manifestoLine.textContent = '';
        words.forEach((w,i)=>{
          const s = document.createElement('span');
          s.className = 'word';
          s.textContent = w + (i < words.length-1 ? ' ' : '');
          manifestoLine.appendChild(s);
        });
        manifestoLine.dataset.manualSplit = '1';
      }
    }

    // Lenis smooth scroll (optional, graceful)
    const hasLenis = await waitFor(() => typeof window.Lenis !== 'undefined', 2500);
    let lenis = null;
    if (hasLenis && !prefersReducedMotion){
      try {
        lenis = new window.Lenis({
          duration: 0.85,
          wheelMultiplier: 1.3,
          easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
          smoothWheel: true,
          smoothTouch: false,
        });
        const raf = (time) => { lenis.raf(time); requestAnimationFrame(raf); };
        requestAnimationFrame(raf);
      } catch(_) { lenis = null; }
    }

    // GSAP + ScrollTrigger (graceful: content already visible if absent)
    const hasGsap = await waitFor(() =>
      typeof window.gsap !== 'undefined' && typeof window.ScrollTrigger !== 'undefined', 3500);

    if (!hasGsap || prefersReducedMotion){
      return;
    }

    const gsap = window.gsap;
    const ScrollTrigger = window.ScrollTrigger;
    gsap.registerPlugin(ScrollTrigger);

    // Bridge Lenis <-> ScrollTrigger
    if (lenis){
      lenis.on('scroll', ScrollTrigger.update);
      gsap.ticker.add((time) => lenis.raf(time * 1000));
      gsap.ticker.lagSmoothing(0);
    }

    const root = document.documentElement;
    const hero = document.querySelector('.plate--hero');

    // ---- 1. HERO: slow zoom-out parallax as the hero scrolls away ----
    if (hero){
      ScrollTrigger.create({
        trigger: hero,
        start: 'top top',
        end: 'bottom top',
        scrub: true,
        onUpdate: (self) => {
          root.style.setProperty('--hero-zoom', (1.06 + self.progress * 0.10).toFixed(4));
        }
      });
    }

    // ---- 2. WORDMARK LETTER SETTLE (translate only; letters never hide) ----
    const wmChars = document.querySelectorAll('.wordmark-plate__type .char, .wordmark-plate__type [data-c]');
    if (wmChars.length){
      gsap.from(wmChars, {
        yPercent: 36,
        duration: .8, ease: 'power3.out',
        stagger: 0.04,
        immediateRender: false,
        scrollTrigger: { trigger: '.wordmark-plate', start: 'top 82%', once: true }
      });
    }

    // ---- 3. MANIFESTO WORD SETTLE (translate only) ----
    const manWords = document.querySelectorAll('.display--manifesto .word, .display--manifesto [data-w]');
    if (manWords.length){
      gsap.from(manWords, {
        yPercent: 40,
        duration: .9, ease: 'power3.out',
        stagger: 0.08,
        immediateRender: false,
        scrollTrigger: { trigger: '.manifesto', start: 'top 80%', once: true }
      });
    }

    // ---- 4. SECTION FADES (immediateRender:false keeps content visible at rest) ----
    document.querySelectorAll('.plate--noon, .plate--afternoon, .spec, .floated, .callout')
      .forEach((sec) => {
        const items = sec.querySelectorAll('h2, .editorial, .prose, .spec__row, .plate__media, .floated__line, .callout__line, .callout__action, .chapter-label');
        if (!items.length) return;
        gsap.from(items, {
          y: 24, opacity: 0,
          duration: .9, ease: 'power3.out',
          stagger: 0.07,
          immediateRender: false,
          scrollTrigger: { trigger: sec, start: 'top 80%', once: true }
        });
      });

    // ---- 5. MAGNETIC LINK ----
    document.querySelectorAll('[data-magnetic]').forEach((el) => {
      const strength = 18;
      el.addEventListener('mousemove', (e) => {
        const r = el.getBoundingClientRect();
        const x = e.clientX - r.left - r.width/2;
        const y = e.clientY - r.top - r.height/2;
        gsap.to(el, { x: x/r.width*strength, y: y/r.height*strength, duration: .35, ease:'power3.out' });
      });
      el.addEventListener('mouseleave', () => {
        gsap.to(el, { x:0, y:0, duration: .5, ease:'elastic.out(1,.5)' });
      });
    });

    // ---- 6. refresh once images settle ----
    window.addEventListener('load', () => ScrollTrigger.refresh());
  });
})();
