/* =========================================================
   Riwaq, Sunstruck Relief controller
   Live-renders the hero headline as sun-cast shadow on stone.
   Scroll advances the sun about one minute per pixel until it sets.
   Graceful degradation: if GSAP/Lenis/SplitType fail to load,
   the canvas hero still runs from vanilla scroll events.
   If canvas itself is unavailable, .hero__static fallback shows.
   ========================================================= */
(function(){
  "use strict";

  document.documentElement.classList.remove("no-js");
  document.documentElement.classList.add("js");

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- HERO: sunstruck relief canvas ---------- */
  function initHero(){
    var stage = document.querySelector("[data-hero]");
    if(!stage) return null;
    var canvas = stage.querySelector("[data-hero-canvas]");
    if(!canvas || !canvas.getContext) return null;

    var ctx = canvas.getContext("2d");
    var dpr = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
    var text = (canvas.getAttribute("data-text") || "").trim() || "Built to be read in sunlight.";
    var words = text.split(/\s+/);
    // Compose into two rows when wide enough
    var rows;
    function composeRows(){
      // line 1: first half words, line 2: second half
      var mid = Math.ceil(words.length / 2);
      rows = [
        words.slice(0, mid).join(" "),
        words.slice(mid).join(" ")
      ];
    }
    composeRows();

    var W=0, H=0;
    function resize(){
      var r = stage.getBoundingClientRect();
      W = Math.max(320, Math.floor(r.width));
      H = Math.max(420, Math.floor(r.height));
      canvas.width  = Math.floor(W * dpr);
      canvas.height = Math.floor(H * dpr);
      canvas.style.width  = W + "px";
      canvas.style.height = H + "px";
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();

    /* derive sun state from scroll progress [0..1]
       0 = dawn (sun low, east, very long shadows west)
       .5 = midday (sun high, short shadows)
       1 = sunset (sun low, west, very long shadows east; type dissolves) */
    function paint(p){
      ctx.clearRect(0,0,W,H);

      // colours from palette
      var BG       = "#E7DCC4";  // --color-bg
      var SUPPORT1 = "#DDD0B4";  // --color-support-1
      var SUPPORT2 = "#9C8E73";  // --color-support-2 = shadow
      var ACCENT   = "#B8462C";  // --color-accent   = sun
      var FG       = "#1A1814";  // --color-fg

      // NOTE: the canvas is transparent so the real relief-wall photograph
      // behind it shows through; the headline below casts its shadow onto
      // that actual stone. We only lay down light/heat, never an opaque field.

      // raking-light vignette across plate (one chromatic event)
      var sunX = (1 - p) * W * 0.15 + p * W * 0.85; // east to west
      var rake = ctx.createRadialGradient(sunX, H * (0.18 + p*0.5), W*0.05, sunX, H*0.5, W*0.85);
      rake.addColorStop(0, hexA(ACCENT, 0.18 * (1 - Math.abs(p-0.5)*1.6)));
      rake.addColorStop(0.6, hexA(ACCENT, 0));
      ctx.fillStyle = rake;
      ctx.fillRect(0,0,W,H);

      // ---- text geometry
      var pad = Math.max(20, W * 0.05);
      var availW = W - pad*2;
      // size the longest line to FILL the available width (monumental), capped by height
      var trial = 100;
      ctx.font = '700 ' + trial + 'px "Cormorant Garamond",Georgia,serif';
      var maxLine = Math.max(ctx.measureText(rows[0]).width, ctx.measureText(rows[1]).width);
      var fillSize = trial * (availW / maxLine);
      var fontSize = Math.min(fillSize, H * 0.42);
      ctx.font = '700 ' + fontSize + 'px "Cormorant Garamond",Georgia,serif';
      ctx.textBaseline = "alphabetic";

      var lineH = fontSize * 0.92;
      var totalH = lineH * 2;
      var topY = (H - totalH) / 2 + lineH * 0.82;

      // ---- compute shadow vector
      // sun altitude: high at p=.5, low at edges → shadow length inverse
      var altitude = Math.sin(Math.PI * Math.min(0.999, Math.max(0.001, p))); // 0..1..0
      var azimuthN = p - 0.5; // -.5 east → .5 west
      // shadow length grows toward edges; capped so glyphs remain composed
      var shadowLen = (1 - altitude) * fontSize * 1.6 + fontSize * 0.06;
      var shadowDx =  azimuthN * 2.2 * shadowLen; // east sun → shadow points west (negative? we follow azimuth)
      var shadowDy =  shadowLen * 0.18;          // small vertical lengthen

      // dissolve factor (final 15% scroll the headline melts to umber)
      var dissolve = smoothstep(0.85, 1.0, p);

      // ---- cast shadow (umber, layered offsets)
      var steps = 14;
      ctx.save();
      for(var i = steps; i >= 1; i--){
        var t = i / steps;
        var dx = shadowDx * t;
        var dy = shadowDy * t;
        var a  = 0.06 * (1 - t) + 0.04;
        ctx.fillStyle = hexA(SUPPORT2, a * (1 - dissolve * 0.55));
        for(var r = 0; r < 2; r++){
          ctx.fillText(rows[0], pad + dx, topY + dy);
          ctx.fillText(rows[1], pad + dx, topY + lineH + dy);
        }
      }
      ctx.restore();

      // ---- ground shadow stripe under headline (subtle)
      var stripeY = topY + lineH + fontSize * 0.12;
      var stripe = ctx.createLinearGradient(0, stripeY, 0, stripeY + fontSize * 0.6);
      stripe.addColorStop(0, hexA(FG, 0.07 * (1 - dissolve)));
      stripe.addColorStop(1, hexA(FG, 0));
      ctx.fillStyle = stripe;
      ctx.fillRect(pad - fontSize*0.1, stripeY, availW + fontSize*0.2, fontSize * 0.6);

      // ---- carved relief headline (the type IS the lit chiaroscuro)
      // Build a clip from text, then fill with directional gradient.
      ctx.save();
      // path: two lines
      ctx.beginPath();
      // We can't directly add text to path in all browsers; use a fillText pass into an offscreen mask
      // Approach: draw text twice, first a lit gradient, then a fine umber edge on the shadow side
      var gradAngle = Math.PI * (0.5 + azimuthN * 0.9); // light direction across letterform
      var gx0 = sunX, gy0 = topY - lineH*0.6;
      var gx1 = gx0 - Math.cos(gradAngle) * W, gy1 = gy0 + Math.sin(gradAngle) * H;
      var letterGrad = ctx.createLinearGradient(gx0, gy0, gx1, gy1);
      var litStop  = 0.05;
      var midStop  = 0.45 + altitude*0.15;
      var darkStop = 1.0;
      letterGrad.addColorStop(litStop,  lerpColor(ACCENT, "#E8B88E", 0.25));
      letterGrad.addColorStop(midStop,  ACCENT);
      letterGrad.addColorStop(0.85,     SUPPORT2);
      letterGrad.addColorStop(darkStop, lerpColor(SUPPORT2, FG, 0.6));

      // dissolve toward umber
      var headFill = letterGrad;
      ctx.fillStyle = headFill;
      ctx.globalAlpha = 1 - dissolve * 0.55;
      ctx.fillText(rows[0], pad, topY);
      ctx.fillText(rows[1], pad, topY + lineH);

      // umber edge along shadow side, gives carved-stone bevel
      ctx.globalAlpha = (0.65 - dissolve*0.55) * (1 - altitude*0.6);
      ctx.fillStyle = SUPPORT2;
      var bevX = -azimuthN * fontSize * 0.04;
      var bevY = fontSize * 0.02;
      ctx.fillText(rows[0], pad + bevX, topY + bevY);
      ctx.fillText(rows[1], pad + bevX, topY + lineH + bevY);

      // highlight rim on lit side, thin ochre keyline
      ctx.globalAlpha = (0.45 - dissolve*0.45) * altitude;
      ctx.fillStyle = lerpColor(ACCENT, BG, 0.45);
      var litX =  azimuthN * fontSize * 0.03;
      var litY = -fontSize * 0.015;
      ctx.fillText(rows[0], pad + litX, topY + litY);
      ctx.fillText(rows[1], pad + litX, topY + lineH + litY);

      ctx.restore();

      // ---- final umber dissolve overlay
      if(dissolve > 0){
        ctx.fillStyle = hexA(SUPPORT2, dissolve * 0.55);
        ctx.fillRect(0,0,W,H);
        // residual heat letterforms
        ctx.globalAlpha = dissolve * 0.32;
        ctx.fillStyle = lerpColor(SUPPORT2, FG, 0.55);
        ctx.fillText(rows[0], pad, topY);
        ctx.fillText(rows[1], pad, topY + lineH);
        ctx.globalAlpha = 1;
      }

      // spec table active row
      var rowsEls = document.querySelectorAll("[data-spec-row]");
      if(rowsEls.length){
        var idx = Math.min(rowsEls.length-1, Math.floor(p * rowsEls.length));
        for(var k=0;k<rowsEls.length;k++){
          rowsEls[k].setAttribute("data-active", k===idx ? "true" : "false");
        }
      }
    }

    window.addEventListener("resize", function(){
      resize();
      composeRows();
      paint(currentP);
    });

    return { paint: paint };
  }

  /* ---------- helpers ---------- */
  function smoothstep(a,b,x){
    var t = Math.max(0, Math.min(1, (x-a)/(b-a)));
    return t*t*(3 - 2*t);
  }
  function hex2rgb(h){
    h = h.replace("#","");
    if(h.length===3) h = h.split("").map(function(c){return c+c}).join("");
    return [parseInt(h.slice(0,2),16), parseInt(h.slice(2,4),16), parseInt(h.slice(4,6),16)];
  }
  function rgb2hex(r,g,b){
    function h(n){var s=Math.max(0,Math.min(255,Math.round(n))).toString(16);return s.length<2?"0"+s:s}
    return "#"+h(r)+h(g)+h(b);
  }
  function lerpColor(a,b,t){
    var A = hex2rgb(a), B = hex2rgb(b);
    return rgb2hex(A[0]+(B[0]-A[0])*t, A[1]+(B[1]-A[1])*t, A[2]+(B[2]-A[2])*t);
  }
  function hexA(h,a){
    var r = hex2rgb(h);
    return "rgba("+r[0]+","+r[1]+","+r[2]+","+a.toFixed(3)+")";
  }

  /* ---------- scroll → sun progress ---------- */
  var hero;
  var currentP = 0;

  function readProgress(){
    var doc = document.documentElement;
    var max = Math.max(1, doc.scrollHeight - window.innerHeight);
    var y = window.scrollY || window.pageYOffset || 0;
    return Math.min(1, Math.max(0, y / max));
  }

  function applyP(p){
    currentP = p;
    document.documentElement.style.setProperty("--sun", p.toFixed(4));
    if(hero) hero.paint(p);
  }

  var userScrolled = false;

  /* one-shot intro: the sun visibly rises across the relief and settles, so the
     hero is alive AT REST on load (not a frozen shadow waiting for scroll). */
  function playIntro(){
    if(!hero || reduceMotion){ applyP(0); return; }
    var dur = 2200, t0 = null, peak = 0.34;
    function frame(ts){
      if(userScrolled) return;            // hand off the moment the user scrolls
      if(t0 === null) t0 = ts;
      var k = Math.min(1, (ts - t0) / dur);
      // ease out-and-back: rise to peak, settle to dawn (0)
      var e = Math.sin(Math.PI * k);       // 0 -> 1 -> 0
      hero.paint(peak * (e*e*(3-2*e)));    // smoothed
      document.documentElement.style.setProperty("--sun", (peak*e).toFixed(4));
      if(k < 1 && !userScrolled) requestAnimationFrame(frame);
      else if(!userScrolled) applyP(0);
    }
    requestAnimationFrame(frame);
  }

  function init(){
    hero = initHero();
    applyP(0);

    /* standfirst settles in beneath the relief shortly after load (it lives in
       the first viewport, so reveal it where it can actually be seen) */
    var stand = document.querySelector("[data-standfirst]");
    if(stand){
      if(reduceMotion) stand.classList.add("is-on");
      else setTimeout(function(){ stand.classList.add("is-on"); }, 650);
    }

    /* masthead gains a soft scrim once scrolled, so the nav stays legible over
       photographs and the dark lower plates (esp. on mobile, no mix-blend). */
    var masthead = document.querySelector(".masthead");
    function syncMasthead(){
      var y = window.scrollY || window.pageYOffset || 0;
      if(y > 40){ userScrolled = true; }
      if(masthead) masthead.classList.toggle("is-scrolled", y > 40);
    }
    window.addEventListener("scroll", syncMasthead, { passive: true });
    syncMasthead();
    playIntro();

    /* Lenis smooth scroll, optional */
    var lenis = null;
    if(window.Lenis && !reduceMotion){
      try{
        lenis = new window.Lenis({
          duration: 1.15,
          easing: function(t){ return Math.min(1, 1.001 - Math.pow(2, -10 * t)); },
          smoothWheel: true,
          smoothTouch: false
        });
        function raf(time){ lenis.raf(time); requestAnimationFrame(raf); }
        requestAnimationFrame(raf);
      } catch(e){ lenis = null; }
    }

    /* GSAP ScrollTrigger, optional, drives sun precisely if present */
    if(window.gsap && window.ScrollTrigger && !reduceMotion){
      try{
        window.gsap.registerPlugin(window.ScrollTrigger);
        if(lenis){
          lenis.on("scroll", window.ScrollTrigger.update);
          window.gsap.ticker.add(function(time){ lenis.raf(time * 1000); });
          window.gsap.ticker.lagSmoothing(0);
        }
        window.ScrollTrigger.create({
          start: 0, end: "max",
          onUpdate: function(self){ if(self.progress > 0.0008) userScrolled = true; applyP(self.progress); }
        });
      } catch(e){
        bindFallbackScroll();
      }
    } else {
      bindFallbackScroll();
    }

    function bindFallbackScroll(){
      var ticking = false;
      function onScroll(){
        if(ticking) return;
        ticking = true;
        requestAnimationFrame(function(){
          applyP(readProgress());
          ticking = false;
        });
      }
      window.addEventListener("scroll", onScroll, { passive: true });
      onScroll();
    }

    /* Magnetic CTA (single instance in manifesto) */
    var magnets = document.querySelectorAll("[data-magnetic]");
    magnets.forEach(function(m){
      if(reduceMotion) return;
      m.addEventListener("pointermove", function(e){
        var r = m.getBoundingClientRect();
        var x = e.clientX - (r.left + r.width/2);
        var y = e.clientY - (r.top + r.height/2);
        m.style.setProperty("--m-x", (x*0.18).toFixed(1) + "px");
        m.style.setProperty("--m-y", (y*0.2).toFixed(1) + "px");
      });
      m.addEventListener("pointerleave", function(){
        m.style.setProperty("--m-x","0px");
        m.style.setProperty("--m-y","0px");
      });
    });
  }

  if(document.readyState === "loading"){
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
