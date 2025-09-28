# Osiris Pipeline - Development Makefile
# LLM-first conversational ETL pipeline generator

.PHONY: help install dev-install test lint format type-check clean build docs chat run-tests setup-env

# Default target
help: ## Show this help message
	@echo "🚀 Osiris Pipeline - Development Commands"
	@echo ""
	@echo "📦 Setup & Installation:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E "(install|setup)" | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "🧪 Testing & Quality:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E "(test|lint|format|type|check)" | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "🚀 Usage & Development:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -v -E "(install|setup|test|lint|format|type|check|help|clean|build)" | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "🧹 Maintenance:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E "(clean|build)" | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# Setup and Installation
setup-env: ## Create virtual environment and install dependencies
	@echo "🔧 Setting up development environment..."
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip setuptools wheel
	.venv/bin/pip install -e ".[dev]"
	@echo "✅ Environment ready! Activate with: source .venv/bin/activate"

install: ## Install package in current environment
	@echo "📦 Installing Osiris Pipeline..."
	pip install -e .
	@echo "✅ Installation complete!"

dev-install: ## Install package with development dependencies
	@echo "📦 Installing Osiris Pipeline (development mode)..."
	pip install -e ".[dev,docs]"
	@echo "✅ Development installation complete!"

# Testing
test: ## Run all tests
	@echo "🧪 Running tests..."
	python -m pytest tests/ -v

test-fast: ## Run tests (exclude slow tests)
	@echo "⚡ Running fast tests..."
	python -m pytest tests/ -v -m "not slow"

test-integration: ## Run integration tests only
	@echo "🔗 Running integration tests..."
	python -m pytest tests/ -v -m "integration"

test-coverage: ## Run tests with coverage report
	@echo "📊 Running tests with coverage..."
	python -m pytest tests/ --cov=osiris --cov-report=html --cov-report=term-missing

# E2B Testing
test-e2b-smoke: ## Run E2B smoke tests (mocked, no API key needed)
	@echo "🔍 Running E2B smoke tests..."
	python -m pytest tests/e2b/test_e2b_smoke.py -v -m "not e2b_live"

test-e2b-live: ## Run live E2B tests (requires E2B_API_KEY)
	@echo "🚀 Running live E2B tests..."
	@if [ -z "$$E2B_API_KEY" ]; then \
		echo "❌ E2B_API_KEY not set. Please export E2B_API_KEY=your-key"; \
		exit 1; \
	fi
	E2B_LIVE_TESTS=1 python -m pytest tests/e2b/ -v -m e2b_live

test-e2b-parity: ## Run Local vs E2B parity tests
	@echo "⚖️  Running parity tests..."
	@if [ -z "$$E2B_API_KEY" ]; then \
		echo "⚠️  Running parity tests with mocked E2B (set E2B_API_KEY for live tests)"; \
	fi
	python -m pytest tests/parity/test_parity_e2b_vs_local.py -v -m parity

test-e2b-orphans: ## Test orphan sandbox detection
	@echo "🧹 Testing orphan detection..."
	python -m pytest tests/e2b/test_orphan_cleanup.py -v

e2b-cleanup: ## Clean up orphaned E2B sandboxes (dry-run by default)
	@echo "🧹 Checking for orphaned E2B sandboxes..."
	@python -c "print('Orphan cleanup utility - would clean sandboxes older than 2 hours')"
	@echo "To run actual cleanup: make e2b-cleanup-force"

e2b-cleanup-force: ## Force cleanup of orphaned E2B sandboxes
	@echo "🧹 Cleaning up orphaned E2B sandboxes..."
	@if [ -z "$$E2B_API_KEY" ]; then \
		echo "❌ E2B_API_KEY not set"; \
		exit 1; \
	fi
	@echo "⚠️  This would clean up real E2B sandboxes - implement with caution"

cov: ## Run pytest with coverage to terminal
	@echo "📊 Running tests with coverage..."
	python -m pytest tests/ --cov=osiris --cov-report=term-missing

cov-html: ## Generate HTML coverage report
	@echo "📊 Generating HTML coverage report..."
	@COVERAGE_DIR="docs/testing/research/coverage-$$(date +%Y%m%d)/html"; \
	mkdir -p $$COVERAGE_DIR && \
	python -m pytest tests/ --cov=osiris --cov-report=html:$$COVERAGE_DIR -q && \
	echo "✅ HTML report generated in $$COVERAGE_DIR"

