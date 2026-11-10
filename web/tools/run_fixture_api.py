"""Local smoke helper: serve the deterministic fixture API over real HTTP.

Serves exactly the canned data used by `web/tests/conftest.py` (which mirrors
the backend_py test fixtures). For local development and browser smoke runs
ONLY — never a source of real market prices. Point the web app at it with
`API_BASE_URL=http://127.0.0.1:18099`.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.conftest import StubApi  # noqa: E402


def main() -> None:
    stub = StubApi(port=int(os.environ.get("FIXTURE_API_PORT", "0")))
    print(f"fixture API listening on {stub.url}", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        stub.stop()


if __name__ == "__main__":
    main()
