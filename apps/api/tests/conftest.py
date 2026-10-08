import os

# Unit tests must not depend on a running Valkey. The Valkey limiter has its own tests
# (test_rate_limit.py) using fakeredis.
os.environ.setdefault("RATE_LIMIT_BACKEND", "memory")
