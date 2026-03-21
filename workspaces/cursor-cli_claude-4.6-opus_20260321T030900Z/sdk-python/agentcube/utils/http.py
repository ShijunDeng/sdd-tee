"""HTTP session factory with connection pooling."""

from __future__ import annotations

from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


def create_session(
    pool_connections: int = 10,
    pool_maxsize: int = 10,
    max_retries: int = 3,
    backoff_factor: float = 0.3,
) -> Session:
    """Build a ``requests.Session`` with pooled connections and retries."""
    session = Session()
    retry = Retry(
        total=max_retries,
        connect=max_retries,
        read=max_retries,
        status=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"),
    )
    adapter = HTTPAdapter(pool_connections=pool_connections, pool_maxsize=pool_maxsize, max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
