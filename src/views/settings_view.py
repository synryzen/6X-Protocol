import gi
import threading

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GLib

from src.services.ai_service import AIService
from src.services.integration_registry_service import IntegrationRegistryService
from src.services.integration_test_service import IntegrationTestService
from src.services.settings_store import SettingsStore
from src.ui import build_icon_title, build_icon_section, build_labeled_field


class SettingsView(Gtk.Box):
    THEME_PRESET_OPTIONS = [
        "graphite",
        "indigo",
        "carbon",
        "aurora",
        "frost",
        "sunset",
        "rose",
        "amber",
    ]
    THEME_PRESET_LABELS = {
        "graphite": "Midnight Graphite",
        "indigo": "Deep Indigo",
        "carbon": "Carbon Green",
        "aurora": "Aurora Dark",
        "frost": "Frost Silver",
        "sunset": "Sunset Ember",
        "rose": "Rose Neon",
        "amber": "Amber Forge",
    }
    LOCAL_BACKEND_OPTIONS = [
        "ollama",
        "lm_studio",
        "openai_compatible",
        "vllm",
        "llama_cpp",
        "text_generation_webui",
        "jan",
    ]
    THEME_OPTIONS = ["system", "light", "dark"]
    DENSITY_OPTIONS = ["comfortable", "compact"]

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("page-root")
        self.add_css_class("settings-root")

        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(6)
        self.set_margin_end(6)

        self.store = SettingsStore()
        self.ai_service = AIService(settings_store=self.store)
        self.integration_registry = IntegrationRegistryService()
        self.integration_test_service = IntegrationTestService(
            integration_registry=self.integration_registry
        )
        self.settings = {}
        self.theme_preview_buttons: dict[str, Gtk.ToggleButton] = {}
        self._syncing_theme_preview = False

        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        header_box.add_css_class("page-hero")

        subtitle = Gtk.Label(
            label="Configure AI providers, visual style, motion behavior, and background automation."
        )
        subtitle.set_wrap(True)
        subtitle.set_halign(Gtk.Align.START)
        subtitle.add_css_class("dim-label")

        header_box.append(
            build_icon_title(
                "Settings",
                "emblem-system-symbolic",
            )
        )
        header_box.append(subtitle)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content_box.set_margin_top(6)
        content_box.set_margin_bottom(6)
        content_box.set_margin_start(6)
        content_box.set_margin_end(6)

        local_ai_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        local_ai_box.add_css_class("settings-toggle-row")

        local_ai_label = Gtk.Label(label="Enable Local AI")
        local_ai_label.add_css_class("heading")
        local_ai_label.set_halign(Gtk.Align.START)
        local_ai_label.set_hexpand(True)

        self.local_ai_switch = Gtk.Switch()
        self.local_ai_switch.connect("notify::active", self.on_local_ai_toggled)

        local_ai_box.append(local_ai_label)
        local_ai_box.append(self.local_ai_switch)

        self.provider_dropdown = Gtk.DropDown.new_from_strings(
            ["local", "openai", "anthropic"]
        )

        self.local_backend_dropdown = Gtk.DropDown.new_from_strings(
            [self.local_backend_label(item) for item in self.LOCAL_BACKEND_OPTIONS]
        )
        self.local_backend_dropdown.connect(
            "notify::selected",
            self.on_local_backend_changed,
        )

        self.local_endpoint_entry = Gtk.Entry()
        self.local_endpoint_entry.set_placeholder_text("http://localhost:11434")

        self.local_api_key_entry = Gtk.Entry()
        self.local_api_key_entry.set_visibility(False)
        self.local_api_key_entry.set_placeholder_text("Optional API key for local runtime")

        self.local_model_entry = Gtk.Entry()
        self.local_model_entry.set_placeholder_text("Example: llama3.1, mistral, qwen2.5")

        self.openai_entry = Gtk.Entry()
        self.openai_entry.set_visibility(False)
        self.openai_entry.set_placeholder_text("sk-...")

        self.anthropic_entry = Gtk.Entry()
        self.anthropic_entry.set_visibility(False)
        self.anthropic_entry.set_placeholder_text("sk-ant-...")

        self.slack_webhook_entry = Gtk.Entry()
        self.slack_webhook_entry.set_visibility(False)
        self.slack_webhook_entry.set_placeholder_text("https://hooks.slack.com/services/...")

        self.discord_webhook_entry = Gtk.Entry()
        self.discord_webhook_entry.set_visibility(False)
        self.discord_webhook_entry.set_placeholder_text("https://discord.com/api/webhooks/...")

        self.teams_webhook_entry = Gtk.Entry()
        self.teams_webhook_entry.set_visibility(False)
        self.teams_webhook_entry.set_placeholder_text(
            "https://outlook.office.com/webhook/..."
        )

        self.openweather_api_entry = Gtk.Entry()
        self.openweather_api_entry.set_visibility(False)
        self.openweather_api_entry.set_placeholder_text("OpenWeather API key")

        self.google_script_url_entry = Gtk.Entry()
        self.google_script_url_entry.set_placeholder_text(
            "https://script.google.com/macros/s/.../exec"
        )
        self.telegram_token_entry = Gtk.Entry()
        self.telegram_token_entry.set_visibility(False)
        self.telegram_token_entry.set_placeholder_text("Telegram bot token")

        self.telegram_chat_id_entry = Gtk.Entry()
        self.telegram_chat_id_entry.set_placeholder_text("Default chat ID")

        self.gmail_api_key_entry = Gtk.Entry()
        self.gmail_api_key_entry.set_visibility(False)
        self.gmail_api_key_entry.set_placeholder_text("Gmail OAuth bearer token")

        self.outlook_api_key_entry = Gtk.Entry()
        self.outlook_api_key_entry.set_visibility(False)
        self.outlook_api_key_entry.set_placeholder_text(
            "Outlook / Microsoft Graph OAuth bearer token"
        )

        self.gmail_from_entry = Gtk.Entry()
        self.gmail_from_entry.set_placeholder_text("alerts@yourdomain.com")

        self.google_sheets_api_key_entry = Gtk.Entry()
        self.google_sheets_api_key_entry.set_visibility(False)
        self.google_sheets_api_key_entry.set_placeholder_text("Google Sheets OAuth bearer token")

        self.google_calendar_api_key_entry = Gtk.Entry()
        self.google_calendar_api_key_entry.set_visibility(False)
        self.google_calendar_api_key_entry.set_placeholder_text(
            "Google Calendar OAuth bearer token"
        )

        self.google_sheets_sheet_id_entry = Gtk.Entry()
        self.google_sheets_sheet_id_entry.set_placeholder_text("Spreadsheet ID")

        self.google_sheets_range_entry = Gtk.Entry()
        self.google_sheets_range_entry.set_placeholder_text("Sheet1!A:B")

        self.notion_api_key_entry = Gtk.Entry()
        self.notion_api_key_entry.set_visibility(False)
        self.notion_api_key_entry.set_placeholder_text("Notion API key")

        self.airtable_api_key_entry = Gtk.Entry()
        self.airtable_api_key_entry.set_visibility(False)
        self.airtable_api_key_entry.set_placeholder_text("Airtable API key")

        self.hubspot_api_key_entry = Gtk.Entry()
        self.hubspot_api_key_entry.set_visibility(False)
        self.hubspot_api_key_entry.set_placeholder_text("HubSpot private app token")

        self.stripe_api_key_entry = Gtk.Entry()
        self.stripe_api_key_entry.set_visibility(False)
        self.stripe_api_key_entry.set_placeholder_text("Stripe secret key")

        self.jira_api_key_entry = Gtk.Entry()
        self.jira_api_key_entry.set_visibility(False)
        self.jira_api_key_entry.set_placeholder_text("Jira API token")

        self.asana_api_key_entry = Gtk.Entry()
        self.asana_api_key_entry.set_visibility(False)
        self.asana_api_key_entry.set_placeholder_text("Asana personal access token")

        self.clickup_api_key_entry = Gtk.Entry()
        self.clickup_api_key_entry.set_visibility(False)
        self.clickup_api_key_entry.set_placeholder_text("ClickUp API token")

        self.trello_api_key_entry = Gtk.Entry()
        self.trello_api_key_entry.set_visibility(False)
        self.trello_api_key_entry.set_placeholder_text("Trello API token/key")

        self.monday_api_key_entry = Gtk.Entry()
        self.monday_api_key_entry.set_visibility(False)
        self.monday_api_key_entry.set_placeholder_text("Monday.com API token")

        self.zendesk_api_key_entry = Gtk.Entry()
        self.zendesk_api_key_entry.set_visibility(False)
        self.zendesk_api_key_entry.set_placeholder_text("Zendesk API token")

        self.pipedrive_api_key_entry = Gtk.Entry()
        self.pipedrive_api_key_entry.set_visibility(False)
        self.pipedrive_api_key_entry.set_placeholder_text("Pipedrive API token")

        self.salesforce_api_key_entry = Gtk.Entry()
        self.salesforce_api_key_entry.set_visibility(False)
        self.salesforce_api_key_entry.set_placeholder_text("Salesforce OAuth access token")

        self.gitlab_api_key_entry = Gtk.Entry()
        self.gitlab_api_key_entry.set_visibility(False)
        self.gitlab_api_key_entry.set_placeholder_text("GitLab API token")

        self.twilio_sid_entry = Gtk.Entry()
        self.twilio_sid_entry.set_placeholder_text("Twilio Account SID")

        self.twilio_token_entry = Gtk.Entry()
        self.twilio_token_entry.set_visibility(False)
        self.twilio_token_entry.set_placeholder_text("Twilio Auth Token")

        self.twilio_from_entry = Gtk.Entry()
        self.twilio_from_entry.set_placeholder_text("+15550001111")

        self.github_api_key_entry = Gtk.Entry()
        self.github_api_key_entry.set_visibility(False)
        self.github_api_key_entry.set_placeholder_text("GitHub token")

        self.linear_api_key_entry = Gtk.Entry()
        self.linear_api_key_entry.set_visibility(False)
        self.linear_api_key_entry.set_placeholder_text("Linear API key")

        self.resend_api_key_entry = Gtk.Entry()
        self.resend_api_key_entry.set_visibility(False)
        self.resend_api_key_entry.set_placeholder_text("Resend API key")

        self.resend_from_entry = Gtk.Entry()
        self.resend_from_entry.set_placeholder_text("alerts@yourdomain.com")

        self.mailgun_api_key_entry = Gtk.Entry()
        self.mailgun_api_key_entry.set_visibility(False)
        self.mailgun_api_key_entry.set_placeholder_text("Mailgun API key")

        self.mailgun_domain_entry = Gtk.Entry()
        self.mailgun_domain_entry.set_placeholder_text("mg.yourdomain.com")

        self.mailgun_from_entry = Gtk.Entry()
        self.mailgun_from_entry.set_placeholder_text("alerts@yourdomain.com")

        self.postgres_conn_entry = Gtk.Entry()
        self.postgres_conn_entry.set_placeholder_text("postgres://user:pass@localhost:5432/db")

        self.mysql_conn_entry = Gtk.Entry()
        self.mysql_conn_entry.set_placeholder_text("mysql://user:pass@localhost:3306/db")

        self.redis_conn_entry = Gtk.Entry()
        self.redis_conn_entry.set_placeholder_text("redis://localhost:6379/0")

        self.theme_segment = self.build_segmented_control(
            self.THEME_OPTIONS,
            {
                "system": "System",
                "light": "Light",
                "dark": "Dark",
            },
        )

        self.theme_preset_dropdown = Gtk.DropDown.new_from_strings(
            [self.theme_preset_label(item) for item in self.THEME_PRESET_OPTIONS]
        )
        self.theme_preset_dropdown.connect(
            "notify::selected",
            self.on_theme_preset_dropdown_changed,
        )
        self.theme_preset_gallery = self.build_theme_preset_gallery()

        self.density_segment = self.build_segmented_control(
            self.DENSITY_OPTIONS,
            {
                "comfortable": "Comfortable",
                "compact": "Compact",
            },
        )

        motion_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        motion_box.add_css_class("settings-toggle-row")
        motion_label = Gtk.Label(label="Reduce Motion")
        motion_label.add_css_class("heading")
        motion_label.set_halign(Gtk.Align.START)
        motion_label.set_hexpand(True)
        self.motion_switch = Gtk.Switch()
        motion_box.append(motion_label)
        motion_box.append(self.motion_switch)

        daemon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        daemon_box.add_css_class("settings-toggle-row")
        daemon_label = Gtk.Label(label="Auto-start Background Daemon")
        daemon_label.add_css_class("heading")
        daemon_label.set_halign(Gtk.Align.START)
        daemon_label.set_hexpand(True)
        self.daemon_switch = Gtk.Switch()
        daemon_box.append(daemon_label)
        daemon_box.append(self.daemon_switch)

        tray_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        tray_box.add_css_class("settings-toggle-row")
        tray_label = Gtk.Label(label="Enable Tray On Launch")
        tray_label.add_css_class("heading")
        tray_label.set_halign(Gtk.Align.START)
        tray_label.set_hexpand(True)
        self.tray_switch = Gtk.Switch()
        tray_box.append(tray_label)
        tray_box.append(self.tray_switch)

        self.status_label = Gtk.Label(label="")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.add_css_class("dim-label")
        self.status_label.add_css_class("inline-status")

        self.appearance_status_label = Gtk.Label(label="")
        self.appearance_status_label.set_halign(Gtk.Align.START)
        self.appearance_status_label.set_wrap(True)
        self.appearance_status_label.add_css_class("dim-label")
        self.appearance_status_label.add_css_class("inline-status")

        save_button = Gtk.Button(label="Save Settings")
        save_button.connect("clicked", self.on_save_clicked)
        save_button.set_halign(Gtk.Align.START)
        save_button.add_css_class("suggested-action")

        self.apply_theme_button = Gtk.Button(label="Apply Theme")
        self.apply_theme_button.connect("clicked", self.on_apply_theme_clicked)
        self.apply_theme_button.set_halign(Gtk.Align.START)
        self.apply_theme_button.add_css_class("suggested-action")
        self.apply_theme_button.add_css_class("compact-action-button")

        save_and_test_button = Gtk.Button(label="Save + Run AI Test")
        save_and_test_button.connect("clicked", self.on_save_and_test_clicked)

        self.ai_test_provider_dropdown = Gtk.DropDown.new_from_strings(
            ["preferred", "local", "openai", "anthropic"]
        )
        self.ai_test_provider_dropdown.set_selected(0)

        self.ai_test_model_entry = Gtk.Entry()
        self.ai_test_model_entry.set_placeholder_text("Optional model override for this test")

        self.ai_test_system_entry = Gtk.Entry()
        self.ai_test_system_entry.set_placeholder_text("Optional system prompt override")

        self.ai_test_temp_override_switch = Gtk.Switch()
        self.ai_test_temp_override_switch.connect(
            "notify::active",
            self.on_ai_test_temp_override_toggled,
        )
        self.ai_test_temperature_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            0.0,
            2.0,
            0.01,
        )
        self.ai_test_temperature_scale.set_draw_value(False)
        self.ai_test_temperature_scale.set_hexpand(True)
        self.ai_test_temperature_spin = Gtk.SpinButton.new_with_range(0.0, 2.0, 0.01)
        self.ai_test_temperature_spin.set_digits(2)
        self.ai_test_temperature_spin.set_numeric(True)
        self.ai_test_temperature_spin.set_width_chars(5)
        self.ai_test_temperature_scale.connect(
            "value-changed",
            self.on_temperature_scale_changed,
        )
        self.ai_test_temperature_spin.connect(
            "value-changed",
            self.on_temperature_spin_changed,
        )
        temperature_control_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        temperature_control_row.add_css_class("settings-adjust-row")
        temperature_control_row.append(self.ai_test_temperature_scale)
        temperature_control_row.append(self.ai_test_temperature_spin)

        self.ai_test_tokens_override_switch = Gtk.Switch()
        self.ai_test_tokens_override_switch.connect(
            "notify::active",
            self.on_ai_test_tokens_override_toggled,
        )
        self.ai_test_max_tokens_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            64,
            64000,
            32,
        )
        self.ai_test_max_tokens_scale.set_draw_value(False)
        self.ai_test_max_tokens_scale.set_hexpand(True)
        self.ai_test_max_tokens_spin = Gtk.SpinButton.new_with_range(64, 64000, 32)
        self.ai_test_max_tokens_spin.set_digits(0)
        self.ai_test_max_tokens_spin.set_numeric(True)
        self.ai_test_max_tokens_spin.set_width_chars(6)
        self.ai_test_max_tokens_scale.connect(
            "value-changed",
            self.on_max_tokens_scale_changed,
        )
        self.ai_test_max_tokens_spin.connect(
            "value-changed",
            self.on_max_tokens_spin_changed,
        )
        max_tokens_control_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        max_tokens_control_row.add_css_class("settings-adjust-row")
        max_tokens_control_row.append(self.ai_test_max_tokens_scale)
        max_tokens_control_row.append(self.ai_test_max_tokens_spin)

        self.ai_test_prompt_buffer = Gtk.TextBuffer()
        self.ai_test_prompt_view = Gtk.TextView(buffer=self.ai_test_prompt_buffer)
        self.ai_test_prompt_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.ai_test_prompt_view.set_size_request(-1, 78)

        prompt_frame = Gtk.Frame()
        prompt_frame.add_css_class("canvas-edit-detail-frame")
        prompt_frame.set_child(self.ai_test_prompt_view)

        self.ai_test_output_buffer = Gtk.TextBuffer()
        self.ai_test_output_view = Gtk.TextView(buffer=self.ai_test_output_buffer)
        self.ai_test_output_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.ai_test_output_view.set_editable(False)
        self.ai_test_output_view.set_cursor_visible(False)
        self.ai_test_output_view.set_size_request(-1, 104)

        output_frame = Gtk.Frame()
        output_frame.add_css_class("canvas-edit-detail-frame")
        output_frame.set_child(self.ai_test_output_view)

        self.ai_models_status_label = Gtk.Label(label="")
        self.ai_models_status_label.set_wrap(True)
        self.ai_models_status_label.set_halign(Gtk.Align.START)
        self.ai_models_status_label.add_css_class("dim-label")
        self.ai_models_status_label.add_css_class("inline-status")

        self.ai_test_status_label = Gtk.Label(label="")
        self.ai_test_status_label.set_wrap(True)
        self.ai_test_status_label.set_halign(Gtk.Align.START)
        self.ai_test_status_label.add_css_class("dim-label")
        self.ai_test_status_label.add_css_class("inline-status")

        self.ai_test_button = Gtk.Button(label="Run AI Test")
        self.ai_test_button.connect("clicked", self.on_ai_test_clicked)
        self.ai_test_button.add_css_class("suggested-action")

        self.fetch_models_button = Gtk.Button(label="Fetch Local Models")
        self.fetch_models_button.connect("clicked", self.on_fetch_models_clicked)
        clear_ai_test_output_button = Gtk.Button(label="Clear Output")
        clear_ai_test_output_button.connect("clicked", self.on_clear_ai_test_output)

        runtime_action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        runtime_action_row.add_css_class("compact-action-row")
        runtime_action_row.append(save_button)
        runtime_action_row.append(self.fetch_models_button)

        ai_test_action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        ai_test_action_row.add_css_class("compact-action-row")
        ai_test_action_row.append(self.ai_test_button)
        ai_test_action_row.append(clear_ai_test_output_button)
        ai_test_action_row.append(save_and_test_button)

        self.settings_stack = Gtk.Stack()
        self.settings_stack.set_hexpand(True)
        self.settings_stack.set_vexpand(True)
        self.settings_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        stack_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        stack_actions.add_css_class("canvas-toolbar-row")
        stack_actions.add_css_class("compact-toolbar-row")
        stack_actions.add_css_class("page-action-bar")

        self.stack_search_entry = Gtk.Entry()
        self.stack_search_entry.set_hexpand(True)
        self.stack_search_entry.set_placeholder_text(
            "Quick jump  •  runtime, ai test, appearance, integrations, automation"
        )
        self.stack_search_entry.connect("changed", self.on_stack_search_changed)

        clear_stack_search_button = Gtk.Button(label="Clear")
        clear_stack_search_button.add_css_class("compact-action-button")
        clear_stack_search_button.connect("clicked", self.on_clear_stack_search)

        stack_actions.append(self.stack_search_entry)
        stack_actions.append(clear_stack_search_button)

        stack_switcher = Gtk.StackSwitcher()
        stack_switcher.set_stack(self.settings_stack)
        stack_switcher.set_halign(Gtk.Align.START)
        stack_switcher.add_css_class("settings-stack-switcher")

        runtime_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        runtime_page.add_css_class("settings-page")
        runtime_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        runtime_row.add_css_class("settings-panel-row")
        runtime_row.set_homogeneous(True)

        runtime_core_panel = self.build_settings_subpanel(
            "Local Runtime",
            "preferences-system-network-symbolic",
            [
                local_ai_box,
                build_labeled_field("Runtime Profile", self.local_backend_dropdown),
                build_labeled_field("Endpoint URL", self.local_endpoint_entry),
                build_labeled_field("Default Local Model", self.local_model_entry),
            ],
        )
        runtime_core_panel.set_hexpand(True)

        runtime_providers_panel = self.build_settings_subpanel(
            "Provider Routing",
            "dialog-password-symbolic",
            [
                build_labeled_field("Preferred AI Provider", self.provider_dropdown),
                build_labeled_field("Local Runtime API Key (Optional)", self.local_api_key_entry),
                build_labeled_field("OpenAI API Key", self.openai_entry),
                build_labeled_field("Anthropic API Key", self.anthropic_entry),
            ],
        )
        runtime_providers_panel.set_hexpand(True)

        runtime_row.append(runtime_core_panel)
        runtime_row.append(runtime_providers_panel)
        runtime_page.append(runtime_row)
        runtime_page.append(
            self.build_settings_subpanel(
                "Runtime Actions",
                "system-run-symbolic",
                [runtime_action_row, self.ai_models_status_label],
            )
        )

        test_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        test_page.add_css_class("settings-page")
        test_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        test_row.add_css_class("settings-panel-row")
        test_row.set_homogeneous(True)

        test_request_panel = self.build_settings_subpanel(
            "Request Setup",
            "system-search-symbolic",
            [
                build_labeled_field("Test Provider", self.ai_test_provider_dropdown),
                build_labeled_field("Test Model Override", self.ai_test_model_entry),
                build_labeled_field("Test System Prompt", self.ai_test_system_entry),
            ],
        )
        test_request_panel.set_hexpand(True)

        test_tuning_panel = self.build_settings_subpanel(
            "Tuning Overrides",
            "preferences-system-symbolic",
            [
                build_labeled_field(
                    "Override Temperature For Test",
                    self.ai_test_temp_override_switch,
                    compact=True,
                ),
                build_labeled_field("Temperature", temperature_control_row),
                build_labeled_field(
                    "Override Max Tokens For Test",
                    self.ai_test_tokens_override_switch,
                    compact=True,
                ),
                build_labeled_field("Max Tokens", max_tokens_control_row),
            ],
        )
        test_tuning_panel.set_hexpand(True)

        test_row.append(test_request_panel)
        test_row.append(test_tuning_panel)
        test_page.append(test_row)
        test_page.append(
            self.build_settings_subpanel(
                "AI Test Actions",
                "system-run-symbolic",
                [ai_test_action_row, self.ai_test_status_label],
            )
        )

        io_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        io_row.add_css_class("settings-panel-row")
        io_row.set_homogeneous(True)

        prompt_panel = self.build_settings_subpanel(
            "Prompt",
            "edit-symbolic",
            [build_labeled_field("Test Prompt", prompt_frame)],
        )
        prompt_panel.set_hexpand(True)

        output_panel = self.build_settings_subpanel(
            "Output",
            "text-x-generic-symbolic",
            [build_labeled_field("AI Test Output", output_frame)],
        )
        output_panel.set_hexpand(True)

        io_row.append(prompt_panel)
        io_row.append(output_panel)
        test_page.append(io_row)

        appearance_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        appearance_page.add_css_class("settings-page")
        appearance_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        appearance_row.add_css_class("settings-panel-row")
        appearance_row.set_homogeneous(True)

        appearance_theme_panel = self.build_settings_subpanel(
            "Theme Manager",
            "applications-graphics-symbolic",
            [
                build_labeled_field("Theme", self.theme_segment),
                build_labeled_field("Theme Preset", self.theme_preset_dropdown),
                build_labeled_field("Preset Gallery", self.theme_preset_gallery),
                build_labeled_field("UI Density", self.density_segment),
                self.build_appearance_actions_row(),
                self.appearance_status_label,
            ],
        )
        appearance_theme_panel.set_hexpand(True)

        appearance_behavior_panel = self.build_settings_subpanel(
            "Display Behavior",
            "video-display-symbolic",
            [motion_box],
        )
        appearance_behavior_panel.set_hexpand(True)

        appearance_row.append(appearance_theme_panel)
        appearance_row.append(appearance_behavior_panel)
        appearance_page.append(appearance_row)

        integrations_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        integrations_page.add_css_class("settings-page")
        integrations_row_top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        integrations_row_top.add_css_class("settings-panel-row")
        integrations_row_top.set_homogeneous(True)

        comms_panel = self.build_settings_subpanel(
            "Messaging Connectors",
            "mail-send-symbolic",
            [
                build_labeled_field("Slack Webhook URL", self.slack_webhook_entry),
                build_labeled_field("Discord Webhook URL", self.discord_webhook_entry),
                build_labeled_field("Teams Webhook URL", self.teams_webhook_entry),
                build_labeled_field("Telegram Bot Token", self.telegram_token_entry),
                build_labeled_field("Telegram Default Chat ID", self.telegram_chat_id_entry),
                build_labeled_field("Twilio Account SID", self.twilio_sid_entry),
                build_labeled_field("Twilio Auth Token", self.twilio_token_entry),
                build_labeled_field("Twilio From Number", self.twilio_from_entry),
            ],
        )
        comms_panel.set_hexpand(True)

        google_panel = self.build_settings_subpanel(
            "Google + Weather",
            "network-server-symbolic",
            [
                build_labeled_field("OpenWeather API Key", self.openweather_api_entry),
                build_labeled_field("Google Apps Script URL", self.google_script_url_entry),
                build_labeled_field("Google Sheets API Key", self.google_sheets_api_key_entry),
                build_labeled_field("Google Calendar API Key", self.google_calendar_api_key_entry),
                build_labeled_field("Google Sheets Spreadsheet ID", self.google_sheets_sheet_id_entry),
                build_labeled_field("Google Sheets Range", self.google_sheets_range_entry),
                build_labeled_field("Gmail API Key", self.gmail_api_key_entry),
                build_labeled_field("Gmail From Address", self.gmail_from_entry),
            ],
        )
        google_panel.set_hexpand(True)

        integrations_row_top.append(comms_panel)
        integrations_row_top.append(google_panel)
        integrations_page.append(integrations_row_top)

        integrations_row_bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        integrations_row_bottom.add_css_class("settings-panel-row")
        integrations_row_bottom.set_homogeneous(True)

        api_panel = self.build_settings_subpanel(
            "SaaS API Tokens",
            "applications-internet-symbolic",
            [
                build_labeled_field("Notion API Key", self.notion_api_key_entry),
                build_labeled_field("Airtable API Key", self.airtable_api_key_entry),
                build_labeled_field("HubSpot API Key", self.hubspot_api_key_entry),
                build_labeled_field("Stripe API Key", self.stripe_api_key_entry),
                build_labeled_field("Jira API Key", self.jira_api_key_entry),
                build_labeled_field("Asana API Key", self.asana_api_key_entry),
                build_labeled_field("ClickUp API Key", self.clickup_api_key_entry),
                build_labeled_field("Trello API Key", self.trello_api_key_entry),
                build_labeled_field("Monday API Key", self.monday_api_key_entry),
                build_labeled_field("Zendesk API Key", self.zendesk_api_key_entry),
                build_labeled_field("Pipedrive API Key", self.pipedrive_api_key_entry),
                build_labeled_field("Salesforce API Key", self.salesforce_api_key_entry),
                build_labeled_field("GitLab API Key", self.gitlab_api_key_entry),
                build_labeled_field("GitHub API Key", self.github_api_key_entry),
                build_labeled_field("Linear API Key", self.linear_api_key_entry),
                build_labeled_field("Outlook Graph API Key", self.outlook_api_key_entry),
                build_labeled_field("Resend API Key", self.resend_api_key_entry),
                build_labeled_field("Resend From Address", self.resend_from_entry),
                build_labeled_field("Mailgun API Key", self.mailgun_api_key_entry),
                build_labeled_field("Mailgun Domain", self.mailgun_domain_entry),
                build_labeled_field("Mailgun From Address", self.mailgun_from_entry),
            ],
        )
        api_panel.set_hexpand(True)

        database_panel = self.build_settings_subpanel(
            "Database Connections",
            "server-database-symbolic",
            [
                build_labeled_field("Postgres Connection URL", self.postgres_conn_entry),
                build_labeled_field("MySQL Connection URL", self.mysql_conn_entry),
                build_labeled_field("Redis Connection URL", self.redis_conn_entry),
            ],
        )
        database_panel.set_hexpand(True)

        integrations_row_bottom.append(api_panel)
        integrations_row_bottom.append(database_panel)
        integrations_page.append(integrations_row_bottom)

        connector_notes = Gtk.Label(
            label=(
                "Action nodes can use integration directives directly. If a directive omits "
                "credentials, execution falls back to these saved connector settings."
            )
        )
        connector_notes.set_wrap(True)
        connector_notes.set_halign(Gtk.Align.START)
        connector_notes.add_css_class("dim-label")
        connector_notes.add_css_class("inline-status")
        integrations_page.append(
            self.build_settings_subpanel(
                "Connector Notes",
                "dialog-information-symbolic",
                [connector_notes],
            )
        )

        self.connector_test_keys: list[str] = []
        self.connector_test_dropdown = Gtk.DropDown.new_from_strings(["No connectors"])
        self.connector_test_dropdown.set_hexpand(True)
        self.connector_test_dropdown.connect(
            "notify::selected",
            self.on_connector_test_selection_changed,
        )
        self.rebuild_connector_test_dropdown()

        self.connector_test_input_entry = Gtk.Entry()
        self.connector_test_input_entry.set_placeholder_text("Optional test input context")

        self.connector_test_directives_buffer = Gtk.TextBuffer()
        self.connector_test_directives_view = Gtk.TextView(
            buffer=self.connector_test_directives_buffer
        )
        self.connector_test_directives_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.connector_test_directives_view.set_size_request(-1, 78)
        connector_test_directives_frame = Gtk.Frame()
        connector_test_directives_frame.add_css_class("canvas-edit-detail-frame")
        connector_test_directives_frame.set_child(self.connector_test_directives_view)

        self.connector_test_output_buffer = Gtk.TextBuffer()
        self.connector_test_output_view = Gtk.TextView(
            buffer=self.connector_test_output_buffer
        )
        self.connector_test_output_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.connector_test_output_view.set_editable(False)
        self.connector_test_output_view.set_cursor_visible(False)
        self.connector_test_output_view.set_size_request(-1, 100)
        connector_test_output_frame = Gtk.Frame()
        connector_test_output_frame.add_css_class("canvas-edit-detail-frame")
        connector_test_output_frame.set_child(self.connector_test_output_view)

        self.connector_test_status_label = Gtk.Label(label="")
        self.connector_test_status_label.set_wrap(True)
        self.connector_test_status_label.set_halign(Gtk.Align.START)
        self.connector_test_status_label.add_css_class("dim-label")
        self.connector_test_status_label.add_css_class("inline-status")

        self.connector_test_button = Gtk.Button(label="Save + Test Connector")
        self.connector_test_button.add_css_class("suggested-action")
        self.connector_test_button.add_css_class("compact-action-button")
        self.connector_test_button.connect("clicked", self.on_connector_test_clicked)

        connector_clear_button = Gtk.Button(label="Clear Output")
        connector_clear_button.add_css_class("compact-action-button")
        connector_clear_button.connect("clicked", self.on_clear_connector_test_output)

        connector_test_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        connector_test_actions.add_css_class("compact-action-row")
        connector_test_actions.append(self.connector_test_button)
        connector_test_actions.append(connector_clear_button)

        connector_test_panel = self.build_settings_subpanel(
            "Connector Quick Test",
            "system-search-symbolic",
            [
                build_labeled_field("Connector", self.connector_test_dropdown),
                build_labeled_field("Input Context", self.connector_test_input_entry),
                build_labeled_field("Directives", connector_test_directives_frame),
                connector_test_actions,
                self.connector_test_status_label,
                build_labeled_field("Test Output", connector_test_output_frame),
            ],
        )
        integrations_page.append(connector_test_panel)

        automation_page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        automation_page.add_css_class("settings-page")
        automation_page.append(
            self.build_settings_subpanel(
                "Background Automation",
                "system-run-symbolic",
                [daemon_box, tray_box],
            )
        )

        runtime_scroll = Gtk.ScrolledWindow()
        runtime_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        runtime_scroll.set_child(runtime_page)
        runtime_scroll.add_css_class("settings-page-scroll")

        test_scroll = Gtk.ScrolledWindow()
        test_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        test_scroll.set_child(test_page)
        test_scroll.add_css_class("settings-page-scroll")

        appearance_scroll = Gtk.ScrolledWindow()
        appearance_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        appearance_scroll.set_child(appearance_page)
        appearance_scroll.add_css_class("settings-page-scroll")

        integrations_scroll = Gtk.ScrolledWindow()
        integrations_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        integrations_scroll.set_child(integrations_page)
        integrations_scroll.add_css_class("settings-page-scroll")

        automation_scroll = Gtk.ScrolledWindow()
        automation_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        automation_scroll.set_child(automation_page)
        automation_scroll.add_css_class("settings-page-scroll")

        self.settings_stack.add_titled(runtime_scroll, "runtime", "Runtime")
        self.settings_stack.add_titled(test_scroll, "test", "AI Test")
        self.settings_stack.add_titled(appearance_scroll, "appearance", "Appearance")
        self.settings_stack.add_titled(integrations_scroll, "integrations", "Integrations")
        self.settings_stack.add_titled(automation_scroll, "automation", "Automation")

        content_box.append(stack_actions)
        content_box.append(stack_switcher)
        content_box.append(self.settings_stack)
        content_box.append(self.status_label)

        form_frame = Gtk.Frame()
        form_frame.add_css_class("panel-card")
        form_frame.add_css_class("entity-form-panel")
        form_frame.add_css_class("settings-main-frame")
        form_frame.set_child(content_box)

        self.append(header_box)
        self.append(form_frame)
        self.reload_settings()

    def provider_index(self, value: str) -> int:
        values = ["local", "openai", "anthropic"]
        return values.index(value) if value in values else 0

    def on_stack_search_changed(self, entry: Gtk.Entry):
        query = entry.get_text().strip().lower()
        if not query:
            return

        route_hints: list[tuple[str, list[str], Gtk.Widget | None]] = [
            ("runtime", ["runtime", "endpoint", "local", "lm studio", "ollama", "model"], self.local_endpoint_entry),
            ("runtime", ["openai"], self.openai_entry),
            ("runtime", ["anthropic"], self.anthropic_entry),
            ("runtime", ["provider", "preferred"], self.provider_dropdown),
            ("test", ["test", "console", "prompt"], self.ai_test_prompt_view),
            ("test", ["temperature", "temp"], self.ai_test_temperature_spin),
            ("test", ["tokens", "max"], self.ai_test_max_tokens_spin),
            ("appearance", ["appearance", "theme"], self.theme_preset_dropdown),
            ("appearance", ["density", "compact"], self.density_segment),
            ("appearance", ["motion"], self.motion_switch),
            ("integrations", ["integration", "slack"], self.slack_webhook_entry),
            ("integrations", ["discord"], self.discord_webhook_entry),
            ("integrations", ["teams", "microsoft"], self.teams_webhook_entry),
            ("integrations", ["telegram"], self.telegram_token_entry),
            ("integrations", ["twilio", "sms"], self.twilio_sid_entry),
            ("integrations", ["weather", "openweather"], self.openweather_api_entry),
            ("integrations", ["google", "script"], self.google_script_url_entry),
            ("integrations", ["google", "calendar"], self.google_calendar_api_key_entry),
            ("integrations", ["sheets"], self.google_sheets_sheet_id_entry),
            ("integrations", ["gmail", "email"], self.gmail_api_key_entry),
            ("integrations", ["outlook", "graph"], self.outlook_api_key_entry),
            ("integrations", ["notion"], self.notion_api_key_entry),
            ("integrations", ["airtable"], self.airtable_api_key_entry),
            ("integrations", ["stripe"], self.stripe_api_key_entry),
            ("integrations", ["jira"], self.jira_api_key_entry),
            ("integrations", ["asana"], self.asana_api_key_entry),
            ("integrations", ["clickup"], self.clickup_api_key_entry),
            ("integrations", ["trello"], self.trello_api_key_entry),
            ("integrations", ["monday"], self.monday_api_key_entry),
            ("integrations", ["zendesk"], self.zendesk_api_key_entry),
            ("integrations", ["pipedrive"], self.pipedrive_api_key_entry),
            ("integrations", ["salesforce"], self.salesforce_api_key_entry),
            ("integrations", ["gitlab"], self.gitlab_api_key_entry),
            ("integrations", ["github"], self.github_api_key_entry),
            ("integrations", ["linear"], self.linear_api_key_entry),
            ("integrations", ["resend"], self.resend_api_key_entry),
            ("integrations", ["mailgun"], self.mailgun_api_key_entry),
            ("integrations", ["postgres", "database"], self.postgres_conn_entry),
            ("integrations", ["mysql"], self.mysql_conn_entry),
            ("integrations", ["redis"], self.redis_conn_entry),
            ("automation", ["automation", "daemon"], self.daemon_switch),
            ("automation", ["tray"], self.tray_switch),
        ]

        for page_name, keywords, focus_widget in route_hints:
            if any(query in keyword for keyword in keywords) or any(
                keyword in query for keyword in keywords
            ):
                self.settings_stack.set_visible_child_name(page_name)
                if focus_widget:
                    GLib.idle_add(self.focus_widget, focus_widget)
                return

    def on_clear_stack_search(self, _button):
        self.stack_search_entry.set_text("")

    def focus_widget(self, widget: Gtk.Widget):
        try:
            widget.grab_focus()
        except Exception:
            pass
        return False

    def build_segmented_control(
        self,
        keys: list[str],
        labels: dict[str, str],
    ) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.add_css_class("settings-segmented-row")
        row.set_hexpand(True)

        buttons: dict[str, Gtk.ToggleButton] = {}
        for key in keys:
            button = Gtk.ToggleButton(label=labels.get(key, key.title()))
            button.add_css_class("settings-segment-button")
            button.set_hexpand(True)
            button.connect("toggled", self.on_segment_button_toggled, key, buttons)
            row.append(button)
            buttons[key] = button

        setattr(row, "_segment_keys", keys)
        setattr(row, "_segment_buttons", buttons)
        return row

    def on_segment_button_toggled(
        self,
        button: Gtk.ToggleButton,
        key: str,
        buttons: dict[str, Gtk.ToggleButton],
    ):
        if not button.get_active():
            if not any(item.get_active() for item in buttons.values()):
                button.set_active(True)
            return

        for other_key, other in buttons.items():
            if other_key != key and other.get_active():
                other.set_active(False)

    def set_segmented_value(self, container: Gtk.Box, value: str):
        buttons = getattr(container, "_segment_buttons", {})
        if not buttons:
            return

        normalized = str(value).strip().lower()
        if normalized not in buttons:
            normalized = next(iter(buttons.keys()))
        buttons[normalized].set_active(True)

    def get_segmented_value(self, container: Gtk.Box, fallback: str) -> str:
        buttons = getattr(container, "_segment_buttons", {})
        for key, button in buttons.items():
            if button.get_active():
                return key
        return fallback

    def local_backend_index(self, value: str) -> int:
        values = self.LOCAL_BACKEND_OPTIONS
        return values.index(value) if value in values else 0

    def local_backend_label(self, backend: str) -> str:
        labels = {
            "ollama": "Ollama",
            "lm_studio": "LM Studio",
            "openai_compatible": "OpenAI Compatible",
            "vllm": "vLLM",
            "llama_cpp": "llama.cpp server",
            "text_generation_webui": "Text Generation WebUI",
            "jan": "Jan",
        }
        return labels.get(backend, backend.replace("_", " ").title())

    def build_settings_subpanel(
        self,
        title: str,
        icon_name: str,
        rows: list[Gtk.Widget],
    ) -> Gtk.Frame:
        panel = Gtk.Frame()
        panel.add_css_class("settings-subpanel")
        panel.add_css_class("canvas-edit-detail-frame")

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        body.add_css_class("settings-subpanel-body")
        body.set_margin_top(6)
        body.set_margin_bottom(6)
        body.set_margin_start(6)
        body.set_margin_end(6)
        body.append(build_icon_section(title, icon_name, level="heading"))
        for row in rows:
            body.append(row)

        panel.set_child(body)
        return panel

    def selected_provider(self) -> str:
        values = ["local", "openai", "anthropic"]
        index = self.provider_dropdown.get_selected()
        return values[index] if 0 <= index < len(values) else "local"

    def selected_local_backend(self) -> str:
        values = self.LOCAL_BACKEND_OPTIONS
        index = self.local_backend_dropdown.get_selected()
        return values[index] if 0 <= index < len(values) else "ollama"

    def theme_index(self, value: str) -> int:
        values = self.THEME_OPTIONS
        return values.index(value) if value in values else 0

    def selected_theme(self) -> str:
        return self.get_segmented_value(self.theme_segment, "system")

    def density_index(self, value: str) -> int:
        values = self.DENSITY_OPTIONS
        return values.index(value) if value in values else 0

    def theme_preset_label(self, value: str) -> str:
        key = str(value).strip().lower()
        return self.THEME_PRESET_LABELS.get(key, key.replace("_", " ").title())

    def theme_preset_index(self, value: str) -> int:
        values = self.THEME_PRESET_OPTIONS
        return values.index(value) if value in values else 0

    def selected_density(self) -> str:
        return self.get_segmented_value(self.density_segment, "comfortable")

    def selected_theme_preset(self) -> str:
        values = self.THEME_PRESET_OPTIONS
        index = self.theme_preset_dropdown.get_selected()
        return values[index] if 0 <= index < len(values) else "graphite"

    def build_theme_preset_gallery(self) -> Gtk.FlowBox:
        flow = Gtk.FlowBox()
        flow.add_css_class("theme-preset-gallery")
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_max_children_per_line(2)
        flow.set_min_children_per_line(2)
        flow.set_homogeneous(True)

        self.theme_preview_buttons = {}
        for preset in self.THEME_PRESET_OPTIONS:
            button = Gtk.ToggleButton(label=self.theme_preset_label(preset))
            button.add_css_class("theme-preview-button")
            button.add_css_class(f"theme-preview-{preset}")
            button.connect("toggled", self.on_theme_preview_toggled, preset)
            flow.append(button)
            self.theme_preview_buttons[preset] = button
        return flow

    def on_theme_preview_toggled(
        self,
        button: Gtk.ToggleButton,
        preset: str,
    ):
        if self._syncing_theme_preview:
            return

        if not button.get_active():
            if not any(item.get_active() for item in self.theme_preview_buttons.values()):
                self._syncing_theme_preview = True
                button.set_active(True)
                self._syncing_theme_preview = False
            return

        self.sync_theme_preview_buttons(preset)
        target_index = self.theme_preset_index(preset)
        if self.theme_preset_dropdown.get_selected() != target_index:
            self.theme_preset_dropdown.set_selected(target_index)
        self.appearance_status_label.set_text(
            f"Preset '{self.theme_preset_label(preset)}' selected. Click Apply Theme."
        )

    def on_theme_preset_dropdown_changed(self, *_args):
        if self._syncing_theme_preview:
            return
        preset = self.selected_theme_preset()
        self.sync_theme_preview_buttons(preset)
        self.appearance_status_label.set_text(
            f"Preset '{self.theme_preset_label(preset)}' selected. Click Apply Theme."
        )

    def sync_theme_preview_buttons(self, selected: str):
        self._syncing_theme_preview = True
        try:
            normalized = str(selected).strip().lower()
            for preset, button in self.theme_preview_buttons.items():
                should_be_active = preset == normalized
                if button.get_active() != should_be_active:
                    button.set_active(should_be_active)
        finally:
            self._syncing_theme_preview = False

    def reload_settings(self):
        self.settings = self.store.load_settings()

        self.local_ai_switch.set_active(bool(self.settings.get("local_ai_enabled", True)))
        self.provider_dropdown.set_selected(
            self.provider_index(self.settings.get("preferred_provider", "local"))
        )
        backend = self.settings.get("local_ai_backend", "ollama")
        self.local_backend_dropdown.set_selected(self.local_backend_index(backend))
        endpoint = (
            self.settings.get("local_ai_endpoint", "")
            or self.settings.get("ollama_url", "")
            or self.default_local_endpoint(str(backend))
        )
        self.local_endpoint_entry.set_text(endpoint)
        self.local_api_key_entry.set_text(self.settings.get("local_ai_api_key", ""))
        self.local_model_entry.set_text(self.settings.get("default_local_model", ""))
        self.openai_entry.set_text(self.settings.get("openai_api_key", ""))
        self.anthropic_entry.set_text(self.settings.get("anthropic_api_key", ""))
        self.slack_webhook_entry.set_text(self.settings.get("slack_webhook_url", ""))
        self.discord_webhook_entry.set_text(self.settings.get("discord_webhook_url", ""))
        self.teams_webhook_entry.set_text(self.settings.get("teams_webhook_url", ""))
        self.telegram_token_entry.set_text(self.settings.get("telegram_bot_token", ""))
        self.telegram_chat_id_entry.set_text(self.settings.get("telegram_default_chat_id", ""))
        self.openweather_api_entry.set_text(self.settings.get("openweather_api_key", ""))
        self.google_script_url_entry.set_text(self.settings.get("google_apps_script_url", ""))
        self.google_sheets_api_key_entry.set_text(self.settings.get("google_sheets_api_key", ""))
        self.google_calendar_api_key_entry.set_text(self.settings.get("google_calendar_api_key", ""))
        self.google_sheets_sheet_id_entry.set_text(self.settings.get("google_sheets_spreadsheet_id", ""))
        self.google_sheets_range_entry.set_text(self.settings.get("google_sheets_range", ""))
        self.gmail_api_key_entry.set_text(self.settings.get("gmail_api_key", ""))
        self.outlook_api_key_entry.set_text(self.settings.get("outlook_api_key", ""))
        self.gmail_from_entry.set_text(self.settings.get("gmail_from_address", ""))
        self.notion_api_key_entry.set_text(self.settings.get("notion_api_key", ""))
        self.airtable_api_key_entry.set_text(self.settings.get("airtable_api_key", ""))
        self.hubspot_api_key_entry.set_text(self.settings.get("hubspot_api_key", ""))
        self.stripe_api_key_entry.set_text(self.settings.get("stripe_api_key", ""))
        self.jira_api_key_entry.set_text(self.settings.get("jira_api_key", ""))
        self.asana_api_key_entry.set_text(self.settings.get("asana_api_key", ""))
        self.clickup_api_key_entry.set_text(self.settings.get("clickup_api_key", ""))
        self.trello_api_key_entry.set_text(self.settings.get("trello_api_key", ""))
        self.monday_api_key_entry.set_text(self.settings.get("monday_api_key", ""))
        self.zendesk_api_key_entry.set_text(self.settings.get("zendesk_api_key", ""))
        self.pipedrive_api_key_entry.set_text(self.settings.get("pipedrive_api_key", ""))
        self.salesforce_api_key_entry.set_text(self.settings.get("salesforce_api_key", ""))
        self.gitlab_api_key_entry.set_text(self.settings.get("gitlab_api_key", ""))
        self.twilio_sid_entry.set_text(self.settings.get("twilio_account_sid", ""))
        self.twilio_token_entry.set_text(self.settings.get("twilio_auth_token", ""))
        self.twilio_from_entry.set_text(self.settings.get("twilio_from_number", ""))
        self.github_api_key_entry.set_text(self.settings.get("github_api_key", ""))
        self.linear_api_key_entry.set_text(self.settings.get("linear_api_key", ""))
        self.resend_api_key_entry.set_text(self.settings.get("resend_api_key", ""))
        self.resend_from_entry.set_text(self.settings.get("resend_from_address", ""))
        self.mailgun_api_key_entry.set_text(self.settings.get("mailgun_api_key", ""))
        self.mailgun_domain_entry.set_text(self.settings.get("mailgun_domain", ""))
        self.mailgun_from_entry.set_text(self.settings.get("mailgun_from_address", ""))
        self.postgres_conn_entry.set_text(self.settings.get("postgres_connection_url", ""))
        self.mysql_conn_entry.set_text(self.settings.get("mysql_connection_url", ""))
        self.redis_conn_entry.set_text(self.settings.get("redis_connection_url", ""))
        self.set_segmented_value(self.theme_segment, self.settings.get("theme", "system"))
        self.theme_preset_dropdown.set_selected(
            self.theme_preset_index(self.settings.get("theme_preset", "graphite"))
        )
        self.sync_theme_preview_buttons(self.settings.get("theme_preset", "graphite"))
        self.set_segmented_value(
            self.density_segment,
            self.settings.get("ui_density", "comfortable"),
        )
        self.motion_switch.set_active(bool(self.settings.get("reduce_motion", False)))
        self.daemon_switch.set_active(bool(self.settings.get("daemon_autostart", False)))
        self.tray_switch.set_active(bool(self.settings.get("tray_enabled", False)))

        self.status_label.set_text("")
        self.ai_models_status_label.set_text("")
        self.ai_test_status_label.set_text("")
        if not self.ai_test_prompt_buffer.get_text(
            self.ai_test_prompt_buffer.get_start_iter(),
            self.ai_test_prompt_buffer.get_end_iter(),
            False,
        ).strip():
            self.ai_test_prompt_buffer.set_text(
                "Reply with a short confirmation that this provider and model are working."
            )
        self.ai_test_temp_override_switch.set_active(False)
        self.ai_test_temperature_scale.set_value(0.2)
        self.ai_test_temperature_spin.set_value(0.2)
        self.ai_test_tokens_override_switch.set_active(False)
        self.ai_test_max_tokens_scale.set_value(700)
        self.ai_test_max_tokens_spin.set_value(700)
        self.ai_test_output_buffer.set_text("")
        self.update_local_endpoint_placeholder()
        self.update_local_fields_state()
        self.update_ai_test_override_states()

    def on_local_ai_toggled(self, switch, _param):
        self.update_local_fields_state()

    def update_local_fields_state(self):
        local_ai_enabled = self.local_ai_switch.get_active()
        self.local_backend_dropdown.set_sensitive(local_ai_enabled)
        self.local_endpoint_entry.set_sensitive(local_ai_enabled)
        self.local_api_key_entry.set_sensitive(
            local_ai_enabled and self.selected_local_backend() != "ollama"
        )
        self.local_model_entry.set_sensitive(local_ai_enabled)
        self.fetch_models_button.set_sensitive(local_ai_enabled)

    def on_ai_test_temp_override_toggled(self, _switch, _param):
        self.update_ai_test_override_states()

    def on_ai_test_tokens_override_toggled(self, _switch, _param):
        self.update_ai_test_override_states()

    def update_ai_test_override_states(self):
        temp_enabled = self.ai_test_temp_override_switch.get_active()
        self.ai_test_temperature_scale.set_sensitive(temp_enabled)
        self.ai_test_temperature_spin.set_sensitive(temp_enabled)

        tokens_enabled = self.ai_test_tokens_override_switch.get_active()
        self.ai_test_max_tokens_scale.set_sensitive(tokens_enabled)
        self.ai_test_max_tokens_spin.set_sensitive(tokens_enabled)

    def on_temperature_scale_changed(self, scale: Gtk.Scale):
        value = round(scale.get_value(), 2)
        if abs(self.ai_test_temperature_spin.get_value() - value) > 0.005:
            self.ai_test_temperature_spin.set_value(value)

    def on_temperature_spin_changed(self, spin: Gtk.SpinButton):
        value = round(spin.get_value(), 2)
        if abs(self.ai_test_temperature_scale.get_value() - value) > 0.005:
            self.ai_test_temperature_scale.set_value(value)

    def on_max_tokens_scale_changed(self, scale: Gtk.Scale):
        value = int(scale.get_value())
        if self.ai_test_max_tokens_spin.get_value_as_int() != value:
            self.ai_test_max_tokens_spin.set_value(value)

    def on_max_tokens_spin_changed(self, spin: Gtk.SpinButton):
        value = spin.get_value_as_int()
        if int(self.ai_test_max_tokens_scale.get_value()) != value:
            self.ai_test_max_tokens_scale.set_value(value)

    def on_save_clicked(self, button):
        endpoint_value = self.sanitize_local_endpoint(
            self.local_endpoint_entry.get_text().strip()
        )
        model_value = self.sanitize_model_name(
            self.local_model_entry.get_text().strip()
        )
        settings = dict(self.settings)
        settings.update({
            "local_ai_enabled": self.local_ai_switch.get_active(),
            "preferred_provider": self.selected_provider(),
            "local_ai_backend": self.selected_local_backend(),
            "local_ai_endpoint": endpoint_value,
            "local_ai_api_key": self.local_api_key_entry.get_text().strip(),
            "ollama_url": endpoint_value,
            "default_local_model": model_value,
            "openai_api_key": self.openai_entry.get_text().strip(),
            "anthropic_api_key": self.anthropic_entry.get_text().strip(),
            "slack_webhook_url": self.slack_webhook_entry.get_text().strip(),
            "discord_webhook_url": self.discord_webhook_entry.get_text().strip(),
            "teams_webhook_url": self.teams_webhook_entry.get_text().strip(),
            "telegram_bot_token": self.telegram_token_entry.get_text().strip(),
            "telegram_default_chat_id": self.telegram_chat_id_entry.get_text().strip(),
            "openweather_api_key": self.openweather_api_entry.get_text().strip(),
            "google_apps_script_url": self.google_script_url_entry.get_text().strip(),
            "google_sheets_api_key": self.google_sheets_api_key_entry.get_text().strip(),
            "google_calendar_api_key": self.google_calendar_api_key_entry.get_text().strip(),
            "google_sheets_spreadsheet_id": self.google_sheets_sheet_id_entry.get_text().strip(),
            "google_sheets_range": self.google_sheets_range_entry.get_text().strip(),
            "gmail_api_key": self.gmail_api_key_entry.get_text().strip(),
            "outlook_api_key": self.outlook_api_key_entry.get_text().strip(),
            "gmail_from_address": self.gmail_from_entry.get_text().strip(),
            "notion_api_key": self.notion_api_key_entry.get_text().strip(),
            "airtable_api_key": self.airtable_api_key_entry.get_text().strip(),
            "hubspot_api_key": self.hubspot_api_key_entry.get_text().strip(),
            "stripe_api_key": self.stripe_api_key_entry.get_text().strip(),
            "jira_api_key": self.jira_api_key_entry.get_text().strip(),
            "asana_api_key": self.asana_api_key_entry.get_text().strip(),
            "clickup_api_key": self.clickup_api_key_entry.get_text().strip(),
            "trello_api_key": self.trello_api_key_entry.get_text().strip(),
            "monday_api_key": self.monday_api_key_entry.get_text().strip(),
            "zendesk_api_key": self.zendesk_api_key_entry.get_text().strip(),
            "pipedrive_api_key": self.pipedrive_api_key_entry.get_text().strip(),
            "salesforce_api_key": self.salesforce_api_key_entry.get_text().strip(),
            "gitlab_api_key": self.gitlab_api_key_entry.get_text().strip(),
            "twilio_account_sid": self.twilio_sid_entry.get_text().strip(),
            "twilio_auth_token": self.twilio_token_entry.get_text().strip(),
            "twilio_from_number": self.twilio_from_entry.get_text().strip(),
            "github_api_key": self.github_api_key_entry.get_text().strip(),
            "linear_api_key": self.linear_api_key_entry.get_text().strip(),
            "resend_api_key": self.resend_api_key_entry.get_text().strip(),
            "resend_from_address": self.resend_from_entry.get_text().strip(),
            "mailgun_api_key": self.mailgun_api_key_entry.get_text().strip(),
            "mailgun_domain": self.mailgun_domain_entry.get_text().strip(),
            "mailgun_from_address": self.mailgun_from_entry.get_text().strip(),
            "postgres_connection_url": self.postgres_conn_entry.get_text().strip(),
            "mysql_connection_url": self.mysql_conn_entry.get_text().strip(),
            "redis_connection_url": self.redis_conn_entry.get_text().strip(),
            "theme": self.selected_theme(),
            "theme_preset": self.selected_theme_preset(),
            "ui_density": self.selected_density(),
            "reduce_motion": self.motion_switch.get_active(),
            "daemon_autostart": self.daemon_switch.get_active(),
            "tray_enabled": self.tray_switch.get_active(),
        })

        self.store.save_settings(settings)
        self.settings = self.store.load_settings()
        self.local_endpoint_entry.set_text(self.settings.get("local_ai_endpoint", ""))
        self.local_model_entry.set_text(self.settings.get("default_local_model", ""))
        root = self.get_root()
        if root and hasattr(root, "apply_user_preferences"):
            root.apply_user_preferences()
        self.status_label.set_text("Settings saved successfully.")
        self.appearance_status_label.set_text("Appearance settings synced.")

    def on_save_and_test_clicked(self, _button):
        self.on_save_clicked(None)
        self.on_ai_test_clicked(None)

    def build_appearance_actions_row(self) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class("compact-action-row")
        row.append(self.apply_theme_button)
        return row

    def on_apply_theme_clicked(self, _button):
        settings = dict(self.settings)
        settings.update(
            {
                "theme": self.selected_theme(),
                "theme_preset": self.selected_theme_preset(),
                "ui_density": self.selected_density(),
                "reduce_motion": self.motion_switch.get_active(),
            }
        )
        self.store.save_settings(settings)
        self.settings = self.store.load_settings()

        root = self.get_root()
        if root and hasattr(root, "apply_user_preferences"):
            root.apply_user_preferences()

        self.appearance_status_label.set_text("Theme applied successfully.")
        self.status_label.set_text("Appearance settings updated.")

    def on_fetch_models_clicked(self, _button):
        backend = self.selected_local_backend()
        endpoint = self.local_endpoint_entry.get_text().strip()
        local_api_key = self.local_api_key_entry.get_text().strip()

        self.fetch_models_button.set_sensitive(False)
        self.ai_models_status_label.set_text(f"Fetching local models ({backend})...")
        threading.Thread(
            target=self._fetch_models_worker,
            args=(backend, endpoint, local_api_key),
            daemon=True,
        ).start()

    def _fetch_models_worker(self, backend: str, endpoint: str, local_api_key: str):
        try:
            models = self.ai_service.list_local_models(
                local_backend=backend,
                local_endpoint=endpoint,
                local_api_key=local_api_key,
            )
        except Exception as error:
            GLib.idle_add(self._finish_fetch_models_error, backend, str(error))
            return
        GLib.idle_add(self._finish_fetch_models_success, backend, models)

    def _finish_fetch_models_success(self, backend: str, models: list[str]):
        self.fetch_models_button.set_sensitive(True)
        if not models:
            self.ai_models_status_label.set_text(
                f"No models found for local runtime '{backend}'."
            )
            return False

        self.ai_models_status_label.set_text(
            f"Found {len(models)} model(s): {', '.join(models[:8])}"
        )
        if not self.local_model_entry.get_text().strip():
            self.local_model_entry.set_text(models[0])
        if not self.ai_test_model_entry.get_text().strip():
            self.ai_test_model_entry.set_text(models[0])
        return False

    def _finish_fetch_models_error(self, backend: str, error_message: str):
        self.fetch_models_button.set_sensitive(True)
        guidance = ""
        if "404" in error_message and backend != "ollama":
            guidance = "  Check endpoint path compatibility (for example: /v1 or /chat/completions)."
        elif "403" in error_message or "1010" in error_message:
            guidance = (
                "  Endpoint rejected access. If you are using a remote gateway, set Local Runtime API Key."
            )
        self.ai_models_status_label.set_text(
            f"Failed to fetch local models ({backend}): {error_message}{guidance}"
        )
        return False

    def on_local_backend_changed(self, *_args):
        self.update_local_endpoint_placeholder()
        current_endpoint = self.local_endpoint_entry.get_text().strip()
        known_default_endpoints = {
            "http://localhost:11434",
            "http://localhost:1234",
            "http://localhost:1234/v1",
            "http://localhost:8000",
            "http://localhost:8000/v1",
            "http://localhost:8080",
            "http://localhost:8080/v1",
            "http://localhost:5000",
            "http://localhost:5000/v1",
            "http://localhost:1337",
            "http://localhost:1337/v1",
        }
        if not current_endpoint or current_endpoint in known_default_endpoints:
            self.local_endpoint_entry.set_text(
                self.default_local_endpoint(self.selected_local_backend())
            )
        self.update_local_fields_state()

    def update_local_endpoint_placeholder(self):
        backend = self.selected_local_backend()
        if backend == "ollama":
            self.local_endpoint_entry.set_placeholder_text("http://localhost:11434")
            return
        if backend == "lm_studio":
            self.local_endpoint_entry.set_placeholder_text("http://localhost:1234/v1")
            return
        if backend == "llama_cpp":
            self.local_endpoint_entry.set_placeholder_text("http://localhost:8080/v1")
            return
        if backend == "text_generation_webui":
            self.local_endpoint_entry.set_placeholder_text("http://localhost:5000/v1")
            return
        if backend == "jan":
            self.local_endpoint_entry.set_placeholder_text("http://localhost:1337/v1")
            return
        self.local_endpoint_entry.set_placeholder_text("http://localhost:8000/v1")

    def default_local_endpoint(self, backend: str) -> str:
        normalized = str(backend).strip().lower()
        if normalized == "lm_studio":
            return "http://localhost:1234/v1"
        if normalized in {"openai_compatible", "vllm"}:
            return "http://localhost:8000/v1"
        if normalized == "llama_cpp":
            return "http://localhost:8080/v1"
        if normalized == "text_generation_webui":
            return "http://localhost:5000/v1"
        if normalized == "jan":
            return "http://localhost:1337/v1"
        return "http://localhost:11434"

    def on_ai_test_clicked(self, _button):
        prompt = self.ai_test_prompt_buffer.get_text(
            self.ai_test_prompt_buffer.get_start_iter(),
            self.ai_test_prompt_buffer.get_end_iter(),
            False,
        ).strip()
        if not prompt:
            self.ai_test_status_label.set_text("Enter a test prompt first.")
            return

        self.ai_test_button.set_sensitive(False)
        self.ai_test_output_buffer.set_text("")
        self.ai_test_status_label.set_text("Running AI test...")

        provider_values = ["preferred", "local", "openai", "anthropic"]
        provider_index = self.ai_test_provider_dropdown.get_selected()
        selected_provider = (
            provider_values[provider_index]
            if 0 <= provider_index < len(provider_values)
            else "preferred"
        )

        node_config: dict[str, str] = {}
        if selected_provider != "preferred":
            node_config["provider"] = selected_provider

        model_override = self.ai_test_model_entry.get_text().strip()
        if model_override:
            node_config["model"] = model_override
        if self.ai_test_temp_override_switch.get_active():
            temp_value = round(self.ai_test_temperature_spin.get_value(), 2)
            node_config["temperature"] = f"{temp_value:.2f}"

        if self.ai_test_tokens_override_switch.get_active():
            token_value = self.ai_test_max_tokens_spin.get_value_as_int()
            node_config["max_tokens"] = str(token_value)

        system_prompt = self.ai_test_system_entry.get_text().strip()

        threading.Thread(
            target=self._run_ai_test_worker,
            args=(prompt, node_config, system_prompt),
            daemon=True,
        ).start()

    def on_clear_ai_test_output(self, _button):
        self.ai_test_status_label.set_text("")
        self.ai_test_output_buffer.set_text("")

    def rebuild_connector_test_dropdown(self):
        integrations = self.integration_registry.list_integrations()
        labels = [f"{item.get('name', '')} ({item.get('key', '')})" for item in integrations]
        keys = [str(item.get("key", "")).strip().lower() for item in integrations]
        if not labels:
            labels = ["No connectors"]
            keys = []

        replacement = Gtk.DropDown.new_from_strings(labels)
        replacement.set_hexpand(True)
        replacement.connect("notify::selected", self.on_connector_test_selection_changed)
        parent = self.connector_test_dropdown.get_parent() if hasattr(self, "connector_test_dropdown") else None
        if isinstance(parent, Gtk.Box):
            parent.remove(self.connector_test_dropdown)
            parent.append(replacement)
        self.connector_test_dropdown = replacement
        self.connector_test_keys = keys
        if self.connector_test_keys:
            self.connector_test_dropdown.set_selected(0)
            if hasattr(self, "connector_test_directives_buffer"):
                self.on_connector_test_selection_changed()
        elif hasattr(self, "connector_test_directives_buffer"):
            self.connector_test_directives_buffer.set_text("")

    def selected_connector_test_key(self) -> str:
        index = self.connector_test_dropdown.get_selected()
        if 0 <= index < len(self.connector_test_keys):
            return self.connector_test_keys[index]
        return ""

    def on_connector_test_selection_changed(self, *_args):
        if not hasattr(self, "connector_test_directives_buffer"):
            return
        key = self.selected_connector_test_key()
        if not key:
            return
        self.connector_test_directives_buffer.set_text(
            self.build_connector_directives_for_key(key)
        )

    def build_connector_directives_for_key(self, key: str) -> str:
        normalized = str(key).strip().lower()
        lines: list[str] = []

        def add(name: str, value: str):
            if str(value).strip():
                lines.append(f"{name}: {str(value).strip()}")

        if normalized == "slack_webhook":
            add("webhook_url", self.slack_webhook_entry.get_text())
        elif normalized == "discord_webhook":
            add("webhook_url", self.discord_webhook_entry.get_text())
        elif normalized == "teams_webhook":
            add("webhook_url", self.teams_webhook_entry.get_text())
        elif normalized == "telegram_bot":
            add("api_key", self.telegram_token_entry.get_text())
            add("chat_id", self.telegram_chat_id_entry.get_text())
        elif normalized == "openweather_current":
            add("api_key", self.openweather_api_entry.get_text())
            add("location", "Austin,US")
            add("units", "metric")
        elif normalized == "google_apps_script":
            add("script_url", self.google_script_url_entry.get_text())
        elif normalized == "google_sheets":
            add("api_key", self.google_sheets_api_key_entry.get_text())
            add("spreadsheet_id", self.google_sheets_sheet_id_entry.get_text())
            add("range", self.google_sheets_range_entry.get_text())
            add("payload", "{\"values\":[[\"6X Test\",\"ok\"]]}")
        elif normalized == "google_calendar_api":
            add("api_key", self.google_calendar_api_key_entry.get_text())
            add("url", "https://www.googleapis.com/calendar/v3/users/me/calendarList")
            add("method", "GET")
        elif normalized == "outlook_graph":
            add("api_key", self.outlook_api_key_entry.get_text())
            add("url", "https://graph.microsoft.com/v1.0/me")
            add("method", "GET")
        elif normalized == "gmail_send":
            add("api_key", self.gmail_api_key_entry.get_text())
            add("from", self.gmail_from_entry.get_text())
            add("to", self.gmail_from_entry.get_text())
            add("subject", "6X Connector Test")
        elif normalized == "notion_api":
            add("api_key", self.notion_api_key_entry.get_text())
            add("url", "https://api.notion.com/v1/users")
            add("method", "GET")
        elif normalized == "airtable_api":
            add("api_key", self.airtable_api_key_entry.get_text())
            add("url", "https://api.airtable.com/v0/REPLACE_BASE/REPLACE_TABLE")
            add("method", "GET")
        elif normalized == "hubspot_api":
            add("api_key", self.hubspot_api_key_entry.get_text())
            add("url", "https://api.hubapi.com/crm/v3/objects/contacts?limit=1")
            add("method", "GET")
        elif normalized == "stripe_api":
            add("api_key", self.stripe_api_key_entry.get_text())
            add("url", "https://api.stripe.com/v1/charges?limit=1")
            add("method", "GET")
        elif normalized == "twilio_sms":
            add("account_sid", self.twilio_sid_entry.get_text())
            add("auth_token", self.twilio_token_entry.get_text())
            add("from", self.twilio_from_entry.get_text())
            add("to", self.twilio_from_entry.get_text())
            add("message", "6X connector test")
        elif normalized == "github_rest":
            add("api_key", self.github_api_key_entry.get_text())
            add("url", "https://api.github.com/user")
            add("method", "GET")
        elif normalized == "linear_api":
            add("api_key", self.linear_api_key_entry.get_text())
            add("query", "{ viewer { id name } }")
        elif normalized == "jira_api":
            add("api_key", self.jira_api_key_entry.get_text())
            add("url", "https://your-domain.atlassian.net/rest/api/3/myself")
            add("method", "GET")
        elif normalized == "asana_api":
            add("api_key", self.asana_api_key_entry.get_text())
            add("url", "https://app.asana.com/api/1.0/users/me")
            add("method", "GET")
        elif normalized == "clickup_api":
            add("api_key", self.clickup_api_key_entry.get_text())
            add("url", "https://api.clickup.com/api/v2/user")
            add("method", "GET")
        elif normalized == "trello_api":
            add("api_key", self.trello_api_key_entry.get_text())
            add("url", "https://api.trello.com/1/members/me")
            add("method", "GET")
        elif normalized == "monday_api":
            add("api_key", self.monday_api_key_entry.get_text())
            add("url", "https://api.monday.com/v2")
            add("method", "POST")
            add("payload", "{\"query\":\"{ me { id name email } }\"}")
        elif normalized == "zendesk_api":
            add("api_key", self.zendesk_api_key_entry.get_text())
            add("url", "https://your-domain.zendesk.com/api/v2/users/me.json")
            add("method", "GET")
        elif normalized == "pipedrive_api":
            add("api_key", self.pipedrive_api_key_entry.get_text())
            add("url", "https://api.pipedrive.com/v1/users/me")
            add("method", "GET")
        elif normalized == "salesforce_api":
            add("api_key", self.salesforce_api_key_entry.get_text())
            add("url", "https://your-instance.my.salesforce.com/services/data/v58.0/limits")
            add("method", "GET")
        elif normalized == "gitlab_api":
            add("api_key", self.gitlab_api_key_entry.get_text())
            add("url", "https://gitlab.com/api/v4/user")
            add("method", "GET")
        elif normalized == "resend_email":
            add("api_key", self.resend_api_key_entry.get_text())
            add("from", self.resend_from_entry.get_text())
            add("to", self.resend_from_entry.get_text())
            add("subject", "6X connector test")
            add("message", "Test from 6X")
        elif normalized == "mailgun_email":
            add("api_key", self.mailgun_api_key_entry.get_text())
            add("domain", self.mailgun_domain_entry.get_text())
            add("from", self.mailgun_from_entry.get_text())
            add("to", self.mailgun_from_entry.get_text())
            add("subject", "6X connector test")
            add("message", "Test from 6X")
        elif normalized == "postgres_sql":
            add("connection_url", self.postgres_conn_entry.get_text())
            add("sql", "select now();")
        elif normalized == "mysql_sql":
            add("connection_url", self.mysql_conn_entry.get_text())
            add("sql", "select now();")
        elif normalized == "sqlite_sql":
            add("path", "/tmp/6x-connector-test.db")
            add("sql", "select 1;")
        elif normalized == "redis_command":
            add("connection_url", self.redis_conn_entry.get_text())
            add("command", "PING")
        elif normalized == "http_request":
            add("url", "https://httpbin.org/get")
            add("method", "GET")
        elif normalized == "http_post":
            add("url", "https://httpbin.org/post")
            add("payload", "{\"source\":\"6x-settings-test\"}")

        return "\n".join(lines)

    def on_connector_test_clicked(self, _button):
        key = self.selected_connector_test_key()
        if not key:
            self.connector_test_status_label.set_text("Select a connector first.")
            return

        self.on_save_clicked(None)
        directives = self.connector_test_directives_buffer.get_text(
            self.connector_test_directives_buffer.get_start_iter(),
            self.connector_test_directives_buffer.get_end_iter(),
            False,
        ).strip()
        input_context = self.connector_test_input_entry.get_text().strip()

        self.connector_test_button.set_sensitive(False)
        self.connector_test_status_label.set_text(f"Running connector test for '{key}'...")
        self.connector_test_output_buffer.set_text("")

        threading.Thread(
            target=self._run_connector_test_worker,
            args=(key, directives, input_context),
            daemon=True,
        ).start()

    def on_clear_connector_test_output(self, _button):
        self.connector_test_status_label.set_text("")
        self.connector_test_output_buffer.set_text("")

    def _run_connector_test_worker(self, key: str, directives: str, input_context: str):
        try:
            result = self.integration_test_service.run_test(
                integration_key=key,
                directives_text=directives,
                input_context=input_context,
            )
        except Exception as error:
            GLib.idle_add(self._finish_connector_test_error, str(error))
            return
        GLib.idle_add(self._finish_connector_test_success, key, result)

    def _finish_connector_test_success(self, key: str, result: dict[str, str]):
        self.connector_test_button.set_sensitive(True)
        output = result.get("output", "")
        logs = result.get("logs", "")
        summary = result.get("summary", "Connector test completed.")
        self.connector_test_status_label.set_text(
            f"Connector test passed for '{key}'. {summary}"
        )
        self.connector_test_output_buffer.set_text(
            f"Output:\n{output or '(No output)'}\n\nLogs:\n{logs or '(No logs)'}"
        )
        return False

    def _finish_connector_test_error(self, error_message: str):
        self.connector_test_button.set_sensitive(True)
        self.connector_test_status_label.set_text(f"Connector test failed: {error_message}")
        return False

    def _run_ai_test_worker(
        self,
        prompt: str,
        node_config: dict[str, str],
        system_prompt: str,
    ):
        try:
            result = self.ai_service.generate_with_metadata(
                prompt=prompt,
                node_config=node_config,
                system_prompt=system_prompt,
            )
        except Exception as error:
            GLib.idle_add(self._finish_ai_test_error, str(error))
            return
        GLib.idle_add(self._finish_ai_test_success, result)

    def _finish_ai_test_success(self, result: dict[str, str]):
        self.ai_test_button.set_sensitive(True)
        provider = result.get("provider", "unknown")
        model = result.get("model", "unknown")
        latency_ms = result.get("latency_ms", "0")
        response = result.get("response", "")

        self.ai_test_status_label.set_text(
            f"AI test passed  •  Provider: {provider}  •  Model: {model}  •  {latency_ms} ms"
        )
        self.ai_test_output_buffer.set_text(response)
        return False

    def _finish_ai_test_error(self, error_message: str):
        self.ai_test_button.set_sensitive(True)
        guidance = ""
        selected_backend = self.selected_local_backend()
        if "404" in error_message and selected_backend != "ollama":
            guidance = "  Check Local Runtime Endpoint path compatibility (for example: /v1 or /chat/completions)."
        elif "403" in error_message or "1010" in error_message:
            guidance = (
                "  Endpoint denied access. If remote, add Local Runtime API Key. "
                "If local LM Studio, use http://127.0.0.1:1234/v1."
            )
        self.ai_test_status_label.set_text(f"AI test failed: {error_message}{guidance}")
        return False

    def sanitize_local_endpoint(self, endpoint: str) -> str:
        return str(endpoint).strip().rstrip("/")

    def sanitize_model_name(self, model_name: str) -> str:
        value = str(model_name).strip().strip("/")
        if not value:
            return value
        lower = value.lower()
        for suffix in ["v1/chat/completions", "chat/completions", "v1/completions", "completions"]:
            if lower.endswith(suffix):
                return value[: -len(suffix)].rstrip("/")
        return value
