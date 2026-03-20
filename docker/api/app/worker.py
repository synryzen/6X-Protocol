"""6X-Protocol worker scaffold process.

This process intentionally stays simple while the runtime extraction is in
progress. It keeps a running worker container alive for compose topology tests.
"""

from __future__ import annotations

import logging
import os
import time

logging.basicConfig(level=logging.INFO, format="[6xp-worker] %(message)s")


def main() -> None:
    interval = float(os.getenv("WORKER_HEARTBEAT_SECONDS", "15"))
    logging.info("Worker scaffold started (interval=%ss)", interval)
    while True:
        logging.info("heartbeat")
        time.sleep(interval)


if __name__ == "__main__":
    main()
