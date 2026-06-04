# Workshop v1.3 description

Draft for Alex review. Sign off triggers technical bootstrap.

## What v1.3 is

Workshop currently ships conversion-template kits — homepage-services-contacts trios optimized for 999.md small-business buyers. Phone number in header, trust badges, big "Book Now" CTA above the fold, the whole conversion playbook. That register works for plumbers, salons, locksmiths, hauliers — buyers who need their website to perform a specific job.

v1.3 adds a second register: awwwards-tier kits. Different buyer, different rules. EU agencies looking for white-label showpieces don't want a phone number in the header — they want a manifesto headline, restrained interactive accents, dramatic type scale, motion choreography, palette tones that read as deliberate. Studio Namma, Marvell, Astrodither, Obys quality bar. The probe sequence on May 10 reached that bar empirically with probe-5 — sun-baked palette, 5 distilled non-Namma moves, full motion vocabulary, 6 audit warnings (the lowest of any probe in the sequence).

v1.3 makes that probe-5-quality output reproducible from Workshop's normal weekly cron run, not from a one-off override script. The override mechanism that produced probe-5 was a hack on top of v1.2 machinery; v1.3 promotes that machinery into the playbook itself.

## How v1.3 coexists with v1.2

Both registers live in one Workshop. No second instance, no separate cron, no fork of the repo.

The mechanism: every kit in `queue.json` carries an `aesthetic_direction` flag — either `conversion` or `awwwards`. Workshop reads the next kit in queue order, sees the flag, routes to the matching pipeline. Different aesthetic config, different audit prompt, different kit-template variant. Both pipelines commit to the same `camelotflows-kits` repo, just in different subfolders by date and slug.

Cron stays the same — weekly run picks one kit from queue, processes it. Manual trigger via `workshop-manual.service` stays the same. The only thing that changes when v1.3 ships is what's IN the queue and how each kit gets processed once Workshop reads its flag.

Conversion kits keep flowing for the 999.md market. Awwwards kits flow in parallel for the EU agency white-label market. Two products, one factory.

## What gets added to the codebase

Nine pieces of work. Most are modifications, two are new files, one is a logic addition to `workshop.py`.

**1. New awwwards aesthetic family in `aesthetic_configs.py`, built empirically from exemplar SOTDs.** The file currently holds four conversion-template aesthetics. v1.3 adds a fifth section — `awwwards-tier` — with five sub-aesthetics nested inside: sun-baked, acid-tech, cool-jewel, warm-earth, editorial-mid-century. Critical methodology: each sub-aesthetic config is built from 2-3 exemplar Awwwards SOTDs (specific Site-of-the-Day entries that exemplify that register), NOT from abstract mood words. Palette extracted from the exemplars' actual colors, photography prefix matched to their luminance profile, motion vocabulary catalogued from their actual implementations, reference-anchor list pointing to the exemplars' vault IDs. Sun-baked already has empirical anchors from probe-5 (Studio Namma + Marvell + Astrodither + Obys). The other four need exemplar identification during bootstrap Phase 1 before their configs can be built. This is "Mechanism 1: empirical anchoring" — the answer to "why would the first non-sun-baked kit not be ugly". Without anchored exemplars, the model invents palette and moves from training data instead of distilling from references; result is a generic kit with right palette and empty moves. Anchored exemplars give the model the same material that produced probe-5 quality for sun-baked.

