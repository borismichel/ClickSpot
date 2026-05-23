# Clickspot developer shortcuts.
# Run inside the project venv: `source .venv/bin/activate`.

.PHONY: help bootstrap seed seed-bronze clickhouse clickhouse-stop

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

bootstrap: ## Install Python/frontend deps and local ClickHouse without Docker.
	scripts/bootstrap.sh

seed: ## Load the offline demo warehouse (CSV -> bronze -> silver -> gold -> anon). No HUBSPOT_TOKEN needed.
	python scripts/seed.py

seed-bronze: ## Load only the bronze layer from the demo CSV (skip silver/gold/anon transforms).
	python scripts/seed.py --bronze-only

clickhouse: ## Start the local Docker-free ClickHouse runtime.
	scripts/clickhouse-local.sh start

clickhouse-stop: ## Stop the local Docker-free ClickHouse runtime.
	scripts/clickhouse-local.sh stop
