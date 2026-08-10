# Osiris Pipeline - Development Makefile
# Records an agent's conversation with a third-party system, freezes it into a
# fingerprinted plan, and replays that plan deterministically.

.PHONY: help setup-env install dev-install \
	test test-coverage cov cov-html cov-json coverage \
	fmt lint security quality precommit \
	commit-wip commit-emergency \
	docs serve-docs \
	clean build check-dist upload-test upload-pypi \
	pre-commit pre-commit-install pre-commit-run pre-commit-all \
	secrets-check secrets-audit \
	ci dev env-info

# Default target
help: ## Show this help message
	@echo "🚀 Osiris Pipeline - Development Commands"
	@echo ""
	@echo "📦 Setup & Installation:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E "(install|setup)" | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "🧪 Testing & Quality:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -E "(test|lint|format|check|cov|security)" | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "🚀 Usage & Development:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | grep -v -E "(install|setup|test|lint|format|check|cov|security|help|clean|build)" | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
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
# One target, the whole suite, no marker selection. A gate that can be narrowed
# by a selector is a gate that will be narrowed until it stops catching anything.
test: ## Run the whole test suite
	python -m pytest tests/ -q

test-coverage: ## Run tests with coverage report (HTML + terminal)
	@echo "📊 Running tests with coverage..."
	python -m pytest tests/ --cov=osiris --cov-report=html --cov-report=term-missing

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

coverage: cov-json cov-html ## Run full coverage analysis (json + html)
	@echo "✅ Full coverage analysis complete!"

# Code Quality
fmt: ## Auto-format code with Black, isort, and Ruff
	@echo "🎨 Auto-formatting code..."
	black --line-length=120 .
	isort --profile=black --line-length=120 .
	ruff check --fix --unsafe-fixes .
	@echo "✅ Code formatted!"

lint: ## Run all linting checks (strict, no auto-fix)
	@echo "🔍 Running strict linting checks..."
	ruff check .
	black --check --line-length=120 .
	isort --check-only --profile=black --line-length=120 .

security: ## Run Bandit security checks
	@echo "🛡️  Running security checks..."
	bandit -r osiris -c bandit.yaml -q

quality: lint security ## Run all quality checks

precommit: ## Install and run pre-commit hooks
	@echo "🔧 Setting up and running pre-commit hooks..."
	pre-commit install
	pre-commit autoupdate
	pre-commit run --all-files

commit-wip: ## Commit with WIP message, skipping slower checks
	@echo "💾 Committing WIP changes..."
	SKIP=ruff,bandit git commit -m "WIP: $${msg:-work in progress}"

commit-emergency: ## Emergency commit, skip all checks (use sparingly!)
	@echo "🚨 Emergency commit (skipping all checks)..."
	git commit --no-verify -m "$${msg:-emergency fix}"

# Development
docs: ## Generate documentation (placeholder)
	@echo "📚 Generating documentation..."
	@echo "📝 TODO: Set up documentation generation with MkDocs"

serve-docs: ## Serve documentation locally (placeholder)
	@echo "🌐 Serving documentation..."
	@echo "📝 TODO: Set up local documentation server"

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

check-dist: ## Check distribution packages with twine
	@echo "🔍 Checking distribution packages..."
	@if [ ! -d "dist" ] || [ -z "$$(ls -A dist)" ]; then \
		echo "❌ No distribution files found. Run 'make build' first."; \
		exit 1; \
	fi
	twine check dist/*
	@echo "✅ Distribution check complete!"

upload-test: clean build check-dist ## Upload to TestPyPI
	@echo "🧪 Uploading to TestPyPI..."
	@echo "⚠️  This will publish to TestPyPI (https://test.pypi.org)"
	twine upload --repository testpypi dist/*
	@echo "✅ Upload to TestPyPI complete!"
	@echo "📝 Test installation with:"
	@echo "   pip install --index-url https://test.pypi.org/simple/ osiris-pipeline"

upload-pypi: clean build check-dist ## Upload to PyPI (PRODUCTION)
	@echo "🚀 Uploading to PyPI..."
	@echo "⚠️⚠️⚠️  THIS WILL PUBLISH TO PRODUCTION PyPI! ⚠️⚠️⚠️"
	@echo ""
	@read -p "Are you ABSOLUTELY SURE you want to publish to PyPI? Type 'yes' to confirm: " confirm; \
	if [ "$$confirm" != "yes" ]; then \
		echo "❌ Upload cancelled."; \
		exit 1; \
	fi
	twine upload dist/*
	@echo "✅ Upload to PyPI complete!"
	@echo "📝 Users can now install with:"
	@echo "   pip install osiris-pipeline"
	@echo "   uvx osiris-pipeline init"

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

pre-commit: fmt lint security test ## Run pre-commit checks (format, lint, security, tests)
	@echo "✅ Pre-commit checks complete!"

ci: lint security test ## Run full CI pipeline
	@echo "✅ CI pipeline complete!"

dev: clean dev-install pre-commit ## Full development setup and validation
	@echo "✅ Development environment ready!"

# Environment info
env-info: ## Show environment information
	@echo "🔍 Environment Information:"
	@echo "Python: $$(python --version)"
	@echo "Pip: $$(pip --version)"
	@echo "Virtual env: $$VIRTUAL_ENV"
	@echo "Working dir: $$(pwd)"
	@echo ""
	@echo "📦 Installed packages:"
	@pip list | grep -E "(osiris|rich|pyyaml|duckdb|pydantic|httpx|typer|mcp)" || echo "No Osiris-related packages found"
