.PHONY: install dev test check lint up down brains schema seed run mcp api

install:          ## Install runtime deps
	pip install -e .

dev:              ## Install with dev extras
	pip install -e ".[dev]"

test:             ## Run offline smoke tests
	pytest -q

check:            ## Live health-check of all system components (DBs, LLM, search)
	python scripts/healthcheck.py $(ARGS)

lint:             ## Ruff + mypy
	ruff check src tests
	mypy src

up:               ## Bring up the CPU stack (DBs + orchestrator + searxng)
	docker compose up -d --build

brains:           ## Bring up GPU model servers too (needs nvidia runtime)
	docker compose --profile gpu up -d --build

down:
	docker compose down

schema:           ## Apply Neo4j constraints + vector index
	docker compose exec -T neo4j cypher-shell -u neo4j -p $${NEO4J_PASSWORD:-please-change-me} < infra/neo4j/schema.cypher

seed:             ## Load demo graph data
	docker compose exec -T neo4j cypher-shell -u neo4j -p $${NEO4J_PASSWORD:-please-change-me} < infra/neo4j/seed.cypher

run:              ## Run the pipeline on the sample CV via CLI
	scholar run examples/sample_cv.txt --query "fully funded PhD, Germany or Netherlands, ML"

mcp:              ## Start the MCP server (stdio)
	python -m scholar.mcp_server

api:              ## Run the API locally (no docker)
	uvicorn scholar.api.main:app --reload --port 8080
