# AgentCube — build, test, images, and codegen
SHELL := /bin/bash
.ONESHELL:

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
CONTAINER_TOOL ?= docker
HUB ?= ghcr.io/volcano-sh
TAG ?= latest

IMAGE_WORKLOADMANAGER := $(HUB)/workloadmanager:$(TAG)
IMAGE_ROUTER := $(HUB)/agentcube-router:$(TAG)
IMAGE_PICOD := $(HUB)/picod:$(TAG)

GO ?= go
GOFLAGS ?=
GOLANGCI_LINT ?= golangci-lint

.PHONY: all build build-agentd build-router build-all run run-local run-router
.PHONY: gen-crd generate gen-client gen-all gen-check
.PHONY: test fmt vet lint clean deps update-deps
.PHONY: docker-build docker-buildx docker-push kind-load
.PHONY: docker-build-workloadmanager docker-build-router docker-build-picod
.PHONY: docker-buildx-workloadmanager docker-buildx-router docker-buildx-picod
.PHONY: docker-push-workloadmanager docker-push-router docker-push-picod
.PHONY: kind-load-workloadmanager kind-load-router kind-load-picod
.PHONY: e2e e2e-clean install build-python-sdk help

all: build ## Default target — build all main binaries

build: build-all ## Alias for build-all

build-all: build-agentd build-router ## Build workload manager (or agentd) and router

# Historical alias — maps to workload manager binary when cmd/agentd is absent.
build-agentd: ## Build workload manager / agentd binary into bin/
	@if [[ -d "$(ROOT)/cmd/agentd" ]]; then $(GO) build $(GOFLAGS) -o "$(ROOT)/bin/agentd" ./cmd/agentd; \
	elif [[ -d "$(ROOT)/cmd/workload-manager" ]]; then $(GO) build $(GOFLAGS) -o "$(ROOT)/bin/workloadmanager" ./cmd/workload-manager; \
	elif [[ -d "$(ROOT)/cmd/workloadmanager" ]]; then $(GO) build $(GOFLAGS) -o "$(ROOT)/bin/workloadmanager" ./cmd/workloadmanager; \
	else echo "no cmd/agentd, cmd/workload-manager, or cmd/workloadmanager"; exit 1; fi

build-router: ## Build router binary into bin/
	@test -d "$(ROOT)/cmd/router" || { echo "missing cmd/router"; exit 1; }
	$(GO) build $(GOFLAGS) -o "$(ROOT)/bin/router" ./cmd/router

run: run-local ## Run local control plane (workload manager)

run-local: build-agentd ## Build and exec workload manager / agentd
	@if [[ -x "$(ROOT)/bin/agentd" ]]; then exec "$(ROOT)/bin/agentd" "$$@"; \
	else exec "$(ROOT)/bin/workloadmanager" "$$@"; fi

run-router: build-router ## Build and exec router
	exec "$(ROOT)/bin/router" "$$@"

## Code generation
gen-crd: generate ## Generate CRD YAML + deepcopy
generate: ## Run hack/update-codegen.sh crd
	@echo ">> CRD / deepcopy (controller-gen)"
	@bash "$(ROOT)/hack/update-codegen.sh" crd

gen-client: ## Generate typed client-go
	@echo ">> client-gen (requires k8s.io/code-generator on PATH or in hack/tools)"
	@bash "$(ROOT)/hack/update-codegen.sh" client

gen-all: generate gen-client ## Full codegen

gen-check: gen-all ## Fail if generated API code differs from git
	@git diff --exit-code -- pkg/apis 2>/dev/null || { echo "generated API code out of date; run make gen-all"; exit 1; }

## Quality
test: ## Run unit tests
	$(GO) test $(GOFLAGS) ./...

fmt: ## go fmt
	$(GO) fmt ./...

vet: ## go vet
	$(GO) vet ./...

lint: ## golangci-lint
	$(GOLANGCI_LINT) run ./...

clean: ## Remove bin/ and build artifacts
	rm -rf "$(ROOT)/bin" "$(ROOT)/dist"
	find "$(ROOT)" -name '*.test' -delete 2>/dev/null || true

