/* ============================================================
   MARN — Rammed Seam motion
   - Bicolor headline straddles a fixed seam (composition reads at rest)
   - Character reveal on load, compaction strata settle in on scroll
   - Lenis smooth scroll mimicking settling clay
   - Graceful degradation if any lib is absent
   ============================================================ */
(function () {
  "use strict";

  const docEl = document.documentElement;
  const reduce = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const hasGsap = typeof window.gsap !== "undefined";
  const hasST   = hasGsap && typeof window.ScrollTrigger !== "undefined";
  const hasLenis = typeof window.Lenis !== "undefined";
  const hasSplit = typeof window.SplitType !== "undefined";

  if (hasST) window.gsap.registerPlugin(window.ScrollTrigger);

  /* ---- Lenis: settling-clay easing ---- */
  let lenis = null;
  if (hasLenis && !reduce) {
    lenis = new window.Lenis({
      duration: 1.25,
      easing: (t) => 1 - Math.pow(1 - t, 4), // quartic out — slow settle
      smoothWheel: true,
      smoothTouch: false,
      wheelMultiplier: 0.95,
    });
    const raf = (time) => { lenis.raf(time); requestAnimationFrame(raf); };
    requestAnimationFrame(raf);
    if (hasST) {
      lenis.on("scroll", window.ScrollTrigger.update);
      window.gsap.ticker.add((t) => lenis.raf(t * 1000));
      window.gsap.ticker.lagSmoothing(0);
    }
  }

  /* ---- Hero: bicolor headline + seam compression ---- */
  const hero = document.querySelector("[data-hero]");
  if (hero) {
    // Split the headline (anchor + both layers) for SplitType char animation.
    let chars = [];
    if (hasSplit && !reduce) {
      const h1 = hero.querySelector(".hero-h1 .anchor");
      const layerInk = hero.querySelector(".hero-h1 .layer--ink");
      const layerCream = hero.querySelector(".hero-h1 .layer--cream");
      try {
        new window.SplitType(h1, { types: "chars" });
        new window.SplitType(layerInk, { types: "chars" });
        new window.SplitType(layerCream, { types: "chars" });
        chars = h1.querySelectorAll(".char");
      } catch (e) { /* noop */ }
    }

    // Intro reveal: characters rise into place.
    if (hasGsap && chars.length && !reduce) {
      const inkChars = hero.querySelectorAll(".hero-h1 .layer--ink .char");
      const creamChars = hero.querySelectorAll(".hero-h1 .layer--cream .char");
      window.gsap.set([chars, inkChars, creamChars], { yPercent: 110, opacity: 0 });
      window.gsap.to([chars, inkChars, creamChars], {
        yPercent: 0,
        opacity: 1,
        duration: 1.1,
        ease: "power3.out",
        stagger: 0.035,
        delay: 0.15,
      });
    }

    // Seam settle on load: the rammed seam compresses from a slightly open
    // pour into its true vertical, the bicolor wordmark resolving as it lands.
    // Desktop only. On mobile the seam collapses to a full-bleed wall (CSS).
    if (hasGsap && !reduce && window.innerWidth > 760) {
      const seam = { x: 46.5 };
      window.gsap.to(seam, {
        x: 50,
        duration: 1.4,
        ease: "power3.out",
        delay: 0.1,
        onUpdate: () => hero.style.setProperty("--seam-x", seam.x + "%"),
      });
    }
  }

  /* ---- Plate parallax (max 8%) ---- */
  if (hasST && !reduce) {
    document.querySelectorAll(".plate img").forEach((img) => {
      window.gsap.fromTo(
        img,
        { yPercent: -4 },
        {
          yPercent: 4,
          ease: "none",
          scrollTrigger: {
            trigger: img.closest(".plate"),
            start: "top bottom",
            end: "bottom top",
            scrub: true,
          },
        }
      );
    });
  }

  /* ---- Magnetic CTA — sienna-glow on cream ---- */
  document.querySelectorAll("[data-magnetic]").forEach((el) => {
    if (reduce) return;
    let rect = null;
    const onEnter = () => { rect = el.getBoundingClientRect(); };
    const onMove = (e) => {
      if (!rect) rect = el.getBoundingClientRect();
      const x = e.clientX - (rect.left + rect.width / 2);
      const y = e.clientY - (rect.top + rect.height / 2);
      el.style.transform = "translate(" + x * 0.18 + "px," + y * 0.18 + "px)";
    };
    const onLeave = () => {
      el.style.transform = "translate(0,0)";
      rect = null;
    };
    el.addEventListener("mouseenter", onEnter);
    el.addEventListener("mousemove", onMove);
    el.addEventListener("mouseleave", onLeave);
    el.style.transition = "transform .35s cubic-bezier(.2,.7,.2,1)";
  });

  /* ---- Ensure ScrollTrigger refreshes after fonts load ---- */
  if (document.fonts && hasST) {
    document.fonts.ready.then(() => window.ScrollTrigger.refresh());
  }
})();
