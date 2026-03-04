# FGIP Watch Targets
#
# Purpose:
#   Run agents safely, then emit a dated receipt with:
#   - proposal counts (pending/approved/rejected)
#   - lint results
#   - a quick snapshot of pending proposals
#   - SHA256 hash of the log (for forensic integrity)
#
# Assumes:
#   repo: /home/voidstr3m33/fgip-engine
#   CLI:  python3 -m fgip.cli
#
# Notes:
#   - Agents ONLY write to staging tables.
#   - These targets do NOT auto-accept/promote anything.
#   - Each run appends to receipts/watch/INDEX.jsonl for timeline diffing.

FGIP_DIR ?= /home/voidstr3m33/fgip-engine
FGIP_DB  ?= $(FGIP_DIR)/fgip.db
FGIP     ?= cd $(FGIP_DIR) && python3 -m fgip.cli --db $(FGIP_DB)

# Where we write receipts (date-stamped)
RECEIPTS_DIR ?= $(FGIP_DIR)/receipts/watch
STAMP        := $(shell date -u +"%Y%m%dT%H%M%SZ")
HOST         := $(shell hostname 2>/dev/null || echo unknown)
INDEX        := $(RECEIPTS_DIR)/INDEX.jsonl

.PHONY: fgip-init fgip-load-citations fgip-snapshot fgip-stats fgip-lint
.PHONY: watch-edgar watch-scotus watch-gao watch-fara watch-all

# ---------- Setup ----------

fgip-init:
	@mkdir -p "$(RECEIPTS_DIR)"
	@$(FGIP) init

fgip-load-citations:
	@mkdir -p "$(RECEIPTS_DIR)"
	@$(FGIP) load-citations

# ---------- Quick commands ----------

fgip-stats:
	@$(FGIP) stats

fgip-lint:
	@$(FGIP) lint

fgip-dedupe:
	@python3 "$(FGIP_DIR)/tools/dedupe_edges.py" --db "$(FGIP_DB)"

fgip-dedupe-dry:
	@python3 "$(FGIP_DIR)/tools/dedupe_edges.py" --db "$(FGIP_DB)" --dry-run

# ---------- Snapshot (no agent run) ----------

fgip-snapshot:
	@mkdir -p "$(RECEIPTS_DIR)"
	@set -e; \
	out="$(RECEIPTS_DIR)/snapshot_$(STAMP)_$(HOST).log"; \
	echo "=== FGIP WATCH SNAPSHOT ==="                        >  "$$out"; \
	echo "UTC: $(STAMP)"                                      >> "$$out"; \
	echo "HOST: $(HOST)"                                      >> "$$out"; \
	echo "DB: $(FGIP_DB)"                                     >> "$$out"; \
	echo ""                                                   >> "$$out"; \
	echo "=== AGENT STATUS ==="                               >> "$$out"; \
	$(FGIP) agent status                                      >> "$$out" 2>&1 || true; \
	echo ""                                                   >> "$$out"; \
	echo "=== STAGING PENDING (claims+edges, top 50) ==="     >> "$$out"; \
	$(FGIP) staging pending --limit 50                        >> "$$out" 2>&1 || true; \
	echo ""                                                   >> "$$out"; \
	echo "=== LINT (epistemic integrity) ==="                 >> "$$out"; \
	$(FGIP) lint                                              >> "$$out" 2>&1 || true; \
	sha=$$(sha256sum "$$out" | cut -d' ' -f1); \
	sha256sum "$$out" > "$$out.sha256"; \
	echo "{\"ts\":\"$(STAMP)\",\"host\":\"$(HOST)\",\"type\":\"snapshot\",\"file\":\"$$out\",\"sha256\":\"$$sha\"}" >> "$(INDEX)"; \
	echo "WROTE: $$out"; \
	echo "WROTE: $$out.sha256 ($$sha)"

# ---------- Watch Targets ----------

