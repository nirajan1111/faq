# Docker Compose command (use 'docker compose' for newer Docker versions)
DOCKER_COMPOSE := docker compose

.PHONY: help build up down logs clean dev prod

help:
	@echo "FAQ Generation System - Available Commands"
	@echo ""
	@echo "  make dev        - Start development environment"
	@echo "  make prod       - Start production environment"
	@echo "  make up         - Start all services (default: dev)"
	@echo "  make down       - Stop all services"
	@echo "  make build      - Build all Docker images"
	@echo "  make logs       - Show logs for all services"
	@echo "  make clean      - Remove all containers and volumes"
	@echo "  make restart    - Restart all services"
	@echo ""
	@echo "Service-specific commands:"
	@echo "  make logs-api   - Show API logs"
	@echo "  make logs-scraper - Show scraper logs"
	@echo "  make shell-api  - Open shell in API container"
	@echo ""

# Development environment
dev:
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml up -d
	@echo ""
	@echo "Development environment started!"
	@echo "Dashboard: http://localhost:3000"
	@echo "API: http://localhost:8000"
	@echo "API Docs: http://localhost:8000/docs"

# Production environment  
prod:
	$(DOCKER_COMPOSE) up -d
	@echo ""
	@echo "Production environment started!"
	@echo "Dashboard: http://localhost:3000"
	@echo "API: http://localhost:8000"

# Default up command
up: dev

# Stop all services
down:
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml down 2>/dev/null || true
	$(DOCKER_COMPOSE) down 2>/dev/null || true

# Build all images
build:
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml build

# Show all logs
logs:
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml logs -f

# Service-specific logs
logs-api:
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml logs -f api

logs-scraper:
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml logs -f reddit-scraper

logs-kafka:
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml logs -f kafka

logs-consumer:
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml logs -f kafka-consumer

# Shell access
shell-api:
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml exec api /bin/bash

shell-mongodb:
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml exec mongodb mongosh faq_generation

# Clean everything
clean:
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml down -v --rmi local 2>/dev/null || true
	$(DOCKER_COMPOSE) down -v --rmi local 2>/dev/null || true
	docker system prune -f

# Restart all services
restart: down up

# Status
status:
	$(DOCKER_COMPOSE) -f docker-compose.dev.yml ps

# Initialize Ollama model
init-ollama:
	@echo "Pulling llama3.2 model..."
	ollama pull llama3.2

# Test API
test-api:
	@echo "Testing API health..."
	curl -s http://localhost:8000/health | python3 -m json.tool
	@echo ""
	@echo "Testing stats endpoint..."
	curl -s http://localhost:8000/api/stats | python3 -m json.tool
