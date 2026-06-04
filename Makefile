.PHONY: test spell spell-fix lint lint-fix lint-notebooks format check install

# Install development dependencies
install:
	uv sync --dev

# Run tests with coverage
test:
	uv run pytest || test $$? -eq 5

# Run spell checking
spell:
	uv run codespell --skip=metaData,notebooks,htmlcov,*.json --ignore-words-list=EHR

# Run spell checking interactively (allows fixing)
spell-fix:
	uv run codespell --interactive 3 --skip=metaData,notebooks,htmlcov,*.json --ignore-words-list=EHR

# Run linting
lint:
	uv run ruff check .

# Run linting with automatic fixes
lint-fix:
	uv run ruff check . --fix

# Run linting on notebooks only
lint-notebooks:
	uv run ruff check notebooks/ || true

# Run code formatting
format:
	uv run ruff format .

# Run all checks (lint, spell, test)
check: lint spell test

# Help target
help:
	@echo "Available targets:"
	@echo "  install  - Install development dependencies"
	@echo "  test     - Run tests with coverage"
	@echo "  spell    - Run spell checking"
	@echo "  spell-fix - Run interactive spell checking (allows fixing)"
	@echo "  lint     - Run code linting"
	@echo "  lint-fix - Run code linting with automatic fixes"
	@echo "  lint-notebooks - Run code linting on notebooks (informational)"
	@echo "  format   - Format code"
	@echo "  check    - Run all checks (lint, spell, test)"
	@echo "  help     - Show this help message"