# Run EDGAR agent once + snapshot
watch-edgar:
	@mkdir -p "$(RECEIPTS_DIR)"
	@set -e; \
	runlog="$(RECEIPTS_DIR)/watch_edgar_$(STAMP)_$(HOST).log"; \
	echo "=== FGIP WATCH: EDGAR ==="                          >  "$$runlog"; \
	echo "UTC: $(STAMP)"                                      >> "$$runlog"; \
	echo "HOST: $(HOST)"                                      >> "$$runlog"; \
	echo "DB: $(FGIP_DB)"                                     >> "$$runlog"; \
	echo ""                                                   >> "$$runlog"; \
	echo "=== RUN AGENT: EDGAR ==="                           >> "$$runlog"; \
	$(FGIP) agent run edgar                                   >> "$$runlog" 2>&1 || true; \
	echo ""                                                   >> "$$runlog"; \
	echo "=== POST-RUN SNAPSHOT ==="                          >> "$$runlog"; \
	$(FGIP) agent status                                      >> "$$runlog" 2>&1 || true; \
	echo ""                                                   >> "$$runlog"; \
	$(FGIP) staging pending --agent edgar --limit 50          >> "$$runlog" 2>&1 || true; \
	echo ""                                                   >> "$$runlog"; \
	$(FGIP) lint                                              >> "$$runlog" 2>&1 || true; \
	sha=$$(sha256sum "$$runlog" | cut -d' ' -f1); \
	sha256sum "$$runlog" > "$$runlog.sha256"; \
	echo "{\"ts\":\"$(STAMP)\",\"host\":\"$(HOST)\",\"type\":\"watch-edgar\",\"file\":\"$$runlog\",\"sha256\":\"$$sha\"}" >> "$(INDEX)"; \
	echo "WROTE: $$runlog"; \
	echo "WROTE: $$runlog.sha256 ($$sha)"

# Run SCOTUS agent once + snapshot
watch-scotus:
	@mkdir -p "$(RECEIPTS_DIR)"
	@set -e; \
	runlog="$(RECEIPTS_DIR)/watch_scotus_$(STAMP)_$(HOST).log"; \
	echo "=== FGIP WATCH: SCOTUS ==="                         >  "$$runlog"; \
	echo "UTC: $(STAMP)"                                      >> "$$runlog"; \
	echo "HOST: $(HOST)"                                      >> "$$runlog"; \
	echo "DB: $(FGIP_DB)"                                     >> "$$runlog"; \
	echo ""                                                   >> "$$runlog"; \
	echo "=== RUN AGENT: SCOTUS ==="                          >> "$$runlog"; \
	$(FGIP) agent run scotus                                  >> "$$runlog" 2>&1 || true; \
	echo ""                                                   >> "$$runlog"; \
	echo "=== POST-RUN SNAPSHOT ==="                          >> "$$runlog"; \
	$(FGIP) agent status                                      >> "$$runlog" 2>&1 || true; \
	echo ""                                                   >> "$$runlog"; \
	$(FGIP) staging pending --agent scotus --limit 50         >> "$$runlog" 2>&1 || true; \
	echo ""                                                   >> "$$runlog"; \
	$(FGIP) lint                                              >> "$$runlog" 2>&1 || true; \
	sha=$$(sha256sum "$$runlog" | cut -d' ' -f1); \
	sha256sum "$$runlog" > "$$runlog.sha256"; \
	echo "{\"ts\":\"$(STAMP)\",\"host\":\"$(HOST)\",\"type\":\"watch-scotus\",\"file\":\"$$runlog\",\"sha256\":\"$$sha\"}" >> "$(INDEX)"; \
	echo "WROTE: $$runlog"; \
	echo "WROTE: $$runlog.sha256 ($$sha)"

# Run GAO agent once + snapshot
watch-gao:
	@mkdir -p "$(RECEIPTS_DIR)"
	@set -e; \
	runlog="$(RECEIPTS_DIR)/watch_gao_$(STAMP)_$(HOST).log"; \
	echo "=== FGIP WATCH: GAO ==="                            >  "$$runlog"; \
	echo "UTC: $(STAMP)"                                      >> "$$runlog"; \
	echo "HOST: $(HOST)"                                      >> "$$runlog"; \
	echo "DB: $(FGIP_DB)"                                     >> "$$runlog"; \
	echo ""                                                   >> "$$runlog"; \
	echo "=== RUN AGENT: GAO ==="                             >> "$$runlog"; \
	$(FGIP) agent run gao                                     >> "$$runlog" 2>&1 || true; \
	echo ""                                                   >> "$$runlog"; \
	echo "=== POST-RUN SNAPSHOT ==="                          >> "$$runlog"; \
	$(FGIP) agent status                                      >> "$$runlog" 2>&1 || true; \
	echo ""                                                   >> "$$runlog"; \
	$(FGIP) staging pending --agent gao --limit 50            >> "$$runlog" 2>&1 || true; \
	echo ""                                                   >> "$$runlog"; \
	$(FGIP) lint                                              >> "$$runlog" 2>&1 || true; \
	sha=$$(sha256sum "$$runlog" | cut -d' ' -f1); \
	sha256sum "$$runlog" > "$$runlog.sha256"; \
	echo "{\"ts\":\"$(STAMP)\",\"host\":\"$(HOST)\",\"type\":\"watch-gao\",\"file\":\"$$runlog\",\"sha256\":\"$$sha\"}" >> "$(INDEX)"; \
	echo "WROTE: $$runlog"; \
	echo "WROTE: $$runlog.sha256 ($$sha)"

