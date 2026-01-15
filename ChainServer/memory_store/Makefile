# ═══════════════════════════════════════════════════════════════════════════════
#                       Memory Store Service - Makefile
# ═══════════════════════════════════════════════════════════════════════════════

.PHONY: help install dev test lint format clean docker-build docker-push k8s-deploy k8s-delete

# Default target
.DEFAULT_GOAL := help

# Variables
PYTHON := python3
PIP := pip
DOCKER := docker
KUBECTL := kubectl
IMAGE_NAME := memory-store
IMAGE_TAG := latest
REGISTRY := your-registry
NAMESPACE := memory-store
HELM_CHART := ./helm
HELM_RELEASE := memory-store
ENVIRONMENT := dev

help: ## Show this help message
	@echo "Memory Store Service - Available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ───────────────────────────────────────────────────────────────────────────────
# Development
# ───────────────────────────────────────────────────────────────────────────────

install: ## Install dependencies
	$(PIP) install -e .

install-dev: ## Install development dependencies
	$(PIP) install -e ".[dev,monitoring]"

dev: ## Run service in development mode with auto-reload
	memory-store --reload --log-level DEBUG

run: ## Run service in production mode
	memory-store

# ───────────────────────────────────────────────────────────────────────────────
# Testing & Quality
# ───────────────────────────────────────────────────────────────────────────────

test: ## Run tests
	pytest tests/ -v

test-cov: ## Run tests with coverage
	pytest tests/ --cov=memory_store --cov-report=html --cov-report=term

lint: ## Run linter
	ruff check .

format: ## Format code
	ruff format .

check: lint test ## Run all checks (lint + test)

# ───────────────────────────────────────────────────────────────────────────────
# Docker
# ───────────────────────────────────────────────────────────────────────────────

docker-build: ## Build Docker image (standard)
	$(DOCKER) build -f deployments/Dockerfile -t $(IMAGE_NAME):$(IMAGE_TAG) .

docker-build-corporate: ## Build Docker image (corporate)
	$(DOCKER) build -f deployments/Dockerfile.corporate -t $(IMAGE_NAME):$(IMAGE_TAG) .

docker-run: ## Run Docker container locally
	$(DOCKER) run -p 8000:8000 --env-file .env $(IMAGE_NAME):$(IMAGE_TAG)

docker-compose-up: ## Start services with docker-compose
	docker-compose -f deployments/docker-compose.yml up -d

docker-compose-down: ## Stop services with docker-compose
	docker-compose -f deployments/docker-compose.yml down

docker-compose-logs: ## View docker-compose logs
	docker-compose -f deployments/docker-compose.yml logs -f memory-store

docker-tag: ## Tag image for registry
	$(DOCKER) tag $(IMAGE_NAME):$(IMAGE_TAG) $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

docker-push: docker-tag ## Push image to registry
	$(DOCKER) push $(REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

# ───────────────────────────────────────────────────────────────────────────────
# Kubernetes (Generic Commands)
# ───────────────────────────────────────────────────────────────────────────────

k8s-status: ## Check deployment status
	$(KUBECTL) get all -n $(NAMESPACE)

k8s-logs: ## View logs from Kubernetes pods
	$(KUBECTL) logs -n $(NAMESPACE) -l app.kubernetes.io/name=memory-store --tail=100 -f

k8s-describe: ## Describe Kubernetes deployment
	$(KUBECTL) describe deployment -n $(NAMESPACE) memory-store

k8s-port-forward: ## Port-forward to local machine
	$(KUBECTL) port-forward -n $(NAMESPACE) svc/memory-store 8000:80

k8s-shell: ## Get shell in pod
	$(KUBECTL) exec -it -n $(NAMESPACE) deployment/memory-store -- /bin/bash

# ───────────────────────────────────────────────────────────────────────────────
# Utilities
# ───────────────────────────────────────────────────────────────────────────────

clean: ## Clean generated files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf build/ dist/ .pytest_cache/ .coverage htmlcov/

health: ## Check service health
	curl -s http://localhost:8000/health | jq .

docs: ## Open API documentation
	@echo "Opening API docs at http://localhost:8000/docs"
	@open http://localhost:8000/docs || xdg-open http://localhost:8000/docs

config-validate: ## Validate configuration
	$(PYTHON) -c "from memory_store.config import get_config; import json; print(json.dumps(get_config().to_dict(), indent=2))"

# ───────────────────────────────────────────────────────────────────────────────
# CI/CD
# ───────────────────────────────────────────────────────────────────────────────

ci: lint test ## Run CI checks

build-and-push: docker-build docker-push ## Build and push Docker image

deploy-full: build-and-push helm-upgrade ## Full deployment (build, push, helm upgrade)

# ───────────────────────────────────────────────────────────────────────────────
# Helm (Corporate Deployment)
# ───────────────────────────────────────────────────────────────────────────────

helm-lint: ## Lint Helm chart
	helm lint $(HELM_CHART)

helm-template: ## Template Helm chart for current environment
	helm template $(HELM_RELEASE) $(HELM_CHART) \
		--values $(HELM_CHART)/environments/$(ENVIRONMENT)/values.yaml \
		--set ghActionInput.imageTag=$(IMAGE_TAG)

helm-template-dev: ## Template Helm chart for DEV
	$(MAKE) helm-template ENVIRONMENT=dev

helm-template-qat: ## Template Helm chart for QAT
	$(MAKE) helm-template ENVIRONMENT=qat

helm-template-prod: ## Template Helm chart for PROD
	$(MAKE) helm-template ENVIRONMENT=prod

helm-install: ## Install Helm chart (DEV by default)
	helm install $(HELM_RELEASE) $(HELM_CHART) \
		--values $(HELM_CHART)/environments/$(ENVIRONMENT)/values.yaml \
		--set ghActionInput.imageTag=$(IMAGE_TAG) \
		--namespace $(NAMESPACE) \
		--create-namespace

helm-upgrade: ## Upgrade Helm release
	helm upgrade $(HELM_RELEASE) $(HELM_CHART) \
		--install \
		--values $(HELM_CHART)/environments/$(ENVIRONMENT)/values.yaml \
		--set ghActionInput.imageTag=$(IMAGE_TAG) \
		--namespace $(NAMESPACE)

helm-uninstall: ## Uninstall Helm release
	helm uninstall $(HELM_RELEASE) --namespace $(NAMESPACE)

helm-package: ## Package Helm chart
	mkdir -p dist
	helm package $(HELM_CHART) --destination ./dist

helm-status: ## Show Helm release status
	helm status $(HELM_RELEASE) --namespace $(NAMESPACE)

helm-history: ## Show Helm release history
	helm history $(HELM_RELEASE) --namespace $(NAMESPACE)

helm-rollback: ## Rollback Helm release to previous version
	helm rollback $(HELM_RELEASE) --namespace $(NAMESPACE)

helm-test: ## Run Helm chart tests
	helm test $(HELM_RELEASE) --namespace $(NAMESPACE)
