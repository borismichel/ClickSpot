# Clickspot developer shortcuts.
# Run inside the project venv: `source .venv/bin/activate`.

.PHONY: help seed seed-bronze

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

seed: ## Load the offline demo warehouse (CSV -> bronze -> silver -> gold -> anon). No HUBSPOT_TOKEN needed.
	python scripts/seed.py

seed-bronze: ## Load only the bronze layer from the demo CSV (skip silver/gold/anon transforms).
	python scripts/seed.py --bronze-only
