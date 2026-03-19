import gi
import threading

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GLib

from src.services.integration_registry_service import IntegrationRegistryService
from src.services.integration_settings_store import IntegrationSettingsStore
from src.services.integration_test_service import IntegrationTestService
from src.services.settings_store import SettingsStore
from src.ui import build_icon_title, build_icon_section, build_labeled_field


class IntegrationsView(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("page-root")
        self.add_css_class("integrations-root")

        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(6)
        self.set_margin_end(6)

        self.registry = IntegrationRegistryService()
        self.integration_settings_store = IntegrationSettingsStore()
        self.integration_test_service = IntegrationTestService(
            integration_registry=self.registry
        )
        self.settings_store = SettingsStore()
        self.integrations: list[dict] = []
        self.test_integration_keys: list[str] = []
        self.test_integration_dropdown: Gtk.DropDown | None = None
        self.category_options: list[str] = []
        self.loading_category_selection = False
        self.source_filter = "all"
        self.category_filter = "all"
        self.quick_setup_status_labels: dict[str, Gtk.Label] = {}
        self.quick_test_buttons: dict[str, Gtk.Button] = {}

        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        header_box.add_css_class("page-hero")

        subtitle = Gtk.Label(
            label="Install integration packs and manage local-first action connectors."
        )
        subtitle.set_wrap(True)
        subtitle.set_halign(Gtk.Align.START)
        subtitle.add_css_class("dim-label")

        header_box.append(
            build_icon_title(
                "Integrations",
                "network-wired-symbolic",
            )
        )
        header_box.append(subtitle)

        self.path_entry = Gtk.Entry()
        self.path_entry.set_hexpand(True)
        self.path_entry.set_placeholder_text("Path to integration pack JSON")

        install_button = Gtk.Button(label="Install Pack")
        install_button.connect("clicked", self.on_install_pack)
        install_button.add_css_class("suggested-action")
        install_button.add_css_class("compact-action-button")

        refresh_button = Gtk.Button(label="Refresh")
        refresh_button.connect("clicked", self.on_refresh_clicked)
        refresh_button.add_css_class("compact-action-button")

        self.status_label = Gtk.Label(label="")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.add_css_class("dim-label")
        self.status_label.add_css_class("inline-status")

        settings = self.settings_store.load_settings()
        self.quick_slack_webhook_entry = Gtk.Entry()
        self.quick_slack_webhook_entry.set_placeholder_text(
            "https://hooks.slack.com/services/..."
        )
        self.quick_slack_webhook_entry.set_text(str(settings.get("slack_webhook_url", "")).strip())

        self.quick_discord_webhook_entry = Gtk.Entry()
        self.quick_discord_webhook_entry.set_placeholder_text(
            "https://discord.com/api/webhooks/..."
        )
        self.quick_discord_webhook_entry.set_text(
            str(settings.get("discord_webhook_url", "")).strip()
        )

        self.quick_teams_webhook_entry = Gtk.Entry()
        self.quick_teams_webhook_entry.set_placeholder_text(
            "https://outlook.office.com/webhook/..."
        )
        self.quick_teams_webhook_entry.set_text(
            str(settings.get("teams_webhook_url", "")).strip()
        )

        self.quick_telegram_token_entry = Gtk.Entry()
        self.quick_telegram_token_entry.set_placeholder_text("Telegram bot token")
        self.quick_telegram_token_entry.set_visibility(False)
        self.quick_telegram_token_entry.set_text(
            str(settings.get("telegram_bot_token", "")).strip()
        )

        self.quick_telegram_chat_entry = Gtk.Entry()
        self.quick_telegram_chat_entry.set_placeholder_text("Default chat id")
        self.quick_telegram_chat_entry.set_text(
            str(settings.get("telegram_default_chat_id", "")).strip()
        )

        self.quick_openweather_key_entry = Gtk.Entry()
        self.quick_openweather_key_entry.set_placeholder_text("OpenWeather API key")
        self.quick_openweather_key_entry.set_visibility(False)
        self.quick_openweather_key_entry.set_text(str(settings.get("openweather_api_key", "")).strip())

        self.quick_openweather_location_entry = Gtk.Entry()
        self.quick_openweather_location_entry.set_placeholder_text("Location  •  Example: Austin,US")
        self.quick_openweather_location_entry.set_text(
            str(settings.get("openweather_default_location", "")).strip() or "Austin,US"
        )

        self.quick_gmail_key_entry = Gtk.Entry()
        self.quick_gmail_key_entry.set_placeholder_text("OAuth bearer token")
        self.quick_gmail_key_entry.set_visibility(False)
        self.quick_gmail_key_entry.set_text(str(settings.get("gmail_api_key", "")).strip())

        self.quick_outlook_key_entry = Gtk.Entry()
        self.quick_outlook_key_entry.set_placeholder_text("Outlook / Graph OAuth bearer token")
        self.quick_outlook_key_entry.set_visibility(False)
        self.quick_outlook_key_entry.set_text(str(settings.get("outlook_api_key", "")).strip())

        self.quick_outlook_url_entry = Gtk.Entry()
        self.quick_outlook_url_entry.set_placeholder_text("https://graph.microsoft.com/v1.0/me")
        self.quick_outlook_url_entry.set_text(
            str(settings.get("outlook_api_url", "")).strip()
            or "https://graph.microsoft.com/v1.0/me"
        )

        self.quick_gmail_from_entry = Gtk.Entry()
        self.quick_gmail_from_entry.set_placeholder_text("From address")
        self.quick_gmail_from_entry.set_text(str(settings.get("gmail_from_address", "")).strip())

        self.quick_sheets_key_entry = Gtk.Entry()
        self.quick_sheets_key_entry.set_placeholder_text("OAuth bearer token")
        self.quick_sheets_key_entry.set_visibility(False)
        self.quick_sheets_key_entry.set_text(str(settings.get("google_sheets_api_key", "")).strip())

        self.quick_google_calendar_key_entry = Gtk.Entry()
        self.quick_google_calendar_key_entry.set_placeholder_text("Google Calendar OAuth bearer token")
        self.quick_google_calendar_key_entry.set_visibility(False)
        self.quick_google_calendar_key_entry.set_text(
            str(settings.get("google_calendar_api_key", "")).strip()
        )

        self.quick_google_calendar_url_entry = Gtk.Entry()
        self.quick_google_calendar_url_entry.set_placeholder_text(
            "https://www.googleapis.com/calendar/v3/users/me/calendarList"
        )
        self.quick_google_calendar_url_entry.set_text(
            str(settings.get("google_calendar_api_url", "")).strip()
            or "https://www.googleapis.com/calendar/v3/users/me/calendarList"
        )

        self.quick_sheets_spreadsheet_entry = Gtk.Entry()
        self.quick_sheets_spreadsheet_entry.set_placeholder_text("Spreadsheet ID")
        self.quick_sheets_spreadsheet_entry.set_text(
            str(settings.get("google_sheets_spreadsheet_id", "")).strip()
        )

        self.quick_sheets_range_entry = Gtk.Entry()
        self.quick_sheets_range_entry.set_placeholder_text("Range  •  Example: Sheet1!A:B")
        self.quick_sheets_range_entry.set_text(str(settings.get("google_sheets_range", "")).strip())

        self.quick_apps_script_url_entry = Gtk.Entry()
        self.quick_apps_script_url_entry.set_placeholder_text(
            "https://script.google.com/macros/s/.../exec"
        )
        self.quick_apps_script_url_entry.set_text(
            str(settings.get("google_apps_script_url", "")).strip()
        )

        self.quick_github_key_entry = Gtk.Entry()
        self.quick_github_key_entry.set_placeholder_text("GitHub personal access token")
        self.quick_github_key_entry.set_visibility(False)
        self.quick_github_key_entry.set_text(str(settings.get("github_api_key", "")).strip())

        self.quick_github_url_entry = Gtk.Entry()
        self.quick_github_url_entry.set_placeholder_text("https://api.github.com/user")
        self.quick_github_url_entry.set_text(
            str(settings.get("github_api_url", "")).strip() or "https://api.github.com/user"
        )

        self.quick_notion_key_entry = Gtk.Entry()
        self.quick_notion_key_entry.set_placeholder_text("Notion API key")
        self.quick_notion_key_entry.set_visibility(False)
        self.quick_notion_key_entry.set_text(str(settings.get("notion_api_key", "")).strip())

        self.quick_notion_url_entry = Gtk.Entry()
        self.quick_notion_url_entry.set_placeholder_text("https://api.notion.com/v1/users")
        self.quick_notion_url_entry.set_text(
            str(settings.get("notion_api_url", "")).strip()
            or "https://api.notion.com/v1/users"
        )

        self.quick_jira_key_entry = Gtk.Entry()
        self.quick_jira_key_entry.set_placeholder_text("Jira API token")
        self.quick_jira_key_entry.set_visibility(False)
        self.quick_jira_key_entry.set_text(str(settings.get("jira_api_key", "")).strip())

        self.quick_jira_url_entry = Gtk.Entry()
        self.quick_jira_url_entry.set_placeholder_text(
            "https://your-domain.atlassian.net/rest/api/3/myself"
        )
        self.quick_jira_url_entry.set_text(
            str(settings.get("jira_api_url", "")).strip()
            or "https://your-domain.atlassian.net/rest/api/3/myself"
        )

        self.quick_asana_key_entry = Gtk.Entry()
        self.quick_asana_key_entry.set_placeholder_text("Asana personal access token")
        self.quick_asana_key_entry.set_visibility(False)
        self.quick_asana_key_entry.set_text(str(settings.get("asana_api_key", "")).strip())

        self.quick_asana_url_entry = Gtk.Entry()
        self.quick_asana_url_entry.set_placeholder_text("https://app.asana.com/api/1.0/users/me")
        self.quick_asana_url_entry.set_text(
            str(settings.get("asana_api_url", "")).strip()
            or "https://app.asana.com/api/1.0/users/me"
        )

        self.quick_clickup_key_entry = Gtk.Entry()
        self.quick_clickup_key_entry.set_placeholder_text("ClickUp API token")
        self.quick_clickup_key_entry.set_visibility(False)
        self.quick_clickup_key_entry.set_text(str(settings.get("clickup_api_key", "")).strip())

        self.quick_clickup_url_entry = Gtk.Entry()
        self.quick_clickup_url_entry.set_placeholder_text("https://api.clickup.com/api/v2/user")
        self.quick_clickup_url_entry.set_text(
            str(settings.get("clickup_api_url", "")).strip()
            or "https://api.clickup.com/api/v2/user"
        )

        self.quick_trello_key_entry = Gtk.Entry()
        self.quick_trello_key_entry.set_placeholder_text("Trello API token/key")
        self.quick_trello_key_entry.set_visibility(False)
        self.quick_trello_key_entry.set_text(str(settings.get("trello_api_key", "")).strip())

        self.quick_trello_url_entry = Gtk.Entry()
        self.quick_trello_url_entry.set_placeholder_text("https://api.trello.com/1/members/me")
        self.quick_trello_url_entry.set_text(
            str(settings.get("trello_api_url", "")).strip()
            or "https://api.trello.com/1/members/me"
        )

        self.quick_monday_key_entry = Gtk.Entry()
        self.quick_monday_key_entry.set_placeholder_text("Monday.com API token")
        self.quick_monday_key_entry.set_visibility(False)
        self.quick_monday_key_entry.set_text(str(settings.get("monday_api_key", "")).strip())

        self.quick_monday_url_entry = Gtk.Entry()
        self.quick_monday_url_entry.set_placeholder_text("https://api.monday.com/v2")
        self.quick_monday_url_entry.set_text(
            str(settings.get("monday_api_url", "")).strip() or "https://api.monday.com/v2"
        )

        self.quick_zendesk_key_entry = Gtk.Entry()
        self.quick_zendesk_key_entry.set_placeholder_text("Zendesk API token")
        self.quick_zendesk_key_entry.set_visibility(False)
        self.quick_zendesk_key_entry.set_text(str(settings.get("zendesk_api_key", "")).strip())

        self.quick_zendesk_url_entry = Gtk.Entry()
        self.quick_zendesk_url_entry.set_placeholder_text(
            "https://your-domain.zendesk.com/api/v2/users/me.json"
        )
        self.quick_zendesk_url_entry.set_text(
            str(settings.get("zendesk_api_url", "")).strip()
            or "https://your-domain.zendesk.com/api/v2/users/me.json"
        )

        self.quick_pipedrive_key_entry = Gtk.Entry()
        self.quick_pipedrive_key_entry.set_placeholder_text("Pipedrive API token")
        self.quick_pipedrive_key_entry.set_visibility(False)
        self.quick_pipedrive_key_entry.set_text(str(settings.get("pipedrive_api_key", "")).strip())

        self.quick_pipedrive_url_entry = Gtk.Entry()
        self.quick_pipedrive_url_entry.set_placeholder_text("https://api.pipedrive.com/v1/users/me")
        self.quick_pipedrive_url_entry.set_text(
            str(settings.get("pipedrive_api_url", "")).strip()
            or "https://api.pipedrive.com/v1/users/me"
        )

        self.quick_salesforce_key_entry = Gtk.Entry()
        self.quick_salesforce_key_entry.set_placeholder_text("Salesforce OAuth access token")
        self.quick_salesforce_key_entry.set_visibility(False)
        self.quick_salesforce_key_entry.set_text(str(settings.get("salesforce_api_key", "")).strip())

        self.quick_salesforce_url_entry = Gtk.Entry()
        self.quick_salesforce_url_entry.set_placeholder_text(
            "https://your-instance.my.salesforce.com/services/data/v58.0/limits"
        )
        self.quick_salesforce_url_entry.set_text(
            str(settings.get("salesforce_api_url", "")).strip()
            or "https://your-instance.my.salesforce.com/services/data/v58.0/limits"
        )

        self.quick_gitlab_key_entry = Gtk.Entry()
        self.quick_gitlab_key_entry.set_placeholder_text("GitLab API token")
        self.quick_gitlab_key_entry.set_visibility(False)
        self.quick_gitlab_key_entry.set_text(str(settings.get("gitlab_api_key", "")).strip())

        self.quick_gitlab_url_entry = Gtk.Entry()
        self.quick_gitlab_url_entry.set_placeholder_text("https://gitlab.com/api/v4/user")
        self.quick_gitlab_url_entry.set_text(
            str(settings.get("gitlab_api_url", "")).strip()
            or "https://gitlab.com/api/v4/user"
        )

        self.quick_hubspot_key_entry = Gtk.Entry()
        self.quick_hubspot_key_entry.set_placeholder_text("HubSpot private app token")
        self.quick_hubspot_key_entry.set_visibility(False)
        self.quick_hubspot_key_entry.set_text(str(settings.get("hubspot_api_key", "")).strip())

        self.quick_hubspot_url_entry = Gtk.Entry()
        self.quick_hubspot_url_entry.set_placeholder_text(
            "https://api.hubapi.com/crm/v3/objects/contacts?limit=1"
        )
        self.quick_hubspot_url_entry.set_text(
            str(settings.get("hubspot_api_url", "")).strip()
            or "https://api.hubapi.com/crm/v3/objects/contacts?limit=1"
        )

        self.quick_stripe_key_entry = Gtk.Entry()
        self.quick_stripe_key_entry.set_placeholder_text("Stripe secret key")
        self.quick_stripe_key_entry.set_visibility(False)
        self.quick_stripe_key_entry.set_text(str(settings.get("stripe_api_key", "")).strip())

        self.quick_stripe_url_entry = Gtk.Entry()
        self.quick_stripe_url_entry.set_placeholder_text("https://api.stripe.com/v1/balance")
        self.quick_stripe_url_entry.set_text(
            str(settings.get("stripe_api_url", "")).strip()
            or "https://api.stripe.com/v1/balance"
        )

        self.quick_twilio_sid_entry = Gtk.Entry()
        self.quick_twilio_sid_entry.set_placeholder_text("Twilio Account SID")
        self.quick_twilio_sid_entry.set_text(str(settings.get("twilio_account_sid", "")).strip())

        self.quick_twilio_token_entry = Gtk.Entry()
        self.quick_twilio_token_entry.set_placeholder_text("Twilio Auth Token")
        self.quick_twilio_token_entry.set_visibility(False)
        self.quick_twilio_token_entry.set_text(str(settings.get("twilio_auth_token", "")).strip())

        self.quick_twilio_from_entry = Gtk.Entry()
        self.quick_twilio_from_entry.set_placeholder_text("+15550001111")
        self.quick_twilio_from_entry.set_text(str(settings.get("twilio_from_number", "")).strip())

        self.quick_twilio_to_entry = Gtk.Entry()
        self.quick_twilio_to_entry.set_placeholder_text("+15550002222")

        install_action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        install_action_row.add_css_class("compact-action-row")
        install_action_row.append(install_button)
        install_action_row.append(refresh_button)

        header_action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header_action_row.add_css_class("canvas-toolbar-row")
        header_action_row.add_css_class("compact-toolbar-row")
        header_action_row.add_css_class("page-action-bar")
        self.header_action_row = header_action_row

        self.search_entry = Gtk.Entry()
        self.search_entry.set_hexpand(True)
        self.search_entry.set_placeholder_text("Search integrations by name, key, or handler")
        self.search_entry.connect("changed", self.on_filters_changed)

        self.source_filter_row = self.build_source_filter_row()
        self.category_dropdown = Gtk.DropDown.new_from_strings(["All Categories"])
        self.category_dropdown.connect("notify::selected", self.on_category_changed)
        self.reset_filters_button = Gtk.Button(label="Reset")
        self.reset_filters_button.add_css_class("compact-action-button")
        self.reset_filters_button.connect("clicked", self.on_reset_filters)

        header_action_row.append(self.search_entry)
        header_action_row.append(self.category_dropdown)
        header_action_row.append(self.source_filter_row)
        header_action_row.append(self.reset_filters_button)

        self.test_dropdown_container = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.test_dropdown_container.set_hexpand(True)

        self.test_input_entry = Gtk.Entry()
        self.test_input_entry.set_placeholder_text("Optional input context for this test")

        self.test_directives_buffer = Gtk.TextBuffer()
        self.test_directives_view = Gtk.TextView(buffer=self.test_directives_buffer)
        self.test_directives_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.test_directives_view.set_size_request(-1, 76)

        directives_frame = Gtk.Frame()
        directives_frame.add_css_class("canvas-edit-detail-frame")
        directives_frame.set_child(self.test_directives_view)

        self.test_output_buffer = Gtk.TextBuffer()
        self.test_output_view = Gtk.TextView(buffer=self.test_output_buffer)
        self.test_output_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.test_output_view.set_editable(False)
        self.test_output_view.set_cursor_visible(False)
        self.test_output_view.set_size_request(-1, 104)

        output_frame = Gtk.Frame()
        output_frame.add_css_class("canvas-edit-detail-frame")
        output_frame.set_child(self.test_output_view)

        self.test_status_label = Gtk.Label(label="")
        self.test_status_label.set_wrap(True)
        self.test_status_label.set_halign(Gtk.Align.START)
        self.test_status_label.add_css_class("dim-label")
        self.test_status_label.add_css_class("inline-status")

        self.run_test_button = Gtk.Button(label="Run Integration Test")
        self.run_test_button.add_css_class("suggested-action")
        self.run_test_button.add_css_class("compact-action-button")
        self.run_test_button.connect("clicked", self.on_run_test_clicked)

        load_template_button = Gtk.Button(label="Load Required Fields")
        load_template_button.connect("clicked", self.on_load_required_template_clicked)
        load_template_button.add_css_class("compact-action-button")

        clear_output_button = Gtk.Button(label="Clear Output")
        clear_output_button.connect("clicked", self.on_clear_test_output_clicked)
        clear_output_button.add_css_class("compact-action-button")

        test_action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        test_action_row.add_css_class("compact-action-row")
        test_action_row.append(self.run_test_button)
        test_action_row.append(load_template_button)
        test_action_row.append(clear_output_button)

        save_profile_button = Gtk.Button(label="Save Test Profile")
        save_profile_button.connect("clicked", self.on_save_profile_clicked)
        save_profile_button.add_css_class("compact-action-button")

        load_profile_button = Gtk.Button(label="Load Saved Profile")
        load_profile_button.connect("clicked", self.on_load_profile_clicked)
        load_profile_button.add_css_class("compact-action-button")

        delete_profile_button = Gtk.Button(label="Delete Saved Profile")
        delete_profile_button.connect("clicked", self.on_delete_profile_clicked)
        delete_profile_button.add_css_class("compact-action-button")

        profile_action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        profile_action_row.add_css_class("compact-action-row")
        profile_action_row.append(save_profile_button)
        profile_action_row.append(load_profile_button)
        profile_action_row.append(delete_profile_button)

        section_title = build_icon_section(
            "Available Integrations",
            "network-server-symbolic",
        )

        self.empty_label = Gtk.Label(label="No integrations found.")
        self.empty_label.add_css_class("dim-label")
        self.empty_label.add_css_class("empty-state-label")
        self.empty_label.set_halign(Gtk.Align.START)

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.list_box.set_vexpand(False)

        workspace_shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        workspace_shell.set_margin_top(6)
        workspace_shell.set_margin_bottom(6)
        workspace_shell.set_margin_start(6)
        workspace_shell.set_margin_end(6)

        top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        top_row.add_css_class("settings-panel-row")
        top_row.set_homogeneous(True)

        install_panel = self.build_form_panel(
            "Pack Installer",
            "folder-download-symbolic",
            [
                build_labeled_field("Pack File Path", self.path_entry),
                install_action_row,
                self.status_label,
            ],
        )
        install_panel.set_hexpand(True)

        test_config_panel = self.build_form_panel(
            "Integration Test Setup",
            "system-search-symbolic",
            [
                build_labeled_field("Integration", self.test_dropdown_container),
                build_labeled_field("Input Context", self.test_input_entry),
                build_labeled_field("Required Fields / Directives", directives_frame),
                test_action_row,
                profile_action_row,
                self.test_status_label,
            ],
        )
        test_config_panel.set_hexpand(True)

        top_row.append(install_panel)
        top_row.append(test_config_panel)
        workspace_shell.append(top_row)

        workspace_shell.append(self.build_quick_setup_panel())

        test_output_panel = self.build_form_panel(
            "Integration Test Output",
            "text-x-generic-symbolic",
            [build_labeled_field("Output + Logs", output_frame)],
        )
        workspace_shell.append(test_output_panel)

        workspace_frame = Gtk.Frame()
        workspace_frame.add_css_class("panel-card")
        workspace_frame.add_css_class("entity-form-panel")
        workspace_frame.set_child(workspace_shell)

        page_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page_content.append(header_box)
        page_content.append(header_action_row)
        page_content.append(workspace_frame)
        page_content.append(section_title)
        page_content.append(self.empty_label)
        page_content.append(self.list_box)
        page_content.set_hexpand(True)
        page_content.set_vexpand(True)
        self.append(page_content)

        self.refresh_list()

    def build_quick_setup_panel(self) -> Gtk.Frame:
        quick_grid = Gtk.Grid()
        quick_grid.set_column_spacing(8)
        quick_grid.set_row_spacing(8)
        quick_grid.add_css_class("integration-quick-grid")

        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="slack",
                title="Slack Webhook",
                icon_name="mail-message-new-symbolic",
                fields=[
                    build_labeled_field("Webhook URL", self.quick_slack_webhook_entry),
                ],
                on_save=self.on_save_slack_quick_setup,
                on_test=self.on_test_slack_quick_setup,
            ),
            0,
            0,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="discord",
                title="Discord Webhook",
                icon_name="mail-message-new-symbolic",
                fields=[
                    build_labeled_field("Webhook URL", self.quick_discord_webhook_entry),
                ],
                on_save=self.on_save_discord_quick_setup,
                on_test=self.on_test_discord_quick_setup,
            ),
            1,
            0,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="telegram",
                title="Telegram Bot",
                icon_name="mail-send-symbolic",
                fields=[
                    build_labeled_field("Bot Token", self.quick_telegram_token_entry),
                    build_labeled_field("Default Chat ID", self.quick_telegram_chat_entry),
                ],
                on_save=self.on_save_telegram_quick_setup,
                on_test=self.on_test_telegram_quick_setup,
            ),
            2,
            0,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="openweather",
                title="OpenWeather",
                icon_name="weather-clear-symbolic",
                fields=[
                    build_labeled_field("API Key", self.quick_openweather_key_entry),
                    build_labeled_field("Default Location", self.quick_openweather_location_entry),
                ],
                on_save=self.on_save_openweather_quick_setup,
                on_test=self.on_test_openweather_quick_setup,
            ),
            0,
            1,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="gmail",
                title="Gmail Send",
                icon_name="mail-send-symbolic",
                fields=[
                    build_labeled_field("OAuth Token", self.quick_gmail_key_entry),
                    build_labeled_field("From Address", self.quick_gmail_from_entry),
                ],
                on_save=self.on_save_gmail_quick_setup,
                on_test=self.on_test_gmail_quick_setup,
            ),
            1,
            1,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="google_sheets",
                title="Google Sheets",
                icon_name="x-office-spreadsheet-symbolic",
                fields=[
                    build_labeled_field("OAuth Token", self.quick_sheets_key_entry),
                    build_labeled_field("Spreadsheet ID", self.quick_sheets_spreadsheet_entry),
                    build_labeled_field("Range", self.quick_sheets_range_entry),
                ],
                on_save=self.on_save_sheets_quick_setup,
                on_test=self.on_test_sheets_quick_setup,
            ),
            2,
            1,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="apps_script",
                title="Google Apps Script",
                icon_name="applications-system-symbolic",
                fields=[
                    build_labeled_field("Script URL", self.quick_apps_script_url_entry),
                ],
                on_save=self.on_save_apps_script_quick_setup,
                on_test=self.on_test_apps_script_quick_setup,
            ),
            0,
            2,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="github",
                title="GitHub REST",
                icon_name="applications-development-symbolic",
                fields=[
                    build_labeled_field("API Key", self.quick_github_key_entry),
                    build_labeled_field("Request URL", self.quick_github_url_entry),
                ],
                on_save=self.on_save_github_quick_setup,
                on_test=self.on_test_github_quick_setup,
            ),
            1,
            2,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="notion",
                title="Notion API",
                icon_name="text-x-generic-symbolic",
                fields=[
                    build_labeled_field("API Key", self.quick_notion_key_entry),
                    build_labeled_field("Request URL", self.quick_notion_url_entry),
                ],
                on_save=self.on_save_notion_quick_setup,
                on_test=self.on_test_notion_quick_setup,
            ),
            2,
            2,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="hubspot",
                title="HubSpot API",
                icon_name="network-server-symbolic",
                fields=[
                    build_labeled_field("API Key", self.quick_hubspot_key_entry),
                    build_labeled_field("Request URL", self.quick_hubspot_url_entry),
                ],
                on_save=self.on_save_hubspot_quick_setup,
                on_test=self.on_test_hubspot_quick_setup,
            ),
            0,
            3,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="stripe",
                title="Stripe API",
                icon_name="wallet-open-symbolic",
                fields=[
                    build_labeled_field("API Key", self.quick_stripe_key_entry),
                    build_labeled_field("Request URL", self.quick_stripe_url_entry),
                ],
                on_save=self.on_save_stripe_quick_setup,
                on_test=self.on_test_stripe_quick_setup,
            ),
            1,
            3,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="twilio",
                title="Twilio SMS",
                icon_name="mail-send-symbolic",
                fields=[
                    build_labeled_field("Account SID", self.quick_twilio_sid_entry),
                    build_labeled_field("Auth Token", self.quick_twilio_token_entry),
                    build_labeled_field("From Number", self.quick_twilio_from_entry),
                    build_labeled_field("To Number", self.quick_twilio_to_entry),
                ],
                on_save=self.on_save_twilio_quick_setup,
                on_test=self.on_test_twilio_quick_setup,
            ),
            2,
            3,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="jira",
                title="Jira API",
                icon_name="view-list-symbolic",
                fields=[
                    build_labeled_field("API Key", self.quick_jira_key_entry),
                    build_labeled_field("Request URL", self.quick_jira_url_entry),
                ],
                on_save=lambda button: self.on_save_token_url_quick_setup(
                    button,
                    "jira",
                    "jira_api_key",
                    self.quick_jira_key_entry,
                    "Jira",
                    url_settings_key="jira_api_url",
                    url_entry=self.quick_jira_url_entry,
                ),
                on_test=lambda button: self.on_test_token_url_quick_setup(
                    button,
                    "jira",
                    "jira_api",
                    "jira_api_key",
                    self.quick_jira_key_entry,
                    self.quick_jira_url_entry,
                    "Jira",
                ),
            ),
            0,
            4,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="asana",
                title="Asana API",
                icon_name="view-calendar-symbolic",
                fields=[
                    build_labeled_field("API Key", self.quick_asana_key_entry),
                    build_labeled_field("Request URL", self.quick_asana_url_entry),
                ],
                on_save=lambda button: self.on_save_token_url_quick_setup(
                    button,
                    "asana",
                    "asana_api_key",
                    self.quick_asana_key_entry,
                    "Asana",
                    url_settings_key="asana_api_url",
                    url_entry=self.quick_asana_url_entry,
                ),
                on_test=lambda button: self.on_test_token_url_quick_setup(
                    button,
                    "asana",
                    "asana_api",
                    "asana_api_key",
                    self.quick_asana_key_entry,
                    self.quick_asana_url_entry,
                    "Asana",
                ),
            ),
            1,
            4,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="clickup",
                title="ClickUp API",
                icon_name="view-grid-symbolic",
                fields=[
                    build_labeled_field("API Key", self.quick_clickup_key_entry),
                    build_labeled_field("Request URL", self.quick_clickup_url_entry),
                ],
                on_save=lambda button: self.on_save_token_url_quick_setup(
                    button,
                    "clickup",
                    "clickup_api_key",
                    self.quick_clickup_key_entry,
                    "ClickUp",
                    url_settings_key="clickup_api_url",
                    url_entry=self.quick_clickup_url_entry,
                ),
                on_test=lambda button: self.on_test_token_url_quick_setup(
                    button,
                    "clickup",
                    "clickup_api",
                    "clickup_api_key",
                    self.quick_clickup_key_entry,
                    self.quick_clickup_url_entry,
                    "ClickUp",
                ),
            ),
            2,
            4,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="trello",
                title="Trello API",
                icon_name="view-grid-symbolic",
                fields=[
                    build_labeled_field("API Key", self.quick_trello_key_entry),
                    build_labeled_field("Request URL", self.quick_trello_url_entry),
                ],
                on_save=lambda button: self.on_save_token_url_quick_setup(
                    button,
                    "trello",
                    "trello_api_key",
                    self.quick_trello_key_entry,
                    "Trello",
                    url_settings_key="trello_api_url",
                    url_entry=self.quick_trello_url_entry,
                ),
                on_test=lambda button: self.on_test_token_url_quick_setup(
                    button,
                    "trello",
                    "trello_api",
                    "trello_api_key",
                    self.quick_trello_key_entry,
                    self.quick_trello_url_entry,
                    "Trello",
                ),
            ),
            0,
            5,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="monday",
                title="Monday API",
                icon_name="view-paged-symbolic",
                fields=[
                    build_labeled_field("API Key", self.quick_monday_key_entry),
                    build_labeled_field("Request URL", self.quick_monday_url_entry),
                ],
                on_save=lambda button: self.on_save_token_url_quick_setup(
                    button,
                    "monday",
                    "monday_api_key",
                    self.quick_monday_key_entry,
                    "Monday",
                    url_settings_key="monday_api_url",
                    url_entry=self.quick_monday_url_entry,
                ),
                on_test=lambda button: self.on_test_token_url_quick_setup(
                    button,
                    "monday",
                    "monday_api",
                    "monday_api_key",
                    self.quick_monday_key_entry,
                    self.quick_monday_url_entry,
                    "Monday",
                    payload='{"query":"{ me { id name email } }"}',
                    method="POST",
                ),
            ),
            1,
            5,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="zendesk",
                title="Zendesk API",
                icon_name="help-about-symbolic",
                fields=[
                    build_labeled_field("API Key", self.quick_zendesk_key_entry),
                    build_labeled_field("Request URL", self.quick_zendesk_url_entry),
                ],
                on_save=lambda button: self.on_save_token_url_quick_setup(
                    button,
                    "zendesk",
                    "zendesk_api_key",
                    self.quick_zendesk_key_entry,
                    "Zendesk",
                    url_settings_key="zendesk_api_url",
                    url_entry=self.quick_zendesk_url_entry,
                ),
                on_test=lambda button: self.on_test_token_url_quick_setup(
                    button,
                    "zendesk",
                    "zendesk_api",
                    "zendesk_api_key",
                    self.quick_zendesk_key_entry,
                    self.quick_zendesk_url_entry,
                    "Zendesk",
                ),
            ),
            2,
            5,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="pipedrive",
                title="Pipedrive API",
                icon_name="network-workgroup-symbolic",
                fields=[
                    build_labeled_field("API Key", self.quick_pipedrive_key_entry),
                    build_labeled_field("Request URL", self.quick_pipedrive_url_entry),
                ],
                on_save=lambda button: self.on_save_token_url_quick_setup(
                    button,
                    "pipedrive",
                    "pipedrive_api_key",
                    self.quick_pipedrive_key_entry,
                    "Pipedrive",
                    url_settings_key="pipedrive_api_url",
                    url_entry=self.quick_pipedrive_url_entry,
                ),
                on_test=lambda button: self.on_test_token_url_quick_setup(
                    button,
                    "pipedrive",
                    "pipedrive_api",
                    "pipedrive_api_key",
                    self.quick_pipedrive_key_entry,
                    self.quick_pipedrive_url_entry,
                    "Pipedrive",
                ),
            ),
            0,
            6,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="salesforce",
                title="Salesforce API",
                icon_name="applications-internet-symbolic",
                fields=[
                    build_labeled_field("API Key", self.quick_salesforce_key_entry),
                    build_labeled_field("Request URL", self.quick_salesforce_url_entry),
                ],
                on_save=lambda button: self.on_save_token_url_quick_setup(
                    button,
                    "salesforce",
                    "salesforce_api_key",
                    self.quick_salesforce_key_entry,
                    "Salesforce",
                    url_settings_key="salesforce_api_url",
                    url_entry=self.quick_salesforce_url_entry,
                ),
                on_test=lambda button: self.on_test_token_url_quick_setup(
                    button,
                    "salesforce",
                    "salesforce_api",
                    "salesforce_api_key",
                    self.quick_salesforce_key_entry,
                    self.quick_salesforce_url_entry,
                    "Salesforce",
                ),
            ),
            1,
            6,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="gitlab",
                title="GitLab API",
                icon_name="applications-development-symbolic",
                fields=[
                    build_labeled_field("API Key", self.quick_gitlab_key_entry),
                    build_labeled_field("Request URL", self.quick_gitlab_url_entry),
                ],
                on_save=lambda button: self.on_save_token_url_quick_setup(
                    button,
                    "gitlab",
                    "gitlab_api_key",
                    self.quick_gitlab_key_entry,
                    "GitLab",
                    url_settings_key="gitlab_api_url",
                    url_entry=self.quick_gitlab_url_entry,
                ),
                on_test=lambda button: self.on_test_token_url_quick_setup(
                    button,
                    "gitlab",
                    "gitlab_api",
                    "gitlab_api_key",
                    self.quick_gitlab_key_entry,
                    self.quick_gitlab_url_entry,
                    "GitLab",
                ),
            ),
            2,
            6,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="teams",
                title="Teams Webhook",
                icon_name="mail-message-new-symbolic",
                fields=[
                    build_labeled_field("Webhook URL", self.quick_teams_webhook_entry),
                ],
                on_save=self.on_save_teams_quick_setup,
                on_test=self.on_test_teams_quick_setup,
            ),
            0,
            7,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="google_calendar",
                title="Google Calendar API",
                icon_name="view-calendar-symbolic",
                fields=[
                    build_labeled_field("API Key", self.quick_google_calendar_key_entry),
                    build_labeled_field("Request URL", self.quick_google_calendar_url_entry),
                ],
                on_save=lambda button: self.on_save_token_url_quick_setup(
                    button,
                    "google_calendar",
                    "google_calendar_api_key",
                    self.quick_google_calendar_key_entry,
                    "Google Calendar",
                    url_settings_key="google_calendar_api_url",
                    url_entry=self.quick_google_calendar_url_entry,
                ),
                on_test=lambda button: self.on_test_token_url_quick_setup(
                    button,
                    "google_calendar",
                    "google_calendar_api",
                    "google_calendar_api_key",
                    self.quick_google_calendar_key_entry,
                    self.quick_google_calendar_url_entry,
                    "Google Calendar",
                ),
            ),
            1,
            7,
            1,
            1,
        )
        quick_grid.attach(
            self.build_quick_setup_card(
                card_key="outlook",
                title="Outlook Graph API",
                icon_name="mail-send-symbolic",
                fields=[
                    build_labeled_field("API Key", self.quick_outlook_key_entry),
                    build_labeled_field("Request URL", self.quick_outlook_url_entry),
                ],
                on_save=lambda button: self.on_save_token_url_quick_setup(
                    button,
                    "outlook",
                    "outlook_api_key",
                    self.quick_outlook_key_entry,
                    "Outlook Graph",
                    url_settings_key="outlook_api_url",
                    url_entry=self.quick_outlook_url_entry,
                ),
                on_test=lambda button: self.on_test_token_url_quick_setup(
                    button,
                    "outlook",
                    "outlook_graph",
                    "outlook_api_key",
                    self.quick_outlook_key_entry,
                    self.quick_outlook_url_entry,
                    "Outlook Graph",
                ),
            ),
            2,
            7,
            1,
            1,
        )

        return self.build_form_panel(
            "Connector Quick Setup",
            "applications-system-symbolic",
            [quick_grid],
        )

    def build_quick_setup_card(
        self,
        card_key: str,
        title: str,
        icon_name: str,
        fields: list[Gtk.Widget],
        on_save,
        on_test,
    ) -> Gtk.Frame:
        frame = Gtk.Frame()
        frame.add_css_class("list-card")
        frame.add_css_class("integration-quick-card")
        frame.add_css_class("integration-card")
        frame.add_css_class(f"integration-card-{self.css_token(card_key)}")
        frame.add_css_class(self.integration_tone_class(card_key, ""))

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        body.set_margin_top(6)
        body.set_margin_bottom(6)
        body.set_margin_start(6)
        body.set_margin_end(6)
        body.add_css_class("integration-card-body")

        title_row = build_icon_section(title, icon_name, level="heading")
        title_row.add_css_class("integration-card-title-row")
        title_row.add_css_class(f"integration-card-title-{self.css_token(card_key)}")
        body.append(title_row)

        for field in fields:
            body.append(field)

        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        action_row.add_css_class("compact-action-row")

        save_button = Gtk.Button(label="Save")
        save_button.add_css_class("compact-action-button")
        save_button.connect("clicked", on_save)

        test_button = Gtk.Button(label="Save + Test")
        test_button.add_css_class("compact-action-button")
        test_button.add_css_class("suggested-action")
        test_button.connect("clicked", on_test)
        self.quick_test_buttons[card_key] = test_button

        action_row.append(save_button)
        action_row.append(test_button)

        status_label = Gtk.Label(label="")
        status_label.set_halign(Gtk.Align.START)
        status_label.set_wrap(True)
        status_label.add_css_class("dim-label")
        status_label.add_css_class("inline-status")
        status_label.add_css_class("integration-quick-status")
        status_label.add_css_class("integration-status-idle")
        self.quick_setup_status_labels[card_key] = status_label

        body.append(action_row)
        body.append(status_label)
        frame.set_child(body)
        return frame

    def set_quick_setup_status(self, card_key: str, message: str):
        label = self.quick_setup_status_labels.get(card_key)
        if label:
            self.apply_quick_status_tone(label, message)
            label.set_text(message)

    def apply_quick_status_tone(self, label: Gtk.Label, message: str):
        for css_class in [
            "integration-status-idle",
            "integration-status-testing",
            "integration-status-success",
            "integration-status-warning",
            "integration-status-error",
        ]:
            label.remove_css_class(css_class)

        text = str(message).strip().lower()
        if not text:
            label.add_css_class("integration-status-idle")
            return
        if "testing" in text:
            label.add_css_class("integration-status-testing")
            return
        if any(token in text for token in ["failed", "error", "invalid"]):
            label.add_css_class("integration-status-error")
            return
        if any(token in text for token in ["enter ", "missing", "first", "needs", "partial"]):
            label.add_css_class("integration-status-warning")
            return
        if any(token in text for token in ["connected", "saved", "ready", "passed"]):
            label.add_css_class("integration-status-success")
            return
        label.add_css_class("integration-status-idle")

    def save_settings_updates(self, updates: dict[str, str]):
        settings = self.settings_store.load_settings()
        for key, value in updates.items():
            settings[key] = str(value).strip()
        self.settings_store.save_settings(settings)
        self.refresh_list()

    def on_save_token_url_quick_setup(
        self,
        _button,
        card_key: str,
        settings_key: str,
        token_entry: Gtk.Entry,
        label: str,
        *,
        url_settings_key: str = "",
        url_entry: Gtk.Entry | None = None,
    ):
        token = token_entry.get_text().strip()
        updates = {settings_key: token}
        if url_settings_key and url_entry is not None:
            updates[url_settings_key] = url_entry.get_text().strip()
        self.save_settings_updates(updates)
        self.set_quick_setup_status(card_key, f"{label} settings saved.")
        self.status_label.set_text(f"Saved {label} quick setup.")

    def on_test_token_url_quick_setup(
        self,
        _button,
        card_key: str,
        integration_key: str,
        settings_key: str,
        token_entry: Gtk.Entry,
        url_entry: Gtk.Entry,
        label: str,
        payload: str = "",
        method: str = "GET",
    ):
        self.on_save_token_url_quick_setup(
            None,
            card_key,
            settings_key,
            token_entry,
            label,
            url_settings_key=f"{integration_key}_url",
            url_entry=url_entry,
        )
        token = token_entry.get_text().strip()
        url = url_entry.get_text().strip()
        if not token:
            self.set_quick_setup_status(card_key, f"Enter {label} API key first.")
            return
        if not url:
            self.set_quick_setup_status(card_key, f"Enter {label} request URL first.")
            return
        directives = {
            "api_key": token,
            "url": url,
            "method": str(method).strip().upper() or "GET",
        }
        if str(payload).strip():
            directives["payload"] = str(payload).strip()
        self.run_quick_setup_test(
            card_key=card_key,
            integration_key=integration_key,
            directives=directives,
            input_context="Quick setup test from Integrations page.",
        )

    def on_save_slack_quick_setup(self, _button):
        webhook_url = self.quick_slack_webhook_entry.get_text().strip()
        self.save_settings_updates({"slack_webhook_url": webhook_url})
        self.set_quick_setup_status("slack", "Slack settings saved.")
        self.status_label.set_text("Saved Slack quick setup.")

    def on_save_discord_quick_setup(self, _button):
        webhook_url = self.quick_discord_webhook_entry.get_text().strip()
        self.save_settings_updates({"discord_webhook_url": webhook_url})
        self.set_quick_setup_status("discord", "Discord settings saved.")
        self.status_label.set_text("Saved Discord quick setup.")

    def on_save_teams_quick_setup(self, _button):
        webhook_url = self.quick_teams_webhook_entry.get_text().strip()
        self.save_settings_updates({"teams_webhook_url": webhook_url})
        self.set_quick_setup_status("teams", "Teams settings saved.")
        self.status_label.set_text("Saved Teams quick setup.")

    def on_save_telegram_quick_setup(self, _button):
        token = self.quick_telegram_token_entry.get_text().strip()
        chat_id = self.quick_telegram_chat_entry.get_text().strip()
        self.save_settings_updates(
            {
                "telegram_bot_token": token,
                "telegram_default_chat_id": chat_id,
            }
        )
        self.set_quick_setup_status("telegram", "Telegram settings saved.")
        self.status_label.set_text("Saved Telegram quick setup.")

    def on_save_openweather_quick_setup(self, _button):
        api_key = self.quick_openweather_key_entry.get_text().strip()
        location = self.quick_openweather_location_entry.get_text().strip()
        self.save_settings_updates(
            {
                "openweather_api_key": api_key,
                "openweather_default_location": location,
            }
        )
        self.set_quick_setup_status("openweather", "OpenWeather settings saved.")
        self.status_label.set_text("Saved OpenWeather quick setup.")

    def on_save_gmail_quick_setup(self, _button):
        api_key = self.quick_gmail_key_entry.get_text().strip()
        from_address = self.quick_gmail_from_entry.get_text().strip()
        self.save_settings_updates(
            {
                "gmail_api_key": api_key,
                "gmail_from_address": from_address,
            }
        )
        self.set_quick_setup_status("gmail", "Gmail settings saved.")
        self.status_label.set_text("Saved Gmail quick setup.")

    def on_save_sheets_quick_setup(self, _button):
        api_key = self.quick_sheets_key_entry.get_text().strip()
        spreadsheet_id = self.quick_sheets_spreadsheet_entry.get_text().strip()
        range_value = self.quick_sheets_range_entry.get_text().strip()
        self.save_settings_updates(
            {
                "google_sheets_api_key": api_key,
                "google_sheets_spreadsheet_id": spreadsheet_id,
                "google_sheets_range": range_value,
            }
        )
        self.set_quick_setup_status("google_sheets", "Google Sheets settings saved.")
        self.status_label.set_text("Saved Google Sheets quick setup.")

    def on_save_apps_script_quick_setup(self, _button):
        script_url = self.quick_apps_script_url_entry.get_text().strip()
        self.save_settings_updates({"google_apps_script_url": script_url})
        self.set_quick_setup_status("apps_script", "Apps Script settings saved.")
        self.status_label.set_text("Saved Google Apps Script quick setup.")

    def on_save_github_quick_setup(self, _button):
        api_key = self.quick_github_key_entry.get_text().strip()
        url = self.quick_github_url_entry.get_text().strip()
        self.save_settings_updates(
            {
                "github_api_key": api_key,
                "github_api_url": url,
            }
        )
        self.set_quick_setup_status("github", "GitHub settings saved.")
        self.status_label.set_text("Saved GitHub quick setup.")

    def on_save_notion_quick_setup(self, _button):
        api_key = self.quick_notion_key_entry.get_text().strip()
        url = self.quick_notion_url_entry.get_text().strip()
        self.save_settings_updates(
            {
                "notion_api_key": api_key,
                "notion_api_url": url,
            }
        )
        self.set_quick_setup_status("notion", "Notion settings saved.")
        self.status_label.set_text("Saved Notion quick setup.")

    def on_save_hubspot_quick_setup(self, _button):
        api_key = self.quick_hubspot_key_entry.get_text().strip()
        url = self.quick_hubspot_url_entry.get_text().strip()
        self.save_settings_updates(
            {
                "hubspot_api_key": api_key,
                "hubspot_api_url": url,
            }
        )
        self.set_quick_setup_status("hubspot", "HubSpot settings saved.")
        self.status_label.set_text("Saved HubSpot quick setup.")

    def on_save_stripe_quick_setup(self, _button):
        api_key = self.quick_stripe_key_entry.get_text().strip()
        url = self.quick_stripe_url_entry.get_text().strip()
        self.save_settings_updates(
            {
                "stripe_api_key": api_key,
                "stripe_api_url": url,
            }
        )
        self.set_quick_setup_status("stripe", "Stripe settings saved.")
        self.status_label.set_text("Saved Stripe quick setup.")

    def on_save_twilio_quick_setup(self, _button):
        account_sid = self.quick_twilio_sid_entry.get_text().strip()
        auth_token = self.quick_twilio_token_entry.get_text().strip()
        from_number = self.quick_twilio_from_entry.get_text().strip()
        self.save_settings_updates(
            {
                "twilio_account_sid": account_sid,
                "twilio_auth_token": auth_token,
                "twilio_from_number": from_number,
            }
        )
        self.set_quick_setup_status("twilio", "Twilio settings saved.")
        self.status_label.set_text("Saved Twilio quick setup.")

    def on_test_slack_quick_setup(self, _button):
        self.on_save_slack_quick_setup(None)
        webhook_url = self.quick_slack_webhook_entry.get_text().strip()
        if not webhook_url:
            self.set_quick_setup_status("slack", "Enter Slack webhook URL first.")
            return
        self.run_quick_setup_test(
            card_key="slack",
            integration_key="slack_webhook",
            directives={
                "webhook_url": webhook_url,
                "text": "6X Protocol Studio quick setup test.",
            },
            input_context="Quick setup test from Integrations page.",
        )

    def on_test_discord_quick_setup(self, _button):
        self.on_save_discord_quick_setup(None)
        webhook_url = self.quick_discord_webhook_entry.get_text().strip()
        if not webhook_url:
            self.set_quick_setup_status("discord", "Enter Discord webhook URL first.")
            return
        self.run_quick_setup_test(
            card_key="discord",
            integration_key="discord_webhook",
            directives={
                "webhook_url": webhook_url,
                "content": "6X Protocol Studio quick setup test.",
            },
            input_context="Quick setup test from Integrations page.",
        )

    def on_test_teams_quick_setup(self, _button):
        self.on_save_teams_quick_setup(None)
        webhook_url = self.quick_teams_webhook_entry.get_text().strip()
        if not webhook_url:
            self.set_quick_setup_status("teams", "Enter Teams webhook URL first.")
            return
        self.run_quick_setup_test(
            card_key="teams",
            integration_key="teams_webhook",
            directives={
                "webhook_url": webhook_url,
                "text": "6X Protocol Studio quick setup test.",
            },
            input_context="Quick setup test from Integrations page.",
        )

    def on_test_telegram_quick_setup(self, _button):
        self.on_save_telegram_quick_setup(None)
        token = self.quick_telegram_token_entry.get_text().strip()
        chat_id = self.quick_telegram_chat_entry.get_text().strip()
        if not token:
            self.set_quick_setup_status("telegram", "Enter Telegram bot token first.")
            return
        if not chat_id:
            self.set_quick_setup_status("telegram", "Enter Telegram chat id first.")
            return
        self.run_quick_setup_test(
            card_key="telegram",
            integration_key="telegram_bot",
            directives={
                "api_key": token,
                "chat_id": chat_id,
                "message": "6X Protocol Studio quick setup test.",
            },
            input_context="Quick setup test from Integrations page.",
        )

    def on_test_openweather_quick_setup(self, _button):
        self.on_save_openweather_quick_setup(None)
        api_key = self.quick_openweather_key_entry.get_text().strip()
        location = self.quick_openweather_location_entry.get_text().strip()
        if not api_key:
            self.set_quick_setup_status("openweather", "Enter OpenWeather API key first.")
            return
        if not location:
            self.set_quick_setup_status("openweather", "Enter a location first.")
            return
        self.run_quick_setup_test(
            card_key="openweather",
            integration_key="openweather_current",
            directives={
                "api_key": api_key,
                "location": location,
                "units": "metric",
            },
            input_context="Quick setup test from Integrations page.",
        )

    def on_test_gmail_quick_setup(self, _button):
        self.on_save_gmail_quick_setup(None)
        api_key = self.quick_gmail_key_entry.get_text().strip()
        from_address = self.quick_gmail_from_entry.get_text().strip()
        if not api_key:
            self.set_quick_setup_status("gmail", "Enter Gmail OAuth token first.")
            return
        if not from_address:
            self.set_quick_setup_status("gmail", "Enter a Gmail from address first.")
            return
        self.run_quick_setup_test(
            card_key="gmail",
            integration_key="gmail_send",
            directives={
                "api_key": api_key,
                "from": from_address,
                "to": from_address,
                "subject": "6X quick setup test",
                "message": "Gmail quick setup is connected.",
            },
            input_context="Quick setup test from Integrations page.",
        )

    def on_test_sheets_quick_setup(self, _button):
        self.on_save_sheets_quick_setup(None)
        api_key = self.quick_sheets_key_entry.get_text().strip()
        spreadsheet_id = self.quick_sheets_spreadsheet_entry.get_text().strip()
        range_value = self.quick_sheets_range_entry.get_text().strip()
        if not api_key:
            self.set_quick_setup_status("google_sheets", "Enter Google Sheets OAuth token first.")
            return
        if not spreadsheet_id:
            self.set_quick_setup_status("google_sheets", "Enter spreadsheet ID first.")
            return
        if not range_value:
            self.set_quick_setup_status("google_sheets", "Enter range first.")
            return
        self.run_quick_setup_test(
            card_key="google_sheets",
            integration_key="google_sheets",
            directives={
                "api_key": api_key,
                "spreadsheet_id": spreadsheet_id,
                "range": range_value,
                "payload": "{\"values\":[[\"6X Quick Test\",\"Connected\"]]}",
            },
            input_context="Quick setup test from Integrations page.",
        )

    def on_test_apps_script_quick_setup(self, _button):
        self.on_save_apps_script_quick_setup(None)
        script_url = self.quick_apps_script_url_entry.get_text().strip()
        if not script_url:
            self.set_quick_setup_status("apps_script", "Enter Script URL first.")
            return
        self.run_quick_setup_test(
            card_key="apps_script",
            integration_key="google_apps_script",
            directives={
                "script_url": script_url,
                "payload": "{\"source\":\"6X\",\"event\":\"quick_setup_test\"}",
            },
            input_context="Quick setup test from Integrations page.",
        )

    def on_test_github_quick_setup(self, _button):
        self.on_save_github_quick_setup(None)
        api_key = self.quick_github_key_entry.get_text().strip()
        url = self.quick_github_url_entry.get_text().strip()
        if not api_key:
            self.set_quick_setup_status("github", "Enter GitHub API key first.")
            return
        if not url:
            self.set_quick_setup_status("github", "Enter GitHub request URL first.")
            return
        self.run_quick_setup_test(
            card_key="github",
            integration_key="github_rest",
            directives={
                "api_key": api_key,
                "url": url,
                "method": "GET",
            },
            input_context="Quick setup test from Integrations page.",
        )

    def on_test_notion_quick_setup(self, _button):
        self.on_save_notion_quick_setup(None)
        api_key = self.quick_notion_key_entry.get_text().strip()
        url = self.quick_notion_url_entry.get_text().strip()
        if not api_key:
            self.set_quick_setup_status("notion", "Enter Notion API key first.")
            return
        if not url:
            self.set_quick_setup_status("notion", "Enter Notion request URL first.")
            return
        self.run_quick_setup_test(
            card_key="notion",
            integration_key="notion_api",
            directives={
                "api_key": api_key,
                "url": url,
                "method": "GET",
                "headers": "{\"Notion-Version\":\"2022-06-28\"}",
            },
            input_context="Quick setup test from Integrations page.",
        )

    def on_test_hubspot_quick_setup(self, _button):
        self.on_save_hubspot_quick_setup(None)
        api_key = self.quick_hubspot_key_entry.get_text().strip()
        url = self.quick_hubspot_url_entry.get_text().strip()
        if not api_key:
            self.set_quick_setup_status("hubspot", "Enter HubSpot API key first.")
            return
        if not url:
            self.set_quick_setup_status("hubspot", "Enter HubSpot request URL first.")
            return
        self.run_quick_setup_test(
            card_key="hubspot",
            integration_key="hubspot_api",
            directives={
                "api_key": api_key,
                "url": url,
                "method": "GET",
            },
            input_context="Quick setup test from Integrations page.",
        )

    def on_test_stripe_quick_setup(self, _button):
        self.on_save_stripe_quick_setup(None)
        api_key = self.quick_stripe_key_entry.get_text().strip()
        url = self.quick_stripe_url_entry.get_text().strip()
        if not api_key:
            self.set_quick_setup_status("stripe", "Enter Stripe API key first.")
            return
        if not url:
            self.set_quick_setup_status("stripe", "Enter Stripe request URL first.")
            return
        self.run_quick_setup_test(
            card_key="stripe",
            integration_key="stripe_api",
            directives={
                "api_key": api_key,
                "url": url,
                "method": "GET",
            },
            input_context="Quick setup test from Integrations page.",
        )

    def on_test_twilio_quick_setup(self, _button):
        self.on_save_twilio_quick_setup(None)
        account_sid = self.quick_twilio_sid_entry.get_text().strip()
        auth_token = self.quick_twilio_token_entry.get_text().strip()
        from_number = self.quick_twilio_from_entry.get_text().strip()
        to_number = self.quick_twilio_to_entry.get_text().strip()
        if not account_sid:
            self.set_quick_setup_status("twilio", "Enter Twilio Account SID first.")
            return
        if not auth_token:
            self.set_quick_setup_status("twilio", "Enter Twilio Auth Token first.")
            return
        if not from_number:
            self.set_quick_setup_status("twilio", "Enter Twilio from number first.")
            return
        if not to_number:
            self.set_quick_setup_status("twilio", "Enter Twilio to number first.")
            return
        self.run_quick_setup_test(
            card_key="twilio",
            integration_key="twilio_sms",
            directives={
                "account_sid": account_sid,
                "auth_token": auth_token,
                "from": from_number,
                "to": to_number,
                "message": "6X Protocol Studio quick setup test.",
            },
            input_context="Quick setup test from Integrations page.",
        )

    def run_quick_setup_test(
        self,
        card_key: str,
        integration_key: str,
        directives: dict[str, str],
        input_context: str,
    ):
        button = self.quick_test_buttons.get(card_key)
        if button:
            button.set_sensitive(False)
        self.set_quick_setup_status(card_key, f"Testing {integration_key}...")
        self.test_status_label.set_text(f"Running quick test for '{integration_key}'...")
        self.test_output_buffer.set_text("")

        directives_text = "\n".join(
            f"{key}: {str(value).strip()}"
            for key, value in directives.items()
            if str(value).strip()
        )

        threading.Thread(
            target=self._run_quick_setup_test_worker,
            args=(card_key, integration_key, directives_text, input_context),
            daemon=True,
        ).start()

    def _run_quick_setup_test_worker(
        self,
        card_key: str,
        integration_key: str,
        directives_text: str,
        input_context: str,
    ):
        try:
            result = self.integration_test_service.run_test(
                integration_key=integration_key,
                directives_text=directives_text,
                input_context=input_context,
            )
        except Exception as error:
            GLib.idle_add(
                self._finish_quick_setup_test_error,
                card_key,
                integration_key,
                str(error),
            )
            return
        GLib.idle_add(
            self._finish_quick_setup_test_success,
            card_key,
            integration_key,
            result,
        )

    def _finish_quick_setup_test_success(
        self,
        card_key: str,
        integration_key: str,
        result: dict[str, str],
    ):
        button = self.quick_test_buttons.get(card_key)
        if button:
            button.set_sensitive(True)

        output = result.get("output", "")
        logs = result.get("logs", "")
        summary = result.get("summary", "Integration test completed.")
        formatted = (
            f"Output:\n{output or '(No output)'}\n\n"
            f"Logs:\n{logs or '(No logs)'}"
        )
        self.test_output_buffer.set_text(formatted)
        self.test_status_label.set_text(f"Integration '{integration_key}' test passed. {summary}")
        self.set_quick_setup_status(card_key, "Connected and tested.")
        self.refresh_list()
        return False

    def _finish_quick_setup_test_error(
        self,
        card_key: str,
        integration_key: str,
        error_message: str,
    ):
        button = self.quick_test_buttons.get(card_key)
        if button:
            button.set_sensitive(True)
        self.test_status_label.set_text(f"Integration '{integration_key}' test failed: {error_message}")
        self.set_quick_setup_status(card_key, f"Test failed: {error_message}")
        return False

    def on_install_pack(self, _button):
        path_value = self.path_entry.get_text().strip()
        if not path_value:
            self.status_label.set_text("Enter a pack file path first.")
            return

        ok, message = self.registry.install_pack_from_file(path_value)
        self.status_label.set_text(message)
        if ok:
            self.path_entry.set_text("")
            self.refresh_list()

    def on_refresh_clicked(self, _button):
        self.refresh_list()
        self.status_label.set_text("Integrations refreshed.")

    def on_filters_changed(self, *_args):
        self.refresh_list()

    def on_category_changed(self, *_args):
        if self.loading_category_selection:
            return
        selected = self.category_dropdown.get_selected()
        if selected <= 0 or selected > len(self.category_options):
            self.category_filter = "all"
        else:
            self.category_filter = self.category_options[selected - 1]
        self.refresh_list()

    def build_form_panel(
        self,
        title: str,
        icon_name: str,
        rows: list[Gtk.Widget],
    ) -> Gtk.Frame:
        panel = Gtk.Frame()
        panel.add_css_class("settings-subpanel")
        panel.add_css_class("canvas-edit-detail-frame")

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
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

    def build_source_filter_row(self) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.add_css_class("segmented-row")
        row.add_css_class("compact-segmented-row")

        self.source_filter_buttons: dict[str, Gtk.ToggleButton] = {}
        for key, label in [
            ("all", "All"),
            ("built-in", "Built-In"),
            ("external", "External"),
        ]:
            button = Gtk.ToggleButton(label=label)
            button.add_css_class("segmented-button")
            button.add_css_class("compact-segmented-button")
            button.connect("toggled", self.on_source_filter_toggled, key)
            row.append(button)
            self.source_filter_buttons[key] = button

        self.source_filter_buttons["all"].set_active(True)
        return row

    def on_source_filter_toggled(self, button: Gtk.ToggleButton, key: str):
        if not button.get_active():
            if not any(item.get_active() for item in self.source_filter_buttons.values()):
                button.set_active(True)
            return

        for other_key, other in self.source_filter_buttons.items():
            if other_key != key and other.get_active():
                other.set_active(False)
        self.source_filter = key
        self.refresh_list()

    def on_reset_filters(self, _button):
        self.search_entry.set_text("")
        self.source_filter_buttons["all"].set_active(True)
        self.category_dropdown.set_selected(0)
        self.refresh_list()

    def selected_test_integration_key(self) -> str:
        if not self.test_integration_dropdown:
            return ""
        index = self.test_integration_dropdown.get_selected()
        if 0 <= index < len(self.test_integration_keys):
            return self.test_integration_keys[index]
        return ""

    def rebuild_test_dropdown(self):
        if self.test_integration_dropdown:
            self.test_dropdown_container.remove(self.test_integration_dropdown)

        if not self.integrations:
            self.test_integration_keys = []
            self.test_integration_dropdown = Gtk.DropDown.new_from_strings(
                ["No integrations available"]
            )
            self.test_integration_dropdown.set_sensitive(False)
            self.test_dropdown_container.append(self.test_integration_dropdown)
            return

        labels = [
            f"{item.get('name', 'Integration')}  ({item.get('key', '')})"
            for item in self.integrations
        ]
        self.test_integration_keys = [str(item.get("key", "")).strip().lower() for item in self.integrations]
        self.test_integration_dropdown = Gtk.DropDown.new_from_strings(labels)
        self.test_integration_dropdown.set_selected(0)
        self.test_integration_dropdown.set_hexpand(True)
        self.test_integration_dropdown.set_sensitive(True)
        self.test_integration_dropdown.connect(
            "notify::selected",
            self.on_test_integration_changed,
        )
        self.test_dropdown_container.append(self.test_integration_dropdown)
        self.on_test_integration_changed()

    def on_test_integration_changed(self, *_args):
        key = self.selected_test_integration_key()
        if not key:
            return

        loaded_profile = self.load_saved_profile(key)
        if loaded_profile:
            return

        integration = self.registry.get_integration(key)
        if not integration:
            return

        required = integration.get("required_fields", [])
        if not required:
            self.test_directives_buffer.set_text("")
            return

        existing = self.test_directives_buffer.get_text(
            self.test_directives_buffer.get_start_iter(),
            self.test_directives_buffer.get_end_iter(),
            False,
        ).strip()
        if existing:
            return

        template_lines = [f"{field}: " for field in required]
        self.test_directives_buffer.set_text("\n".join(template_lines))

    def on_load_required_template_clicked(self, _button):
        key = self.selected_test_integration_key()
        if not key:
            self.test_status_label.set_text("Select an integration first.")
            return

        integration = self.registry.get_integration(key)
        if not integration:
            self.test_status_label.set_text("Could not load integration details.")
            return

        required = integration.get("required_fields", [])
        if not required:
            self.test_directives_buffer.set_text("")
            self.test_status_label.set_text("This integration has no required fields.")
            return

        template_lines = [f"{field}: " for field in required]
        self.test_directives_buffer.set_text("\n".join(template_lines))
        self.test_status_label.set_text("Loaded required field template.")

    def on_clear_test_output_clicked(self, _button):
        self.test_output_buffer.set_text("")
        self.test_status_label.set_text("")

    def on_save_profile_clicked(self, _button):
        key = self.selected_test_integration_key()
        if not key:
            self.test_status_label.set_text("Select an integration first.")
            return

        directives = self.test_directives_buffer.get_text(
            self.test_directives_buffer.get_start_iter(),
            self.test_directives_buffer.get_end_iter(),
            False,
        ).strip()
        profile = {
            "input_context": self.test_input_entry.get_text().strip(),
            "directives": directives,
        }
        self.integration_settings_store.save_profile(key, profile)
        self.test_status_label.set_text(f"Saved test profile for '{key}'.")

    def on_load_profile_clicked(self, _button):
        key = self.selected_test_integration_key()
        if not key:
            self.test_status_label.set_text("Select an integration first.")
            return

        if self.load_saved_profile(key):
            self.test_status_label.set_text(f"Loaded saved test profile for '{key}'.")
            return
        self.test_status_label.set_text(f"No saved profile found for '{key}'.")

    def on_delete_profile_clicked(self, _button):
        key = self.selected_test_integration_key()
        if not key:
            self.test_status_label.set_text("Select an integration first.")
            return

        self.integration_settings_store.delete_profile(key)
        self.test_status_label.set_text(f"Deleted saved test profile for '{key}'.")
        self.test_input_entry.set_text("")
        self.on_load_required_template_clicked(None)

    def on_run_test_clicked(self, _button):
        key = self.selected_test_integration_key()
        if not key:
            self.test_status_label.set_text("Select an integration to test.")
            return

        directives = self.test_directives_buffer.get_text(
            self.test_directives_buffer.get_start_iter(),
            self.test_directives_buffer.get_end_iter(),
            False,
        )
        input_context = self.test_input_entry.get_text().strip()

        self.run_test_button.set_sensitive(False)
        self.test_status_label.set_text(f"Running integration test for '{key}'...")
        self.test_output_buffer.set_text("")

        threading.Thread(
            target=self._run_test_worker,
            args=(key, directives, input_context),
            daemon=True,
        ).start()

    def _run_test_worker(self, key: str, directives: str, input_context: str):
        try:
            result = self.integration_test_service.run_test(
                integration_key=key,
                directives_text=directives,
                input_context=input_context,
            )
        except Exception as error:
            GLib.idle_add(self._finish_test_error, key, str(error))
            return
        GLib.idle_add(self._finish_test_success, key, result)

    def _finish_test_success(self, key: str, result: dict[str, str]):
        self.run_test_button.set_sensitive(True)
        output = result.get("output", "")
        logs = result.get("logs", "")
        summary = result.get("summary", "Integration test completed.")
        formatted = (
            f"Output:\n{output or '(No output)'}\n\n"
            f"Logs:\n{logs or '(No logs)'}"
        )
        self.test_output_buffer.set_text(formatted)
        self.test_status_label.set_text(f"Integration '{key}' test passed. {summary}")
        return False

    def _finish_test_error(self, key: str, error_message: str):
        self.run_test_button.set_sensitive(True)
        self.test_status_label.set_text(f"Integration '{key}' test failed: {error_message}")
        return False

    def load_saved_profile(self, key: str) -> bool:
        profile = self.integration_settings_store.get_profile(key)
        if not profile:
            return False

        self.test_input_entry.set_text(profile.get("input_context", ""))
        self.test_directives_buffer.set_text(profile.get("directives", ""))
        return True

    def filtered_integrations(self, integrations: list[dict]) -> list[dict]:
        query = self.search_entry.get_text().strip().lower()
        source_filter = self.source_filter
        category_filter = self.category_filter

        filtered: list[dict] = []
        for integration in integrations:
            source = str(integration.get("source", "")).strip().lower()
            is_builtin = source == "built-in"
            if source_filter == "built-in" and not is_builtin:
                continue
            if source_filter == "external" and is_builtin:
                continue

            category = str(integration.get("category", "")).strip().lower()
            if category_filter != "all" and category != category_filter:
                continue

            if query:
                haystack = (
                    f"{integration.get('name', '')} "
                    f"{integration.get('key', '')} "
                    f"{integration.get('handler', '')} "
                    f"{integration.get('description', '')} "
                    f"{integration.get('category', '')} "
                    f"{integration.get('auth_type', '')}"
                ).strip().lower()
                if query not in haystack:
                    continue

            filtered.append(integration)
        return filtered

    def refresh_list(self):
        if not hasattr(self, "list_box"):
            return
        child = self.list_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.list_box.remove(child)
            child = next_child

        all_integrations = self.registry.list_integrations()
        self.integrations = all_integrations
        self.rebuild_category_dropdown(all_integrations)
        self.rebuild_test_dropdown()
        integrations = self.filtered_integrations(all_integrations)
        self.empty_label.set_visible(len(integrations) == 0)

        for integration in integrations:
            self.list_box.append(self.build_card(integration))

    def rebuild_category_dropdown(self, integrations: list[dict]):
        categories = sorted(
            {
                str(item.get("category", "")).strip()
                for item in integrations
                if str(item.get("category", "")).strip()
            },
            key=lambda item: item.lower(),
        )
        self.category_options = [item.lower() for item in categories]
        labels = ["All Categories", *categories]
        replacement = Gtk.DropDown.new_from_strings(labels)
        replacement.connect("notify::selected", self.on_category_changed)

        previous = getattr(self, "category_dropdown", None)
        if previous and previous.get_parent() is self.header_action_row:
            self.header_action_row.remove(previous)
            self.header_action_row.insert_child_after(replacement, self.search_entry)
        self.category_dropdown = replacement

        self.loading_category_selection = True
        try:
            if self.category_filter != "all" and self.category_filter in self.category_options:
                self.category_dropdown.set_selected(self.category_options.index(self.category_filter) + 1)
            else:
                self.category_dropdown.set_selected(0)
                self.category_filter = "all"
        finally:
            self.loading_category_selection = False

    def build_card(self, integration: dict) -> Gtk.Frame:
        frame = Gtk.Frame()
        frame.add_css_class("list-card")
        frame.add_css_class("entity-card")
        frame.add_css_class("integration-card")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(6)
        box.set_margin_end(6)

        title = Gtk.Label(label=f"{integration.get('name', '')}  ({integration.get('key', '')})")
        title.add_css_class("heading")
        title.set_halign(Gtk.Align.START)

        description = Gtk.Label(label=integration.get("description", ""))
        description.set_wrap(True)
        description.set_halign(Gtk.Align.START)

        source = str(integration.get("source", "Unknown")).strip()
        handler = str(integration.get("handler", "")).strip()
        category = str(integration.get("category", "General")).strip()
        auth_type = str(integration.get("auth_type", "custom")).strip()
        key = str(integration.get("key", "")).strip().lower()

        frame.add_css_class(f"integration-card-{self.css_token(key)}")
        frame.add_css_class(self.integration_tone_class(key, category))

        required = integration.get("required_fields", [])
        required_text = ", ".join(required) if required else "None"
        connection_label, connection_css = self.integration_connection_chip(integration)

        chip_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        chip_row.set_halign(Gtk.Align.START)

        source_chip = Gtk.Label(label=f"Source • {source}")
        source_chip.add_css_class("status-chip")
        source_chip.add_css_class("integration-meta-chip")
        source_chip.add_css_class(
            "integration-chip-builtin"
            if source.lower() == "built-in"
            else "integration-chip-external"
        )

        handler_chip = Gtk.Label(label=f"Handler • {handler or 'unknown'}")
        handler_chip.add_css_class("status-chip")
        handler_chip.add_css_class("integration-meta-chip")
        handler_chip.add_css_class("integration-chip-handler")

        required_chip = Gtk.Label(label=f"Required {len(required)}")
        required_chip.add_css_class("status-chip")
        required_chip.add_css_class("integration-meta-chip")
        required_chip.add_css_class("integration-chip-required")

        category_chip = Gtk.Label(label=f"Category • {category}")
        category_chip.add_css_class("status-chip")
        category_chip.add_css_class("integration-meta-chip")
        category_chip.add_css_class("integration-chip-category")

        connection_chip = Gtk.Label(label=connection_label)
        connection_chip.add_css_class("status-chip")
        connection_chip.add_css_class("integration-meta-chip")
        connection_chip.add_css_class(connection_css)

        chip_row.append(source_chip)
        chip_row.append(category_chip)
        chip_row.append(handler_chip)
        chip_row.append(required_chip)
        chip_row.append(connection_chip)

        meta = Gtk.Label(
            label=(
                f"Source: {source}  •  "
                f"Category: {category}  •  "
                f"Handler: {handler}  •  "
                f"Auth: {auth_type}  •  "
                f"Required fields: {required_text}"
            )
        )
        meta.set_wrap(True)
        meta.set_halign(Gtk.Align.START)
        meta.add_css_class("dim-label")

        box.append(title)
        box.append(description)
        box.append(chip_row)
        box.append(meta)
        frame.set_child(box)
        return frame

    def css_token(self, value: str) -> str:
        text = str(value).strip().lower().replace("_", "-").replace(" ", "-")
        cleaned = "".join(char for char in text if char.isalnum() or char == "-")
        return cleaned or "default"

    def integration_tone_class(self, key: str, category: str) -> str:
        normalized_key = str(key).strip().lower()
        normalized_category = str(category).strip().lower()

        if normalized_key in {
            "slack",
            "slack_webhook",
            "discord",
            "discord_webhook",
            "teams",
            "teams_webhook",
            "telegram",
            "telegram_bot",
            "outlook",
            "outlook_graph",
        }:
            return "integration-tone-communication"
        if normalized_key in {"gmail", "gmail_send", "twilio", "twilio_sms", "resend_email", "mailgun_email"}:
            return "integration-tone-messaging"
        if normalized_key in {"openweather", "openweather_current"}:
            return "integration-tone-weather"
        if normalized_key in {
            "google_sheets",
            "apps_script",
            "google_apps_script",
            "google_calendar",
            "google_calendar_api",
        }:
            return "integration-tone-google"
        if normalized_key in {"github", "github_rest", "gitlab", "gitlab_api", "linear_api"}:
            return "integration-tone-dev"
        if normalized_key in {
            "notion",
            "notion_api",
            "airtable_api",
            "hubspot",
            "hubspot_api",
            "jira",
            "jira_api",
            "asana",
            "asana_api",
            "clickup",
            "clickup_api",
            "trello",
            "trello_api",
            "monday",
            "monday_api",
            "zendesk",
            "zendesk_api",
            "salesforce",
            "salesforce_api",
            "pipedrive",
            "pipedrive_api",
        }:
            return "integration-tone-productivity"
        if normalized_key in {"stripe", "stripe_api"}:
            return "integration-tone-commerce"
        if normalized_category in {"communication", "messaging"}:
            return "integration-tone-messaging"
        if normalized_category in {"project", "support", "crm", "productivity"}:
            return "integration-tone-productivity"
        if normalized_category in {"developer"}:
            return "integration-tone-dev"
        if normalized_category in {"database", "storage", "data"}:
            return "integration-tone-data"
        if normalized_category in {"automation", "workflow"}:
            return "integration-tone-automation"
        return "integration-tone-default"

    def parse_directives(self, text: str) -> dict[str, str]:
        parsed: dict[str, str] = {}
        for line in str(text).splitlines():
            raw = line.strip()
            if not raw or ":" not in raw:
                continue
            key, value = raw.split(":", 1)
            normalized = key.strip().lower()
            if not normalized:
                continue
            parsed[normalized] = value.strip()
        return parsed

    def integration_connection_chip(self, integration: dict) -> tuple[str, str]:
        key = str(integration.get("key", "")).strip().lower()
        required = [
            str(item).strip().lower()
            for item in integration.get("required_fields", [])
            if str(item).strip()
        ]
        settings = self.settings_store.load_settings()
        profile = self.integration_settings_store.get_profile(key)
        directives = self.parse_directives(profile.get("directives", ""))
        integration_defaults: dict[str, dict[str, str]] = {
            "slack_webhook": {
                "webhook_url": str(settings.get("slack_webhook_url", "")).strip(),
            },
            "discord_webhook": {
                "webhook_url": str(settings.get("discord_webhook_url", "")).strip(),
            },
            "teams_webhook": {
                "webhook_url": str(settings.get("teams_webhook_url", "")).strip(),
            },
            "telegram_bot": {
                "api_key": str(settings.get("telegram_bot_token", "")).strip(),
                "chat_id": str(settings.get("telegram_default_chat_id", "")).strip(),
            },
            "openweather_current": {
                "api_key": str(settings.get("openweather_api_key", "")).strip(),
                "location": str(settings.get("openweather_default_location", "")).strip(),
            },
            "google_apps_script": {
                "script_url": str(settings.get("google_apps_script_url", "")).strip(),
            },
            "google_sheets": {
                "api_key": str(settings.get("google_sheets_api_key", "")).strip(),
                "spreadsheet_id": str(settings.get("google_sheets_spreadsheet_id", "")).strip(),
                "range": str(settings.get("google_sheets_range", "")).strip(),
            },
            "google_calendar_api": {
                "api_key": str(settings.get("google_calendar_api_key", "")).strip(),
                "url": str(settings.get("google_calendar_api_url", "")).strip(),
            },
            "outlook_graph": {
                "api_key": str(settings.get("outlook_api_key", "")).strip(),
                "url": str(settings.get("outlook_api_url", "")).strip(),
            },
            "gmail_send": {
                "api_key": str(settings.get("gmail_api_key", "")).strip(),
                "from": str(settings.get("gmail_from_address", "")).strip(),
            },
            "notion_api": {
                "api_key": str(settings.get("notion_api_key", "")).strip(),
                "url": str(settings.get("notion_api_url", "")).strip(),
            },
            "airtable_api": {
                "api_key": str(settings.get("airtable_api_key", "")).strip(),
                "url": str(settings.get("airtable_api_url", "")).strip(),
            },
            "hubspot_api": {
                "api_key": str(settings.get("hubspot_api_key", "")).strip(),
                "url": str(settings.get("hubspot_api_url", "")).strip(),
            },
            "stripe_api": {
                "api_key": str(settings.get("stripe_api_key", "")).strip(),
                "url": str(settings.get("stripe_api_url", "")).strip(),
            },
            "github_rest": {
                "api_key": str(settings.get("github_api_key", "")).strip(),
                "url": str(settings.get("github_api_url", "")).strip(),
            },
            "linear_api": {"api_key": str(settings.get("linear_api_key", "")).strip()},
            "jira_api": {
                "api_key": str(settings.get("jira_api_key", "")).strip(),
                "url": str(settings.get("jira_api_url", "")).strip(),
            },
            "asana_api": {
                "api_key": str(settings.get("asana_api_key", "")).strip(),
                "url": str(settings.get("asana_api_url", "")).strip(),
            },
            "clickup_api": {
                "api_key": str(settings.get("clickup_api_key", "")).strip(),
                "url": str(settings.get("clickup_api_url", "")).strip(),
            },
            "trello_api": {
                "api_key": str(settings.get("trello_api_key", "")).strip(),
                "url": str(settings.get("trello_api_url", "")).strip(),
            },
            "monday_api": {
                "api_key": str(settings.get("monday_api_key", "")).strip(),
                "url": str(settings.get("monday_api_url", "")).strip(),
            },
            "zendesk_api": {
                "api_key": str(settings.get("zendesk_api_key", "")).strip(),
                "url": str(settings.get("zendesk_api_url", "")).strip(),
            },
            "pipedrive_api": {
                "api_key": str(settings.get("pipedrive_api_key", "")).strip(),
                "url": str(settings.get("pipedrive_api_url", "")).strip(),
            },
            "salesforce_api": {
                "api_key": str(settings.get("salesforce_api_key", "")).strip(),
                "url": str(settings.get("salesforce_api_url", "")).strip(),
            },
            "gitlab_api": {
                "api_key": str(settings.get("gitlab_api_key", "")).strip(),
                "url": str(settings.get("gitlab_api_url", "")).strip(),
            },
            "twilio_sms": {
                "account_sid": str(settings.get("twilio_account_sid", "")).strip(),
                "auth_token": str(settings.get("twilio_auth_token", "")).strip(),
                "from": str(settings.get("twilio_from_number", "")).strip(),
            },
            "resend_email": {
                "api_key": str(settings.get("resend_api_key", "")).strip(),
                "from": str(settings.get("resend_from_address", "")).strip(),
            },
            "mailgun_email": {
                "api_key": str(settings.get("mailgun_api_key", "")).strip(),
                "domain": str(settings.get("mailgun_domain", "")).strip(),
                "from": str(settings.get("mailgun_from_address", "")).strip(),
            },
            "postgres_sql": {
                "connection_url": str(settings.get("postgres_connection_url", "")).strip(),
            },
            "mysql_sql": {
                "connection_url": str(settings.get("mysql_connection_url", "")).strip(),
            },
            "redis_command": {
                "connection_url": str(settings.get("redis_connection_url", "")).strip(),
            },
        }
        alias_groups: dict[str, list[str]] = {
            "url": ["webhook_url", "script_url", "endpoint"],
            "webhook_url": ["url"],
            "script_url": ["url"],
            "api_key": ["token", "bearer", "authorization"],
            "connection_url": ["url", "database_url"],
        }

        available_values = dict(directives)
        for field, value in integration_defaults.get(key, {}).items():
            normalized_value = str(value).strip()
            if not normalized_value:
                continue
            available_values.setdefault(field, normalized_value)
            for alias in alias_groups.get(field, []):
                available_values.setdefault(alias, normalized_value)

        def has_field_value(field_name: str) -> bool:
            direct = str(available_values.get(field_name, "")).strip()
            if direct:
                return True
            for alias in alias_groups.get(field_name, []):
                if str(available_values.get(alias, "")).strip():
                    return True
            for canonical, aliases in alias_groups.items():
                if field_name in aliases and str(available_values.get(canonical, "")).strip():
                    return True
            return False

        if not required:
            return ("Ready", "integration-chip-ready")

        missing = [field for field in required if not has_field_value(field)]
        if not missing:
            return ("Connected", "integration-chip-ready")
        if len(missing) < len(required):
            return ("Partial Setup", "integration-chip-partial")
        return ("Needs Setup", "integration-chip-setup")
