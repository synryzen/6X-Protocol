import subprocess
import sys
from pathlib import Path
from typing import Dict, Tuple


class SystemdUserService:
    SERVICE_NAME = "6x-protocol-studio.service"

    def __init__(self):
        self.service_dir = Path.home() / ".config" / "systemd" / "user"
        self.service_path = self.service_dir / self.SERVICE_NAME
        self.runner_module = "src.daemon_runner"
        self.project_root = Path(__file__).resolve().parents[2]

    def install(self) -> Tuple[bool, str]:
        available, error = self._systemd_available()
        if not available:
            return False, error

        self.service_dir.mkdir(parents=True, exist_ok=True)
        self.service_path.write_text(self._service_content(), encoding="utf-8")

        ok, message = self._run_systemctl("daemon-reload")
        if not ok:
            return False, message

        return True, f"Installed user service at {self.service_path}."

    def uninstall(self) -> Tuple[bool, str]:
        available, error = self._systemd_available()
        if not available:
            return False, error

        if not self.service_path.exists():
            return False, "Service file is not installed."

        self._run_systemctl("disable", "--now", self.SERVICE_NAME)
        self.service_path.unlink(missing_ok=True)
        ok, message = self._run_systemctl("daemon-reload")
        if not ok:
            return False, message

        return True, "Uninstalled user service."

    def start(self) -> Tuple[bool, str]:
        return self._run_systemctl("start", self.SERVICE_NAME)

    def stop(self) -> Tuple[bool, str]:
        return self._run_systemctl("stop", self.SERVICE_NAME)

    def enable(self) -> Tuple[bool, str]:
        return self._run_systemctl("enable", self.SERVICE_NAME)

    def disable(self) -> Tuple[bool, str]:
        return self._run_systemctl("disable", self.SERVICE_NAME)

    def enable_and_start(self) -> Tuple[bool, str]:
        return self._run_systemctl("enable", "--now", self.SERVICE_NAME)

    def status(self) -> Dict[str, str | bool]:
        available, error = self._systemd_available()
        if not available:
            return {
                "available": False,
                "installed": False,
                "enabled": False,
                "active": False,
                "message": error,
            }

        installed = self.service_path.exists()
        enabled = self._is_enabled()
        active = self._is_active()

        return {
            "available": True,
            "installed": installed,
            "enabled": enabled,
            "active": active,
            "message": "",
        }

    def get_logs(self, lines: int = 120) -> Tuple[bool, str]:
        available, error = self._systemd_available()
        if not available:
            return False, error

        if not self.service_path.exists():
            return False, "Service file is not installed."

        line_count = max(1, min(500, int(lines)))
        try:
            result = subprocess.run(
                [
                    "journalctl",
                    "--user",
                    "-u",
                    self.SERVICE_NAME,
                    "--no-pager",
                    "--output=short-iso",
                    "-n",
                    str(line_count),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return False, "journalctl is not available on this machine."
        except Exception as error:
            return False, f"Failed to query service logs: {error}"

        if result.returncode != 0:
            details = self._format_error(result)
            return False, details or "Unable to read service logs."

        text = (result.stdout or "").strip()
        if not text:
            return True, "No Linux service logs yet."
        return True, text

    def _service_content(self) -> str:
        python_exec = sys.executable
        project_root = str(self.project_root)
        return (
            "[Unit]\n"
            "Description=6X Protocol Studio Background Daemon\n"
            "After=network.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"WorkingDirectory={project_root}\n"
            f"ExecStart={python_exec} -m {self.runner_module}\n"
            "Restart=on-failure\n"
            "RestartSec=3\n"
            "Environment=PYTHONUNBUFFERED=1\n\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )

    def _systemd_available(self) -> Tuple[bool, str]:
        try:
            result = subprocess.run(
                ["systemctl", "--user", "show-environment"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return False, "systemctl is not available on this machine."
        except Exception as error:
            return False, f"Unable to check systemd user session: {error}"

        if result.returncode != 0:
            details = self._format_error(result)
            return False, f"systemd user session unavailable. {details}".strip()

        return True, ""

    def _run_systemctl(self, *args: str) -> Tuple[bool, str]:
        available, error = self._systemd_available()
        if not available:
            return False, error

        try:
            result = subprocess.run(
                ["systemctl", "--user", *args],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as error:
            return False, f"Failed to run systemctl {' '.join(args)}: {error}"

        if result.returncode == 0:
            return True, f"systemctl {' '.join(args)} completed."

        details = self._format_error(result)
        return False, details or f"systemctl {' '.join(args)} failed."

    def _is_enabled(self) -> bool:
        result = subprocess.run(
            ["systemctl", "--user", "is-enabled", self.SERVICE_NAME],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == "enabled"

    def _is_active(self) -> bool:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", self.SERVICE_NAME],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0 and result.stdout.strip() == "active"

    def _format_error(self, result: subprocess.CompletedProcess) -> str:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        return stderr or stdout
