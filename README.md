# Scout-Workshop

Two-system autonomous design template generator running on the Hostinger VPS (`srv1420550`). Scout (Day 2) gathers design references and wisdom into a versioned vault and Qdrant index. Workshop (Day 3) synthesizes a brief, plans, audits, and ships a WordPress block-theme template with screenshots delivered to Telegram.

## Status

- Day 1 — foundation (this checkpoint): ✓ shipped
- Day 2 — Scout playbook + Anthropic Routine: pending
- Day 3 — Workshop build loop + DDEV preview: pending

## Directory layout

```
/opt/scout-workshop/
├── .env                       # secrets, mode 600 — never committed
├── .env.example               # template
├── .gitignore
├── Makefile                   # `make help` for targets
├── README.md                  # this file
├── logs/                      # bootstrap-act.log, day-1-bootstrap-report.md
├── scripts/
│   ├── scout_lib.py           # shared helpers (embed, scrape, Qdrant, Telegram)
│   └── verify_bootstrap.py    # Day 1 + ongoing E2E checks
├── skills/                    # Claude Code skills, including workshop-build.md (Day 3)
├── state/
│   └── screenshots/           # cached page captures, sha256-of-url.png
├── venv/                      # Python virtual environment
└── vault/                     # git-versioned knowledge base — separate GitHub repo
    ├── README.md
    ├── references/{awwwards,dribbble,wordpress-showcase,framer-showcase}/
    ├── techniques/
    ├── wisdom/                # YouTube wisdom syntheses
    ├── production-sites/      # client / portfolio site teardowns
    └── templates/{in-progress,completed}/
```

## Architecture (compute split)

- **Scout** runs as an Anthropic Routine on the Anthropic cloud, scheduled daily at 06:00 UTC. It reaches the VPS over Tailscale (`100.110.49.44`) to read/write Qdrant and to commit/push the vault repo. Subscription auth (Max 20×); no API key.
- **Workshop** runs locally on the VPS via `claude --print "$(cat /opt/scout-workshop/skills/workshop-build.md)"`, triggered by cron. Subscription auth.
- **OpenRouter** is used only for paid auxiliary calls: Gemini Embedding 2 Preview ($0.20/M tokens, multimodal, 1536 dim) and Cohere Rerank 4 Pro ($0.0025/search). Estimated combined cost: $2–4/month.

## Vault

Git-versioned at `vault/`. Remote: `git@github.com:Xander1993/scout-workshop-vault.git` (private). GitHub is source of truth; Syncthing mirroring to laptop is optional. Auth via dedicated SSH key `~/.ssh/scout_workshop_ed25519`.

## Running things manually

```bash
# Activate venv (or call binaries directly via venv/bin/...)
source /opt/scout-workshop/venv/bin/activate

# Run all verification checks
make verify

# Tail logs
make logs

# Clear cached state (with confirmation)
make clean-state

# Drop into a Python REPL with scout_lib loaded
python -c "import sys; sys.path.insert(0,'scripts'); import scout_lib as sl; \
           print(sl.embed('hello')[:5])"
```

## Debugging

- Bootstrap log: `logs/bootstrap-act.log`
- Verification report: `logs/day-1-bootstrap-report.md`
- Qdrant health: `curl -fsS http://localhost:6333/collections`
- Existing collections that must remain untouched: `hermes_knowledge`, `dreamscape_studio`
- Existing Docker containers that must remain untouched: `hermes-qdrant-vps`, `n8n-n8n-1`, `openclaw-garagedoors`, `hermes-gateway-vps`, plus the OpenClaw memory archive, browserless, whisper-stt, comfyui-callback, ollama, proxy-app stack

## Day 2 + Day 3 plans

Placeholders — drafted in separate conversations and committed to `skills/scout-playbook.md` and `skills/workshop-build.md` respectively.
