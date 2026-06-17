/* ============================================================
   VESPRA - sun-baked single-product
   Pinned product canvas + four sun-arc washes.
   Degrades gracefully: with no GSAP/Lenis the page still reads
   as a stack of static plates; with no JS at all the inline
   chapter headings show and the pin unsticks.
   ============================================================ */

(function () {
  'use strict';

  var root = document.documentElement;
  root.classList.add('has-js');
  document.body.classList.remove('no-js');
  document.body.classList.add('js');

  var reduced = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* wait for BOTH gsap and ScrollTrigger - they load async and in any order, so
     gating on gsap alone could start init before ScrollTrigger arrives and silently
     skip the entire pin/parallax/sun-arc setup (dead motion). */
  function whenReady(cb) {
    var tries = 0;
    (function tick() {
      tries++;
      if ((window.gsap && window.ScrollTrigger) || tries > 80) return cb();
      setTimeout(tick, 50);
    })();
  }

  function splitChars(el) {
    if (!el) return [];
    var text = el.textContent || '';
    el.textContent = '';
    var spans = [];
    for (var i = 0; i < text.length; i++) {
      var c = text.charAt(i);
      if (c === ' ') { el.appendChild(document.createTextNode(' ')); continue; }
      var s = document.createElement('span');
      s.className = 'char';
      s.textContent = c;
      el.appendChild(s);
      spans.push(s);
    }
    return spans;
  }

  function wrapChapterTitle() {
    var line = document.querySelector('.canvas__title [data-line]');
    if (!line) return;
    var t = line.textContent;
    line.innerHTML = '<span>' + t + '</span>';
  }

  var WASHES = [
    { key: 'dawn',  label: 'Dawn',  title: 'Pressed at first light.',  body: 'Agave hearts hauled in before the sun cracks the ridge. Stone-pressed slow, the way the highlands have asked since the road in was a footpath.' },
    { key: 'noon',  label: 'Noon',  title: 'Bottled at noon.',         body: 'The light flattens and shadows pull in tight. One bottle, filled by hand, sealed with wax the colour of the wall it leans against.' },
    { key: 'dusk',  label: 'Dusk',  title: 'Rested through dusk.',      body: 'Held in clay while the wall outside cools from sienna into rust. The spirit reads the day back to itself, listens to the room, and slows.' },
    { key: 'night', label: 'Night', title: 'Poured after dark.',        body: 'A short glass, no ice. The bottle goes back on its shelf and the wall keeps the last of the heat. This is the hour it was built for.' }
  ];

  var washApplied = false;

  function applyWash(idx) {
    var w = WASHES[Math.max(0, Math.min(WASHES.length - 1, idx))];
    if (!w) return;
    if (washApplied && document.body.getAttribute('data-wash') === w.key) return;
    document.body.setAttribute('data-wash', w.key);

    var titleEl = document.querySelector('.canvas__title');
    var titleSpan = document.querySelector('.canvas__title [data-line] > span');
    var bodyEl = document.querySelector('[data-chapter-body]');

    if (titleEl && titleSpan) {
      titleSpan.textContent = w.title;
      if (washApplied) {
        titleEl.classList.remove('is-in');
        void titleSpan.offsetWidth;
        titleEl.classList.add('is-in');
      } else {
        /* first paint: show instantly (no fade) so the headline is never caught mid-reveal */
        titleSpan.style.transition = 'none';
        titleEl.classList.add('is-in');
        void titleSpan.offsetWidth;
        titleSpan.style.transition = '';
      }
    }
    if (bodyEl) {
      bodyEl.textContent = w.body;
      if (washApplied) {
        bodyEl.style.opacity = '0';
        void bodyEl.offsetWidth;
      }
      bodyEl.style.opacity = '0.88';
    }
    washApplied = true;
  }

  function init() {
    var hasGsap = !!window.gsap;
    var hasST = !!(window.gsap && window.ScrollTrigger);
    if (hasST) window.gsap.registerPlugin(window.ScrollTrigger);

    /* hero wordmark reveal */
    var h1 = document.querySelector('[data-split]');
    var chars = splitChars(h1);
    if (chars.length && hasGsap && !reduced) {
      window.gsap.to(chars, { y: 0, opacity: 1, duration: 1.1, ease: 'expo.out', stagger: 0.045, delay: 0.12 });
    } else if (chars.length) {
      for (var i = 0; i < chars.length; i++) { chars[i].style.transform = 'translateY(0)'; chars[i].style.opacity = '1'; }
    }

    wrapChapterTitle();
    setTimeout(function () { applyWash(0); }, 60);

    var canvas = document.querySelector('.canvas');
    var pin = document.querySelector('.canvas__pin');
    var chapters = document.querySelectorAll('.chapter');

    if (hasST && canvas && pin && chapters.length && !reduced) {
      window.ScrollTrigger.create({
        trigger: canvas, start: 'top top', end: 'bottom bottom',
        pin: pin, pinSpacing: false, anticipatePin: 1
      });

      var wall = document.querySelector('.canvas__wall');
      if (wall) {
        window.gsap.to(wall, {
          yPercent: -7, ease: 'none',
          scrollTrigger: { trigger: canvas, start: 'top top', end: 'bottom bottom', scrub: true }
        });
      }
      var bottle = document.querySelector('.canvas__bottle');
      if (bottle) {
        window.gsap.fromTo(bottle, { yPercent: 3 }, {
          yPercent: -3, ease: 'none',
          scrollTrigger: { trigger: canvas, start: 'top top', end: 'bottom bottom', scrub: true }
        });
      }

      /* the sun itself: glow scrubs across the wall on an arc - low at dawn, high at noon, low at night */
      var wash = document.querySelector('.canvas__wash');
      var canvasCopy = document.querySelector('.canvas__copy');
      if (wash) {
        window.ScrollTrigger.create({
          trigger: canvas, start: 'top top', end: 'bottom bottom', scrub: 0.6,
          onUpdate: function (self) {
            var p = self.progress;
            var x = 14 + p * 72;
            var y = 72 - Math.sin(p * Math.PI) * 44;
            wash.style.setProperty('--sun-x', x.toFixed(1) + '%');
            wash.style.setProperty('--sun-y', y.toFixed(1) + '%');
            /* The bottle cutout reads on every wash (dawn -> near-black night) so the
               canvas never sits on an empty wall. Only in the final stretch (p>0.93)
               do bottle + copy ease out, so the pin releases onto a clean wall instead
               of shearing the night bottle across the beige spec section below. */
            var fade = p > 0.93 ? (1 - (p - 0.93) / 0.07) : 1;
            fade = Math.max(0, Math.min(1, fade));
            if (bottle) bottle.style.opacity = fade.toFixed(3);
            if (canvasCopy) canvasCopy.style.opacity = fade.toFixed(3);
          }
        });
      }

      for (var c = 0; c < chapters.length; c++) {
        (function (idx, el) {
          window.ScrollTrigger.create({
            trigger: el, start: 'top center+=10%', end: 'bottom center',
            onEnter: function () { applyWash(idx); },
            onEnterBack: function () { applyWash(idx); }
          });
        })(c, chapters[c]);
      }
    } else if (chapters.length && 'IntersectionObserver' in window) {
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) {
          if (e.isIntersecting) applyWash(+e.target.getAttribute('data-idx'));
        });
      }, { threshold: 0.5 });
      for (var k = 0; k < chapters.length; k++) { chapters[k].setAttribute('data-idx', k); io.observe(chapters[k]); }
    }

    /* Lenis smooth scroll */
    if (window.Lenis && hasGsap && !reduced) {
      try {
        var lenis = new window.Lenis({
          duration: 1.15,
          easing: function (t) { return Math.min(1, 1.001 - Math.pow(2, -10 * t)); },
          smoothWheel: true, smoothTouch: false
        });
        function raf(time) { lenis.raf(time); if (window.ScrollTrigger) window.ScrollTrigger.update(); requestAnimationFrame(raf); }
        requestAnimationFrame(raf);
        document.querySelectorAll('a[href^="#"]').forEach(function (a) {
          a.addEventListener('click', function (ev) {
            var id = a.getAttribute('href');
            if (id.length > 1) { var t = document.querySelector(id); if (t) { ev.preventDefault(); lenis.scrollTo(t, { offset: 0 }); } }
          });
        });
      } catch (e) { /* fail quietly */ }
    }

    /* nav: protected scrim once past the hero + retract on scroll-down so the
       fixed bar never reads as colliding with live content. */
    var nav = document.querySelector('.nav');
    if (nav) {
      var lastY = window.pageYOffset || 0;
      var ticking = false;
      var onScroll = function () {
        var y = window.pageYOffset || 0;
        var threshold = Math.max(120, window.innerHeight * 0.7);
        if (y > threshold) nav.classList.add('nav--scrolled');
        else nav.classList.remove('nav--scrolled');
        if (y > lastY && y > threshold + 60) nav.classList.add('nav--hidden');
        else nav.classList.remove('nav--hidden');
        lastY = y;
        ticking = false;
      };
      window.addEventListener('scroll', function () {
        if (!ticking) { window.requestAnimationFrame(onScroll); ticking = true; }
      }, { passive: true });
      onScroll();
    }

    /* magnetic CTA */
    var mag = document.querySelector('[data-magnetic]');
    if (mag && !reduced) {
      var RADIUS = 120, STRENGTH = 0.3;
      mag.addEventListener('mousemove', function (e) {
        var r = mag.getBoundingClientRect();
        var dx = e.clientX - (r.left + r.width / 2);
        var dy = e.clientY - (r.top + r.height / 2);
        if (Math.sqrt(dx * dx + dy * dy) < RADIUS) mag.style.transform = 'translate(' + (dx * STRENGTH) + 'px,' + (dy * STRENGTH) + 'px)';
      });
      mag.addEventListener('mouseleave', function () {
        mag.style.transition = 'transform 600ms cubic-bezier(.22,.61,.36,1)';
        mag.style.transform = 'translate(0,0)';
        setTimeout(function () { mag.style.transition = ''; }, 620);
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { whenReady(init); });
  } else { whenReady(init); }
})();