deps: ## go mod download
	$(GO) mod download
	$(GO) mod verify

update-deps: ## go get -u and tidy
	$(GO) get -u ./...
	$(GO) mod tidy

## OCI images (context = repo root)
DOCKERFILE_WM := $(ROOT)/docker/Dockerfile
DOCKERFILE_ROUTER := $(ROOT)/docker/Dockerfile.router
DOCKERFILE_PICOD := $(ROOT)/docker/Dockerfile.picod

docker-build: docker-build-workloadmanager docker-build-router docker-build-picod ## Build all images

docker-build-workloadmanager: ## docker build workload manager
	$(CONTAINER_TOOL) build -f "$(DOCKERFILE_WM)" -t "$(IMAGE_WORKLOADMANAGER)" "$(ROOT)"

docker-build-router: ## docker build router
	$(CONTAINER_TOOL) build -f "$(DOCKERFILE_ROUTER)" -t "$(IMAGE_ROUTER)" "$(ROOT)"

docker-build-picod: ## docker build picod
	$(CONTAINER_TOOL) build -f "$(DOCKERFILE_PICOD)" -t "$(IMAGE_PICOD)" "$(ROOT)"

docker-buildx: docker-buildx-workloadmanager docker-buildx-router docker-buildx-picod ## buildx --load all images

docker-buildx-workloadmanager: ## buildx workload manager
	$(CONTAINER_TOOL) buildx build --load -f "$(DOCKERFILE_WM)" -t "$(IMAGE_WORKLOADMANAGER)" "$(ROOT)"

docker-buildx-router: ## buildx router
	$(CONTAINER_TOOL) buildx build --load -f "$(DOCKERFILE_ROUTER)" -t "$(IMAGE_ROUTER)" "$(ROOT)"

docker-buildx-picod: ## buildx picod
	$(CONTAINER_TOOL) buildx build --load -f "$(DOCKERFILE_PICOD)" -t "$(IMAGE_PICOD)" "$(ROOT)"

docker-push: docker-push-workloadmanager docker-push-router docker-push-picod ## Push all images to registry

docker-push-workloadmanager: ## push workload manager image
	$(CONTAINER_TOOL) push "$(IMAGE_WORKLOADMANAGER)"

docker-push-router: ## push router image
	$(CONTAINER_TOOL) push "$(IMAGE_ROUTER)"

docker-push-picod: ## push picod image
	$(CONTAINER_TOOL) push "$(IMAGE_PICOD)"

kind-load: kind-load-workloadmanager kind-load-router kind-load-picod ## kind load docker-image (all)

kind-load-workloadmanager: docker-build-workloadmanager ## kind load workload manager
	kind load docker-image "$(IMAGE_WORKLOADMANAGER)" || true

kind-load-router: docker-build-router ## kind load router
	kind load docker-image "$(IMAGE_ROUTER)" || true

kind-load-picod: docker-build-picod ## kind load picod
	kind load docker-image "$(IMAGE_PICOD)" || true

## E2E / install / SDK
e2e: ## Run e2e tests (tag e2e)
	@echo ">> Run e2e (override with E2E_FLAGS)"
	$(GO) test $(GOFLAGS) -tags=e2e -count=1 ./test/e2e/... $(E2E_FLAGS)

e2e-clean: ## Delete kind cluster used for e2e
	kind delete cluster --name agentcube-e2e 2>/dev/null || true

install: ## helm upgrade --install base chart
	helm upgrade --install agentcube "$(ROOT)/manifests/charts/base" \
		--namespace agentcube --create-namespace

build-python-sdk: ## pip install sdk-python editable
	@if [[ -d "$(ROOT)/sdk-python" ]]; then pip install -e "$(ROOT)/sdk-python"; else echo "sdk-python not present"; exit 1; fi

help: ## Show targets
	@grep -E '^[a-zA-Z0-9_.-]+:.*?## ' "$(MAKEFILE_LIST)" | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-32s\033[0m %s\n", $$1, $$2}'
