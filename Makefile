# Datacove Makefile — Development & Deployment Automation
# Non-breaking: Helper commands only, no application code changes
# 
# Usage:
#   make help          Show all commands
#   make dev           Start development server
#   make test          Run all tests
#   make build         Build Docker image
#   make deploy        Deploy to production
#
# Set environment:
#   ENV=development (default) or ENV=production
#   PYTHON_ENV=.venv_new (use custom venv)

.PHONY: help install dev test lint format clean build deploy up down logs health

# Variables
PROJECT_NAME := datacove
PYTHON := python
PIP := pip
VENV_DIR := .venv_new
ENV ?= development
DOCKER_IMAGE := datacove:latest
DOCKER_REGISTRY ?=
PORT ?= 8000

# Color output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

help:
	@echo "$(GREEN)═══════════════════════════════════════════════════════════════$(NC)"
	@echo "$(GREEN)Datacove Makefile — Development & Deployment$(NC)"
	@echo "$(GREEN)═══════════════════════════════════════════════════════════════$(NC)"
	@echo ""
	@echo "$(YELLOW)Environment Setup:$(NC)"
	@echo "  $(GREEN)make install$(NC)                Install dependencies"
	@echo "  $(GREEN)make venv$(NC)                  Create Python virtual environment"
	@echo "  $(GREEN)make clean-venv$(NC)           Delete virtual environment"
	@echo ""
	@echo "$(YELLOW)Development:$(NC)"
	@echo "  $(GREEN)make dev$(NC)                   Start FastAPI dev server (auto-reload)"
	@echo "  $(GREEN)make dev-watch$(NC)             Dev server with file watch"
	@echo "  $(GREEN)make frontend$(NC)              Start Vite dev server (frontend)"
	@echo "  $(GREEN)make backend$(NC)               Start Just backend"
	@echo ""
	@echo "$(YELLOW)Testing & Quality:$(NC)"
	@echo "  $(GREEN)make test$(NC)                  Run all unit tests"
	@echo "  $(GREEN)make test-integration$(NC)     Run integration tests only"
	@echo "  $(GREEN)make test-routes$(NC)           Test all routes load correctly"
	@echo "  $(GREEN)make lint$(NC)                  Run code linting"
	@echo "  $(GREEN)make format$(NC)                Auto-format Python code"
	@echo "  $(GREEN)make typecheck$(NC)             Run Pylance type checking"
	@echo ""
	@echo "$(YELLOW)Docker & Deployment:$(NC)"
	@echo "  $(GREEN)make build$(NC)                 Build Docker image"
	@echo "  $(GREEN)make build-prod$(NC)            Build production Docker image"
	@echo "  $(GREEN)make up$(NC)                    Start services with docker-compose"
	@echo "  $(GREEN)make down$(NC)                  Stop docker-compose services"
	@echo "  $(GREEN)make logs$(NC)                  View docker logs"
	@echo "  $(GREEN)make health$(NC)                Check service health"
	@echo ""
	@echo "$(YELLOW)Database & Migrations:$(NC)"
	@echo "  $(GREEN)make migrate$(NC)               Run database migrations"
	@echo "  $(GREEN)make seed$(NC)                  Seed database with sample data"
	@echo ""
	@echo "$(YELLOW)Utilities:$(NC)"
	@echo "  $(GREEN)make clean$(NC)                 Remove build artifacts & cache"
	@echo "  $(GREEN)make requirements$(NC)         Update requirements.txt"
	@echo "  $(GREEN)make version$(NC)               Show service versions"
	@echo "  $(GREEN)make help$(NC)                  Show this help message"
	@echo ""

# ──────────────────────────────────────────────────────────────────────────────
# Environment Setup
# ──────────────────────────────────────────────────────────────────────────────

venv:
	@echo "$(YELLOW)Creating Python virtual environment...$(NC)"
	$(PYTHON) -m venv $(VENV_DIR)
	@echo "$(GREEN)✓ Virtual environment created at $(VENV_DIR)$(NC)"
	@echo "$(YELLOW)Activate with: . $(VENV_DIR)/Scripts/activate$(NC)"

install: venv
	@echo "$(YELLOW)Installing dependencies...$(NC)"
	$(VENV_DIR)/Scripts/pip install --upgrade pip setuptools wheel
	$(VENV_DIR)/Scripts/pip install -r requirements.txt
	@echo "$(GREEN)✓ Dependencies installed$(NC)"

clean-venv:
	@if [ -d "$(VENV_DIR)" ]; then \
		echo "$(YELLOW)Removing virtual environment...$(NC)"; \
		rm -rf $(VENV_DIR); \
		echo "$(GREEN)✓ Virtual environment removed$(NC)"; \
	fi

# ──────────────────────────────────────────────────────────────────────────────
# Development
# ──────────────────────────────────────────────────────────────────────────────

dev: backend frontend

backend:
	@echo "$(YELLOW)Starting backend server ($(PORT))...$(NC)"
	@echo "$(GREEN)→ http://localhost:$(PORT)$(NC)"
	@echo "$(GREEN)→ http://localhost:$(PORT)/docs$(NC)"
	$(VENV_DIR)/Scripts/uvicorn main:app --reload --host 0.0.0.0 --port $(PORT)

dev-watch:
	@echo "$(YELLOW)Starting backend in watch mode...$(NC)"
	$(VENV_DIR)/Scripts/watchmedo auto-restart -d . -p '*.py' \
		-- $(VENV_DIR)/Scripts/uvicorn main:app --reload --host 0.0.0.0 --port $(PORT)