# Run FARA agent once + snapshot (Foreign Agents Registration Act - Tier 0)
watch-fara:
	@mkdir -p "$(RECEIPTS_DIR)"
	@set -e; \
	runlog="$(RECEIPTS_DIR)/watch_fara_$(STAMP)_$(HOST).log"; \
	echo "=== FGIP WATCH: FARA ==="                           >  "$$runlog"; \
	echo "UTC: $(STAMP)"                                      >> "$$runlog"; \
	echo "HOST: $(HOST)"                                      >> "$$runlog"; \
	echo "DB: $(FGIP_DB)"                                     >> "$$runlog"; \
	echo ""                                                   >> "$$runlog"; \
	echo "=== RUN AGENT: FARA ==="                            >> "$$runlog"; \
	$(FGIP) agent run fara                                    >> "$$runlog" 2>&1 || true; \
	echo ""                                                   >> "$$runlog"; \
	echo "=== PRELINT (garbage filter) ==="                   >> "$$runlog"; \
	$(FGIP) staging prelint --agent fara                      >> "$$runlog" 2>&1 || true; \
	echo ""                                                   >> "$$runlog"; \
	echo "=== POST-RUN SNAPSHOT ==="                          >> "$$runlog"; \
	$(FGIP) agent status                                      >> "$$runlog" 2>&1 || true; \
	echo ""                                                   >> "$$runlog"; \
	$(FGIP) staging pending --agent fara --limit 50           >> "$$runlog" 2>&1 || true; \
	echo ""                                                   >> "$$runlog"; \
	$(FGIP) lint                                              >> "$$runlog" 2>&1 || true; \
	sha=$$(sha256sum "$$runlog" | cut -d' ' -f1); \
	sha256sum "$$runlog" > "$$runlog.sha256"; \
	echo "{\"ts\":\"$(STAMP)\",\"host\":\"$(HOST)\",\"type\":\"watch-fara\",\"file\":\"$$runlog\",\"sha256\":\"$$sha\"}" >> "$(INDEX)"; \
	echo "WROTE: $$runlog"; \
	echo "WROTE: $$runlog.sha256 ($$sha)"

# Convenience: run all watchers, then a global snapshot
watch-all:
	@$(MAKE) watch-edgar
	@$(MAKE) watch-scotus
	@$(MAKE) watch-gao
	@$(MAKE) watch-fara
	@$(MAKE) fgip-snapshot

# ---------- Timeline / Forensic Helpers ----------

# Show recent watch runs (last 20 lines of INDEX.jsonl)
watch-recent:
	@if [ -f "$(INDEX)" ]; then \
		echo "=== Recent Watch Runs ==="; \
		tail -20 "$(INDEX)" | python3 -c "import sys,json; [print(f\"{json.loads(l)['ts']} {json.loads(l)['type']:15} sha256:{json.loads(l)['sha256'][:16]}...\") for l in sys.stdin]" 2>/dev/null || tail -20 "$(INDEX)"; \
	else \
		echo "No INDEX.jsonl found. Run 'make watch-edgar' first."; \
	fi

# Diff two watch logs by timestamp (usage: make watch-diff T1=20260222T123456Z T2=20260223T010203Z)
watch-diff:
	@if [ -z "$(T1)" ] || [ -z "$(T2)" ]; then \
		echo "Usage: make watch-diff T1=<timestamp1> T2=<timestamp2>"; \
		echo "  Timestamps from 'make watch-recent'"; \
	else \
		f1=$$(grep "$(T1)" "$(INDEX)" | head -1 | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['file'])"); \
		f2=$$(grep "$(T2)" "$(INDEX)" | head -1 | python3 -c "import sys,json; print(json.loads(sys.stdin.read())['file'])"); \
		echo "Diffing:"; \
		echo "  $$f1"; \
		echo "  $$f2"; \
		diff -u "$$f1" "$$f2" || true; \
	fi

