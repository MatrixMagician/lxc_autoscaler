# Makefile for LXC Autoscaler Docker Operations
# Provides convenient commands for building, running, and managing the container

.PHONY: help build run stop clean logs shell test validate health dev prod push pull

# Default target
.DEFAULT_GOAL := help

# Variables
DOCKER_IMAGE := lxc-autoscaler
DOCKER_TAG := $(shell git describe --tags --always --dirty 2>/dev/null || echo "latest")
CONTAINER_NAME := lxc-autoscaler
BUILD_DATE := $(shell date -u +'%Y-%m-%dT%H:%M:%SZ')
VCS_REF := $(shell git rev-parse HEAD 2>/dev/null || echo "unknown")

# Colors for terminal output
RED := \033[31m
GREEN := \033[32m
YELLOW := \033[33m
BLUE := \033[34m
RESET := \033[0m

help: ## Show this help message
	@echo "$(BLUE)LXC Autoscaler Docker Management$(RESET)"
	@echo ""
	@echo "$(YELLOW)Usage:$(RESET)"
	@echo "  make [target]"
	@echo ""
	@echo "$(YELLOW)Available targets:$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'

build: ## Build the Docker image
	@echo "$(BLUE)Building Docker image...$(RESET)"
	docker build \
		--build-arg BUILD_DATE="$(BUILD_DATE)" \
		--build-arg VERSION="$(DOCKER_TAG)" \
		--build-arg VCS_REF="$(VCS_REF)" \
		-t $(DOCKER_IMAGE):$(DOCKER_TAG) \
		-t $(DOCKER_IMAGE):latest \
		.
	@echo "$(GREEN)Build completed: $(DOCKER_IMAGE):$(DOCKER_TAG)$(RESET)"

build-dev: ## Build development image with debugging tools
	@echo "$(BLUE)Building development Docker image...$(RESET)"
	docker build \
		--build-arg BUILD_DATE="$(BUILD_DATE)" \
		--build-arg VERSION="$(DOCKER_TAG)-dev" \
		--build-arg VCS_REF="$(VCS_REF)" \
		--target builder \
		-t $(DOCKER_IMAGE):$(DOCKER_TAG)-dev \
		-t $(DOCKER_IMAGE):dev \
		.
	@echo "$(GREEN)Development build completed: $(DOCKER_IMAGE):$(DOCKER_TAG)-dev$(RESET)"

run: ## Run the container with docker-compose
	@echo "$(BLUE)Starting LXC Autoscaler with docker-compose...$(RESET)"
	@if [ ! -f config/config.yaml ]; then \
		echo "$(RED)Error: config/config.yaml not found$(RESET)"; \
		echo "$(YELLOW)Please copy and configure:$(RESET)"; \
		echo "  cp examples/config.yaml config/config.yaml"; \
		echo "  # Edit config/config.yaml with your Proxmox settings"; \
		exit 1; \
	fi
	docker-compose up -d
	@echo "$(GREEN)Container started. Use 'make logs' to view output.$(RESET)"

stop: ## Stop the running container
	@echo "$(BLUE)Stopping LXC Autoscaler...$(RESET)"
	docker-compose down
	@echo "$(GREEN)Container stopped.$(RESET)"

restart: ## Restart the container
	@echo "$(BLUE)Restarting LXC Autoscaler...$(RESET)"
	docker-compose restart
	@echo "$(GREEN)Container restarted.$(RESET)"

logs: ## Show container logs
	docker-compose logs -f --tail=100

logs-all: ## Show all container logs
	docker-compose logs --tail=all

shell: ## Open shell in running container
	@echo "$(BLUE)Opening shell in container...$(RESET)"
	docker-compose exec lxc-autoscaler /bin/bash

shell-root: ## Open root shell in running container (for debugging)
	@echo "$(YELLOW)Opening root shell in container...$(RESET)"
	docker-compose exec --user root lxc-autoscaler /bin/bash

validate: ## Validate configuration without starting daemon
	@echo "$(BLUE)Validating configuration...$(RESET)"
	@if [ ! -f config/config.yaml ]; then \
		echo "$(RED)Error: config/config.yaml not found$(RESET)"; \
		exit 1; \
	fi
	docker run --rm \
		-v $(PWD)/config:/app/config:ro \
		$(DOCKER_IMAGE):latest \
		--validate-config

dry-run: ## Run in dry-run mode (no actual scaling)
	@echo "$(BLUE)Starting in dry-run mode...$(RESET)"
	@if [ ! -f config/config.yaml ]; then \
		echo "$(RED)Error: config/config.yaml not found$(RESET)"; \
		exit 1; \
	fi
	DRY_RUN=true docker-compose up -d
	@echo "$(GREEN)Container started in dry-run mode.$(RESET)"

health: ## Check container health
	@echo "$(BLUE)Checking container health...$(RESET)"
	@if docker-compose ps | grep -q "Up (healthy)"; then \
		echo "$(GREEN)✓ Container is healthy$(RESET)"; \
	elif docker-compose ps | grep -q "Up (unhealthy)"; then \
		echo "$(RED)✗ Container is unhealthy$(RESET)"; \
		exit 1; \
	elif docker-compose ps | grep -q "Up"; then \
		echo "$(YELLOW)⚠ Container is starting up$(RESET)"; \
	else \
		echo "$(RED)✗ Container is not running$(RESET)"; \
		exit 1; \
	fi

status: ## Show container status
	@echo "$(BLUE)Container status:$(RESET)"
	docker-compose ps

test: ## Run tests in container
	@echo "$(BLUE)Running tests...$(RESET)"
	docker run --rm \
		-v $(PWD):/app/src:ro \
		$(DOCKER_IMAGE):latest \
		/bin/bash -c "cd /app/src && python -m pytest tests/ -v"

clean: ## Clean up containers and images
	@echo "$(BLUE)Cleaning up...$(RESET)"
	docker-compose down -v --remove-orphans
	docker image prune -f
	docker volume prune -f
	@echo "$(GREEN)Cleanup completed.$(RESET)"

clean-all: ## Remove all containers, images, and volumes
	@echo "$(RED)This will remove all Docker containers, images, and volumes!$(RESET)"
	@read -p "Are you sure? [y/N]: " confirm && [ "$$confirm" = "y" ] || exit 1
	docker-compose down -v --remove-orphans
	docker rmi $(DOCKER_IMAGE):latest $(DOCKER_IMAGE):$(DOCKER_TAG) 2>/dev/null || true
	docker system prune -a -f --volumes
	@echo "$(GREEN)Complete cleanup finished.$(RESET)"

init-config: ## Initialize configuration from example
	@echo "$(BLUE)Initializing configuration...$(RESET)"
	@mkdir -p config
	@if [ -f config/config.yaml ]; then \
		echo "$(YELLOW)config/config.yaml already exists, creating backup...$(RESET)"; \
		cp config/config.yaml config/config.yaml.backup.$$(date +%s); \
	fi
	cp examples/config.yaml config/config.yaml
	@echo "$(GREEN)Configuration initialized at config/config.yaml$(RESET)"
	@echo "$(YELLOW)Please edit config/config.yaml with your Proxmox settings before running.$(RESET)"

# Development targets
dev: build-dev ## Start development environment
	@echo "$(BLUE)Starting development environment...$(RESET)"
	docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d

dev-shell: ## Open development shell with source mounted
	@echo "$(BLUE)Opening development shell...$(RESET)"
	docker run --rm -it \
		-v $(PWD):/app/src \
		-v $(PWD)/config:/app/config:ro \
		$(DOCKER_IMAGE):dev \
		/bin/bash

# Production targets
prod: build ## Deploy to production
	@echo "$(BLUE)Deploying to production...$(RESET)"
	@echo "$(YELLOW)Make sure to set proper environment variables in production!$(RESET)"
	VERSION=$(DOCKER_TAG) docker-compose up -d

push: ## Push image to registry (requires login)
	@echo "$(BLUE)Pushing image to registry...$(RESET)"
	docker push $(DOCKER_IMAGE):$(DOCKER_TAG)
	docker push $(DOCKER_IMAGE):latest
	@echo "$(GREEN)Image pushed successfully.$(RESET)"

pull: ## Pull image from registry
	@echo "$(BLUE)Pulling image from registry...$(RESET)"
	docker pull $(DOCKER_IMAGE):latest
	@echo "$(GREEN)Image pulled successfully.$(RESET)"

info: ## Show build information
	@echo "$(BLUE)Build Information:$(RESET)"
	@echo "  Image: $(DOCKER_IMAGE):$(DOCKER_TAG)"
	@echo "  Build Date: $(BUILD_DATE)"
	@echo "  VCS Ref: $(VCS_REF)"
	@echo "  Container: $(CONTAINER_NAME)"

# Quick setup target
setup: init-config build ## Quick setup: initialize config and build image
	@echo "$(GREEN)Setup completed!$(RESET)"
	@echo "$(YELLOW)Next steps:$(RESET)"
	@echo "  1. Edit config/config.yaml with your Proxmox settings"
	@echo "  2. Run 'make validate' to test configuration"
	@echo "  3. Run 'make dry-run' to test without actual scaling"
	@echo "  4. Run 'make run' to start the autoscaler"