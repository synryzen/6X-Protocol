import signal
import time

from src.services.daemon_service import WorkflowDaemonService


class DaemonRunner:
    def __init__(self):
        self._shutdown_requested = False
        self.daemon = WorkflowDaemonService()

    def request_shutdown(self, _signum, _frame):
        self._shutdown_requested = True

    def run(self) -> int:
        signal.signal(signal.SIGTERM, self.request_shutdown)
        signal.signal(signal.SIGINT, self.request_shutdown)

        started = self.daemon.start()
        if not started:
            print("6X daemon is already running in this process.", flush=True)
            return 1

        print("6X daemon runner started.", flush=True)
        try:
            while not self._shutdown_requested:
                time.sleep(0.5)
        finally:
            self.daemon.stop()
            print("6X daemon runner stopped.", flush=True)

        return 0


def main() -> int:
    runner = DaemonRunner()
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main())