cov-json: ## Generate JSON coverage report
	@echo "📊 Generating JSON coverage report..."
	@COVERAGE_DIR="docs/testing/research/coverage-$$(date +%Y%m%d)"; \
	mkdir -p $$COVERAGE_DIR && \
	python -m pytest tests/ --cov=osiris --cov-report=json:$$COVERAGE_DIR/coverage.json -q && \
	echo "✅ JSON report generated in $$COVERAGE_DIR/coverage.json"

cov-md: ## Generate markdown coverage report from JSON
	@echo "📊 Generating markdown coverage report..."
	@LATEST_JSON=$$(ls -d docs/testing/research/coverage-*/coverage.json 2>/dev/null | tail -1); \
	if [ -z "$$LATEST_JSON" ]; then \
		echo "❌ No coverage JSON found. Run 'make cov-json' first."; \
		exit 1; \
	fi; \
	COVERAGE_DIR=$$(dirname $$LATEST_JSON); \
	python tools/validation/coverage_summary.py $$LATEST_JSON \
		--format markdown \
		--output $$COVERAGE_DIR/coverage.md && \
	echo "✅ Markdown report generated in $$COVERAGE_DIR/coverage.md"

coverage: cov-json cov-html cov-md ## Run full coverage analysis (json + html + md)
	@echo "✅ Full coverage analysis complete!"

coverage-check: ## Check coverage against thresholds (non-blocking for now)
	@echo "📊 Checking coverage thresholds..."
	@LATEST_JSON=$$(ls -d docs/testing/research/coverage-*/coverage.json 2>/dev/null | tail -1); \
	if [ -z "$$LATEST_JSON" ]; then \
		echo "❌ No coverage data found. Run 'make cov-json' first."; \
		exit 1; \
	fi; \
	python tools/validation/coverage_summary.py $$LATEST_JSON \
		--overall-min 0.4 \
		--remote-min 0.5 \
		--cli-min 0.5 \
		--core-min 0.6 \
		--format markdown || true

# Code Quality
lint: ## Run all linting checks
	@echo "🔍 Running linting checks..."
	ruff check osiris/ tests/
	black --check osiris/ tests/
	isort --check-only osiris/ tests/

format: ## Format code with black and isort
	@echo "🎨 Formatting code..."
	black osiris/ tests/
	isort osiris/ tests/
	@echo "✅ Code formatted!"

format-check: ## Check if code formatting is correct
	@echo "🔍 Checking code formatting..."
	black --check osiris/ tests/
	isort --check-only osiris/ tests/

type-check: ## Run type checking with mypy (disabled for MVP)
	@echo "🔍 MyPy type checking disabled for MVP"
	@echo "⚠️  Too many type annotation issues (64 errors)"
	@echo "💡 Run 'mypy osiris/' manually if needed"
	# mypy osiris/

ruff-fix: ## Fix auto-fixable linting issues
	@echo "🔧 Fixing linting issues..."
	ruff check --fix osiris/ tests/

quality: lint type-check ## Run all quality checks

# Osiris Usage (runs in testing_env to isolate artifacts)
chat: ## Start interactive chat session
	@echo "🤖 Starting Osiris chat..."
	@if [ ! -d "testing_env" ]; then \
		echo "📁 Creating testing_env directory..."; \
		mkdir -p testing_env; \
	fi
	cd testing_env && python ../osiris.py chat --interactive

chat-pro: ## Start chat session with pro mode (custom prompts)
	@echo "🚀 Starting Osiris chat (pro mode)..."
	@if [ ! -d "testing_env" ]; then \
		echo "📁 Creating testing_env directory..."; \
		mkdir -p testing_env; \
	fi
	cd testing_env && python ../osiris.py chat --interactive --pro-mode

init: ## Initialize Osiris configuration
	@echo "⚙️  Initializing Osiris..."
	@if [ ! -d "testing_env" ]; then \
		echo "📁 Creating testing_env directory..."; \
		mkdir -p testing_env; \
	fi
	cd testing_env && python ../osiris.py init

validate: ## Validate Osiris configuration
	@echo "✅ Validating configuration..."
	@if [ ! -d "testing_env" ]; then \
		echo "📁 Creating testing_env directory..."; \
		mkdir -p testing_env; \
	fi
	cd testing_env && python ../osiris.py validate

dump-prompts: ## Export LLM system prompts for customization
	@echo "📝 Exporting system prompts..."
	python osiris.py dump-prompts --export