# --- Forensic integrity (strong verify with sidecar .sha256 files) ---

# Create sidecar .sha256 file (standard sha256sum format)
.PHONY: watch-hash
watch-hash:
	@set -e; \
	test -n "$(F)" || (echo "Usage: make watch-hash F=/path/to/log" && exit 2); \
	sha256sum "$(F)" > "$(F).sha256"; \
	echo "WROTE: $(F).sha256"; \
	cat "$(F).sha256"

# Verify log against its sidecar .sha256 using sha256sum -c
.PHONY: watch-verify
watch-verify:
	@set -e; \
	test -n "$(F)" || (echo "Usage: make watch-verify F=/path/to/log" && exit 2); \
	test -f "$(F).sha256" || (echo "Missing: $(F).sha256 (run watch-hash first)" && exit 2); \
	cd "$$(dirname "$(F)")" && sha256sum -c "$$(basename "$(F)").sha256"; \
	echo "VERIFIED OK: $(F)"

# Verify all existing files in INDEX.jsonl (skips missing files, prints failures)
.PHONY: watch-verify-index
watch-verify-index:
	@python3 "$(FGIP_DIR)/tools/verify_index.py" "$(INDEX)"

# ---------- Echo UI Gateway ----------

.PHONY: echo-ui echo-ui-dev echo-ui-smoke

