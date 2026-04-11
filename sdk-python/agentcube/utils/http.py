"""HTTP utilities for AgentCube SDK."""

import requests
from requests.adapters import HTTPAdapter


def create_session(pool_connections: int = 10, pool_maxsize: int = 10) -> requests.Session:
    """Create a requests Session with connection pooling.

    Args:
        pool_connections: Number of connections to pool
        pool_maxsize: Maximum number of connections in the pool

    Returns:
        Configured requests Session instance
    """
    session = requests.Session()
    adapter = HTTPAdapter(
        pool_connections=pool_connections,
        pool_maxsize=pool_maxsize,
    )
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session
