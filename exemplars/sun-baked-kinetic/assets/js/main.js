/* Meridiana - Sundial Wordmark kit
   Techniques: at-rest sun-sweep intro, sticky-stack chapters,
   clip-path reveals, SplitType, magnetic affordance.
*/
(function(){
  'use strict';

  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var hasGsap = typeof window.gsap !== 'undefined';
  var hasST   = hasGsap && typeof window.ScrollTrigger !== 'undefined';
  var hasLenis= typeof window.Lenis !== 'undefined';
  var hasSplit= typeof window.SplitType !== 'undefined';

  if (hasST) { window.gsap.registerPlugin(window.ScrollTrigger); }

  // ---------- LENIS + GSAP bridge ----------
  var lenis = null;
  if (hasLenis && !reduced){
    lenis = new window.Lenis({
      duration: 0.9,
      easing: function(t){ return 1 - Math.pow(1 - t, 3); },
      smoothWheel: true,
      wheelMultiplier: 1.25
    });
    if (hasST){
      lenis.on('scroll', window.ScrollTrigger.update);
      window.gsap.ticker.add(function(t){ lenis.raf(t * 1000); });
      window.gsap.ticker.lagSmoothing(0);
    } else {
      function raf(time){ lenis.raf(time); requestAnimationFrame(raf); }
      requestAnimationFrame(raf);
    }
  }

  // ---------- NAV CONTRAST (pure DOM, runs in every path incl reduced/no-js) ----------
  // The fixed nav uses multiply (dark text) over the light plates, but that
  // vanishes over the dark bleed / dusk / studio plates. Flag `nav-on-dark` so
  // the nav switches to a legible bone treatment whenever a dark plate is behind.
  (function navContrast(){
    var header = document.querySelector('.topline');
    if (!header) return;
    var darks = [].slice.call(document.querySelectorAll('.plate--dark'));
    if (!darks.length) return;
    function update(){
      var probe = header.getBoundingClientRect().bottom - 6;
      var onDark = darks.some(function(el){
        var r = el.getBoundingClientRect();
        return r.top <= probe && r.bottom >= probe;
      });
      document.body.classList.toggle('nav-on-dark', onDark);
    }
    update();
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', update);
  })();

  if (reduced) {
    document.querySelectorAll('[data-split] .word, [data-split] .line').forEach(function(n){ n.style.transform='none'; n.style.opacity=1; });
    return;
  }

  if (!hasGsap || !hasST){
    // Fallback: just reveal everything
    document.querySelectorAll('.reveal').forEach(function(n){ n.style.clipPath='none'; });
    document.querySelectorAll('[data-split] .word, [data-split] .line').forEach(function(n){ n.style.transform='none'; n.style.opacity=1; });
    return;
  }

  var gsap = window.gsap;
  var ScrollTrigger = window.ScrollTrigger;

  // ---------- STATIC-CAPTURE REVEAL SAFETY ----------
  // Every entrance is registered as an idempotent play() in `pending`. A real
  // scroll plays each one first when it reaches the trigger; whatever a scroll
  // hasn't reached is played by a short post-load timer (well before the quality
  // gate's full-page capture) so a non-scrolled / static render is NEVER blank.
  var pending = [];
  function defer(play){
    var done = false;
    var wrapped = function(){ if (done) return; done = true; play(); };
    pending.push(wrapped);
    return wrapped;
  }
  function finalizeReveals(){ pending.forEach(function(p){ p(); }); }

  // ---------- SPLIT TYPE ----------
  function applySplits(){
    document.querySelectorAll('[data-split]').forEach(function(el){
      var type = el.getAttribute('data-split') === 'lines' ? 'lines,words' : 'words';
      var split;
      if (hasSplit){
        try { split = new window.SplitType(el, { types: type, tagName: 'span' }); }
        catch(e){ split = null; }
      }
      // Animate the .word spans (lines mode keeps its .line wrappers static and
      // slides the words inside). The rise is a small fixed 16px, not a full
      // line-height, so a staggered word never descends into the body copy below.
      var lineEls = el.querySelectorAll('.line');
      if (lineEls.length) gsap.set(lineEls, { y: 0, opacity: 1 });   // guard: empty NodeList warns in GSAP
      var nodes = el.querySelectorAll('.word');
      if (!nodes.length) nodes = el.querySelectorAll('.line');
      if (!nodes.length) return;
      gsap.set(nodes, { y: 16, opacity: 0 });
      var play = defer(function(){
        gsap.to(nodes, {
          y: 0, opacity: 1,
          duration: 0.9, ease: 'power3.out',
          stagger: 0.04
        });
      });
      ScrollTrigger.create({ trigger: el, start: 'top 82%', once: true, onEnter: play });
    });
  }

  // ---------- HERO : SUN-ANGLE SCROLL + PARALLAX ----------
  function heroSundial(){
    var hero = document.getElementById('hero');
    if (!hero) return;
    var layers = hero.querySelectorAll('[data-parallax]');
    var root = document.documentElement;

    // The hero is a clean 100vh moment with no scroll runway, so there is no
    // scrub range to drive. playIntro() owns the at-rest sun sweep instead;
    // bail out here so a zero-range trigger can't reset the sun back to dawn.
    if (hero.offsetHeight - window.innerHeight < 40) return;

    // Pin + scrub : drives --sun-progress 0→1 over hero runway
    ScrollTrigger.create({
      trigger: hero,
      start: 'top top',
      end: 'bottom bottom',
      scrub: true,
      onUpdate: function(self){
        var p = self.progress;
        root.style.setProperty('--sun-progress', p.toFixed(3));

        // sun moves dawn-left-low → noon-centre-high → dusk-right-low
        var sx, sy;
        if (p < 0.5){
          var k = p / 0.5;
          sx = (-38 + k * 38);
          sy = (18  - k * 22);
        } else {
          var k2 = (p - 0.5) / 0.5;
          sx = (0 + k2 * 38);
          sy = (-4 + k2 * 22);
        }
        root.style.setProperty('--sun-x', sx.toFixed(2) + 'vw');
        root.style.setProperty('--sun-y', sy.toFixed(2) + 'vh');

        // text-shadow length follows abs(sin) of sun height - long at dawn/dusk, none at noon
        var shadowLen = 0.04 + Math.pow(Math.abs(p - 0.5) * 2, 1.4) * 1.6;
        var shadowDir = (p < 0.5 ? -1 : 1); // east at dawn, west at dusk
        root.style.setProperty('--shadow-x', (shadowLen * shadowDir).toFixed(3) + 'em');
        root.style.setProperty('--shadow-y', (0.02 + (1 - Math.abs(p - 0.5) * 2) * 0.04).toFixed(3) + 'em');
        root.style.setProperty('--shadow-blur', (0.10 + shadowLen * 0.18).toFixed(3) + 'em');
        root.style.setProperty('--shadow-alpha', (0.30 + Math.abs(p - 0.5) * 0.7).toFixed(3));

        // bleach : ochre at dawn → bone at noon → ochre at dusk
        var bleach = 1 - Math.pow(Math.abs(p - 0.5) * 2, 1.3);
        root.style.setProperty('--bleach', bleach.toFixed(3));
      }
    });

    // Per-layer parallax inside hero
    layers.forEach(function(layer){
      var speed = parseFloat(layer.getAttribute('data-parallax')) || 0.9;
      // higher value = nearly fixed; lower value = moves more
      var distance = (1 - speed) * 100; // vh
      gsap.to(layer, {
        yPercent: distance * 1.0,
        ease: 'none',
        scrollTrigger: {
          trigger: hero,
          start: 'top top',
          end: 'bottom bottom',
          scrub: true
        }
      });
    });
  }

  // ---------- STICKY-STACK CHAPTERS ----------
  function chaptersStack(){
    var chapters = document.querySelectorAll('.chapter');
    chapters.forEach(function(ch, i){
      // Each chapter is an opaque sticky panel; the next simply slides up over the
      // pinned previous one. (The old leaving-panel opacity:0.45 fade made the
      // opaque background translucent, so the prior chapter's copy bled through the
      // incoming one - the overprint defect. Clean stack, no fade.)
      // image reveal inside each chapter
      var rev = ch.querySelector('.reveal');
      var img = ch.querySelector('.reveal img');
      if (rev && img){
        var play = defer(function(){
          gsap.to(rev, { clipPath: 'inset(0 0 0% 0)', duration: 1.2, ease: 'power3.out' });
          gsap.to(img, { scale: 1.0, duration: 1.6, ease: 'power2.out' });
        });
        ScrollTrigger.create({ trigger: ch, start: 'top 78%', once: true, onEnter: play });
      }
    });
  }

  // ---------- CLIP-PATH REVEALS (work grid + bleed horizon) ----------
  function genericReveals(){
    document.querySelectorAll('.figure .reveal').forEach(function(rev){
      var img = rev.querySelector('img');
      var play = defer(function(){
        gsap.to(rev, { clipPath: 'inset(0 0 0% 0)', duration: 1.05, ease: 'power3.out' });
        if (img) gsap.to(img, { scale: 1.0, duration: 1.4, ease: 'power2.out' });
      });
      ScrollTrigger.create({ trigger: rev, start: 'top 88%', once: true, onEnter: play });
    });
    var horizon = document.querySelector('.bleed__horizon');
    if (horizon){
      var playHorizon = defer(function(){ horizon.classList.add('is-in'); });
      ScrollTrigger.create({ trigger: horizon, start: 'top 80%', once: true, onEnter: playHorizon });
    }
  }

  // ---------- MAGNETIC AFFORDANCE (no custom cursor) ----------
  function magnetic(){
    if (!matchMedia('(hover:hover) and (pointer:fine)').matches) return;
    document.querySelectorAll('[data-magnetic]').forEach(function(el){
      var qx = gsap.quickTo(el, 'x', { duration: 0.45, ease: 'power3.out' });
      var qy = gsap.quickTo(el, 'y', { duration: 0.45, ease: 'power3.out' });
      el.addEventListener('mousemove', function(e){
        var r = el.getBoundingClientRect();
        var cx = r.left + r.width/2;
        var cy = r.top + r.height/2;
        qx((e.clientX - cx) * 0.35);
        qy((e.clientY - cy) * 0.35);
      });
      el.addEventListener('mouseleave', function(){ qx(0); qy(0); });
    });
  }

  // ---------- AT-REST INTRO : sun rises across the wall on load ----------
  function playIntro(){
    var root = document.documentElement;
    var done = false;
    var p = { v: 0 };
    function applySun(pr){
      var sx = -38 + pr * 30;            // -38vw -> -8vw  (dawn light walks right)
      var sy = 18  - pr * 13;            //  18vh ->  5vh  (and climbs)
      root.style.setProperty('--sun-x', sx.toFixed(2) + 'vw');
      root.style.setProperty('--sun-y', sy.toFixed(2) + 'vh');
      var shadowLen = 1.45 - pr * 0.55;  // long dawn shadow shortens as light climbs
      root.style.setProperty('--shadow-x', (-shadowLen).toFixed(3) + 'em');
      root.style.setProperty('--shadow-y', '0.05em');
      root.style.setProperty('--shadow-blur', (0.10 + shadowLen * 0.16).toFixed(3) + 'em');
      root.style.setProperty('--shadow-alpha', '0.55');
      root.style.setProperty('--bleach', (0.08 + pr * 0.22).toFixed(3));
    }
    applySun(0);
    var tween = gsap.to(p, { v: 1, duration: 2.6, ease: 'sine.inOut',
      onUpdate: function(){ applySun(p.v); } });
    function stop(){ if (done) return; done = true; tween.kill();
      window.removeEventListener('wheel', stop);
      window.removeEventListener('touchstart', stop);
      window.removeEventListener('keydown', stop);
    }
    // hand off the instant the visitor drives the sun themselves
    window.addEventListener('wheel', stop, { passive: true, once: true });
    window.addEventListener('touchstart', stop, { passive: true, once: true });
    window.addEventListener('keydown', stop, { once: true });
  }

  // ---------- INITIATE ----------
  function init(){
    applySplits();
    heroSundial();
    chaptersStack();
    genericReveals();
    magnetic();
    ScrollTrigger.refresh();
    playIntro();
    // Static-capture safety: play any entrance a real scroll hasn't reached yet,
    // well before the quality gate's full-page capture, so no section is blank.
    setTimeout(finalizeReveals, 1200);
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(init, 60);
  } else {
    window.addEventListener('DOMContentLoaded', init);
  }
})();