frontend:
	@echo "$(YELLOW)Starting Vite development server...$(NC)"
	cd ../frontend && npm run dev

# ──────────────────────────────────────────────────────────────────────────────
# Testing & Quality
# ──────────────────────────────────────────────────────────────────────────────

test:
	@echo "$(YELLOW)Running all tests...$(NC)"
	$(VENV_DIR)/Scripts/pytest tests/ -v --tb=short
	@echo "$(GREEN)✓ Tests completed$(NC)"

test-integration:
	@echo "$(YELLOW)Running integration tests...$(NC)"
	$(VENV_DIR)/Scripts/pytest tests/test_integration.py -v
	@echo "$(GREEN)✓ Integration tests completed$(NC)"

test-routes:
	@echo "$(YELLOW)Testing routes...$(NC)"
	$(VENV_DIR)/Scripts/python test_all_routes.py
	@echo "$(GREEN)✓ Routes tested$(NC)"

lint:
	@echo "$(YELLOW)Running code linter...$(NC)"
	$(VENV_DIR)/Scripts/pylint routes/ services/ models/ --disable=C0111,W0212 --max-line-length=120
	@echo "$(GREEN)✓ Linting complete$(NC)"

format:
	@echo "$(YELLOW)Formatting Python code...$(NC)"
	$(VENV_DIR)/Scripts/black . --line-length=120
	@echo "$(GREEN)✓ Code formatted$(NC)"

typecheck:
	@echo "$(YELLOW)Running type checks...$(NC)"
	$(VENV_DIR)/Scripts/mypy services/ routes/ --ignore-missing-imports
	@echo "$(GREEN)✓ Type checking complete$(NC)"

# ──────────────────────────────────────────────────────────────────────────────
# Docker & Deployment
# ──────────────────────────────────────────────────────────────────────────────

build:
	@echo "$(YELLOW)Building Docker image (development)...$(NC)"
	docker build -t $(DOCKER_IMAGE) .
	@echo "$(GREEN)✓ Image built: $(DOCKER_IMAGE)$(NC)"

build-prod:
	@echo "$(YELLOW)Building Docker image (production)...$(NC)"
	docker build -t $(DOCKER_IMAGE) --build-arg ENV=production .
	@echo "$(GREEN)✓ Production image built$(NC)"

up:
	@echo "$(YELLOW)Starting services with docker-compose...$(NC)"
	docker-compose up -d
	@echo "$(GREEN)✓ Services started$(NC)"
	@echo "$(YELLOW)Waiting for services to be ready...$(NC)"
	@sleep 5
	@make health

down:
	@echo "$(YELLOW)Stopping docker-compose services...$(NC)"
	docker-compose down
	@echo "$(GREEN)✓ Services stopped$(NC)"

logs:
	@echo "$(YELLOW)Showing service logs...$(NC)"
	docker-compose logs -f

health:
	@echo "$(YELLOW)Checking service health...$(NC)"
	@docker-compose ps 2>/dev/null || echo "Services not running"
	@curl -s http://localhost:8000/health && echo "\n$(GREEN)✓ Backend healthy$(NC)" || echo "$(RED)✗ Backend not responding$(NC)"

# ──────────────────────────────────────────────────────────────────────────────
# Database & Migrations
# ──────────────────────────────────────────────────────────────────────────────

migrate:
	@echo "$(YELLOW)Running database migrations...$(NC)"
	$(VENV_DIR)/Scripts/python -m alembic upgrade head
	@echo "$(GREEN)✓ Migrations applied$(NC)"

seed:
	@echo "$(YELLOW)Seeding database...$(NC)"
	$(VENV_DIR)/Scripts/python scripts/seed_db.py
	@echo "$(GREEN)✓ Database seeded$(NC)"

# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────

clean:
	@echo "$(YELLOW)Cleaning build artifacts...$(NC)"
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build/ dist/ .coverage 2>/dev/null || true
	@echo "$(GREEN)✓ Cleaned$(NC)"

requirements:
	@echo "$(YELLOW)Generating requirements.txt...$(NC)"
	$(VENV_DIR)/Scripts/pip freeze > requirements.txt
	@echo "$(GREEN)✓ requirements.txt updated$(NC)"

version:
	@echo "$(GREEN)Service Versions:$(NC)"
	@echo "Python: $$(python --version)"
	@echo "FastAPI: $$($(VENV_DIR)/Scripts/pip show fastapi | grep Version)"
	@echo "SQLAlchemy: $$($(VENV_DIR)/Scripts/pip show sqlalchemy | grep Version)"
	@echo "Pandas: $$($(VENV_DIR)/Scripts/pip show pandas | grep Version)"

# ──────────────────────────────────────────────────────────────────────────────
# CI/CD & Production
# ──────────────────────────────────────────────────────────────────────────────

.PHONY: ci ci-test ci-build ci-deploy

ci: clean install lint typecheck test
	@echo "$(GREEN)✓ CI pipeline complete$(NC)"

ci-test: lint typecheck test test-integration
	@echo "$(GREEN)✓ All tests passed$(NC)"

ci-build: build
	@echo "$(GREEN)✓ Build successful$(NC)"

ci-deploy: ci-build
	@echo "$(YELLOW)Ready for deployment$(NC)"
	@echo "$(GREEN)→ Run 'make up' to start services$(NC)"

# Default target
.DEFAULT_GOAL := help
