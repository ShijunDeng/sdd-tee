# AgentCube SDK Tests

This directory contains unit tests for the AgentCube Python SDK.

## Running Tests

```bash
cd sdk-python
pip install -e .
pip install pytest pytest-cov
pytest tests/
```

## Test Files

- `test_exceptions.py` - Tests for exception hierarchy
- `test_utils.py` - Tests for utility functions
- `test_control_plane.py` - Tests for ControlPlaneClient
- `test_code_interpreter_data_plane.py` - Tests for CodeInterpreterDataPlaneClient
- `test_agent_runtime_data_plane.py` - Tests for AgentRuntimeDataPlaneClient
- `test_code_interpreter_client.py` - Tests for CodeInterpreterClient
- `test_agent_runtime_client.py` - Tests for AgentRuntimeClient
