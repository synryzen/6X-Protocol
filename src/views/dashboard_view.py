import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

from src.services.workflow_store import WorkflowStore
from src.services.settings_store import SettingsStore
from src.services.bot_store import BotStore
from src.services.run_store import RunStore
from src.services.integration_registry_service import IntegrationRegistryService
from src.services.template_marketplace_service import TemplateMarketplaceService
from src.services.daemon_service import get_daemon_service
from src.services.systemd_user_service import SystemdUserService
from src.ui import build_icon_title, build_icon_section


class DashboardView(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add_css_class("page-root")
        self.add_css_class("dashboard-root")

        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(6)
        self.set_margin_end(6)

        self.workflow_store = WorkflowStore()
        self.settings_store = SettingsStore()
        self.bot_store = BotStore()
        self.run_store = RunStore()
        self.integration_registry = IntegrationRegistryService()
        self.template_marketplace = TemplateMarketplaceService()
        self.daemon_service = get_daemon_service()
        self.systemd_service = SystemdUserService()
        self.dashboard_scope = "all"
        self.system_line_items: list[tuple[Gtk.Label, str]] = []
        self.next_step_items: list[tuple[Gtk.Label, str]] = []

        hero_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        hero_box.add_css_class("page-hero")
        hero_box.add_css_class("dashboard-hero")

        hero_kicker = Gtk.Label(label="LOCAL-FIRST AUTOMATION STUDIO")
        hero_kicker.add_css_class("hero-kicker")
        hero_kicker.set_halign(Gtk.Align.START)

        subtitle = Gtk.Label(
            label="Build, monitor, and manage workflows, bots, and runtime activity from one desktop-native control center."
        )
        subtitle.set_wrap(True)
        subtitle.set_max_width_chars(90)
        subtitle.set_halign(Gtk.Align.START)
        subtitle.add_css_class("dim-label")

        hero_box.append(hero_kicker)
        hero_box.append(
            build_icon_title(
                "Automation Command Center",
                "applications-system-symbolic",
            )
        )
        hero_box.append(subtitle)

        header_action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header_action_row.add_css_class("page-action-bar")
        header_action_row.add_css_class("compact-toolbar-row")

        self.search_entry = Gtk.Entry()
        self.search_entry.set_hexpand(True)
        self.search_entry.set_placeholder_text("Quick filter system signals and next steps")
        self.search_entry.connect("changed", self.on_dashboard_filter_changed)

        self.scope_filter_row = self.build_scope_filter_row()

        self.reset_filters_button = Gtk.Button(label="Reset")
        self.reset_filters_button.add_css_class("compact-action-button")
        self.reset_filters_button.connect("clicked", self.on_reset_dashboard_filters)

        header_action_row.append(self.search_entry)
        header_action_row.append(self.scope_filter_row)
        header_action_row.append(self.reset_filters_button)

        stats_grid = Gtk.Grid()
        stats_grid.set_column_spacing(16)
        stats_grid.set_row_spacing(16)
        stats_grid.set_hexpand(True)
        stats_grid.add_css_class("dashboard-stats-grid")

        self.workflow_value_label = Gtk.Label(label="0")
        self.bot_value_label = Gtk.Label(label="0")
        self.run_value_label = Gtk.Label(label="0")

        stats_grid.attach(
            self.build_stat_card(
                self.workflow_value_label,
                "Saved Workflows",
                "Workflow definitions currently stored in the app",
                "workflows",
            ),
            0,
            0,
            1,
            1,
        )
        stats_grid.attach(
            self.build_stat_card(
                self.bot_value_label,
                "Saved Bots",
                "Reusable AI bot profiles configured in the app",
                "bots",
            ),
            1,
            0,
            1,
            1,
        )
        stats_grid.attach(
            self.build_stat_card(
                self.run_value_label,
                "Run History",
                "Execution records currently stored locally",
                "runs",
            ),
            2,
            0,
            1,
            1,
        )

        lower_grid = Gtk.Grid()
        lower_grid.set_column_spacing(16)
        lower_grid.set_row_spacing(16)
        lower_grid.set_hexpand(True)
        lower_grid.set_vexpand(True)
        lower_grid.add_css_class("dashboard-lower-grid")

        lower_grid.attach(
            self.build_system_panel(),
            0,
            0,
            2,
            1,
        )

        lower_grid.attach(
            self.build_next_steps_panel(),
            2,
            0,
            1,
            1,
        )

        self.append(hero_box)
        self.append(header_action_row)
        self.append(stats_grid)
        self.append(lower_grid)

        self.refresh_data()

    def build_stat_card(
        self,
        value_label: Gtk.Label,
        title: str,
        subtitle: str,
        variant: str,
    ) -> Gtk.Frame:
        frame = Gtk.Frame()
        frame.set_hexpand(True)
        frame.add_css_class("metric-card")
        frame.add_css_class(f"metric-{variant}")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)

        value_label.add_css_class("title-1")
        value_label.add_css_class("metric-value")
        value_label.set_halign(Gtk.Align.START)

        title_label = Gtk.Label(label=title)
        title_label.add_css_class("heading")
        title_label.set_halign(Gtk.Align.START)

        subtitle_label = Gtk.Label(label=subtitle)
        subtitle_label.set_wrap(True)
        subtitle_label.set_halign(Gtk.Align.START)
        subtitle_label.add_css_class("dim-label")

        box.append(value_label)
        box.append(title_label)
        box.append(subtitle_label)

        frame.set_child(box)
        return frame

    def build_system_panel(self) -> Gtk.Frame:
        frame = Gtk.Frame()
        frame.set_hexpand(True)
        frame.set_vexpand(True)
        frame.add_css_class("panel-card")
        frame.add_css_class("dashboard-system-panel")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)

        title_label = build_icon_section(
            "System Overview",
            "computer-symbolic",
        )

        self.storage_mode_label = self.build_line_label()
        self.workflow_count_label = self.build_line_label()
        self.bot_count_label = self.build_line_label()
        self.run_count_label = self.build_line_label()
        self.local_ai_enabled_label = self.build_line_label()
        self.local_backend_label = self.build_line_label()
        self.preferred_provider_label = self.build_line_label()
        self.local_model_label = self.build_line_label()
        self.openai_key_label = self.build_line_label()
        self.anthropic_key_label = self.build_line_label()
        self.integration_count_label = self.build_line_label()
        self.template_count_label = self.build_line_label()
        self.daemon_status_label = self.build_line_label()
        self.systemd_service_label = self.build_line_label()

        self.system_line_items = [
            (self.storage_mode_label, "runtime"),
            (self.workflow_count_label, "runtime"),
            (self.bot_count_label, "runtime"),
            (self.run_count_label, "runtime"),
            (self.local_ai_enabled_label, "ai"),
            (self.local_backend_label, "ai"),
            (self.preferred_provider_label, "ai"),
            (self.local_model_label, "ai"),
            (self.openai_key_label, "ai"),
            (self.anthropic_key_label, "ai"),
            (self.integration_count_label, "integrations"),
            (self.template_count_label, "integrations"),
            (self.daemon_status_label, "runtime"),
            (self.systemd_service_label, "runtime"),
        ]

        box.append(title_label)
        for label, _category in self.system_line_items:
            box.append(label)

        self.system_empty_label = Gtk.Label(label="No system lines match the current filter.")
        self.system_empty_label.set_halign(Gtk.Align.START)
        self.system_empty_label.add_css_class("dim-label")
        self.system_empty_label.add_css_class("empty-state-label")
        self.system_empty_label.set_visible(False)
        box.append(self.system_empty_label)

        frame.set_child(box)
        return frame

    def build_line_label(self) -> Gtk.Label:
        label = Gtk.Label(label="")
        label.set_wrap(True)
        label.set_halign(Gtk.Align.START)
        label.add_css_class("dashboard-line")
        return label

    def build_next_steps_panel(self) -> Gtk.Frame:
        frame = Gtk.Frame()
        frame.set_hexpand(True)
        frame.set_vexpand(True)
        frame.add_css_class("panel-card")
        frame.add_css_class("panel-accent")
        frame.add_css_class("dashboard-next-panel")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)

        title_label = build_icon_section(
            "Next Recommended Steps",
            "list-add-symbolic",
        )

        box.append(title_label)
        self.next_step_items = []
        for text, category in [
            ("Create workflow definitions in the Workflows page", "runtime"),
            ("Define reusable bot profiles in Bots", "ai"),
            ("Install integrations and templates from Marketplace", "integrations"),
            ("Run interval workflows with the Background Daemon", "runtime"),
        ]:
            label = Gtk.Label(label=f"• {text}")
            label.set_wrap(True)
            label.set_halign(Gtk.Align.START)
            box.append(label)
            self.next_step_items.append((label, category))

        self.next_steps_empty_label = Gtk.Label(label="No recommended steps match the current filter.")
        self.next_steps_empty_label.set_halign(Gtk.Align.START)
        self.next_steps_empty_label.add_css_class("dim-label")
        self.next_steps_empty_label.add_css_class("empty-state-label")
        self.next_steps_empty_label.set_visible(False)
        box.append(self.next_steps_empty_label)

        frame.set_child(box)
        return frame

    def build_scope_filter_row(self) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.add_css_class("segmented-row")
        row.add_css_class("compact-segmented-row")

        self.scope_filter_buttons: dict[str, Gtk.ToggleButton] = {}
        for key, label in [
            ("all", "All"),
            ("runtime", "Runtime"),
            ("ai", "AI"),
            ("integrations", "Integrations"),
        ]:
            button = Gtk.ToggleButton(label=label)
            button.add_css_class("segmented-button")
            button.add_css_class("compact-segmented-button")
            button.connect("toggled", self.on_scope_filter_toggled, key)
            row.append(button)
            self.scope_filter_buttons[key] = button

        self.scope_filter_buttons["all"].set_active(True)
        return row

    def on_scope_filter_toggled(self, button: Gtk.ToggleButton, key: str):
        if not button.get_active():
            if not any(item.get_active() for item in self.scope_filter_buttons.values()):
                button.set_active(True)
            return

        for other_key, other in self.scope_filter_buttons.items():
            if other_key != key and other.get_active():
                other.set_active(False)
        self.dashboard_scope = key
        self.apply_dashboard_filters()

    def on_dashboard_filter_changed(self, *_args):
        self.apply_dashboard_filters()

    def on_reset_dashboard_filters(self, _button):
        self.search_entry.set_text("")
        self.scope_filter_buttons["all"].set_active(True)
        self.apply_dashboard_filters()

    def matches_filter(self, text: str, category: str) -> bool:
        query = self.search_entry.get_text().strip().lower()
        scope = self.dashboard_scope
        if scope != "all" and category != scope:
            return False
        if query and query not in text.lower():
            return False
        return True

    def apply_dashboard_filters(self):
        visible_system_lines = 0
        for label, category in self.system_line_items:
            matches = self.matches_filter(label.get_text(), category)
            label.set_visible(matches)
            if matches:
                visible_system_lines += 1
        if hasattr(self, "system_empty_label"):
            self.system_empty_label.set_visible(visible_system_lines == 0)

        visible_steps = 0
        for label, category in self.next_step_items:
            matches = self.matches_filter(label.get_text(), category)
            label.set_visible(matches)
            if matches:
                visible_steps += 1
        if hasattr(self, "next_steps_empty_label"):
            self.next_steps_empty_label.set_visible(visible_steps == 0)

    def refresh_data(self):
        workflows = self.workflow_store.load_workflows()
        bots = self.bot_store.load_bots()
        runs = self.run_store.load_runs()
        settings = self.settings_store.load_settings()

        workflow_count = len(workflows)
        bot_count = len(bots)
        run_count = len(runs)

        preferred_provider = settings.get("preferred_provider", "local")
        local_backend = settings.get("local_ai_backend", "ollama")
        local_model = settings.get("default_local_model", "")
        local_model_display = local_model if local_model.strip() else "Not set"
        local_ai_enabled = bool(settings.get("local_ai_enabled", True))
        openai_key_connected = bool(settings.get("openai_api_key", "").strip())
        anthropic_key_connected = bool(settings.get("anthropic_api_key", "").strip())
        integration_count = len(self.integration_registry.list_integrations())
        template_count = len(self.template_marketplace.list_templates())
        daemon_running = self.daemon_service.is_running()
        systemd_status = self.systemd_service.status()
        systemd_active = bool(systemd_status.get("active", False))

        self.workflow_value_label.set_text(str(workflow_count))
        self.bot_value_label.set_text(str(bot_count))
        self.run_value_label.set_text(str(run_count))

        self.storage_mode_label.set_text("• Storage mode: Local JSON")
        self.workflow_count_label.set_text(f"• Workflow count: {workflow_count}")
        self.bot_count_label.set_text(f"• Bot count: {bot_count}")
        self.run_count_label.set_text(f"• Run count: {run_count}")
        self.local_ai_enabled_label.set_text(
            f"• Local AI enabled: {'Yes' if local_ai_enabled else 'No'}"
        )
        self.local_backend_label.set_text(f"• Local runtime: {local_backend}")
        self.preferred_provider_label.set_text(
            f"• Preferred provider: {preferred_provider}"
        )
        self.local_model_label.set_text(f"• Default local model: {local_model_display}")
        self.openai_key_label.set_text(
            f"• OpenAI key present: {'Yes' if openai_key_connected else 'No'}"
        )
        self.anthropic_key_label.set_text(
            f"• Anthropic key present: {'Yes' if anthropic_key_connected else 'No'}"
        )
        self.integration_count_label.set_text(f"• Installed integrations: {integration_count}")
        self.template_count_label.set_text(f"• Installed templates: {template_count}")
        if daemon_running and systemd_active:
            self.daemon_status_label.set_text(
                "• Background daemon running: Yes (local + Linux service)"
            )
        else:
            self.daemon_status_label.set_text(
                f"• Background daemon running: {'Yes' if daemon_running else 'No'}"
            )
        if not bool(systemd_status.get("available", False)):
            self.systemd_service_label.set_text("• Linux user service: Unavailable")
        else:
            installed = bool(systemd_status.get("installed", False))
            enabled = bool(systemd_status.get("enabled", False))
            self.systemd_service_label.set_text(
                "• Linux user service: "
                f"{'Installed' if installed else 'Not installed'}, "
                f"{'Enabled' if enabled else 'Disabled'}, "
                f"{'Running' if systemd_active else 'Stopped'}"
            )
        self.apply_dashboard_filters()
