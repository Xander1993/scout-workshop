/* WORKSHOP_FLOOR dashboard — main.js
   - Fetches /api/runs + /api/stats
   - Renders hero, marquee, density bars, runs grid, filter rail
   - GSAP entrance + ScrollTrigger reveals
   - Lenis smooth scroll
   - Magnetic micro-interaction on chips/cards
   - Click run card → modal with full detail
   - Polls /api/health every 30s for live indicator
*/

(() => {
"use strict";

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

const state = {
  runs: [],
  stats: null,
  filters: { register: null, aesthetic: null, audit_status: null },
};

const REG_LABELS = { conversion: "CONVERSION", awwwards: "AWWWARDS" };
const STATUS_LABELS = { pass: "PASS", warn: "WARN", fail: "FAIL", null: "PENDING" };

// ---------- DATA ----------
async function fetchData() {
  const [runsRes, statsRes] = await Promise.all([
    fetch("/api/runs").then(r => r.json()),
    fetch("/api/stats").then(r => r.json()),
  ]);
  state.runs = runsRes;
  state.stats = statsRes;
}

// ---------- HERO STATS ----------
function renderHeroStats() {
  if (!state.stats) return;
  for (const el of $$("[data-stat]")) {
    const key = el.dataset.stat;
    const val = state.stats[key];
    if (val == null) { el.textContent = "0"; continue; }
    animateCount(el, val);
  }
}

function animateCount(el, target) {
  const obj = { v: 0 };
  const isFloat = !Number.isInteger(target);
  const dur = 1.4;
  if (window.gsap) {
    gsap.to(obj, {
      v: target,
      duration: dur,
      ease: "power3.out",
      onUpdate: () => {
        el.textContent = isFloat ? obj.v.toFixed(1) : Math.round(obj.v).toLocaleString();
      },
    });
  } else {
    el.textContent = isFloat ? target.toFixed(1) : target.toLocaleString();
  }
}

// ---------- HERO LATEST ----------
function renderHeroLatest() {
  const latest = state.stats?.latest_run;
  if (!latest) return;
  const card = $("#hero-latest");
  card.removeAttribute("hidden");
  const img = $("#hero-latest-img");
  if (latest.screenshot_files?.includes("home-desktop.png")) {
    img.src = `/api/screenshot/${latest.slug}/home-desktop.png`;
  } else if (latest.screenshot_files?.length) {
    img.src = `/api/screenshot/${latest.slug}/${latest.screenshot_files[0]}`;
  }
  $("#hero-latest-ts").textContent = formatTs(latest.ts);
  $("#hero-latest-slug").textContent = `${latest.vertical} · ${latest.aesthetic.replaceAll("-", " ")}`;
  $("#hero-latest-excerpt").textContent = latest.brief_excerpt || "—";
  const chips = $("#hero-latest-chips");
  chips.innerHTML = "";
  chips.appendChild(makeChip(REG_LABELS[latest.register] || latest.register, `register-${latest.register}`));
  chips.appendChild(makeChip(STATUS_LABELS[latest.audit_status] || "PENDING", `status-${latest.audit_status || "none"}`));
  chips.appendChild(makeChip(`DENSITY · ${latest.density.toUpperCase()}`, `density-${latest.density}`));
}

// ---------- MARQUEE ----------
function renderMarquee() {
  const s = state.stats;
  if (!s) return;
  const items = [
    { num: s.total_runs, label: "runs observed" },
    { num: `${s.ship_rate_pct}%`, label: "ship rate" },
    { num: s.avg_warnings_per_run, label: "avg warnings" },
    { num: s.total_images_generated, label: "images generated" },
    { num: Object.keys(s.aesthetics || {}).length, label: "aesthetics tried" },
    { num: s.warn_count, label: "warned" },
    { num: s.pass_count, label: "passed clean" },
  ];
  // Duplicate the sequence for seamless scrolling
  const html = (items.map(itemHtml).join("") + '<span class="mq-sep">//</span>').repeat(2);
  $("#mq-track").innerHTML = html;
}
function itemHtml(it) {
  return `<span class="mq-item"><span class="num">${it.num}</span><em>${it.label}</em><span class="mq-sep">//</span></span>`;
}

// ---------- DENSITY BARS ----------
function renderDensity() {
  const dist = state.stats?.densities || {};
  const total = Object.values(dist).reduce((a, b) => a + b, 0) || 1;
  const buckets = ["rich", "ok", "thin", "sparse"];
  const labels = { rich: "RICH (10+ sections)", ok: "OK (6–9)", thin: "THIN (4–5)", sparse: "SPARSE (≤3)" };
  $("#density-bars").innerHTML = buckets.map(b => {
    const n = dist[b] || 0;
    const pct = Math.round((n / total) * 100);
    return `<div class="density-bar fadein" data-bucket="${b}">
      <div class="density-bar-label">${labels[b]}</div>
      <div class="density-bar-count">${n}</div>
      <div class="density-bar-pct">${pct}% OF RUNS</div>
    </div>`;
  }).join("");
}

// ---------- RUNS GRID ----------
function renderRuns() {
  const filtered = state.runs.filter(r => {
    if (state.filters.register && r.register !== state.filters.register) return false;
    if (state.filters.aesthetic && r.aesthetic !== state.filters.aesthetic) return false;
    if (state.filters.audit_status && r.audit_status !== state.filters.audit_status) return false;
    return true;
  });
  $("#visible-count").textContent = filtered.length;
  $("#runs-grid").innerHTML = filtered.map(runCardHtml).join("");
  // Attach card click handlers
  $$(".run-card").forEach(card => {
    card.addEventListener("click", () => openDetail(card.dataset.slug));
  });
  // Run entrance animation
  if (window.gsap) {
    gsap.fromTo(".run-card", { opacity: 0, y: 18 },
      { opacity: 1, y: 0, duration: .7, stagger: .04, ease: "power3.out" });
  }
}
function runCardHtml(r) {
  const hasHome = r.screenshot_files?.includes("home-desktop.png");
  const imgSrc = hasHome ? `/api/screenshot/${r.slug}/home-desktop.png`
               : r.screenshot_files?.length ? `/api/screenshot/${r.slug}/${r.screenshot_files[0]}`
               : "";
  const cleanAesthetic = r.aesthetic.replaceAll("-", " ");
  return `<article class="run-card" data-slug="${r.slug}">
    <div class="run-card-image">
      ${imgSrc ? `<img loading="lazy" src="${imgSrc}" alt="">` : ""}
      <span class="run-card-density ${r.density}">${r.density.toUpperCase()}</span>
    </div>
    <div class="run-card-body">
      <div class="run-card-meta">
        <span>${formatTsShort(r.ts)}</span>
        <span>${r.vertical}</span>
      </div>
      <div class="run-card-slug">${cleanAesthetic}</div>
      <div class="run-card-chips">
        <span class="chip size-sm register-${r.register}">${REG_LABELS[r.register] || r.register}</span>
        ${r.audit_status ? `<span class="chip size-sm status-${r.audit_status}">${STATUS_LABELS[r.audit_status]}</span>` : ""}
        ${r.register_verdict ? `<span class="chip size-sm ${r.flagged ? "verdict-flagged" : "verdict-pass"}" title="${(r.register_verdict.reasons || []).join("; ")}">${r.flagged ? "⚑ FLAGGED" : "★ PREMIUM"}</span>` : ""}
        ${r.warnings_count > 0 ? `<span class="chip size-sm">${r.warnings_count}<span style="opacity:.6"> W</span></span>` : ""}
      </div>
    </div>
  </article>`;
}

// ---------- FILTERS ----------
function renderFilters() {
  // Register
  const registers = Array.from(new Set(state.runs.map(r => r.register)));
  $("#filter-register").innerHTML = registers.map(r =>
    `<button class="chip" data-filter="register" data-value="${r}">${REG_LABELS[r] || r}</button>`).join("");
  // Aesthetic
  const aesthetics = Array.from(new Set(state.runs.map(r => r.aesthetic))).sort();
  $("#filter-aesthetic").innerHTML = aesthetics.map(a =>
    `<button class="chip" data-filter="aesthetic" data-value="${a}">${a.replaceAll("-", " ").toUpperCase()}</button>`).join("");
  // Status
  const statuses = Array.from(new Set(state.runs.map(r => r.audit_status).filter(Boolean)));
  $("#filter-status").innerHTML = statuses.map(s =>
    `<button class="chip status-${s}" data-filter="audit_status" data-value="${s}">${STATUS_LABELS[s]}</button>`).join("");

  $$(".rail .chip").forEach(c => {
    c.addEventListener("click", () => {
      const f = c.dataset.filter;
      const v = c.dataset.value;
      if (state.filters[f] === v) { state.filters[f] = null; }
      else { state.filters[f] = v; }
      // Update active state
      $$(`[data-filter="${f}"]`).forEach(el => el.classList.toggle("active", el.dataset.value === state.filters[f]));
      renderRuns();
    });
  });

  $("#rail-clear").addEventListener("click", () => {
    state.filters = { register: null, aesthetic: null, audit_status: null };
    $$(".rail .chip").forEach(el => el.classList.remove("active"));
    renderRuns();
  });
}

// ---------- DETAIL MODAL ----------
async function openDetail(slug) {
  const data = await fetch(`/api/runs/${encodeURIComponent(slug)}`).then(r => r.json());
  const body = $("#modal-body");
  const cleanAesthetic = data.aesthetic.replaceAll("-", " ");
  const warnings = data.warnings || [];
  const screenshots = data.screenshot_files || [];

  body.innerHTML = `
    <div class="detail-head">
      <div class="detail-eyebrow">${formatTs(data.ts)} · ${data.vertical} · ${data.register}</div>
      <h2 class="detail-title">${cleanAesthetic}</h2>
      <div class="detail-chips">
        <span class="chip register-${data.register}">${REG_LABELS[data.register] || data.register}</span>
        ${data.audit_status ? `<span class="chip status-${data.audit_status}">${STATUS_LABELS[data.audit_status]}</span>` : ""}
        <span class="chip density-${data.density}">DENSITY · ${data.density.toUpperCase()}</span>
      </div>
    </div>

    <div class="detail-grid">
      <div class="detail-box">
        <h4>BRIEF · AESTHETIC</h4>
        <p>${(data.brief_excerpt || "—").replaceAll("*", "")}</p>
      </div>
      <div class="detail-box">
        <h4>STATS</h4>
        <div class="detail-stats">
          <div><div class="detail-stat-num">${data.sections_index_html + data.articles_index_html}</div><div class="detail-stat-lbl">SECTIONS</div></div>
          <div><div class="detail-stat-num">${data.image_files}</div><div class="detail-stat-lbl">IMAGES</div></div>
          <div><div class="detail-stat-num">${data.warnings_count}</div><div class="detail-stat-lbl">WARNINGS</div></div>
          <div><div class="detail-stat-num">${Math.round(data.bytes_index_html / 1024)}<span class="unit" style="font-size:.55em;color:var(--muted);font-style:italic">k</span></div><div class="detail-stat-lbl">INDEX HTML</div></div>
        </div>
      </div>
    </div>

    ${warnings.length ? `
    <div class="detail-box" style="margin-top:2rem">
      <h4>AUDIT WARNINGS</h4>
      <ul class="detail-warnings">
        ${warnings.slice(0, 12).map(w => `<li>${escapeHtml(w)}</li>`).join("")}
      </ul>
    </div>` : ""}

    ${screenshots.length ? `
    <h4 style="margin-top:2.4rem;font-family:var(--mono);font-size:.6875rem;letter-spacing:.22em;color:var(--muted);text-transform:uppercase">SCREENSHOTS</h4>
    <div class="detail-screenshots">
      ${screenshots.map(s => `<a href="/api/screenshot/${data.slug}/${s}" target="_blank"><img loading="lazy" src="/api/screenshot/${data.slug}/${s}" alt=""></a>`).join("")}
    </div>` : ""}
  `;

  const modal = $("#modal");
  modal.removeAttribute("hidden");
  modal.setAttribute("aria-hidden", "false");
  if (window.gsap) {
    gsap.fromTo(".modal-frame", { opacity: 0, y: 24, scale: .97 },
      { opacity: 1, y: 0, scale: 1, duration: .55, ease: "power3.out" });
  }
}

function closeDetail() {
  const modal = $("#modal");
  modal.setAttribute("hidden", "");
  modal.setAttribute("aria-hidden", "true");
}

// ---------- HELPERS ----------
function makeChip(label, klass = "") {
  const el = document.createElement("span");
  el.className = `chip ${klass}`;
  el.textContent = label;
  return el;
}
function formatTs(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" }).toUpperCase()
      + " · " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}
function formatTsShort(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" }).toUpperCase();
  } catch { return iso; }
}
function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ---------- MAGNETIC MICRO-INTERACTION ----------
function attachMagnetic(sel, strength = 0.25) {
  if (!window.gsap) return;
  $$(sel).forEach(el => {
    el.addEventListener("mousemove", e => {
      const r = el.getBoundingClientRect();
      const x = (e.clientX - r.left - r.width / 2) * strength;
      const y = (e.clientY - r.top - r.height / 2) * strength;
      gsap.to(el, { x, y, duration: .4, ease: "power3.out" });
    });
    el.addEventListener("mouseleave", () => {
      gsap.to(el, { x: 0, y: 0, duration: .5, ease: "elastic.out(1,0.6)" });
    });
  });
}

// ---------- INIT ----------
async function init() {
  // Native scroll only — Lenis removed because it fought ScrollTrigger
  // and double-smoothed against CSS `scroll-behavior`.
  await fetchData();
  renderHeroStats();
  renderHeroLatest();
  renderMarquee();
  renderDensity();
  renderFilters();
  renderRuns();

  document.body.classList.remove("loading");
  document.body.classList.add("loaded");

  // ScrollTrigger reveals
  if (window.gsap && window.ScrollTrigger) {
    gsap.registerPlugin(ScrollTrigger);
    gsap.utils.toArray(".density-bar").forEach((el, i) => {
      gsap.fromTo(el, { opacity: 0, y: 24 },
        { opacity: 1, y: 0, duration: .7, delay: i * 0.05, ease: "power3.out",
          scrollTrigger: { trigger: el, start: "top 88%" } });
    });
    gsap.from(".grid-title", { opacity: 0, y: 30, duration: 1, ease: "power3.out",
      scrollTrigger: { trigger: ".grid", start: "top 80%" } });
    gsap.from(".ft-wordmark", { opacity: 0, y: 40, duration: 1.2, ease: "power3.out",
      scrollTrigger: { trigger: ".ft", start: "top 88%" } });
  }

  // Magnetic micro-interaction (settled after first render)
  setTimeout(() => attachMagnetic(".rail .chip", 0.35), 200);

  // Modal close handlers
  document.addEventListener("click", e => {
    if (e.target.closest("[data-close]")) closeDetail();
  });
  document.addEventListener("keydown", e => {
    if (e.key === "Escape") closeDetail();
  });

  // Live indicator: poll health every 30s
  setInterval(async () => {
    try {
      const h = await fetch("/api/health").then(r => r.json());
      if (h.ok) {
        $(".hd-status-text").textContent = "LIVE · TAILNET";
      }
    } catch {
      $(".hd-status-text").textContent = "OFFLINE";
    }
  }, 30000);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}

})();