**2. New `self_audit_awwwards` prompt.** Lives in `workshop-playbook.md` parallel to the existing `self_audit`. Different boolean checks: instead of `has_click_to_call` and `has_trust_signals` (which are baked into v1.2 audit and made it impossible for awwwards kits to clear because they're built around different rules), the awwwards version checks `has_one_primary_cta`, `manifesto_headline_present`, `architectural_type_scale`, `motion_libraries_loaded_with_sri`, `palette_multi_tonal`. The yardstick matches the register. No more structural floor of 2 warnings that can never be cleared.

**3. Awwwards kit-template variant.** The current `workshop/kit-template/` is conversion-register-shaped (above-fold CTA, service cards, testimonial section, heavy contact form). The new awwwards variant lives in `workshop/kit-template-awwwards/` with different base structure — manifesto hero, portfolio grid, oversized footer wordmark, type-stack section. Workshop picks the variant by reading the kit's `aesthetic_direction` flag.

**4. Orchestration-time URL+SRI pre-flight.** Before `kit_generation` runs, Workshop fetches each CDN library URL it intends to use (GSAP, ScrollTrigger, SplitType, Lenis), computes their SRI hashes (SHA-512 fingerprints — strings that browsers compare against the actual file content to verify nothing's tampered with), and injects the exact strings into the prompt as constants. This eliminates the failure mode where the model invents plausible-looking cdnjs URLs that don't actually exist (probe-2 broke this way — model fabricated split-type and lenis URLs, both 404'd at runtime). If a library disappears between hash-compute and runtime, the run aborts loudly instead of silently shipping a broken kit.

**5. Palette-aware photography prefix.** After `kit_generation` produces theme files, Workshop parses the `--color-bg` CSS variable from the output, computes its luminance (0-255 brightness on a perceptual scale — a way to say "how light or dark this color reads to the eye"), and constructs a photography prompt prefix that ensures generated images will contrast against the page background. Light bg gets "low-to-mid-key dramatic photography" instruction; dark bg gets "high-key bright photography" instruction. Then Workshop patches (overwrites at runtime) `generate_kit_images.GENERATION_PROMPT_PREFIX` with that string before image generation runs. Probe-5 used this and landed 0 photo-bg luminance risks across all generated images.

**6. Source-HTML leak scan.** Currently Workshop's leak scan runs Playwright (a browser automation tool that loads the kit in a headless browser) and reads `innerText` from the rendered page. Problem: CSS `text-transform: lowercase` makes `{{BRAND}}` render in `innerText` as `{{brand}}`, which the scan flags as a stray token even though the source HTML was clean. v1.3 leak scan reads the source HTML files directly with regex, ignoring CSS transformations. False positives from probe-4 disappear.

**7. Word-length cap for hero h1.** In probes 2-4, the hero headline used `clamp(4rem, 22vw, 18rem)` font sizing. With a long word like "considered" (10 characters), the responsive 22vw size overflowed the viewport at 390px mobile width — text wrapped mid-word. probe-5 reduced to `clamp(3.5rem, 16vw, 12rem)` AND added a rule: no word in hero h1 exceeds 10 characters. The model rephrased "considered" to "kept" and the overflow disappeared. v1.3 codifies both — smaller clamp ceiling, plus a word-length rule in the prompt with concrete substitution examples ("Treatments" → "Care", "Considered" → "Kept").

**8. Hard reference diversification with fail-loud.** When Workshop calls `retrieve_inspiration` to pull 3 references from the vault, the retrieval applies a max-1-per-source-domain filter. If the filtered result has fewer than 3 references (vault not diverse enough yet for this brief), Workshop sends a Telegram message: "Cannot generate kit X — vault needs more diverse references for this brief. Run halted." The kit does NOT ship. Alex either waits for vault to grow more references, or triggers manually with a one-time flag to bypass diversification. Soft warning would let 1:1-clones ship; hard requirement is real defense against the copyright-surface risk that the probe sequence exposed.

**9. Vault-gated rotation in `workshop.py` — Mechanism 2.** Each sub-aesthetic config specifies a `min_exemplar_count` (e.g., ≥2 vault references tagged for that sub-aesthetic). On every cron run, Workshop checks the vault BEFORE picking the next queue item. If the next item's sub-aesthetic doesn't have enough vault exemplars to anchor against, Workshop skips it and tries the next item, looking for a sub-aesthetic with sufficient vault support. If no awwwards sub-aesthetic in queue has enough vault exemplars at this run, Workshop fails loud to Telegram with vault state per sub-aesthetic. This is the second half of "why first non-sun-baked kit won't be ugly" — Mechanism 1 says configs are built from exemplars, Mechanism 2 says a sub-aesthetic doesn't enter active production until vault contains the exemplars to anchor it. Combined: sub-aesthetics validate empirically through vault accumulation, not through guessing. Diversification (Component 8) decides WHICH 3 refs anchor the kit once generation runs; vault-gating decides WHETHER generation runs at all.

## How a typical v1.3 run looks end-to-end

Cron fires Sunday morning. Workshop reads `queue.json`, picks the next kit. Suppose this one is `2026-05-17-acid-tech-saas-tools` with `aesthetic_direction=awwwards`, `sub_aesthetic=acid-tech`.

Vault-gating check runs first. Workshop counts acid-tech-tagged references in the vault. Acid-tech config specifies `min_exemplar_count: 2`; vault has 3 acid-tech refs. Gate passes. (If gate had failed — fewer than 2 acid-tech refs — Workshop would skip this queue item, try the next one, look for any awwwards sub-aesthetic with sufficient vault support. If no item in queue had vault support, Workshop would fail loud to Telegram with vault state per sub-aesthetic, and wait for next cron or manual trigger.)

Workshop loads the acid-tech config from `aesthetic_configs.py` — neon-on-black palette derived from acid-tech exemplar set, fluorescent photography prefix matched to exemplar luminance profile, motion vocabulary catalogued from exemplars' implementations. It calls `retrieve_inspiration` with the brief and the max-1-per-source-domain filter, biased toward acid-tech anchor reference IDs. Qdrant returns 3 references — one Awwwards SOTD, one Dribbble piece, one WP showcase entry, all from different source domains. Workshop proceeds.

Pre-flight: Workshop fetches the GSAP URL from cdnjs, then ScrollTrigger, then SplitType, then Lenis. Computes SHA-512 hashes for each file. Builds the SRI block as exact `<script integrity="sha512-..." crossorigin="anonymous">` strings ready to paste into HTML. If any fetch fails or any hash differs from what's expected, run aborts here with a Telegram message naming the broken library.

`kit_generation` runs. Claude reads the brief, the three diverse references, the pre-computed SRI block, the prompt with anti-1:1-clone instructions and word-length rules. Produces five static files: `index.html`, `services.html`, `contacts.html`, `assets/css/style.css`, `assets/js/main.js`. Returns the bundle.

Workshop parses the produced `index.html` for `--color-bg`. Suppose it's `#0A0A0A` (very dark). Luminance computes to 10 out of 255. Workshop builds the photography prefix: "Photograph in high-key bright register, target mean luminance 180-220, sharp neon highlights, fluorescent ambient — must contrast against dark page background." It patches `generate_kit_images.GENERATION_PROMPT_PREFIX` with this string before image generation runs.

Image generation runs against Gemini. Four images come back. Workshop verifies each has mean luminance differing from `--color-bg` by at least 20 points. If any fails the contrast check, run aborts.

`self_audit_awwwards` runs. The new boolean checks evaluate against the produced kit. The kit passes the checklist if `has_one_primary_cta=true`, `manifesto_headline_present=true`, and so on. Any warnings get logged. The audit is non-deterministic across runs (known limitation — same kit can get different warning counts on different audit calls), so warning count is informational, not a ship gate.

Source-HTML leak scan runs against the three HTML files (no Playwright, just regex on file contents). Word-length verification runs on hero h1. If either finds a real issue, Workshop logs a warning but doesn't fail — failure is reserved for things Workshop can mechanically detect as broken (markup leak, fabricated URL, luminance miss).

Workshop spins up `python -m http.server` on a port in the 8200-8210 range (allocated for Workshop, isolated from existing VPS services — hermes-qdrant, n8n, OpenClaw, NemoClaw, Hermes Agent are all untouched), serves the generated kit as static files locally, then Playwright (browser automation library — runs headless Chromium) loads each page in turn and takes three screenshots — homepage, services, contacts. Screenshots commit to `camelotflows-kits` alongside the kit files. Workshop sends Alex a Telegram message: screenshots, commit URL, audit summary. No Docker, no DDEV, no WordPress install — Workshop produces static kits, deployment to actual WP is downstream work for whoever buys the kit.

Alex looks at the screenshots. Either ships, or doesn't. There's no "regenerate cooler" instruction yet — that's v1.3.1 work.

## Failure modes Workshop handles explicitly

**Vault not diverse enough for the brief.** Hard diversification fails — Workshop halts, sends Telegram message, no kit ships. Alex decides whether to wait for vault to grow, or trigger manually with a one-time `--allow-domain-duplicates` flag.

**CDN library 404 between pre-flight and runtime.** SRI hash mismatch detected at prompt-construction or after. Run aborts with diff showing expected vs actual. Telegram message names the broken library. Most likely fix: bump the library version in `aesthetic_configs.py` and re-run.

**Audit verdict variance.** Same kit can get 5 warnings on one audit call and 7 on a re-run. v1.3 doesn't fix this — it's a property of how Claude generates audit responses. The ship gate is Alex's eyes on screenshots, not the warning count. v1.3 audit serves as a checklist for the model during generation more than as a verdict after.

**Model invents tokens or markup the leak scan misses.** Soft warning, Alex review. Same posture as v1.2.

**Hero h1 still overflows despite word-length cap.** Rare with the 16vw clamp ceiling and the ≤10-char word rule, but post-generation verification catches it. Soft warning, Alex sees the overflow in screenshots.

**No sub-aesthetic in queue has vault support.** Vault-gating fails across all awwwards items in queue. Workshop sends Telegram with vault state per sub-aesthetic ("acid-tech: 1/2, cool-jewel: 0/2, warm-earth: 1/2..."). Alex decides — wait for Scout to grow vault, or manually inject anchor refs to vault for a specific sub-aesthetic, or use override flag to bypass gating, or reshuffle queue to put conversion kits up front. Either way, no kit ships this cycle for awwwards register.

**Anchored sub-aesthetic still produces ugly kit on first cron run.** With Mechanisms 1 and 2 in place, the model has anchored configs and vault-confirmed refs to work from — far better starting position than "abstract mood word + arbitrary retrieval". But model generation remains generative; first run can still land poorly. Mitigation: each first run is its own validation, Alex sees screenshots, iterates the sub-aesthetic config if needed (palette tweak, motion change, exemplar replacement). Full-rotation cadence means next attempt for that sub-aesthetic is several weeks out unless Alex triggers manually. Skip-and-retry logic deferred to v1.3.1.

## What's deferred to v1.3.1+

Iteration commands. Workshop v1.0 plan called for "regenerate but cooler" / "more dramatic hero" as v1.1; never built. Stays deferred. Alex's only iteration mechanism in v1.3.0 is waiting for the next cron run or manual trigger.

Skip-and-retry for failing sub-aesthetics in rotation.

Multi-style-bucket diversification. The current hard filter is by source domain. If a single domain hosts multiple style buckets, that's a coarser filter than ideal — may need finer-grained tagging later.

Audit determinism. Would require running audit at temperature=0 if the `claude --print` CLI exposes that parameter. Needs empirical verification at the VPS, deferred to bootstrap phase.

## Known structural risks at v1.3.0 launch

**Four unvalidated sub-aesthetics with empirical gating.** Sun-baked is the only sub-aesthetic with probe-validated config from the May 10 probe sequence. The other four — acid-tech, cool-jewel, warm-earth, editorial-mid-century — get configs built from exemplar SOTDs during bootstrap Phase 1 (Mechanism 1). They enter active rotation only when vault contains enough anchor references for them (Mechanism 2). Practical implication: at v1.3.0 launch, if vault has acid-tech exemplars but not cool-jewel exemplars, cron rotation runs sun-baked + acid-tech, skips cool-jewel until Scout fills more cool-jewel refs. First production run of each non-sun-baked sub-aesthetic is still its empirical validation — but with anchored config and vault-confirmed refs, not abstract mood + arbitrary retrieval. The risk is reduced significantly vs naive "ship 5 abstract configs and pray", but it's not zero — generation is still generative, and first runs can still surprise.

**Vault size vs vault-gating + hard-diversification.** Vault currently grows ~5 refs/day. At v1.3.0 launch, vault may not contain enough exemplars for all 5 sub-aesthetics yet. Vault-gating (Mechanism 2) will skip sub-aesthetics without exemplars — this is planned behavior, not a bug, but it means rotation cadence will be uneven during weeks 1-3 of v1.3.0 operation. Hard diversification (Component 8) may additionally trigger fail-loud on sub-aesthetics that pass the gate if domain diversity is still thin among their exemplars. First 2-3 weeks will likely run mostly sun-baked + whichever 1-2 sub-aesthetics get vault traction first. Vault grows in parallel; rotation expands as Scout fills exemplars. Manual override flag `--allow-domain-duplicates` and per-run gate-bypass exist for one-off escape hatches.

**Audit verdict variance.** Same kit, different runs of `self_audit_awwwards`, different warning counts. Not a blocker, but worth knowing — warning count is informational, not a quality gate. Screenshots are the gate.

---

End of description draft. Standing by for "годится" or revision requests. Once approved, technical bootstrap follows for VPS Claude execution.
