from typing import Callable, Optional

from src.services.daemon_service import WorkflowDaemonService


class TrayService:
    def __init__(self):
        self.available = False
        self.enabled = False
        self._indicator = None
        self._gtk3 = None
        self._app_indicator = None
        self._daemon_service = None
        self._status_item = None
        self._start_item = None
        self._stop_item = None

    def initialize(
        self,
        daemon_service: WorkflowDaemonService,
        on_show_window: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> str:
        if self.enabled:
            return "Tray integration is already enabled."

        try:
            import gi

            gi.require_version("Gtk", "3.0")
            from gi.repository import Gtk as Gtk3

            try:
                gi.require_version("AyatanaAppIndicator3", "0.1")
                from gi.repository import AyatanaAppIndicator3 as AppIndicator3
            except Exception:
                gi.require_version("AppIndicator3", "0.1")
                from gi.repository import AppIndicator3
        except Exception as error:
            self.available = False
            self.enabled = False
            return f"System tray integration unavailable: {error}"

        indicator = AppIndicator3.Indicator.new(
            "6x-protocol-studio",
            "applications-system",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        if hasattr(indicator, "set_title"):
            indicator.set_title("6X-Protocol Studio")

        menu = Gtk3.Menu()

        open_item = Gtk3.MenuItem(label="Open 6X-Protocol Studio")
        open_item.connect("activate", lambda _item: on_show_window())
        menu.append(open_item)

        menu.append(Gtk3.SeparatorMenuItem())

        status_item = Gtk3.MenuItem(label="Daemon: Unknown")
        status_item.set_sensitive(False)
        menu.append(status_item)

        start_item = Gtk3.MenuItem(label="Start Daemon")
        start_item.connect("activate", lambda _item: self._start_daemon())
        menu.append(start_item)

        stop_item = Gtk3.MenuItem(label="Stop Daemon")
        stop_item.connect("activate", lambda _item: self._stop_daemon())
        menu.append(stop_item)

        refresh_item = Gtk3.MenuItem(label="Refresh State")
        refresh_item.connect("activate", lambda _item: self.refresh_state())
        menu.append(refresh_item)

        menu.append(Gtk3.SeparatorMenuItem())

        quit_item = Gtk3.MenuItem(label="Quit")
        quit_item.connect("activate", lambda _item: on_quit())
        menu.append(quit_item)

        menu.show_all()
        indicator.set_menu(menu)

        self.available = True
        self.enabled = True
        self._indicator = indicator
        self._gtk3 = Gtk3
        self._app_indicator = AppIndicator3
        self._daemon_service = daemon_service
        self._status_item = status_item
        self._start_item = start_item
        self._stop_item = stop_item
        self.refresh_state(daemon_service)
        return "System tray integration enabled."

    def shutdown(self) -> str:
        if not self.enabled:
            return "Tray integration is already disabled."

        try:
            if self._indicator and self._app_indicator:
                self._indicator.set_status(self._app_indicator.IndicatorStatus.PASSIVE)
        except Exception:
            pass

        self.enabled = False
        self._indicator = None
        self._gtk3 = None
        self._app_indicator = None
        self._daemon_service = None
        self._status_item = None
        self._start_item = None
        self._stop_item = None
        return "System tray integration disabled."

    def refresh_state(self, daemon_service: Optional[WorkflowDaemonService] = None):
        if daemon_service:
            self._daemon_service = daemon_service
        if not self.enabled or not self._daemon_service:
            return

        running = bool(self._daemon_service.is_running())
        if self._status_item:
            self._status_item.set_label("Daemon: Running" if running else "Daemon: Stopped")
        if self._start_item:
            self._start_item.set_sensitive(not running)
        if self._stop_item:
            self._stop_item.set_sensitive(running)

        self._set_indicator_icon("media-playback-start" if running else "media-playback-stop")

    def _set_indicator_icon(self, icon_name: str):
        if not self._indicator:
            return
        try:
            if hasattr(self._indicator, "set_icon_full"):
                self._indicator.set_icon_full(icon_name, "6X-Protocol Studio")
            elif hasattr(self._indicator, "set_icon"):
                self._indicator.set_icon(icon_name)
        except Exception:
            pass

    def _start_daemon(self):
        if not self._daemon_service:
            return
        self._daemon_service.start()
        self.refresh_state()

    def _stop_daemon(self):
        if not self._daemon_service:
            return
        self._daemon_service.stop()
        self.refresh_state()


_tray_service_instance: Optional[TrayService] = None


def get_tray_service() -> TrayService:
    global _tray_service_instance
    if _tray_service_instance is None:
        _tray_service_instance = TrayService()
    return _tray_service_instance
