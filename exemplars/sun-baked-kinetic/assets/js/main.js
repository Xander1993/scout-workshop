/* Meridiana - Sundial Wordmark kit
   Techniques: parallax-diorama hero, scroll-bound sun-angle,
   sticky-stack chapters, clip-path reveals, SplitType, counters,
   magnetic affordance + custom cursor.
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

  // ---------- HOUR readout ticker ----------
  (function(){
    var el = document.querySelector('[data-hour]');
    if (!el) return;
    function tick(){
      var d = new Date();
      var hh = String(d.getHours()).padStart(2,'0');
      var mm = String(d.getMinutes()).padStart(2,'0');
      el.textContent = hh + ':' + mm;
    }
    tick(); setInterval(tick, 30000);
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

  // ---------- SPLIT TYPE ----------
  function applySplits(){
    document.querySelectorAll('[data-split]').forEach(function(el){
      var type = el.getAttribute('data-split') === 'lines' ? 'lines,words' : 'words';
      var split;
      if (hasSplit){
        try { split = new window.SplitType(el, { types: type, tagName: 'span' }); }
        catch(e){ split = null; }
      }
      // The CSS hides BOTH .line and .word (opacity:0 + translateY). A parent at
      // opacity:0 makes its children invisible regardless of their own opacity, so
      // the .line must be the VISIBLE clip-window (opacity:1, no shift) and the
      // .word is what slides up inside it. Animating only one left the text hidden.
      var lineEls = el.querySelectorAll('.line');
      if (lineEls.length) gsap.set(lineEls, { yPercent: 0, opacity: 1 });   // guard: empty NodeList warns in GSAP
      var nodes = el.querySelectorAll('.word');
      if (!nodes.length) nodes = el.querySelectorAll('.line');
      if (!nodes.length) return;
      gsap.set(nodes, { yPercent: 110, opacity: 0 });
      ScrollTrigger.create({
        trigger: el,
        start: 'top 82%',
        once: true,
        onEnter: function(){
          gsap.to(nodes, {
            yPercent: 0, opacity: 1,
            duration: 1.05, ease: 'power3.out',
            stagger: 0.045
          });
        }
      });
    });
  }

  // ---------- HERO : SUN-ANGLE SCROLL + PARALLAX ----------
  function heroSundial(){
    var hero = document.getElementById('hero');
    if (!hero) return;
    var pin = hero.querySelector('.stage__pin');
    var layers = hero.querySelectorAll('[data-parallax]');
    var root = document.documentElement;

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

    // Mouse-tilt (camera) - lerped
    var mx = 0, my = 0, tx = 0, ty = 0;
    var tiltable = hero.querySelectorAll('[data-depth]');
    pin.addEventListener('mousemove', function(e){
      var r = pin.getBoundingClientRect();
      mx = (e.clientX - r.left) / r.width - 0.5;
      my = (e.clientY - r.top) / r.height - 0.5;
    });
    function tickTilt(){
      tx += (mx - tx) * 0.08;
      ty += (my - ty) * 0.08;
      tiltable.forEach(function(el){
        var d = parseFloat(el.getAttribute('data-depth')) || 10;
        var x = -tx * d;
        var y = -ty * d * 0.6;
        // preserve translateX(-50%) on layers whose base centres them
        var base = el.classList.contains('wordmark') ? 'translate(-50%, -50%)' :
                   (el.classList.contains('diorama__horizon') || el.classList.contains('diorama__dune') || el.classList.contains('diorama__grit')) ? 'translateX(-50%)' : '';
        el.style.translate = x.toFixed(2) + 'px ' + y.toFixed(2) + 'px';
      });
      requestAnimationFrame(tickTilt);
    }
    tickTilt();
  }

  // ---------- STICKY-STACK CHAPTERS ----------
  function chaptersStack(){
    var chapters = document.querySelectorAll('.chapter');
    chapters.forEach(function(ch, i){
      // scale + fade the leaving chapter as the next rises over it
      if (i < chapters.length - 1){
        gsap.to(ch, {
          scale: 0.92,
          opacity: 0.45,
          ease: 'none',
          scrollTrigger: {
            trigger: chapters[i+1],
            start: 'top bottom',
            end: 'top top',
            scrub: true
          }
        });
      }
      // image reveal inside each chapter
      var rev = ch.querySelector('.reveal');
      var img = ch.querySelector('.reveal img');
      if (rev && img){
        ScrollTrigger.create({
          trigger: ch,
          start: 'top 78%',
          once: true,
          onEnter: function(){
            gsap.to(rev, { clipPath: 'inset(0 0 0% 0)', duration: 1.2, ease: 'power3.out' });
            gsap.to(img, { scale: 1.0, duration: 1.6, ease: 'power2.out' });
          }
        });
      }
    });
  }

  // ---------- CLIP-PATH REVEALS (work grid + bleed horizon) ----------
  function genericReveals(){
    document.querySelectorAll('.figure .reveal').forEach(function(rev){
      var img = rev.querySelector('img');
      ScrollTrigger.create({
        trigger: rev,
        start: 'top 88%',
        once: true,
        onEnter: function(){
          gsap.to(rev, { clipPath: 'inset(0 0 0% 0)', duration: 1.05, ease: 'power3.out' });
          if (img) gsap.to(img, { scale: 1.0, duration: 1.4, ease: 'power2.out' });
        }
      });
    });
    var horizon = document.querySelector('.bleed__horizon');
    if (horizon){
      ScrollTrigger.create({
        trigger: horizon, start: 'top 80%', once: true,
        onEnter: function(){ horizon.classList.add('is-in'); }
      });
    }
  }

  // ---------- COUNTERS ----------
  function counters(){
    document.querySelectorAll('[data-count]').forEach(function(el){
      var target = parseInt(el.getAttribute('data-count'), 10);
      var suffix = el.getAttribute('data-suffix') || '';
      var proxy = { v: 0 };
      ScrollTrigger.create({
        trigger: el,
        start: 'top 85%',
        once: true,
        onEnter: function(){
          gsap.to(proxy, {
            v: target,
            duration: 2.2,
            ease: 'power2.out',
            onUpdate: function(){ el.textContent = Math.round(proxy.v) + suffix; }
          });
        }
      });
    });
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
    counters();
    magnetic();
    ScrollTrigger.refresh();
    playIntro();
  }

  if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(init, 60);
  } else {
    window.addEventListener('DOMContentLoaded', init);
  }
})();