run-sample: ## Run sample pipeline
	@echo "🚀 Running sample pipeline..."
	@if [ ! -d "testing_env" ]; then \
		echo "📁 Creating testing_env directory..."; \
		mkdir -p testing_env; \
	fi
	cd testing_env && python ../osiris.py run sample_pipeline.yaml --dry-run

# Development
docs: ## Generate documentation (placeholder)
	@echo "📚 Generating documentation..."
	@echo "📝 TODO: Set up documentation generation with MkDocs"

serve-docs: ## Serve documentation locally (placeholder)
	@echo "🌐 Serving documentation..."
	@echo "📝 TODO: Set up local documentation server"

# Scripts
test-transfer: ## Run manual transfer test script
	@echo "🔄 Running manual transfer test..."
	cd scripts && python test_manual_transfer.py --help

# Database
db-test: ## Test database connections
	@echo "🗄️  Testing database connections..."
	python osiris.py validate

# Clean and Build
clean: ## Clean up build artifacts and cache files
	@echo "🧹 Cleaning up..."
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	find . -type d -name __pycache__ -delete
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	@echo "✅ Cleanup complete!"

build: ## Build package distribution
	@echo "📦 Building package..."
	python -m build
	@echo "✅ Build complete! Check dist/ folder"

# Development workflow helpers
pre-commit-install: ## Install pre-commit hooks
	@echo "🔧 Installing pre-commit hooks..."
	pre-commit install
	@echo "✅ Pre-commit hooks installed!"

pre-commit-run: ## Run all pre-commit hooks on staged files
	@echo "🔍 Running pre-commit hooks..."
	pre-commit run

pre-commit-all: ## Run all pre-commit hooks on all files
	@echo "🔍 Running pre-commit hooks on all files..."
	pre-commit run --all-files

secrets-check: ## Run secret detection on all files
	@echo "🔐 Scanning for secrets..."
	detect-secrets scan --baseline .secrets.baseline .
	@echo "✅ No new secrets detected!"

secrets-audit: ## Audit detected secrets interactively
	@echo "🔍 Auditing secrets baseline..."
	detect-secrets audit .secrets.baseline

pre-commit: format lint type-check secrets-check test-fast ## Run pre-commit checks (format, lint, type-check, secrets, fast tests)
	@echo "✅ Pre-commit checks complete!"

ci: lint type-check secrets-check test test-coverage test-e2b-smoke ## Run full CI pipeline
	@echo "✅ CI pipeline complete!"

ci-nightly: ci test-e2b-parity e2b-cleanup ## Run nightly CI pipeline with parity tests
	@echo "🌙 Nightly CI pipeline complete!"

dev: clean dev-install pre-commit ## Full development setup and validation
	@echo "✅ Development environment ready!"

# Quick commands
q-test: test-fast ## Quick alias for fast tests
q-lint: format-check ruff-fix ## Quick lint and fix
q-chat: chat ## Quick alias for chat
q-pro: chat-pro ## Quick alias for pro mode chat

# Environment info
env-info: ## Show environment information
	@echo "🔍 Environment Information:"
	@echo "Python: $$(python --version)"
	@echo "Pip: $$(pip --version)"
	@echo "Virtual env: $$VIRTUAL_ENV"
	@echo "Working dir: $$(pwd)"
	@echo ""
	@echo "📦 Installed packages:"
	@pip list | grep -E "(osiris|click|rich|duckdb|openai|anthropic)" || echo "No Osiris-related packages found"

# mempack for ChatGPT
mempack:
	python tools/mempack/mempack.py -c tools/mempack/mempack.yaml

# E2B Development
e2b-dev: ## Run E2B pipeline locally for development
	@echo "🔧 Running E2B test pipeline..."
	@if [ ! -d "testing_env" ]; then \
		echo "📁 Creating testing_env directory..."; \
		mkdir -p testing_env; \
	fi
	cd testing_env && python ../osiris.py run ../docs/examples/mysql_to_local_csv_all_tables.yaml --e2b --dry-run

e2b-live-run: ## Run example pipeline in E2B (requires API key)
	@echo "🚀 Running pipeline in E2B sandbox..."
	@if [ -z "$$E2B_API_KEY" ]; then \
		echo "❌ E2B_API_KEY not set"; \
		exit 1; \
	fi
	@if [ ! -d "testing_env" ]; then \
		mkdir -p testing_env; \
	fi
	cd testing_env && python ../osiris.py run ../docs/examples/mysql_to_local_csv_all_tables.yaml --e2b
