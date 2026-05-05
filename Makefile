SHELL := /bin/bash
ROOT  := /opt/scout-workshop
VENV  := $(ROOT)/venv
PY    := $(VENV)/bin/python

.DEFAULT_GOAL := help

.PHONY: help verify scout-test workshop-test logs clean-state

help: ## Show available targets
	@echo "Scout-Workshop — make targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""

verify: ## Run all Day 1 verification checks (Qdrant, embedding, Telegram, Firecrawl, screenshot)
	@$(PY) $(ROOT)/scripts/verify_bootstrap.py

scout-test: ## Placeholder — Scout playbook lands Day 2
	@echo "Scout playbook lands Day 2"

workshop-test: ## Placeholder — Workshop playbook lands Day 3
	@echo "Workshop playbook lands Day 3"

logs: ## Tail recent logs (last 100 lines per file)
	@if ls $(ROOT)/logs/*.log >/dev/null 2>&1; then \
		tail -n 100 $(ROOT)/logs/*.log; \
	else \
		echo "No logs yet in $(ROOT)/logs/"; \
	fi

clean-state: ## Clear state/ directory (screenshots + resumability cache)
	@read -r -p "Clear $(ROOT)/state/? This deletes screenshots and resumability state. [y/N] " ans; \
	if [[ "$$ans" == "y" || "$$ans" == "Y" ]]; then \
		rm -rf $(ROOT)/state/* && \
		mkdir -p $(ROOT)/state/screenshots && \
		echo "Cleared."; \
	else \
		echo "Aborted."; \
	fi
