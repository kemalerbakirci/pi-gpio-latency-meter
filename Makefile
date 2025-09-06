# Makefile for GPIO Latency Meter

.PHONY: run-sim run-real test lint plot install clean help

# Default target
help:
	@echo "Available targets:"
	@echo "  run-sim    - Quick simulator test (5 seconds)"
	@echo "  run-real   - Real GPIO test (requires hardware)"
	@echo "  test       - Run unit tests"
	@echo "  lint       - Check code formatting"
	@echo "  plot       - Plot latest results"
	@echo "  install    - Install package in development mode"
	@echo "  clean      - Clean generated files"

# Quick simulator test
run-sim:
	@echo "🧪 Running simulator test..."
	python3 latency_meter.py --backend sim --seconds 5 --csv data/sim_test.csv
	@echo "✅ Simulator test complete"

# Real GPIO test (requires hardware)
run-real:
	@echo "🔌 Running real GPIO test..."
	@echo "⚠️  Ensure GPIO18 and GPIO23 are connected with 10kΩ pulldown"
	python3 latency_meter.py --backend gpiod --seconds 10 --csv data/real_test.csv
	@echo "✅ Real GPIO test complete"

# Run unit tests
test:
	@echo "🧪 Running unit tests..."
	python3 -m pytest tests/ -v --tb=short
	@echo "✅ Tests complete"

# Code formatting and linting
lint:
	@echo "🔍 Checking code formatting..."
	black --check --diff latency_meter.py sim_backend.py plot.py tests/
	isort --check-only --diff latency_meter.py sim_backend.py plot.py tests/
	flake8 latency_meter.py sim_backend.py plot.py tests/ --max-line-length=100
	@echo "✅ Lint check complete"

# Format code
format:
	@echo "🎨 Formatting code..."
	black latency_meter.py sim_backend.py plot.py tests/
	isort latency_meter.py sim_backend.py plot.py tests/
	@echo "✅ Code formatted"

# Plot latest results
plot:
	@echo "📊 Plotting latest results..."
	@if [ -f data/sim_test.csv ]; then \
		python3 plot.py --csv data/sim_test.csv --output plots/latest_sim.png; \
	elif [ -f data/real_test.csv ]; then \
		python3 plot.py --csv data/real_test.csv --output plots/latest_real.png; \
	else \
		echo "❌ No test data found. Run 'make run-sim' first."; \
	fi

# Install in development mode
install:
	@echo "📦 Installing in development mode..."
	pip install -e .
	@echo "✅ Installation complete"

# Clean generated files
clean:
	@echo "🧹 Cleaning generated files..."
	rm -rf __pycache__/ .pytest_cache/ *.egg-info/
	rm -rf build/ dist/
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete
	@echo "✅ Clean complete"

# Environment check
env-check:
	@echo "🔍 Checking environment..."
	@bash scripts/env_check.sh

# Continuous integration simulation
ci:
	@echo "🤖 Running CI pipeline..."
	$(MAKE) lint
	$(MAKE) test
	$(MAKE) run-sim
	@echo "✅ CI pipeline complete"
