# AR-026 — K8s/AgentCube Provider Tasks

**Module:** `cmd/cli`  
**Language:** Python  
**Size:** M  
**Stage:** Not started

---

## Phase 1: CLI Structure and Command Setup

### T001: Create CLI module structure
- [ ] Create `cmd/cli/` directory structure
  - Directory: `cmd/cli/`
  - Subdirectory: `cmd/cli/commands/`
  - Subdirectory: `cmd/cli/providers/`
  - Verify: All directories exist

### T002: Set up Python project files
- [ ] Create `cmd/cli/requirements.txt` with dependencies
  - Dependencies: `click`, `kubernetes`, `pyyaml`, `requests`
  - Verify: File exists with correct dependencies

### T003: Create CLI entry point
- [ ] Create `cmd/cli/main.py` entry point
  - File: `cmd/cli/main.py`
  - Use Click for CLI framework
  - Add `--version` flag
  - Add `--help` documentation
  - Verify: Entry point works with `python main.py --help`

### T004: Create base command structure
- [ ] Create `cmd/cli/commands/__init__.py`
- [ ] Create `cmd/cli/commands/base.py` with base command class
  - Abstract base class for all commands
  - Common logging setup
  - Configuration loading
  - Verify: Base class can be imported

---

## Phase 2: Provider Interface and Base Classes

### T005: Create provider interface
- [ ] Create `cmd/cli/providers/__init__.py`
- [ ] Create `cmd/cli/providers/base.py`
  - Define `Provider` abstract base class
  - Methods: `deploy()`, `delete()`, `status()`, `logs()`, `list()`
  - Verify: Interface is properly defined with ABC

### T006: Create K8s provider implementation
- [ ] Create `cmd/cli/providers/k8s.py`
  - Class: `K8sProvider`
  - Inherits from `Provider`
  - Kubernetes client initialization
  - Namespace management
  - Verify: Can import and instantiate

### T007: Create AgentCube provider implementation
- [ ] Create `cmd/cli/providers/agentcube.py`
  - Class: `AgentCubeProvider`
  - Inherits from `Provider`
  - AgentCube API client
  - CRD management for AgentRuntime
  - CRD management for CodeInterpreter
  - Verify: Can import and instantiate

---

## Phase 3: CLI Commands Implementation

### T008: Implement deploy command
- [ ] Create `cmd/cli/commands/deploy.py`
  - Command: `agentcube deploy`
  - Flags: `--provider`, `--file`, `--namespace`, `--name`
  - Support for YAML/JSON deployment specs
  - Verify: Command registered and help works

### T009: Implement delete command
- [ ] Create `cmd/cli/commands/delete.py`
  - Command: `agentcube delete`
  - Flags: `--provider`, `--namespace`, `--name`, `--all`
  - Verify: Command registered and help works

### T010: Implement status command
- [ ] Create `cmd/cli/commands/status.py`
  - Command: `agentcube status`
  - Flags: `--provider`, `--namespace`, `--name`, `--watch`
  - Display resource status in table format
  - Verify: Command registered and help works

### T011: Implement logs command
- [ ] Create `cmd/cli/commands/logs.py`
  - Command: `agentcube logs`
  - Flags: `--provider`, `--namespace`, `--name`, `--follow`, `--tail`
  - Stream logs from pods
  - Verify: Command registered and help works

### T012: Implement list command
- [ ] Create `cmd/cli/commands/list.py`
  - Command: `agentcube list`
  - Flags: `--provider`, `--namespace`, `--all-namespaces`, `--output`
  - Table and JSON output formats
  - Verify: Command registered and help works

---

## Phase 4: Configuration and Utilities

### T013: Create configuration module
- [ ] Create `cmd/cli/config.py`
  - Load config from `~/.agentcube/config.yaml`
  - Environment variable support
  - Default provider settings
  - Kubernetes context selector
  - Verify: Config loads correctly

### T014: Create utilities module
- [ ] Create `cmd/cli/utils.py`
  - YAML/JSON parsing utilities
  - Table formatting for CLI output
  - Error handling helpers
  - Kubernetes resource helpers
  - Verify: Utilities work correctly

### T015: Create validation module
- [ ] Create `cmd/cli/validation.py`
  - Deployment spec validation
  - Resource name validation
  - Namespace validation
  - Provider-specific validation
  - Verify: Validation functions work

---

## Phase 5: Testing

### T016: Create unit tests structure
- [ ] Create `cmd/cli/tests/` directory
  - Subdirectory: `cmd/cli/tests/unit/`
  - Subdirectory: `cmd/cli/tests/integration/`
  - Create `cmd/cli/tests/__init__.py`
  - Verify: Test directories exist

### T017: Create provider unit tests
- [ ] Create `cmd/cli/tests/unit/test_providers.py`
  - Test K8sProvider initialization
  - Test AgentCubeProvider initialization
  - Mock Kubernetes API calls
  - Verify: All tests pass

### T018: Create commands unit tests
- [ ] Create `cmd/cli/tests/unit/test_commands.py`
  - Test deploy command with mocks
  - Test delete command with mocks
  - Test status command with mocks
  - Test list command with mocks
  - Test logs command with mocks
  - Verify: All tests pass

### T019: Create integration tests
- [ ] Create `cmd/cli/tests/integration/test_k8s_integration.py`
  - Test against kind/minikube cluster
  - Test actual CRD operations
  - Test pod lifecycle
  - Verify: Integration tests pass (if cluster available)

---

## Phase 6: Documentation and Finalization

### T020: Create CLI README
- [ ] Create `cmd/cli/README.md`
  - Installation instructions
  - Configuration guide
  - Command reference
  - Usage examples
  - Verify: Documentation is complete

### T021: Create usage examples
- [ ] Create `cmd/cli/examples/` directory
  - Example: `deployment-agent.yaml`
  - Example: `deployment-interpreter.yaml`
  - Example: Sample configuration file
  - Verify: Examples are valid YAML

### T022: Create Makefile targets
- [ ] Update root `Makefile` with CLI targets
  - Target: `build-cli`
  - Target: `test-cli`
  - Target: `install-cli`
  - Verify: Make targets work

### T023: Final verification
- [ ] Run all unit tests: `pytest cmd/cli/tests/unit/ -v`
- [ ] Check code coverage
- [ ] Run linting: `flake8 cmd/cli/` and `black --check cmd/cli/`
- [ ] Verify: All checks pass

---

## Verification

- [ ] All 23 tasks completed
- [ ] CLI module structure follows project conventions
- [ ] All commands implement required functionality
- [ ] Provider interface is extensible for future providers
- [ ] Unit tests achieve >80% coverage
- [ ] Documentation is complete with examples
- [ ] Code passes linting and formatting checks
- [ ] Integration with existing agentcube project verified
