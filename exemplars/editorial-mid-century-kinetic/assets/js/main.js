/* =========================================================================
   SET TO MEASURE - Stele, architectural lettering atelier
   Defensive motion controller for the justification engine.
   - The hero & chapter measures re-justify live on scroll (the signature).
   - Parallax + mouse-tilt diorama, SplitType line reveals, clip-path
     reveals, animated counters, magnetic CTA, Lenis smooth scroll.
   - Every effect degrades to fully-visible, scrollable content.
   ========================================================================= */
(function () {
  "use strict";

  var doc = document;
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var hasGSAP = typeof window.gsap !== "undefined";
  var hasST = hasGSAP && typeof window.ScrollTrigger !== "undefined";

  function lerp(a, b, t) { return a + (b - a) * t; }
  function clamp(v, lo, hi) { return v < lo ? lo : v > hi ? hi : v; }

  /* ---- fail-safe: restore every hidden carrier to visible ---- */
  function revealAll() {
    var carriers = doc.querySelectorAll("[data-split] .word, [data-split] .char");
    for (var i = 0; i < carriers.length; i++) { carriers[i].style.opacity = "1"; carriers[i].style.transform = "none"; }
    var clips = doc.querySelectorAll(".clip-reveal");
    for (var j = 0; j < clips.length; j++) {
      clips[j].style.clipPath = "none";
      var im = clips[j].querySelector("img"); if (im) im.style.transform = "none";
    }
    doc.body.classList.add("is-settled");
  }

  /* settle safety net - if a trigger never fires, never leave content blank */
  var settleTimer = setTimeout(function () { doc.body.classList.add("is-settled"); }, 2600);

  /* =========================================================================
     PARALLAX + MOUSE-TILT (hero diorama) - runs on its own rAF.
     Scroll translateY lives on the LAYER; mouse tilt on the INNER node,
     so the two transforms never collide.
     ========================================================================= */
  var gridLayer = doc.querySelector(".hero__grid");
  var photoLayer = doc.querySelector(".hero__photo");
  var gridInner = gridLayer ? gridLayer.querySelector("svg") : null;
  var photoInner = photoLayer ? photoLayer.querySelector("figure") : null;
  var heroProgress = 0;
  var tmx = 0, tmy = 0, mx = 0, my = 0;

  if (!reduce) {
    window.addEventListener("mousemove", function (e) {
      tmx = (e.clientX / window.innerWidth) - 0.5;
      tmy = (e.clientY / window.innerHeight) - 0.5;
    }, { passive: true });

    (function tiltLoop(now) {
      var t = (now || 0) / 1000;
      // autonomous diorama breathing - the hero stays alive AT REST, with no
      // pointer or scroll input, so the kinetic page never reads as static.
      var ax = Math.sin(t * 0.34) * 7, ay = Math.cos(t * 0.27) * 5;
      mx += (tmx - mx) * 0.06;
      my += (tmy - my) * 0.06;
      if (gridInner) gridInner.style.transform = "translate3d(" + (mx * 26 + ax * 0.45).toFixed(1) + "px," + (my * 18 + ay * 0.45).toFixed(1) + "px,0)";
      if (photoInner) photoInner.style.transform = "translate3d(" + (mx * -42 + ax).toFixed(1) + "px," + (my * -28 + ay).toFixed(1) + "px,0)";
      requestAnimationFrame(tiltLoop);
    })(0);
  }

  function applyHeroScroll(p) {
    heroProgress = p;
    if (gridLayer) gridLayer.style.transform = "translateY(" + (p * -70).toFixed(1) + "px)";
    if (photoLayer) photoLayer.style.transform = "translateY(" + (p * 130).toFixed(1) + "px)";
    var ph = photoLayer ? photoLayer.querySelector("img") : null;
    if (ph) ph.style.transform = "scale(" + (1.12 - p * 0.1).toFixed(3) + ")";
  }

  /* =========================================================================
     THE JUSTIFICATION ENGINE (no GSAP needed for the core math)
     ========================================================================= */
  var wordmark = doc.getElementById("wordmark");
  function justifyWordmark(p) {
    if (!wordmark) return;
    // measure narrows then widens; left-anchored so the right margin moves
    var w = p < 0.5 ? lerp(62, 100, p / 0.5) : lerp(100, 74, (p - 0.5) / 0.5);
    var ls = p < 0.5 ? lerp(-0.02, 0.03, p / 0.5) : lerp(0.03, -0.005, (p - 0.5) / 0.5);
    wordmark.style.width = w.toFixed(2) + "%";
    wordmark.style.letterSpacing = ls.toFixed(4) + "em";
  }

  var chapterBody = doc.getElementById("chapterBody");
  var chapterFill = doc.getElementById("chapterFill");
  var roMeasure = doc.getElementById("roMeasure");
  var roWord = doc.getElementById("roWord");
  function justifyChapter(p) {
    if (chapterBody) {
      var w = p < 0.5 ? lerp(50, 100, p / 0.5) : lerp(100, 64, (p - 0.5) / 0.5);
      chapterBody.style.width = w.toFixed(2) + "%";
      if (roMeasure) roMeasure.textContent = Math.round(w * 0.62);
      if (roWord) roWord.textContent = Math.round(100 + (100 - w) * 1.9);
    }
    if (chapterFill) chapterFill.style.width = (p * 100).toFixed(1) + "%";
  }

  /* =========================================================================
     SCROLL MOTION - GSAP / ScrollTrigger / Lenis / SplitType
     ========================================================================= */
  if (reduce || !hasGSAP || !hasST) {
    // No motion engine (reduced-motion, OR the GSAP/ScrollTrigger CDN failed to
    // load while this local script still ran): reveal EVERYTHING so clip-masked
    // images and split-line copy can never stay hidden behind a dead trigger.
    revealAll();
    return;
  }

  var gsap = window.gsap;
  var ST = window.ScrollTrigger;
  gsap.registerPlugin(ST);

  /* ---- Lenis smooth scroll, bridged to ScrollTrigger ---- */
  var lenis = null;
  if (typeof window.Lenis !== "undefined") {
    try {
      lenis = new window.Lenis({ duration: 0.88, wheelMultiplier: 1.25, smoothWheel: true });
      lenis.on("scroll", ST.update);
      gsap.ticker.add(function (time) { lenis.raf(time * 1000); });
      gsap.ticker.lagSmoothing(0);
    } catch (e) { lenis = null; }
  }

  // Keep ScrollTrigger in sync with ANY scroll source - native wheel/keyboard,
  // anchor jumps, find-in-page, or programmatic window.scrollTo - not just Lenis.
  // Without this a non-Lenis scroll can skip a reveal trigger and strand a
  // split-line section (e.g. the manifesto) translated out of view.
  window.addEventListener("scroll", function () { ST.update(); }, { passive: true });

  /* ---- HERO: sticky stage + scrub drives the justify engine & parallax ---- */
  var heroSection = doc.querySelector(".hero");
  var introDone = false;
  if (heroSection) {
    justifyWordmark(0); applyHeroScroll(0);
    ST.create({
      trigger: heroSection, start: "top top", end: "bottom bottom", scrub: true,
      onUpdate: function (self) {
        // until the user scrolls, the load intro owns the measure; don't let a
        // progress~0 fire snap the wordmark back to its tight start state.
        if (self.progress > 0.0008 || introDone) justifyWordmark(self.progress);
        applyHeroScroll(self.progress);
      }
    });
    // AT-REST SIGNATURE: on load the wordmark "sets the measure" - the column
    // opens from a tight justify out to full width and settles back to its rest
    // state, demonstrating the justification engine before any scroll. It hands
    // the measure to the scrub seamlessly (ends where progress 0 begins).
    (function playIntro() {
      var start = null, dur = 2300;
      function frame(ts) {
        if (start === null) start = ts;
        var p = clamp((ts - start) / dur, 0, 1);
        var phase = p < 0.6 ? (p / 0.6) : (1 - (p - 0.6) / 0.4);   // 0 -> 1 -> 0
        var e = phase < 0.5 ? 2 * phase * phase : 1 - Math.pow(-2 * phase + 2, 2) / 2;
        justifyWordmark(e * 0.5);                                   // tight -> full -> tight
        if (p < 1) requestAnimationFrame(frame);
        else { introDone = true; justifyWordmark(0); }
      }
      requestAnimationFrame(frame);
    })();
  }

  /* ---- CHAPTER: sticky stage + scrub re-justifies the paragraph ---- */
  var chapterSection = doc.querySelector(".chapter");
  if (chapterSection) {
    justifyChapter(0);
    ST.create({
      trigger: chapterSection, start: "top top", end: "bottom bottom", scrub: true,
      onUpdate: function (self) { justifyChapter(self.progress); }
    });
  }

  /* ---- per-element justify scrub: width narrows -> widens -> settles ---- */
  gsap.utils.toArray("[data-justify]").forEach(function (el) {
    var mn = parseFloat(el.getAttribute("data-jmin")) || 62;
    var md = parseFloat(el.getAttribute("data-jmid")) || 100;
    var en = parseFloat(el.getAttribute("data-jend")) || 78;
    gsap.timeline({ scrollTrigger: { trigger: el, start: "top 90%", end: "bottom 22%", scrub: true } })
      .fromTo(el, { width: mn + "%" }, { width: md + "%", ease: "none" })
      .to(el, { width: en + "%", ease: "none" });
  });

  /* ---- SplitType line reveals on [data-split] ---- */
  var hasSplit = typeof window.SplitType !== "undefined";
  gsap.utils.toArray("[data-split]").forEach(function (el) {
    var words = null;
    if (hasSplit) {
      try {
        var st = new window.SplitType(el, { types: "lines,words" });
        words = st.words;
        (st.lines || []).forEach(function (ln) { ln.style.overflow = "hidden"; });
      } catch (e) { words = null; }
    }
    if (!words || !words.length) {
      gsap.from(el, { autoAlpha: 0, y: 36, duration: 0.9, ease: "power3.out",
        scrollTrigger: { trigger: el, start: "top 85%" } });
      return;
    }
    gsap.set(words, { yPercent: 110, opacity: 0 });
    gsap.to(words, {
      yPercent: 0, opacity: 1, duration: 0.8, ease: "power3.out", stagger: 0.04,
      scrollTrigger: { trigger: el, start: "top 84%" }
    });
  });

  /* ---- clip-path media reveals ---- */
  gsap.utils.toArray(".clip-reveal").forEach(function (el) {
    var img = el.querySelector("img");
    var tl = gsap.timeline({ scrollTrigger: { trigger: el, start: "top 86%" } });
    tl.fromTo(el, { clipPath: "inset(0 0 100% 0)" }, { clipPath: "inset(0 0 0% 0)", duration: 1.0, ease: "power3.inOut" }, 0);
    if (img) tl.to(img, { scale: 1, duration: 1.25, ease: "power3.out" }, 0);
  });

  /* ---- animated counters ---- */
  gsap.utils.toArray("[data-count]").forEach(function (el) {
    var target = parseFloat(el.getAttribute("data-count")) || 0;
    var prefix = el.getAttribute("data-prefix") || "";
    var proxy = { v: 0 };
    gsap.to(proxy, {
      v: target, duration: 1.7, ease: "power2.out",
      scrollTrigger: { trigger: el, start: "top 90%" },
      onUpdate: function () { el.textContent = prefix + Math.round(proxy.v); }
    });
  });

  /* ---- magnetic CTA ---- */
  var cta = doc.getElementById("commit");
  if (cta && !reduce) {
    cta.addEventListener("mousemove", function (e) {
      var r = cta.getBoundingClientRect();
      gsap.to(cta, {
        x: (e.clientX - (r.left + r.width / 2)) * 0.35,
        y: (e.clientY - (r.top + r.height / 2)) * 0.35,
        duration: 0.4, ease: "power2.out"
      });
    });
    cta.addEventListener("mouseleave", function () {
      gsap.to(cta, { x: 0, y: 0, duration: 0.6, ease: "elastic.out(1,0.4)" });
    });
  }

  clearTimeout(settleTimer);
  ST.refresh();
})();
