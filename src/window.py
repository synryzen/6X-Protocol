import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib, Gdk

from src.services.daemon_service import get_daemon_service
from src.services.settings_store import SettingsStore
from src.services.systemd_user_service import SystemdUserService
from src.services.tray_service import get_tray_service
from src.ui import create_icon
from src.views.daemon_view import DaemonView
from src.views.dashboard_view import DashboardView
from src.views.workflows_view import WorkflowsView
from src.views.canvas_view import CanvasView
from src.views.bots_view import BotsView
from src.views.runs_view import RunsView
from src.views.integrations_view import IntegrationsView
from src.views.marketplace_view import MarketplaceView
from src.views.settings_view import SettingsView


class MainWindow(Adw.ApplicationWindow):
    THEME_PRESETS = [
        "graphite",
        "indigo",
        "carbon",
        "aurora",
        "frost",
        "sunset",
        "rose",
        "amber",
    ]
    NAV_ITEMS = [
        ("dashboard", "Dashboard", "view-grid-symbolic"),
        ("workflows", "Workflows", "network-workgroup-symbolic"),
        ("canvas", "Canvas", "applications-graphics-symbolic"),
        ("bots", "Bots", "system-users-symbolic"),
        ("runs", "Runs", "document-open-recent-symbolic"),
        ("integrations", "Integrations", "network-wired-symbolic"),
        ("marketplace", "Marketplace", "folder-download-symbolic"),
        ("daemon", "Daemon", "system-run-symbolic"),
        ("settings", "Settings", "emblem-system-symbolic"),
    ]

    def __init__(self, application):
        super().__init__(application=application)
        self.add_css_class("app-window")

        self.set_title("6X-Protocol Studio")
        self.set_default_size(1380, 860)
        self.set_resizable(True)

        self.settings_store = SettingsStore()
        self.daemon_service = get_daemon_service()
        self.systemd_service = SystemdUserService()
        self.tray_service = get_tray_service()
        self._last_canvas_theme_signature: tuple[bool, str, str, bool] | None = None
        self._syncing_nav_selection = False
        self.navigation_rows: dict[str, Gtk.ListBoxRow] = {}

        header_bar = Adw.HeaderBar()
        header_bar.add_css_class("app-headerbar")

        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_box.add_css_class("app-title-box")

        app_title = Gtk.Label(label="6X-Protocol Studio")
        app_title.add_css_class("title-2")
        app_title.set_halign(Gtk.Align.START)

        app_subtitle = Gtk.Label(label="Linux-native automation cockpit")
        app_subtitle.add_css_class("dim-label")
        app_subtitle.set_halign(Gtk.Align.START)

        title_box.append(app_title)
        title_box.append(app_subtitle)
        header_bar.set_title_widget(title_box)

        self.active_view_label = Gtk.Label(label="Dashboard")
        self.active_view_label.add_css_class("app-view-chip")
        header_bar.pack_start(self.active_view_label)

        self.daemon_state_label = Gtk.Label(label="Daemon: Stopped")
        self.daemon_state_label.add_css_class("dim-label")
        self.daemon_state_label.add_css_class("daemon-state-chip")

        self.daemon_toggle_button = Gtk.Button(label="Start Daemon")
        self.daemon_toggle_button.connect("clicked", self.on_daemon_toggle_clicked)
        self.daemon_toggle_button.add_css_class("suggested-action")
        self.daemon_toggle_button.add_css_class("header-action-button")

        self.command_palette_button = Gtk.Button(label="Command Palette")
        self.command_palette_button.connect("clicked", self.on_command_palette_clicked)
        self.command_palette_button.add_css_class("header-action-button")

        header_bar.pack_end(self.command_palette_button)
        header_bar.pack_end(self.daemon_state_label)
        header_bar.pack_end(self.daemon_toggle_button)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(220)
        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)

        self.dashboard_view = DashboardView()
        self.workflows_view = WorkflowsView()
        self.canvas_view = CanvasView()
        self.bots_view = BotsView()
        self.runs_view = RunsView()
        self.integrations_view = IntegrationsView()
        self.marketplace_view = MarketplaceView()
        self.daemon_view = DaemonView(application=application)
        self.settings_view = SettingsView()

        self.stack.add_titled(
            self.wrap_view_for_stack(self.dashboard_view), "dashboard", "Dashboard"
        )
        self.stack.add_titled(
            self.wrap_view_for_stack(self.workflows_view), "workflows", "Workflows"
        )
        self.stack.add_titled(self.wrap_view_for_stack(self.canvas_view), "canvas", "Canvas")
        self.stack.add_titled(self.wrap_view_for_stack(self.bots_view), "bots", "Bots")
        self.stack.add_titled(self.wrap_view_for_stack(self.runs_view), "runs", "Runs")
        self.stack.add_titled(
            self.wrap_view_for_stack(self.integrations_view), "integrations", "Integrations"
        )
        self.stack.add_titled(
            self.wrap_view_for_stack(self.marketplace_view), "marketplace", "Marketplace"
        )
        self.stack.add_titled(self.wrap_view_for_stack(self.daemon_view), "daemon", "Daemon")
        self.stack.add_titled(
            self.wrap_view_for_stack(self.settings_view), "settings", "Settings"
        )
        self.stack.connect("notify::visible-child-name", self.on_visible_child_changed)

        sidebar = self.build_navigation_sidebar()
        sidebar.set_size_request(196, -1)
        sidebar.set_vexpand(True)
        sidebar.add_css_class("navigation-sidebar")

        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.add_css_class("sidebar-scroll")
        sidebar_scroll.set_hexpand(False)
        sidebar_scroll.set_vexpand(True)
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_child(sidebar)

        sidebar_frame = Gtk.Frame()
        sidebar_frame.add_css_class("shell-sidebar")
        sidebar_frame.set_margin_top(7)
        sidebar_frame.set_margin_bottom(7)
        sidebar_frame.set_margin_start(7)
        sidebar_frame.set_margin_end(6)
        sidebar_frame.set_child(sidebar_scroll)

        main_content_frame = Gtk.Frame()
        main_content_frame.add_css_class("shell-content")
        main_content_frame.set_margin_top(7)
        main_content_frame.set_margin_bottom(7)
        main_content_frame.set_margin_start(6)
        main_content_frame.set_margin_end(7)
        main_content_frame.set_hexpand(True)
        main_content_frame.set_vexpand(True)
        main_content_frame.set_child(self.stack)

        content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        content_box.add_css_class("app-shell")
        content_box.append(sidebar_frame)
        content_box.append(main_content_frame)

        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_css_class("app-toolbar-view")
        toolbar_view.add_top_bar(header_bar)
        toolbar_view.set_content(content_box)

        self.set_content(toolbar_view)
        self.command_palette_window: Gtk.Window | None = None
        self.command_palette_entry: Gtk.Entry | None = None
        self.command_palette_list: Gtk.ListBox | None = None
        self.command_palette_empty_label: Gtk.Label | None = None
        self.command_palette_commands: list[dict] = []
        self._install_key_shortcuts()
        self.apply_user_preferences()
        self.apply_startup_preferences()
        self.sync_navigation_selection()
        self.refresh_daemon_controls()
        GLib.timeout_add_seconds(2, self.on_daemon_status_timer)

    def wrap_view_for_stack(self, view: Gtk.Widget) -> Gtk.ScrolledWindow:
        scroller = Gtk.ScrolledWindow()
        scroller.set_hexpand(True)
        scroller.set_vexpand(True)
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_child(view)
        return scroller

    def build_navigation_sidebar(self) -> Gtk.Box:
        sidebar_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        brand_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        brand_box.add_css_class("sidebar-brand")
        brand_box.set_margin_top(6)
        brand_box.set_margin_bottom(4)
        brand_box.set_margin_start(6)
        brand_box.set_margin_end(6)

        brand_kicker = Gtk.Label(label="6X-PROTOCOL STUDIO")
        brand_kicker.add_css_class("sidebar-brand-kicker")
        brand_kicker.set_halign(Gtk.Align.START)

        brand_title = Gtk.Label(label="Operations Cockpit")
        brand_title.add_css_class("sidebar-brand-title")
        brand_title.set_halign(Gtk.Align.START)

        brand_subtitle = Gtk.Label(label="Local-first automation workstation")
        brand_subtitle.add_css_class("dim-label")
        brand_subtitle.add_css_class("sidebar-brand-subtitle")
        brand_subtitle.set_halign(Gtk.Align.START)

        self.sidebar_daemon_label = Gtk.Label(label="Daemon Offline")
        self.sidebar_daemon_label.add_css_class("daemon-state-chip")
        self.sidebar_daemon_label.set_halign(Gtk.Align.START)

        brand_box.append(brand_kicker)
        brand_box.append(brand_title)
        brand_box.append(brand_subtitle)
        brand_box.append(self.sidebar_daemon_label)

        nav_list = Gtk.ListBox()
        nav_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        nav_list.add_css_class("navigation-list")

        for view_name, title, icon_name in self.NAV_ITEMS:
            row = Gtk.ListBoxRow()
            row.set_selectable(True)
            row.set_activatable(True)
            row.set_name(view_name)
            row.add_css_class("navigation-row")

            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            row_box.add_css_class("navigation-row-content")
            row_box.set_margin_top(0)
            row_box.set_margin_bottom(0)
            row_box.set_margin_start(3)
            row_box.set_margin_end(3)

            icon = create_icon(icon_name, css_class="navigation-row-icon")

            label = Gtk.Label(label=title)
            label.set_halign(Gtk.Align.START)
            label.set_hexpand(True)
            label.add_css_class("navigation-row-label")

            row_box.append(icon)
            row_box.append(label)
            row.set_child(row_box)
            nav_list.append(row)
            self.navigation_rows[view_name] = row

        nav_list.connect("row-selected", self.on_navigation_row_selected)
        self.navigation_list = nav_list
        sidebar_box.append(brand_box)
        sidebar_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        sidebar_box.append(nav_list)
        return sidebar_box

    def on_navigation_row_selected(self, _listbox, row: Gtk.ListBoxRow | None):
        if self._syncing_nav_selection or row is None:
            return

        visible_name = row.get_name()
        if visible_name:
            self.stack.set_visible_child_name(visible_name)

    def sync_navigation_selection(self):
        current = self.stack.get_visible_child_name() or "dashboard"
        row = self.navigation_rows.get(current)
        if not row:
            return

        self._syncing_nav_selection = True
        self.navigation_list.select_row(row)
        self._syncing_nav_selection = False

    def on_visible_child_changed(self, stack, _param):
        visible_name = stack.get_visible_child_name()
        visible_title = next(
            (
                title
                for view_name, title, _icon_name in self.NAV_ITEMS
                if view_name == visible_name
            ),
            "Dashboard",
        )
        self.active_view_label.set_text(visible_title)
        self.refresh_visible_view(visible_name)

        self.apply_user_preferences()
        self.sync_navigation_selection()
        self.refresh_daemon_controls()

    def on_daemon_toggle_clicked(self, _button):
        if self.daemon_service.is_running():
            self.daemon_service.stop()
        else:
            systemd_status = self.systemd_service.status()
            if bool(systemd_status.get("active", False)):
                self.daemon_state_label.set_text("Daemon: Managed by Linux service")
                self.daemon_toggle_button.set_sensitive(False)
                self.tray_service.refresh_state(self.daemon_service)
                self.daemon_view.refresh_view()
                return
            self.daemon_service.start()
        self.refresh_daemon_controls()
        self.tray_service.refresh_state(self.daemon_service)
        self.daemon_view.refresh_view()

    def on_daemon_status_timer(self):
        self.refresh_daemon_controls()
        self.tray_service.refresh_state(self.daemon_service)
        return True

    def refresh_visible_view(self, visible_name: str | None):
        if visible_name == "dashboard":
            self.dashboard_view.refresh_data()
        elif visible_name == "workflows":
            self.workflows_view.workflows = self.workflows_view.store.load_workflows()
            self.workflows_view.refresh_list()
        elif visible_name == "canvas":
            self.canvas_view.reload_workflows()
        elif visible_name == "bots":
            self.bots_view.settings = self.bots_view.settings_store.load_settings()
            self.bots_view.bots = self.bots_view.store.load_bots()
            if not self.bots_view.editing_bot_id:
                self.bots_view.reset_form()
            self.bots_view.refresh_list()
        elif visible_name == "runs":
            self.runs_view.on_refresh_clicked(None)
        elif visible_name == "integrations":
            self.integrations_view.refresh_list()
        elif visible_name == "marketplace":
            self.marketplace_view.refresh_list()
            self.canvas_view.reload_templates()
        elif visible_name == "daemon":
            self.daemon_view.refresh_view()
        elif visible_name == "settings":
            self.settings_view.reload_settings()

    def refresh_daemon_controls(self):
        systemd_status = self.systemd_service.status()
        systemd_active = bool(systemd_status.get("active", False))
        running = self.daemon_service.is_running()

        state_classes = [
            "daemon-state-running",
            "daemon-state-stopped",
            "daemon-state-managed",
        ]
        for css_class in state_classes:
            self.daemon_state_label.remove_css_class(css_class)
            if hasattr(self, "sidebar_daemon_label") and self.sidebar_daemon_label:
                self.sidebar_daemon_label.remove_css_class(css_class)

        if systemd_active:
            self.daemon_state_label.set_text("Daemon: Managed by Linux service")
            self.daemon_state_label.add_css_class("daemon-state-managed")
            if hasattr(self, "sidebar_daemon_label") and self.sidebar_daemon_label:
                self.sidebar_daemon_label.set_text("Daemon Managed")
                self.sidebar_daemon_label.add_css_class("daemon-state-managed")
            self.daemon_toggle_button.set_label("Start Daemon")
            self.daemon_toggle_button.set_sensitive(False)
            return

        self.daemon_state_label.set_text(f"Daemon: {'Running' if running else 'Stopped'}")
        self.daemon_state_label.add_css_class(
            "daemon-state-running" if running else "daemon-state-stopped"
        )
        if hasattr(self, "sidebar_daemon_label") and self.sidebar_daemon_label:
            self.sidebar_daemon_label.set_text("Daemon Running" if running else "Daemon Offline")
            self.sidebar_daemon_label.add_css_class(
                "daemon-state-running" if running else "daemon-state-stopped"
            )
        self.daemon_toggle_button.set_label("Stop Daemon" if running else "Start Daemon")
        self.daemon_toggle_button.set_sensitive(True)
        self.tray_service.refresh_state(self.daemon_service)

    def apply_startup_preferences(self):
        settings = self.settings_store.load_settings()
        systemd_status = self.systemd_service.status()
        systemd_active = bool(systemd_status.get("active", False))

        if bool(settings.get("daemon_autostart", False)) and not systemd_active:
            self.daemon_service.start()

        if bool(settings.get("tray_enabled", False)):
            self.tray_service.initialize(
                daemon_service=self.daemon_service,
                on_show_window=self.present,
                on_quit=self.get_application().quit,
            )

    def apply_user_preferences(self):
        settings = self.settings_store.load_settings()

        style_manager = Adw.StyleManager.get_default()
        default_scheme = getattr(
            Adw.ColorScheme,
            "DEFAULT",
            getattr(Adw.ColorScheme, "PREFER_LIGHT"),
        )
        force_dark = getattr(Adw.ColorScheme, "FORCE_DARK")
        force_light = getattr(Adw.ColorScheme, "FORCE_LIGHT")
        theme = settings.get("theme", "system")

        if theme == "dark":
            style_manager.set_color_scheme(force_dark)
            resolved_dark = True
        elif theme == "light":
            style_manager.set_color_scheme(force_light)
            resolved_dark = False
        else:
            style_manager.set_color_scheme(default_scheme)
            resolved_dark = bool(style_manager.get_dark())

        self.remove_css_class("theme-dark")
        self.remove_css_class("theme-light")
        self.add_css_class("theme-dark" if resolved_dark else "theme-light")

        theme_preset = str(settings.get("theme_preset", "graphite")).strip().lower()
        allowed_presets = set(self.THEME_PRESETS)
        if theme_preset not in allowed_presets:
            theme_preset = "graphite"
        for preset in self.THEME_PRESETS:
            self.remove_css_class(f"theme-preset-{preset}")
        self.add_css_class(f"theme-preset-{theme_preset}")

        if self.command_palette_window:
            self.command_palette_window.remove_css_class("theme-dark")
            self.command_palette_window.remove_css_class("theme-light")
            self.command_palette_window.add_css_class(
                "theme-dark" if resolved_dark else "theme-light"
            )
            for preset in self.THEME_PRESETS:
                self.command_palette_window.remove_css_class(f"theme-preset-{preset}")
            self.command_palette_window.add_css_class(f"theme-preset-{theme_preset}")

        density = settings.get("ui_density", "comfortable")
        self.remove_css_class("density-compact")
        self.remove_css_class("density-comfortable")
        if density == "compact":
            self.add_css_class("density-compact")
        else:
            self.add_css_class("density-comfortable")

        if self.command_palette_window:
            self.command_palette_window.remove_css_class("density-compact")
            self.command_palette_window.remove_css_class("density-comfortable")
            self.command_palette_window.add_css_class(
                "density-compact" if density == "compact" else "density-comfortable"
            )

        reduce_motion = bool(settings.get("reduce_motion", False))
        gtk_settings = Gtk.Settings.get_default()
        if gtk_settings:
            gtk_settings.set_property("gtk-enable-animations", not reduce_motion)

        if reduce_motion:
            self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
            self.stack.set_transition_duration(0)
            self.add_css_class("reduce-motion")
            if self.command_palette_window:
                self.command_palette_window.add_css_class("reduce-motion")
        else:
            self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
            self.stack.set_transition_duration(220)
            self.remove_css_class("reduce-motion")
            if self.command_palette_window:
                self.command_palette_window.remove_css_class("reduce-motion")

        canvas_signature = (
            resolved_dark,
            theme_preset,
            str(density),
            reduce_motion,
        )
        should_refresh_canvas = canvas_signature != self._last_canvas_theme_signature
        self._last_canvas_theme_signature = canvas_signature

        # Canvas uses custom Cairo rendering, so refresh only when theme-affecting prefs changed.
        if should_refresh_canvas and hasattr(self, "canvas_view") and self.canvas_view:
            try:
                self.canvas_view.refresh_canvas()
                self.canvas_view.link_layer.queue_draw()
            except Exception:
                pass

    def _install_key_shortcuts(self):
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_global_key_pressed)
        self.add_controller(key_controller)

    def on_global_key_pressed(self, _controller, keyval, _keycode, state):
        control_pressed = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift_pressed = bool(state & Gdk.ModifierType.SHIFT_MASK)

        if control_pressed and keyval in (Gdk.KEY_k, Gdk.KEY_K):
            self.open_command_palette()
            return True

        if control_pressed and keyval in (Gdk.KEY_comma, Gdk.KEY_less):
            self.stack.set_visible_child_name("settings")
            return True

        if control_pressed and not shift_pressed:
            index_map = {
                Gdk.KEY_1: 0,
                Gdk.KEY_2: 1,
                Gdk.KEY_3: 2,
                Gdk.KEY_4: 3,
                Gdk.KEY_5: 4,
                Gdk.KEY_6: 5,
                Gdk.KEY_7: 6,
                Gdk.KEY_8: 7,
                Gdk.KEY_9: 8,
            }
            target_index = index_map.get(keyval, -1)
            if 0 <= target_index < len(self.NAV_ITEMS):
                self.stack.set_visible_child_name(self.NAV_ITEMS[target_index][0])
                return True

        if keyval == Gdk.KEY_Escape and self.command_palette_window:
            if self.command_palette_window.get_visible():
                self.close_command_palette()
                return True

        return False

    def on_command_palette_clicked(self, _button):
        self.open_command_palette()

    def ensure_command_palette(self):
        if self.command_palette_window:
            return

        palette_window = Gtk.Window()
        palette_window.set_title("Command Palette")
        palette_window.set_transient_for(self)
        palette_window.set_modal(True)
        palette_window.set_default_size(640, 480)
        palette_window.add_css_class("app-window")
        palette_window.add_css_class("command-palette-window")
        palette_window.connect("close-request", self.on_command_palette_close_request)

        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_command_palette_key_pressed)
        palette_window.add_controller(key_controller)

        shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        shell.add_css_class("command-palette-shell")
        shell.set_margin_top(10)
        shell.set_margin_bottom(10)
        shell.set_margin_start(10)
        shell.set_margin_end(10)

        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header_row.append(create_icon("system-search-symbolic"))
        header_title = Gtk.Label(label="Command Palette")
        header_title.add_css_class("title-3")
        header_title.add_css_class("command-palette-header-title")
        header_title.set_halign(Gtk.Align.START)
        header_title.set_hexpand(True)
        header_row.append(header_title)

        close_button = Gtk.Button(label="Close")
        close_button.connect("clicked", lambda _button: self.close_command_palette())
        header_row.append(close_button)

        entry = Gtk.Entry()
        entry.add_css_class("command-palette-entry")
        entry.set_placeholder_text("Search commands, pages, and actions...")
        entry.connect("changed", self.on_command_palette_query_changed)
        entry.connect("activate", self.on_command_palette_entry_activate)

        list_box = Gtk.ListBox()
        list_box.add_css_class("command-palette-list")
        list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        list_box.connect("row-activated", self.on_command_palette_row_activated)

        scroll = Gtk.ScrolledWindow()
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_child(list_box)

        empty_label = Gtk.Label(label="No commands match this search.")
        empty_label.add_css_class("dim-label")
        empty_label.add_css_class("empty-state-label")
        empty_label.set_halign(Gtk.Align.START)

        hint = Gtk.Label(
            label="Shortcuts: Ctrl+K palette  •  Ctrl+1..9 pages  •  Ctrl+, settings"
        )
        hint.add_css_class("dim-label")
        hint.add_css_class("command-palette-hint")
        hint.set_halign(Gtk.Align.START)

        shell.append(header_row)
        shell.append(entry)
        shell.append(scroll)
        shell.append(empty_label)
        shell.append(hint)
        palette_window.set_child(shell)

        self.command_palette_window = palette_window
        self.command_palette_entry = entry
        self.command_palette_list = list_box
        self.command_palette_empty_label = empty_label
        self.apply_user_preferences()

    def open_command_palette(self):
        self.ensure_command_palette()
        if not self.command_palette_window or not self.command_palette_entry:
            return

        self.rebuild_command_palette_list()
        self.command_palette_entry.set_text("")
        self.apply_command_palette_filter("")
        self.command_palette_window.present()
        GLib.idle_add(self._focus_command_palette_entry)

    def _focus_command_palette_entry(self):
        if self.command_palette_entry:
            self.command_palette_entry.grab_focus()
        return False

    def on_command_palette_close_request(self, _window):
        self.close_command_palette()
        return True

    def on_command_palette_key_pressed(self, _controller, keyval, _keycode, _state):
        if keyval == Gdk.KEY_Escape:
            self.close_command_palette()
            return True
        return False

    def close_command_palette(self):
        if self.command_palette_window:
            self.command_palette_window.hide()
        self.grab_focus()

    def on_command_palette_query_changed(self, entry: Gtk.Entry):
        self.apply_command_palette_filter(entry.get_text().strip())

    def on_command_palette_entry_activate(self, _entry: Gtk.Entry):
        if not self.command_palette_list:
            return

        row = self.command_palette_list.get_first_child()
        while row:
            if row.get_visible():
                self.command_palette_list.select_row(row)
                self.on_command_palette_row_activated(self.command_palette_list, row)
                return
            row = row.get_next_sibling()

    def on_command_palette_row_activated(self, _list_box, row: Gtk.ListBoxRow):
        command = getattr(row, "command_data", None)
        if not command:
            return
        handler = command.get("handler")
        if callable(handler):
            handler()
        self.close_command_palette()

    def rebuild_command_palette_list(self):
        if not self.command_palette_list:
            return

        child = self.command_palette_list.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.command_palette_list.remove(child)
            child = next_child

        self.command_palette_commands = self.get_command_palette_commands()
        for command in self.command_palette_commands:
            row = Gtk.ListBoxRow()
            row.add_css_class("command-palette-row")
            row.set_activatable(True)
            row.set_selectable(True)
            row.command_data = command
            row.search_blob = (
                f"{command.get('title', '')} {command.get('subtitle', '')} "
                f"{command.get('keywords', '')}"
            ).strip().lower()

            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            content.add_css_class("command-palette-row-content")
            content.set_margin_top(8)
            content.set_margin_bottom(8)
            content.set_margin_start(10)
            content.set_margin_end(10)

            icon = create_icon(
                command.get("icon", "applications-system-symbolic"),
                css_class="command-palette-icon",
            )

            text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            text_box.set_hexpand(True)

            title_label = Gtk.Label(label=command.get("title", "Command"))
            title_label.add_css_class("heading")
            title_label.add_css_class("command-palette-title")
            title_label.set_halign(Gtk.Align.START)

            subtitle_label = Gtk.Label(label=command.get("subtitle", ""))
            subtitle_label.add_css_class("dim-label")
            subtitle_label.add_css_class("command-palette-subtitle")
            subtitle_label.set_halign(Gtk.Align.START)
            subtitle_label.set_wrap(True)

            text_box.append(title_label)
            text_box.append(subtitle_label)

            shortcut_text = command.get("shortcut", "")
            shortcut_label = Gtk.Label(label=shortcut_text)
            shortcut_label.add_css_class("command-palette-shortcut")
            shortcut_label.set_halign(Gtk.Align.END)

            content.append(icon)
            content.append(text_box)
            content.append(shortcut_label)
            row.set_child(content)
            self.command_palette_list.append(row)

    def apply_command_palette_filter(self, query: str):
        if not self.command_palette_list:
            return

        normalized = query.strip().lower()
        tokens = [token for token in normalized.split() if token]
        has_visible = False

        row = self.command_palette_list.get_first_child()
        while row:
            search_blob = getattr(row, "search_blob", "")
            visible = all(token in search_blob for token in tokens)
            row.set_visible(visible)
            has_visible = has_visible or visible
            row = row.get_next_sibling()

        if self.command_palette_empty_label:
            self.command_palette_empty_label.set_visible(not has_visible)

    def get_command_palette_commands(self) -> list[dict]:
        commands: list[dict] = []

        for index, (view_name, title, icon_name) in enumerate(self.NAV_ITEMS):
            commands.append(
                {
                    "title": f"Go to {title}",
                    "subtitle": f"Open the {title} workspace.",
                    "icon": icon_name,
                    "shortcut": f"Ctrl+{index + 1}" if index < 9 else "",
                    "keywords": f"navigate page {view_name} {title.lower()}",
                    "handler": lambda name=view_name: self.stack.set_visible_child_name(name),
                }
            )

        running = self.daemon_service.is_running()
        commands.append(
            {
                "title": "Stop Daemon" if running else "Start Daemon",
                "subtitle": "Toggle local workflow daemon execution.",
                "icon": "process-stop-symbolic" if running else "media-playback-start-symbolic",
                "shortcut": "",
                "keywords": "daemon start stop background",
                "handler": lambda: self.on_daemon_toggle_clicked(None),
            }
        )

        commands.append(
            {
                "title": "Refresh Current View",
                "subtitle": "Reload data and refresh visible page state.",
                "icon": "view-refresh-symbolic",
                "shortcut": "",
                "keywords": "refresh reload update",
                "handler": lambda: self.refresh_visible_view(self.stack.get_visible_child_name()),
            }
        )

        commands.append(
            {
                "title": "Toggle Theme (Dark/Light)",
                "subtitle": "Quick switch between light and dark interface modes.",
                "icon": "weather-clear-night-symbolic",
                "shortcut": "",
                "keywords": "theme dark light",
                "handler": self.toggle_theme_mode,
            }
        )

        commands.append(
            {
                "title": "Cycle Theme Preset",
                "subtitle": "Rotate Graphite, Indigo, Carbon, Aurora, Frost, Sunset, Rose, and Amber.",
                "icon": "applications-graphics-symbolic",
                "shortcut": "",
                "keywords": "theme preset graphite indigo carbon aurora frost sunset rose amber",
                "handler": self.cycle_theme_preset,
            }
        )

        commands.append(
            {
                "title": "Enable Tray" if not self.tray_service.enabled else "Disable Tray",
                "subtitle": "Toggle Linux tray integration for background control.",
                "icon": "preferences-system-symbolic",
                "shortcut": "",
                "keywords": "tray indicator",
                "handler": self.toggle_tray_from_palette,
            }
        )
        commands.extend(self.get_workflows_palette_commands())
        commands.extend(self.get_bots_palette_commands())
        commands.extend(self.get_integrations_palette_commands())
        commands.extend(self.get_runs_palette_commands())
        commands.extend(self.get_canvas_palette_commands())
        return commands

    def get_workflows_palette_commands(self) -> list[dict]:
        return [
            {
                "title": "Workflows: Apply Slack Preset",
                "subtitle": "Load the Slack Alert workflow preset into the workflow form.",
                "icon": "network-workgroup-symbolic",
                "shortcut": "",
                "keywords": "workflow preset slack",
                "handler": lambda: self.apply_workflow_preset_from_palette(0),
            },
            {
                "title": "Workflows: Apply HTTP Sync Preset",
                "subtitle": "Load the HTTP sync workflow preset into the workflow form.",
                "icon": "network-workgroup-symbolic",
                "shortcut": "",
                "keywords": "workflow preset http sync",
                "handler": lambda: self.apply_workflow_preset_from_palette(1),
            },
            {
                "title": "Workflows: Clear Form",
                "subtitle": "Clear workflow name, trigger, and action fields.",
                "icon": "edit-clear-symbolic",
                "shortcut": "",
                "keywords": "workflow clear form",
                "handler": lambda: self.workflows_view.on_clear_form(None),
            },
        ]

    def get_bots_palette_commands(self) -> list[dict]:
        return [
            {
                "title": "Bots: Apply Support Preset",
                "subtitle": "Load Support Assistant bot preset into bot profile fields.",
                "icon": "system-users-symbolic",
                "shortcut": "",
                "keywords": "bot preset support",
                "handler": lambda: self.apply_bot_preset_from_palette(0),
            },
            {
                "title": "Bots: Apply Reviewer Preset",
                "subtitle": "Load Workflow Reviewer bot preset into bot profile fields.",
                "icon": "system-users-symbolic",
                "shortcut": "",
                "keywords": "bot preset reviewer",
                "handler": lambda: self.apply_bot_preset_from_palette(1),
            },
            {
                "title": "Bots: Run Draft Bot Test",
                "subtitle": "Execute bot draft test using current bot form fields.",
                "icon": "system-search-symbolic",
                "shortcut": "",
                "keywords": "bot test draft",
                "handler": lambda: self.bots_view.on_run_form_test(None),
            },
        ]

    def get_integrations_palette_commands(self) -> list[dict]:
        return [
            {
                "title": "Integrations: Refresh List",
                "subtitle": "Reload installed integrations and connector status chips.",
                "icon": "network-wired-symbolic",
                "shortcut": "",
                "keywords": "integrations refresh connectors",
                "handler": lambda: self.integrations_view.on_refresh_clicked(None),
            },
            {
                "title": "Integrations: Test Slack Quick Setup",
                "subtitle": "Run Save + Test for Slack webhook quick setup.",
                "icon": "mail-message-new-symbolic",
                "shortcut": "",
                "keywords": "integration slack test",
                "handler": lambda: self.integrations_view.on_test_slack_quick_setup(None),
            },
            {
                "title": "Integrations: Test OpenWeather Quick Setup",
                "subtitle": "Run Save + Test for OpenWeather quick setup.",
                "icon": "weather-clear-symbolic",
                "shortcut": "",
                "keywords": "integration openweather weather test",
                "handler": lambda: self.integrations_view.on_test_openweather_quick_setup(None),
            },
            {
                "title": "Integrations: Test Notion Quick Setup",
                "subtitle": "Run Save + Test for Notion API quick setup.",
                "icon": "text-x-generic-symbolic",
                "shortcut": "",
                "keywords": "integration notion test",
                "handler": lambda: self.integrations_view.on_test_notion_quick_setup(None),
            },
            {
                "title": "Integrations: Test HubSpot Quick Setup",
                "subtitle": "Run Save + Test for HubSpot API quick setup.",
                "icon": "network-server-symbolic",
                "shortcut": "",
                "keywords": "integration hubspot test",
                "handler": lambda: self.integrations_view.on_test_hubspot_quick_setup(None),
            },
            {
                "title": "Integrations: Test Stripe Quick Setup",
                "subtitle": "Run Save + Test for Stripe API quick setup.",
                "icon": "wallet-open-symbolic",
                "shortcut": "",
                "keywords": "integration stripe test",
                "handler": lambda: self.integrations_view.on_test_stripe_quick_setup(None),
            },
            {
                "title": "Integrations: Test Twilio Quick Setup",
                "subtitle": "Run Save + Test for Twilio SMS quick setup.",
                "icon": "mail-send-symbolic",
                "shortcut": "",
                "keywords": "integration twilio sms test",
                "handler": lambda: self.integrations_view.on_test_twilio_quick_setup(None),
            },
        ]

    def get_runs_palette_commands(self) -> list[dict]:
        return [
            {
                "title": "Runs: Run Selected Workflow",
                "subtitle": "Start a new run from the selected workflow in Runs view.",
                "icon": "media-playback-start-symbolic",
                "shortcut": "",
                "keywords": "runs execute workflow",
                "handler": lambda: self.runs_view.on_run_selected_workflow(None),
            },
            {
                "title": "Runs: Refresh Runs",
                "subtitle": "Reload runs, timeline data, and workflow dropdown.",
                "icon": "view-refresh-symbolic",
                "shortcut": "",
                "keywords": "runs refresh history timeline",
                "handler": lambda: self.runs_view.on_refresh_clicked(None),
            },
        ]

    def get_canvas_palette_commands(self) -> list[dict]:
        return [
            {
                "title": "Canvas: Save Graph",
                "subtitle": "Save current graph to selected workflow.",
                "icon": "document-save-symbolic",
                "shortcut": "",
                "keywords": "canvas save graph",
                "handler": lambda: self.canvas_view.on_save_graph(None),
            },
            {
                "title": "Canvas: Run Preflight",
                "subtitle": "Validate canvas graph and list warnings/errors.",
                "icon": "dialog-warning-symbolic",
                "shortcut": "",
                "keywords": "canvas preflight validate",
                "handler": lambda: self.canvas_view.on_run_preflight_check(None),
            },
            {
                "title": "Canvas: Add AI Node",
                "subtitle": "Insert a new AI node into the graph.",
                "icon": "preferences-system-symbolic",
                "shortcut": "",
                "keywords": "canvas add ai node",
                "handler": lambda: self.canvas_view.on_add_ai(None),
            },
            {
                "title": "Canvas: Undo",
                "subtitle": "Undo last graph edit operation.",
                "icon": "edit-undo-symbolic",
                "shortcut": "Ctrl+Z",
                "keywords": "canvas undo",
                "handler": lambda: self.canvas_view.on_undo_clicked(None),
            },
            {
                "title": "Canvas: Redo",
                "subtitle": "Redo previously undone graph operation.",
                "icon": "edit-redo-symbolic",
                "shortcut": "Ctrl+Shift+Z",
                "keywords": "canvas redo",
                "handler": lambda: self.canvas_view.on_redo_clicked(None),
            },
            {
                "title": "Canvas: Snap To Grid",
                "subtitle": "Snap selected node positions to grid.",
                "icon": "view-grid-symbolic",
                "shortcut": "Ctrl+Shift+G",
                "keywords": "canvas snap grid",
                "handler": lambda: self.canvas_view.on_snap_grid_clicked(None),
            },
            {
                "title": "Canvas: Distribute Horizontally",
                "subtitle": "Distribute selected nodes across horizontal span.",
                "icon": "object-flip-horizontal-symbolic",
                "shortcut": "Ctrl+Shift+D",
                "keywords": "canvas distribute horizontal",
                "handler": lambda: self.canvas_view.on_distribute_x_clicked(None),
            },
            {
                "title": "Canvas: Align Left",
                "subtitle": "Align selected nodes to left edge.",
                "icon": "format-justify-left-symbolic",
                "shortcut": "",
                "keywords": "canvas align left",
                "handler": lambda: self.canvas_view.on_align_left_clicked(None),
            },
            {
                "title": "Canvas: Align Row",
                "subtitle": "Align selected nodes to one row.",
                "icon": "format-justify-fill-symbolic",
                "shortcut": "",
                "keywords": "canvas align row",
                "handler": lambda: self.canvas_view.on_align_row_clicked(None),
            },
        ]

    def apply_workflow_preset_from_palette(self, index: int):
        self.stack.set_visible_child_name("workflows")
        if index < 0 or index >= len(self.workflows_view.workflow_presets):
            return
        self.workflows_view.workflow_preset_dropdown.set_selected(index)
        self.workflows_view.on_apply_workflow_preset(None)

    def apply_bot_preset_from_palette(self, index: int):
        self.stack.set_visible_child_name("bots")
        if index < 0 or index >= len(self.bots_view.bot_presets):
            return
        self.bots_view.bot_preset_dropdown.set_selected(index)
        self.bots_view.on_apply_bot_preset(None)

    def toggle_theme_mode(self):
        settings = self.settings_store.load_settings()
        current = str(settings.get("theme", "dark")).strip().lower()
        settings["theme"] = "light" if current == "dark" else "dark"
        self.settings_store.save_settings(settings)
        self.apply_user_preferences()
        self.settings_view.reload_settings()

    def cycle_theme_preset(self):
        settings = self.settings_store.load_settings()
        current = str(settings.get("theme_preset", "graphite")).strip().lower()
        if current not in self.THEME_PRESETS:
            current = self.THEME_PRESETS[0]
        index = self.THEME_PRESETS.index(current)
        settings["theme_preset"] = self.THEME_PRESETS[(index + 1) % len(self.THEME_PRESETS)]
        self.settings_store.save_settings(settings)
        self.apply_user_preferences()
        self.settings_view.reload_settings()

    def toggle_tray_from_palette(self):
        settings = self.settings_store.load_settings()
        if self.tray_service.enabled:
            message = self.tray_service.shutdown()
            settings["tray_enabled"] = False
        else:
            message = self.tray_service.initialize(
                daemon_service=self.daemon_service,
                on_show_window=self.present,
                on_quit=self.get_application().quit,
            )
            settings["tray_enabled"] = self.tray_service.enabled
        self.settings_store.save_settings(settings)
        self.daemon_view.status_label.set_text(message)
        self.daemon_view.refresh_view()
        self.settings_view.reload_settings()