# Start Echo Gateway on port 7777
echo-ui:
	ECHO_LLM_BASE_URL=$${ECHO_LLM_BASE_URL:-http://127.0.0.1:11434/v1} \
	ECHO_MODEL=$${ECHO_MODEL:-qwen2.5:latest} \
	python3 -m uvicorn echo_gateway.app:app --host 0.0.0.0 --port 7777

# Start Echo Gateway with hot reload for development
echo-ui-dev:
	ECHO_LLM_BASE_URL=$${ECHO_LLM_BASE_URL:-http://127.0.0.1:11434/v1} \
	ECHO_MODEL=$${ECHO_MODEL:-qwen2.5:latest} \
	python3 -m uvicorn echo_gateway.app:app --host 0.0.0.0 --port 7777 --reload

# Run smoke test for Echo Gateway
echo-ui-smoke:
	@python3 "$(FGIP_DIR)/tools/smoke_echo_ui.py"

# ---------- Echo Runtime (Unified Task Router) ----------

.PHONY: echo-up echo-smoke echo-reset

# Start Echo Runtime with warm LLM, KAT gate, and unified task endpoint
# This is the primary way to run Echo - warm on startup, one /v1/task endpoint
echo-up:
	ECHO_LLM_BASE_URL=$${ECHO_LLM_BASE_URL:-http://127.0.0.1:11434/v1} \
	ECHO_MODEL=$${ECHO_MODEL:-qwen2.5:latest} \
	FGIP_DB_PATH=$${FGIP_DB_PATH:-fgip.db} \
	KAT_MODE=$${KAT_MODE:-trust_cached} \
	python3 -m uvicorn echo_gateway.app:app --host 0.0.0.0 --port 7777

# Run smoke tests for Echo Runtime
echo-smoke:
	@echo "=== Echo Runtime Smoke Test ===" && \
	echo "1. Health check..." && \
	curl -s http://localhost:7777/v1/health | python3 -m json.tool && \
	echo "" && \
	echo "2. Chat task..." && \
	curl -s -X POST http://localhost:7777/v1/task \
		-H "Content-Type: application/json" \
		-d '{"task_type": "chat", "payload": {"messages": [{"role": "user", "content": "ping"}]}}' \
		| python3 -m json.tool && \
	echo "" && \
	echo "=== Smoke Test Complete ==="

# Reset Echo state (clear KAT cache, restart)
echo-reset:
	@echo "Resetting Echo state..." && \
	curl -s http://localhost:7777/v1/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Status: {d.get(\"status\")}'); print(f'Warmed: {d.get(\"warmed\")}')"

# ---------- CDNA Server (OpenAI-compatible inference) ----------

.PHONY: cdna-up cdna-health echo-up-cdna

# Start CDNA server on port 7778
cdna-up:
	python3 -m uvicorn cdna_server.app:app --host 0.0.0.0 --port 7778

# Check CDNA server health
cdna-health:
	@curl -s http://localhost:7778/v1/health | python3 -m json.tool

# Start Echo with CDNA backend instead of Ollama
echo-up-cdna:
	ECHO_LLM_BASE_URL=http://127.0.0.1:7778/v1 \
	ECHO_MODEL=qwen2.5:3b-cdna-stub \
	FGIP_DB_PATH=$${FGIP_DB_PATH:-fgip.db} \
	KAT_MODE=$${KAT_MODE:-trust_cached} \
	python3 -m uvicorn echo_gateway.app:app --host 0.0.0.0 --port 7777

# Full CDNA smoke test: start both servers, verify routing
cdna-smoke:
	@echo "=== CDNA Smoke Test ===" && \
	echo "1. CDNA health..." && \
	curl -s http://localhost:7778/v1/health | python3 -m json.tool && \
	echo "" && \
	echo "2. Echo health (should show cdna model)..." && \
	curl -s http://localhost:7777/v1/health | python3 -m json.tool && \
	echo "" && \
	echo "3. Chat via CDNA..." && \
	curl -s -X POST http://localhost:7777/v1/task \
		-H "Content-Type: application/json" \
		-d '{"task_type": "chat", "payload": {"messages": [{"role": "user", "content": "ping"}]}}' \
		| python3 -m json.tool && \
	echo "" && \
	echo "=== Smoke Test Complete (check router_path in receipt) ==="

# ---------- CDNA Stage 1 Verification ----------

.PHONY: cdna-verify-stage1 cdna-forward-test

# Run Stage 1 acceptance gate: CDNA forward must match HF oracle
# Creates receipt in receipts/cdna_stage1/
cdna-verify-stage1:
	python3 cdna_server/verify_stage1.py --prompt "Paris is the capital of"

# Quick CDNA forward pass test (no oracle comparison)
cdna-forward-test:
	python3 -c "from cdna_server import cdna_forward_topk; topk, r = cdna_forward_topk('Hello'); print(f'Status: {r.status}'); [print(f'  {i+1}. [{t[0]}] {t[2]!r}') for i,t in enumerate(topk)]"

# Strict Stage 1 verification (for uncompressed weights)
cdna-verify-stage1-strict:
	python3 cdna_server/verify_stage1.py --prompt "Paris is the capital of" --strict

# ---------- CDNA Stage 2 Verification ----------

.PHONY: cdna-verify-stage2 cdna-generate-test cdna-up-real

# Run Stage 2 acceptance gate: generation + KV cache + API
# Creates receipt in receipts/cdna_stage2/
cdna-verify-stage2:
	python3 cdna_server/verify_stage2.py --prompt "Paris is the capital of" --tokens 32

# Fast Stage 2 verification (1 token, no determinism check)
cdna-verify-stage2-fast:
	CDNA_USE_TENSOR_CACHE=1 python3 cdna_server/verify_stage2.py --fast

# Quick generation test
cdna-generate-test:
	python3 -c "from cdna_server import generate; text, r = generate('Hello', max_tokens=8); print(f'Status: {r.status}'); print(f'Generated: {text!r}'); print(f'Tokens/sec: {r.tokens_per_sec:.2f}')"

# Start CDNA server with real inference (not stub)
# Stage 3: Tensor cache + C++ kernel with AVX2
cdna-up-real:
	CDNA_MODE=real \
	CDNA_USE_TENSOR_CACHE=1 \
	HELIX_USE_CPP_KERNEL=1 \
	HELIX_USE_FUSED_MATMUL=1 \
	OMP_NUM_THREADS=$$(nproc) \
	OPENBLAS_NUM_THREADS=$$(nproc) \
	python3 -m uvicorn cdna_server.app:app --host 0.0.0.0 --port 7778

# Start Echo with real CDNA backend
# Stage 3: Increased timeout (600s) for slow CDNA inference
echo-up-cdna-real:
	ECHO_LLM_BASE_URL=http://127.0.0.1:7778/v1 \
	ECHO_MODEL=mistral-7b-cdna \
	ECHO_LLM_BACKEND=cdna \
	ECHO_LLM_TIMEOUT=600 \
	FGIP_DB_PATH=$${FGIP_DB_PATH:-fgip.db} \
	KAT_MODE=$${KAT_MODE:-trust_cached} \
	python3 -m uvicorn echo_gateway.app:app --host 0.0.0.0 --port 7777
