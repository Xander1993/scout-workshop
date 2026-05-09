# Workshop — Architecture Decision Records

Decisions made during Workshop bootstrap. Each ADR is short on purpose. If you find yourself disagreeing, write a new ADR superseding the old one — do not edit history.

---

## ADR-1: Reuse `scout_lib.rerank()` instead of installing the Cohere SDK

**Context:** Workshop's retrieval step (top-20 → top-8) needs Cohere Rerank 4 Pro. Two paths exist: (a) `pip install cohere` with a separate Cohere API key, or (b) reuse `scout_lib.rerank()` which already calls `https://openrouter.ai/api/v1/rerank` via the existing `OPENROUTER_API_KEY`.

**Decision:** Workshop imports `from scout_lib import rerank`. Do not install the `cohere` PyPI package. Do not provision a separate Cohere API key.

**Consequences:** One auth path, one billing source (OpenRouter). Workshop and Scout share rerank behavior and bug fixes. If Cohere model availability on OpenRouter changes, both systems break together — acceptable given OpenRouter is already a hard dependency.

---

## ADR-2: Workshop systemd units live in `/opt/scout-workshop/systemd/` as source-of-truth

**Context:** Existing Scout units (`scout.service`, `scout.timer`, `scout-ingest.*`, `scout-budget-reset.*`) live only as root-owned copies in `/etc/systemd/system/`, with no in-repo source. That makes them un-versioned and hard to review.

**Decision:** Workshop units (`workshop.service`, `workshop.timer`, `workshop-manual.service`, `reaction-poller.service`, `reaction-poller.timer`) live in `/opt/scout-workshop/systemd/` and are deployed to `/etc/systemd/system/` via `sudo cp` + `daemon-reload`. Scout's existing units are NOT migrated — that is separate, out-of-scope work.

**Consequences:** Workshop units are versioned and PR-reviewable. Mixed convention with Scout is accepted as transitional. A future task can retrofit Scout if desired.

---

## ADR-3: Cron schedule fixed at `Sun *-*-* 01:00:00 UTC` — accept ±1hr DST drift

**Context:** Goal is "Sunday 03:00 Moldova time." Moldova observes EET/EEST (UTC+2 / UTC+3), so the correct UTC offset shifts twice yearly. Implementing DST switching adds complexity for marginal benefit.

**Decision:** Use `OnCalendar=Sun *-*-* 01:00:00 UTC` for `workshop.timer`. No DST-aware logic. Run lands at 03:00 Moldova in winter, 04:00 Moldova in summer.

**Consequences:** ±1 hr local-time drift twice a year, accepted. Anyone who needs exact local time can edit the timer manually at the DST boundary. Avoids fragile timezone math and a dependency on `OnCalendar=...local`-style behavior under systemd.

---

## ADR-4: `workshop.service` sets `MemoryMax=4G` — OOM fails loud, no swap fallback

**Context:** VPS has 15 GB RAM and **0 B swap**. A Workshop run runs `claude --print` (Opus 4.7), `python -m http.server`, and Playwright Chromium concurrently alongside ongoing Scout / Hermes / OpenClaw load. Without a cap, an OOM thrash could destabilize unrelated services before the kernel kills anything.

**Decision:** `workshop.service` declares `MemoryMax=4G`. If Workshop exceeds 4 GB, systemd kills the unit with a clear OOM signal in the journal. No retry. Alex investigates root cause.

**Consequences:** Failures are localized, observable, and root-cause-able instead of silent thrashing. 4 GB is generous for the expected workload; if real runs prove it tight, the cap is one config edit away.

---

## ADR-5: Reaction poller is gated on a getUpdates-collision audit (Phase 2 prerequisite)

**Context:** Telegram Bot API allows only **one** active `getUpdates` consumer per bot token. Scout and Workshop share `TELEGRAM_BOT_TOKEN`. If Scout already polls (cron loop, daemon, or webhook), adding a Workshop reaction poller silently breaks one or both.

**Decision:** Before implementing the reaction poller in Phase 2, grep `/opt/scout-workshop/scripts/` for `getUpdates`, `update_id`, polling loops, or webhook setup. If any hit is found, halt Phase 2 reaction-poller work and report — the collision must be resolved first (e.g., switch one consumer to webhook, or merge into a single poller). Other Phase 2 work (kit pipeline, audit, screenshots, delivery) is unaffected and proceeds.

**Consequences:** No silent breakage of Scout's Telegram path. Reaction logging may ship later than the rest of Phase 2 if a collision exists; v1.0 spec already treats reactions as log-only with no behavior coupling, so deferral is low-cost.

---

## ADR-6: Two distinct Google API quota pools

**Context:** Workshop touches two different Google APIs with separate quotas:
- Vertex AI (`aiplatform.googleapis.com`): used by `scout_lib` for text embeddings via `gemini-embedding-2-preview`, called from the `retrieve_inspiration` phase
- AI Studio (`generativelanguage.googleapis.com`): used by `generate_kit_images` for image generation via `gemini-3.1-flash-image-preview` (Nano Banana 2)

Despite shared "Gemini" branding, these are separate quota pools. Embedding quota exhaustion does NOT affect image generation and vice versa. This was discovered concretely on 2026-05-09 when the natural-organic kit attempt died at `retrieve_inspiration` with `RESOURCE_EXHAUSTED` on the embedding API while the image-gen API simultaneously continued returning HTTP 200 to `generate_kit_images` self-tests.

**Decision:** Treat them as independent failure modes. Each has its own `RuntimeError` path with distinct Telegram alert messaging. Robustness wrappers in `workshop.py main()` catch each phase separately so the operator alert names which API specifically tripped.

**Consequences:** When debugging quota issues, check which API specifically. When planning daily run capacity, embedding limits constrain how many distinct vertical/aesthetic combinations can run per day; image limits constrain how many images per kit. They scale independently — running 4 kits exhausts embeddings by 4 query calls but the image-gen pool by ~4 × 13–22 image calls. Future capacity work (e.g., paid quota uplift) must be planned per-pool, not globally.
