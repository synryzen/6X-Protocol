import gi
import time

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GLib

from src.services.daemon_service import get_daemon_service
from src.services.systemd_user_service import SystemdUserService
from src.services.tray_service import get_tray_service
from src.ui import build_icon_title, build_icon_section, wrap_horizontal_row


class DaemonView(Gtk.Box):
    def __init__(self, application=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("page-root")
        self.add_css_class("daemon-root")

        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(6)
        self.set_margin_end(6)

        self.application = application
        self.daemon = get_daemon_service()
        self.tray = get_tray_service()
        self.systemd_service = SystemdUserService()
        self._cached_service_logs = "No Linux service logs yet."
        self._last_service_log_refresh = 0.0
        self.log_source = "app"
        self.quick_filter_query = ""

        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        header_box.add_css_class("page-hero")

        subtitle = Gtk.Label(
            label="Run interval-based workflows in the background and control daemon/tray behavior."
        )
        subtitle.set_wrap(True)
        subtitle.set_halign(Gtk.Align.START)
        subtitle.add_css_class("dim-label")

        header_box.append(
            build_icon_title(
                "Background Daemon",
                "system-run-symbolic",
            )
        )
        header_box.append(subtitle)

        header_action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header_action_row.add_css_class("page-action-bar")
        header_action_row.add_css_class("compact-toolbar-row")

        self.quick_filter_entry = Gtk.Entry()
        self.quick_filter_entry.set_hexpand(True)
        self.quick_filter_entry.set_placeholder_text(
            "Quick filter schedules and logs"
        )
        self.quick_filter_entry.connect("changed", self.on_quick_filter_changed)

        clear_filter_button = Gtk.Button(label="Reset")
        clear_filter_button.add_css_class("compact-action-button")
        clear_filter_button.connect("clicked", self.on_clear_quick_filter_clicked)

        header_action_row.append(self.quick_filter_entry)
        header_action_row.append(clear_filter_button)

        controls_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        controls_row.add_css_class("daemon-controls-row")
        controls_row.add_css_class("page-action-bar")

        self.start_button = Gtk.Button(label="Start Daemon")
        self.start_button.connect("clicked", self.on_start_clicked)
        self.start_button.add_css_class("suggested-action")

        self.stop_button = Gtk.Button(label="Stop Daemon")
        self.stop_button.connect("clicked", self.on_stop_clicked)

        self.enable_tray_button = Gtk.Button(label="Enable Tray")
        self.enable_tray_button.connect("clicked", self.on_enable_tray_clicked)

        self.disable_tray_button = Gtk.Button(label="Disable Tray")
        self.disable_tray_button.connect("clicked", self.on_disable_tray_clicked)

        controls_row.append(self.start_button)
        controls_row.append(self.stop_button)
        controls_row.append(self.enable_tray_button)
        controls_row.append(self.disable_tray_button)

        service_controls_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        service_controls_row.add_css_class("page-action-bar")

        self.install_service_button = Gtk.Button(label="Install Service")
        self.install_service_button.connect("clicked", self.on_install_service_clicked)

        self.enable_start_service_button = Gtk.Button(label="Enable + Start Service")
        self.enable_start_service_button.connect("clicked", self.on_enable_start_service_clicked)
        self.enable_start_service_button.add_css_class("suggested-action")

        self.stop_disable_service_button = Gtk.Button(label="Stop + Disable Service")
        self.stop_disable_service_button.connect("clicked", self.on_stop_disable_service_clicked)

        self.uninstall_service_button = Gtk.Button(label="Uninstall Service")
        self.uninstall_service_button.connect("clicked", self.on_uninstall_service_clicked)

        service_controls_row.append(self.install_service_button)
        service_controls_row.append(self.enable_start_service_button)
        service_controls_row.append(self.stop_disable_service_button)
        service_controls_row.append(self.uninstall_service_button)

        self.systemd_state_label = Gtk.Label(label="")
        self.systemd_state_label.set_halign(Gtk.Align.START)
        self.systemd_state_label.add_css_class("dim-label")
        self.systemd_state_label.add_css_class("inline-status")

        self.status_label = Gtk.Label(label="")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.add_css_class("dim-label")
        self.status_label.add_css_class("inline-status")

        self.state_label = Gtk.Label(label="")
        self.state_label.set_halign(Gtk.Align.START)
        self.state_label.add_css_class("heading")
        self.state_label.add_css_class("inline-status")

        schedule_title = build_icon_section(
            "Scheduled Workflows",
            "view-calendar-symbolic",
        )

        self.schedule_label = Gtk.Label(label="")
        self.schedule_label.set_wrap(True)
        self.schedule_label.set_halign(Gtk.Align.START)
        self.schedule_label.add_css_class("dim-label")
        self.schedule_label.add_css_class("empty-state-label")

        logs_title = build_icon_section(
            "Daemon Logs",
            "text-x-log-symbolic",
        )

        logs_controls_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        logs_controls_row.add_css_class("daemon-controls-row")
        logs_controls_row.add_css_class("compact-toolbar-row")
        logs_controls_row.add_css_class("page-action-bar")
        self.log_source_row = self.build_log_source_row()
        self.refresh_logs_button = Gtk.Button(label="Refresh Logs")
        self.refresh_logs_button.add_css_class("compact-action-button")
        self.refresh_logs_button.connect("clicked", self.on_refresh_logs_clicked)
        logs_controls_row.append(self.log_source_row)
        logs_controls_row.append(self.refresh_logs_button)

        self.logs_buffer = Gtk.TextBuffer()
        self.logs_view = Gtk.TextView(buffer=self.logs_buffer)
        self.logs_view.set_editable(False)
        self.logs_view.set_cursor_visible(False)
        self.logs_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)

        logs_scroll = Gtk.ScrolledWindow()
        logs_scroll.set_hexpand(True)
        logs_scroll.set_vexpand(True)
        logs_scroll.set_child(self.logs_view)

        daemon_panel_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        daemon_panel_box.set_margin_top(8)
        daemon_panel_box.set_margin_bottom(8)
        daemon_panel_box.set_margin_start(8)
        daemon_panel_box.set_margin_end(8)
        daemon_panel_box.append(build_icon_section("Daemon Control", "media-playback-start-symbolic"))
        daemon_panel_box.append(wrap_horizontal_row(controls_row))
        daemon_panel_box.append(self.state_label)
        daemon_panel_box.append(self.status_label)
        daemon_panel_box.append(schedule_title)
        daemon_panel_box.append(self.schedule_label)

        daemon_panel = Gtk.Frame()
        daemon_panel.add_css_class("panel-card")
        daemon_panel.add_css_class("entity-form-panel")
        daemon_panel.set_child(daemon_panel_box)

        service_title = build_icon_section(
            "Linux User Service (systemd)",
            "applications-system-symbolic",
        )

        service_subtitle = Gtk.Label(
            label=(
                "Run workflows in the background even when the app window is closed. "
                "This manages a user-level systemd service."
            )
        )
        service_subtitle.set_wrap(True)
        service_subtitle.set_halign(Gtk.Align.START)
        service_subtitle.add_css_class("dim-label")

        service_panel_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        service_panel_box.set_margin_top(8)
        service_panel_box.set_margin_bottom(8)
        service_panel_box.set_margin_start(8)
        service_panel_box.set_margin_end(8)
        service_panel_box.append(service_title)
        service_panel_box.append(service_subtitle)
        service_panel_box.append(wrap_horizontal_row(service_controls_row))
        service_panel_box.append(self.systemd_state_label)

        service_panel = Gtk.Frame()
        service_panel.add_css_class("panel-card")
        service_panel.add_css_class("entity-form-panel")
        service_panel.set_child(service_panel_box)

        logs_panel_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        logs_panel_box.set_margin_top(8)
        logs_panel_box.set_margin_bottom(8)
        logs_panel_box.set_margin_start(8)
        logs_panel_box.set_margin_end(8)
        logs_panel_box.append(logs_title)
        logs_panel_box.append(wrap_horizontal_row(logs_controls_row))
        logs_panel_box.append(logs_scroll)

        logs_panel = Gtk.Frame()
        logs_panel.add_css_class("panel-card")
        logs_panel.add_css_class("entity-form-panel")
        logs_panel.set_hexpand(True)
        logs_panel.set_vexpand(True)
        logs_panel.set_child(logs_panel_box)

        self.append(header_box)
        self.append(header_action_row)
        self.append(daemon_panel)
        self.append(service_panel)
        self.append(logs_panel)

        self.refresh_view()
        GLib.timeout_add_seconds(2, self.on_timer_refresh)

    def on_start_clicked(self, _button):
        systemd_state = self.systemd_service.status()
        if bool(systemd_state.get("active", False)):
            self.status_label.set_text(
                "Local daemon start blocked: Linux service is running."
            )
            self.refresh_view()
            return

        started = self.daemon.start()
        self.status_label.set_text(
            "Daemon started." if started else "Daemon is already running."
        )
        self.refresh_view()

    def on_stop_clicked(self, _button):
        stopped = self.daemon.stop()
        self.status_label.set_text("Daemon stopped." if stopped else "Daemon is not running.")
        self.refresh_view()

    def on_enable_tray_clicked(self, _button):
        message = self.tray.initialize(
            daemon_service=self.daemon,
            on_show_window=self._show_window,
            on_quit=self._quit_application,
        )
        self.status_label.set_text(message)
        self.refresh_view()

    def on_disable_tray_clicked(self, _button):
        message = self.tray.shutdown()
        self.status_label.set_text(message)
        self.refresh_view()

    def on_timer_refresh(self):
        self.refresh_view()
        return True

    def on_quick_filter_changed(self, *_args):
        self.quick_filter_query = self.quick_filter_entry.get_text().strip().lower()
        self.refresh_view(force_logs=True)

    def on_clear_quick_filter_clicked(self, _button):
        self.quick_filter_entry.set_text("")
        self.quick_filter_query = ""
        self.refresh_view(force_logs=True)

    def build_log_source_row(self) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.add_css_class("segmented-row")
        row.add_css_class("compact-segmented-row")

        self.log_source_buttons: dict[str, Gtk.ToggleButton] = {}
        for key, label in [
            ("app", "App Daemon"),
            ("linux", "Linux Service"),
        ]:
            button = Gtk.ToggleButton(label=label)
            button.add_css_class("segmented-button")
            button.add_css_class("compact-segmented-button")
            button.connect("toggled", self.on_log_source_toggled, key)
            row.append(button)
            self.log_source_buttons[key] = button

        self.log_source_buttons["app"].set_active(True)
        return row

    def on_log_source_toggled(self, button: Gtk.ToggleButton, key: str):
        if not button.get_active():
            if not any(item.get_active() for item in self.log_source_buttons.values()):
                button.set_active(True)
            return

        for other_key, other in self.log_source_buttons.items():
            if other_key != key and other.get_active():
                other.set_active(False)
        self.log_source = key
        self.refresh_view(force_logs=True)

    def on_refresh_logs_clicked(self, _button):
        self.refresh_view(force_logs=True)

    def on_install_service_clicked(self, _button):
        ok, message = self.systemd_service.install()
        self.status_label.set_text(message if ok else f"Service install failed: {message}")
        self.refresh_view()

    def on_enable_start_service_clicked(self, _button):
        ok, message = self.systemd_service.enable_and_start()
        self.status_label.set_text(message if ok else f"Service start failed: {message}")
        self.refresh_view()

    def on_stop_disable_service_clicked(self, _button):
        stop_ok, stop_message = self.systemd_service.stop()
        disable_ok, disable_message = self.systemd_service.disable()
        if stop_ok and disable_ok:
            self.status_label.set_text("Service stopped and disabled.")
        elif stop_ok:
            self.status_label.set_text(f"Service stopped, disable failed: {disable_message}")
        elif disable_ok:
            self.status_label.set_text(f"Service disabled, stop failed: {stop_message}")
        else:
            self.status_label.set_text(
                f"Service stop/disable failed: {stop_message or disable_message}"
            )
        self.refresh_view()

    def on_uninstall_service_clicked(self, _button):
        ok, message = self.systemd_service.uninstall()
        self.status_label.set_text(message if ok else f"Service uninstall failed: {message}")
        self.refresh_view()

    def refresh_view(self, force_logs: bool = False):
        daemon_state = "Running" if self.daemon.is_running() else "Stopped"
        tray_state = "Enabled" if self.tray.enabled else "Disabled"
        self.state_label.set_text(f"Daemon: {daemon_state}  •  Tray: {tray_state}")

        systemd_state = self.systemd_service.status()
        if not bool(systemd_state.get("available")):
            self.systemd_state_label.set_text(
                f"Linux user service: unavailable ({systemd_state.get('message', '')})"
            )
            self.install_service_button.set_sensitive(False)
            self.enable_start_service_button.set_sensitive(False)
            self.stop_disable_service_button.set_sensitive(False)
            self.uninstall_service_button.set_sensitive(False)
        else:
            installed = bool(systemd_state.get("installed", False))
            enabled = bool(systemd_state.get("enabled", False))
            active = bool(systemd_state.get("active", False))
            self.systemd_state_label.set_text(
                "Linux user service: "
                f"{'Installed' if installed else 'Not installed'}  •  "
                f"{'Enabled' if enabled else 'Disabled'}  •  "
                f"{'Running' if active else 'Stopped'}"
            )
            self.install_service_button.set_sensitive(not installed)
            self.enable_start_service_button.set_sensitive(installed)
            self.stop_disable_service_button.set_sensitive(installed)
            self.uninstall_service_button.set_sensitive(installed)

        systemd_active = bool(systemd_state.get("active", False))
        self.start_button.set_sensitive(not self.daemon.is_running() and not systemd_active)
        self.stop_button.set_sensitive(self.daemon.is_running())
        self.enable_tray_button.set_sensitive(not self.tray.enabled)
        self.disable_tray_button.set_sensitive(self.tray.enabled)

        schedules = self.daemon.get_schedule_snapshot()
        if not schedules:
            self.schedule_label.set_text("No interval workflows found. Use trigger 'interval:60'.")
        else:
            lines = [
                (
                    f"• {item['workflow_name']}  "
                    f"(every {item['interval_seconds']}s, next in ~{item['next_run_in_seconds']}s)"
                )
                for item in schedules
            ]
            query = self.quick_filter_query
            if query:
                lines = [line for line in lines if query in line.lower()]
            self.schedule_label.set_text(
                "\n".join(lines) if lines else "No scheduled workflows match the current filter."
            )

        self.refresh_logs(force=force_logs)

    def selected_log_source(self) -> str:
        return self.log_source

    def refresh_logs(self, force: bool = False):
        if not hasattr(self, "logs_buffer"):
            return
        source = self.selected_log_source()
        if source == "linux":
            now = time.time()
            if force or (now - self._last_service_log_refresh) >= 4.0:
                ok, text = self.systemd_service.get_logs(lines=120)
                self._cached_service_logs = text if ok else f"Service logs unavailable: {text}"
                self._last_service_log_refresh = now
            lines = str(self._cached_service_logs).splitlines()
            query = self.quick_filter_query
            if query:
                lines = [line for line in lines if query in line.lower()]
            self.logs_buffer.set_text(
                "\n".join(lines) if lines else "No Linux service logs match the current filter."
            )
            return

        logs = self.daemon.get_logs(limit=120)
        query = self.quick_filter_query
        if query:
            logs = [line for line in logs if query in str(line).lower()]
        self.logs_buffer.set_text(
            "\n".join(logs) if logs else "No app daemon logs match the current filter."
        )

    def _show_window(self):
        root = self.get_root()
        if root:
            try:
                root.present()
                return
            except Exception:
                pass

        if self.application and self.application.props.active_window:
            self.application.props.active_window.present()

    def _quit_application(self):
        if self.application:
            self.application.quit()
