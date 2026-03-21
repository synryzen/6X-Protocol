import gi
import json
import math
import re
import threading
import uuid

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GLib, Gdk

from src.models.canvas_edge import CanvasEdge
from src.models.canvas_node import CanvasNode
from src.models.run_record import RunRecord
from src.models.workflow import Workflow
from src.services.canvas_layout_service import CanvasLayoutService
from src.services.execution_engine import ExecutionEngine
from src.services.integration_registry_service import IntegrationRegistryService
from src.services.run_execution_service import get_run_execution_service
from src.services.run_store import RunStore
from src.services.settings_store import SettingsStore
from src.services.template_marketplace_service import TemplateMarketplaceService
from src.services.workflow_validation_service import WorkflowValidationService
from src.services.workflow_store import WorkflowStore
from src.ui import build_icon_section, create_icon, wrap_horizontal_row


class CanvasView(Gtk.Box):
    CARD_WIDTH = 162
    CARD_HEIGHT = 84
    STAGE_WIDTH = 2000
    STAGE_HEIGHT = 1200
    MIN_ZOOM = 0.7
    MAX_ZOOM = 1.6
    ZOOM_STEP = 0.1
    SNAP_GRID = 20
    ALIGN_SNAP_DISTANCE = 14
    LINK_TARGET_SNAP_DISTANCE = 190
    LINK_TYPES = ["next", "true", "false"]
    PROVIDER_OPTIONS = ["inherit", "local", "openai", "anthropic"]
    TRIGGER_MODE_OPTIONS = ["manual", "schedule_interval", "webhook", "file_watch", "cron"]
    CONDITION_MODE_OPTIONS = ["contains", "equals", "not_contains", "regex", "min_len", "true", "false", "raw"]
    EXECUTION_PRESETS = {
        "safe": {"retry_max": 0, "retry_backoff_ms": 0, "timeout_sec": 30.0},
        "balanced": {"retry_max": 1, "retry_backoff_ms": 250, "timeout_sec": 60.0},
        "aggressive": {"retry_max": 3, "retry_backoff_ms": 500, "timeout_sec": 120.0},
    }
    NODE_EXECUTION_PRESET_KEYS = ["fast", "standard", "heavy", "approval"]
    ACTION_FAST_INTEGRATIONS = {
        "slack_webhook",
        "discord_webhook",
        "teams_webhook",
        "telegram_bot",
        "twilio_sms",
        "openweather_current",
    }
    ACTION_STANDARD_INTEGRATIONS = {
        "http_post",
        "http_request",
        "google_apps_script",
        "google_sheets",
        "google_calendar_api",
        "outlook_graph",
        "notion_api",
        "airtable_api",
        "hubspot_api",
        "stripe_api",
        "github_rest",
        "gitlab_api",
        "google_drive_api",
        "dropbox_api",
        "shopify_api",
        "webflow_api",
        "supabase_api",
        "openrouter_api",
        "linear_api",
        "jira_api",
        "asana_api",
        "clickup_api",
        "trello_api",
        "monday_api",
        "zendesk_api",
        "pipedrive_api",
        "salesforce_api",
        "gmail_send",
        "resend_email",
        "mailgun_email",
    }
    ACTION_HEAVY_INTEGRATIONS = {
        "shell_command",
        "file_append",
        "postgres_sql",
        "mysql_sql",
        "sqlite_sql",
        "redis_command",
        "s3_cli",
    }
    REQUIRED_FIELD_ALIASES = {
        "url": ["webhook_url", "script_url", "connection_url"],
        "webhook_url": ["url"],
        "script_url": ["url"],
        "connection_url": ["url"],
        "sql": ["payload", "query", "command"],
        "query": ["sql", "payload"],
        "command": ["payload", "query"],
        "api_key": ["auth_token"],
        "auth_token": ["api_key"],
        "payload": ["message", "text", "content", "approval_message"],
        "message": ["payload", "text", "content", "approval_message"],
        "text": ["message", "payload", "content"],
        "content": ["message", "payload", "text"],
    }

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("page-root")
        self.add_css_class("canvas-root")
        self.set_focusable(True)

        self.set_margin_top(0)
        self.set_margin_bottom(0)
        self.set_margin_start(0)
        self.set_margin_end(0)

        self.layout_service = CanvasLayoutService()
        self.workflow_store = WorkflowStore()
        self.integration_registry = IntegrationRegistryService()
        self.settings_store = SettingsStore()
        self.execution_engine = ExecutionEngine(
            integration_registry=self.integration_registry,
            settings_store=self.settings_store,
        )
        self.validation_service = WorkflowValidationService()
        self.template_marketplace = TemplateMarketplaceService()
        self.run_store = RunStore()
        self.run_execution_service = get_run_execution_service()
        self.templates: list[dict] = []
        self.template_dropdown: Gtk.DropDown | None = None
        self.latest_workflow_run_id: str = ""
        self.latest_workflow_run_status: str = ""
        self.latest_workflow_run_failed_node_id: str = ""
        self.latest_workflow_run_pending_approval_node_id: str = ""

        self.workflows: list[Workflow] = []
        self.workflow_dropdown: Gtk.DropDown | None = None
        self.active_workflow_id: str | None = None

        self.nodes: list[CanvasNode] = []
        self.edges: list[CanvasEdge] = []
        self.node_widgets: dict[str, Gtk.Widget] = {}
        self.selected_node_id: str | None = None
        self.selected_node_ids: set[str] = set()
        self.pending_link_source_id: str | None = None
        self.drag_origin: dict[str, int | str] = {}
        self.drag_group_origins: dict[str, tuple[int, int]] = {}
        self.link_preview_source_id: str | None = None
        self.link_preview_end_x: int = 0
        self.link_preview_end_y: int = 0
        self.port_drag_active = False
        self.port_drag_origin: dict[str, float] = {}
        self.port_drag_just_finished = False
        self.hovered_port_node_id: str | None = None
        self.hovered_port_kind: str | None = None
        self.link_hover_target_id: str | None = None
        self.syncing_trigger_mode_quick = False
        self.syncing_action_category = False
        self.loading_action_controls = False
        self.last_action_group_integration = ""
        self.action_field_rows: dict[str, Gtk.Widget] = {}
        self.action_field_labels: dict[str, Gtk.Label] = {}
        self.action_field_widgets: dict[str, list[Gtk.Widget]] = {}
        self.action_field_feedback_labels: dict[str, Gtk.Label] = {}
        self.node_field_rows: dict[str, Gtk.Widget] = {}
        self.node_field_labels: dict[str, Gtk.Label] = {}
        self.node_field_widgets: dict[str, list[Gtk.Widget]] = {}
        self.node_field_feedback_labels: dict[str, Gtk.Label] = {}
        self.preflight_error_node_ids: set[str] = set()
        self.preflight_warning_node_ids: set[str] = set()
        self.preflight_error_edge_ids: set[str] = set()
        self.preflight_warning_edge_ids: set[str] = set()
        self.preflight_error_edge_pairs: set[str] = set()
        self.preflight_warning_edge_pairs: set[str] = set()
        self.preflight_issue_items: list[dict[str, str]] = []
        self.loading_graph_settings = False
        self.execution_preset_buttons: dict[str, Gtk.ToggleButton] = {}
        self.node_execution_preset_buttons: dict[str, Gtk.ToggleButton] = {}
        self.loading_node_execution_preset = False
        self.node_drag_active = False
        self.suppress_next_node_click = False
        self.zoom_factor = 1.0
        self.pan_drag_active = False
        self.pan_drag_origin: dict[str, float] = {}
        self.drag_guide_x: float | None = None
        self.drag_guide_y: float | None = None
        self.selection_rect_active = False
        self.selection_rect_start_x = 0.0
        self.selection_rect_start_y = 0.0
        self.selection_rect_end_x = 0.0
        self.selection_rect_end_y = 0.0
        self.selection_additive = False
        self.selection_base_ids: set[str] = set()
        self.suppress_stage_click_once = False
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self.max_history_entries = 80
        self.history_restoring = False
        self.drag_history_captured = False
        self.minimap_position_initialized = False
        self.minimap_user_placed = False
        self.minimap_x = 0
        self.minimap_y = 0
        self.minimap_drag_active = False
        self.minimap_drag_moved = False
        self.minimap_drag_origin: dict[str, int] = {}
        minimap_settings = self.settings_store.load_settings()
        self.minimap_user_placed = bool(
            minimap_settings.get("canvas_minimap_user_placed", False)
        )
        self.minimap_x = self.parse_int(minimap_settings.get("canvas_minimap_x", 0), 0)
        self.minimap_y = self.parse_int(minimap_settings.get("canvas_minimap_y", 0), 0)
        if self.minimap_user_placed:
            self.minimap_x = max(10, self.minimap_x)
            self.minimap_y = max(10, self.minimap_y)
            self.minimap_position_initialized = True

        workflow_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        workflow_row.add_css_class("canvas-toolbar-row")
        workflow_row.add_css_class("compact-toolbar-row")
        workflow_row.set_halign(Gtk.Align.FILL)

        self.workflow_dropdown_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10
        )
        self.workflow_dropdown_container.set_hexpand(True)

        refresh_workflows_button = Gtk.Button(label="Refresh")
        refresh_workflows_button.connect("clicked", self.on_refresh_workflows)
        refresh_workflows_button.add_css_class("compact-action-button")

        workflow_row.append(self.workflow_dropdown_container)
        workflow_row.append(refresh_workflows_button)

        build_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        build_row.add_css_class("canvas-toolbar-row")
        build_row.add_css_class("compact-toolbar-row")
        build_row.set_halign(Gtk.Align.FILL)

        self.add_trigger_button = Gtk.Button(label="Trigger")
        self.add_trigger_button.connect("clicked", self.on_add_trigger)
        self.add_trigger_button.add_css_class("compact-action-button")

        self.add_action_button = Gtk.Button(label="Action")
        self.add_action_button.connect("clicked", self.on_add_action)
        self.add_action_button.add_css_class("compact-action-button")

        self.add_ai_button = Gtk.Button(label="AI")
        self.add_ai_button.connect("clicked", self.on_add_ai)
        self.add_ai_button.add_css_class("suggested-action")
        self.add_ai_button.add_css_class("compact-action-button")

        self.add_condition_button = Gtk.Button(label="Condition")
        self.add_condition_button.connect("clicked", self.on_add_condition)
        self.add_condition_button.add_css_class("compact-action-button")

        self.link_type_dropdown = Gtk.DropDown.new_from_strings(self.LINK_TYPES)
        self.link_type_dropdown.set_selected(0)

        self.start_link_button = Gtk.Button(label="Link From")
        self.start_link_button.connect("clicked", self.on_start_link)
        self.start_link_button.add_css_class("compact-action-button")

        self.auto_wire_button = Gtk.Button(label="Auto Wire")
        self.auto_wire_button.connect("clicked", self.on_auto_wire)
        self.auto_wire_button.add_css_class("compact-action-button")

        self.delete_selected_button = Gtk.Button(label="Delete")
        self.delete_selected_button.connect("clicked", self.on_delete_selected)
        self.delete_selected_button.add_css_class("compact-action-button")

        self.save_graph_button = Gtk.Button(label="Save")
        self.save_graph_button.connect("clicked", self.on_save_graph)
        self.save_graph_button.add_css_class("suggested-action")
        self.save_graph_button.add_css_class("compact-action-button")

        self.preflight_button = Gtk.Button(label="Preflight")
        self.preflight_button.connect("clicked", self.on_run_preflight_check)
        self.preflight_button.add_css_class("compact-action-button")

        self.clear_button = Gtk.Button(label="Clear")
        self.clear_button.connect("clicked", self.on_clear_canvas)
        self.clear_button.add_css_class("compact-action-button")

        build_row.append(self.add_trigger_button)
        build_row.append(self.add_action_button)
        build_row.append(self.add_ai_button)
        build_row.append(self.add_condition_button)

        link_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        link_row.add_css_class("canvas-toolbar-row")
        link_row.add_css_class("compact-toolbar-row")
        link_row.set_halign(Gtk.Align.FILL)
        link_row.append(self.link_type_dropdown)
        link_row.append(self.start_link_button)
        link_row.append(self.auto_wire_button)
        link_row.append(self.delete_selected_button)

        run_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        run_row.add_css_class("canvas-toolbar-row")
        run_row.add_css_class("compact-toolbar-row")
        run_row.set_halign(Gtk.Align.FILL)

        self.run_workflow_button = Gtk.Button(label="Run")
        self.run_workflow_button.connect("clicked", self.on_run_active_workflow)
        self.run_workflow_button.add_css_class("suggested-action")
        self.run_workflow_button.add_css_class("compact-action-button")

        self.cancel_run_button = Gtk.Button(label="Cancel")
        self.cancel_run_button.connect("clicked", self.on_cancel_latest_workflow_run)
        self.cancel_run_button.add_css_class("compact-action-button")

        self.retry_failed_button = Gtk.Button(label="Retry Failed")
        self.retry_failed_button.connect("clicked", self.on_retry_latest_failed_node)
        self.retry_failed_button.add_css_class("compact-action-button")

        self.resume_run_button = Gtk.Button(label="Approve")
        self.resume_run_button.connect("clicked", self.on_resume_latest_approval)
        self.resume_run_button.add_css_class("compact-action-button")

        self.refresh_run_state_button = Gtk.Button(label="Refresh Run")
        self.refresh_run_state_button.connect("clicked", self.on_refresh_workflow_run_state_clicked)
        self.refresh_run_state_button.add_css_class("compact-action-button")

        run_row.append(self.run_workflow_button)
        run_row.append(self.cancel_run_button)
        run_row.append(self.retry_failed_button)
        run_row.append(self.resume_run_button)
        run_row.append(self.refresh_run_state_button)
        run_row.append(self.preflight_button)
        run_row.append(self.save_graph_button)
        run_row.append(self.clear_button)

        self.workflow_run_state_label = Gtk.Label(label="No workflow selected.")
        self.workflow_run_state_label.set_wrap(True)
        self.workflow_run_state_label.set_halign(Gtk.Align.START)
        self.workflow_run_state_label.add_css_class("dim-label")
        self.workflow_run_state_label.add_css_class("canvas-status")

        view_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        view_row.add_css_class("canvas-toolbar-row")
        view_row.add_css_class("compact-toolbar-row")
        view_row.set_halign(Gtk.Align.FILL)

        self.zoom_out_button = Gtk.Button(label="-")
        self.zoom_out_button.connect("clicked", self.on_zoom_out_clicked)
        self.zoom_out_button.add_css_class("compact-action-button")

        self.zoom_reset_button = Gtk.Button(label="100%")
        self.zoom_reset_button.connect("clicked", self.on_zoom_reset_clicked)
        self.zoom_reset_button.add_css_class("compact-action-button")

        self.zoom_in_button = Gtk.Button(label="+")
        self.zoom_in_button.connect("clicked", self.on_zoom_in_clicked)
        self.zoom_in_button.add_css_class("compact-action-button")

        self.zoom_fit_button = Gtk.Button(label="Fit")
        self.zoom_fit_button.connect("clicked", self.on_zoom_fit_clicked)
        self.zoom_fit_button.add_css_class("compact-action-button")

        self.minimap_reset_button = Gtk.Button(label="Mini")
        self.minimap_reset_button.connect("clicked", self.on_minimap_reset_clicked)
        self.minimap_reset_button.add_css_class("compact-action-button")

        view_row.append(self.zoom_out_button)
        view_row.append(self.zoom_reset_button)
        view_row.append(self.zoom_in_button)
        view_row.append(self.zoom_fit_button)
        view_row.append(self.minimap_reset_button)

        arrange_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        arrange_row.add_css_class("canvas-toolbar-row")
        arrange_row.add_css_class("compact-toolbar-row")
        arrange_row.set_halign(Gtk.Align.FILL)

        self.undo_button = Gtk.Button(label="Undo")
        self.undo_button.add_css_class("compact-action-button")
        self.undo_button.connect("clicked", self.on_undo_clicked)

        self.redo_button = Gtk.Button(label="Redo")
        self.redo_button.add_css_class("compact-action-button")
        self.redo_button.connect("clicked", self.on_redo_clicked)

        self.align_left_button = Gtk.Button(label="Align Left")
        self.align_left_button.add_css_class("compact-action-button")
        self.align_left_button.connect("clicked", self.on_align_left_clicked)

        self.align_row_button = Gtk.Button(label="Align Row")
        self.align_row_button.add_css_class("compact-action-button")
        self.align_row_button.connect("clicked", self.on_align_row_clicked)

        self.distribute_x_button = Gtk.Button(label="Distribute X")
        self.distribute_x_button.add_css_class("compact-action-button")
        self.distribute_x_button.connect("clicked", self.on_distribute_x_clicked)

        self.snap_grid_button = Gtk.Button(label="Snap Grid")
        self.snap_grid_button.add_css_class("compact-action-button")
        self.snap_grid_button.connect("clicked", self.on_snap_grid_clicked)

        arrange_row.append(self.undo_button)
        arrange_row.append(self.redo_button)
        arrange_row.append(self.align_left_button)
        arrange_row.append(self.align_row_button)
        arrange_row.append(self.distribute_x_button)
        arrange_row.append(self.snap_grid_button)

        template_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        template_row.add_css_class("canvas-toolbar-row")
        template_row.add_css_class("compact-toolbar-row")
        template_row.set_halign(Gtk.Align.FILL)

        self.template_dropdown_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8
        )
        self.template_dropdown_container.set_hexpand(True)

        self.add_template_button = Gtk.Button(label="Add Template")
        self.add_template_button.connect("clicked", self.on_add_template_node)
        self.add_template_button.add_css_class("compact-action-button")

        self.refresh_templates_button = Gtk.Button(label="Refresh")
        self.refresh_templates_button.connect("clicked", self.on_refresh_templates)
        self.refresh_templates_button.add_css_class("compact-action-button")

        template_row.append(self.template_dropdown_container)
        template_row.append(self.add_template_button)
        template_row.append(self.refresh_templates_button)

        execution_row = Gtk.Grid()
        execution_row.add_css_class("canvas-toolbar-row")
        execution_row.add_css_class("compact-toolbar-row")
        execution_row.add_css_class("canvas-execution-grid")
        execution_row.set_column_spacing(8)
        execution_row.set_row_spacing(6)
        execution_row.set_column_homogeneous(False)
        execution_row.set_halign(Gtk.Align.FILL)

        retry_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        retry_box.add_css_class("canvas-execution-field")
        retry_label = Gtk.Label(label="Retries")
        retry_label.add_css_class("dim-label")
        retry_label.set_halign(Gtk.Align.START)
        self.graph_retry_spin = Gtk.SpinButton.new_with_range(0, 8, 1)
        self.graph_retry_spin.set_digits(0)
        self.graph_retry_spin.set_width_chars(3)
        self.graph_retry_spin.add_css_class("inspector-adjust-spin")
        self.graph_retry_spin.add_css_class("canvas-execution-spin")
        self.graph_retry_spin.connect("value-changed", self.on_graph_execution_setting_changed)
        retry_box.append(retry_label)
        retry_box.append(self.graph_retry_spin)

        backoff_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        backoff_box.add_css_class("canvas-execution-field")
        backoff_label = Gtk.Label(label="Backoff ms")
        backoff_label.add_css_class("dim-label")
        backoff_label.set_halign(Gtk.Align.START)
        self.graph_backoff_spin = Gtk.SpinButton.new_with_range(0, 10000, 50)
        self.graph_backoff_spin.set_digits(0)
        self.graph_backoff_spin.set_width_chars(6)
        self.graph_backoff_spin.add_css_class("inspector-adjust-spin")
        self.graph_backoff_spin.add_css_class("canvas-execution-spin")
        self.graph_backoff_spin.connect("value-changed", self.on_graph_execution_setting_changed)
        backoff_box.append(backoff_label)
        backoff_box.append(self.graph_backoff_spin)

        timeout_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        timeout_box.add_css_class("canvas-execution-field")
        timeout_box.set_hexpand(True)
        timeout_label = Gtk.Label(label="Timeout s")
        timeout_label.add_css_class("dim-label")
        timeout_label.set_halign(Gtk.Align.START)
        self.graph_timeout_spin = Gtk.SpinButton.new_with_range(0.0, 600.0, 0.5)
        self.graph_timeout_spin.set_digits(1)
        self.graph_timeout_spin.set_width_chars(5)
        self.graph_timeout_spin.add_css_class("inspector-adjust-spin")
        self.graph_timeout_spin.add_css_class("canvas-execution-spin")
        self.graph_timeout_spin.connect("value-changed", self.on_graph_execution_setting_changed)
        timeout_box.append(timeout_label)
        timeout_box.append(self.graph_timeout_spin)

        execution_row.attach(retry_box, 0, 0, 1, 1)
        execution_row.attach(backoff_box, 1, 0, 1, 1)
        execution_row.attach(timeout_box, 0, 1, 2, 1)

        execution_preset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        execution_preset_row.add_css_class("segmented-row")
        execution_preset_row.add_css_class("compact-segmented-row")
        execution_preset_row.add_css_class("canvas-execution-preset-row")

        for key, label in [
            ("safe", "Safe"),
            ("balanced", "Balanced"),
            ("aggressive", "Aggressive"),
        ]:
            button = Gtk.ToggleButton(label=label)
            button.add_css_class("segmented-button")
            button.add_css_class("compact-segmented-button")
            button.connect("toggled", self.on_execution_preset_toggled, key)
            execution_preset_row.append(button)
            self.execution_preset_buttons[key] = button

        self.preflight_issue_summary = Gtk.Label(
            label="Run preflight to detect node and link issues before execution."
        )
        self.preflight_issue_summary.set_wrap(True)
        self.preflight_issue_summary.set_halign(Gtk.Align.START)
        self.preflight_issue_summary.add_css_class("dim-label")

        self.preflight_issue_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.preflight_issue_list.add_css_class("preflight-issue-list")

        self.preflight_issue_scroll = Gtk.ScrolledWindow()
        self.preflight_issue_scroll.set_hexpand(True)
        self.preflight_issue_scroll.set_vexpand(False)
        self.preflight_issue_scroll.set_min_content_height(92)
        self.preflight_issue_scroll.set_max_content_height(132)
        self.preflight_issue_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.preflight_issue_scroll.set_child(self.preflight_issue_list)

        self.status_label = Gtk.Label(label="")
        self.status_label.set_wrap(True)
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.add_css_class("dim-label")
        self.status_label.add_css_class("canvas-status")

        main_split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        main_split.add_css_class("canvas-split")
        main_split.set_hexpand(True)
        main_split.set_vexpand(True)
        main_split.set_wide_handle(True)
        main_split.set_position(1036)

        canvas_frame = Gtk.Frame()
        canvas_frame.add_css_class("panel-card")
        canvas_frame.add_css_class("canvas-stage-frame")
        canvas_frame.set_hexpand(True)
        canvas_frame.set_vexpand(True)

        canvas_scroll = Gtk.ScrolledWindow()
        canvas_scroll.set_hexpand(True)
        canvas_scroll.set_vexpand(True)
        canvas_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        canvas_scroll.add_css_class("canvas-scroll")
        self.canvas_scroll = canvas_scroll

        self.fixed = Gtk.Fixed()
        self.fixed.set_size_request(self.STAGE_WIDTH, self.STAGE_HEIGHT)
        self.fixed.add_css_class("canvas-stage")

        self.link_layer = Gtk.DrawingArea()
        self.link_layer.set_content_width(self.STAGE_WIDTH)
        self.link_layer.set_content_height(self.STAGE_HEIGHT)
        self.link_layer.set_draw_func(self.on_draw_links)
        self.link_layer.add_css_class("canvas-link-layer")
        # Keep link layer strictly visual so pointer gestures always reach node widgets.
        self.link_layer.set_can_target(False)

        stage_overlay = Gtk.Overlay()
        stage_overlay.set_child(self.link_layer)
        stage_overlay.add_overlay(self.fixed)

        self.canvas_overlay = Gtk.Overlay()
        self.canvas_overlay.add_css_class("canvas-viewport-overlay")

        self.minimap_area = Gtk.DrawingArea()
        self.minimap_area.set_content_width(196)
        self.minimap_area.set_content_height(128)
        self.minimap_area.add_css_class("canvas-minimap")
        self.minimap_area.set_halign(Gtk.Align.START)
        self.minimap_area.set_valign(Gtk.Align.START)
        self.minimap_area.set_margin_top(10)
        self.minimap_area.set_margin_start(10)
        self.minimap_area.set_draw_func(self.on_draw_minimap)
        self.canvas_overlay.add_overlay(self.minimap_area)

        stage_click = Gtk.GestureClick()
        stage_click.set_button(Gdk.BUTTON_PRIMARY)
        stage_click.connect("released", self.on_canvas_stage_clicked)
        self.fixed.add_controller(stage_click)

        stage_motion = Gtk.EventControllerMotion()
        stage_motion.connect("motion", self.on_stage_pointer_motion)
        self.fixed.add_controller(stage_motion)

        stage_select_drag = Gtk.GestureDrag()
        stage_select_drag.set_button(Gdk.BUTTON_PRIMARY)
        stage_select_drag.connect("drag-begin", self.on_stage_select_drag_begin)
        stage_select_drag.connect("drag-update", self.on_stage_select_drag_update)
        stage_select_drag.connect("drag-end", self.on_stage_select_drag_end)
        self.fixed.add_controller(stage_select_drag)

        minimap_click = Gtk.GestureClick()
        minimap_click.set_button(1)
        minimap_click.connect("released", self.on_minimap_released)
        self.minimap_area.add_controller(minimap_click)

        minimap_drag = Gtk.GestureDrag()
        minimap_drag.set_button(0)
        minimap_drag.connect("drag-begin", self.on_minimap_drag_begin)
        minimap_drag.connect("drag-update", self.on_minimap_drag_update)
        minimap_drag.connect("drag-end", self.on_minimap_drag_end)
        self.minimap_area.add_controller(minimap_drag)

        pan_drag = Gtk.GestureDrag()
        pan_drag.set_button(2)
        pan_drag.connect("drag-begin", self.on_canvas_pan_begin)
        pan_drag.connect("drag-update", self.on_canvas_pan_update)
        pan_drag.connect("drag-end", self.on_canvas_pan_end)
        self.fixed.add_controller(pan_drag)

        canvas_scroll.set_child(stage_overlay)
        self.canvas_overlay.set_child(canvas_scroll)
        canvas_frame.set_child(self.canvas_overlay)
        hadj = self.canvas_scroll.get_hadjustment()
        vadj = self.canvas_scroll.get_vadjustment()
        if hadj:
            hadj.connect("value-changed", self.on_canvas_viewport_changed)
            hadj.connect("changed", self.on_canvas_viewport_changed)
        if vadj:
            vadj.connect("value-changed", self.on_canvas_viewport_changed)
            vadj.connect("changed", self.on_canvas_viewport_changed)
        GLib.idle_add(self.ensure_minimap_position)

        inspector_frame = Gtk.Frame()
        inspector_frame.add_css_class("panel-card")
        inspector_frame.add_css_class("canvas-inspector-frame")
        inspector_frame.add_css_class("canvas-inspector-shell")
        inspector_frame.set_size_request(272, -1)
        inspector_frame.set_hexpand(False)
        inspector_frame.set_vexpand(True)

        inspector_shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        inspector_shell.add_css_class("canvas-inspector-shell-box")
        inspector_shell.set_margin_top(6)
        inspector_shell.set_margin_bottom(6)
        inspector_shell.set_margin_start(6)
        inspector_shell.set_margin_end(6)

        control_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        control_box.add_css_class("canvas-control-box")

        inspector_scroll = Gtk.ScrolledWindow()
        inspector_scroll.set_vexpand(True)
        inspector_scroll.set_hexpand(True)
        inspector_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        inspector_scroll.add_css_class("canvas-inspector-scroll")

        workflow_scroll = Gtk.ScrolledWindow()
        workflow_scroll.set_vexpand(True)
        workflow_scroll.set_hexpand(True)
        workflow_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        workflow_scroll.add_css_class("canvas-inspector-scroll")

        self.inspector_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.inspector_box.add_css_class("canvas-inspector")

        control_title = build_icon_section(
            "Workflow Builder",
            "applications-graphics-symbolic",
            level="heading",
        )
        control_title.add_css_class("canvas-rail-heading")

        control_subtitle = Gtk.Label(
            label="Create and wire nodes, then select any node to configure it."
        )
        control_subtitle.set_wrap(True)
        control_subtitle.set_halign(Gtk.Align.START)
        control_subtitle.add_css_class("dim-label")
        control_subtitle.add_css_class("canvas-control-subtitle")

        shortcut_hint = Gtk.Label(
            label=(
                "Shortcuts: Ctrl+S save  •  Ctrl+L link  •  Ctrl+P preflight  •  "
                "Ctrl+Z undo/redo  •  Ctrl+Shift+G snap  •  Ctrl +/- zoom  •  "
                "Shift-drag box select  •  Ctrl-drag snap  •  Del remove  •  Drag mini map to move"
            )
        )
        shortcut_hint.set_wrap(True)
        shortcut_hint.set_halign(Gtk.Align.START)
        shortcut_hint.add_css_class("dim-label")
        shortcut_hint.add_css_class("canvas-control-subtitle")

        setup_title = build_icon_section("Workflow", "view-grid-symbolic", level="heading")

        build_title = build_icon_section("Add Nodes", "list-add-symbolic", level="heading")

        link_title = build_icon_section("Link", "insert-link-symbolic", level="heading")

        run_title = build_icon_section("Graph", "media-playback-start-symbolic", level="heading")
        view_title = build_icon_section("View", "zoom-fit-best-symbolic", level="heading")
        execution_title = build_icon_section(
            "Execution Defaults",
            "preferences-system-symbolic",
            level="heading",
        )
        execution_preset_title = build_icon_section(
            "Execution Preset",
            "applications-system-symbolic",
            level="heading",
        )
        preflight_issues_title = build_icon_section(
            "Preflight Issues",
            "dialog-warning-symbolic",
            level="heading",
        )

        templates_title = build_icon_section("Templates", "folder-download-symbolic", level="heading")

        inspector_title = build_icon_section(
            "Selected Node",
            "sidebar-show-right-symbolic",
        )

        self.node_name_label = Gtk.Label(label="No node selected")
        self.node_name_label.add_css_class("heading")
        self.node_name_label.add_css_class("canvas-inspector-title")
        self.node_name_label.set_halign(Gtk.Align.START)

        self.node_type_label = Gtk.Label(label="Type: —")
        self.node_type_label.set_halign(Gtk.Align.START)
        self.node_type_label.add_css_class("dim-label")

        self.node_position_label = Gtk.Label(label="Position: —")
        self.node_position_label.set_halign(Gtk.Align.START)
        self.node_position_label.add_css_class("dim-label")

        self.node_link_label = Gtk.Label(label="Links: —")
        self.node_link_label.set_halign(Gtk.Align.START)
        self.node_link_label.add_css_class("dim-label")

        preview_title = build_icon_section(
            "Node Preview",
            "document-preview-symbolic",
        )

        self.node_summary_label = Gtk.Label(label="Select a node to inspect details.")
        self.node_summary_label.set_wrap(True)
        self.node_summary_label.set_halign(Gtk.Align.START)
        self.node_summary_label.add_css_class("canvas-summary-label")

        self.node_detail_label = Gtk.Label(label="")
        self.node_detail_label.set_wrap(True)
        self.node_detail_label.set_halign(Gtk.Align.START)
        self.node_detail_label.add_css_class("dim-label")

        self.edit_title = build_icon_section(
            "Edit Node",
            "document-edit-symbolic",
        )

        self.edit_name_entry = Gtk.Entry()
        self.edit_name_entry.set_placeholder_text("Node name")

        self.edit_summary_entry = Gtk.Entry()
        self.edit_summary_entry.set_placeholder_text("Summary shown in inspector")

        self.edit_detail_buffer = Gtk.TextBuffer()
        self.edit_detail_view = Gtk.TextView(buffer=self.edit_detail_buffer)
        self.edit_detail_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.edit_detail_view.set_size_request(-1, 92)

        self.detail_frame = Gtk.Frame()
        self.detail_frame.add_css_class("canvas-edit-detail-frame")
        self.detail_frame.set_child(self.edit_detail_view)

        self.detail_hint = Gtk.Label(
            label=(
                "Detail directives:\n"
                "trigger_mode:, trigger_value:, action_template:, prompt:, integration:, url:, webhook_url:, api_key:, location:, script_url:, payload:, path:, command:, to:, from:, subject:, chat_id:, account_sid:, auth_token:, domain:, bot_chain:, expression:"
            )
        )
        self.detail_hint.set_wrap(True)
        self.detail_hint.set_halign(Gtk.Align.START)
        self.detail_hint.add_css_class("dim-label")

        detail_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        detail_box.append(self.detail_frame)
        detail_box.append(self.detail_hint)
        self.detail_expander = Gtk.Expander(label="Advanced Directives")
        self.detail_expander.add_css_class("canvas-detail-expander")
        self.detail_expander.set_expanded(False)
        self.detail_expander.set_child(detail_box)

        trigger_section_title = build_icon_section(
            "Trigger Configuration",
            "media-playback-start-symbolic",
        )
        self.trigger_mode_dropdown = Gtk.DropDown.new_from_strings(self.TRIGGER_MODE_OPTIONS)
        self.trigger_mode_dropdown.set_selected(0)
        self.trigger_mode_dropdown.connect("notify::selected", self.on_trigger_mode_changed)
        self.trigger_mode_row, self.trigger_mode_label = self.build_inspector_field_row(
            "Trigger Mode",
            self.trigger_mode_dropdown,
        )
        self.register_node_field(
            "trigger_mode",
            self.trigger_mode_row,
            self.trigger_mode_dropdown,
            label=self.trigger_mode_label,
        )

        self.trigger_mode_quick_buttons: dict[str, Gtk.ToggleButton] = {}
        trigger_mode_quick_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        trigger_mode_quick_row.add_css_class("segmented-row")
        trigger_mode_quick_row.add_css_class("compact-segmented-row")
        for mode_key, mode_label in [
            ("manual", "Manual"),
            ("schedule_interval", "Interval"),
            ("cron", "Cron"),
            ("webhook", "Webhook"),
            ("file_watch", "Watch"),
        ]:
            button = Gtk.ToggleButton(label=mode_label)
            button.add_css_class("segmented-button")
            button.add_css_class("compact-segmented-button")
            button.connect("toggled", self.on_trigger_mode_quick_toggled, mode_key)
            trigger_mode_quick_row.append(button)
            self.trigger_mode_quick_buttons[mode_key] = button
        self.trigger_mode_quick_scroll = wrap_horizontal_row(trigger_mode_quick_row)
        self.trigger_mode_quick_field_row, _ = self.build_inspector_field_row(
            "Quick Trigger",
            self.trigger_mode_quick_scroll,
        )

        self.trigger_preset_row = Gtk.FlowBox()
        self.trigger_preset_row.set_max_children_per_line(3)
        self.trigger_preset_row.set_selection_mode(Gtk.SelectionMode.NONE)
        self.trigger_preset_row.add_css_class("canvas-action-quick-row")
        self.trigger_preset_specs: list[tuple[str, str, str]] = [
            ("Run Now", "manual", ""),
            ("Every 30s", "schedule_interval", "30"),
            ("Every 5m", "schedule_interval", "300"),
            ("Every 10m", "schedule_interval", "600"),
            ("Every 1h", "schedule_interval", "3600"),
            ("Daily 9AM", "cron", "0 9 * * *"),
            ("Weekdays 8AM", "cron", "0 8 * * 1-5"),
            ("Webhook", "webhook", "/incoming"),
            ("File Watch", "file_watch", "/tmp/watch-folder"),
            ("Watch /var/log", "file_watch", "/var/log"),
            ("Cron 15m", "cron", "*/15 * * * *"),
        ]
        for label, mode_key, value in self.trigger_preset_specs:
            button = Gtk.Button(label=label)
            button.add_css_class("compact-action-button")
            button.add_css_class("canvas-action-quick-button")
            button.connect("clicked", self.on_trigger_preset_clicked, mode_key, value)
            self.trigger_preset_row.insert(button, -1)
        self.trigger_preset_field_row, _ = self.build_inspector_field_row(
            "Starter Presets",
            self.trigger_preset_row,
        )

        self.trigger_interval_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            5,
            86400,
            5,
        )
        self.trigger_interval_scale.add_css_class("inspector-adjust-scale")
        self.trigger_interval_scale.set_draw_value(False)
        self.trigger_interval_scale.set_hexpand(True)
        self.trigger_interval_spin = Gtk.SpinButton.new_with_range(5, 86400, 5)
        self.trigger_interval_spin.add_css_class("inspector-adjust-spin")
        self.trigger_interval_spin.set_digits(0)
        self.trigger_interval_spin.set_numeric(True)
        self.trigger_interval_spin.set_width_chars(6)
        self.trigger_interval_scale.connect("value-changed", self.on_trigger_interval_scale_changed)
        self.trigger_interval_spin.connect("value-changed", self.on_trigger_interval_spin_changed)
        self.trigger_interval_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.trigger_interval_row.add_css_class("settings-adjust-row")
        self.trigger_interval_row.add_css_class("inspector-adjust-row")
        self.trigger_interval_row.append(self.trigger_interval_scale)
        self.trigger_interval_row.append(self.trigger_interval_spin)
        self.trigger_interval_field_row, self.trigger_interval_label = self.build_inspector_field_row(
            "Interval Seconds",
            self.trigger_interval_row,
        )
        self.register_node_field(
            "trigger_interval",
            self.trigger_interval_field_row,
            self.trigger_interval_scale,
            self.trigger_interval_spin,
            label=self.trigger_interval_label,
        )

        self.trigger_webhook_entry = Gtk.Entry()
        self.trigger_webhook_entry.set_placeholder_text("/incoming/order")
        self.trigger_webhook_row, self.trigger_webhook_label = self.build_inspector_field_row(
            "Webhook Path",
            self.trigger_webhook_entry,
        )
        self.register_node_field(
            "trigger_webhook",
            self.trigger_webhook_row,
            self.trigger_webhook_entry,
            label=self.trigger_webhook_label,
        )

        self.trigger_watch_path_entry = Gtk.Entry()
        self.trigger_watch_path_entry.set_placeholder_text("/tmp/watch-folder")
        self.trigger_watch_path_row, self.trigger_watch_path_label = self.build_inspector_field_row(
            "Watch Path",
            self.trigger_watch_path_entry,
        )
        self.register_node_field(
            "trigger_watch_path",
            self.trigger_watch_path_row,
            self.trigger_watch_path_entry,
            label=self.trigger_watch_path_label,
        )

        self.trigger_cron_entry = Gtk.Entry()
        self.trigger_cron_entry.set_placeholder_text("*/15 * * * *")
        self.trigger_cron_row, self.trigger_cron_label = self.build_inspector_field_row(
            "Cron Expression",
            self.trigger_cron_entry,
        )
        self.register_node_field(
            "trigger_cron",
            self.trigger_cron_row,
            self.trigger_cron_entry,
            label=self.trigger_cron_label,
        )

        self.trigger_value_entry = Gtk.Entry()
        self.trigger_value_entry.set_placeholder_text("Trigger value")
        self.trigger_value_row, self.trigger_value_label = self.build_inspector_field_row(
            "Trigger Value",
            self.trigger_value_entry,
        )
        self.register_node_field(
            "trigger_value",
            self.trigger_value_row,
            self.trigger_value_entry,
            label=self.trigger_value_label,
        )

        self.trigger_hint_label = Gtk.Label(
            label="Choose trigger mode and value to define how this workflow starts."
        )
        self.trigger_hint_label.set_wrap(True)
        self.trigger_hint_label.set_halign(Gtk.Align.START)
        self.trigger_hint_label.add_css_class("dim-label")

        self.trigger_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.trigger_section.add_css_class("canvas-trigger-panel")
        self.trigger_section.append(trigger_section_title)
        self.trigger_section.append(self.trigger_mode_row)
        self.trigger_section.append(self.trigger_mode_quick_field_row)
        self.trigger_section.append(self.trigger_preset_field_row)
        self.trigger_section.append(self.trigger_interval_field_row)
        self.trigger_section.append(self.trigger_webhook_row)
        self.trigger_section.append(self.trigger_watch_path_row)
        self.trigger_section.append(self.trigger_cron_row)
        self.trigger_section.append(self.trigger_value_row)
        self.trigger_section.append(self.trigger_hint_label)

        action_integration_title = build_icon_section(
            "Action Integration",
            "network-wired-symbolic",
        )
        self.action_template_specs = self.action_template_definitions()
        self.action_template_keys = [str(item.get("key", "")).strip() for item in self.action_template_specs]
        self.action_template_labels = [str(item.get("label", "")).strip() for item in self.action_template_specs]
        self.action_template_dropdown = Gtk.DropDown.new_from_strings(self.action_template_labels)
        self.action_template_dropdown.set_selected(0)
        self.action_template_dropdown.connect(
            "notify::selected",
            self.on_action_template_changed,
        )
        self.action_template_apply_button = Gtk.Button(label="Apply")
        self.action_template_apply_button.add_css_class("compact-action-button")
        self.action_template_apply_button.connect("clicked", self.on_apply_action_template_clicked)
        action_template_row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_template_row_box.append(self.action_template_dropdown)
        action_template_row_box.append(self.action_template_apply_button)
        self.action_template_row, _ = self.build_inspector_field_row(
            "Action Type",
            action_template_row_box,
        )
        self.action_saved_defaults_button = Gtk.Button(label="Load Saved Defaults")
        self.action_saved_defaults_button.add_css_class("compact-action-button")
        self.action_saved_defaults_button.connect(
            "clicked",
            self.on_load_saved_action_defaults_clicked,
        )
        self.action_saved_defaults_row, _ = self.build_inspector_field_row(
            "Connector Defaults",
            self.action_saved_defaults_button,
        )
        self.action_template_hint_label = Gtk.Label(label="")
        self.action_template_hint_label.set_wrap(True)
        self.action_template_hint_label.set_halign(Gtk.Align.START)
        self.action_template_hint_label.add_css_class("dim-label")

        self.action_quick_specs: list[tuple[str, str, str]] = [
            ("Slack", "slack_webhook", "notify_slack"),
            ("Discord", "discord_webhook", "notify_discord"),
            ("Teams", "teams_webhook", "notify_teams"),
            ("HTTP", "http_request", "http_request"),
            ("Calendar", "google_apps_script", "calendar_event"),
            ("GCal API", "google_calendar_api", "google_calendar_event"),
            ("Sheets", "google_sheets", "google_sheets_append"),
            ("Telegram", "telegram_bot", "message_telegram"),
            ("Gmail", "gmail_send", "message_email"),
            ("Outlook", "outlook_graph", "outlook_message"),
            ("Twilio", "twilio_sms", "message_sms"),
            ("Weather", "openweather_current", "weather_lookup"),
            ("Notion", "notion_api", "notion_page"),
            ("Airtable", "airtable_api", "airtable_record"),
            ("GitHub", "github_rest", "github_user"),
            ("HubSpot", "hubspot_api", "hubspot_contacts"),
            ("Stripe", "stripe_api", "stripe_balance"),
            ("Drive", "google_drive_api", "google_drive_files"),
            ("Dropbox", "dropbox_api", "dropbox_files"),
            ("Shopify", "shopify_api", "shopify_products"),
            ("Webflow", "webflow_api", "webflow_sites"),
            ("Supabase", "supabase_api", "supabase_rows"),
            ("OpenRouter", "openrouter_api", "openrouter_chat"),
            ("Jira", "jira_api", "jira_issue_lookup"),
            ("Asana", "asana_api", "asana_task"),
            ("ClickUp", "clickup_api", "clickup_task"),
            ("Trello", "trello_api", "trello_board"),
            ("Monday", "monday_api", "monday_query"),
            ("Zendesk", "zendesk_api", "zendesk_ticket"),
            ("Salesforce", "salesforce_api", "salesforce_query"),
            ("Pipedrive", "pipedrive_api", "pipedrive_deal"),
            ("Linear", "linear_api", "linear_query"),
            ("GitLab", "gitlab_api", "gitlab_rest"),
            ("Shell", "shell_command", "shell_command"),
            ("Approval", "approval_gate", "approval_gate"),
        ]
        self.action_quick_buttons: dict[str, Gtk.Button] = {}
        self.action_quick_row = Gtk.FlowBox()
        self.action_quick_row.set_max_children_per_line(3)
        self.action_quick_row.set_selection_mode(Gtk.SelectionMode.NONE)
        self.action_quick_row.add_css_class("canvas-action-quick-row")
        for label, integration_key, template_key in self.action_quick_specs:
            button = Gtk.Button(label=label)
            button.add_css_class("compact-action-button")
            button.add_css_class("canvas-action-quick-button")
            button.connect(
                "clicked",
                self.on_action_quick_clicked,
                integration_key,
                template_key,
            )
            self.action_quick_buttons[integration_key] = button
            self.action_quick_row.insert(button, -1)

        self.action_category_buttons: dict[str, Gtk.ToggleButton] = {}
        action_category_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        action_category_row.add_css_class("segmented-row")
        action_category_row.add_css_class("compact-segmented-row")
        for key, label in [
            ("notify", "Notify"),
            ("message", "Message"),
            ("data", "Data/API"),
            ("system", "System"),
            ("control", "Control"),
        ]:
            button = Gtk.ToggleButton(label=label)
            button.add_css_class("segmented-button")
            button.add_css_class("compact-segmented-button")
            button.connect("toggled", self.on_action_category_toggled, key)
            action_category_row.append(button)
            self.action_category_buttons[key] = button
        self.action_category_scroll = wrap_horizontal_row(action_category_row)
        self.action_category_row, _ = self.build_inspector_field_row(
            "Action Intent",
            self.action_category_scroll,
        )

        self.action_integration_options = self.load_action_integration_options()
        self.action_integration_keys = [key for key, _label in self.action_integration_options]
        self.action_integration_labels = [label for _key, label in self.action_integration_options]
        self.action_integration_dropdown = Gtk.DropDown.new_from_strings(
            self.action_integration_labels
        )
        self.action_integration_dropdown.connect(
            "notify::selected",
            self.on_action_integration_changed,
        )
        self.action_integration_row, _ = self.build_inspector_field_row(
            "Integration",
            self.action_integration_dropdown,
        )
        self.action_preset_specs: list[dict[str, str]] = []
        self.action_preset_dropdown = Gtk.DropDown.new_from_strings(["No presets"])
        self.action_preset_dropdown.set_hexpand(True)
        self.action_preset_apply_button = Gtk.Button(label="Apply Preset")
        self.action_preset_apply_button.add_css_class("compact-action-button")
        self.action_preset_apply_button.connect("clicked", self.on_apply_action_preset)
        action_preset_row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_preset_row_box.append(self.action_preset_dropdown)
        action_preset_row_box.append(self.action_preset_apply_button)
        self.action_preset_row, _ = self.build_inspector_field_row(
            "Quick Presets",
            action_preset_row_box,
        )

        self.action_endpoint_entry = Gtk.Entry()
        self.action_endpoint_entry.set_placeholder_text("Endpoint URL")
        self.action_endpoint_row, self.action_endpoint_label = self.build_inspector_field_row(
            "Endpoint URL",
            self.action_endpoint_entry,
        )

        self.action_method_dropdown = Gtk.DropDown.new_from_strings(
            ["GET", "POST", "PUT", "PATCH", "DELETE"]
        )
        self.action_method_dropdown.set_selected(1)
        self.action_method_row, self.action_method_label = self.build_inspector_field_row(
            "HTTP Method",
            self.action_method_dropdown,
        )

        self.action_message_entry = Gtk.Entry()
        self.action_message_entry.set_placeholder_text("Message / content")
        self.action_message_row, self.action_message_label = self.build_inspector_field_row(
            "Message",
            self.action_message_entry,
        )

        self.action_to_entry = Gtk.Entry()
        self.action_to_entry.set_placeholder_text("Recipient")
        self.action_to_row, _ = self.build_inspector_field_row(
            "To",
            self.action_to_entry,
        )

        self.action_from_entry = Gtk.Entry()
        self.action_from_entry.set_placeholder_text("Sender")
        self.action_from_row, _ = self.build_inspector_field_row(
            "From",
            self.action_from_entry,
        )

        self.action_subject_entry = Gtk.Entry()
        self.action_subject_entry.set_placeholder_text("Message subject")
        self.action_subject_row, _ = self.build_inspector_field_row(
            "Subject",
            self.action_subject_entry,
        )

        self.action_chat_id_entry = Gtk.Entry()
        self.action_chat_id_entry.set_placeholder_text("Telegram chat id")
        self.action_chat_id_row, _ = self.build_inspector_field_row(
            "Chat ID",
            self.action_chat_id_entry,
        )

        self.action_account_sid_entry = Gtk.Entry()
        self.action_account_sid_entry.set_placeholder_text("Twilio Account SID")
        self.action_account_sid_row, _ = self.build_inspector_field_row(
            "Account SID",
            self.action_account_sid_entry,
        )

        self.action_auth_token_entry = Gtk.Entry()
        self.action_auth_token_entry.set_visibility(False)
        self.action_auth_token_entry.set_placeholder_text("Twilio Auth Token")
        self.action_auth_token_row, _ = self.build_inspector_field_row(
            "Auth Token",
            self.action_auth_token_entry,
        )

        self.action_domain_entry = Gtk.Entry()
        self.action_domain_entry.set_placeholder_text("Mailgun domain  •  mg.yourdomain.com")
        self.action_domain_row, _ = self.build_inspector_field_row(
            "Domain",
            self.action_domain_entry,
        )

        self.action_username_entry = Gtk.Entry()
        self.action_username_entry.set_placeholder_text("Optional display username")
        self.action_username_row, _ = self.build_inspector_field_row(
            "Username",
            self.action_username_entry,
        )

        self.action_payload_buffer = Gtk.TextBuffer()
        self.action_payload_view = Gtk.TextView(buffer=self.action_payload_buffer)
        self.action_payload_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.action_payload_view.set_size_request(-1, 72)
        action_payload_frame = Gtk.Frame()
        action_payload_frame.add_css_class("canvas-edit-detail-frame")
        action_payload_frame.set_child(self.action_payload_view)
        self.action_payload_row, self.action_payload_label = self.build_inspector_field_row(
            "Payload",
            action_payload_frame,
        )

        self.action_headers_entry = Gtk.Entry()
        self.action_headers_entry.set_placeholder_text(
            'Headers JSON  •  {"Authorization":"Bearer ..."}'
        )
        self.action_headers_row, self.action_headers_label = self.build_inspector_field_row(
            "Headers",
            self.action_headers_entry,
        )

        self.action_api_key_entry = Gtk.Entry()
        self.action_api_key_entry.set_visibility(False)
        self.action_api_key_entry.set_placeholder_text("API key")
        self.action_api_key_row, self.action_api_key_label = self.build_inspector_field_row(
            "API Key",
            self.action_api_key_entry,
        )

        self.action_location_entry = Gtk.Entry()
        self.action_location_entry.set_placeholder_text("Location  •  Example: Austin,US")
        self.action_location_row, _ = self.build_inspector_field_row(
            "Location",
            self.action_location_entry,
        )

        self.action_units_dropdown = Gtk.DropDown.new_from_strings(
            ["metric", "imperial", "standard"]
        )
        self.action_units_row, _ = self.build_inspector_field_row(
            "Weather Units",
            self.action_units_dropdown,
        )

        self.action_path_entry = Gtk.Entry()
        self.action_path_entry.set_placeholder_text("/home/user/output.log")
        self.action_path_row, self.action_path_label = self.build_inspector_field_row(
            "File Path",
            self.action_path_entry,
        )

        self.action_command_entry = Gtk.Entry()
        self.action_command_entry.set_placeholder_text("Command to execute")
        self.action_command_row, self.action_command_label = self.build_inspector_field_row(
            "Shell Command",
            self.action_command_entry,
        )

        self.action_timeout_spin = Gtk.SpinButton.new_with_range(0.0, 600.0, 0.5)
        self.action_timeout_spin.set_digits(1)
        self.action_timeout_spin.set_width_chars(5)
        self.action_timeout_row, self.action_timeout_label = self.build_inspector_field_row(
            "Timeout Seconds",
            self.action_timeout_spin,
        )

        self.register_action_field(
            "integration",
            self.action_integration_row,
            self.action_integration_dropdown,
        )
        self.register_action_field(
            "preset",
            self.action_preset_row,
            self.action_preset_dropdown,
        )
        self.register_action_field(
            "endpoint",
            self.action_endpoint_row,
            self.action_endpoint_entry,
            label=self.action_endpoint_label,
        )
        self.register_action_field(
            "method",
            self.action_method_row,
            self.action_method_dropdown,
            label=self.action_method_label,
        )
        self.register_action_field(
            "message",
            self.action_message_row,
            self.action_message_entry,
            label=self.action_message_label,
        )
        self.register_action_field("to", self.action_to_row, self.action_to_entry)
        self.register_action_field("from", self.action_from_row, self.action_from_entry)
        self.register_action_field("subject", self.action_subject_row, self.action_subject_entry)
        self.register_action_field("chat_id", self.action_chat_id_row, self.action_chat_id_entry)
        self.register_action_field(
            "account_sid",
            self.action_account_sid_row,
            self.action_account_sid_entry,
        )
        self.register_action_field(
            "auth_token",
            self.action_auth_token_row,
            self.action_auth_token_entry,
        )
        self.register_action_field("domain", self.action_domain_row, self.action_domain_entry)
        self.register_action_field(
            "username",
            self.action_username_row,
            self.action_username_entry,
        )
        self.register_action_field(
            "payload",
            self.action_payload_row,
            action_payload_frame,
            self.action_payload_view,
            label=self.action_payload_label,
        )
        self.register_action_field(
            "headers",
            self.action_headers_row,
            self.action_headers_entry,
            label=self.action_headers_label,
        )
        self.register_action_field(
            "api_key",
            self.action_api_key_row,
            self.action_api_key_entry,
            label=self.action_api_key_label,
        )
        self.register_action_field("location", self.action_location_row, self.action_location_entry)
        self.register_action_field("units", self.action_units_row, self.action_units_dropdown)
        self.register_action_field("path", self.action_path_row, self.action_path_entry)
        self.register_action_field("command", self.action_command_row, self.action_command_entry)
        self.register_action_field(
            "timeout_sec",
            self.action_timeout_row,
            self.action_timeout_spin,
            label=self.action_timeout_label,
        )

        self.action_requirements_label = Gtk.Label(label="")
        self.action_requirements_label.set_wrap(True)
        self.action_requirements_label.set_halign(Gtk.Align.START)
        self.action_requirements_label.add_css_class("dim-label")
        self.action_requirements_label.add_css_class("inline-status")

        self.action_integration_section = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
        )
        self.action_integration_section.add_css_class("canvas-action-integration-panel")
        self.action_routing_rows = [
            self.action_integration_row,
            self.action_preset_row,
            self.action_endpoint_row,
            self.action_method_row,
            self.action_timeout_row,
        ]
        self.action_delivery_rows = [
            self.action_message_row,
            self.action_to_row,
            self.action_from_row,
            self.action_subject_row,
            self.action_chat_id_row,
        ]
        self.action_payload_rows = [
            self.action_payload_row,
            self.action_location_row,
            self.action_units_row,
            self.action_path_row,
            self.action_command_row,
        ]
        self.action_auth_rows = [
            self.action_api_key_row,
            self.action_headers_row,
            self.action_account_sid_row,
            self.action_auth_token_row,
            self.action_domain_row,
            self.action_username_row,
        ]
        self.action_routing_group = self.build_inspector_group(
            "Routing",
            self.action_routing_rows,
            expanded=True,
        )
        self.action_delivery_group = self.build_inspector_group(
            "Delivery",
            self.action_delivery_rows,
            expanded=True,
        )
        self.action_payload_group = self.build_inspector_group(
            "Payload",
            self.action_payload_rows,
            expanded=False,
        )
        self.action_auth_group = self.build_inspector_group(
            "Auth",
            self.action_auth_rows,
            expanded=False,
        )
        self.action_integration_section.append(action_integration_title)
        self.action_integration_section.append(self.action_template_row)
        self.action_integration_section.append(self.action_saved_defaults_row)
        self.action_integration_section.append(self.action_category_row)
        self.action_integration_section.append(self.action_template_hint_label)
        self.action_integration_section.append(self.action_requirements_label)
        self.action_integration_section.append(self.action_quick_row)
        self.action_integration_section.append(self.action_routing_group)
        self.action_integration_section.append(self.action_delivery_group)
        self.action_integration_section.append(self.action_payload_group)
        self.action_integration_section.append(self.action_auth_group)
        self.action_scaffold_button = Gtk.Button(label="Scaffold Required Fields")
        self.action_scaffold_button.add_css_class("compact-action-button")
        self.action_scaffold_button.connect(
            "clicked",
            self.on_scaffold_action_required_fields_clicked,
        )

        self.test_node_button = Gtk.Button(label="Test This Node")
        self.test_node_button.add_css_class("compact-action-button")
        self.test_node_button.add_css_class("suggested-action")
        self.test_node_button.connect("clicked", self.on_test_selected_node_clicked)

        self.node_test_status_label = Gtk.Label(label="")
        self.node_test_status_label.set_wrap(True)
        self.node_test_status_label.set_halign(Gtk.Align.START)
        self.node_test_status_label.add_css_class("dim-label")
        self.node_test_status_label.add_css_class("inline-status")

        self.node_test_result_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.node_test_result_card.add_css_class("node-test-result-card")

        self.node_test_result_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.node_test_result_header.add_css_class("node-test-result-header")
        self.node_test_result_state_chip = Gtk.Label(label="IDLE")
        self.node_test_result_state_chip.add_css_class("node-test-state-chip")
        self.node_test_result_state_chip.add_css_class("node-test-state-idle")
        self.node_test_result_summary_label = Gtk.Label(label="No node test has been run yet.")
        self.node_test_result_summary_label.set_halign(Gtk.Align.START)
        self.node_test_result_summary_label.set_hexpand(True)
        self.node_test_result_summary_label.set_wrap(True)
        self.node_test_result_summary_label.add_css_class("dim-label")
        self.node_test_result_header.append(self.node_test_result_state_chip)
        self.node_test_result_header.append(self.node_test_result_summary_label)

        self.node_test_result_output_buffer = Gtk.TextBuffer()
        self.node_test_result_output_view = Gtk.TextView.new_with_buffer(
            self.node_test_result_output_buffer
        )
        self.node_test_result_output_view.set_editable(False)
        self.node_test_result_output_view.set_cursor_visible(False)
        self.node_test_result_output_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.node_test_result_output_view.add_css_class("node-test-result-output")
        self.node_test_result_output_scroll = Gtk.ScrolledWindow()
        self.node_test_result_output_scroll.set_policy(
            Gtk.PolicyType.NEVER,
            Gtk.PolicyType.AUTOMATIC,
        )
        self.node_test_result_output_scroll.set_min_content_height(120)
        self.node_test_result_output_scroll.set_child(self.node_test_result_output_view)
        self.node_test_result_output_scroll.add_css_class("node-test-result-scroll")

        self.node_test_result_card.append(self.node_test_result_header)
        self.node_test_result_card.append(self.node_test_result_output_scroll)
        self.node_test_result_card.set_visible(False)

        self.node_test_actions_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.node_test_actions_row.add_css_class("compact-action-row")
        self.node_test_actions_row.append(self.action_scaffold_button)
        self.node_test_actions_row.append(self.test_node_button)

        self.node_test_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.node_test_section.add_css_class("canvas-action-integration-panel")
        self.node_test_section.append(build_icon_section("Node Test Console", "system-run-symbolic"))
        self.node_test_section.append(self.node_test_actions_row)
        self.node_test_section.append(self.node_test_status_label)
        self.node_test_section.append(self.node_test_result_card)

        self.provider_label = Gtk.Label(label="Provider Override")
        self.provider_label.set_halign(Gtk.Align.START)
        self.provider_label.add_css_class("dim-label")

        self.edit_provider_dropdown = Gtk.DropDown.new_from_strings(self.PROVIDER_OPTIONS)
        self.edit_provider_dropdown.set_selected(0)

        self.edit_model_entry = Gtk.Entry()
        self.edit_model_entry.set_placeholder_text("Model override (optional)")

        self.edit_bot_entry = Gtk.Entry()
        self.edit_bot_entry.set_placeholder_text("Bot name (optional)")

        self.edit_bot_chain_entry = Gtk.Entry()
        self.edit_bot_chain_entry.set_placeholder_text("Bot chain  •  Example: Planner > Reviewer")

        self.edit_system_entry = Gtk.Entry()
        self.edit_system_entry.set_placeholder_text("System prompt override (optional)")

        self.temp_title = Gtk.Label(label="Temperature")
        self.temp_title.add_css_class("heading")
        self.temp_title.set_halign(Gtk.Align.START)

        self.edit_temp_override_switch = Gtk.Switch()
        self.edit_temp_override_switch.connect(
            "notify::active",
            self.on_temp_override_toggled,
        )
        self.edit_temp_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            0.0,
            2.0,
            0.01,
        )
        self.edit_temp_scale.add_css_class("inspector-adjust-scale")
        self.edit_temp_scale.set_draw_value(False)
        self.edit_temp_scale.set_hexpand(True)
        self.edit_temp_spin = Gtk.SpinButton.new_with_range(0.0, 2.0, 0.01)
        self.edit_temp_spin.add_css_class("inspector-adjust-spin")
        self.edit_temp_spin.set_digits(2)
        self.edit_temp_spin.set_numeric(True)
        self.edit_temp_spin.set_width_chars(6)
        self.edit_temp_scale.connect("value-changed", self.on_temp_scale_changed)
        self.edit_temp_spin.connect("value-changed", self.on_temp_spin_changed)

        self.temp_adjust_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.temp_adjust_row.add_css_class("settings-adjust-row")
        self.temp_adjust_row.add_css_class("inspector-adjust-row")
        self.temp_adjust_row.append(self.edit_temp_scale)
        self.temp_adjust_row.append(self.edit_temp_spin)

        self.max_tokens_title = Gtk.Label(label="Max Tokens")
        self.max_tokens_title.add_css_class("heading")
        self.max_tokens_title.set_halign(Gtk.Align.START)

        self.edit_tokens_override_switch = Gtk.Switch()
        self.edit_tokens_override_switch.connect(
            "notify::active",
            self.on_tokens_override_toggled,
        )
        self.edit_tokens_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            64,
            64000,
            32,
        )
        self.edit_tokens_scale.add_css_class("inspector-adjust-scale")
        self.edit_tokens_scale.set_draw_value(False)
        self.edit_tokens_scale.set_hexpand(True)
        self.edit_tokens_spin = Gtk.SpinButton.new_with_range(64, 64000, 32)
        self.edit_tokens_spin.add_css_class("inspector-adjust-spin")
        self.edit_tokens_spin.set_digits(0)
        self.edit_tokens_spin.set_numeric(True)
        self.edit_tokens_spin.set_width_chars(7)
        self.edit_tokens_scale.connect("value-changed", self.on_tokens_scale_changed)
        self.edit_tokens_spin.connect("value-changed", self.on_tokens_spin_changed)

        self.max_tokens_adjust_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.max_tokens_adjust_row.add_css_class("settings-adjust-row")
        self.max_tokens_adjust_row.add_css_class("inspector-adjust-row")
        self.max_tokens_adjust_row.append(self.edit_tokens_scale)
        self.max_tokens_adjust_row.append(self.edit_tokens_spin)

        self.condition_title = Gtk.Label(label="Condition Builder")
        self.condition_title.add_css_class("heading")
        self.condition_title.set_halign(Gtk.Align.START)

        self.edit_condition_mode_dropdown = Gtk.DropDown.new_from_strings(self.CONDITION_MODE_OPTIONS)
        self.edit_condition_mode_dropdown.set_selected(0)
        self.edit_condition_mode_dropdown.connect(
            "notify::selected",
            self.on_condition_mode_changed,
        )
        self.condition_mode_row, self.condition_mode_label = self.build_inspector_field_row(
            "Condition Mode",
            self.edit_condition_mode_dropdown,
        )
        self.register_node_field(
            "condition_mode",
            self.condition_mode_row,
            self.edit_condition_mode_dropdown,
            label=self.condition_mode_label,
        )

        self.edit_condition_value_entry = Gtk.Entry()
        self.edit_condition_value_entry.set_placeholder_text("Condition value or pattern")
        self.condition_value_row, self.condition_value_label = self.build_inspector_field_row(
            "Condition Value",
            self.edit_condition_value_entry,
        )
        self.register_node_field(
            "condition_value",
            self.condition_value_row,
            self.edit_condition_value_entry,
            label=self.condition_value_label,
        )

        self.edit_condition_min_len_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            1,
            8000,
            1,
        )
        self.edit_condition_min_len_scale.add_css_class("inspector-adjust-scale")
        self.edit_condition_min_len_scale.set_draw_value(False)
        self.edit_condition_min_len_scale.set_hexpand(True)
        self.edit_condition_min_len_spin = Gtk.SpinButton.new_with_range(1, 8000, 1)
        self.edit_condition_min_len_spin.add_css_class("inspector-adjust-spin")
        self.edit_condition_min_len_spin.set_digits(0)
        self.edit_condition_min_len_spin.set_numeric(True)
        self.edit_condition_min_len_spin.set_width_chars(6)
        self.edit_condition_min_len_scale.connect(
            "value-changed",
            self.on_condition_min_len_scale_changed,
        )
        self.edit_condition_min_len_spin.connect(
            "value-changed",
            self.on_condition_min_len_spin_changed,
        )

        condition_min_len_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        condition_min_len_row.add_css_class("settings-adjust-row")
        condition_min_len_row.add_css_class("inspector-adjust-row")
        condition_min_len_row.append(self.edit_condition_min_len_scale)
        condition_min_len_row.append(self.edit_condition_min_len_spin)
        self.condition_min_len_row = condition_min_len_row
        self.condition_min_len_field_row, self.condition_min_len_label = self.build_inspector_field_row(
            "Minimum Length",
            self.condition_min_len_row,
        )
        self.register_node_field(
            "condition_min_len",
            self.condition_min_len_field_row,
            self.edit_condition_min_len_scale,
            self.edit_condition_min_len_spin,
            label=self.condition_min_len_label,
        )

        self.condition_preview_input_entry = Gtk.Entry()
        self.condition_preview_input_entry.set_placeholder_text(
            "Sample input text used to preview true/false branch routing"
        )
        self.condition_preview_input_row, _ = self.build_inspector_field_row(
            "Preview Input",
            self.condition_preview_input_entry,
        )

        self.condition_preview_label = Gtk.Label(
            label="Condition preview is shown here when a condition node is selected."
        )
        self.condition_preview_label.set_wrap(True)
        self.condition_preview_label.set_halign(Gtk.Align.START)
        self.condition_preview_label.add_css_class("dim-label")
        self.condition_preview_label.add_css_class("inline-status")

        self.node_execution_title = Gtk.Label(label="Node Execution")
        self.node_execution_title.add_css_class("heading")
        self.node_execution_title.set_halign(Gtk.Align.START)

        node_exec_grid = Gtk.Grid()
        node_exec_grid.add_css_class("canvas-toolbar-row")
        node_exec_grid.add_css_class("compact-toolbar-row")
        node_exec_grid.add_css_class("canvas-execution-grid")
        node_exec_grid.set_column_spacing(8)
        node_exec_grid.set_row_spacing(6)
        node_exec_grid.set_column_homogeneous(False)
        node_exec_grid.set_halign(Gtk.Align.FILL)

        node_retry_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        node_retry_box.add_css_class("canvas-execution-field")
        node_retry_label = Gtk.Label(label="Retries")
        node_retry_label.add_css_class("dim-label")
        node_retry_label.set_halign(Gtk.Align.START)
        self.node_retry_spin = Gtk.SpinButton.new_with_range(0, 8, 1)
        self.node_retry_spin.set_digits(0)
        self.node_retry_spin.set_width_chars(3)
        self.node_retry_spin.add_css_class("inspector-adjust-spin")
        self.node_retry_spin.add_css_class("canvas-execution-spin")
        self.node_retry_spin.connect("value-changed", self.on_node_execution_value_changed)
        node_retry_box.append(node_retry_label)
        node_retry_box.append(self.node_retry_spin)

        node_backoff_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        node_backoff_box.add_css_class("canvas-execution-field")
        node_backoff_label = Gtk.Label(label="Backoff ms")
        node_backoff_label.add_css_class("dim-label")
        node_backoff_label.set_halign(Gtk.Align.START)
        self.node_backoff_spin = Gtk.SpinButton.new_with_range(0, 10000, 50)
        self.node_backoff_spin.set_digits(0)
        self.node_backoff_spin.set_width_chars(6)
        self.node_backoff_spin.add_css_class("inspector-adjust-spin")
        self.node_backoff_spin.add_css_class("canvas-execution-spin")
        self.node_backoff_spin.connect("value-changed", self.on_node_execution_value_changed)
        node_backoff_box.append(node_backoff_label)
        node_backoff_box.append(self.node_backoff_spin)

        node_timeout_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        node_timeout_box.add_css_class("canvas-execution-field")
        node_timeout_box.set_hexpand(True)
        node_timeout_label = Gtk.Label(label="Timeout s")
        node_timeout_label.add_css_class("dim-label")
        node_timeout_label.set_halign(Gtk.Align.START)
        self.node_timeout_spin = Gtk.SpinButton.new_with_range(0.0, 600.0, 0.5)
        self.node_timeout_spin.set_digits(1)
        self.node_timeout_spin.set_width_chars(5)
        self.node_timeout_spin.add_css_class("inspector-adjust-spin")
        self.node_timeout_spin.add_css_class("canvas-execution-spin")
        self.node_timeout_spin.connect("value-changed", self.on_node_execution_value_changed)
        node_timeout_box.append(node_timeout_label)
        node_timeout_box.append(self.node_timeout_spin)

        node_exec_grid.attach(node_retry_box, 0, 0, 1, 1)
        node_exec_grid.attach(node_backoff_box, 1, 0, 1, 1)
        node_exec_grid.attach(node_timeout_box, 0, 1, 2, 1)

        self.node_execution_preset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.node_execution_preset_row.add_css_class("segmented-row")
        self.node_execution_preset_row.add_css_class("compact-segmented-row")
        self.node_execution_preset_row.add_css_class("canvas-node-execution-preset-row")
        self.node_execution_preset_row.set_halign(Gtk.Align.FILL)

        preset_labels = {
            "fast": "Fast",
            "standard": "Standard",
            "heavy": "Heavy",
            "approval": "Approval",
        }
        for preset_key in self.NODE_EXECUTION_PRESET_KEYS:
            button = Gtk.ToggleButton(label=preset_labels.get(preset_key, preset_key.title()))
            button.add_css_class("compact-action-button")
            button.connect("toggled", self.on_node_execution_preset_toggled, preset_key)
            self.node_execution_preset_row.append(button)
            self.node_execution_preset_buttons[preset_key] = button

        node_exec_action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        node_exec_action_row.add_css_class("compact-action-row")
        self.node_execution_defaults_button = Gtk.Button(label="Use Recommended Defaults")
        self.node_execution_defaults_button.add_css_class("compact-action-button")
        self.node_execution_defaults_button.connect(
            "clicked",
            self.on_node_execution_defaults_clicked,
        )
        node_exec_action_row.append(self.node_execution_defaults_button)

        self.node_execution_hint_label = Gtk.Label(label="")
        self.node_execution_hint_label.set_wrap(True)
        self.node_execution_hint_label.set_halign(Gtk.Align.START)
        self.node_execution_hint_label.add_css_class("dim-label")
        self.node_execution_hint_label.add_css_class("inline-status")

        self.apply_node_button = Gtk.Button(label="Apply Node Changes")
        self.apply_node_button.connect("clicked", self.on_apply_node_changes)
        self.apply_node_button.add_css_class("suggested-action")
        self.apply_node_button.add_css_class("compact-action-button")

        control_box.append(control_title)
        control_box.append(control_subtitle)
        control_box.append(shortcut_hint)
        control_box.append(setup_title)
        control_box.append(wrap_horizontal_row(workflow_row))
        control_box.append(build_title)
        control_box.append(wrap_horizontal_row(build_row))
        control_box.append(link_title)
        control_box.append(wrap_horizontal_row(link_row))
        control_box.append(run_title)
        control_box.append(wrap_horizontal_row(run_row))
        control_box.append(self.workflow_run_state_label)
        control_box.append(view_title)
        control_box.append(wrap_horizontal_row(view_row))
        control_box.append(wrap_horizontal_row(arrange_row))
        control_box.append(execution_title)
        control_box.append(wrap_horizontal_row(execution_row))
        control_box.append(execution_preset_title)
        control_box.append(wrap_horizontal_row(execution_preset_row))
        control_box.append(templates_title)
        control_box.append(wrap_horizontal_row(template_row))
        control_box.append(preflight_issues_title)
        control_box.append(self.preflight_issue_summary)
        control_box.append(self.preflight_issue_scroll)
        control_box.append(self.status_label)

        self.inspector_box.append(inspector_title)
        self.inspector_box.append(self.node_name_label)
        self.inspector_box.append(self.node_type_label)
        self.inspector_box.append(self.node_position_label)
        self.inspector_box.append(self.node_link_label)
        self.inspector_box.append(preview_title)
        self.inspector_box.append(self.node_summary_label)
        self.inspector_box.append(self.node_detail_label)
        self.inspector_box.append(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))
        self.inspector_box.append(self.edit_title)
        self.inspector_box.append(self.edit_name_entry)
        self.inspector_box.append(self.edit_summary_entry)
        self.inspector_box.append(self.detail_expander)
        self.inspector_box.append(self.trigger_section)
        self.inspector_box.append(self.action_integration_section)
        self.inspector_box.append(self.provider_label)
        self.inspector_box.append(self.edit_provider_dropdown)
        self.inspector_box.append(self.edit_model_entry)
        self.inspector_box.append(self.edit_bot_entry)
        self.inspector_box.append(self.edit_bot_chain_entry)
        self.inspector_box.append(self.edit_system_entry)
        self.inspector_box.append(self.temp_title)
        self.inspector_box.append(self.edit_temp_override_switch)
        self.inspector_box.append(self.temp_adjust_row)
        self.inspector_box.append(self.max_tokens_title)
        self.inspector_box.append(self.edit_tokens_override_switch)
        self.inspector_box.append(self.max_tokens_adjust_row)
        self.inspector_box.append(self.condition_title)
        self.inspector_box.append(self.condition_mode_row)
        self.inspector_box.append(self.condition_value_row)
        self.inspector_box.append(self.condition_min_len_field_row)
        self.inspector_box.append(self.condition_preview_input_row)
        self.inspector_box.append(self.condition_preview_label)
        self.inspector_box.append(self.node_execution_title)
        self.inspector_box.append(node_exec_grid)
        self.inspector_box.append(self.node_execution_preset_row)
        self.inspector_box.append(node_exec_action_row)
        self.inspector_box.append(self.node_execution_hint_label)
        self.inspector_box.append(self.node_test_section)
        self.inspector_box.append(self.apply_node_button)

        inspector_scroll.set_child(self.inspector_box)
        workflow_scroll.set_child(control_box)

        self.workflow_mode_box = control_box
        self.workflow_mode_scroll = workflow_scroll
        self.node_mode_scroll = inspector_scroll
        self.workflow_mode_box.add_css_class("canvas-workflow-mode")
        self.workflow_mode_scroll.add_css_class("canvas-workflow-mode-scroll")
        self.node_mode_scroll.add_css_class("canvas-node-mode-scroll")
        inspector_shell.append(self.workflow_mode_scroll)
        inspector_shell.append(self.node_mode_scroll)
        inspector_frame.set_child(inspector_shell)

        main_split.set_start_child(canvas_frame)
        main_split.set_end_child(inspector_frame)
        main_split.set_resize_start_child(True)
        main_split.set_shrink_start_child(True)
        main_split.set_resize_end_child(False)
        main_split.set_shrink_end_child(False)

        self.append(main_split)

        canvas_key_controller = Gtk.EventControllerKey()
        canvas_key_controller.connect("key-pressed", self.on_canvas_key_pressed)
        self.add_controller(canvas_key_controller)

        self.update_zoom_button_label()
        self.update_stage_dimensions()
        self.reload_templates()
        self.reload_workflows()
        self.update_trigger_controls_state()
        self.update_condition_controls_state()
        self.update_inspector_adjustment_states()
        self.update_action_integration_section_visibility(None)
        self.update_action_integration_field_visibility()
        self.bind_action_field_change_events()
        self.bind_trigger_condition_change_events()
        self.render_preflight_issue_list()
        self.clear_inspector()
        self.refresh_workflow_run_state(quiet=True)
        GLib.timeout_add(1200, self.poll_workflow_run_state)

    def set_status(self, message: str):
        self.status_label.set_text(message)

    def set_selection(self, node_ids: set[str], primary_id: str | None = None):
        previous_ids = set(self.selected_node_ids)
        previous_primary = self.selected_node_id

        valid_ids = {node_id for node_id in node_ids if self.find_node(node_id)}
        self.selected_node_ids = valid_ids

        resolved_primary = primary_id if primary_id in valid_ids else None
        if not resolved_primary and self.selected_node_id in valid_ids:
            resolved_primary = self.selected_node_id
        if not resolved_primary and valid_ids:
            resolved_primary = next(iter(valid_ids))

        self.selected_node_id = resolved_primary
        self.apply_selection_set_visual_state(
            previous_ids,
            self.selected_node_ids,
            previous_primary,
            self.selected_node_id,
        )

    def set_single_selection(self, node_id: str | None):
        if node_id:
            self.set_selection({node_id}, primary_id=node_id)
        else:
            self.set_selection(set(), primary_id=None)

    def apply_selection_set_visual_state(
        self,
        previous_ids: set[str],
        current_ids: set[str],
        previous_primary: str | None,
        current_primary: str | None,
    ):
        for node_id in previous_ids - current_ids:
            widget = self.node_widgets.get(node_id)
            if widget:
                widget.remove_css_class("canvas-node-selected")
                widget.remove_css_class("canvas-node-primary")

        for node_id in current_ids - previous_ids:
            widget = self.node_widgets.get(node_id)
            if widget:
                widget.add_css_class("canvas-node-selected")

        if previous_primary and previous_primary != current_primary:
            widget = self.node_widgets.get(previous_primary)
            if widget:
                widget.remove_css_class("canvas-node-primary")
        if current_primary:
            widget = self.node_widgets.get(current_primary)
            if widget:
                widget.add_css_class("canvas-node-primary")

    def current_selection_bounds(self) -> tuple[float, float, float, float]:
        left = min(self.selection_rect_start_x, self.selection_rect_end_x)
        top = min(self.selection_rect_start_y, self.selection_rect_end_y)
        right = max(self.selection_rect_start_x, self.selection_rect_end_x)
        bottom = max(self.selection_rect_start_y, self.selection_rect_end_y)
        return left, top, right, bottom

    def on_stage_select_drag_begin(self, gesture: Gtk.GestureDrag, start_x: float, start_y: float):
        state = gesture.get_current_event_state()
        selection_modifiers = Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK
        if not bool(state & selection_modifiers):
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        if self.port_drag_active or self.node_drag_active:
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        if self.find_node_at_point(int(start_x), int(start_y)):
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        additive = bool(state & selection_modifiers)
        self.selection_rect_active = True
        self.selection_rect_start_x = float(start_x)
        self.selection_rect_start_y = float(start_y)
        self.selection_rect_end_x = float(start_x)
        self.selection_rect_end_y = float(start_y)
        self.selection_additive = additive
        self.selection_base_ids = set(self.selected_node_ids) if additive else set()
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.link_layer.queue_draw()

    def on_stage_select_drag_update(self, _gesture: Gtk.GestureDrag, offset_x: float, offset_y: float):
        if not self.selection_rect_active:
            return
        self.selection_rect_end_x = self.selection_rect_start_x + float(offset_x)
        self.selection_rect_end_y = self.selection_rect_start_y + float(offset_y)
        self.link_layer.queue_draw()

    def on_stage_select_drag_end(self, _gesture: Gtk.GestureDrag, _offset_x: float, _offset_y: float):
        if not self.selection_rect_active:
            return

        left, top, right, bottom = self.current_selection_bounds()
        selected_ids: set[str] = set(self.selection_base_ids) if self.selection_additive else set()
        for node in self.nodes:
            node_x = self.to_screen(node.x)
            node_y = self.to_screen(node.y)
            node_w = self.card_screen_width()
            node_h = self.card_screen_height()
            intersects = (
                node_x < right
                and (node_x + node_w) > left
                and node_y < bottom
                and (node_y + node_h) > top
            )
            if intersects:
                selected_ids.add(node.id)

        primary = self.selected_node_id if self.selected_node_id in selected_ids else None
        if not primary and selected_ids:
            primary = next(iter(selected_ids))

        self.set_selection(selected_ids, primary_id=primary)
        self.selection_rect_active = False
        self.selection_additive = False
        self.selection_base_ids = set()
        self.suppress_stage_click_once = True
        self.link_layer.queue_draw()

        if self.selected_node_id:
            selected_node = self.find_node(self.selected_node_id)
            if selected_node:
                self.update_inspector(selected_node)
            self.update_control_state()
            self.set_status(f"Selected {len(self.selected_node_ids)} node(s).")
        else:
            self.clear_inspector()
            self.update_control_state()
            self.set_status("Selection cleared.")

    def build_inspector_field_row(self, label_text: str, widget: Gtk.Widget) -> tuple[Gtk.Box, Gtk.Label]:
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        row.add_css_class("settings-field-row")
        label = Gtk.Label(label=label_text)
        label.add_css_class("heading")
        label.set_halign(Gtk.Align.START)
        row.append(label)
        row.append(widget)
        return row, label

    def register_action_field(
        self,
        field_key: str,
        row: Gtk.Widget,
        *widgets: Gtk.Widget,
        label: Gtk.Label | None = None,
    ):
        key = str(field_key).strip().lower()
        if not key:
            return
        row.add_css_class("canvas-action-field-row")
        feedback = Gtk.Label(label="")
        feedback.set_wrap(True)
        feedback.set_halign(Gtk.Align.START)
        feedback.add_css_class("dim-label")
        feedback.add_css_class("canvas-action-field-feedback")
        feedback.set_visible(False)
        if isinstance(row, Gtk.Box):
            row.append(feedback)

        self.action_field_rows[key] = row
        self.action_field_feedback_labels[key] = feedback
        self.action_field_widgets[key] = [item for item in widgets if item is not None]
        if label:
            self.action_field_labels[key] = label

    def clear_action_field_feedback(self):
        for key, row in self.action_field_rows.items():
            row.remove_css_class("canvas-action-field-error-row")
            row.remove_css_class("canvas-action-field-warning-row")
            row.set_tooltip_text(None)
            label = self.action_field_labels.get(key)
            if label:
                label.remove_css_class("canvas-action-field-error-label")
                label.remove_css_class("canvas-action-field-warning-label")
            feedback = self.action_field_feedback_labels.get(key)
            if feedback:
                feedback.set_text("")
                feedback.remove_css_class("canvas-action-field-feedback-error")
                feedback.remove_css_class("canvas-action-field-feedback-warning")
                feedback.set_visible(False)
            for widget in self.action_field_widgets.get(key, []):
                widget.remove_css_class("canvas-action-field-input-error")
                widget.remove_css_class("canvas-action-field-input-warning")

    def set_action_field_feedback(self, field_key: str, message: str, severity: str = "error"):
        key = str(field_key).strip().lower()
        row = self.action_field_rows.get(key)
        if not row:
            return
        if not row.get_visible():
            return

        normalized = "warning" if str(severity).strip().lower() == "warning" else "error"
        feedback = self.action_field_feedback_labels.get(key)
        label = self.action_field_labels.get(key)
        css_suffix = "warning" if normalized == "warning" else "error"
        row_css = f"canvas-action-field-{css_suffix}-row"
        label_css = f"canvas-action-field-{css_suffix}-label"
        feedback_css = f"canvas-action-field-feedback-{css_suffix}"
        input_css = f"canvas-action-field-input-{css_suffix}"

        row.add_css_class(row_css)
        row.set_tooltip_text(message)
        if label:
            label.add_css_class(label_css)
        if feedback:
            feedback.set_text(str(message).strip())
            feedback.add_css_class(feedback_css)
            feedback.set_visible(True)
        for widget in self.action_field_widgets.get(key, []):
            widget.add_css_class(input_css)

    def register_node_field(
        self,
        field_key: str,
        row: Gtk.Widget,
        *widgets: Gtk.Widget,
        label: Gtk.Label | None = None,
    ):
        key = str(field_key).strip().lower()
        if not key:
            return
        row.add_css_class("canvas-node-field-row")
        feedback = Gtk.Label(label="")
        feedback.set_wrap(True)
        feedback.set_halign(Gtk.Align.START)
        feedback.add_css_class("dim-label")
        feedback.add_css_class("canvas-node-field-feedback")
        feedback.set_visible(False)
        if isinstance(row, Gtk.Box):
            row.append(feedback)

        self.node_field_rows[key] = row
        self.node_field_feedback_labels[key] = feedback
        self.node_field_widgets[key] = [item for item in widgets if item is not None]
        if label:
            self.node_field_labels[key] = label

    def clear_node_field_feedback(self, field_keys: set[str] | None = None):
        keys = (
            {str(item).strip().lower() for item in field_keys}
            if field_keys
            else set(self.node_field_rows.keys())
        )
        for key in keys:
            row = self.node_field_rows.get(key)
            if not row:
                continue
            row.remove_css_class("canvas-node-field-error-row")
            row.remove_css_class("canvas-node-field-warning-row")
            row.set_tooltip_text(None)
            label = self.node_field_labels.get(key)
            if label:
                label.remove_css_class("canvas-node-field-error-label")
                label.remove_css_class("canvas-node-field-warning-label")
            feedback = self.node_field_feedback_labels.get(key)
            if feedback:
                feedback.set_text("")
                feedback.remove_css_class("canvas-node-field-feedback-error")
                feedback.remove_css_class("canvas-node-field-feedback-warning")
                feedback.set_visible(False)
            for widget in self.node_field_widgets.get(key, []):
                widget.remove_css_class("canvas-node-field-input-error")
                widget.remove_css_class("canvas-node-field-input-warning")

    def set_node_field_feedback(self, field_key: str, message: str, severity: str = "error"):
        key = str(field_key).strip().lower()
        row = self.node_field_rows.get(key)
        if not row:
            return
        if not row.get_visible():
            return

        normalized = "warning" if str(severity).strip().lower() == "warning" else "error"
        feedback = self.node_field_feedback_labels.get(key)
        label = self.node_field_labels.get(key)
        css_suffix = "warning" if normalized == "warning" else "error"
        row_css = f"canvas-node-field-{css_suffix}-row"
        label_css = f"canvas-node-field-{css_suffix}-label"
        feedback_css = f"canvas-node-field-feedback-{css_suffix}"
        input_css = f"canvas-node-field-input-{css_suffix}"

        row.add_css_class(row_css)
        row.set_tooltip_text(message)
        if label:
            label.add_css_class(label_css)
        if feedback:
            feedback.set_text(str(message).strip())
            feedback.add_css_class(feedback_css)
            feedback.set_visible(True)
        for widget in self.node_field_widgets.get(key, []):
            widget.add_css_class(input_css)

    def build_inspector_group(
        self,
        title: str,
        rows: list[Gtk.Widget],
        expanded: bool = False,
    ) -> Gtk.Expander:
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        body.add_css_class("canvas-inspector-group-body")
        for row in rows:
            body.append(row)

        group = Gtk.Expander(label=title)
        group.add_css_class("canvas-inspector-group")
        group.set_expanded(expanded)
        group.set_child(body)
        return group

    def load_action_integration_options(self) -> list[tuple[str, str]]:
        integrations = self.integration_registry.list_integrations()
        options: list[tuple[str, str]] = []
        for item in integrations:
            key = str(item.get("key", "")).strip().lower()
            name = str(item.get("name", "")).strip() or key
            if not key:
                continue
            options.append((key, f"{name} ({key})"))
        if not options:
            return [("standard", "Standard Action (standard)")]
        return options

    def action_template_definitions(self) -> list[dict]:
        return [
            {
                "key": "generic_action",
                "label": "Generic Action",
                "description": "Flexible action shell for custom integration logic.",
                "integration": "standard",
                "defaults": {},
            },
            {
                "key": "notify_slack",
                "label": "Notify • Slack",
                "description": "Send workflow status updates to Slack webhook channel.",
                "integration": "slack_webhook",
                "defaults": {"message": "Workflow update: ${last_output}"},
            },
            {
                "key": "notify_discord",
                "label": "Notify • Discord",
                "description": "Broadcast workflow updates to Discord webhook.",
                "integration": "discord_webhook",
                "defaults": {"message": "Workflow update: ${last_output}"},
            },
            {
                "key": "notify_teams",
                "label": "Notify • Teams",
                "description": "Send workflow updates to a Microsoft Teams webhook.",
                "integration": "teams_webhook",
                "defaults": {"message": "Workflow update: ${last_output}"},
            },
            {
                "key": "message_email",
                "label": "Message • Email",
                "description": "Send an email using Gmail integration settings.",
                "integration": "gmail_send",
                "defaults": {
                    "to": "you@example.com",
                    "subject": "Workflow Update",
                    "message": "${last_output}",
                },
            },
            {
                "key": "message_sms",
                "label": "Message • SMS",
                "description": "Send SMS notification via Twilio.",
                "integration": "twilio_sms",
                "defaults": {
                    "to": "+15550002222",
                    "from": "+15550001111",
                    "message": "${last_output}",
                },
            },
            {
                "key": "message_telegram",
                "label": "Message • Telegram",
                "description": "Send Telegram message to configured chat.",
                "integration": "telegram_bot",
                "defaults": {"chat_id": "REPLACE_CHAT_ID", "message": "Workflow update: ${last_output}"},
            },
            {
                "key": "calendar_event",
                "label": "Calendar • Event",
                "description": "Create/update calendar event through Google Apps Script endpoint.",
                "integration": "google_apps_script",
                "defaults": {
                    "payload": "{\"operation\":\"calendar_event\",\"title\":\"Automation Event\",\"summary\":\"${last_output}\"}",
                },
            },
            {
                "key": "google_calendar_event",
                "label": "Calendar • Google API",
                "description": "Call Google Calendar API with OAuth bearer token.",
                "integration": "google_calendar_api",
                "defaults": {
                    "endpoint": "https://www.googleapis.com/calendar/v3/users/me/calendarList",
                    "method": "GET",
                },
            },
            {
                "key": "google_sheets_append",
                "label": "Data • Google Sheets",
                "description": "Append workflow data into a Google Sheets range.",
                "integration": "google_sheets",
                "defaults": {
                    "payload": "{\"spreadsheet_id\":\"REPLACE_ID\",\"range\":\"Sheet1!A:B\",\"values\":[[\"${workflow_name}\",\"${last_output}\"]]}",
                },
            },
            {
                "key": "outlook_message",
                "label": "Message • Outlook",
                "description": "Call Outlook Graph API for mail/calendar actions.",
                "integration": "outlook_graph",
                "defaults": {
                    "endpoint": "https://graph.microsoft.com/v1.0/me/messages?$top=5",
                    "method": "GET",
                },
            },
            {
                "key": "weather_lookup",
                "label": "Data • Weather",
                "description": "Lookup current weather using OpenWeather connector.",
                "integration": "openweather_current",
                "defaults": {"location": "Austin,US", "units": "metric"},
            },
            {
                "key": "http_request",
                "label": "Data • HTTP Request",
                "description": "Call REST endpoint with method/headers/payload.",
                "integration": "http_request",
                "defaults": {"endpoint": "https://api.example.com/endpoint", "method": "POST"},
            },
            {
                "key": "webhook_post",
                "label": "Data • Webhook POST",
                "description": "Send JSON to a webhook endpoint.",
                "integration": "http_post",
                "defaults": {"endpoint": "https://api.example.com/webhook"},
            },
            {
                "key": "jira_issue_lookup",
                "label": "Project • Jira",
                "description": "Call Jira Cloud API for user/issue/project operations.",
                "integration": "jira_api",
                "defaults": {
                    "endpoint": "https://your-domain.atlassian.net/rest/api/3/myself",
                    "method": "GET",
                },
            },
            {
                "key": "asana_task",
                "label": "Project • Asana",
                "description": "Call Asana API to fetch users/workspaces/tasks.",
                "integration": "asana_api",
                "defaults": {
                    "endpoint": "https://app.asana.com/api/1.0/users/me",
                    "method": "GET",
                },
            },
            {
                "key": "clickup_task",
                "label": "Project • ClickUp",
                "description": "Call ClickUp API for lists, tasks, and updates.",
                "integration": "clickup_api",
                "defaults": {
                    "endpoint": "https://api.clickup.com/api/v2/user",
                    "method": "GET",
                },
            },
            {
                "key": "trello_board",
                "label": "Project • Trello",
                "description": "Call Trello API for boards, lists, and cards.",
                "integration": "trello_api",
                "defaults": {
                    "endpoint": "https://api.trello.com/1/members/me",
                    "method": "GET",
                },
            },
            {
                "key": "monday_query",
                "label": "Project • Monday",
                "description": "Call Monday GraphQL API for workspace entities.",
                "integration": "monday_api",
                "defaults": {
                    "endpoint": "https://api.monday.com/v2",
                    "method": "POST",
                    "payload": "{\"query\":\"{ me { id name email } }\"}",
                },
            },
            {
                "key": "zendesk_ticket",
                "label": "Support • Zendesk",
                "description": "Call Zendesk API for ticket and user workflows.",
                "integration": "zendesk_api",
                "defaults": {
                    "endpoint": "https://your-domain.zendesk.com/api/v2/users/me.json",
                    "method": "GET",
                },
            },
            {
                "key": "salesforce_query",
                "label": "CRM • Salesforce",
                "description": "Call Salesforce REST endpoints with OAuth token.",
                "integration": "salesforce_api",
                "defaults": {
                    "endpoint": "https://your-instance.my.salesforce.com/services/data/v58.0/limits",
                    "method": "GET",
                },
            },
            {
                "key": "pipedrive_deal",
                "label": "CRM • Pipedrive",
                "description": "Call Pipedrive API for people, deals, and pipeline state.",
                "integration": "pipedrive_api",
                "defaults": {
                    "endpoint": "https://api.pipedrive.com/v1/users/me",
                    "method": "GET",
                },
            },
            {
                "key": "notion_page",
                "label": "Docs • Notion",
                "description": "Create a Notion page using API token and database id.",
                "integration": "notion_api",
                "defaults": {
                    "endpoint": "https://api.notion.com/v1/pages",
                    "method": "POST",
                    "payload": "{\"parent\":{\"database_id\":\"REPLACE_DB\"},\"properties\":{\"Name\":{\"title\":[{\"text\":{\"content\":\"Workflow Update\"}}]}}}",
                },
            },
            {
                "key": "airtable_record",
                "label": "Data • Airtable",
                "description": "Create a record in Airtable base/table from workflow output.",
                "integration": "airtable_api",
                "defaults": {
                    "endpoint": "https://api.airtable.com/v0/REPLACE_BASE/REPLACE_TABLE",
                    "method": "POST",
                    "payload": "{\"records\":[{\"fields\":{\"Name\":\"${workflow_name}\",\"Output\":\"${last_output}\"}}]}",
                },
            },
            {
                "key": "github_user",
                "label": "Developer • GitHub",
                "description": "Query GitHub REST API with bearer token.",
                "integration": "github_rest",
                "defaults": {
                    "endpoint": "https://api.github.com/user",
                    "method": "GET",
                    "headers": "{\"Accept\":\"application/vnd.github+json\"}",
                },
            },
            {
                "key": "hubspot_contacts",
                "label": "CRM • HubSpot",
                "description": "Read HubSpot contacts through CRM API.",
                "integration": "hubspot_api",
                "defaults": {
                    "endpoint": "https://api.hubapi.com/crm/v3/objects/contacts?limit=5",
                    "method": "GET",
                },
            },
            {
                "key": "stripe_balance",
                "label": "Commerce • Stripe",
                "description": "Fetch Stripe account balance and charges.",
                "integration": "stripe_api",
                "defaults": {
                    "endpoint": "https://api.stripe.com/v1/balance",
                    "method": "GET",
                },
            },
            {
                "key": "google_drive_files",
                "label": "Google • Drive Files",
                "description": "List files from Google Drive API.",
                "integration": "google_drive_api",
                "defaults": {
                    "endpoint": "https://www.googleapis.com/drive/v3/files?pageSize=10",
                    "method": "GET",
                },
            },
            {
                "key": "dropbox_files",
                "label": "Storage • Dropbox Files",
                "description": "List files from Dropbox API.",
                "integration": "dropbox_api",
                "defaults": {
                    "endpoint": "https://api.dropboxapi.com/2/files/list_folder",
                    "method": "POST",
                    "payload": "{\"path\":\"\",\"recursive\":false,\"limit\":20}",
                },
            },
            {
                "key": "shopify_products",
                "label": "Commerce • Shopify Products",
                "description": "Read Shopify product list using Admin API.",
                "integration": "shopify_api",
                "defaults": {
                    "endpoint": "https://your-store.myshopify.com/admin/api/2024-10/products.json?limit=10",
                    "method": "GET",
                },
            },
            {
                "key": "webflow_sites",
                "label": "Web • Webflow Sites",
                "description": "List available Webflow sites.",
                "integration": "webflow_api",
                "defaults": {
                    "endpoint": "https://api.webflow.com/v2/sites",
                    "method": "GET",
                },
            },
            {
                "key": "supabase_rows",
                "label": "Data • Supabase Rows",
                "description": "Query rows from Supabase REST endpoint.",
                "integration": "supabase_api",
                "defaults": {
                    "endpoint": "https://YOUR_PROJECT.supabase.co/rest/v1/your_table?select=*",
                    "method": "GET",
                },
            },
            {
                "key": "openrouter_chat",
                "label": "AI • OpenRouter Chat",
                "description": "Call OpenRouter chat/completions endpoint.",
                "integration": "openrouter_api",
                "defaults": {
                    "endpoint": "https://openrouter.ai/api/v1/chat/completions",
                    "method": "POST",
                    "payload": "{\"model\":\"openai/gpt-4o-mini\",\"messages\":[{\"role\":\"user\",\"content\":\"Say hi from 6X Protocol\"}]}",
                },
            },
            {
                "key": "linear_query",
                "label": "Project • Linear",
                "description": "Run a Linear GraphQL query for issues and teams.",
                "integration": "linear_api",
                "defaults": {
                    "payload": "{\"query\":\"{ viewer { id name } }\"}",
                },
            },
            {
                "key": "gitlab_rest",
                "label": "Developer • GitLab",
                "description": "Call GitLab REST API with private token.",
                "integration": "gitlab_api",
                "defaults": {
                    "endpoint": "https://gitlab.com/api/v4/user",
                    "method": "GET",
                },
            },
            {
                "key": "file_append",
                "label": "Local • File Append",
                "description": "Append workflow output to a local file.",
                "integration": "file_append",
                "defaults": {"path": "/tmp/6x-workflow.log", "message": "${last_output}"},
            },
            {
                "key": "shell_command",
                "label": "Local • Shell Command",
                "description": "Run local shell command with workflow context.",
                "integration": "shell_command",
                "defaults": {"command": "echo \"$INPUT_CONTEXT\""},
            },
            {
                "key": "approval_gate",
                "label": "Control • Approval Gate",
                "description": "Pause run and wait for human approval.",
                "integration": "approval_gate",
                "defaults": {"message": "Approve this step before continuing."},
            },
        ]

    def action_template_index(self, key: str) -> int:
        normalized = str(key).strip().lower()
        if normalized in self.action_template_keys:
            return self.action_template_keys.index(normalized)
        return 0

    def selected_action_template(self) -> dict:
        index = self.action_template_dropdown.get_selected()
        if 0 <= index < len(self.action_template_specs):
            return self.action_template_specs[index]
        return self.action_template_specs[0] if self.action_template_specs else {}

    def update_action_template_hint(self):
        selected = self.selected_action_template()
        description = str(selected.get("description", "")).strip()
        integration = str(selected.get("integration", "")).strip()
        if description and integration:
            self.action_template_hint_label.set_text(f"{description} Integration: {integration}.")
            return
        if description:
            self.action_template_hint_label.set_text(description)
            return
        self.action_template_hint_label.set_text("Choose an action type to preconfigure this node.")

    def on_action_template_changed(self, *_args):
        self.update_action_template_hint()
        template_key = str(self.selected_action_template().get("key", "")).strip().lower()
        integration = self.selected_action_integration()
        self.sync_action_category_state(
            self.infer_action_category(template_key, integration)
        )

    def apply_action_template(self, template_key: str, announce: bool = True):
        if template_key not in self.action_template_keys:
            return
        index = self.action_template_keys.index(template_key)
        spec = self.action_template_specs[index]
        integration = str(spec.get("integration", "")).strip().lower() or "standard"
        defaults = spec.get("defaults", {}) if isinstance(spec.get("defaults", {}), dict) else {}

        self.action_template_dropdown.set_selected(index)
        self.action_integration_dropdown.set_selected(self.action_integration_index(integration))
        self.update_action_integration_field_visibility()
        self.action_endpoint_entry.set_text(str(defaults.get("endpoint", "")).strip())
        self.action_message_entry.set_text(str(defaults.get("message", "")).strip())
        self.action_to_entry.set_text(str(defaults.get("to", "")).strip())
        self.action_from_entry.set_text(str(defaults.get("from", "")).strip())
        self.action_subject_entry.set_text(str(defaults.get("subject", "")).strip())
        self.action_chat_id_entry.set_text(str(defaults.get("chat_id", "")).strip())
        self.action_account_sid_entry.set_text(str(defaults.get("account_sid", "")).strip())
        self.action_auth_token_entry.set_text(str(defaults.get("auth_token", "")).strip())
        self.action_domain_entry.set_text(str(defaults.get("domain", "")).strip())
        self.action_username_entry.set_text(str(defaults.get("username", "")).strip())
        self.set_action_payload_text(str(defaults.get("payload", "")).strip())
        self.action_headers_entry.set_text(str(defaults.get("headers", "")).strip())
        self.action_api_key_entry.set_text(str(defaults.get("api_key", "")).strip())
        self.action_location_entry.set_text(str(defaults.get("location", "")).strip())
        self.action_units_dropdown.set_selected(
            self.action_units_index(str(defaults.get("units", "metric")).strip())
        )
        self.action_path_entry.set_text(str(defaults.get("path", "")).strip())
        self.action_command_entry.set_text(str(defaults.get("command", "")).strip())
        method = str(defaults.get("method", "")).strip().upper()
        if method:
            self.action_method_dropdown.set_selected(self.action_method_index(method))
        timeout = str(defaults.get("timeout_sec", "")).strip()
        if timeout:
            self.action_timeout_spin.set_value(max(0.0, self.parse_float(timeout, 0.0)))
        self.update_action_template_hint()
        if announce:
            self.set_status(f"Applied action type: {spec.get('label', template_key)}.")

    def on_apply_action_template_clicked(self, _button):
        selected = self.selected_action_template()
        key = str(selected.get("key", "")).strip().lower()
        if not key:
            return
        self.apply_action_template(key, announce=True)

    def saved_action_defaults(self, integration: str) -> dict[str, str]:
        key = str(integration).strip().lower()
        settings = self.settings_store.load_settings()
        defaults: dict[str, str] = {}

        def add(target_key: str, value: str):
            text = str(value).strip()
            if text:
                defaults[target_key] = text

        if key == "slack_webhook":
            add("endpoint", settings.get("slack_webhook_url", ""))
        elif key == "discord_webhook":
            add("endpoint", settings.get("discord_webhook_url", ""))
        elif key == "teams_webhook":
            add("endpoint", settings.get("teams_webhook_url", ""))
        elif key == "telegram_bot":
            add("api_key", settings.get("telegram_bot_token", ""))
            add("chat_id", settings.get("telegram_default_chat_id", ""))
        elif key == "openweather_current":
            add("api_key", settings.get("openweather_api_key", ""))
            add("location", settings.get("openweather_default_location", ""))
        elif key == "google_apps_script":
            add("endpoint", settings.get("google_apps_script_url", ""))
        elif key == "google_sheets":
            add("api_key", settings.get("google_sheets_api_key", ""))
            add("spreadsheet_id", settings.get("google_sheets_spreadsheet_id", ""))
            add("range", settings.get("google_sheets_range", ""))
        elif key == "google_calendar_api":
            add("api_key", settings.get("google_calendar_api_key", ""))
            add("endpoint", settings.get("google_calendar_api_url", ""))
        elif key == "outlook_graph":
            add("api_key", settings.get("outlook_api_key", ""))
            add("endpoint", settings.get("outlook_api_url", ""))
        elif key == "gmail_send":
            add("api_key", settings.get("gmail_api_key", ""))
            add("from", settings.get("gmail_from_address", ""))
        elif key == "twilio_sms":
            add("account_sid", settings.get("twilio_account_sid", ""))
            add("auth_token", settings.get("twilio_auth_token", ""))
            add("from", settings.get("twilio_from_number", ""))
        elif key == "resend_email":
            add("api_key", settings.get("resend_api_key", ""))
            add("from", settings.get("resend_from_address", ""))
        elif key == "mailgun_email":
            add("api_key", settings.get("mailgun_api_key", ""))
            add("domain", settings.get("mailgun_domain", ""))
            add("from", settings.get("mailgun_from_address", ""))
        else:
            integration_key_map = {
                "notion_api": ("notion_api_key", "notion_api_url"),
                "airtable_api": ("airtable_api_key", "airtable_api_url"),
                "hubspot_api": ("hubspot_api_key", "hubspot_api_url"),
                "stripe_api": ("stripe_api_key", "stripe_api_url"),
                "github_rest": ("github_api_key", "github_api_url"),
                "jira_api": ("jira_api_key", "jira_api_url"),
                "asana_api": ("asana_api_key", "asana_api_url"),
                "clickup_api": ("clickup_api_key", "clickup_api_url"),
                "trello_api": ("trello_api_key", "trello_api_url"),
                "monday_api": ("monday_api_key", "monday_api_url"),
                "zendesk_api": ("zendesk_api_key", "zendesk_api_url"),
                "pipedrive_api": ("pipedrive_api_key", "pipedrive_api_url"),
                "salesforce_api": ("salesforce_api_key", "salesforce_api_url"),
                "gitlab_api": ("gitlab_api_key", "gitlab_api_url"),
                "google_drive_api": ("google_drive_api_key", "google_drive_api_url"),
                "dropbox_api": ("dropbox_api_key", "dropbox_api_url"),
                "shopify_api": ("shopify_api_key", "shopify_api_url"),
                "webflow_api": ("webflow_api_key", "webflow_api_url"),
                "supabase_api": ("supabase_api_key", "supabase_api_url"),
                "openrouter_api": ("openrouter_api_key", "openrouter_api_url"),
                "linear_api": ("linear_api_key", ""),
            }
            api_key_key, url_key = integration_key_map.get(key, ("", ""))
            if api_key_key:
                add("api_key", settings.get(api_key_key, ""))
            if url_key:
                add("endpoint", settings.get(url_key, ""))

        return defaults

    def on_load_saved_action_defaults_clicked(self, _button):
        integration = self.selected_action_integration()
        defaults = self.saved_action_defaults(integration)
        if not defaults:
            self.set_status("No saved defaults found for this integration.")
            return

        if "endpoint" in defaults:
            self.action_endpoint_entry.set_text(defaults["endpoint"])
        if "api_key" in defaults:
            self.action_api_key_entry.set_text(defaults["api_key"])
        if "chat_id" in defaults:
            self.action_chat_id_entry.set_text(defaults["chat_id"])
        if "location" in defaults:
            self.action_location_entry.set_text(defaults["location"])
        if "account_sid" in defaults:
            self.action_account_sid_entry.set_text(defaults["account_sid"])
        if "auth_token" in defaults:
            self.action_auth_token_entry.set_text(defaults["auth_token"])
        if "from" in defaults:
            self.action_from_entry.set_text(defaults["from"])
        if "domain" in defaults:
            self.action_domain_entry.set_text(defaults["domain"])

        spreadsheet_id = defaults.get("spreadsheet_id", "")
        range_value = defaults.get("range", "")
        if integration == "google_sheets" and spreadsheet_id and range_value:
            self.set_payload_if_missing(
                (
                    '{"spreadsheet_id":"'
                    + spreadsheet_id.replace('"', '\\"')
                    + '","range":"'
                    + range_value.replace('"', '\\"')
                    + '","values":[["${workflow_name}","${last_output}"]]}'
                ),
                force=False,
            )

        self.update_action_requirements_status()
        count = len(defaults)
        noun = "value" if count == 1 else "values"
        self.set_status(
            f"Loaded {count} saved {noun} for {integration or 'action integration'}."
        )

    def infer_action_template_key(self, merged_config: dict[str, str]) -> str:
        explicit = str(merged_config.get("action_template", "")).strip().lower()
        if explicit in self.action_template_keys:
            return explicit

        integration = str(merged_config.get("integration", "")).strip().lower()
        mapping = {
            "slack_webhook": "notify_slack",
            "discord_webhook": "notify_discord",
            "teams_webhook": "notify_teams",
            "gmail_send": "message_email",
            "twilio_sms": "message_sms",
            "telegram_bot": "message_telegram",
            "outlook_graph": "outlook_message",
            "google_apps_script": "calendar_event",
            "google_calendar_api": "google_calendar_event",
            "google_sheets": "google_sheets_append",
            "openweather_current": "weather_lookup",
            "http_request": "http_request",
            "http_post": "webhook_post",
            "notion_api": "notion_page",
            "airtable_api": "airtable_record",
            "github_rest": "github_user",
            "hubspot_api": "hubspot_contacts",
            "stripe_api": "stripe_balance",
            "google_drive_api": "google_drive_files",
            "dropbox_api": "dropbox_files",
            "shopify_api": "shopify_products",
            "webflow_api": "webflow_sites",
            "supabase_api": "supabase_rows",
            "openrouter_api": "openrouter_chat",
            "jira_api": "jira_issue_lookup",
            "asana_api": "asana_task",
            "clickup_api": "clickup_task",
            "trello_api": "trello_board",
            "monday_api": "monday_query",
            "zendesk_api": "zendesk_ticket",
            "salesforce_api": "salesforce_query",
            "pipedrive_api": "pipedrive_deal",
            "linear_api": "linear_query",
            "gitlab_api": "gitlab_rest",
            "file_append": "file_append",
            "shell_command": "shell_command",
            "approval_gate": "approval_gate",
            "standard": "generic_action",
        }
        return mapping.get(integration, "generic_action")

    def action_integration_index(self, key: str) -> int:
        normalized = str(key).strip().lower()
        if normalized in self.action_integration_keys:
            return self.action_integration_keys.index(normalized)
        if "standard" in self.action_integration_keys:
            return self.action_integration_keys.index("standard")
        return 0

    def selected_action_integration(self) -> str:
        index = self.action_integration_dropdown.get_selected()
        if 0 <= index < len(self.action_integration_keys):
            return self.action_integration_keys[index]
        return "standard"

    def rebuild_action_preset_dropdown(self, labels: list[str], selected_index: int = 0):
        replacement = Gtk.DropDown.new_from_strings(labels)
        replacement.set_hexpand(True)
        replacement.set_selected(max(0, min(selected_index, len(labels) - 1)))
        parent = self.action_preset_dropdown.get_parent()
        if isinstance(parent, Gtk.Box):
            parent.remove(self.action_preset_dropdown)
            parent.prepend(replacement)
        self.action_preset_dropdown = replacement

    def action_preset_definitions(self, integration: str) -> list[dict[str, str]]:
        key = str(integration).strip().lower()
        if key == "slack_webhook":
            return [
                {"label": "Slack Alert", "message": "Automation alert: action completed.", "timeout_sec": "30.0"},
                {"label": "Slack Summary", "message": "Workflow summary: ${last_output}", "timeout_sec": "30.0"},
            ]
        if key == "discord_webhook":
            return [
                {"label": "Discord Alert", "message": "Automation alert: action completed.", "timeout_sec": "30.0"},
                {"label": "Discord Summary", "message": "Workflow summary: ${last_output}", "timeout_sec": "30.0"},
            ]
        if key == "teams_webhook":
            return [
                {"label": "Teams Alert", "message": "Automation alert: action completed.", "timeout_sec": "30.0"},
                {"label": "Teams Summary", "message": "Workflow summary: ${last_output}", "timeout_sec": "30.0"},
            ]
        if key == "http_post":
            return [
                {
                    "label": "JSON Forwarder",
                    "endpoint": "https://api.example.com/events",
                    "payload": "{\"event\":\"workflow_update\",\"data\":\"${last_output}\"}",
                    "timeout_sec": "45.0",
                }
            ]
        if key == "http_request":
            return [
                {
                    "label": "HTTP GET",
                    "endpoint": "https://httpbin.org/get",
                    "method": "GET",
                    "payload": "{\"query\":\"status\"}",
                    "timeout_sec": "30.0",
                },
                {
                    "label": "HTTP POST JSON",
                    "endpoint": "https://httpbin.org/post",
                    "method": "POST",
                    "payload": "{\"event\":\"workflow_update\",\"data\":\"${last_output}\"}",
                    "timeout_sec": "30.0",
                },
            ]
        if key == "openweather_current":
            return [
                {"label": "Current Weather (Metric)", "location": "Austin,US", "units": "metric", "timeout_sec": "20.0"},
                {"label": "Current Weather (Imperial)", "location": "Austin,US", "units": "imperial", "timeout_sec": "20.0"},
            ]
        if key == "telegram_bot":
            return [
                {
                    "label": "Telegram Alert",
                    "chat_id": "REPLACE_CHAT_ID",
                    "message": "Workflow update: ${last_output}",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "gmail_send":
            return [
                {
                    "label": "Gmail Notification",
                    "to": "you@example.com",
                    "subject": "Workflow update",
                    "message": "${last_output}",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "resend_email":
            return [
                {
                    "label": "Resend Notification",
                    "from": "alerts@yourdomain.com",
                    "to": "you@example.com",
                    "subject": "Workflow update",
                    "message": "${last_output}",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "mailgun_email":
            return [
                {
                    "label": "Mailgun Notification",
                    "domain": "mg.yourdomain.com",
                    "from": "alerts@yourdomain.com",
                    "to": "you@example.com",
                    "subject": "Workflow update",
                    "message": "${last_output}",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "google_sheets":
            return [
                {
                    "label": "Append Row",
                    "payload": "{\"spreadsheet_id\":\"REPLACE_ID\",\"range\":\"Sheet1!A:B\",\"values\":[[\"${workflow_name}\",\"${last_output}\"]]}",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "google_calendar_api":
            return [
                {
                    "label": "Calendar List",
                    "endpoint": "https://www.googleapis.com/calendar/v3/users/me/calendarList",
                    "method": "GET",
                    "timeout_sec": "30.0",
                },
                {
                    "label": "List Upcoming Events",
                    "endpoint": "https://www.googleapis.com/calendar/v3/calendars/primary/events?maxResults=5&singleEvents=true&orderBy=startTime",
                    "method": "GET",
                    "timeout_sec": "30.0",
                },
            ]
        if key == "outlook_graph":
            return [
                {
                    "label": "Outlook Me",
                    "endpoint": "https://graph.microsoft.com/v1.0/me",
                    "method": "GET",
                    "timeout_sec": "30.0",
                },
                {
                    "label": "Recent Outlook Messages",
                    "endpoint": "https://graph.microsoft.com/v1.0/me/messages?$top=5",
                    "method": "GET",
                    "timeout_sec": "30.0",
                },
            ]
        if key == "notion_api":
            return [
                {
                    "label": "Notion Create Page",
                    "endpoint": "https://api.notion.com/v1/pages",
                    "method": "POST",
                    "payload": "{\"parent\":{\"database_id\":\"REPLACE_DB\"},\"properties\":{\"Name\":{\"title\":[{\"text\":{\"content\":\"Workflow Update\"}}]}}}",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "airtable_api":
            return [
                {
                    "label": "Airtable Create Record",
                    "endpoint": "https://api.airtable.com/v0/REPLACE_BASE/REPLACE_TABLE",
                    "method": "POST",
                    "payload": "{\"records\":[{\"fields\":{\"Name\":\"${workflow_name}\",\"Output\":\"${last_output}\"}}]}",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "hubspot_api":
            return [
                {
                    "label": "HubSpot Contacts",
                    "endpoint": "https://api.hubapi.com/crm/v3/objects/contacts?limit=5",
                    "method": "GET",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "stripe_api":
            return [
                {
                    "label": "Stripe Charges",
                    "endpoint": "https://api.stripe.com/v1/charges?limit=5",
                    "method": "GET",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "google_drive_api":
            return [
                {
                    "label": "Drive File List",
                    "endpoint": "https://www.googleapis.com/drive/v3/files?pageSize=10",
                    "method": "GET",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "dropbox_api":
            return [
                {
                    "label": "Dropbox List Folder",
                    "endpoint": "https://api.dropboxapi.com/2/files/list_folder",
                    "method": "POST",
                    "payload": "{\"path\":\"\",\"recursive\":false,\"limit\":20}",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "shopify_api":
            return [
                {
                    "label": "Shopify Products",
                    "endpoint": "https://your-store.myshopify.com/admin/api/2024-10/products.json?limit=10",
                    "method": "GET",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "webflow_api":
            return [
                {
                    "label": "Webflow Sites",
                    "endpoint": "https://api.webflow.com/v2/sites",
                    "method": "GET",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "supabase_api":
            return [
                {
                    "label": "Supabase Query",
                    "endpoint": "https://YOUR_PROJECT.supabase.co/rest/v1/your_table?select=*",
                    "method": "GET",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "openrouter_api":
            return [
                {
                    "label": "OpenRouter Chat",
                    "endpoint": "https://openrouter.ai/api/v1/chat/completions",
                    "method": "POST",
                    "payload": "{\"model\":\"openai/gpt-4o-mini\",\"messages\":[{\"role\":\"user\",\"content\":\"Say hi from 6X Protocol\"}]}",
                    "timeout_sec": "45.0",
                }
            ]
        if key == "github_rest":
            return [
                {
                    "label": "GitHub User",
                    "endpoint": "https://api.github.com/user",
                    "method": "GET",
                    "headers": "{\"Accept\":\"application/vnd.github+json\"}",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "gitlab_api":
            return [
                {
                    "label": "GitLab User",
                    "endpoint": "https://gitlab.com/api/v4/user",
                    "method": "GET",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "jira_api":
            return [
                {
                    "label": "Jira Current User",
                    "endpoint": "https://your-domain.atlassian.net/rest/api/3/myself",
                    "method": "GET",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "asana_api":
            return [
                {
                    "label": "Asana Current User",
                    "endpoint": "https://app.asana.com/api/1.0/users/me",
                    "method": "GET",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "clickup_api":
            return [
                {
                    "label": "ClickUp Current User",
                    "endpoint": "https://api.clickup.com/api/v2/user",
                    "method": "GET",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "trello_api":
            return [
                {
                    "label": "Trello Member",
                    "endpoint": "https://api.trello.com/1/members/me",
                    "method": "GET",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "monday_api":
            return [
                {
                    "label": "Monday Me Query",
                    "endpoint": "https://api.monday.com/v2",
                    "method": "POST",
                    "payload": "{\"query\":\"{ me { id name email } }\"}",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "zendesk_api":
            return [
                {
                    "label": "Zendesk Current User",
                    "endpoint": "https://your-domain.zendesk.com/api/v2/users/me.json",
                    "method": "GET",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "pipedrive_api":
            return [
                {
                    "label": "Pipedrive Current User",
                    "endpoint": "https://api.pipedrive.com/v1/users/me",
                    "method": "GET",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "salesforce_api":
            return [
                {
                    "label": "Salesforce Limits",
                    "endpoint": "https://your-instance.my.salesforce.com/services/data/v58.0/limits",
                    "method": "GET",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "linear_api":
            return [
                {
                    "label": "Linear Viewer",
                    "payload": "{\"query\":\"{ viewer { id name } }\"}",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "twilio_sms":
            return [
                {
                    "label": "Twilio SMS",
                    "account_sid": "REPLACE_SID",
                    "auth_token": "REPLACE_TOKEN",
                    "from": "+15550001111",
                    "to": "+15550002222",
                    "message": "${last_output}",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "postgres_sql":
            return [
                {
                    "label": "Postgres Query",
                    "endpoint": "postgresql://user:password@localhost:5432/postgres",
                    "payload": "select now();",
                    "timeout_sec": "60.0",
                }
            ]
        if key == "sqlite_sql":
            return [
                {
                    "label": "SQLite Query",
                    "path": "/tmp/6x.db",
                    "payload": "create table if not exists logs(message text);",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "mysql_sql":
            return [
                {
                    "label": "MySQL Query",
                    "endpoint": "mysql://user:password@localhost:3306/mysql",
                    "payload": "select now();",
                    "timeout_sec": "60.0",
                }
            ]
        if key == "redis_command":
            return [
                {
                    "label": "Redis Ping",
                    "endpoint": "redis://localhost:6379/0",
                    "command": "PING",
                    "timeout_sec": "20.0",
                }
            ]
        if key == "s3_cli":
            return [
                {
                    "label": "List Buckets",
                    "command": "s3 ls",
                    "timeout_sec": "45.0",
                }
            ]
        if key == "google_apps_script":
            return [
                {
                    "label": "Script JSON Push",
                    "endpoint": "https://script.google.com/macros/s/REPLACE_ME/exec",
                    "payload": "{\"workflow\":\"${workflow_name}\",\"output\":\"${last_output}\"}",
                    "timeout_sec": "30.0",
                }
            ]
        if key == "file_append":
            return [
                {"label": "Append Result Log", "path": "/tmp/6x-workflow.log", "message": "${last_output}"}
            ]
        if key == "shell_command":
            return [
                {"label": "Echo Output", "command": "echo \"$INPUT_CONTEXT\"", "timeout_sec": "60.0"}
            ]
        if key == "approval_gate":
            return [
                {"label": "Manual Review Gate", "message": "Approve this step before continuing."}
            ]
        return []

    def refresh_action_presets(self, integration: str):
        self.action_preset_specs = self.action_preset_definitions(integration)
        if not self.action_preset_specs:
            self.rebuild_action_preset_dropdown(["No presets"])
            self.action_preset_apply_button.set_sensitive(False)
            return

        labels = [item.get("label", "Preset") for item in self.action_preset_specs]
        self.rebuild_action_preset_dropdown(labels)
        self.action_preset_apply_button.set_sensitive(True)

    def on_apply_action_preset(self, _button):
        if not self.action_preset_specs:
            return
        index = self.action_preset_dropdown.get_selected()
        if index < 0 or index >= len(self.action_preset_specs):
            return
        preset = self.action_preset_specs[index]

        endpoint = preset.get("endpoint", "")
        message = preset.get("message", "")
        payload = preset.get("payload", "")
        api_key = preset.get("api_key", "")
        location = preset.get("location", "")
        units = preset.get("units", "")
        path = preset.get("path", "")
        command = preset.get("command", "")
        to_value = str(preset.get("to", "")).strip()
        from_value = str(preset.get("from", "")).strip()
        subject_value = str(preset.get("subject", "")).strip()
        chat_id_value = str(preset.get("chat_id", "")).strip()
        account_sid_value = str(preset.get("account_sid", "")).strip()
        auth_token_value = str(preset.get("auth_token", "")).strip()
        domain_value = str(preset.get("domain", "")).strip()
        method = str(preset.get("method", "")).strip()
        headers = str(preset.get("headers", "")).strip()
        timeout_raw = preset.get("timeout_sec", "")

        if endpoint:
            self.action_endpoint_entry.set_text(endpoint)
        if message:
            self.action_message_entry.set_text(message)
        if payload:
            self.set_action_payload_text(payload)
        if api_key:
            self.action_api_key_entry.set_text(api_key)
        if location:
            self.action_location_entry.set_text(location)
        if units:
            self.action_units_dropdown.set_selected(self.action_units_index(units))
        if path:
            self.action_path_entry.set_text(path)
        if command:
            self.action_command_entry.set_text(command)
        if to_value:
            self.action_to_entry.set_text(to_value)
        elif self.action_to_row.get_visible():
            self.action_to_entry.set_text("")
        if from_value:
            self.action_from_entry.set_text(from_value)
        elif self.action_from_row.get_visible():
            self.action_from_entry.set_text("")
        if subject_value:
            self.action_subject_entry.set_text(subject_value)
        elif self.action_subject_row.get_visible():
            self.action_subject_entry.set_text("")
        if chat_id_value:
            self.action_chat_id_entry.set_text(chat_id_value)
        elif self.action_chat_id_row.get_visible():
            self.action_chat_id_entry.set_text("")
        if account_sid_value:
            self.action_account_sid_entry.set_text(account_sid_value)
        elif self.action_account_sid_row.get_visible():
            self.action_account_sid_entry.set_text("")
        if auth_token_value:
            self.action_auth_token_entry.set_text(auth_token_value)
        elif self.action_auth_token_row.get_visible():
            self.action_auth_token_entry.set_text("")
        if domain_value:
            self.action_domain_entry.set_text(domain_value)
        elif self.action_domain_row.get_visible():
            self.action_domain_entry.set_text("")
        if method:
            self.action_method_dropdown.set_selected(self.action_method_index(method))
        elif self.action_method_row.get_visible():
            self.action_method_dropdown.set_selected(self.action_method_index("POST"))
        if headers:
            self.action_headers_entry.set_text(headers)
        elif self.action_headers_row.get_visible():
            self.action_headers_entry.set_text("")
        if timeout_raw:
            self.action_timeout_spin.set_value(max(0.0, self.parse_float(timeout_raw, 0.0)))

        preset_name = preset.get("label", "preset")
        self.update_action_requirements_status()
        self.set_status(f"Applied action preset: {preset_name}.")

    def on_action_integration_changed(self, *_args):
        if self.loading_action_controls:
            return
        previous_integration = str(self.last_action_group_integration or "").strip().lower()
        integration = self.selected_action_integration()
        self.update_action_integration_field_visibility()
        template_key = self.infer_action_template_key({"integration": integration})
        self.action_template_dropdown.set_selected(self.action_template_index(template_key))
        self.update_action_template_hint()
        self.apply_action_smart_defaults(integration, force=False)
        selected_node = self.get_selected_node()
        if selected_node and self.node_type_key(selected_node.node_type) in {"action", "template"}:
            if self.should_auto_apply_execution_defaults_on_integration_change(
                selected_node,
                previous_integration,
            ):
                self.apply_node_execution_defaults_for_context(
                    selected_node.node_type,
                    integration,
                    announce=False,
                )
            else:
                self.update_node_execution_hint(selected_node.node_type, integration)
        self.sync_action_category_state(
            self.infer_action_category(template_key, integration)
        )

    def on_action_quick_clicked(
        self,
        _button: Gtk.Button,
        integration_key: str,
        template_key: str,
    ):
        self.action_integration_dropdown.set_selected(
            self.action_integration_index(integration_key)
        )
        if template_key in self.action_template_keys:
            self.apply_action_template(template_key, announce=False)
        else:
            self.update_action_integration_field_visibility()
        self.sync_action_category_state(
            self.infer_action_category(template_key, integration_key)
        )
        self.set_status(f"Action quick setup: {integration_key}.")

    def infer_action_category(self, template_key: str, integration: str) -> str:
        template = str(template_key).strip().lower()
        target = str(integration).strip().lower()
        if target in {
            "slack_webhook",
            "discord_webhook",
            "teams_webhook",
        }:
            return "notify"
        if target in {
            "gmail_send",
            "telegram_bot",
            "twilio_sms",
            "resend_email",
            "mailgun_email",
            "outlook_graph",
        }:
            return "message"
        if target in {
            "http_post",
            "http_request",
            "openweather_current",
            "google_apps_script",
            "google_sheets",
            "google_calendar_api",
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "openrouter_api",
            "linear_api",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "openrouter_api",
            "postgres_sql",
            "mysql_sql",
            "sqlite_sql",
            "redis_command",
            "s3_cli",
        }:
            return "data"
        if target in {
            "shell_command",
            "file_append",
        }:
            return "system"
        if template in {"approval_gate"}:
            return "control"
        if target in {"approval_gate"}:
            return "control"
        if template in {"shell_command", "file_append"}:
            return "system"
        if template in {"notify_slack", "notify_discord", "notify_teams"}:
            return "notify"
        if template in {"message_email", "message_sms", "message_telegram", "outlook_message"}:
            return "message"
        if template in {
            "http_request",
            "webhook_post",
            "weather_lookup",
            "calendar_event",
            "google_calendar_event",
            "jira_issue_lookup",
            "asana_task",
            "clickup_task",
            "trello_board",
            "monday_query",
            "zendesk_ticket",
            "salesforce_query",
            "pipedrive_deal",
            "gitlab_rest",
        }:
            return "data"
        return "notify"

    def set_entry_if_missing(self, entry: Gtk.Entry, value: str, force: bool = False):
        if force or not entry.get_text().strip():
            entry.set_text(str(value).strip())

    def set_payload_if_missing(self, value: str, force: bool = False):
        if force or not self.get_action_payload_text().strip():
            self.set_action_payload_text(str(value).strip())

    def apply_saved_integration_defaults(self, integration: str, force: bool = False):
        key = str(integration).strip().lower()
        settings = self.settings_store.load_settings()
        mapping = {
            "slack_webhook": {
                "endpoint": "slack_webhook_url",
            },
            "discord_webhook": {
                "endpoint": "discord_webhook_url",
            },
            "teams_webhook": {
                "endpoint": "teams_webhook_url",
            },
            "telegram_bot": {
                "api_key": "telegram_bot_token",
                "chat_id": "telegram_default_chat_id",
            },
            "openweather_current": {
                "api_key": "openweather_api_key",
                "location": "openweather_default_location",
            },
            "google_apps_script": {
                "endpoint": "google_apps_script_url",
            },
            "google_sheets": {
                "api_key": "google_sheets_api_key",
            },
            "google_calendar_api": {
                "api_key": "google_calendar_api_key",
                "endpoint": "google_calendar_api_url",
            },
            "outlook_graph": {
                "api_key": "outlook_api_key",
                "endpoint": "outlook_api_url",
            },
            "gmail_send": {
                "api_key": "gmail_api_key",
                "from": "gmail_from_address",
            },
            "notion_api": {
                "api_key": "notion_api_key",
                "endpoint": "notion_api_url",
            },
            "airtable_api": {
                "api_key": "airtable_api_key",
                "endpoint": "airtable_api_url",
            },
            "hubspot_api": {
                "api_key": "hubspot_api_key",
                "endpoint": "hubspot_api_url",
            },
            "stripe_api": {
                "api_key": "stripe_api_key",
                "endpoint": "stripe_api_url",
            },
            "github_rest": {
                "api_key": "github_api_key",
                "endpoint": "github_api_url",
            },
            "jira_api": {
                "api_key": "jira_api_key",
                "endpoint": "jira_api_url",
            },
            "asana_api": {
                "api_key": "asana_api_key",
                "endpoint": "asana_api_url",
            },
            "clickup_api": {
                "api_key": "clickup_api_key",
                "endpoint": "clickup_api_url",
            },
            "trello_api": {
                "api_key": "trello_api_key",
                "endpoint": "trello_api_url",
            },
            "monday_api": {
                "api_key": "monday_api_key",
                "endpoint": "monday_api_url",
            },
            "zendesk_api": {
                "api_key": "zendesk_api_key",
                "endpoint": "zendesk_api_url",
            },
            "pipedrive_api": {
                "api_key": "pipedrive_api_key",
                "endpoint": "pipedrive_api_url",
            },
            "salesforce_api": {
                "api_key": "salesforce_api_key",
                "endpoint": "salesforce_api_url",
            },
            "gitlab_api": {
                "api_key": "gitlab_api_key",
                "endpoint": "gitlab_api_url",
            },
            "google_drive_api": {
                "api_key": "google_drive_api_key",
                "endpoint": "google_drive_api_url",
            },
            "dropbox_api": {
                "api_key": "dropbox_api_key",
                "endpoint": "dropbox_api_url",
            },
            "shopify_api": {
                "api_key": "shopify_api_key",
                "endpoint": "shopify_api_url",
            },
            "webflow_api": {
                "api_key": "webflow_api_key",
                "endpoint": "webflow_api_url",
            },
            "supabase_api": {
                "api_key": "supabase_api_key",
                "endpoint": "supabase_api_url",
            },
            "openrouter_api": {
                "api_key": "openrouter_api_key",
                "endpoint": "openrouter_api_url",
            },
            "twilio_sms": {
                "account_sid": "twilio_account_sid",
                "auth_token": "twilio_auth_token",
                "from": "twilio_from_number",
            },
            "resend_email": {
                "api_key": "resend_api_key",
                "from": "resend_from_address",
            },
            "mailgun_email": {
                "api_key": "mailgun_api_key",
                "domain": "mailgun_domain",
                "from": "mailgun_from_address",
            },
            "postgres_sql": {
                "endpoint": "postgres_connection_url",
            },
            "mysql_sql": {
                "endpoint": "mysql_connection_url",
            },
            "sqlite_sql": {
                "location": "sqlite_default_path",
            },
        }
        defaults = mapping.get(key, {})
        if not defaults:
            return
        endpoint_value = str(settings.get(defaults.get("endpoint", ""), "")).strip()
        if endpoint_value:
            self.set_entry_if_missing(self.action_endpoint_entry, endpoint_value, force=force)
        api_key_value = str(settings.get(defaults.get("api_key", ""), "")).strip()
        if api_key_value:
            self.set_entry_if_missing(self.action_api_key_entry, api_key_value, force=force)
        chat_value = str(settings.get(defaults.get("chat_id", ""), "")).strip()
        if chat_value:
            self.set_entry_if_missing(self.action_chat_id_entry, chat_value, force=force)
        from_value = str(settings.get(defaults.get("from", ""), "")).strip()
        if from_value:
            self.set_entry_if_missing(self.action_from_entry, from_value, force=force)
        domain_value = str(settings.get(defaults.get("domain", ""), "")).strip()
        if domain_value:
            self.set_entry_if_missing(self.action_domain_entry, domain_value, force=force)
        account_sid_value = str(settings.get(defaults.get("account_sid", ""), "")).strip()
        if account_sid_value:
            self.set_entry_if_missing(self.action_account_sid_entry, account_sid_value, force=force)
        auth_token_value = str(settings.get(defaults.get("auth_token", ""), "")).strip()
        if auth_token_value:
            self.set_entry_if_missing(self.action_auth_token_entry, auth_token_value, force=force)
        location_value = str(settings.get(defaults.get("location", ""), "")).strip()
        if location_value:
            if key == "sqlite_sql":
                self.set_entry_if_missing(self.action_path_entry, location_value, force=force)
            else:
                self.set_entry_if_missing(self.action_location_entry, location_value, force=force)

    def apply_action_smart_defaults(self, integration: str, force: bool = False):
        key = str(integration).strip().lower()
        self.apply_saved_integration_defaults(key, force=force)
        if key == "slack_webhook":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://hooks.slack.com/services/REPLACE/REPLACE/REPLACE",
                force=force,
            )
            self.set_entry_if_missing(
                self.action_message_entry,
                "Workflow update: ${last_output}",
                force=force,
            )
        elif key == "discord_webhook":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://discord.com/api/webhooks/REPLACE/REPLACE",
                force=force,
            )
            self.set_entry_if_missing(
                self.action_message_entry,
                "Workflow update: ${last_output}",
                force=force,
            )
        elif key == "teams_webhook":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://outlook.office.com/webhook/REPLACE/IncomingWebhook/REPLACE/REPLACE",
                force=force,
            )
            self.set_entry_if_missing(
                self.action_message_entry,
                "Workflow update: ${last_output}",
                force=force,
            )
        elif key == "http_request":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://api.example.com/v1/events",
                force=force,
            )
            if force or not self.action_headers_entry.get_text().strip():
                self.action_headers_entry.set_text('{"Content-Type":"application/json"}')
            self.set_payload_if_missing('{"event":"workflow_update","data":"${last_output}"}', force=force)
            self.action_method_dropdown.set_selected(self.action_method_index("POST"))
        elif key == "http_post":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://api.example.com/v1/events",
                force=force,
            )
            self.set_payload_if_missing('{"event":"workflow_update","data":"${last_output}"}', force=force)
            self.action_method_dropdown.set_selected(self.action_method_index("POST"))
        elif key == "jira_api":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://your-domain.atlassian.net/rest/api/3/myself",
                force=force,
            )
            self.action_method_dropdown.set_selected(self.action_method_index("GET"))
        elif key == "asana_api":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://app.asana.com/api/1.0/users/me",
                force=force,
            )
            self.action_method_dropdown.set_selected(self.action_method_index("GET"))
        elif key == "clickup_api":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://api.clickup.com/api/v2/user",
                force=force,
            )
            self.action_method_dropdown.set_selected(self.action_method_index("GET"))
        elif key == "trello_api":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://api.trello.com/1/members/me",
                force=force,
            )
            self.action_method_dropdown.set_selected(self.action_method_index("GET"))
        elif key == "monday_api":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://api.monday.com/v2",
                force=force,
            )
            self.action_method_dropdown.set_selected(self.action_method_index("POST"))
            self.set_payload_if_missing('{"query":"{ me { id name email } }"}', force=force)
        elif key == "zendesk_api":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://your-domain.zendesk.com/api/v2/users/me.json",
                force=force,
            )
            self.action_method_dropdown.set_selected(self.action_method_index("GET"))
        elif key == "pipedrive_api":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://api.pipedrive.com/v1/users/me",
                force=force,
            )
            self.action_method_dropdown.set_selected(self.action_method_index("GET"))
        elif key == "salesforce_api":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://your-instance.my.salesforce.com/services/data/v58.0/limits",
                force=force,
            )
            self.action_method_dropdown.set_selected(self.action_method_index("GET"))
        elif key == "gitlab_api":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://gitlab.com/api/v4/user",
                force=force,
            )
            self.action_method_dropdown.set_selected(self.action_method_index("GET"))
        elif key == "telegram_bot":
            self.set_entry_if_missing(self.action_chat_id_entry, "REPLACE_CHAT_ID", force=force)
            self.set_entry_if_missing(
                self.action_message_entry,
                "Workflow update: ${last_output}",
                force=force,
            )
        elif key in {"gmail_send", "resend_email", "mailgun_email"}:
            self.set_entry_if_missing(self.action_to_entry, "you@example.com", force=force)
            self.set_entry_if_missing(self.action_from_entry, "alerts@yourdomain.com", force=force)
            self.set_entry_if_missing(self.action_subject_entry, "Workflow Update", force=force)
            self.set_entry_if_missing(
                self.action_message_entry,
                "Workflow update: ${last_output}",
                force=force,
            )
            if key == "mailgun_email":
                self.set_entry_if_missing(self.action_domain_entry, "mg.yourdomain.com", force=force)
        elif key == "twilio_sms":
            self.set_entry_if_missing(self.action_to_entry, "+15550002222", force=force)
            self.set_entry_if_missing(self.action_from_entry, "+15550001111", force=force)
            self.set_entry_if_missing(
                self.action_message_entry,
                "Workflow update: ${last_output}",
                force=force,
            )
        elif key == "google_apps_script":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://script.google.com/macros/s/REPLACE/exec",
                force=force,
            )
            self.set_entry_if_missing(self.action_message_entry, "Automation Event", force=force)
            self.set_payload_if_missing(
                '{"event":"workflow_update","summary":"${last_output}"}',
                force=force,
            )
        elif key == "google_sheets":
            self.set_payload_if_missing(
                '{"spreadsheet_id":"REPLACE_ID","range":"Sheet1!A:B","values":[["${workflow_name}","${last_output}"]]}',
                force=force,
            )
        elif key == "openweather_current":
            self.set_entry_if_missing(self.action_location_entry, "Austin,US", force=force)
            self.action_units_dropdown.set_selected(self.action_units_index("metric"))
        elif key == "google_calendar_api":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://www.googleapis.com/calendar/v3/users/me/calendarList",
                force=force,
            )
            self.action_method_dropdown.set_selected(self.action_method_index("GET"))
        elif key == "outlook_graph":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://graph.microsoft.com/v1.0/me/messages?$top=5",
                force=force,
            )
            self.action_method_dropdown.set_selected(self.action_method_index("GET"))
        elif key == "notion_api":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://api.notion.com/v1/pages",
                force=force,
            )
            self.action_method_dropdown.set_selected(self.action_method_index("POST"))
            self.set_payload_if_missing(
                '{"parent":{"database_id":"REPLACE_DB"},"properties":{"Name":{"title":[{"text":{"content":"Workflow Update"}}]}}}',
                force=force,
            )
        elif key == "airtable_api":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://api.airtable.com/v0/REPLACE_BASE/REPLACE_TABLE",
                force=force,
            )
            self.action_method_dropdown.set_selected(self.action_method_index("POST"))
            self.set_payload_if_missing(
                '{"records":[{"fields":{"Name":"${workflow_name}","Output":"${last_output}"}}]}',
                force=force,
            )
        elif key == "github_rest":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://api.github.com/user",
                force=force,
            )
            self.action_method_dropdown.set_selected(self.action_method_index("GET"))
            if force or not self.action_headers_entry.get_text().strip():
                self.action_headers_entry.set_text('{"Accept":"application/vnd.github+json"}')
        elif key == "hubspot_api":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://api.hubapi.com/crm/v3/objects/contacts?limit=5",
                force=force,
            )
            self.action_method_dropdown.set_selected(self.action_method_index("GET"))
        elif key == "stripe_api":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "https://api.stripe.com/v1/balance",
                force=force,
            )
            self.action_method_dropdown.set_selected(self.action_method_index("GET"))
        elif key == "linear_api":
            self.set_payload_if_missing(
                '{"query":"{ viewer { id name } }"}',
                force=force,
            )
        elif key == "shell_command":
            self.set_entry_if_missing(
                self.action_command_entry,
                "echo \"${last_output}\"",
                force=force,
            )
        elif key == "postgres_sql":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "postgresql://user:password@localhost:5432/postgres",
                force=force,
            )
            self.set_payload_if_missing(
                "select now() as current_time;",
                force=force,
            )
        elif key == "mysql_sql":
            self.set_entry_if_missing(
                self.action_endpoint_entry,
                "mysql://user:password@localhost:3306/mysql",
                force=force,
            )
            self.set_payload_if_missing(
                "select now() as current_time;",
                force=force,
            )
        elif key == "sqlite_sql":
            self.set_entry_if_missing(
                self.action_path_entry,
                "/tmp/6x_protocol.db",
                force=force,
            )
            self.set_payload_if_missing(
                "select datetime('now') as current_time;",
                force=force,
            )
        elif key == "redis_command":
            self.set_entry_if_missing(
                self.action_command_entry,
                "ping",
                force=force,
            )
        elif key == "s3_cli":
            self.set_entry_if_missing(
                self.action_command_entry,
                "s3 ls",
                force=force,
            )
        elif key == "file_append":
            self.set_entry_if_missing(self.action_path_entry, "/tmp/workflow.log", force=force)
            self.set_entry_if_missing(
                self.action_message_entry,
                "${last_output}",
                force=force,
            )
        elif key == "approval_gate":
            self.set_entry_if_missing(
                self.action_message_entry,
                "Approve this step before continuing.",
                force=force,
            )

    def integration_requirement_summary(self, integration: str) -> str:
        key = str(integration).strip().lower()
        if key in {"slack_webhook", "discord_webhook", "teams_webhook"}:
            return "Required: webhook URL, message. Optional: username, timeout."
        if key == "telegram_bot":
            return "Required: bot token (API key), chat id. Optional: endpoint override, timeout."
        if key in {"gmail_send", "resend_email", "mailgun_email"}:
            return "Required: API key/token, to, from, subject, message."
        if key == "twilio_sms":
            return "Required: account SID, auth token, from, to, message."
        if key == "google_sheets":
            return "Required: OAuth token, spreadsheet id, range, payload values."
        if key in {
            "google_calendar_api",
            "outlook_graph",
            "github_rest",
            "hubspot_api",
            "stripe_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "openrouter_api",
        }:
            return "Required: API key/token and endpoint URL. Optional: method, headers, payload."
        if key in {"notion_api", "airtable_api", "linear_api", "monday_api"}:
            return "Required: API key/token plus JSON payload for request body/query."
        if key in {"http_request", "http_post"}:
            return "Required: endpoint URL. Optional: headers JSON, payload JSON, timeout."
        if key in {"postgres_sql", "mysql_sql"}:
            return "Required: connection URL and SQL payload."
        if key == "redis_command":
            return "Required: command. Optional: redis:// connection URL and timeout."
        if key in {"shell_command", "s3_cli"}:
            return "Required: command. Optional: timeout."
        if key in {"file_append", "sqlite_sql"}:
            return "Required: path and content/sql payload."
        if key == "openweather_current":
            return "Required: API key and location. Optional: units, timeout."
        if key == "approval_gate":
            return "Required: approval message. Optional: timeout (0 = wait indefinitely)."
        return "Configure integration-specific fields, then click Apply Node Changes."

    def node_execution_profile(self, node_type: str, integration: str = "") -> dict[str, float]:
        node_key = self.node_type_key(node_type)
        target = str(integration).strip().lower()
        if node_key == "trigger":
            return {"retry_max": 0.0, "retry_backoff_ms": 0.0, "timeout_sec": 15.0}
        if node_key == "condition":
            return {"retry_max": 0.0, "retry_backoff_ms": 0.0, "timeout_sec": 8.0}
        if node_key == "ai":
            return {"retry_max": 1.0, "retry_backoff_ms": 300.0, "timeout_sec": 120.0}
        if node_key in {"action", "template"}:
            if target == "approval_gate":
                return {"retry_max": 0.0, "retry_backoff_ms": 0.0, "timeout_sec": 0.0}
            if target in self.ACTION_FAST_INTEGRATIONS:
                return {"retry_max": 1.0, "retry_backoff_ms": 200.0, "timeout_sec": 25.0}
            if target in self.ACTION_HEAVY_INTEGRATIONS:
                return {"retry_max": 1.0, "retry_backoff_ms": 400.0, "timeout_sec": 90.0}
            if target in self.ACTION_STANDARD_INTEGRATIONS:
                return {"retry_max": 1.0, "retry_backoff_ms": 250.0, "timeout_sec": 45.0}
            return {"retry_max": 1.0, "retry_backoff_ms": 250.0, "timeout_sec": 45.0}
        return {"retry_max": 1.0, "retry_backoff_ms": 250.0, "timeout_sec": 60.0}

    def node_has_explicit_execution_overrides(self, config: dict | None) -> bool:
        if not isinstance(config, dict):
            return False
        for key in ("retry_max", "retry_backoff_ms", "timeout_sec"):
            if str(config.get(key, "")).strip():
                return True
        return False

    def execution_controls_match_profile(self, profile: dict[str, float]) -> bool:
        retry_value = self.node_retry_spin.get_value_as_int()
        backoff_value = self.node_backoff_spin.get_value_as_int()
        timeout_value = round(self.node_timeout_spin.get_value(), 1)
        return bool(
            retry_value == int(profile.get("retry_max", 0))
            and backoff_value == int(profile.get("retry_backoff_ms", 0))
            and abs(timeout_value - float(profile.get("timeout_sec", 0.0))) < 0.05
        )

    def should_auto_apply_execution_defaults_on_integration_change(
        self,
        node: CanvasNode,
        previous_integration: str,
    ) -> bool:
        if self.node_has_explicit_execution_overrides(node.config):
            return False
        # Keep user-tuned live controls when they no longer match the previous context.
        prev_profile = self.node_execution_profile(node.node_type, previous_integration)
        return self.execution_controls_match_profile(prev_profile)

    def suggested_node_execution_preset(self, node_type: str, integration: str = "") -> str:
        node_key = self.node_type_key(node_type)
        target = str(integration).strip().lower()
        if node_key in {"trigger", "condition"}:
            return "fast"
        if node_key == "ai":
            return "heavy"
        if node_key in {"action", "template"}:
            if target == "approval_gate":
                return "approval"
            if target in self.ACTION_FAST_INTEGRATIONS:
                return "fast"
            if target in self.ACTION_HEAVY_INTEGRATIONS:
                return "heavy"
            return "standard"
        return "standard"

    def node_execution_preset_profile(
        self,
        preset_key: str,
        node_type: str,
        integration: str = "",
    ) -> dict[str, float]:
        node_key = self.node_type_key(node_type)
        normalized = str(preset_key).strip().lower()
        target = str(integration).strip().lower()
        recommended = self.node_execution_profile(node_type, integration)

        if normalized == "approval":
            return {"retry_max": 0.0, "retry_backoff_ms": 0.0, "timeout_sec": 0.0}

        if normalized == "fast":
            if node_key == "trigger":
                return {"retry_max": 0.0, "retry_backoff_ms": 0.0, "timeout_sec": 12.0}
            if node_key == "condition":
                return {"retry_max": 0.0, "retry_backoff_ms": 0.0, "timeout_sec": 6.0}
            if node_key == "ai":
                return {"retry_max": 1.0, "retry_backoff_ms": 240.0, "timeout_sec": 90.0}
            if node_key in {"action", "template"}:
                if target in self.ACTION_FAST_INTEGRATIONS:
                    return dict(recommended)
                return {"retry_max": 1.0, "retry_backoff_ms": 180.0, "timeout_sec": 28.0}
            return dict(recommended)

        if normalized == "heavy":
            if node_key == "trigger":
                return {"retry_max": 0.0, "retry_backoff_ms": 0.0, "timeout_sec": 24.0}
            if node_key == "condition":
                return {"retry_max": 1.0, "retry_backoff_ms": 120.0, "timeout_sec": 20.0}
            if node_key == "ai":
                return {"retry_max": 2.0, "retry_backoff_ms": 420.0, "timeout_sec": 180.0}
            if node_key in {"action", "template"}:
                if target in self.ACTION_HEAVY_INTEGRATIONS:
                    return dict(recommended)
                return {"retry_max": 2.0, "retry_backoff_ms": 520.0, "timeout_sec": 120.0}
            return dict(recommended)

        # Standard follows the recommended profile for current node context.
        return dict(recommended)

    def current_node_execution_preset(self, node_type: str, integration: str = "") -> str | None:
        retry_value = self.node_retry_spin.get_value_as_int()
        backoff_value = self.node_backoff_spin.get_value_as_int()
        timeout_value = round(self.node_timeout_spin.get_value(), 1)

        for preset_key in self.NODE_EXECUTION_PRESET_KEYS:
            profile = self.node_execution_preset_profile(preset_key, node_type, integration)
            if (
                retry_value == int(profile.get("retry_max", 0))
                and backoff_value == int(profile.get("retry_backoff_ms", 0))
                and abs(timeout_value - float(profile.get("timeout_sec", 0.0))) < 0.05
            ):
                return preset_key
        return None

    def sync_node_execution_preset_buttons(self, node_type: str, integration: str = ""):
        active_key = self.current_node_execution_preset(node_type, integration)
        self.loading_node_execution_preset = True
        for preset_key, button in self.node_execution_preset_buttons.items():
            button.set_active(active_key == preset_key)
        self.loading_node_execution_preset = False

    def on_node_execution_preset_toggled(self, button: Gtk.ToggleButton, preset_key: str):
        if self.loading_node_execution_preset:
            return
        if not button.get_active():
            if any(item.get_active() for item in self.node_execution_preset_buttons.values()):
                return
            node = self.get_selected_node()
            if node:
                integration = (
                    self.selected_action_integration()
                    if self.node_type_key(node.node_type) in {"action", "template"}
                    else ""
                )
                self.update_node_execution_hint(node.node_type, integration)
            return

        node = self.get_selected_node()
        if not node:
            return
        integration = (
            self.selected_action_integration()
            if self.node_type_key(node.node_type) in {"action", "template"}
            else ""
        )
        profile = self.node_execution_preset_profile(preset_key, node.node_type, integration)
        self.loading_node_execution_preset = True
        self.node_retry_spin.set_value(float(profile.get("retry_max", 0.0)))
        self.node_backoff_spin.set_value(float(profile.get("retry_backoff_ms", 0.0)))
        self.node_timeout_spin.set_value(float(profile.get("timeout_sec", 0.0)))
        self.loading_node_execution_preset = False
        self.sync_node_execution_preset_buttons(node.node_type, integration)
        self.update_node_execution_hint(node.node_type, integration)
        self.set_status(f"Node execution preset applied: {preset_key.title()}.")

    def apply_node_execution_defaults_for_context(
        self,
        node_type: str,
        integration: str = "",
        *,
        announce: bool = True,
    ):
        defaults = self.node_execution_profile(node_type, integration)
        self.loading_node_execution_preset = True
        self.node_retry_spin.set_value(float(defaults.get("retry_max", 1.0)))
        self.node_backoff_spin.set_value(float(defaults.get("retry_backoff_ms", 250.0)))
        self.node_timeout_spin.set_value(float(defaults.get("timeout_sec", 60.0)))
        self.loading_node_execution_preset = False
        self.sync_node_execution_preset_buttons(node_type, integration)
        self.update_node_execution_hint(node_type, integration)
        if announce:
            self.set_status("Recommended node execution defaults applied.")

    def load_node_execution_controls(self, merged_config: dict[str, str], node_type: str):
        integration = str(merged_config.get("integration", "")).strip().lower()
        defaults = self.node_execution_profile(node_type, integration)
        retry_max = self.parse_int(merged_config.get("retry_max", ""), int(defaults["retry_max"]))
        backoff_ms = self.parse_int(
            merged_config.get("retry_backoff_ms", ""),
            int(defaults["retry_backoff_ms"]),
        )
        timeout_sec = self.parse_float(
            merged_config.get("timeout_sec", ""),
            float(defaults["timeout_sec"]),
        )
        self.loading_node_execution_preset = True
        self.node_retry_spin.set_value(float(max(0, retry_max)))
        self.node_backoff_spin.set_value(float(max(0, backoff_ms)))
        self.node_timeout_spin.set_value(float(max(0.0, timeout_sec)))
        self.loading_node_execution_preset = False
        self.sync_node_execution_preset_buttons(node_type, integration)
        self.update_node_execution_hint(node_type, integration)

    def update_node_execution_hint(self, node_type: str, integration: str = ""):
        defaults = self.node_execution_profile(node_type, integration)
        suggested_preset = self.suggested_node_execution_preset(node_type, integration)
        active_preset = self.current_node_execution_preset(node_type, integration)
        retry_value = self.node_retry_spin.get_value_as_int()
        backoff_value = self.node_backoff_spin.get_value_as_int()
        timeout_value = round(self.node_timeout_spin.get_value(), 1)
        mode = "Custom" if (
            retry_value != int(defaults["retry_max"])
            or backoff_value != int(defaults["retry_backoff_ms"])
            or abs(timeout_value - float(defaults["timeout_sec"])) > 0.05
        ) else "Recommended"
        if active_preset:
            mode = f"Preset {active_preset.title()}"
        node_label = self.node_type_chip_text(node_type)
        target = str(integration).strip().lower()
        integration_label = f" • {target}" if target else ""
        self.node_execution_hint_label.set_text(
            f"{mode} profile for {node_label}{integration_label} "
            f"(recommended: {suggested_preset.title()}): retry {retry_value}, "
            f"backoff {backoff_value}ms, timeout {timeout_value:.1f}s."
        )
        self.sync_node_execution_preset_buttons(node_type, integration)

    def on_node_execution_defaults_clicked(self, _button):
        node = self.get_selected_node()
        if not node:
            return
        integration = ""
        if self.node_type_key(node.node_type) in {"action", "template"}:
            integration = self.selected_action_integration()
        self.apply_node_execution_defaults_for_context(node.node_type, integration, announce=True)

    def on_node_execution_value_changed(self, _spin: Gtk.SpinButton):
        if self.loading_node_execution_preset:
            return
        node = self.get_selected_node()
        if not node:
            return
        integration = ""
        if self.node_type_key(node.node_type) in {"action", "template"}:
            integration = self.selected_action_integration()
        self.update_node_execution_hint(node.node_type, integration)

    def update_action_group_visibility(self, integration: str):
        rows_by_group: list[tuple[Gtk.Expander, list[Gtk.Widget]]] = [
            (self.action_routing_group, self.action_routing_rows),
            (self.action_delivery_group, self.action_delivery_rows),
            (self.action_payload_group, self.action_payload_rows),
            (self.action_auth_group, self.action_auth_rows),
        ]

        for group, rows in rows_by_group:
            group.set_visible(any(row.get_visible() for row in rows))

        current = str(integration).strip().lower()
        if current != self.last_action_group_integration:
            self.action_routing_group.set_expanded(True)
            self.action_delivery_group.set_expanded(
                current
                in {
                    "slack_webhook",
                    "discord_webhook",
                    "teams_webhook",
                    "telegram_bot",
                    "gmail_send",
                    "twilio_sms",
                    "resend_email",
                    "mailgun_email",
                    "approval_gate",
                    "file_append",
                    "google_apps_script",
                    "outlook_graph",
                }
            )
            self.action_payload_group.set_expanded(
                current
                in {
                    "http_post",
                    "http_request",
                    "google_apps_script",
                    "google_sheets",
                    "google_calendar_api",
                    "notion_api",
                    "airtable_api",
                    "hubspot_api",
                    "stripe_api",
                    "github_rest",
                    "gitlab_api",
                    "google_drive_api",
                    "dropbox_api",
                    "shopify_api",
                    "webflow_api",
                    "supabase_api",
                    "openrouter_api",
                    "linear_api",
                    "jira_api",
                    "asana_api",
                    "clickup_api",
                    "trello_api",
                    "monday_api",
                    "zendesk_api",
                    "pipedrive_api",
                    "salesforce_api",
                    "postgres_sql",
                    "mysql_sql",
                    "sqlite_sql",
                    "shell_command",
                    "file_append",
                    "openweather_current",
                }
            )
            self.action_auth_group.set_expanded(
                current
                in {
                    "http_request",
                    "telegram_bot",
                    "gmail_send",
                    "google_sheets",
                    "google_calendar_api",
                    "notion_api",
                    "airtable_api",
                    "hubspot_api",
                    "stripe_api",
                    "github_rest",
                    "gitlab_api",
                    "google_drive_api",
                    "dropbox_api",
                    "shopify_api",
                    "webflow_api",
                    "supabase_api",
                    "openrouter_api",
                    "linear_api",
                    "jira_api",
                    "asana_api",
                    "clickup_api",
                    "trello_api",
                    "monday_api",
                    "zendesk_api",
                    "pipedrive_api",
                    "salesforce_api",
                    "twilio_sms",
                    "outlook_graph",
                    "resend_email",
                    "mailgun_email",
                }
            )
            self.last_action_group_integration = current

    def sync_action_category_state(self, active_key: str):
        desired = str(active_key).strip().lower()
        if desired not in self.action_category_buttons:
            desired = "notify"
        self.syncing_action_category = True
        for key, button in self.action_category_buttons.items():
            button.set_active(key == desired)
        self.syncing_action_category = False

    def on_action_category_toggled(self, button: Gtk.ToggleButton, category_key: str):
        if self.syncing_action_category:
            return
        if not button.get_active():
            if not any(item.get_active() for item in self.action_category_buttons.values()):
                self.sync_action_category_state(
                    self.infer_action_category(
                        str(self.selected_action_template().get("key", "")).strip().lower(),
                        self.selected_action_integration(),
                    )
                )
            return

        self.sync_action_category_state(category_key)
        template_map = {
            "notify": "notify_slack",
            "message": "message_telegram",
            "data": "http_request",
            "system": "shell_command",
            "control": "approval_gate",
        }
        template_key = template_map.get(category_key, "notify_slack")
        self.apply_action_template(template_key, announce=False)
        self.set_status(f"Action intent set to {category_key}.")

    def update_action_quick_button_state(self, integration: str):
        active_key = str(integration).strip().lower()
        for key, button in self.action_quick_buttons.items():
            if key == active_key:
                button.add_css_class("canvas-action-quick-active")
            else:
                button.remove_css_class("canvas-action-quick-active")

    def update_action_integration_field_visibility(self):
        integration = self.selected_action_integration()
        self.refresh_action_presets(integration)
        self.update_action_quick_button_state(integration)

        show_endpoint = integration in {
            "http_post",
            "http_request",
            "slack_webhook",
            "discord_webhook",
            "teams_webhook",
            "google_apps_script",
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "openrouter_api",
            "linear_api",
            "google_calendar_api",
            "outlook_graph",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
            "resend_email",
            "mailgun_email",
            "postgres_sql",
            "mysql_sql",
            "redis_command",
        }
        show_method = integration in {
            "http_request",
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "openrouter_api",
            "google_calendar_api",
            "outlook_graph",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
        }
        show_message = integration in {
            "slack_webhook",
            "discord_webhook",
            "teams_webhook",
            "approval_gate",
            "file_append",
            "telegram_bot",
            "gmail_send",
            "twilio_sms",
            "resend_email",
            "mailgun_email",
            "google_apps_script",
            "outlook_graph",
        }
        show_to = integration in {"gmail_send", "resend_email", "mailgun_email", "twilio_sms"}
        show_from = integration in {"gmail_send", "resend_email", "mailgun_email", "twilio_sms"}
        show_subject = integration in {"gmail_send", "resend_email", "mailgun_email"}
        show_chat_id = integration in {"telegram_bot"}
        show_account_sid = integration in {"twilio_sms"}
        show_auth_token = integration in {"twilio_sms"}
        show_domain = integration in {"mailgun_email"}
        show_username = integration in {"slack_webhook", "discord_webhook"}
        show_payload = integration in {
            "http_post",
            "http_request",
            "google_apps_script",
            "google_sheets",
            "google_calendar_api",
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "openrouter_api",
            "linear_api",
            "outlook_graph",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
            "postgres_sql",
            "mysql_sql",
            "sqlite_sql",
        }
        show_headers = integration in {
            "http_request",
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "openrouter_api",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
            "google_calendar_api",
            "outlook_graph",
        }
        show_api_key = integration in {
            "openweather_current",
            "http_request",
            "telegram_bot",
            "gmail_send",
            "google_sheets",
            "google_calendar_api",
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "openrouter_api",
            "linear_api",
            "outlook_graph",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
            "resend_email",
            "mailgun_email",
        }
        show_location = integration in {"openweather_current"}
        show_units = integration in {"openweather_current"}
        show_path = integration in {"file_append", "sqlite_sql"}
        show_command = integration in {"shell_command", "redis_command", "s3_cli"}
        show_timeout = integration in {
            "http_post",
            "http_request",
            "slack_webhook",
            "discord_webhook",
            "teams_webhook",
            "openweather_current",
            "google_apps_script",
            "shell_command",
            "telegram_bot",
            "gmail_send",
            "google_sheets",
            "google_calendar_api",
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "openrouter_api",
            "linear_api",
            "outlook_graph",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
            "twilio_sms",
            "resend_email",
            "mailgun_email",
            "postgres_sql",
            "mysql_sql",
            "sqlite_sql",
            "redis_command",
            "s3_cli",
        }

        self.action_endpoint_row.set_visible(show_endpoint)
        self.action_method_row.set_visible(show_method)
        self.action_message_row.set_visible(show_message)
        self.action_to_row.set_visible(show_to)
        self.action_from_row.set_visible(show_from)
        self.action_subject_row.set_visible(show_subject)
        self.action_chat_id_row.set_visible(show_chat_id)
        self.action_account_sid_row.set_visible(show_account_sid)
        self.action_auth_token_row.set_visible(show_auth_token)
        self.action_domain_row.set_visible(show_domain)
        self.action_username_row.set_visible(show_username)
        self.action_payload_row.set_visible(show_payload)
        self.action_headers_row.set_visible(show_headers)
        self.action_api_key_row.set_visible(show_api_key)
        self.action_location_row.set_visible(show_location)
        self.action_units_row.set_visible(show_units)
        self.action_path_row.set_visible(show_path)
        self.action_command_row.set_visible(show_command)
        self.action_timeout_row.set_visible(show_timeout)
        self.update_action_group_visibility(integration)
        self.action_requirements_label.set_text(self.integration_requirement_summary(integration))

        self.action_to_entry.set_placeholder_text("Recipient")
        self.action_from_entry.set_placeholder_text("Sender")
        self.action_subject_entry.set_placeholder_text("Message subject")
        self.action_chat_id_entry.set_placeholder_text("Telegram chat id")
        self.action_account_sid_entry.set_placeholder_text("Twilio Account SID")
        self.action_auth_token_entry.set_placeholder_text("Twilio Auth Token")
        self.action_domain_entry.set_placeholder_text("Mailgun domain  •  mg.yourdomain.com")
        self.action_api_key_label.set_text("API Key")
        self.action_api_key_entry.set_placeholder_text("API key")
        self.action_payload_label.set_text("Payload")
        self.action_headers_label.set_text("Headers")
        self.action_timeout_label.set_text("Timeout Seconds")
        self.action_method_label.set_text("HTTP Method")
        self.action_path_label.set_text("File Path")
        self.action_command_label.set_text("Shell Command")

        if integration == "http_post":
            self.action_endpoint_label.set_text("HTTP URL")
            self.action_endpoint_entry.set_placeholder_text("https://api.example.com/endpoint")
            self.action_payload_view.set_tooltip_text("JSON/body payload for POST request.")
            self.action_message_label.set_text("Message")
            self.action_payload_label.set_text("JSON Payload")
            self.action_timeout_label.set_text("Request Timeout Seconds")
        elif integration == "http_request":
            self.action_endpoint_label.set_text("Request URL")
            self.action_endpoint_entry.set_placeholder_text("https://api.example.com/endpoint")
            self.action_payload_view.set_tooltip_text("Request payload or JSON body.")
            self.action_message_label.set_text("Optional Message")
            self.action_payload_label.set_text("Request Payload")
            self.action_headers_label.set_text("Request Headers")
            self.action_timeout_label.set_text("Request Timeout Seconds")
        elif integration == "slack_webhook":
            self.action_endpoint_label.set_text("Slack Webhook URL")
            self.action_endpoint_entry.set_placeholder_text("https://hooks.slack.com/services/...")
            self.action_message_label.set_text("Slack Message")
        elif integration == "discord_webhook":
            self.action_endpoint_label.set_text("Discord Webhook URL")
            self.action_endpoint_entry.set_placeholder_text("https://discord.com/api/webhooks/...")
            self.action_message_label.set_text("Discord Content")
        elif integration == "teams_webhook":
            self.action_endpoint_label.set_text("Teams Webhook URL")
            self.action_endpoint_entry.set_placeholder_text("https://outlook.office.com/webhook/...")
            self.action_message_label.set_text("Teams Message")
        elif integration == "google_apps_script":
            self.action_endpoint_label.set_text("Script URL")
            self.action_endpoint_entry.set_placeholder_text(
                "https://script.google.com/macros/s/.../exec"
            )
            self.action_message_label.set_text("Event Title")
        elif integration == "google_calendar_api":
            self.action_endpoint_label.set_text("Google Calendar URL")
            self.action_endpoint_entry.set_placeholder_text(
                "https://www.googleapis.com/calendar/v3/users/me/calendarList"
            )
            self.action_message_label.set_text("Optional Message")
            self.action_api_key_label.set_text("OAuth Token")
            self.action_api_key_entry.set_placeholder_text("Google OAuth bearer token")
        elif integration == "outlook_graph":
            self.action_endpoint_label.set_text("Outlook Graph URL")
            self.action_endpoint_entry.set_placeholder_text(
                "https://graph.microsoft.com/v1.0/me/messages?$top=5"
            )
            self.action_message_label.set_text("Optional Message")
            self.action_api_key_label.set_text("OAuth Token")
            self.action_api_key_entry.set_placeholder_text("Outlook / Graph bearer token")
        elif integration == "openweather_current":
            self.action_message_label.set_text("Message")
            self.action_api_key_label.set_text("OpenWeather API Key")
            self.action_api_key_entry.set_placeholder_text("OpenWeather API key")
        elif integration in {"telegram_bot", "gmail_send", "resend_email", "mailgun_email"}:
            self.action_message_label.set_text("Message Body")
            if integration == "telegram_bot":
                self.action_chat_id_entry.set_placeholder_text("Telegram chat id  •  123456789")
                self.action_api_key_label.set_text("Bot Token")
                self.action_api_key_entry.set_placeholder_text("Telegram bot token")
            elif integration == "gmail_send":
                self.action_to_entry.set_placeholder_text("you@example.com")
                self.action_from_entry.set_placeholder_text("alerts@yourdomain.com")
                self.action_subject_entry.set_placeholder_text("Workflow update")
                self.action_api_key_label.set_text("OAuth Token")
                self.action_api_key_entry.set_placeholder_text("Gmail OAuth bearer token")
            elif integration == "resend_email":
                self.action_to_entry.set_placeholder_text("you@example.com")
                self.action_from_entry.set_placeholder_text("alerts@yourdomain.com")
                self.action_subject_entry.set_placeholder_text("Workflow update")
                self.action_api_key_label.set_text("Resend API Key")
                self.action_api_key_entry.set_placeholder_text("re_...")
            elif integration == "mailgun_email":
                self.action_to_entry.set_placeholder_text("you@example.com")
                self.action_from_entry.set_placeholder_text("alerts@yourdomain.com")
                self.action_subject_entry.set_placeholder_text("Workflow update")
                self.action_domain_entry.set_placeholder_text("mg.yourdomain.com")
                self.action_api_key_label.set_text("Mailgun API Key")
                self.action_api_key_entry.set_placeholder_text("Mailgun API key")
        elif integration == "twilio_sms":
            self.action_message_label.set_text("SMS Message")
            self.action_to_entry.set_placeholder_text("+15550002222")
            self.action_from_entry.set_placeholder_text("+15550001111")
            self.action_account_sid_entry.set_placeholder_text("ACxxxxxxxxxxxxxxxx")
        elif integration == "approval_gate":
            self.action_message_label.set_text("Approval Message")
        elif integration == "file_append":
            self.action_message_label.set_text("File Content")
            self.action_payload_label.set_text("File Payload")
            self.action_path_label.set_text("File Path")
        elif integration in {"postgres_sql", "mysql_sql"}:
            self.action_endpoint_label.set_text("Connection URL")
            if integration == "postgres_sql":
                self.action_endpoint_entry.set_placeholder_text(
                    "postgresql://user:password@localhost:5432/postgres"
                )
            else:
                self.action_endpoint_entry.set_placeholder_text(
                    "mysql://user:password@localhost:3306/mysql"
                )
            self.action_payload_label.set_text("SQL Query")
            self.action_payload_view.set_tooltip_text("SQL statement to execute.")
            self.action_timeout_label.set_text("Execution Timeout Seconds")
        elif integration == "sqlite_sql":
            self.action_path_label.set_text("SQLite DB Path")
            self.action_path_entry.set_placeholder_text("/tmp/6x_protocol.db")
            self.action_payload_label.set_text("SQL Query")
            self.action_payload_view.set_tooltip_text("SQL statement to execute.")
            self.action_timeout_label.set_text("Execution Timeout Seconds")
        elif integration == "redis_command":
            self.action_endpoint_label.set_text("Redis Connection URL")
            self.action_endpoint_entry.set_placeholder_text("redis://localhost:6379/0")
            self.action_command_label.set_text("Redis Command")
            self.action_command_entry.set_placeholder_text("ping")
            self.action_timeout_label.set_text("Execution Timeout Seconds")
        elif integration == "s3_cli":
            self.action_command_label.set_text("AWS S3 Command")
            self.action_command_entry.set_placeholder_text("s3 ls")
            self.action_timeout_label.set_text("Execution Timeout Seconds")
        elif integration in {"monday_api", "linear_api"}:
            self.action_payload_label.set_text("GraphQL Payload")
            self.action_api_key_label.set_text("API Token")
            self.action_api_key_entry.set_placeholder_text("Service API token")
        elif integration == "openrouter_api":
            self.action_api_key_label.set_text("OpenRouter API Key")
            self.action_api_key_entry.set_placeholder_text("sk-or-v1-...")
        elif integration in {
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
        }:
            self.action_api_key_label.set_text("API Token")
            self.action_api_key_entry.set_placeholder_text("Service API token")
        else:
            self.action_endpoint_label.set_text("Endpoint URL")
            self.action_message_label.set_text("Message")

        template_key = str(self.selected_action_template().get("key", "")).strip().lower()
        self.sync_action_category_state(
            self.infer_action_category(template_key, integration)
        )
        selected_node = self.get_selected_node()
        if selected_node and self.node_type_key(selected_node.node_type) in {"action", "template"}:
            self.update_node_execution_hint(selected_node.node_type, integration)
        self.update_action_requirements_status()

    def bind_action_field_change_events(self):
        action_entries = [
            self.action_endpoint_entry,
            self.action_message_entry,
            self.action_to_entry,
            self.action_from_entry,
            self.action_subject_entry,
            self.action_chat_id_entry,
            self.action_account_sid_entry,
            self.action_auth_token_entry,
            self.action_domain_entry,
            self.action_username_entry,
            self.action_headers_entry,
            self.action_api_key_entry,
            self.action_location_entry,
            self.action_path_entry,
            self.action_command_entry,
        ]
        for entry in action_entries:
            entry.connect("changed", self.on_action_fields_changed)

        self.action_method_dropdown.connect("notify::selected", self.on_action_fields_changed)
        self.action_units_dropdown.connect("notify::selected", self.on_action_fields_changed)
        self.action_timeout_spin.connect("value-changed", self.on_action_fields_changed)
        self.action_payload_buffer.connect("changed", self.on_action_fields_changed)

    def on_action_fields_changed(self, *_args):
        if self.loading_action_controls:
            return
        self.update_action_requirements_status()

    def on_scaffold_action_required_fields_clicked(self, _button):
        selected_node = self.get_selected_node()
        if not selected_node or self.node_type_key(selected_node.node_type) not in {"action", "template"}:
            self.set_status("Select an action or template node to scaffold required fields.")
            return

        integration = self.selected_action_integration()
        if not integration:
            self.set_status("Choose an integration before scaffolding required fields.")
            return

        # Pull integration-aware defaults first without overriding user-provided input.
        self.apply_action_smart_defaults(integration, force=False)

        app_settings = self.settings_store.load_settings()
        draft_config: dict[str, str] = {}
        self.apply_action_controls_to_config(draft_config, selected_node.node_type)
        missing_fields = self.missing_required_action_fields(
            draft_config,
            app_settings=app_settings,
        )
        if not missing_fields:
            self.update_action_requirements_status()
            self.set_status("Required fields are already filled for this integration.")
            return

        filled_fields: list[str] = []
        for required_field in missing_fields:
            if self.scaffold_required_action_field(integration, required_field):
                filled_fields.append(required_field)

        self.update_action_requirements_status()

        updated_config: dict[str, str] = {}
        self.apply_action_controls_to_config(updated_config, selected_node.node_type)
        remaining_fields = self.missing_required_action_fields(
            updated_config,
            app_settings=app_settings,
        )
        if not remaining_fields:
            if filled_fields:
                preview = ", ".join(filled_fields[:4])
                if len(filled_fields) > 4:
                    preview = f"{preview}, +{len(filled_fields) - 4} more"
                self.set_status(f"Scaffolded required fields: {preview}.")
            else:
                self.set_status("Required fields are configured.")
            return

        unresolved = ", ".join(remaining_fields[:4])
        if len(remaining_fields) > 4:
            unresolved = f"{unresolved}, +{len(remaining_fields) - 4} more"
        if filled_fields:
            self.set_status(
                f"Scaffolded {len(filled_fields)} field(s), but still missing: {unresolved}."
            )
        else:
            self.set_status(
                f"Could not auto-scaffold remaining field(s): {unresolved}. Fill them manually."
            )

    def scaffold_required_action_field(self, integration: str, required_field: str) -> bool:
        key = str(required_field).strip().lower()
        if not key:
            return False

        if key in {"url", "webhook_url", "script_url", "connection_url"}:
            if self.action_endpoint_entry.get_text().strip():
                return False
            self.action_endpoint_entry.set_text(self.scaffold_endpoint_placeholder(integration))
            return True

        if key in {"message", "text", "content", "approval_message"}:
            if self.action_message_entry.get_text().strip():
                return False
            if str(integration).strip().lower() == "approval_gate":
                self.action_message_entry.set_text("Approve this step to continue the workflow.")
            else:
                self.action_message_entry.set_text("Workflow update: ${last_output}")
            return True

        if key == "api_key":
            if self.action_api_key_entry.get_text().strip():
                return False
            self.action_api_key_entry.set_text("REPLACE_API_KEY")
            return True

        if key == "auth_token":
            if self.action_auth_token_entry.get_text().strip():
                return False
            self.action_auth_token_entry.set_text("REPLACE_AUTH_TOKEN")
            return True

        if key == "location":
            if self.action_location_entry.get_text().strip():
                return False
            self.action_location_entry.set_text("Austin,US")
            return True

        if key == "units":
            if self.selected_action_units() == "metric":
                return False
            self.action_units_dropdown.set_selected(self.action_units_index("metric"))
            return True

        if key == "path":
            if self.action_path_entry.get_text().strip():
                return False
            integration_key = str(integration).strip().lower()
            if integration_key == "sqlite_sql":
                self.action_path_entry.set_text("/tmp/6x_protocol.db")
            else:
                self.action_path_entry.set_text("/tmp/workflow.log")
            return True

        if key in {"command", "sql", "query"}:
            integration_key = str(integration).strip().lower()
            if key == "command" and self.action_command_entry.get_text().strip():
                return False
            if integration_key == "redis_command":
                command = "ping"
            elif integration_key == "s3_cli":
                command = "s3 ls"
            elif key in {"sql", "query"} or integration_key in {"postgres_sql", "mysql_sql", "sqlite_sql"}:
                command = "select now();"
            else:
                command = "echo \"${last_output}\""

            if key == "command":
                self.action_command_entry.set_text(command)
                return True

            if self.get_action_payload_text().strip():
                return False
            self.set_action_payload_text(command)
            return True

        if key == "chat_id":
            if self.action_chat_id_entry.get_text().strip():
                return False
            self.action_chat_id_entry.set_text("REPLACE_CHAT_ID")
            return True

        if key == "account_sid":
            if self.action_account_sid_entry.get_text().strip():
                return False
            self.action_account_sid_entry.set_text("REPLACE_ACCOUNT_SID")
            return True

        if key == "from":
            if self.action_from_entry.get_text().strip():
                return False
            if str(integration).strip().lower() == "twilio_sms":
                self.action_from_entry.set_text("+15550001111")
            else:
                self.action_from_entry.set_text("sender@example.com")
            return True

        if key == "to":
            if self.action_to_entry.get_text().strip():
                return False
            if str(integration).strip().lower() == "twilio_sms":
                self.action_to_entry.set_text("+15550002222")
            else:
                self.action_to_entry.set_text("recipient@example.com")
            return True

        if key == "subject":
            if self.action_subject_entry.get_text().strip():
                return False
            self.action_subject_entry.set_text("Workflow Update")
            return True

        if key == "domain":
            if self.action_domain_entry.get_text().strip():
                return False
            self.action_domain_entry.set_text("mg.example.com")
            return True

        if key == "headers":
            if self.action_headers_entry.get_text().strip():
                return False
            self.action_headers_entry.set_text('{"Content-Type":"application/json"}')
            return True

        if key == "payload":
            if self.get_action_payload_text().strip():
                return False
            self.set_action_payload_text('{"input":"${last_output}"}')
            return True

        if key in {"spreadsheet_id", "range"}:
            return self.ensure_payload_key(
                key,
                "REPLACE_SHEET_ID" if key == "spreadsheet_id" else "Sheet1!A:B",
            )

        return False

    def scaffold_endpoint_placeholder(self, integration: str) -> str:
        key = str(integration).strip().lower()
        mapping = {
            "slack_webhook": "https://hooks.slack.com/services/REPLACE/REPLACE/REPLACE",
            "discord_webhook": "https://discord.com/api/webhooks/REPLACE/REPLACE",
            "teams_webhook": "https://outlook.office.com/webhook/REPLACE/IncomingWebhook/REPLACE/REPLACE",
            "google_apps_script": "https://script.google.com/macros/s/REPLACE/exec",
            "http_request": "https://api.example.com/v1/events",
            "http_post": "https://api.example.com/v1/events",
            "google_calendar_api": "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            "outlook_graph": "https://graph.microsoft.com/v1.0/me/messages",
            "notion_api": "https://api.notion.com/v1/pages",
            "airtable_api": "https://api.airtable.com/v0/BASE_ID/TABLE_NAME",
            "hubspot_api": "https://api.hubapi.com/crm/v3/objects/contacts",
            "stripe_api": "https://api.stripe.com/v1/balance",
            "github_rest": "https://api.github.com/user",
            "gitlab_api": "https://gitlab.com/api/v4/user",
            "jira_api": "https://your-domain.atlassian.net/rest/api/3/myself",
            "asana_api": "https://app.asana.com/api/1.0/users/me",
            "clickup_api": "https://api.clickup.com/api/v2/user",
            "trello_api": "https://api.trello.com/1/members/me",
            "monday_api": "https://api.monday.com/v2",
            "zendesk_api": "https://your-domain.zendesk.com/api/v2/users/me.json",
            "pipedrive_api": "https://api.pipedrive.com/v1/users/me",
            "salesforce_api": "https://your-instance.my.salesforce.com/services/data/v58.0/limits",
            "google_drive_api": "https://www.googleapis.com/drive/v3/files",
            "dropbox_api": "https://api.dropboxapi.com/2/files/list_folder",
            "shopify_api": "https://your-store.myshopify.com/admin/api/2024-01/products.json",
            "webflow_api": "https://api.webflow.com/v2/sites",
            "supabase_api": "https://PROJECT_REF.supabase.co/rest/v1",
            "openrouter_api": "https://openrouter.ai/api/v1/chat/completions",
            "postgres_sql": "postgresql://user:password@localhost:5432/database",
            "mysql_sql": "mysql://user:password@localhost:3306/database",
            "redis_command": "redis://localhost:6379/0",
        }
        return mapping.get(key, "https://api.example.com/v1/endpoint")

    def ensure_payload_key(self, key: str, value: str) -> bool:
        payload_raw = self.get_action_payload_text().strip()
        payload_obj: dict[str, str] = {}
        if payload_raw:
            try:
                parsed_payload = json.loads(payload_raw)
            except Exception:
                return False
            if not isinstance(parsed_payload, dict):
                return False
            payload_obj = {
                str(item_key).strip(): str(item_value).strip()
                for item_key, item_value in parsed_payload.items()
            }

        current = str(payload_obj.get(key, "")).strip()
        if current:
            return False
        payload_obj[key] = value
        self.set_action_payload_text(json.dumps(payload_obj))
        return True

    def bind_trigger_condition_change_events(self):
        for entry in [
            self.trigger_webhook_entry,
            self.trigger_watch_path_entry,
            self.trigger_cron_entry,
            self.trigger_value_entry,
            self.edit_condition_value_entry,
            self.condition_preview_input_entry,
        ]:
            entry.connect("changed", self.on_trigger_condition_fields_changed)

        self.trigger_interval_scale.connect("value-changed", self.on_trigger_condition_fields_changed)
        self.trigger_interval_spin.connect("value-changed", self.on_trigger_condition_fields_changed)
        self.edit_condition_min_len_scale.connect(
            "value-changed",
            self.on_trigger_condition_fields_changed,
        )
        self.edit_condition_min_len_spin.connect(
            "value-changed",
            self.on_trigger_condition_fields_changed,
        )

    def on_trigger_condition_fields_changed(self, *_args):
        self.apply_trigger_validation_feedback()
        self.apply_condition_validation_feedback()

    def update_action_requirements_status(self):
        integration = self.selected_action_integration()
        summary = self.integration_requirement_summary(integration)
        self.clear_action_field_feedback()
        selected_node = self.get_selected_node()
        if not selected_node or self.node_type_key(selected_node.node_type) not in {"action", "template"}:
            self.action_requirements_label.set_text(summary)
            return

        merged = self.parse_detail_directives(selected_node.detail)
        merged.update(selected_node.config)
        merged["integration"] = integration

        # Mirror active inspector edits so requirement hints are live while typing.
        endpoint = self.action_endpoint_entry.get_text().strip()
        message = self.action_message_entry.get_text().strip()
        payload = self.action_payload_text().strip()
        api_key = self.action_api_key_entry.get_text().strip()
        path = self.action_path_entry.get_text().strip()
        command = self.action_command_entry.get_text().strip()
        if endpoint:
            merged["url"] = endpoint
            merged["webhook_url"] = endpoint
        if message:
            merged["message"] = message
        if payload:
            merged["payload"] = payload
        if api_key:
            merged["api_key"] = api_key
            merged["auth_token"] = api_key
        if path:
            merged["path"] = path
        if command:
            merged["command"] = command
        to_value = self.action_to_entry.get_text().strip()
        from_value = self.action_from_entry.get_text().strip()
        subject_value = self.action_subject_entry.get_text().strip()
        chat_value = self.action_chat_id_entry.get_text().strip()
        sid_value = self.action_account_sid_entry.get_text().strip()
        token_value = self.action_auth_token_entry.get_text().strip()
        domain_value = self.action_domain_entry.get_text().strip()
        location_value = self.action_location_entry.get_text().strip()
        if to_value:
            merged["to"] = to_value
        if from_value:
            merged["from"] = from_value
        if subject_value:
            merged["subject"] = subject_value
        if chat_value:
            merged["chat_id"] = chat_value
        if sid_value:
            merged["account_sid"] = sid_value
        if token_value:
            merged["auth_token"] = token_value
        if domain_value:
            merged["domain"] = domain_value
        if location_value:
            merged["location"] = location_value

        app_settings = self.settings_store.load_settings()
        missing_fields = self.missing_required_action_fields(
            merged,
            app_settings=app_settings,
        )
        field_issues = self.build_action_inline_validation_issues(
            integration,
            merged,
            missing_fields,
            app_settings,
        )

        prioritized: dict[str, tuple[str, str]] = {}
        for field_key, severity, message in field_issues:
            existing = prioritized.get(field_key)
            if existing and existing[0] == "error" and severity != "error":
                continue
            prioritized[field_key] = (severity, message)

        for field_key, (severity, message) in prioritized.items():
            self.set_action_field_feedback(field_key, message, severity)

        errors = [item for item in field_issues if item[1] == "error"]
        warnings = [item for item in field_issues if item[1] == "warning"]
        if not errors and not warnings:
            self.action_requirements_label.set_text(f"{summary} Ready: required fields are filled.")
            return

        preview_items = [item[2] for item in [*errors, *warnings][:3]]
        preview = " • ".join(preview_items)
        remaining = len(field_issues) - len(preview_items)
        if remaining > 0:
            preview = f"{preview} • +{remaining} more"
        self.action_requirements_label.set_text(
            f"{summary} Fix {len(errors)} error(s), {len(warnings)} warning(s): {preview}"
        )

    def parse_detail_directives(self, text: str) -> dict[str, str]:
        directives: dict[str, str] = {}
        for line in str(text).splitlines():
            raw = line.strip()
            if not raw or ":" not in raw:
                continue
            key, value = raw.split(":", 1)
            directives[key.strip().lower()] = value.strip()
        return directives

    def action_units_index(self, value: str) -> int:
        normalized = str(value).strip().lower()
        values = ["metric", "imperial", "standard"]
        if normalized in values:
            return values.index(normalized)
        return 0

    def selected_action_units(self) -> str:
        values = ["metric", "imperial", "standard"]
        index = self.action_units_dropdown.get_selected()
        return values[index] if 0 <= index < len(values) else "metric"

    def action_method_index(self, value: str) -> int:
        methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]
        normalized = str(value).strip().upper()
        if normalized in methods:
            return methods.index(normalized)
        return 1

    def selected_action_method(self) -> str:
        methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]
        index = self.action_method_dropdown.get_selected()
        if 0 <= index < len(methods):
            return methods[index]
        return "POST"

    def set_action_payload_text(self, text: str):
        self.action_payload_buffer.set_text(text)

    def get_action_payload_text(self) -> str:
        start = self.action_payload_buffer.get_start_iter()
        end = self.action_payload_buffer.get_end_iter()
        return self.action_payload_buffer.get_text(start, end, False)

    def load_action_controls(self, merged_config: dict[str, str]):
        integration = str(merged_config.get("integration", "")).strip().lower() or "standard"
        self.loading_action_controls = True
        try:
            self.action_integration_dropdown.set_selected(self.action_integration_index(integration))
            inferred_template = self.infer_action_template_key(merged_config)
            self.action_template_dropdown.set_selected(self.action_template_index(inferred_template))
            self.update_action_template_hint()
            payload_text = str(merged_config.get("payload", "")).strip()
            payload_obj: dict[str, str] = {}
            if payload_text:
                try:
                    parsed = json.loads(payload_text)
                    if isinstance(parsed, dict):
                        payload_obj = {
                            str(key).strip(): str(value).strip()
                            for key, value in parsed.items()
                        }
                except Exception:
                    payload_obj = {}

            if integration in {"postgres_sql", "mysql_sql", "sqlite_sql"}:
                sql_payload = str(payload_obj.get("sql", "")).strip()
                direct_sql = str(merged_config.get("sql", "")).strip()
                if sql_payload:
                    payload_text = sql_payload
                elif direct_sql and not payload_text:
                    payload_text = direct_sql

            endpoint = ""
            if integration in {"http_post", "http_request"}:
                endpoint = str(merged_config.get("url", "")).strip()
            elif integration in {"slack_webhook", "discord_webhook", "teams_webhook"}:
                endpoint = (
                    str(merged_config.get("webhook_url", "")).strip()
                    or str(merged_config.get("url", "")).strip()
                )
            elif integration == "google_apps_script":
                endpoint = (
                    str(merged_config.get("script_url", "")).strip()
                    or str(merged_config.get("url", "")).strip()
                )
            elif integration in {
                "notion_api",
                "airtable_api",
                "hubspot_api",
                "stripe_api",
                "github_rest",
                "gitlab_api",
                "google_drive_api",
                "dropbox_api",
                "shopify_api",
                "webflow_api",
                "supabase_api",
                "openrouter_api",
                "linear_api",
                "google_calendar_api",
                "outlook_graph",
                "jira_api",
                "asana_api",
                "clickup_api",
                "trello_api",
                "monday_api",
                "zendesk_api",
                "pipedrive_api",
                "salesforce_api",
                "resend_email",
                "mailgun_email",
            }:
                endpoint = str(merged_config.get("url", "")).strip()
            elif integration in {"postgres_sql", "mysql_sql", "redis_command"}:
                endpoint = (
                    str(merged_config.get("connection_url", "")).strip()
                    or str(payload_obj.get("connection_url", "")).strip()
                    or str(payload_obj.get("url", "")).strip()
                    or str(merged_config.get("url", "")).strip()
                )
            self.action_endpoint_entry.set_text(endpoint)
            self.action_method_dropdown.set_selected(
                self.action_method_index(str(merged_config.get("method", "")).strip() or "POST")
            )

            message = ""
            if integration == "slack_webhook":
                message = str(merged_config.get("text", "")).strip()
            elif integration == "discord_webhook":
                message = str(merged_config.get("content", "")).strip()
            elif integration == "teams_webhook":
                message = str(merged_config.get("text", "")).strip()
            elif integration == "approval_gate":
                message = str(merged_config.get("approval_message", "")).strip()
            elif integration == "file_append":
                message = str(merged_config.get("content", "")).strip()
            else:
                message = (
                    str(merged_config.get("message", "")).strip()
                    or str(merged_config.get("text", "")).strip()
                    or str(merged_config.get("content", "")).strip()
                    or str(payload_obj.get("message", "")).strip()
                    or str(payload_obj.get("text", "")).strip()
                    or str(payload_obj.get("content", "")).strip()
                )
            self.action_message_entry.set_text(message)

            self.action_to_entry.set_text(
                str(merged_config.get("to", "")).strip() or str(payload_obj.get("to", "")).strip()
            )
            self.action_from_entry.set_text(
                str(merged_config.get("from", "")).strip() or str(payload_obj.get("from", "")).strip()
            )
            self.action_subject_entry.set_text(
                str(merged_config.get("subject", "")).strip()
                or str(payload_obj.get("subject", "")).strip()
            )
            self.action_chat_id_entry.set_text(
                str(merged_config.get("chat_id", "")).strip()
                or str(payload_obj.get("chat_id", "")).strip()
            )
            self.action_account_sid_entry.set_text(
                str(merged_config.get("account_sid", "")).strip()
                or str(payload_obj.get("account_sid", "")).strip()
            )
            self.action_auth_token_entry.set_text(
                str(merged_config.get("auth_token", "")).strip()
                or str(payload_obj.get("auth_token", "")).strip()
            )
            self.action_domain_entry.set_text(
                str(merged_config.get("domain", "")).strip()
                or str(payload_obj.get("domain", "")).strip()
            )
            self.action_username_entry.set_text(str(merged_config.get("username", "")).strip())
            self.set_action_payload_text(payload_text)
            self.action_headers_entry.set_text(str(merged_config.get("headers", "")).strip())
            self.action_api_key_entry.set_text(str(merged_config.get("api_key", "")).strip())
            self.action_location_entry.set_text(str(merged_config.get("location", "")).strip())
            self.action_units_dropdown.set_selected(
                self.action_units_index(merged_config.get("units", "metric"))
            )
            self.action_path_entry.set_text(
                str(merged_config.get("path", "")).strip()
                or str(payload_obj.get("path", "")).strip()
            )
            self.action_command_entry.set_text(str(merged_config.get("command", "")).strip())
            timeout_value = self.parse_float(merged_config.get("timeout_sec", ""), 0.0)
            self.action_timeout_spin.set_value(max(0.0, timeout_value))
        finally:
            self.loading_action_controls = False
        self.update_action_integration_field_visibility()

    def apply_action_controls_to_config(
        self,
        updated_config: dict[str, str],
        node_type: str,
    ):
        node_key = self.node_type_key(node_type)
        action_like = node_key in {"action", "template"}

        integration_keys = [
            "action_template",
            "integration",
            "url",
            "webhook_url",
            "script_url",
            "api_key",
            "location",
            "units",
            "payload",
            "path",
            "command",
            "text",
            "message",
            "content",
            "username",
            "approval_message",
            "timeout_sec",
            "method",
            "headers",
            "chat_id",
            "to",
            "from",
            "subject",
            "spreadsheet_id",
            "range",
            "account_sid",
            "auth_token",
            "domain",
            "connection_url",
            "sql",
            "query",
        ]
        for key in integration_keys:
            updated_config[key] = ""

        if not action_like:
            return

        updated_config["action_template"] = str(
            self.selected_action_template().get("key", "generic_action")
        ).strip()
        integration = self.selected_action_integration()
        updated_config["integration"] = integration or "standard"
        endpoint = self.action_endpoint_entry.get_text().strip()
        message = self.action_message_entry.get_text().strip()
        username = self.action_username_entry.get_text().strip()
        payload = self.get_action_payload_text().strip()
        headers = self.action_headers_entry.get_text().strip()
        api_key = self.action_api_key_entry.get_text().strip()
        location = self.action_location_entry.get_text().strip()
        units = self.selected_action_units()
        path = self.action_path_entry.get_text().strip()
        command = self.action_command_entry.get_text().strip()
        to_value = self.action_to_entry.get_text().strip()
        from_value = self.action_from_entry.get_text().strip()
        subject_value = self.action_subject_entry.get_text().strip()
        chat_id_value = self.action_chat_id_entry.get_text().strip()
        account_sid_value = self.action_account_sid_entry.get_text().strip()
        auth_token_value = self.action_auth_token_entry.get_text().strip()
        domain_value = self.action_domain_entry.get_text().strip()
        method = self.selected_action_method()
        timeout_value = round(self.action_timeout_spin.get_value(), 1)

        if endpoint:
            if integration in {"http_post", "http_request"}:
                updated_config["url"] = endpoint
            elif integration in {"slack_webhook", "discord_webhook", "teams_webhook"}:
                updated_config["webhook_url"] = endpoint
                updated_config["url"] = endpoint
            elif integration == "google_apps_script":
                updated_config["script_url"] = endpoint
                updated_config["url"] = endpoint
            elif integration in {"postgres_sql", "mysql_sql", "redis_command"}:
                updated_config["connection_url"] = endpoint
            else:
                updated_config["url"] = endpoint
        if method and integration in {
            "http_request",
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "openrouter_api",
            "google_calendar_api",
            "outlook_graph",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
        }:
            updated_config["method"] = method
        if headers and integration in {
            "http_request",
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "openrouter_api",
            "google_calendar_api",
            "outlook_graph",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
        }:
            updated_config["headers"] = headers

        if payload and integration in {
            "http_post",
            "http_request",
            "google_apps_script",
            "telegram_bot",
            "gmail_send",
            "google_sheets",
            "google_calendar_api",
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "openrouter_api",
            "linear_api",
            "outlook_graph",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
            "twilio_sms",
            "resend_email",
            "mailgun_email",
            "postgres_sql",
            "mysql_sql",
            "sqlite_sql",
        }:
            updated_config["payload"] = payload
        if payload and integration in {"postgres_sql", "mysql_sql", "sqlite_sql"}:
            updated_config["sql"] = payload
        if username and integration in {"slack_webhook", "discord_webhook", "teams_webhook"}:
            updated_config["username"] = username

        if message:
            if integration == "slack_webhook":
                updated_config["text"] = message
            elif integration == "discord_webhook":
                updated_config["content"] = message
            elif integration == "teams_webhook":
                updated_config["text"] = message
            elif integration == "approval_gate":
                updated_config["approval_message"] = message
            elif integration == "file_append":
                updated_config["content"] = message
            else:
                updated_config["message"] = message

        if integration in {
            "openweather_current",
            "http_request",
            "telegram_bot",
            "gmail_send",
            "google_sheets",
            "google_calendar_api",
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "openrouter_api",
            "linear_api",
            "outlook_graph",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
            "resend_email",
            "mailgun_email",
        }:
            updated_config["api_key"] = api_key
        if integration == "openweather_current":
            updated_config["location"] = location
            updated_config["units"] = units
        if integration in {"file_append", "sqlite_sql"}:
            updated_config["path"] = path
        if integration in {"shell_command", "redis_command", "s3_cli"}:
            updated_config["command"] = command
        if integration == "google_sheets":
            try:
                payload_obj = json.loads(payload) if payload else {}
            except Exception:
                payload_obj = {}
            if isinstance(payload_obj, dict):
                spreadsheet_id = str(payload_obj.get("spreadsheet_id", "")).strip()
                range_value = str(payload_obj.get("range", "")).strip()
                if spreadsheet_id:
                    updated_config["spreadsheet_id"] = spreadsheet_id
                if range_value:
                    updated_config["range"] = range_value
        if to_value and integration in {"gmail_send", "resend_email", "mailgun_email", "twilio_sms"}:
            updated_config["to"] = to_value
        if from_value and integration in {"gmail_send", "resend_email", "mailgun_email", "twilio_sms"}:
            updated_config["from"] = from_value
        if subject_value and integration in {"gmail_send", "resend_email", "mailgun_email"}:
            updated_config["subject"] = subject_value
        if chat_id_value and integration in {"telegram_bot"}:
            updated_config["chat_id"] = chat_id_value
        if account_sid_value and integration in {"twilio_sms"}:
            updated_config["account_sid"] = account_sid_value
        if auth_token_value and integration in {"twilio_sms"}:
            updated_config["auth_token"] = auth_token_value
        if domain_value and integration in {"mailgun_email"}:
            updated_config["domain"] = domain_value

        if timeout_value > 0.0 and integration in {
            "http_post",
            "http_request",
            "slack_webhook",
            "discord_webhook",
            "teams_webhook",
            "openweather_current",
            "google_apps_script",
            "shell_command",
            "telegram_bot",
            "gmail_send",
            "google_sheets",
            "google_calendar_api",
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "openrouter_api",
            "linear_api",
            "outlook_graph",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
            "twilio_sms",
            "resend_email",
            "mailgun_email",
            "postgres_sql",
            "mysql_sql",
            "sqlite_sql",
            "redis_command",
            "s3_cli",
        }:
            updated_config["timeout_sec"] = f"{timeout_value:.1f}"

    def apply_node_execution_controls_to_config(
        self,
        updated_config: dict[str, str],
        node_type: str,
    ):
        integration = self.selected_action_integration()
        defaults = self.node_execution_profile(node_type, integration)
        retry_value = max(0, self.node_retry_spin.get_value_as_int())
        backoff_value = max(0, self.node_backoff_spin.get_value_as_int())
        timeout_value = max(0.0, round(self.node_timeout_spin.get_value(), 1))

        updated_config["retry_max"] = str(retry_value)
        updated_config["retry_backoff_ms"] = str(backoff_value)
        updated_config["timeout_sec"] = (
            f"{timeout_value:.1f}" if timeout_value > 0.0 else "0.0"
        )

        # Keep values deterministic when controls are at recommended defaults.
        if retry_value == int(defaults["retry_max"]):
            updated_config["retry_max"] = str(int(defaults["retry_max"]))
        if backoff_value == int(defaults["retry_backoff_ms"]):
            updated_config["retry_backoff_ms"] = str(int(defaults["retry_backoff_ms"]))

    def to_screen(self, logical_value: float) -> int:
        return int(round(float(logical_value) * self.zoom_factor))

    def to_logical(self, screen_value: float) -> int:
        if self.zoom_factor <= 0:
            return int(round(screen_value))
        return int(round(float(screen_value) / self.zoom_factor))

    def card_screen_width(self) -> int:
        return max(110, self.to_screen(self.CARD_WIDTH))

    def card_screen_height(self) -> int:
        return max(64, self.to_screen(self.CARD_HEIGHT))

    def update_zoom_button_label(self):
        if hasattr(self, "zoom_reset_button") and self.zoom_reset_button:
            percent = int(round(self.zoom_factor * 100))
            self.zoom_reset_button.set_label(f"{percent}%")

    def update_stage_dimensions(self):
        stage_width = max(640, self.to_screen(self.STAGE_WIDTH))
        stage_height = max(420, self.to_screen(self.STAGE_HEIGHT))
        self.fixed.set_size_request(stage_width, stage_height)
        self.link_layer.set_content_width(stage_width)
        self.link_layer.set_content_height(stage_height)
        if hasattr(self, "minimap_area") and self.minimap_area:
            self.minimap_area.queue_draw()

    def clamp_adjustment_value(self, adjustment: Gtk.Adjustment, value: float):
        lower = adjustment.get_lower()
        upper = max(lower, adjustment.get_upper() - adjustment.get_page_size())
        adjustment.set_value(max(lower, min(upper, value)))

    def center_view_on_logical(self, logical_x: float, logical_y: float):
        if not self.canvas_scroll:
            return
        hadj = self.canvas_scroll.get_hadjustment()
        vadj = self.canvas_scroll.get_vadjustment()
        if not hadj or not vadj:
            return

        target_x = (logical_x * self.zoom_factor) - (hadj.get_page_size() / 2)
        target_y = (logical_y * self.zoom_factor) - (vadj.get_page_size() / 2)
        self.clamp_adjustment_value(hadj, target_x)
        self.clamp_adjustment_value(vadj, target_y)

    def set_zoom(self, zoom_value: float, status_message: bool = True):
        target_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, float(zoom_value)))
        previous_zoom = self.zoom_factor
        if abs(target_zoom - previous_zoom) < 0.001:
            return

        logical_center_x = self.STAGE_WIDTH / 2
        logical_center_y = self.STAGE_HEIGHT / 2

        if self.canvas_scroll:
            hadj = self.canvas_scroll.get_hadjustment()
            vadj = self.canvas_scroll.get_vadjustment()
            if hadj and vadj and previous_zoom > 0:
                logical_center_x = (hadj.get_value() + (hadj.get_page_size() / 2)) / previous_zoom
                logical_center_y = (vadj.get_value() + (vadj.get_page_size() / 2)) / previous_zoom

        self.zoom_factor = target_zoom
        self.update_zoom_button_label()
        self.refresh_canvas()
        self.center_view_on_logical(logical_center_x, logical_center_y)
        if status_message:
            self.set_status(f"Zoom set to {int(round(target_zoom * 100))}%.")

    def on_zoom_out_clicked(self, _button):
        self.set_zoom(self.zoom_factor - self.ZOOM_STEP)

    def on_zoom_in_clicked(self, _button):
        self.set_zoom(self.zoom_factor + self.ZOOM_STEP)

    def on_zoom_reset_clicked(self, _button):
        self.set_zoom(1.0)

    def on_zoom_fit_clicked(self, _button):
        if not self.nodes:
            self.set_zoom(1.0)
            return

        hadj = self.canvas_scroll.get_hadjustment() if self.canvas_scroll else None
        vadj = self.canvas_scroll.get_vadjustment() if self.canvas_scroll else None
        if not hadj or not vadj:
            self.set_zoom(1.0)
            return

        min_x = min(node.x for node in self.nodes)
        min_y = min(node.y for node in self.nodes)
        max_x = max(node.x + self.CARD_WIDTH for node in self.nodes)
        max_y = max(node.y + self.CARD_HEIGHT for node in self.nodes)

        logical_width = max(220.0, (max_x - min_x) + 160.0)
        logical_height = max(180.0, (max_y - min_y) + 140.0)
        zoom_x = hadj.get_page_size() / logical_width
        zoom_y = vadj.get_page_size() / logical_height
        fit_zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, min(zoom_x, zoom_y)))

        self.set_zoom(fit_zoom, status_message=False)
        self.center_view_on_logical((min_x + max_x) / 2, (min_y + max_y) / 2)
        self.set_status(f"Zoom fit applied ({int(round(self.zoom_factor * 100))}%).")

    def on_minimap_reset_clicked(self, _button):
        self.minimap_user_placed = False
        self.minimap_position_initialized = False
        self.ensure_minimap_position()
        self.persist_minimap_position()
        if hasattr(self, "minimap_area") and self.minimap_area:
            self.minimap_area.queue_draw()
        self.set_status("Mini map reset to default position.")

    def on_canvas_viewport_changed(self, *_args):
        self.ensure_minimap_position()
        if hasattr(self, "minimap_area") and self.minimap_area:
            self.minimap_area.queue_draw()

    def on_canvas_pan_begin(self, _gesture, _start_x: float, _start_y: float):
        if not self.canvas_scroll:
            return
        hadj = self.canvas_scroll.get_hadjustment()
        vadj = self.canvas_scroll.get_vadjustment()
        if not hadj or not vadj:
            return
        self.pan_drag_active = True
        self.pan_drag_origin = {
            "hadj": hadj.get_value(),
            "vadj": vadj.get_value(),
        }

    def on_canvas_pan_update(self, _gesture, offset_x: float, offset_y: float):
        if not self.pan_drag_active or not self.canvas_scroll:
            return
        hadj = self.canvas_scroll.get_hadjustment()
        vadj = self.canvas_scroll.get_vadjustment()
        if not hadj or not vadj:
            return
        start_h = float(self.pan_drag_origin.get("hadj", hadj.get_value()))
        start_v = float(self.pan_drag_origin.get("vadj", vadj.get_value()))
        self.clamp_adjustment_value(hadj, start_h - offset_x)
        self.clamp_adjustment_value(vadj, start_v - offset_y)

    def on_canvas_pan_end(self, _gesture, _offset_x: float, _offset_y: float):
        self.pan_drag_active = False
        self.pan_drag_origin = {}

    def on_minimap_released(self, _gesture, _n_press, x: float, y: float):
        if self.minimap_drag_moved:
            self.minimap_drag_moved = False
            self.set_status("Mini map repositioned.")
            return
        self.navigate_via_minimap(x, y)

    def minimap_overlay_size(self) -> tuple[int, int]:
        width = 0
        height = 0
        if hasattr(self, "canvas_overlay") and self.canvas_overlay:
            width = int(self.canvas_overlay.get_allocated_width())
            height = int(self.canvas_overlay.get_allocated_height())
        if (width <= 0 or height <= 0) and self.canvas_scroll:
            width = max(width, int(self.canvas_scroll.get_allocated_width()))
            height = max(height, int(self.canvas_scroll.get_allocated_height()))
        return max(0, width), max(0, height)

    def minimap_size(self) -> tuple[int, int]:
        width = int(self.minimap_area.get_allocated_width())
        height = int(self.minimap_area.get_allocated_height())
        if width <= 0:
            width = int(self.minimap_area.get_content_width())
        if height <= 0:
            height = int(self.minimap_area.get_content_height())
        return max(1, width), max(1, height)

    def clamp_minimap_position(self, x: int, y: int) -> tuple[int, int]:
        overlay_w, overlay_h = self.minimap_overlay_size()
        mini_w, mini_h = self.minimap_size()
        padding = 10

        if overlay_w <= 0 or overlay_h <= 0:
            return max(0, x), max(0, y)

        max_x = max(padding, overlay_w - mini_w - padding)
        max_y = max(padding, overlay_h - mini_h - padding)
        clamped_x = max(padding, min(int(x), max_x))
        clamped_y = max(padding, min(int(y), max_y))
        return clamped_x, clamped_y

    def apply_minimap_position(self, x: int, y: int, mark_user_placed: bool = False):
        clamped_x, clamped_y = self.clamp_minimap_position(x, y)
        self.minimap_x = clamped_x
        self.minimap_y = clamped_y
        self.minimap_area.set_margin_start(clamped_x)
        self.minimap_area.set_margin_top(clamped_y)
        self.minimap_position_initialized = True
        if mark_user_placed:
            self.minimap_user_placed = True

    def ensure_minimap_position(self):
        if not hasattr(self, "minimap_area") or not self.minimap_area:
            return False

        overlay_w, overlay_h = self.minimap_overlay_size()
        if overlay_w <= 0 or overlay_h <= 0:
            return False

        _mini_w, _mini_h = self.minimap_size()
        if not self.minimap_position_initialized:
            default_x = 12
            self.apply_minimap_position(default_x, 10, mark_user_placed=False)
            return False

        clamped_x, clamped_y = self.clamp_minimap_position(self.minimap_x, self.minimap_y)
        if clamped_x != self.minimap_x or clamped_y != self.minimap_y:
            self.apply_minimap_position(clamped_x, clamped_y, mark_user_placed=self.minimap_user_placed)
        return False

    def on_minimap_drag_begin(self, gesture: Gtk.GestureDrag, _start_x: float, _start_y: float):
        self.ensure_minimap_position()
        self.minimap_drag_active = True
        self.minimap_drag_moved = False
        self.minimap_drag_origin = {
            "x": int(self.minimap_x),
            "y": int(self.minimap_y),
        }
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def on_minimap_drag_update(self, _gesture: Gtk.GestureDrag, offset_x: float, offset_y: float):
        if not self.minimap_drag_active:
            return
        if abs(offset_x) > 1.5 or abs(offset_y) > 1.5:
            self.minimap_drag_moved = True
        start_x = int(self.minimap_drag_origin.get("x", self.minimap_x))
        start_y = int(self.minimap_drag_origin.get("y", self.minimap_y))
        target_x = int(round(start_x + offset_x))
        target_y = int(round(start_y + offset_y))
        self.apply_minimap_position(target_x, target_y, mark_user_placed=True)

    def on_minimap_drag_end(self, _gesture: Gtk.GestureDrag, _offset_x: float, _offset_y: float):
        self.minimap_drag_active = False
        self.minimap_drag_origin = {}
        if self.minimap_drag_moved:
            self.persist_minimap_position()

    def persist_minimap_position(self):
        try:
            settings = self.settings_store.load_settings()
            settings.update(
                {
                    "canvas_minimap_x": int(self.minimap_x),
                    "canvas_minimap_y": int(self.minimap_y),
                    "canvas_minimap_user_placed": bool(self.minimap_user_placed),
                }
            )
            self.settings_store.save_settings(settings)
        except Exception:
            return

    def navigate_via_minimap(self, x: float, y: float):
        width = max(1, self.minimap_area.get_allocated_width())
        height = max(1, self.minimap_area.get_allocated_height())
        logical_x = max(0.0, min(float(self.STAGE_WIDTH), (x / width) * self.STAGE_WIDTH))
        logical_y = max(0.0, min(float(self.STAGE_HEIGHT), (y / height) * self.STAGE_HEIGHT))
        self.center_view_on_logical(logical_x, logical_y)
        self.set_status("Canvas moved via mini map.")

    def on_draw_minimap(self, _area, cr, width: int, height: int):
        self.ensure_minimap_position()
        dark_mode = self.is_dark_mode()
        if dark_mode:
            cr.set_source_rgba(0.07, 0.11, 0.18, 0.92)
        else:
            cr.set_source_rgba(0.96, 0.98, 1.0, 0.95)
        self.draw_rounded_rect(cr, 0.5, 0.5, width - 1.0, height - 1.0, 10.0)
        cr.fill()

        if dark_mode:
            cr.set_source_rgba(0.38, 0.56, 0.88, 0.45)
        else:
            cr.set_source_rgba(0.58, 0.67, 0.82, 0.52)
        self.draw_rounded_rect(cr, 0.5, 0.5, width - 1.0, height - 1.0, 10.0)
        cr.set_line_width(1.0)
        cr.stroke()

        scale_x = width / float(self.STAGE_WIDTH)
        scale_y = height / float(self.STAGE_HEIGHT)
        node_w = max(3.0, self.CARD_WIDTH * scale_x)
        node_h = max(2.0, self.CARD_HEIGHT * scale_y)

        for node in self.nodes:
            nx = node.x * scale_x
            ny = node.y * scale_y
            if node.id == self.selected_node_id:
                if dark_mode:
                    cr.set_source_rgba(0.56, 0.78, 1.0, 0.95)
                else:
                    cr.set_source_rgba(0.12, 0.36, 0.86, 0.9)
            else:
                if dark_mode:
                    cr.set_source_rgba(0.74, 0.83, 0.96, 0.65)
                else:
                    cr.set_source_rgba(0.31, 0.44, 0.62, 0.58)
            self.draw_rounded_rect(cr, nx, ny, node_w, node_h, 2.5)
            cr.fill()

        if not self.canvas_scroll:
            return
        hadj = self.canvas_scroll.get_hadjustment()
        vadj = self.canvas_scroll.get_vadjustment()
        if not hadj or not vadj or self.zoom_factor <= 0:
            return

        logical_view_x = hadj.get_value() / self.zoom_factor
        logical_view_y = vadj.get_value() / self.zoom_factor
        logical_view_w = hadj.get_page_size() / self.zoom_factor
        logical_view_h = vadj.get_page_size() / self.zoom_factor

        vx = logical_view_x * scale_x
        vy = logical_view_y * scale_y
        vw = max(8.0, logical_view_w * scale_x)
        vh = max(6.0, logical_view_h * scale_y)

        if dark_mode:
            cr.set_source_rgba(0.86, 0.93, 1.0, 0.88)
        else:
            cr.set_source_rgba(0.12, 0.3, 0.72, 0.85)
        self.draw_rounded_rect(cr, vx, vy, vw, vh, 4.0)
        cr.set_line_width(1.2)
        cr.stroke()

    def on_refresh_workflows(self, _button):
        self.reload_workflows()

    def on_refresh_templates(self, _button):
        self.reload_templates()
        self.set_status("Template list refreshed.")

    def latest_run_for_workflow(self, workflow_id: str) -> RunRecord | None:
        target_workflow_id = str(workflow_id).strip()
        if not target_workflow_id:
            return None
        runs = self.run_store.load_runs()
        for run in runs:
            if str(run.workflow_id).strip() == target_workflow_id:
                return run
        return None

    def refresh_workflow_run_state(self, quiet: bool = False):
        workflow = self.get_active_workflow()
        if not workflow:
            self.latest_workflow_run_id = ""
            self.latest_workflow_run_status = ""
            self.latest_workflow_run_failed_node_id = ""
            self.latest_workflow_run_pending_approval_node_id = ""
            self.workflow_run_state_label.set_text("No workflow selected.")
            self.update_control_state()
            return

        latest = self.latest_run_for_workflow(workflow.id)
        if not latest:
            self.latest_workflow_run_id = ""
            self.latest_workflow_run_status = ""
            self.latest_workflow_run_failed_node_id = ""
            self.latest_workflow_run_pending_approval_node_id = ""
            self.workflow_run_state_label.set_text("No runs yet for this workflow.")
            self.update_control_state()
            return

        self.latest_workflow_run_id = str(latest.id).strip()
        self.latest_workflow_run_status = str(latest.status).strip().lower()
        self.latest_workflow_run_failed_node_id = str(latest.last_failed_node_id).strip()
        self.latest_workflow_run_pending_approval_node_id = str(latest.pending_approval_node_id).strip()
        run_short = self.latest_workflow_run_id[:8] if self.latest_workflow_run_id else "unknown"
        summary = str(latest.summary).strip() or "No summary yet."
        self.workflow_run_state_label.set_text(
            f"Latest run {run_short} • {self.latest_workflow_run_status.upper()} • {summary}"
        )
        self.update_control_state()
        if not quiet:
            self.set_status(
                f"Run state refreshed: {self.latest_workflow_run_status.upper()} ({run_short})."
            )

    def poll_workflow_run_state(self):
        try:
            self.refresh_workflow_run_state(quiet=True)
        except Exception:
            return True
        return True

    def on_refresh_workflow_run_state_clicked(self, _button):
        self.refresh_workflow_run_state(quiet=False)

    def on_run_active_workflow(self, _button):
        workflow = self.get_active_workflow()
        if not workflow:
            self.set_status("Select a workflow before running.")
            return

        candidate = Workflow(
            id=workflow.id,
            name=workflow.name,
            trigger=workflow.trigger,
            action=workflow.action,
            graph=self.build_graph_payload(),
        )
        run = self.run_execution_service.start_workflow_run(candidate)
        run_short = str(run.id).strip()[:8] if run and run.id else "unknown"
        self.refresh_workflow_run_state(quiet=True)
        self.set_status(f"Run started for '{workflow.name}' (run {run_short}).")

    def on_cancel_latest_workflow_run(self, _button):
        if not self.latest_workflow_run_id:
            self.set_status("No recent run available for this workflow.")
            return
        ok, message = self.run_execution_service.request_stop(self.latest_workflow_run_id)
        self.refresh_workflow_run_state(quiet=True)
        if ok:
            self.set_status(message)
        else:
            self.set_status(f"Cancel failed: {message}")

    def on_retry_latest_failed_node(self, _button):
        if not self.latest_workflow_run_id:
            self.set_status("No recent run available for this workflow.")
            return
        ok, message, _run = self.run_execution_service.retry_from_failed_node(
            self.latest_workflow_run_id
        )
        self.refresh_workflow_run_state(quiet=True)
        if ok:
            self.set_status(message)
        else:
            self.set_status(f"Retry failed: {message}")

    def on_resume_latest_approval(self, _button):
        if not self.latest_workflow_run_id:
            self.set_status("No recent run available for this workflow.")
            return
        ok, message, _run = self.run_execution_service.approve_and_resume(
            self.latest_workflow_run_id
        )
        self.refresh_workflow_run_state(quiet=True)
        if ok:
            self.set_status(message)
        else:
            self.set_status(f"Resume failed: {message}")

    def rebuild_template_dropdown(self, labels: list[str], selected_index: int):
        if self.template_dropdown:
            self.template_dropdown_container.remove(self.template_dropdown)

        self.template_dropdown = Gtk.DropDown.new_from_strings(labels)
        self.template_dropdown.set_hexpand(True)
        self.template_dropdown.set_selected(selected_index)
        self.template_dropdown_container.append(self.template_dropdown)

    def reload_templates(self):
        self.templates = self.template_marketplace.list_templates()

        if not self.templates:
            self.rebuild_template_dropdown(["No templates found"], 0)
            self.template_dropdown.set_sensitive(False)
            self.update_control_state()
            return

        labels = [
            f"{item.get('name', 'Template')}  ({item.get('pack_name', 'Pack')})"
            for item in self.templates
        ]
        self.rebuild_template_dropdown(labels, 0)
        self.template_dropdown.set_sensitive(True)
        self.update_control_state()

    def rebuild_workflow_dropdown(self, labels: list[str], selected_index: int):
        if self.workflow_dropdown:
            self.workflow_dropdown_container.remove(self.workflow_dropdown)

        self.workflow_dropdown = Gtk.DropDown.new_from_strings(labels)
        self.workflow_dropdown.set_hexpand(True)
        self.workflow_dropdown.set_selected(selected_index)
        self.workflow_dropdown.connect("notify::selected", self.on_workflow_selected)
        self.workflow_dropdown_container.append(self.workflow_dropdown)

    def reload_workflows(self):
        self.workflows = self.workflow_store.load_workflows()

        if not self.workflows:
            self.active_workflow_id = None
            self.rebuild_workflow_dropdown(["No workflows found"], 0)
            self.workflow_dropdown.set_sensitive(False)
            self.nodes = []
            self.edges = []
            self.selected_node_id = None
            self.selected_node_ids = set()
            self.pending_link_source_id = None
            self.reset_history()
            self.clear_preflight_annotations()
            self.load_graph_settings({})
            self.refresh_canvas()
            self.clear_inspector()
            self.refresh_workflow_run_state(quiet=True)
            self.update_control_state()
            self.set_status("No workflows available. Create one in Workflows to edit a graph.")
            return

        labels = [workflow.name for workflow in self.workflows]
        selected_index = 0

        if self.active_workflow_id:
            for index, workflow in enumerate(self.workflows):
                if workflow.id == self.active_workflow_id:
                    selected_index = index
                    break

        self.rebuild_workflow_dropdown(labels, selected_index)
        self.workflow_dropdown.set_sensitive(True)

        self.active_workflow_id = self.workflows[selected_index].id
        self.load_graph_for_active_workflow()
        self.refresh_workflow_run_state(quiet=True)
        self.update_control_state()

    def on_workflow_selected(self, _dropdown, _param):
        if not self.workflow_dropdown:
            return

        selected_index = self.workflow_dropdown.get_selected()
        if selected_index < 0 or selected_index >= len(self.workflows):
            return

        self.active_workflow_id = self.workflows[selected_index].id
        self.load_graph_for_active_workflow()
        self.refresh_workflow_run_state(quiet=True)

    def get_active_workflow(self) -> Workflow | None:
        if not self.active_workflow_id:
            return None

        for workflow in self.workflows:
            if workflow.id == self.active_workflow_id:
                return workflow
        return None

    def load_graph_for_active_workflow(self):
        workflow = self.get_active_workflow()
        if not workflow:
            self.nodes = []
            self.edges = []
            self.selected_node_id = None
            self.selected_node_ids = set()
            self.pending_link_source_id = None
            self.clear_preflight_annotations()
            self.load_graph_settings({})
            self.refresh_canvas()
            self.clear_inspector()
            self.refresh_workflow_run_state(quiet=True)
            return

        graph = workflow.normalized_graph()
        self.nodes = self.parse_nodes(graph)
        self.edges = self.parse_edges(graph)
        if not self.edges and len(self.nodes) >= 2:
            inferred = self.auto_wire_nodes(strict_two_node=False)
            if inferred > 0:
                self.workflow_store.update_workflow_graph(
                    workflow.id,
                    self.build_graph_payload(),
                )
                self.set_status(
                    f"Recovered {inferred} link(s) for '{workflow.name}' from an unlinked graph."
                )
        self.selected_node_id = None
        self.selected_node_ids = set()
        self.pending_link_source_id = None
        self.reset_history()
        self.load_graph_settings(graph)

        self.refresh_canvas()
        self.inline_validate_graph()
        self.clear_inspector()
        self.refresh_workflow_run_state(quiet=True)
        if self.nodes:
            self.set_status(
                f"Loaded graph for '{workflow.name}'. Select a node to edit its settings."
            )
        else:
            self.set_status(f"Workflow '{workflow.name}' has an empty graph. Add nodes and save.")

        self.update_control_state()

    def parse_nodes(self, graph: dict) -> list[CanvasNode]:
        parsed: list[CanvasNode] = []
        for item in graph.get("nodes", []):
            if not isinstance(item, dict):
                continue
            node = CanvasNode.from_dict(item)
            if node.id:
                parsed.append(node)
        return parsed

    def parse_edges(self, graph: dict) -> list[CanvasEdge]:
        parsed: list[CanvasEdge] = []
        seen_signatures: set[tuple[str, str, str]] = set()
        raw_edges = graph.get("edges", [])
        if not isinstance(raw_edges, list):
            raw_edges = []
        legacy_links = graph.get("links", [])
        if isinstance(legacy_links, list):
            raw_edges = [*raw_edges, *legacy_links]

        for item in raw_edges:
            if not isinstance(item, dict):
                continue
            source_id = str(
                item.get("source_node_id")
                or item.get("source")
                or item.get("source_id")
                or item.get("from")
                or ""
            ).strip()
            target_id = str(
                item.get("target_node_id")
                or item.get("target")
                or item.get("target_id")
                or item.get("to")
                or ""
            ).strip()
            if not source_id or not target_id:
                continue

            condition_raw = str(
                item.get("condition")
                or item.get("link_type")
                or item.get("type")
                or ""
            ).strip().lower()
            condition = condition_raw if condition_raw in {"true", "false"} else ""
            signature = (source_id, target_id, condition)
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)

            edge_id = str(item.get("id", "")).strip() or str(uuid.uuid4())
            parsed.append(
                CanvasEdge(
                    id=edge_id,
                    source_node_id=source_id,
                    target_node_id=target_id,
                    condition=condition,
                )
            )
        return parsed

    def update_control_state(self):
        has_workflow = self.active_workflow_id is not None
        has_selected = self.get_selected_node() is not None
        selected_count = len(self.selected_node_ids)
        if selected_count == 0 and has_selected:
            selected_count = 1

        for button in [
            self.add_trigger_button,
            self.add_action_button,
            self.add_ai_button,
            self.add_condition_button,
            self.run_workflow_button,
            self.cancel_run_button,
            self.retry_failed_button,
            self.resume_run_button,
            self.refresh_run_state_button,
            self.start_link_button,
            self.auto_wire_button,
            self.delete_selected_button,
            self.save_graph_button,
            self.preflight_button,
            self.clear_button,
        ]:
            button.set_sensitive(has_workflow)

        self.link_type_dropdown.set_sensitive(has_workflow)
        self.graph_retry_spin.set_sensitive(has_workflow)
        self.graph_backoff_spin.set_sensitive(has_workflow)
        self.graph_timeout_spin.set_sensitive(has_workflow)
        for button in self.execution_preset_buttons.values():
            button.set_sensitive(has_workflow)
        can_cancel_run = (
            bool(self.latest_workflow_run_id)
            and self.latest_workflow_run_status in {"running", "waiting_approval"}
        )
        can_retry_failed = (
            bool(self.latest_workflow_run_id)
            and self.latest_workflow_run_status == "failed"
            and bool(self.latest_workflow_run_failed_node_id)
        )
        can_resume_approval = (
            bool(self.latest_workflow_run_id)
            and self.latest_workflow_run_status == "waiting_approval"
            and bool(self.latest_workflow_run_pending_approval_node_id)
        )
        self.cancel_run_button.set_sensitive(has_workflow and can_cancel_run)
        self.retry_failed_button.set_sensitive(has_workflow and can_retry_failed)
        self.resume_run_button.set_sensitive(has_workflow and can_resume_approval)
        self.delete_selected_button.set_sensitive(has_workflow and has_selected)
        self.apply_node_button.set_sensitive(has_workflow and has_selected)
        self.add_template_button.set_sensitive(has_workflow and bool(self.templates))
        self.refresh_templates_button.set_sensitive(True)
        self.undo_button.set_sensitive(has_workflow and len(self.undo_stack) > 0)
        self.redo_button.set_sensitive(has_workflow and len(self.redo_stack) > 0)
        self.align_left_button.set_sensitive(has_workflow and selected_count > 1)
        self.align_row_button.set_sensitive(has_workflow and selected_count > 1)
        self.distribute_x_button.set_sensitive(has_workflow and selected_count > 2)
        self.snap_grid_button.set_sensitive(has_workflow and selected_count > 0)

        for field in [
            self.edit_name_entry,
            self.edit_summary_entry,
            self.edit_detail_view,
            self.trigger_mode_dropdown,
            self.trigger_interval_scale,
            self.trigger_interval_spin,
            self.trigger_webhook_entry,
            self.trigger_watch_path_entry,
            self.trigger_cron_entry,
            self.trigger_value_entry,
            self.action_template_dropdown,
            self.action_template_apply_button,
            self.action_saved_defaults_button,
            self.action_integration_dropdown,
            self.action_preset_dropdown,
            self.action_preset_apply_button,
            self.action_endpoint_entry,
            self.action_message_entry,
            self.action_to_entry,
            self.action_from_entry,
            self.action_subject_entry,
            self.action_chat_id_entry,
            self.action_account_sid_entry,
            self.action_auth_token_entry,
            self.action_domain_entry,
            self.action_username_entry,
            self.action_payload_view,
            self.action_headers_entry,
            self.action_api_key_entry,
            self.action_location_entry,
            self.action_units_dropdown,
            self.action_path_entry,
            self.action_command_entry,
            self.action_timeout_spin,
            self.edit_provider_dropdown,
            self.edit_model_entry,
            self.edit_bot_entry,
            self.edit_bot_chain_entry,
            self.edit_system_entry,
            self.edit_temp_override_switch,
            self.edit_temp_scale,
            self.edit_temp_spin,
            self.edit_tokens_override_switch,
            self.edit_tokens_scale,
            self.edit_tokens_spin,
            self.edit_condition_mode_dropdown,
            self.edit_condition_value_entry,
            self.edit_condition_min_len_scale,
            self.edit_condition_min_len_spin,
            self.condition_preview_input_entry,
            self.node_retry_spin,
            self.node_backoff_spin,
            self.node_timeout_spin,
        ]:
            field.set_sensitive(has_workflow and has_selected)
        self.node_execution_defaults_button.set_sensitive(has_workflow and has_selected)
        for button in self.node_execution_preset_buttons.values():
            button.set_sensitive(has_workflow and has_selected)
        self.action_integration_section.set_sensitive(has_workflow and has_selected)
        selected = self.get_selected_node()
        selected_key = self.node_type_key(selected.node_type) if selected else ""
        can_test_node = selected_key in {"action", "template", "ai", "condition"}
        self.test_node_button.set_sensitive(has_workflow and has_selected and can_test_node)
        self.action_scaffold_button.set_sensitive(
            has_workflow and has_selected and selected_key in {"action", "template"}
        )
        self.configure_node_test_controls(selected.node_type if selected else None)
        self.refresh_condition_branch_preview()
        self.update_sidebar_mode()

    def add_node(
        self,
        name: str,
        node_type: str,
        detail: str,
        summary: str,
        x: int,
        y: int,
        config: dict[str, str] | None = None,
    ):
        previous_selected = self.selected_node_id
        self.push_undo_snapshot()
        node = CanvasNode(
            id=str(uuid.uuid4()),
            name=name,
            node_type=node_type,
            detail=detail,
            summary=summary,
            x=x,
            y=y,
            config=config or {},
        )
        self.nodes.append(node)
        auto_linked = False
        if previous_selected and previous_selected != node.id:
            if self.node_type_key(node.node_type) != "trigger":
                auto_linked = self.add_edge(
                    previous_selected,
                    node.id,
                    condition_override="",
                    push_history=False,
                    auto_save=False,
                    show_status_on_duplicate=False,
                )
        self.selected_node_id = node.id
        self.selected_node_ids = {node.id}
        self.refresh_canvas()
        self.update_inspector(node)
        if auto_linked:
            self.maybe_auto_save("Node added, auto-linked, and auto-saved.")
        else:
            self.maybe_auto_save("Node added and auto-saved.")
        self.inline_validate_graph()
        self.update_control_state()

    def on_add_trigger(self, _button):
        x, y = self.layout_service.next_position()
        self.add_node(
            name="New Trigger",
            node_type="Trigger",
            detail="trigger:manual",
            summary="Begins the workflow when its trigger condition is met.",
            x=x,
            y=y,
            config={
                "trigger_mode": "manual",
                "trigger_value": "",
            },
        )

    def on_add_action(self, _button):
        x, y = self.layout_service.next_position()
        self.add_node(
            name="New Action",
            node_type="Action",
            detail="integration:standard",
            summary="Performs a concrete workflow action.",
            x=x,
            y=y,
            config={
                "integration": "standard",
                "action_template": "generic_action",
                "method": "POST",
                "timeout_sec": "30.0",
            },
        )

    def on_add_ai(self, _button):
        x, y = self.layout_service.next_position()
        self.add_node(
            name="New AI Node",
            node_type="AI Node",
            detail="prompt: Process the incoming workflow context.",
            summary="Processes content with local or cloud AI.",
            x=x,
            y=y,
            config={
                "provider": "inherit",
            },
        )

    def on_add_condition(self, _button):
        x, y = self.layout_service.next_position()
        self.add_node(
            name="New Condition",
            node_type="Condition",
            detail="contains:success",
            summary="Evaluates logic and routes workflow branches.",
            x=x,
            y=y,
            config={
                "expression": "contains:success",
            },
        )

    def on_add_template_node(self, _button):
        if not self.templates or not self.template_dropdown:
            self.set_status("No templates available. Install one in Template Marketplace.")
            return

        selected = self.template_dropdown.get_selected()
        if selected < 0 or selected >= len(self.templates):
            self.set_status("Select a valid template first.")
            return

        template = self.templates[selected]
        x, y = self.layout_service.next_position()
        self.add_node(
            name=template.get("name", "Template Node"),
            node_type=template.get("node_type", "Action"),
            detail=template.get("detail", ""),
            summary=template.get("summary", ""),
            x=x,
            y=y,
            config=template.get("config", {}),
        )
        self.set_status(f"Template node '{template.get('name', 'Template')}' added.")

    def on_start_link(self, _button):
        selected = self.get_selected_node()
        if not selected:
            self.set_status("Select a source node first, then click Start Link.")
            return

        if self.pending_link_source_id == selected.id:
            previous_source = self.pending_link_source_id
            self.cancel_link_preview()
            self.pending_link_source_id = None
            self.apply_link_source_visual_state(previous_source, None)
            self.set_status("Link mode canceled.")
            return

        previous_source = self.pending_link_source_id
        self.pending_link_source_id = selected.id
        self.begin_link_preview(selected.id)
        self.apply_link_source_visual_state(previous_source, selected.id)
        self.link_layer.queue_draw()
        link_type = self.get_selected_link_type()
        self.set_status(
            f"Link mode active from '{selected.name}' as '{link_type}'. Select a target node."
        )

    def get_selected_link_type(self) -> str:
        index = self.link_type_dropdown.get_selected()
        if 0 <= index < len(self.LINK_TYPES):
            return self.LINK_TYPES[index]
        return "next"

    def get_selected_link_condition(self) -> str:
        link_type = self.get_selected_link_type()
        return "" if link_type == "next" else link_type

    def validate_current_graph(self):
        workflow = self.get_active_workflow()
        workflow_name = workflow.name if workflow else "Workflow"
        return self.validation_service.validate_graph(
            self.nodes,
            self.edges,
            workflow_name,
        )

    def inline_validate_graph(self):
        if not self.active_workflow_id or not self.nodes:
            self.clear_preflight_annotations()
            return None
        result = self.validate_current_graph()
        self.apply_preflight_annotations(result)
        return result

    def graph_history_state(self) -> dict:
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "settings": self.collect_graph_settings(),
        }

    def graph_history_signature(self, state: dict) -> str:
        try:
            return json.dumps(state, sort_keys=True)
        except Exception:
            return str(state)

    def reset_history(self):
        self.undo_stack = []
        self.redo_stack = []

    def push_undo_snapshot(self):
        if self.history_restoring or not self.active_workflow_id:
            return

        snapshot = self.graph_history_state()
        if self.undo_stack:
            previous_signature = self.graph_history_signature(self.undo_stack[-1])
            current_signature = self.graph_history_signature(snapshot)
            if previous_signature == current_signature:
                return

        self.undo_stack.append(snapshot)
        if len(self.undo_stack) > self.max_history_entries:
            self.undo_stack = self.undo_stack[-self.max_history_entries :]
        self.redo_stack = []
        self.update_control_state()

    def persist_graph_if_auto_save(self):
        if not self.active_workflow_id or not self.should_auto_save():
            return
        self.workflow_store.update_workflow_graph(
            self.active_workflow_id,
            self.build_graph_payload(),
        )

    def restore_graph_from_history(self, state: dict):
        graph = {
            "version": 1,
            "nodes": state.get("nodes", []),
            "edges": state.get("edges", []),
            "settings": state.get("settings", {}),
        }
        self.history_restoring = True
        try:
            self.nodes = self.parse_nodes(graph)
            self.edges = self.parse_edges(graph)
            self.selected_node_id = None
            self.selected_node_ids = set()
            self.pending_link_source_id = None
            self.load_graph_settings(graph)
            self.refresh_canvas()
            self.inline_validate_graph()
            self.clear_inspector()
            self.update_control_state()
        finally:
            self.history_restoring = False

    def on_undo_clicked(self, _button):
        if not self.undo_stack:
            self.set_status("Nothing to undo.")
            return
        current_state = self.graph_history_state()
        target_state = self.undo_stack.pop()
        self.redo_stack.append(current_state)
        self.restore_graph_from_history(target_state)
        self.persist_graph_if_auto_save()
        self.set_status("Undo applied.")

    def on_redo_clicked(self, _button):
        if not self.redo_stack:
            self.set_status("Nothing to redo.")
            return
        current_state = self.graph_history_state()
        target_state = self.redo_stack.pop()
        self.undo_stack.append(current_state)
        self.restore_graph_from_history(target_state)
        self.persist_graph_if_auto_save()
        self.set_status("Redo applied.")

    def selected_nodes(self) -> list[CanvasNode]:
        node_ids = set(self.selected_node_ids)
        if not node_ids and self.selected_node_id:
            node_ids = {self.selected_node_id}
        return [node for node in self.nodes if node.id in node_ids]

    def on_align_left_clicked(self, _button):
        selected_nodes = self.selected_nodes()
        if len(selected_nodes) < 2:
            self.set_status("Select at least two nodes to align.")
            return
        self.push_undo_snapshot()
        target_x = min(node.x for node in selected_nodes)
        for node in selected_nodes:
            node.x = max(0, min(self.STAGE_WIDTH - self.CARD_WIDTH, int(target_x)))
        self.refresh_canvas()
        self.inline_validate_graph()
        focus = self.get_selected_node()
        if focus:
            self.update_inspector(focus)
        self.persist_graph_if_auto_save()
        self.set_status("Aligned selected nodes to the left edge.")
        self.update_control_state()

    def on_align_row_clicked(self, _button):
        selected_nodes = self.selected_nodes()
        if len(selected_nodes) < 2:
            self.set_status("Select at least two nodes to align.")
            return
        anchor = self.get_selected_node() or selected_nodes[0]
        target_y = anchor.y
        self.push_undo_snapshot()
        for node in selected_nodes:
            node.y = max(0, min(self.STAGE_HEIGHT - self.CARD_HEIGHT, int(target_y)))
        self.refresh_canvas()
        self.inline_validate_graph()
        focus = self.get_selected_node()
        if focus:
            self.update_inspector(focus)
        self.persist_graph_if_auto_save()
        self.set_status("Aligned selected nodes into one row.")
        self.update_control_state()

    def on_distribute_x_clicked(self, _button):
        selected_nodes = sorted(self.selected_nodes(), key=lambda node: node.x)
        if len(selected_nodes) < 3:
            self.set_status("Select at least three nodes to distribute.")
            return

        left_x = selected_nodes[0].x
        right_x = selected_nodes[-1].x
        if right_x <= left_x:
            self.set_status("Distribute requires nodes with different horizontal positions.")
            return

        self.push_undo_snapshot()
        slots = len(selected_nodes) - 1
        span = float(right_x - left_x)
        for index, node in enumerate(selected_nodes):
            target_x = left_x + int(round((span * index) / slots))
            snapped = round(target_x / self.SNAP_GRID) * self.SNAP_GRID
            node.x = max(0, min(self.STAGE_WIDTH - self.CARD_WIDTH, int(snapped)))

        self.refresh_canvas()
        self.inline_validate_graph()
        focus = self.get_selected_node()
        if focus:
            self.update_inspector(focus)
        self.persist_graph_if_auto_save()
        self.set_status("Distributed selected nodes horizontally.")
        self.update_control_state()

    def on_snap_grid_clicked(self, _button):
        selected_nodes = self.selected_nodes()
        if not selected_nodes:
            self.set_status("Select at least one node to snap to grid.")
            return

        self.push_undo_snapshot()
        max_x = max(0, self.STAGE_WIDTH - self.CARD_WIDTH)
        max_y = max(0, self.STAGE_HEIGHT - self.CARD_HEIGHT)
        for node in selected_nodes:
            snapped_x = round(node.x / self.SNAP_GRID) * self.SNAP_GRID
            snapped_y = round(node.y / self.SNAP_GRID) * self.SNAP_GRID
            node.x = max(0, min(max_x, int(snapped_x)))
            node.y = max(0, min(max_y, int(snapped_y)))

        self.refresh_canvas()
        self.inline_validate_graph()
        focus = self.get_selected_node()
        if focus:
            self.update_inspector(focus)
        self.persist_graph_if_auto_save()
        self.set_status("Snapped selected nodes to grid.")
        self.update_control_state()

    def add_edge(
        self,
        source_node_id: str,
        target_node_id: str,
        *,
        condition_override: str | None = None,
        push_history: bool = True,
        auto_save: bool = True,
        show_status_on_duplicate: bool = True,
    ) -> bool:
        if source_node_id == target_node_id:
            self.set_status("Cannot link a node to itself.")
            return False

        source_node = self.find_node(source_node_id)
        target_node = self.find_node(target_node_id)
        if not source_node or not target_node:
            self.set_status("Link failed because source or target node was not found.")
            return False
        if self.node_type_key(target_node.node_type) == "trigger":
            self.set_status("Trigger nodes cannot be used as link targets.")
            return False

        condition = (
            str(condition_override).strip().lower()
            if condition_override is not None
            else self.get_selected_link_condition()
        )
        if condition not in {"", "true", "false"}:
            condition = ""

        for edge in self.edges:
            if (
                edge.source_node_id == source_node_id
                and edge.target_node_id == target_node_id
                and edge.condition == condition
            ):
                if show_status_on_duplicate:
                    self.set_status("That link already exists.")
                return False

        if push_history:
            self.push_undo_snapshot()
        self.edges.append(
            CanvasEdge(
                id=str(uuid.uuid4()),
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                condition=condition,
            )
        )
        self.inline_validate_graph()
        self.link_layer.queue_draw()
        if auto_save:
            self.maybe_auto_save("Link added and auto-saved.")
        return True

    def ordered_nodes_for_auto_wire(self) -> list[CanvasNode]:
        if not self.nodes:
            return []
        triggers = [node for node in self.nodes if self.node_type_key(node.node_type) == "trigger"]
        non_triggers = [node for node in self.nodes if self.node_type_key(node.node_type) != "trigger"]
        if triggers:
            anchor = triggers[0]
            ordered = [anchor, *[node for node in non_triggers if node.id != anchor.id]]
            extras = [node for node in triggers[1:] if node.id != anchor.id]
            ordered.extend(extras)
            return ordered
        return list(self.nodes)

    def auto_wire_nodes(self, strict_two_node: bool = False) -> int:
        ordered_nodes = self.ordered_nodes_for_auto_wire()
        if strict_two_node and len(ordered_nodes) != 2:
            return 0
        if len(ordered_nodes) < 2:
            return 0

        created = 0
        current_source = ordered_nodes[0]
        for target in ordered_nodes[1:]:
            if self.node_type_key(target.node_type) == "trigger":
                current_source = target
                continue
            if self.add_edge(
                current_source.id,
                target.id,
                condition_override="",
                push_history=False,
                auto_save=False,
                show_status_on_duplicate=False,
            ):
                created += 1
            current_source = target
        return created

    def on_auto_wire(self, _button):
        if not self.active_workflow_id:
            self.set_status("Select a workflow first.")
            return
        if len(self.nodes) < 2:
            self.set_status("Add at least two nodes before auto-wiring.")
            return

        self.push_undo_snapshot()
        created = self.auto_wire_nodes(strict_two_node=False)
        self.refresh_canvas()
        self.inline_validate_graph()
        self.update_control_state()

        if created <= 0:
            self.set_status("No new links were created. Nodes may already be connected.")
            return

        self.maybe_auto_save(f"Auto-wired {created} link(s) and auto-saved.")

    def begin_link_preview(self, source_node_id: str):
        source = self.find_node(source_node_id)
        if not source:
            return
        start_x, start_y = self.node_output_anchor(source)
        self.link_preview_source_id = source_node_id
        self.link_preview_end_x = start_x
        self.link_preview_end_y = start_y
        self.set_link_hover_target(None)
        self.link_layer.queue_draw()

    def update_link_preview_position(self, x: int, y: int):
        if not self.link_preview_source_id:
            return
        self.link_preview_end_x = max(0, x)
        self.link_preview_end_y = max(0, y)
        self.link_layer.queue_draw()

    def cancel_link_preview(self):
        self.link_preview_source_id = None
        self.link_preview_end_x = 0
        self.link_preview_end_y = 0
        self.port_drag_active = False
        self.port_drag_origin = {}
        self.set_link_hover_target(None)
        self.link_layer.queue_draw()

    def set_link_hover_target(self, node_id: str | None):
        previous = self.link_hover_target_id
        if previous == node_id:
            return

        if previous:
            previous_widget = self.node_widgets.get(previous)
            if previous_widget:
                previous_widget.remove_css_class("canvas-node-link-target")

        self.link_hover_target_id = node_id

        if node_id:
            current_widget = self.node_widgets.get(node_id)
            if current_widget:
                current_widget.add_css_class("canvas-node-link-target")
        self.link_layer.queue_draw()

    def valid_link_target_at(self, x: int, y: int, source_id: str | None) -> CanvasNode | None:
        if not source_id:
            return None
        target = self.find_node_at_point(x, y, exclude_node_id=source_id)
        if not target:
            target = self.find_nearest_link_target(
                x,
                y,
                source_id,
                max_distance=self.LINK_TARGET_SNAP_DISTANCE,
            )
        if not target:
            return None
        if self.node_type_key(target.node_type) == "trigger":
            return None
        return target

    def find_nearest_link_target(
        self,
        x: int,
        y: int,
        source_id: str,
        *,
        max_distance: int,
    ) -> CanvasNode | None:
        best_node: CanvasNode | None = None
        best_distance = float(max_distance) + 0.01

        for node in self.nodes:
            if node.id == source_id:
                continue
            if self.node_type_key(node.node_type) == "trigger":
                continue

            input_x, input_y = self.node_input_anchor(node)
            delta_x = float(int(x) - int(input_x))
            delta_y = float(int(y) - int(input_y))
            distance = math.sqrt((delta_x * delta_x) + (delta_y * delta_y))

            if distance < best_distance:
                best_distance = distance
                best_node = node

        return best_node

    def finalize_link_preview_at(self, end_x: int, end_y: int):
        source_id = self.link_preview_source_id or self.pending_link_source_id
        if not source_id:
            return

        target = self.valid_link_target_at(end_x, end_y, source_id) or (
            self.find_node(self.link_hover_target_id) if self.link_hover_target_id else None
        )
        source = self.find_node(source_id)
        previous_source = self.pending_link_source_id

        if target and self.add_edge(source_id, target.id):
            previous_selected = self.selected_node_id
            self.set_single_selection(target.id)
            self.pending_link_source_id = None
            self.cancel_link_preview()
            self.apply_selection_visual_state(previous_selected, target.id)
            self.apply_link_source_visual_state(previous_source, None)
            self.update_inspector(target)
            self.update_control_state()
            if source:
                self.set_status(f"Linked '{source.name}' -> '{target.name}'.")
            return

        self.pending_link_source_id = None
        self.cancel_link_preview()
        self.apply_link_source_visual_state(previous_source, None)
        self.update_control_state()
        self.set_status("Link canceled. Drop on a different node.")

    def on_delete_selected(self, _button):
        selected_ids = set(self.selected_node_ids)
        if not selected_ids and self.selected_node_id:
            selected_ids = {self.selected_node_id}
        if not selected_ids:
            return

        self.push_undo_snapshot()
        self.nodes = [node for node in self.nodes if node.id not in selected_ids]
        self.edges = [
            edge
            for edge in self.edges
            if edge.source_node_id not in selected_ids and edge.target_node_id not in selected_ids
        ]
        removed_count = len(selected_ids)
        self.selected_node_id = None
        self.selected_node_ids = set()
        self.pending_link_source_id = None

        self.refresh_canvas()
        self.link_layer.queue_draw()

        self.clear_inspector()

        self.maybe_auto_save(f"{removed_count} node(s) removed and auto-saved.")
        self.inline_validate_graph()
        self.update_control_state()

    def on_clear_canvas(self, _button):
        if self.nodes or self.edges:
            self.push_undo_snapshot()
        self.nodes = []
        self.edges = []
        self.selected_node_id = None
        self.selected_node_ids = set()
        self.pending_link_source_id = None
        self.clear_preflight_annotations()
        self.refresh_canvas()
        self.clear_inspector()
        self.maybe_auto_save("Canvas cleared and auto-saved.")
        self.update_control_state()

    def collect_graph_settings(self) -> dict:
        preset = self.current_execution_preset()
        return {
            "retry_max": self.graph_retry_spin.get_value_as_int(),
            "retry_backoff_ms": self.graph_backoff_spin.get_value_as_int(),
            "timeout_sec": round(self.graph_timeout_spin.get_value(), 1),
            "execution_preset": preset,
        }

    def load_graph_settings(self, graph: dict):
        settings = graph.get("settings", {}) if isinstance(graph, dict) else {}
        if not isinstance(settings, dict):
            settings = {}
        default = self.EXECUTION_PRESETS["balanced"]

        self.loading_graph_settings = True
        self.graph_retry_spin.set_value(
            float(
                self.parse_int(
                    settings.get("retry_max", default.get("retry_max", 1)),
                    self.parse_int(default.get("retry_max", 1), 1),
                )
            )
        )
        self.graph_backoff_spin.set_value(
            float(
                self.parse_int(
                    settings.get("retry_backoff_ms", default.get("retry_backoff_ms", 250)),
                    self.parse_int(default.get("retry_backoff_ms", 250), 250),
                )
            )
        )
        self.graph_timeout_spin.set_value(
            self.parse_float(
                settings.get("timeout_sec", default.get("timeout_sec", 60.0)),
                self.parse_float(default.get("timeout_sec", 60.0), 60.0),
            )
        )
        self.sync_execution_preset_buttons()
        self.loading_graph_settings = False

    def on_graph_execution_setting_changed(self, _spin):
        if self.loading_graph_settings:
            return
        self.sync_execution_preset_buttons()
        self.inline_validate_graph()
        if self.active_workflow_id:
            self.maybe_auto_save("Execution defaults updated and auto-saved.")

    def on_execution_preset_toggled(self, button: Gtk.ToggleButton, key: str):
        if self.loading_graph_settings:
            return
        if not button.get_active():
            return

        for other_key, other_button in self.execution_preset_buttons.items():
            if other_key != key and other_button.get_active():
                self.loading_graph_settings = True
                other_button.set_active(False)
                self.loading_graph_settings = False

        preset = self.EXECUTION_PRESETS.get(key, {})
        self.loading_graph_settings = True
        self.graph_retry_spin.set_value(float(self.parse_int(preset.get("retry_max", 0), 0)))
        self.graph_backoff_spin.set_value(
            float(self.parse_int(preset.get("retry_backoff_ms", 250), 250))
        )
        self.graph_timeout_spin.set_value(self.parse_float(preset.get("timeout_sec", 60.0), 60.0))
        self.loading_graph_settings = False
        self.inline_validate_graph()
        if self.active_workflow_id:
            self.maybe_auto_save(f"Execution preset '{key}' applied and auto-saved.")

    def current_execution_preset(self) -> str:
        retry = self.graph_retry_spin.get_value_as_int()
        backoff = self.graph_backoff_spin.get_value_as_int()
        timeout = round(self.graph_timeout_spin.get_value(), 1)

        for key, preset in self.EXECUTION_PRESETS.items():
            if (
                retry == self.parse_int(preset.get("retry_max", 0), 0)
                and backoff == self.parse_int(preset.get("retry_backoff_ms", 250), 250)
                and abs(timeout - self.parse_float(preset.get("timeout_sec", 60.0), 60.0)) < 0.05
            ):
                return key
        return "custom"

    def sync_execution_preset_buttons(self):
        active = self.current_execution_preset()
        self.loading_graph_settings = True
        for key, button in self.execution_preset_buttons.items():
            button.set_active(key == active)
        self.loading_graph_settings = False

    def build_graph_payload(self) -> dict:
        return {
            "version": 1,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "settings": self.collect_graph_settings(),
        }

    def on_save_graph(self, _button):
        if not self.active_workflow_id:
            self.set_status("Select a workflow before saving.")
            return

        validation = self.validate_current_graph()
        self.apply_preflight_annotations(validation)
        if not validation.ok:
            preview = " | ".join(validation.errors[:2])
            self.set_status(
                f"Save blocked: fix {len(validation.errors)} validation error(s). {preview}"
            )
            return

        graph = self.build_graph_payload()
        saved = self.workflow_store.update_workflow_graph(self.active_workflow_id, graph)

        if saved:
            if validation.warnings:
                warning_preview = " | ".join(validation.warnings[:2])
                self.set_status(
                    f"Canvas graph saved with {len(validation.warnings)} warning(s). {warning_preview}"
                )
            else:
                self.set_status("Canvas graph saved to workflow.")
            self.reload_workflows()
            return

        self.set_status("Failed to save graph. Try refreshing workflows.")

    def on_run_preflight_check(self, _button):
        workflow = self.get_active_workflow()
        if not workflow:
            self.set_status("Select a workflow before running preflight.")
            return

        candidate = Workflow(
            id=workflow.id,
            name=workflow.name,
            trigger=workflow.trigger,
            action=workflow.action,
            graph=self.build_graph_payload(),
        )
        result = self.validation_service.validate_workflow(candidate)
        self.apply_preflight_annotations(result)

        error_node_count = len(self.preflight_error_node_ids)
        warning_node_count = len(self.preflight_warning_node_ids)
        error_edge_count = len(
            {f"id:{item}" for item in self.preflight_error_edge_ids}
            | {f"pair:{item}" for item in self.preflight_error_edge_pairs}
        )
        warning_edge_count = len(
            {f"id:{item}" for item in self.preflight_warning_edge_ids}
            | {f"pair:{item}" for item in self.preflight_warning_edge_pairs}
        )

        if result.ok and not result.warnings:
            self.set_status("Preflight passed. Graph is ready to execute.")
            return
        if result.ok and result.warnings:
            warning_preview = " | ".join(result.warnings[:2])
            self.set_status(
                f"Preflight passed with warnings ({warning_node_count} node, {warning_edge_count} edge): {warning_preview}"
            )
            return

        preview = " | ".join(result.errors[:2])
        self.set_status(
            f"Preflight failed with {len(result.errors)} error(s) [{error_node_count} node, {error_edge_count} edge]. {preview}"
        )

    def clear_preflight_annotations(self):
        self.preflight_error_node_ids.clear()
        self.preflight_warning_node_ids.clear()
        self.preflight_error_edge_ids.clear()
        self.preflight_warning_edge_ids.clear()
        self.preflight_error_edge_pairs.clear()
        self.preflight_warning_edge_pairs.clear()
        self.preflight_issue_items = []
        self.render_preflight_issue_list()

    def apply_preflight_annotations(self, result):
        self.clear_preflight_annotations()
        for issue in getattr(result, "issues", []):
            severity = str(getattr(issue, "severity", "")).strip().lower()
            node_id = str(getattr(issue, "node_id", "")).strip()
            edge_id = str(getattr(issue, "edge_id", "")).strip()
            source = str(getattr(issue, "source_node_id", "")).strip()
            target = str(getattr(issue, "target_node_id", "")).strip()
            pair = self.edge_pair_key(source, target) if source and target else ""

            if severity == "error":
                if node_id:
                    self.preflight_error_node_ids.add(node_id)
                if edge_id:
                    self.preflight_error_edge_ids.add(edge_id)
                if pair:
                    self.preflight_error_edge_pairs.add(pair)
            elif severity == "warning":
                if node_id and node_id not in self.preflight_error_node_ids:
                    self.preflight_warning_node_ids.add(node_id)
                if edge_id and edge_id not in self.preflight_error_edge_ids:
                    self.preflight_warning_edge_ids.add(edge_id)
                if pair and pair not in self.preflight_error_edge_pairs:
                    self.preflight_warning_edge_pairs.add(pair)

        self.preflight_issue_items = [
            {
                "severity": str(getattr(issue, "severity", "")).strip().lower(),
                "message": str(getattr(issue, "message", "")).strip(),
                "node_id": str(getattr(issue, "node_id", "")).strip(),
                "edge_id": str(getattr(issue, "edge_id", "")).strip(),
                "source_node_id": str(getattr(issue, "source_node_id", "")).strip(),
                "target_node_id": str(getattr(issue, "target_node_id", "")).strip(),
            }
            for issue in getattr(result, "issues", [])
        ]
        self.render_preflight_issue_list()
        self.refresh_canvas()
        self.link_layer.queue_draw()

    def render_preflight_issue_list(self):
        child = self.preflight_issue_list.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.preflight_issue_list.remove(child)
            child = next_child

        if not self.preflight_issue_items:
            self.preflight_issue_summary.set_text(
                "Run preflight to detect node and link issues before execution."
            )
            empty = Gtk.Label(label="No preflight issues.")
            empty.set_halign(Gtk.Align.START)
            empty.add_css_class("dim-label")
            empty.add_css_class("empty-state-label")
            self.preflight_issue_list.append(empty)
            return

        errors = [item for item in self.preflight_issue_items if item.get("severity") == "error"]
        warnings = [item for item in self.preflight_issue_items if item.get("severity") == "warning"]
        self.preflight_issue_summary.set_text(
            f"{len(errors)} error(s), {len(warnings)} warning(s). Click an issue to jump."
        )

        for index, issue in enumerate(self.preflight_issue_items[:24]):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            row.add_css_class("preflight-issue-row")

            severity = issue.get("severity", "warning")
            severity_label = Gtk.Label(label="ERR" if severity == "error" else "WARN")
            severity_label.add_css_class("preflight-issue-severity")
            severity_label.add_css_class(
                "preflight-issue-error" if severity == "error" else "preflight-issue-warning"
            )

            message = issue.get("message", "").strip()
            if len(message) > 84:
                message = f"{message[:81]}..."
            message_label = Gtk.Label(label=message or "Issue")
            message_label.set_wrap(True)
            message_label.set_halign(Gtk.Align.START)
            message_label.set_hexpand(True)
            message_label.add_css_class("dim-label")

            focus_button = Gtk.Button(label="Go")
            focus_button.add_css_class("compact-action-button")
            focus_button.connect("clicked", self.on_focus_preflight_issue, index)

            row.append(severity_label)
            row.append(message_label)
            row.append(focus_button)
            self.preflight_issue_list.append(row)

    def on_focus_preflight_issue(self, _button, issue_index: int):
        if issue_index < 0 or issue_index >= len(self.preflight_issue_items):
            return

        issue = self.preflight_issue_items[issue_index]
        node_id = issue.get("node_id", "").strip()
        source_node_id = issue.get("source_node_id", "").strip()
        target_node_id = issue.get("target_node_id", "").strip()
        focus_node_id = node_id or source_node_id or target_node_id
        if not focus_node_id:
            self.set_status(issue.get("message", "Issue selected."))
            return

        node = self.find_node(focus_node_id)
        if not node:
            self.set_status("Issue references a node that is not present in this graph.")
            return

        self.selected_node_id = node.id
        self.ensure_node_visible(node)
        self.refresh_canvas()
        self.update_inspector(node)
        self.update_control_state()
        self.set_status(issue.get("message", "Focused preflight issue."))

    def edge_pair_key(self, source_node_id: str, target_node_id: str) -> str:
        source = str(source_node_id).strip()
        target = str(target_node_id).strip()
        if not source or not target:
            return ""
        return f"{source}->{target}"

    def edge_has_issue(self, edge: CanvasEdge, severity: str) -> bool:
        edge_id = str(edge.id).strip()
        pair = self.edge_pair_key(edge.source_node_id, edge.target_node_id)
        normalized = severity.strip().lower()

        if normalized == "error":
            return edge_id in self.preflight_error_edge_ids or pair in self.preflight_error_edge_pairs
        if normalized == "warning":
            if edge_id in self.preflight_error_edge_ids or pair in self.preflight_error_edge_pairs:
                return False
            return (
                edge_id in self.preflight_warning_edge_ids
                or pair in self.preflight_warning_edge_pairs
            )
        return False

    def should_auto_save(self) -> bool:
        settings = self.settings_store.load_settings()
        return bool(settings.get("auto_save_workflows", True))

    def maybe_auto_save(self, success_message: str):
        if not self.should_auto_save():
            self.set_status("Graph changed. Auto-save is off, use Save Graph to persist.")
            return

        if not self.active_workflow_id:
            return

        saved = self.workflow_store.update_workflow_graph(
            self.active_workflow_id, self.build_graph_payload()
        )
        if saved:
            self.set_status(success_message)
        else:
            self.set_status("Graph changed, but auto-save failed. Use Save Graph.")

    def refresh_canvas(self):
        self.hovered_port_node_id = None
        self.hovered_port_kind = None
        self.update_stage_dimensions()

        child = self.fixed.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.fixed.remove(child)
            child = next_child

        self.node_widgets = {}
        for node in self.nodes:
            widget = self.create_node_card(node)
            self.node_widgets[node.id] = widget
            self.fixed.put(widget, self.to_screen(node.x), self.to_screen(node.y))

        self.link_layer.queue_draw()
        if hasattr(self, "minimap_area") and self.minimap_area:
            self.minimap_area.queue_draw()

    def set_node_drag_cursor(self, cursor_name: str):
        for widget in self.node_widgets.values():
            if not widget:
                continue
            try:
                widget.set_cursor_from_name(cursor_name)
            except Exception:
                continue

    def create_node_card(self, node: CanvasNode) -> Gtk.Frame:
        frame = Gtk.Frame()
        frame.set_size_request(self.card_screen_width(), self.card_screen_height())
        frame.add_css_class("canvas-node-card")
        frame.add_css_class("canvas-node-draggable")
        node_kind = self.node_type_key(node.node_type)
        frame.add_css_class(f"canvas-node-{node_kind}")
        try:
            frame.set_cursor_from_name("grab")
        except Exception:
            pass

        if node.id in self.selected_node_ids:
            frame.add_css_class("canvas-node-selected")
        if self.selected_node_id == node.id:
            frame.add_css_class("canvas-node-primary")
        if self.pending_link_source_id == node.id or self.link_preview_source_id == node.id:
            frame.add_css_class("canvas-node-link-source")
        if self.link_hover_target_id == node.id:
            frame.add_css_class("canvas-node-link-target")
        if node.id in self.preflight_error_node_ids:
            frame.add_css_class("canvas-node-preflight-error")
        elif node.id in self.preflight_warning_node_ids:
            frame.add_css_class("canvas-node-preflight-warning")

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        content.add_css_class("canvas-node-content")
        content.set_margin_top(6)
        content.set_margin_bottom(6)
        content.set_margin_start(7)
        content.set_margin_end(7)

        chip_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        chip_row.set_halign(Gtk.Align.START)

        node_icon = create_icon(
            self.node_type_icon_name(node.node_type),
            css_class="node-kind-icon",
        )
        chip_row.append(node_icon)

        type_chip = Gtk.Label(label=self.node_type_chip_text(node.node_type))
        type_chip.add_css_class("node-kind-chip")
        type_chip.add_css_class(f"node-kind-{node_kind}")
        type_chip.set_halign(Gtk.Align.START)
        chip_row.append(type_chip)

        provider_override = str(node.config.get("provider", "")).strip().lower()
        if provider_override and provider_override != "inherit":
            provider_chip = Gtk.Label(label=provider_override.upper())
            provider_chip.add_css_class("node-provider-chip")
            provider_chip.set_halign(Gtk.Align.START)
            chip_row.append(provider_chip)

        if node.id in self.preflight_error_node_ids:
            issue_chip = Gtk.Label(label="ERROR")
            issue_chip.add_css_class("node-issue-chip")
            issue_chip.add_css_class("node-issue-error")
            chip_row.append(issue_chip)
        elif node.id in self.preflight_warning_node_ids:
            issue_chip = Gtk.Label(label="WARN")
            issue_chip.add_css_class("node-issue-chip")
            issue_chip.add_css_class("node-issue-warning")
            chip_row.append(issue_chip)

        name_label = Gtk.Label(label=node.name)
        name_label.add_css_class("title-4")
        name_label.add_css_class("canvas-node-title")
        name_label.set_halign(Gtk.Align.START)

        detail_preview = node.detail.strip() or node.summary.strip()
        if len(detail_preview) > 72:
            detail_preview = f"{detail_preview[:69]}..."
        detail_label = Gtk.Label(label=detail_preview)
        detail_label.set_wrap(True)
        detail_label.set_halign(Gtk.Align.START)
        detail_label.add_css_class("canvas-node-detail")

        port_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        port_row.set_halign(Gtk.Align.FILL)
        port_row.set_hexpand(True)
        port_row.add_css_class("canvas-port-row")

        input_port = Gtk.Label(label="●")
        input_port.add_css_class("canvas-node-port")
        input_port.add_css_class("canvas-node-port-in")
        input_port.add_css_class("canvas-node-port-dot")
        input_port.set_size_request(28, 28)
        input_port.set_can_target(True)
        input_port.set_halign(Gtk.Align.START)
        input_port.set_valign(Gtk.Align.CENTER)

        output_port = Gtk.Label(label="●")
        output_port.add_css_class("canvas-node-port")
        output_port.add_css_class("canvas-node-port-out")
        output_port.add_css_class("canvas-node-port-dot")
        output_port.set_size_request(28, 28)
        output_port.set_can_target(True)
        output_port.set_halign(Gtk.Align.END)
        output_port.set_valign(Gtk.Align.CENTER)

        self.attach_port_hover_controller(input_port, node.id, "in")
        self.attach_port_hover_controller(output_port, node.id, "out")

        port_spacer = Gtk.Box()
        port_spacer.set_hexpand(True)

        port_row.append(input_port)
        port_row.append(port_spacer)
        port_row.append(output_port)

        content.append(chip_row)
        content.append(name_label)
        content.append(detail_label)
        content.append(port_row)

        if self.pending_link_source_id == node.id:
            link_source_label = Gtk.Label(label="Link source active")
            link_source_label.set_halign(Gtk.Align.START)
            link_source_label.add_css_class("node-link-source-label")
            content.append(link_source_label)
        elif self.link_hover_target_id == node.id:
            link_target_label = Gtk.Label(label="Release to connect")
            link_target_label.set_halign(Gtk.Align.START)
            link_target_label.add_css_class("node-link-target-label")
            content.append(link_target_label)

        frame.set_child(content)

        output_drag = Gtk.GestureDrag()
        output_drag.set_button(Gdk.BUTTON_PRIMARY)
        output_drag.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        output_drag.set_exclusive(True)
        output_drag.connect("drag-begin", self.on_output_port_drag_begin, node.id, output_port)
        output_drag.connect("drag-update", self.on_output_port_drag_update, node.id, output_port)
        output_drag.connect("drag-end", self.on_output_port_drag_end, node.id, output_port)
        output_port.add_controller(output_drag)

        output_click = Gtk.GestureClick()
        output_click.set_button(Gdk.BUTTON_PRIMARY)
        output_click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        output_click.connect("released", self.on_output_port_released, node.id)
        output_port.add_controller(output_click)

        input_click = Gtk.GestureClick()
        input_click.set_button(Gdk.BUTTON_PRIMARY)
        input_click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        input_click.connect("released", self.on_input_port_released, node.id)
        input_port.add_controller(input_click)

        click = Gtk.GestureClick()
        click.set_button(Gdk.BUTTON_PRIMARY)
        click.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
        click.connect("released", self.on_node_clicked, node.id)
        frame.add_controller(click)

        drag = Gtk.GestureDrag()
        drag.set_button(Gdk.BUTTON_PRIMARY)
        drag.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
        drag.set_exclusive(True)
        drag.connect("drag-begin", self.on_node_drag_begin, node.id)
        drag.connect("drag-update", self.on_node_drag_update, node.id)
        drag.connect("drag-end", self.on_node_drag_end, node.id)
        frame.add_controller(drag)

        return frame

    def attach_port_hover_controller(self, port: Gtk.Widget, node_id: str, kind: str):
        motion = Gtk.EventControllerMotion()
        motion.connect("enter", self.on_port_hover_enter, node_id, kind, port)
        motion.connect("leave", self.on_port_hover_leave, node_id, kind, port)
        port.add_controller(motion)

    def on_port_hover_enter(
        self,
        _controller,
        _x: float,
        _y: float,
        node_id: str,
        kind: str,
        port: Gtk.Widget,
    ):
        self.hovered_port_node_id = node_id
        self.hovered_port_kind = kind
        port.add_css_class("canvas-node-port-hover")
        self.link_layer.queue_draw()

    def on_port_hover_leave(
        self,
        _controller,
        node_id: str,
        kind: str,
        port: Gtk.Widget,
    ):
        if self.hovered_port_node_id == node_id and self.hovered_port_kind == kind:
            self.hovered_port_node_id = None
            self.hovered_port_kind = None
        port.remove_css_class("canvas-node-port-hover")
        self.link_layer.queue_draw()

    def on_output_port_drag_begin(
        self,
        gesture,
        start_x: float,
        start_y: float,
        node_id: str,
        output_port: Gtk.Widget,
    ):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.port_drag_just_finished = False
        success, stage_x, stage_y = output_port.translate_coordinates(
            self.fixed,
            float(start_x),
            float(start_y),
        )
        self.begin_output_link_drag(
            node_id,
            pointer_x=float(stage_x) if success else None,
            pointer_y=float(stage_y) if success else None,
        )

    def begin_output_link_drag(
        self,
        node_id: str,
        *,
        pointer_x: float | None = None,
        pointer_y: float | None = None,
    ):
        self.grab_focus()
        self.node_drag_active = False
        self.drag_origin = {}
        self.drag_group_origins = {}
        self.port_drag_active = True
        anchor_x = 0.0
        anchor_y = 0.0
        source_node = self.find_node(node_id)
        if source_node:
            output_x, output_y = self.node_output_anchor(source_node)
            anchor_x = float(output_x)
            anchor_y = float(output_y)
        pointer_bias_x = 0.0
        pointer_bias_y = 0.0
        if pointer_x is not None and pointer_y is not None:
            pointer_bias_x = float(pointer_x) - anchor_x
            pointer_bias_y = float(pointer_y) - anchor_y
        self.port_drag_origin = {
            "anchor_x": anchor_x,
            "anchor_y": anchor_y,
            "pointer_bias_x": pointer_bias_x,
            "pointer_bias_y": pointer_bias_y,
        }
        previous_selected = self.selected_node_id
        previous_source = self.pending_link_source_id
        self.set_single_selection(node_id)
        self.pending_link_source_id = node_id
        self.set_link_hover_target(None)
        self.apply_selection_visual_state(previous_selected, node_id)
        self.apply_link_source_visual_state(previous_source, node_id)
        self.begin_link_preview(node_id)
        self.update_link_preview_position(int(anchor_x), int(anchor_y))
        selected = self.find_node(node_id)
        if selected:
            self.update_inspector(selected)
            link_type = self.get_selected_link_type()
            self.set_status(
                f"Link mode active from '{selected.name}' as '{link_type}'. Drag to target."
            )
        self.update_control_state()

    def on_output_port_drag_update(
        self,
        _gesture,
        offset_x: float,
        offset_y: float,
        node_id: str,
        _output_port: Gtk.Widget,
    ):
        if not self.port_drag_active:
            return

        anchor_x = float(self.port_drag_origin.get("anchor_x", 0.0))
        anchor_y = float(self.port_drag_origin.get("anchor_y", 0.0))
        bias_x = float(self.port_drag_origin.get("pointer_bias_x", 0.0))
        bias_y = float(self.port_drag_origin.get("pointer_bias_y", 0.0))
        x = int(anchor_x + bias_x + float(offset_x))
        y = int(anchor_y + bias_y + float(offset_y))
        source_id = self.link_preview_source_id or self.pending_link_source_id or node_id
        target = self.active_drag_target(source_id, x, y)
        if target:
            self.set_link_hover_target(target.id)
            snap_x, snap_y = self.node_input_anchor(target)
            self.update_link_preview_position(int(snap_x), int(snap_y))
        else:
            self.set_link_hover_target(None)
            self.update_link_preview_position(x, y)

    def on_output_port_drag_end(
        self,
        _gesture,
        offset_x: float,
        offset_y: float,
        _node_id: str,
        _output_port: Gtk.Widget,
    ):
        # Prefer the live preview endpoint so drag-release keeps the exact cursor target.
        end_x = int(self.link_preview_end_x)
        end_y = int(self.link_preview_end_y)
        if end_x <= 0 and end_y <= 0:
            anchor_x = float(self.port_drag_origin.get("anchor_x", 0.0))
            anchor_y = float(self.port_drag_origin.get("anchor_y", 0.0))
            bias_x = float(self.port_drag_origin.get("pointer_bias_x", 0.0))
            bias_y = float(self.port_drag_origin.get("pointer_bias_y", 0.0))
            end_x = int(anchor_x + bias_x + float(offset_x))
            end_y = int(anchor_y + bias_y + float(offset_y))
        source_id = self.link_preview_source_id or self.pending_link_source_id

        if self.port_drag_active:
            if source_id:
                hover_target = self.active_drag_target(source_id, end_x, end_y)
                if hover_target:
                    input_x, input_y = self.node_input_anchor(hover_target)
                    end_x = int(input_x)
                    end_y = int(input_y)
            self.finalize_link_preview_at(end_x, end_y)
        elif self.link_hover_target_id:
            hover_target = self.find_node(self.link_hover_target_id)
            if hover_target:
                input_x, input_y = self.node_input_anchor(hover_target)
                self.finalize_link_preview_at(int(input_x), int(input_y))
            else:
                previous_source = self.pending_link_source_id
                self.cancel_link_preview()
                self.pending_link_source_id = None
                self.apply_link_source_visual_state(previous_source, None)
                self.update_control_state()
                self.set_status("Link canceled. Drop on a different node.")
        else:
            previous_source = self.pending_link_source_id
            self.cancel_link_preview()
            self.pending_link_source_id = None
            self.apply_link_source_visual_state(previous_source, None)
            self.update_control_state()
            self.set_status("Link canceled. Drop on a different node.")

        self.port_drag_active = False
        self.port_drag_origin = {}
        self.port_drag_just_finished = True
        GLib.timeout_add(120, self.clear_recent_port_drag_flag)

    def clear_recent_port_drag_flag(self):
        self.port_drag_just_finished = False
        return False

    def on_input_port_released(self, _gesture, _n_press, _x, _y, node_id: str):
        _gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        source_id = self.link_preview_source_id or self.pending_link_source_id
        if not source_id or source_id == node_id:
            return

        target = self.find_node(node_id)
        source = self.find_node(source_id)
        previous_source = self.pending_link_source_id
        if target and self.add_edge(source_id, node_id):
            previous_selected = self.selected_node_id
            self.set_single_selection(target.id)
            self.pending_link_source_id = None
            self.cancel_link_preview()
            self.apply_selection_visual_state(previous_selected, target.id)
            self.apply_link_source_visual_state(previous_source, None)
            self.update_inspector(target)
            self.update_control_state()
            if source:
                self.set_status(f"Linked '{source.name}' -> '{target.name}'.")
        self.set_link_hover_target(None)

    def on_output_port_released(self, _gesture, _n_press, _x, _y, node_id: str):
        _gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        if self.node_drag_active or self.port_drag_active or self.port_drag_just_finished:
            return
        selected = self.find_node(node_id)
        if not selected:
            return

        previous_source = self.pending_link_source_id
        if previous_source == node_id:
            self.pending_link_source_id = None
            self.cancel_link_preview()
            self.apply_link_source_visual_state(previous_source, None)
            self.update_control_state()
            self.set_status("Link mode canceled.")
            return

        previous_selected = self.selected_node_id
        self.set_single_selection(node_id)
        self.pending_link_source_id = node_id
        self.begin_link_preview(node_id)
        self.apply_selection_visual_state(previous_selected, node_id)
        self.apply_link_source_visual_state(previous_source, node_id)
        self.link_layer.queue_draw()
        self.update_inspector(selected)
        self.update_control_state()
        link_type = self.get_selected_link_type()
        self.set_status(
            f"Link mode active from '{selected.name}' as '{link_type}'. Select a target node."
        )

    def on_node_clicked(self, gesture: Gtk.GestureClick, _n_press, _x, _y, node_id: str):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.grab_focus()
        if self.suppress_next_node_click:
            self.suppress_next_node_click = False
            return
        if self.node_drag_active and not self.drag_origin:
            # Recover from interrupted gesture state so clicks are not blocked.
            self.node_drag_active = False
        if self.node_drag_active:
            return

        previous_selected = self.selected_node_id
        previous_selection_set = set(self.selected_node_ids)
        previous_source = self.pending_link_source_id
        node = self.find_node(node_id)
        if not node:
            return

        source_name = None
        if self.pending_link_source_id:
            source = self.find_node(self.pending_link_source_id)
            source_name = source.name if source else self.pending_link_source_id

        link_created = False
        if self.pending_link_source_id and self.pending_link_source_id != node_id:
            link_created = self.add_edge(self.pending_link_source_id, node_id)
            self.pending_link_source_id = None
            self.cancel_link_preview()
            self.set_single_selection(node_id)
            self.apply_selection_visual_state(previous_selected, node_id)
        elif self.pending_link_source_id == node_id:
            # Clicking the active link source should exit link mode and keep node selected.
            self.pending_link_source_id = None
            self.cancel_link_preview()
            self.set_single_selection(node_id)
            self.apply_selection_visual_state(previous_selected, node_id)
            self.set_status("Link mode canceled.")
        else:
            state = gesture.get_current_event_state()
            additive = bool(
                state
                & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK)
            )
            if additive:
                updated = set(self.selected_node_ids)
                if node_id in updated:
                    updated.remove(node_id)
                    new_primary = self.selected_node_id
                    if new_primary == node_id:
                        new_primary = next(iter(updated), None) if updated else None
                    self.set_selection(updated, primary_id=new_primary)
                else:
                    updated.add(node_id)
                    self.set_selection(updated, primary_id=node_id)
            else:
                self.set_single_selection(node_id)

        self.apply_selection_set_visual_state(
            previous_selection_set,
            self.selected_node_ids,
            previous_selected,
            self.selected_node_id,
        )
        if previous_source != self.pending_link_source_id:
            self.apply_link_source_visual_state(previous_source, self.pending_link_source_id)
        self.link_layer.queue_draw()

        selected_node = self.get_selected_node()
        if selected_node:
            self.update_inspector(selected_node)
        else:
            self.clear_inspector()
        self.update_control_state()

        if link_created:
            self.set_status(f"Linked '{source_name}' -> '{node.name}'.")

    def on_canvas_stage_clicked(self, gesture, _n_press, x: float, y: float):
        self.grab_focus()
        if self.port_drag_active:
            self.finalize_link_preview_at(int(x), int(y))
            self.port_drag_active = False
            self.port_drag_origin = {}
            return
        if self.suppress_stage_click_once:
            self.suppress_stage_click_once = False
            return
        hit_node = self.find_node_at_point(int(x), int(y))
        if hit_node:
            # Fallback: if node-level click handler was preempted by gesture arena ordering,
            # still select the node and surface its inspector controls.
            state = gesture.get_current_event_state()
            additive = bool(
                state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK)
            )
            previous_selected = self.selected_node_id
            previous_selection_set = set(self.selected_node_ids)
            if additive:
                updated = set(self.selected_node_ids)
                if hit_node.id in updated:
                    updated.remove(hit_node.id)
                    new_primary = self.selected_node_id
                    if new_primary == hit_node.id:
                        new_primary = next(iter(updated), None) if updated else None
                    self.set_selection(updated, primary_id=new_primary)
                else:
                    updated.add(hit_node.id)
                    self.set_selection(updated, primary_id=hit_node.id)
            else:
                self.set_single_selection(hit_node.id)
            self.apply_selection_set_visual_state(
                previous_selection_set,
                self.selected_node_ids,
                previous_selected,
                self.selected_node_id,
            )
            selected_node = self.get_selected_node()
            if selected_node:
                self.update_inspector(selected_node)
            else:
                self.clear_inspector()
            self.update_control_state()
            return

        if not self.get_selected_node() and not self.pending_link_source_id:
            self.clear_inspector()
            self.update_control_state()
            return

        previous_selected = self.selected_node_id
        previous_selection_set = set(self.selected_node_ids)
        previous_source = self.pending_link_source_id
        self.selected_node_id = None
        self.selected_node_ids = set()
        self.pending_link_source_id = None
        self.cancel_link_preview()
        self.apply_selection_set_visual_state(
            previous_selection_set,
            self.selected_node_ids,
            previous_selected,
            None,
        )
        self.apply_link_source_visual_state(previous_source, None)
        self.link_layer.queue_draw()
        self.clear_inspector()
        self.update_control_state()
        self.set_status("Canvas selection cleared.")

    def on_stage_pointer_motion(self, _controller, x: float, y: float):
        if not self.port_drag_active:
            return
        source_id = self.link_preview_source_id or self.pending_link_source_id
        if not source_id:
            return
        stage_x = int(x)
        stage_y = int(y)
        target = self.active_drag_target(source_id, stage_x, stage_y)
        if target:
            self.set_link_hover_target(target.id)
            snap_x, snap_y = self.node_input_anchor(target)
            self.update_link_preview_position(int(snap_x), int(snap_y))
        else:
            self.set_link_hover_target(None)
            self.update_link_preview_position(stage_x, stage_y)

    def active_drag_target(self, source_id: str, x: int, y: int) -> CanvasNode | None:
        hovered_target = self.drag_hover_target(source_id)
        if hovered_target:
            return hovered_target
        return self.valid_link_target_at(x, y, source_id)

    def drag_hover_target(self, source_id: str) -> CanvasNode | None:
        if self.hovered_port_kind != "in":
            return None
        hovered_id = str(self.hovered_port_node_id or "").strip()
        if not hovered_id or hovered_id == source_id:
            return None
        hovered_node = self.find_node(hovered_id)
        if not hovered_node:
            return None
        if self.node_type_key(hovered_node.node_type) == "trigger":
            return None
        return hovered_node

    def gesture_stage_point(self, gesture) -> tuple[float, float] | None:
        widget = gesture.get_widget() if hasattr(gesture, "get_widget") else None
        if not widget:
            return None
        try:
            has_point, local_x, local_y = gesture.get_point()
        except Exception:
            return None
        if not has_point:
            return None
        try:
            translated = widget.translate_coordinates(self.fixed, float(local_x), float(local_y))
        except Exception:
            return None
        if not translated or not translated[0]:
            return None
        return float(translated[1]), float(translated[2])

    def on_node_drag_begin(self, gesture, start_x, start_y, node_id: str):
        # Dragging should always move nodes. If link mode is active, cancel it first.
        if self.pending_link_source_id and self.pending_link_source_id != node_id:
            previous_source = self.pending_link_source_id
            self.pending_link_source_id = None
            self.cancel_link_preview()
            self.apply_link_source_visual_state(previous_source, None)
            self.update_control_state()
            self.set_status("Link mode canceled. Dragging node.")

        if self.port_drag_active:
            # An output-port drag is already driving link preview for this sequence.
            return
        if self.started_near_output_port(float(start_x), float(start_y)):
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            stage_pointer = self.gesture_stage_point(gesture)
            if stage_pointer:
                pointer_stage_x, pointer_stage_y = stage_pointer
                self.begin_output_link_drag(
                    node_id,
                    pointer_x=pointer_stage_x,
                    pointer_y=pointer_stage_y,
                )
            else:
                self.begin_output_link_drag(node_id)
            return
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        node = self.find_node(node_id)
        if not node:
            return

        previous_selected = self.selected_node_id
        previous_selection_set = set(self.selected_node_ids)
        if node_id not in self.selected_node_ids:
            self.set_single_selection(node_id)
        else:
            self.set_selection(set(self.selected_node_ids), primary_id=node_id)
        stage_pointer = self.gesture_stage_point(gesture)
        if stage_pointer:
            pointer_stage_x, pointer_stage_y = stage_pointer
        else:
            gesture_widget = gesture.get_widget() if hasattr(gesture, "get_widget") else None
            if gesture_widget:
                success, translated_x, translated_y = gesture_widget.translate_coordinates(
                    self.fixed,
                    float(start_x),
                    float(start_y),
                )
                if success:
                    pointer_stage_x = float(translated_x)
                    pointer_stage_y = float(translated_y)
                else:
                    pointer_stage_x = float(self.to_screen(node.x))
                    pointer_stage_y = float(self.to_screen(node.y))
            else:
                pointer_stage_x = float(self.to_screen(node.x))
                pointer_stage_y = float(self.to_screen(node.y))
        self.node_drag_active = True
        self.drag_origin = {
            "node_id": node_id,
            "x": node.x,
            "y": node.y,
            "pointer_stage_x": pointer_stage_x,
            "pointer_stage_y": pointer_stage_y,
        }
        self.drag_group_origins = {
            item.id: (item.x, item.y)
            for item in self.nodes
            if item.id in self.selected_node_ids
        }
        self.push_undo_snapshot()
        self.drag_history_captured = True
        self.drag_guide_x = None
        self.drag_guide_y = None
        self.suppress_stage_click_once = True
        self.set_node_drag_cursor("grabbing")
        if previous_selected != self.selected_node_id or previous_selection_set != self.selected_node_ids:
            self.apply_selection_set_visual_state(
                previous_selection_set,
                self.selected_node_ids,
                previous_selected,
                self.selected_node_id,
            )
            self.link_layer.queue_draw()
        self.update_inspector(node)

    def on_node_drag_update(self, _gesture, offset_x: float, offset_y: float, node_id: str):
        if self.port_drag_active and not self.drag_origin and self.link_preview_source_id == node_id:
            anchor_x = float(self.port_drag_origin.get("anchor_x", 0.0))
            anchor_y = float(self.port_drag_origin.get("anchor_y", 0.0))
            bias_x = float(self.port_drag_origin.get("pointer_bias_x", 0.0))
            bias_y = float(self.port_drag_origin.get("pointer_bias_y", 0.0))
            x = int(anchor_x + bias_x + float(offset_x))
            y = int(anchor_y + bias_y + float(offset_y))
            source_id = self.link_preview_source_id or self.pending_link_source_id or node_id
            target = self.active_drag_target(source_id, x, y)
            if target:
                self.set_link_hover_target(target.id)
                snap_x, snap_y = self.node_input_anchor(target)
                self.update_link_preview_position(int(snap_x), int(snap_y))
            else:
                self.set_link_hover_target(None)
                self.update_link_preview_position(x, y)
            return

        if self.drag_origin.get("node_id") != node_id:
            return

        if node_id not in self.drag_group_origins:
            return

        start_x, start_y = self.drag_group_origins[node_id]

        proposed_x = float(start_x + (offset_x / self.zoom_factor))
        proposed_y = float(start_y + (offset_y / self.zoom_factor))
        stage_pointer = self.gesture_stage_point(_gesture)
        if stage_pointer:
            pointer_stage_x, pointer_stage_y = stage_pointer
            start_pointer_x = float(self.drag_origin.get("pointer_stage_x", self.to_screen(start_x)))
            start_pointer_y = float(self.drag_origin.get("pointer_stage_y", self.to_screen(start_y)))
            proposed_x = float(start_x + ((pointer_stage_x - start_pointer_x) / self.zoom_factor))
            proposed_y = float(start_y + ((pointer_stage_y - start_pointer_y) / self.zoom_factor))
        # Keep node motion visually stable while dragging. Forcing grid/guide snap on
        # every motion event can cause rapid oscillation near boundaries.
        snapped_x = proposed_x
        snapped_y = proposed_y

        state = _gesture.get_current_event_state()
        live_snap_enabled = bool(state & Gdk.ModifierType.CONTROL_MASK)
        if live_snap_enabled:
            snapped_x = round(proposed_x / self.SNAP_GRID) * self.SNAP_GRID
            snapped_y = round(proposed_y / self.SNAP_GRID) * self.SNAP_GRID
        guide_x, guide_y = self.find_alignment_guides(
            node_id,
            int(round(proposed_x)),
            int(round(proposed_y)),
            exclude_ids=set(self.drag_group_origins.keys()),
        )

        if live_snap_enabled:
            if guide_x is not None:
                snapped_x = guide_x
            if guide_y is not None:
                snapped_y = guide_y

        delta_x = int(snapped_x - start_x)
        delta_y = int(snapped_y - start_y)
        max_x = max(0, self.STAGE_WIDTH - self.CARD_WIDTH)
        max_y = max(0, self.STAGE_HEIGHT - self.CARD_HEIGHT)
        for drag_node_id, (origin_x, origin_y) in self.drag_group_origins.items():
            drag_node = self.find_node(drag_node_id)
            drag_widget = self.node_widgets.get(drag_node_id)
            if not drag_node or not drag_widget:
                continue
            drag_node.x = max(0, min(max_x, int(origin_x + delta_x)))
            drag_node.y = max(0, min(max_y, int(origin_y + delta_y)))
            self.fixed.move(drag_widget, self.to_screen(drag_node.x), self.to_screen(drag_node.y))

        self.drag_guide_x = guide_x
        self.drag_guide_y = guide_y

        self.link_layer.queue_draw()
        if hasattr(self, "minimap_area") and self.minimap_area:
            self.minimap_area.queue_draw()

        primary_node = self.get_selected_node()
        if primary_node:
            self.node_position_label.set_text(f"Position: {primary_node.x}, {primary_node.y}")

    def on_node_drag_end(self, _gesture, _offset_x, _offset_y, node_id: str):
        if self.port_drag_active and not self.drag_origin and self.link_preview_source_id == node_id:
            end_x = int(self.link_preview_end_x)
            end_y = int(self.link_preview_end_y)
            if end_x <= 0 and end_y <= 0:
                anchor_x = float(self.port_drag_origin.get("anchor_x", 0.0))
                anchor_y = float(self.port_drag_origin.get("anchor_y", 0.0))
                bias_x = float(self.port_drag_origin.get("pointer_bias_x", 0.0))
                bias_y = float(self.port_drag_origin.get("pointer_bias_y", 0.0))
                end_x = int(anchor_x + bias_x + float(_offset_x))
                end_y = int(anchor_y + bias_y + float(_offset_y))
            self.finalize_link_preview_at(end_x, end_y)
            self.port_drag_active = False
            self.port_drag_origin = {}
            return

        if self.drag_origin.get("node_id") != node_id:
            # Defensive reset when GTK reports a drag-end without a matching origin.
            self.drag_origin = {}
            self.drag_group_origins = {}
            self.node_drag_active = False
            self.drag_history_captured = False
            self.drag_guide_x = None
            self.drag_guide_y = None
            self.set_node_drag_cursor("grab")
            return

        self.drag_origin = {}
        self.drag_group_origins = {}
        self.node_drag_active = False
        self.drag_history_captured = False
        self.drag_guide_x = None
        self.drag_guide_y = None
        self.link_layer.queue_draw()
        self.set_node_drag_cursor("grab")
        self.suppress_next_node_click = True
        GLib.timeout_add(80, self.release_suppressed_click)
        node = self.find_node(node_id)
        if node:
            self.update_inspector(node)
        self.maybe_auto_save("Node moved and auto-saved.")
        self.inline_validate_graph()

    def started_near_output_port(self, x: float, y: float) -> bool:
        width = float(self.card_screen_width())
        height = float(self.card_screen_height())
        center_x = width - 18.0
        center_y = height - 18.0
        radius = 22.0
        dx = float(x) - center_x
        dy = float(y) - center_y
        return (dx * dx) + (dy * dy) <= (radius * radius)

    def release_suppressed_click(self):
        self.suppress_next_node_click = False
        return False

    def apply_selection_visual_state(self, previous_node_id: str | None, current_node_id: str | None):
        previous_ids = {previous_node_id} if previous_node_id else set()
        current_ids = {current_node_id} if current_node_id else set()
        self.apply_selection_set_visual_state(
            previous_ids,
            current_ids,
            previous_node_id,
            current_node_id,
        )

    def apply_link_source_visual_state(
        self,
        previous_node_id: str | None,
        current_node_id: str | None,
    ):
        if previous_node_id:
            previous_widget = self.node_widgets.get(previous_node_id)
            if previous_widget:
                previous_widget.remove_css_class("canvas-node-link-source")
        if current_node_id:
            current_widget = self.node_widgets.get(current_node_id)
            if current_widget:
                current_widget.add_css_class("canvas-node-link-source")

    def on_canvas_key_pressed(self, _controller, keyval, _keycode, state):
        control_pressed = bool(state & Gdk.ModifierType.CONTROL_MASK)
        shift_pressed = bool(state & Gdk.ModifierType.SHIFT_MASK)

        if control_pressed and keyval in (Gdk.KEY_z, Gdk.KEY_Z):
            if shift_pressed:
                self.on_redo_clicked(None)
            else:
                self.on_undo_clicked(None)
            return True

        if control_pressed and keyval in (Gdk.KEY_y, Gdk.KEY_Y):
            self.on_redo_clicked(None)
            return True

        if keyval in (Gdk.KEY_Delete, Gdk.KEY_KP_Delete, Gdk.KEY_BackSpace):
            self.on_delete_selected(None)
            return True

        if keyval == Gdk.KEY_Escape:
            if self.pending_link_source_id or self.link_preview_source_id:
                previous_source = self.pending_link_source_id
                self.pending_link_source_id = None
                self.cancel_link_preview()
                self.apply_link_source_visual_state(previous_source, None)
                self.set_status("Link mode canceled.")
                return True
            if self.selected_node_id:
                previous_selected = self.selected_node_id
                previous_selection_set = set(self.selected_node_ids)
                self.selected_node_id = None
                self.selected_node_ids = set()
                self.apply_selection_set_visual_state(
                    previous_selection_set,
                    self.selected_node_ids,
                    previous_selected,
                    None,
                )
                self.clear_inspector()
                self.update_control_state()
                self.set_status("Canvas selection cleared.")
                return True

        if control_pressed and keyval in (Gdk.KEY_a, Gdk.KEY_A):
            all_ids = {node.id for node in self.nodes}
            self.set_selection(all_ids, primary_id=self.selected_node_id)
            if self.selected_node_id:
                selected = self.find_node(self.selected_node_id)
                if selected:
                    self.update_inspector(selected)
            self.update_control_state()
            self.set_status(f"Selected {len(all_ids)} node(s).")
            return True

        if control_pressed and keyval in (Gdk.KEY_s, Gdk.KEY_S):
            self.on_save_graph(None)
            return True

        if control_pressed and keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            self.on_zoom_out_clicked(None)
            return True

        if control_pressed and keyval in (Gdk.KEY_equal, Gdk.KEY_plus, Gdk.KEY_KP_Add):
            self.on_zoom_in_clicked(None)
            return True

        if control_pressed and keyval in (Gdk.KEY_0, Gdk.KEY_KP_0):
            self.on_zoom_reset_clicked(None)
            return True

        if control_pressed and keyval in (Gdk.KEY_l, Gdk.KEY_L):
            self.on_start_link(None)
            return True

        if control_pressed and keyval in (Gdk.KEY_p, Gdk.KEY_P):
            self.on_run_preflight_check(None)
            return True

        if control_pressed and shift_pressed and keyval in (Gdk.KEY_g, Gdk.KEY_G):
            self.on_snap_grid_clicked(None)
            return True

        if control_pressed and shift_pressed and keyval in (Gdk.KEY_d, Gdk.KEY_D):
            self.on_distribute_x_clicked(None)
            return True

        return False

    def on_draw_links(self, _area, cr, _width, _height):
        dark_mode = self.is_dark_mode()
        self.draw_canvas_stage(cr, _width, _height, dark_mode)
        cr.set_line_cap(1)
        cr.set_line_join(1)

        node_map = {node.id: node for node in self.nodes}

        for edge in self.edges:
            source = node_map.get(edge.source_node_id)
            target = node_map.get(edge.target_node_id)
            if not source or not target:
                continue

            start_x, start_y = self.node_output_anchor(source)
            end_x, end_y = self.node_input_anchor(target)
            control_offset = max(80, abs(end_x - start_x) * 0.35)

            red, green, blue, alpha = self.edge_color(edge.condition, dark_mode)
            is_selected_path = bool(
                {edge.source_node_id, edge.target_node_id}.intersection(self.selected_node_ids)
            )
            edge_error = self.edge_has_issue(edge, "error")
            edge_warning = self.edge_has_issue(edge, "warning")

            if edge_error:
                red, green, blue, alpha = (1.0, 0.38, 0.34, 1.0)
            elif edge_warning:
                red, green, blue, alpha = (1.0, 0.72, 0.28, 1.0)

            if dark_mode:
                glow_alpha = 0.7 if is_selected_path else 0.56
                glow_width = 6.2 if is_selected_path else 4.9
                stroke_width = 3.2 if is_selected_path else 2.6
                shadow = (0.95, 0.98, 1.0, 0.2 if is_selected_path else 0.14)
            else:
                glow_alpha = 0.62 if is_selected_path else 0.48
                glow_width = 5.0 if is_selected_path else 4.0
                stroke_width = 2.8 if is_selected_path else 2.2
                shadow = (0.03, 0.08, 0.18, 0.2 if is_selected_path else 0.14)
            if edge_error:
                glow_width += 1.2
                stroke_width += 0.8
                glow_alpha = min(1.0, glow_alpha + 0.12)
            elif edge_warning:
                glow_width += 0.8
                stroke_width += 0.5
                glow_alpha = min(1.0, glow_alpha + 0.08)

            self.trace_edge_curve(
                cr,
                start_x,
                start_y,
                end_x,
                end_y,
                control_offset,
            )
            cr.set_source_rgba(*shadow)
            cr.set_line_width(stroke_width + 2.4)
            cr.stroke()

            if is_selected_path:
                self.trace_edge_curve(
                    cr,
                    start_x,
                    start_y,
                    end_x,
                    end_y,
                    control_offset,
                )
                accent_alpha = 0.22 if dark_mode else 0.17
                cr.set_source_rgba(0.9, 0.95, 1.0, accent_alpha)
                cr.set_line_width(stroke_width + 2.2)
                cr.stroke()

            self.trace_edge_curve(
                cr,
                start_x,
                start_y,
                end_x,
                end_y,
                control_offset,
            )
            cr.set_source_rgba(red, green, blue, glow_alpha)
            cr.set_line_width(glow_width)
            cr.stroke()

            self.trace_edge_curve(
                cr,
                start_x,
                start_y,
                end_x,
                end_y,
                control_offset,
            )
            cr.set_source_rgba(red, green, blue, alpha)
            cr.set_line_width(stroke_width)
            cr.stroke()

            self.draw_edge_arrow(
                cr,
                end_x,
                end_y,
                end_x - control_offset,
                end_y,
                (red, green, blue, alpha),
                is_selected_path,
            )

            if edge.condition:
                mid_x, mid_y = self.cubic_bezier_point(
                    start_x,
                    start_y,
                    start_x + control_offset,
                    start_y,
                    end_x - control_offset,
                    end_y,
                    end_x,
                    end_y,
                    0.5,
                )
                label_text = edge.condition.upper()
                x_bearing, y_bearing, text_width, text_height, _, _ = cr.text_extents(label_text)
                pad_x = 8
                pad_y = 4
                box_width = text_width + (pad_x * 2)
                box_height = text_height + (pad_y * 2)
                box_x = mid_x - (box_width / 2)
                box_y = mid_y - (box_height / 2)

                bg_red, bg_green, bg_blue, _ = self.edge_color(edge.condition, dark_mode)
                bg_alpha = 0.26 if dark_mode else 0.18
                text_color = (0.93, 0.97, 1.0, 0.96) if dark_mode else (0.03, 0.1, 0.22, 0.92)

                self.draw_rounded_rect(cr, box_x, box_y, box_width, box_height, 8)
                cr.set_source_rgba(bg_red, bg_green, bg_blue, bg_alpha)
                cr.fill()

                self.draw_rounded_rect(cr, box_x, box_y, box_width, box_height, 8)
                cr.set_source_rgba(bg_red, bg_green, bg_blue, 0.58 if dark_mode else 0.4)
                cr.set_line_width(1.0)
                cr.stroke()

                cr.select_font_face("Sans", 0, 0)
                cr.set_font_size(10.5)
                cr.set_source_rgba(*text_color)
                text_x = box_x + pad_x - x_bearing
                text_y = box_y + pad_y - y_bearing
                cr.move_to(text_x, text_y)
                cr.show_text(label_text)
                cr.stroke()

        preview_source = node_map.get(self.link_preview_source_id or "")
        if preview_source:
            start_x, start_y = self.node_output_anchor(preview_source)
            end_x = self.link_preview_end_x or start_x
            end_y = self.link_preview_end_y or start_y
            control_offset = max(80, abs(end_x - start_x) * 0.35)

            if self.link_hover_target_id:
                hover_target = node_map.get(self.link_hover_target_id)
                if hover_target:
                    hover_x, hover_y = self.node_input_anchor(hover_target)
                    hover_offset = max(80, abs(hover_x - start_x) * 0.35)
                    self.trace_edge_curve(
                        cr,
                        start_x,
                        start_y,
                        hover_x,
                        hover_y,
                        hover_offset,
                    )
                    cr.set_source_rgba(0.86, 0.93, 1.0, 0.28 if dark_mode else 0.22)
                    cr.set_line_width(7.4)
                    cr.stroke()
                    self.draw_hover_drop_indicator(
                        cr,
                        hover_x,
                        hover_y,
                        dark_mode=dark_mode,
                        active=True,
                    )

            preview_condition = self.get_selected_link_condition()
            red, green, blue, _alpha = self.edge_color(preview_condition, dark_mode)

            self.trace_edge_curve(
                cr,
                start_x,
                start_y,
                end_x,
                end_y,
                control_offset,
            )
            cr.set_dash([9.0, 6.0], 0)
            cr.set_source_rgba(red, green, blue, 0.96 if dark_mode else 0.9)
            cr.set_line_width(3.3)
            cr.stroke()
            cr.set_dash([], 0)

            self.draw_edge_arrow(
                cr,
                end_x,
                end_y,
                end_x - control_offset,
                end_y,
                (red, green, blue, 0.82),
                False,
            )
            if not self.link_hover_target_id:
                self.draw_hover_drop_indicator(
                    cr,
                    end_x,
                    end_y,
                    dark_mode=dark_mode,
                    active=False,
                )

        self.draw_selection_rect(cr, dark_mode)
        self.draw_alignment_guides(cr, _width, _height, dark_mode)
        self.draw_connection_handles(cr, dark_mode)

    def draw_selection_rect(self, cr, dark_mode: bool):
        if not self.selection_rect_active:
            return
        left, top, right, bottom = self.current_selection_bounds()
        width = max(1.0, right - left)
        height = max(1.0, bottom - top)
        if dark_mode:
            fill = (0.37, 0.63, 0.98, 0.16)
            border = (0.56, 0.78, 1.0, 0.82)
        else:
            fill = (0.2, 0.46, 0.93, 0.12)
            border = (0.14, 0.36, 0.86, 0.74)
        self.draw_rounded_rect(cr, left, top, width, height, 8.0)
        cr.set_source_rgba(*fill)
        cr.fill_preserve()
        cr.set_source_rgba(*border)
        cr.set_line_width(1.2)
        cr.set_dash([5.0, 4.0], 0)
        cr.stroke()
        cr.set_dash([], 0)

    def draw_alignment_guides(self, cr, width: int, height: int, dark_mode: bool):
        if self.drag_guide_x is None and self.drag_guide_y is None:
            return

        if dark_mode:
            color = (0.56, 0.78, 1.0, 0.78)
        else:
            color = (0.16, 0.38, 0.88, 0.62)

        cr.set_dash([6.0, 5.0], 0)
        cr.set_line_width(1.2)
        if self.drag_guide_x is not None:
            screen_x = self.to_screen(self.drag_guide_x + (self.CARD_WIDTH / 2))
            cr.move_to(screen_x, 0)
            cr.line_to(screen_x, height)
            cr.set_source_rgba(*color)
            cr.stroke()
        if self.drag_guide_y is not None:
            screen_y = self.to_screen(self.drag_guide_y + (self.CARD_HEIGHT / 2))
            cr.move_to(0, screen_y)
            cr.line_to(width, screen_y)
            cr.set_source_rgba(*color)
            cr.stroke()
        cr.set_dash([], 0)

    def find_alignment_guides(
        self,
        node_id: str,
        proposed_x: float,
        proposed_y: float,
        exclude_ids: set[str] | None = None,
    ) -> tuple[float | None, float | None]:
        best_x_dist = float(self.ALIGN_SNAP_DISTANCE) + 0.1
        best_y_dist = float(self.ALIGN_SNAP_DISTANCE) + 0.1
        best_x: float | None = None
        best_y: float | None = None

        current_x_anchors = [0.0, self.CARD_WIDTH / 2.0, float(self.CARD_WIDTH)]
        current_y_anchors = [0.0, self.CARD_HEIGHT / 2.0, float(self.CARD_HEIGHT)]

        excluded = set(exclude_ids or set())
        excluded.add(node_id)
        for other in self.nodes:
            if other.id in excluded:
                continue

            other_x_anchors = [
                float(other.x),
                float(other.x) + (self.CARD_WIDTH / 2.0),
                float(other.x) + float(self.CARD_WIDTH),
            ]
            other_y_anchors = [
                float(other.y),
                float(other.y) + (self.CARD_HEIGHT / 2.0),
                float(other.y) + float(self.CARD_HEIGHT),
            ]

            for current_offset in current_x_anchors:
                current_anchor = float(proposed_x) + current_offset
                for other_anchor in other_x_anchors:
                    distance = abs(current_anchor - other_anchor)
                    if distance <= self.ALIGN_SNAP_DISTANCE and distance < best_x_dist:
                        best_x_dist = distance
                        best_x = float(other_anchor - current_offset)

            for current_offset in current_y_anchors:
                current_anchor = float(proposed_y) + current_offset
                for other_anchor in other_y_anchors:
                    distance = abs(current_anchor - other_anchor)
                    if distance <= self.ALIGN_SNAP_DISTANCE and distance < best_y_dist:
                        best_y_dist = distance
                        best_y = float(other_anchor - current_offset)

        return best_x, best_y

    def node_type_key(self, node_type: str) -> str:
        normalized = node_type.strip().lower()
        if not normalized:
            return ""
        if "trigger" in normalized:
            return "trigger"
        if "condition" in normalized:
            return "condition"
        if normalized == "action":
            return "action"
        if "ai" in normalized:
            return "ai"
        return "template"

    def node_type_icon_name(self, node_type: str) -> str:
        node_key = self.node_type_key(node_type)
        if node_key == "trigger":
            return "media-playback-start-symbolic"
        if node_key == "condition":
            return "dialog-question-symbolic"
        if node_key == "action":
            return "system-run-symbolic"
        if node_key == "ai":
            return "preferences-system-symbolic"
        return "folder-download-symbolic"

    def node_type_chip_text(self, node_type: str) -> str:
        node_key = self.node_type_key(node_type)
        if node_key == "trigger":
            return "TRIGGER"
        if node_key == "condition":
            return "CONDITION"
        if node_key == "action":
            return "ACTION"
        if node_key == "ai":
            return "AI"
        return "TEMPLATE"

    def is_dark_mode(self) -> bool:
        root = self.get_root()
        if root and hasattr(root, "has_css_class"):
            try:
                return bool(root.has_css_class("theme-dark"))
            except Exception:
                pass
        return False

    def has_root_class(self, css_class: str) -> bool:
        root = self.get_root()
        if not root or not hasattr(root, "has_css_class"):
            return False
        try:
            return bool(root.has_css_class(css_class))
        except Exception:
            return False

    def active_theme_preset(self) -> str:
        for preset in [
            "graphite",
            "indigo",
            "carbon",
            "aurora",
            "frost",
            "sunset",
            "rose",
            "amber",
        ]:
            if self.has_root_class(f"theme-preset-{preset}"):
                return preset
        return "graphite"

    def canvas_palette(self, dark_mode: bool) -> dict[str, tuple[float, float, float, float]]:
        preset = self.active_theme_preset()

        if dark_mode:
            base = {
                "bg": (0.13, 0.18, 0.26, 1.0),
                "spot_a": (0.34, 0.58, 0.95, 0.1),
                "spot_b": (0.24, 0.74, 0.9, 0.08),
                "line_minor": (0.78, 0.86, 0.98, 0.08),
                "line_major": (0.86, 0.92, 1.0, 0.15),
                "dot": (0.85, 0.91, 0.98, 0.3),
                "dot_major": (0.98, 0.99, 1.0, 0.44),
                "edge_next": (0.72, 0.9, 1.0, 1.0),
                "edge_true": (0.58, 0.97, 0.75, 1.0),
                "edge_false": (1.0, 0.72, 0.64, 1.0),
            }
            preset_overrides = {
                "indigo": {
                    "bg": (0.09, 0.1, 0.18, 1.0),
                    "spot_a": (0.42, 0.35, 0.95, 0.11),
                    "spot_b": (0.58, 0.39, 0.96, 0.08),
                    "dot": (0.64, 0.62, 0.87, 0.24),
                    "dot_major": (0.84, 0.81, 1.0, 0.38),
                    "edge_next": (0.68, 0.68, 1.0, 0.95),
                },
                "carbon": {
                    "bg": (0.07, 0.12, 0.12, 1.0),
                    "spot_a": (0.08, 0.66, 0.56, 0.11),
                    "spot_b": (0.14, 0.78, 0.45, 0.08),
                    "dot": (0.54, 0.74, 0.68, 0.24),
                    "dot_major": (0.74, 0.95, 0.86, 0.39),
                    "edge_next": (0.39, 0.88, 0.86, 0.95),
                },
                "aurora": {
                    "bg": (0.07, 0.13, 0.11, 1.0),
                    "spot_a": (0.08, 0.75, 0.57, 0.11),
                    "spot_b": (0.24, 0.86, 0.45, 0.08),
                    "dot": (0.56, 0.77, 0.69, 0.24),
                    "dot_major": (0.82, 1.0, 0.9, 0.39),
                    "edge_next": (0.45, 0.9, 0.8, 0.95),
                },
                "frost": {
                    "bg": (0.08, 0.12, 0.18, 1.0),
                    "spot_a": (0.22, 0.64, 0.96, 0.11),
                    "spot_b": (0.56, 0.66, 0.96, 0.08),
                    "dot": (0.58, 0.73, 0.89, 0.24),
                    "dot_major": (0.82, 0.9, 1.0, 0.39),
                    "edge_next": (0.57, 0.82, 1.0, 0.95),
                },
                "sunset": {
                    "bg": (0.16, 0.1, 0.12, 1.0),
                    "spot_a": (0.99, 0.52, 0.3, 0.13),
                    "spot_b": (0.96, 0.28, 0.43, 0.11),
                    "line_minor": (0.98, 0.77, 0.66, 0.1),
                    "line_major": (1.0, 0.85, 0.74, 0.17),
                    "dot": (0.99, 0.79, 0.66, 0.3),
                    "dot_major": (1.0, 0.9, 0.82, 0.46),
                    "edge_next": (1.0, 0.66, 0.43, 0.98),
                    "edge_true": (0.98, 0.8, 0.46, 1.0),
                    "edge_false": (0.99, 0.45, 0.52, 1.0),
                },
                "rose": {
                    "bg": (0.14, 0.09, 0.16, 1.0),
                    "spot_a": (0.9, 0.34, 0.67, 0.14),
                    "spot_b": (0.72, 0.42, 0.96, 0.12),
                    "line_minor": (0.92, 0.72, 0.96, 0.1),
                    "line_major": (0.97, 0.84, 1.0, 0.18),
                    "dot": (0.93, 0.76, 0.98, 0.3),
                    "dot_major": (0.98, 0.9, 1.0, 0.46),
                    "edge_next": (0.93, 0.58, 0.93, 0.98),
                    "edge_true": (0.95, 0.75, 0.98, 1.0),
                    "edge_false": (0.99, 0.5, 0.72, 1.0),
                },
                "amber": {
                    "bg": (0.14, 0.12, 0.07, 1.0),
                    "spot_a": (0.98, 0.67, 0.2, 0.14),
                    "spot_b": (0.96, 0.48, 0.12, 0.11),
                    "line_minor": (0.95, 0.84, 0.62, 0.1),
                    "line_major": (0.99, 0.91, 0.74, 0.18),
                    "dot": (0.98, 0.86, 0.56, 0.3),
                    "dot_major": (1.0, 0.93, 0.76, 0.46),
                    "edge_next": (0.98, 0.74, 0.33, 0.98),
                    "edge_true": (0.97, 0.86, 0.47, 1.0),
                    "edge_false": (0.97, 0.5, 0.25, 1.0),
                },
            }
        else:
            base = {
                "bg": (0.97, 0.985, 1.0, 1.0),
                "spot_a": (0.44, 0.67, 0.98, 0.045),
                "spot_b": (0.3, 0.77, 0.92, 0.042),
                "line_minor": (0.16, 0.29, 0.48, 0.07),
                "line_major": (0.12, 0.25, 0.42, 0.13),
                "dot": (0.2, 0.33, 0.52, 0.18),
                "dot_major": (0.1, 0.23, 0.41, 0.28),
                "edge_next": (0.1, 0.42, 0.88, 1.0),
                "edge_true": (0.07, 0.57, 0.3, 1.0),
                "edge_false": (0.82, 0.23, 0.2, 1.0),
            }
            preset_overrides = {
                "indigo": {
                    "spot_a": (0.46, 0.52, 0.96, 0.09),
                    "spot_b": (0.59, 0.43, 0.95, 0.06),
                    "dot": (0.3, 0.34, 0.58, 0.2),
                    "dot_major": (0.23, 0.27, 0.52, 0.31),
                    "edge_next": (0.34, 0.34, 0.88, 0.92),
                },
                "carbon": {
                    "spot_a": (0.15, 0.62, 0.53, 0.08),
                    "spot_b": (0.21, 0.74, 0.45, 0.06),
                    "dot": (0.22, 0.42, 0.39, 0.19),
                    "dot_major": (0.17, 0.37, 0.33, 0.3),
                    "edge_next": (0.08, 0.58, 0.55, 0.92),
                },
                "aurora": {
                    "spot_a": (0.11, 0.67, 0.52, 0.08),
                    "spot_b": (0.34, 0.78, 0.39, 0.06),
                    "dot": (0.24, 0.45, 0.36, 0.19),
                    "dot_major": (0.17, 0.4, 0.31, 0.3),
                    "edge_next": (0.12, 0.61, 0.5, 0.92),
                },
                "frost": {
                    "spot_a": (0.3, 0.66, 0.94, 0.09),
                    "spot_b": (0.56, 0.64, 0.95, 0.06),
                    "dot": (0.25, 0.45, 0.62, 0.2),
                    "dot_major": (0.18, 0.36, 0.56, 0.32),
                    "edge_next": (0.2, 0.52, 0.9, 0.92),
                },
                "sunset": {
                    "bg": (1.0, 0.97, 0.95, 1.0),
                    "spot_a": (0.98, 0.56, 0.32, 0.12),
                    "spot_b": (0.94, 0.3, 0.45, 0.09),
                    "line_minor": (0.49, 0.27, 0.24, 0.1),
                    "line_major": (0.45, 0.24, 0.23, 0.16),
                    "dot": (0.51, 0.28, 0.27, 0.23),
                    "dot_major": (0.47, 0.24, 0.25, 0.34),
                    "edge_next": (0.86, 0.36, 0.2, 0.94),
                    "edge_true": (0.82, 0.49, 0.17, 0.98),
                    "edge_false": (0.84, 0.23, 0.3, 0.98),
                },
                "rose": {
                    "bg": (0.99, 0.96, 1.0, 1.0),
                    "spot_a": (0.88, 0.34, 0.67, 0.12),
                    "spot_b": (0.71, 0.41, 0.95, 0.09),
                    "line_minor": (0.4, 0.24, 0.47, 0.1),
                    "line_major": (0.37, 0.21, 0.45, 0.16),
                    "dot": (0.42, 0.25, 0.5, 0.23),
                    "dot_major": (0.38, 0.22, 0.47, 0.34),
                    "edge_next": (0.68, 0.28, 0.67, 0.94),
                    "edge_true": (0.6, 0.36, 0.76, 0.98),
                    "edge_false": (0.77, 0.25, 0.45, 0.98),
                },
                "amber": {
                    "bg": (1.0, 0.99, 0.95, 1.0),
                    "spot_a": (0.97, 0.69, 0.2, 0.12),
                    "spot_b": (0.95, 0.48, 0.15, 0.09),
                    "line_minor": (0.44, 0.33, 0.12, 0.1),
                    "line_major": (0.4, 0.29, 0.09, 0.16),
                    "dot": (0.46, 0.34, 0.09, 0.23),
                    "dot_major": (0.42, 0.3, 0.08, 0.34),
                    "edge_next": (0.74, 0.47, 0.12, 0.94),
                    "edge_true": (0.62, 0.46, 0.1, 0.98),
                    "edge_false": (0.8, 0.36, 0.09, 0.98),
                },
            }

        palette = dict(base)
        palette.update(preset_overrides.get(preset, {}))
        return palette

    def draw_canvas_stage(self, cr, width: int, height: int, dark_mode: bool):
        palette = self.canvas_palette(dark_mode)

        cr.set_source_rgba(*palette["bg"])
        cr.rectangle(0, 0, width, height)
        cr.fill()

        cr.set_source_rgba(*palette["spot_a"])
        cr.arc(width * 0.2, height * 0.22, min(width, height) * 0.19, 0, math.tau)
        cr.fill()

        cr.set_source_rgba(*palette["spot_b"])
        cr.arc(width * 0.82, height * 0.18, min(width, height) * 0.13, 0, math.tau)
        cr.fill()

        step = 22
        major_step = step * 5

        line_minor = palette["line_minor"]
        line_major = palette["line_major"]
        dot_minor = palette["dot"]
        dot_major = palette["dot_major"]
        # Keep the stage legible across all presets with slightly stronger guides.
        line_minor_alpha = min(1.0, float(line_minor[3]) * 1.45)
        line_major_alpha = min(1.0, float(line_major[3]) * 1.32)
        dot_minor_alpha = min(1.0, float(dot_minor[3]) * 1.36)
        dot_major_alpha = min(1.0, float(dot_major[3]) * 1.34)

        # Draw a subtle base line grid under the dot grid to improve stage readability.
        cr.new_path()
        for x in range(0, width + step, step):
            if x % major_step == 0:
                continue
            px = x + 0.5
            cr.move_to(px, 0)
            cr.line_to(px, height)
        for y in range(0, height + step, step):
            if y % major_step == 0:
                continue
            py = y + 0.5
            cr.move_to(0, py)
            cr.line_to(width, py)
        cr.set_source_rgba(line_minor[0], line_minor[1], line_minor[2], line_minor_alpha)
        cr.set_line_width(0.7)
        cr.stroke()

        cr.new_path()
        for x in range(0, width + major_step, major_step):
            px = x + 0.5
            cr.move_to(px, 0)
            cr.line_to(px, height)
        for y in range(0, height + major_step, major_step):
            py = y + 0.5
            cr.move_to(0, py)
            cr.line_to(width, py)
        cr.set_source_rgba(line_major[0], line_major[1], line_major[2], line_major_alpha)
        cr.set_line_width(1.0)
        cr.stroke()

        cr.new_path()
        for y in range(0, height + step, step):
            for x in range(0, width + step, step):
                is_major = ((x // step) % 5 == 0) and ((y // step) % 5 == 0)
                if is_major:
                    continue
                cr.new_sub_path()
                cr.arc(x, y, 0.9, 0, math.tau)
        cr.set_source_rgba(dot_minor[0], dot_minor[1], dot_minor[2], dot_minor_alpha)
        cr.fill()

        cr.new_path()
        for y in range(0, height + step, step):
            for x in range(0, width + step, step):
                is_major = ((x // step) % 5 == 0) and ((y // step) % 5 == 0)
                if not is_major:
                    continue
                cr.new_sub_path()
                cr.arc(x, y, 1.48, 0, math.tau)
        cr.set_source_rgba(dot_major[0], dot_major[1], dot_major[2], dot_major_alpha)
        cr.fill()

    def edge_color(self, condition: str, dark_mode: bool) -> tuple[float, float, float, float]:
        palette = self.canvas_palette(dark_mode)
        if condition == "true":
            return palette["edge_true"]
        if condition == "false":
            return palette["edge_false"]
        return palette["edge_next"]

    def draw_connection_handles(self, cr, dark_mode: bool):
        for node in self.nodes:
            node_selected = node.id in self.selected_node_ids
            source_active = node.id in {self.pending_link_source_id, self.link_preview_source_id}
            target_active = node.id == self.link_hover_target_id
            hover_in = (
                self.hovered_port_node_id == node.id and self.hovered_port_kind == "in"
            )
            hover_out = (
                self.hovered_port_node_id == node.id and self.hovered_port_kind == "out"
            )

            input_x, input_y = self.node_input_anchor(node)
            output_x, output_y = self.node_output_anchor(node)

            if target_active:
                self.draw_link_target_halo(cr, node, dark_mode)

            self.draw_single_handle(
                cr,
                input_x,
                input_y,
                dark_mode=dark_mode,
                outgoing=False,
                selected=node_selected,
                hovered=hover_in or target_active,
                source_active=False,
            )
            self.draw_single_handle(
                cr,
                output_x,
                output_y,
                dark_mode=dark_mode,
                outgoing=True,
                selected=node_selected,
                hovered=hover_out,
                source_active=source_active,
            )

    def draw_link_target_halo(self, cr, node: CanvasNode, dark_mode: bool):
        x = float(self.to_screen(node.x) - 7)
        y = float(self.to_screen(node.y) - 7)
        width = float(self.card_screen_width() + 14)
        height = float(self.card_screen_height() + 14)
        radius = 15.0

        if dark_mode:
            fill = (0.52, 0.75, 1.0, 0.14)
            stroke = (0.68, 0.84, 1.0, 0.9)
            glow = (0.78, 0.9, 1.0, 0.26)
        else:
            fill = (0.18, 0.45, 0.92, 0.1)
            stroke = (0.2, 0.5, 0.96, 0.78)
            glow = (0.32, 0.6, 0.98, 0.2)

        self.draw_rounded_rect(cr, x - 2.0, y - 2.0, width + 4.0, height + 4.0, radius + 2.0)
        cr.set_source_rgba(*glow)
        cr.set_line_width(2.8)
        cr.stroke()

        self.draw_rounded_rect(cr, x, y, width, height, radius)
        cr.set_source_rgba(*fill)
        cr.fill_preserve()
        cr.set_source_rgba(*stroke)
        cr.set_line_width(1.8)
        cr.stroke()

    def draw_hover_drop_indicator(
        self,
        cr,
        x: int,
        y: int,
        *,
        dark_mode: bool,
        active: bool,
    ):
        cx = float(x)
        cy = float(y)
        if dark_mode:
            outer = (0.74, 0.89, 1.0, 0.32 if active else 0.2)
            ring = (0.62, 0.84, 1.0, 0.96 if active else 0.72)
            inner = (0.08, 0.19, 0.34, 0.86 if active else 0.72)
        else:
            outer = (0.32, 0.58, 0.98, 0.26 if active else 0.16)
            ring = (0.2, 0.48, 0.94, 0.84 if active else 0.62)
            inner = (0.92, 0.96, 1.0, 0.9 if active else 0.78)

        cr.new_path()
        cr.arc(cx, cy, 13.0 if active else 11.0, 0, math.tau)
        cr.set_source_rgba(*outer)
        cr.fill()

        cr.new_path()
        cr.arc(cx, cy, 8.6 if active else 7.4, 0, math.tau)
        cr.set_source_rgba(*inner)
        cr.fill_preserve()
        cr.set_source_rgba(*ring)
        cr.set_line_width(2.0 if active else 1.6)
        cr.stroke()

    def draw_single_handle(
        self,
        cr,
        x: float,
        y: float,
        *,
        dark_mode: bool,
        outgoing: bool,
        selected: bool,
        hovered: bool,
        source_active: bool,
    ):
        if hovered:
            radius = 10.8
            ring_alpha = 0.9 if dark_mode else 0.8
            core_alpha = 0.98
        elif selected or source_active:
            radius = 9.4
            ring_alpha = 0.76 if dark_mode else 0.66
            core_alpha = 0.96
        else:
            radius = 8.2
            ring_alpha = 0.62 if dark_mode else 0.52
            core_alpha = 0.95

        if outgoing:
            if dark_mode:
                ring_color = (0.47, 0.74, 1.0)
                core_color = (0.75, 0.89, 1.0)
            else:
                ring_color = (0.13, 0.43, 0.9)
                core_color = (0.21, 0.5, 0.98)
        else:
            if dark_mode:
                ring_color = (0.58, 0.71, 0.9)
                core_color = (0.88, 0.93, 1.0)
            else:
                ring_color = (0.34, 0.46, 0.66)
                core_color = (0.52, 0.63, 0.8)

        cr.arc(x, y, radius, 0, math.tau)
        cr.set_source_rgba(*ring_color, ring_alpha)
        cr.set_line_width(2.4 if hovered else 1.9)
        cr.stroke()

        cr.arc(x, y, max(2.0, radius - 3.0), 0, math.tau)
        cr.set_source_rgba(*core_color, core_alpha)
        cr.fill()

    def trace_edge_curve(self, cr, start_x, start_y, end_x, end_y, control_offset):
        cr.move_to(start_x, start_y)
        cr.curve_to(
            start_x + control_offset,
            start_y,
            end_x - control_offset,
            end_y,
            end_x,
            end_y,
        )

    def draw_edge_arrow(
        self,
        cr,
        end_x: float,
        end_y: float,
        control_x: float,
        control_y: float,
        color: tuple[float, float, float, float],
        is_selected_path: bool,
    ):
        angle = math.atan2(end_y - control_y, end_x - control_x)
        arrow_size = 10 if is_selected_path else 8
        left_angle = angle + 2.6
        right_angle = angle - 2.6

        left_x = end_x + arrow_size * math.cos(left_angle)
        left_y = end_y + arrow_size * math.sin(left_angle)
        right_x = end_x + arrow_size * math.cos(right_angle)
        right_y = end_y + arrow_size * math.sin(right_angle)

        cr.move_to(end_x, end_y)
        cr.line_to(left_x, left_y)
        cr.line_to(right_x, right_y)
        cr.close_path()
        cr.set_source_rgba(*color)
        cr.fill()

    def cubic_bezier_point(
        self,
        p0x: float,
        p0y: float,
        p1x: float,
        p1y: float,
        p2x: float,
        p2y: float,
        p3x: float,
        p3y: float,
        t: float,
    ) -> tuple[float, float]:
        one_minus_t = 1 - t
        x = (
            (one_minus_t ** 3) * p0x
            + 3 * (one_minus_t ** 2) * t * p1x
            + 3 * one_minus_t * (t ** 2) * p2x
            + (t ** 3) * p3x
        )
        y = (
            (one_minus_t ** 3) * p0y
            + 3 * (one_minus_t ** 2) * t * p1y
            + 3 * one_minus_t * (t ** 2) * p2y
            + (t ** 3) * p3y
        )
        return x, y

    def draw_rounded_rect(self, cr, x: float, y: float, width: float, height: float, radius: float):
        corner = min(radius, width / 2, height / 2)
        cr.new_sub_path()
        cr.arc(x + width - corner, y + corner, corner, -math.pi / 2, 0)
        cr.arc(x + width - corner, y + height - corner, corner, 0, math.pi / 2)
        cr.arc(x + corner, y + height - corner, corner, math.pi / 2, math.pi)
        cr.arc(x + corner, y + corner, corner, math.pi, 3 * math.pi / 2)
        cr.close_path()

    def node_input_anchor(self, node: CanvasNode) -> tuple[int, int]:
        y_offset = max(12, min(18, self.card_screen_height() // 6))
        return (
            self.to_screen(node.x) + 4,
            self.to_screen(node.y) + self.card_screen_height() - y_offset,
        )

    def node_output_anchor(self, node: CanvasNode) -> tuple[int, int]:
        y_offset = max(12, min(18, self.card_screen_height() // 6))
        return (
            self.to_screen(node.x) + self.card_screen_width() - 4,
            self.to_screen(node.y) + self.card_screen_height() - y_offset,
        )

    def find_node(self, node_id: str) -> CanvasNode | None:
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def ensure_node_visible(self, node: CanvasNode):
        if not self.canvas_scroll:
            return
        hadj = self.canvas_scroll.get_hadjustment()
        vadj = self.canvas_scroll.get_vadjustment()
        if not hadj or not vadj:
            return

        target_x = max(
            hadj.get_lower(),
            min(
                self.to_screen(node.x) - 120,
                hadj.get_upper() - hadj.get_page_size(),
            ),
        )
        target_y = max(
            vadj.get_lower(),
            min(
                self.to_screen(node.y) - 120,
                vadj.get_upper() - vadj.get_page_size(),
            ),
        )
        hadj.set_value(target_x)
        vadj.set_value(target_y)

    def find_node_at_point(
        self,
        x: int,
        y: int,
        exclude_node_id: str | None = None,
    ) -> CanvasNode | None:
        for node in reversed(self.nodes):
            if exclude_node_id and node.id == exclude_node_id:
                continue
            node_x = self.to_screen(node.x)
            node_y = self.to_screen(node.y)
            node_width = self.card_screen_width()
            node_height = self.card_screen_height()
            if node_x <= x <= (node_x + node_width) and node_y <= y <= (node_y + node_height):
                return node
        return None

    def get_selected_node(self) -> CanvasNode | None:
        if self.selected_node_id:
            node = self.find_node(self.selected_node_id)
            if node:
                if self.selected_node_id not in self.selected_node_ids:
                    self.selected_node_ids.add(self.selected_node_id)
                return node
        if self.selected_node_ids:
            fallback_id = next(iter(self.selected_node_ids))
            fallback = self.find_node(fallback_id)
            if fallback:
                self.selected_node_id = fallback.id
                return fallback
            self.selected_node_ids = set()
        self.selected_node_id = None
        return None

    def provider_index(self, value: str) -> int:
        normalized = value.strip().lower()
        if normalized in self.PROVIDER_OPTIONS:
            return self.PROVIDER_OPTIONS.index(normalized)
        return 0

    def selected_provider_override(self) -> str:
        index = self.edit_provider_dropdown.get_selected()
        if 0 <= index < len(self.PROVIDER_OPTIONS):
            return self.PROVIDER_OPTIONS[index]
        return "inherit"

    def set_detail_text(self, text: str):
        self.edit_detail_buffer.set_text(text)

    def get_detail_text(self) -> str:
        start = self.edit_detail_buffer.get_start_iter()
        end = self.edit_detail_buffer.get_end_iter()
        return self.edit_detail_buffer.get_text(start, end, False)

    def on_apply_node_changes(self, _button):
        node = self.get_selected_node()
        if not node:
            return

        updated_name = self.edit_name_entry.get_text().strip() or node.name
        updated_summary = self.edit_summary_entry.get_text().strip()
        updated_detail = self.get_detail_text().strip()
        updated_config = self.build_updated_node_config(node)
        node_kind = self.node_type_key(node.node_type)
        if node_kind == "trigger":
            trigger_issues = self.apply_trigger_validation_feedback()
            trigger_errors = [item for item in trigger_issues if item[1] == "error"]
            if trigger_errors:
                self.set_status(f"Apply blocked: {trigger_errors[0][2]}")
                return
        if node_kind == "condition":
            condition_issues = self.apply_condition_validation_feedback()
            condition_errors = [item for item in condition_issues if item[1] == "error"]
            if condition_errors:
                self.set_status(f"Apply blocked: {condition_errors[0][2]}")
                return
        if node_kind in {"action", "template"}:
            missing_fields = self.missing_required_action_fields(
                updated_config,
                app_settings=self.settings_store.load_settings(),
            )
            if missing_fields:
                missing_label = ", ".join(missing_fields[:3])
                if len(missing_fields) > 3:
                    missing_label = f"{missing_label}, +{len(missing_fields) - 3} more"
                self.set_status(
                    f"Apply blocked: missing required field(s): {missing_label}."
                )
                self.node_test_status_label.set_text(
                    f"Required fields missing: {missing_label}"
                )
                return

        self.push_undo_snapshot()
        node.name = updated_name
        node.summary = updated_summary
        node.detail = updated_detail
        node.config = updated_config
        if node_kind == "trigger":
            node.detail = self.current_trigger_detail()
            self.set_detail_text(node.detail)

        self.refresh_canvas()
        self.update_inspector(node)
        self.maybe_auto_save("Node changes applied and auto-saved.")
        self.inline_validate_graph()

    def build_updated_node_config(self, node: CanvasNode) -> dict[str, str]:
        updated_config = dict(node.config)
        node_key = self.node_type_key(node.node_type)
        updated_config["provider"] = self.selected_provider_override()
        updated_config["model"] = self.edit_model_entry.get_text().strip()
        updated_config["bot"] = self.edit_bot_entry.get_text().strip()
        updated_config["bot_chain"] = self.edit_bot_chain_entry.get_text().strip()
        updated_config["system"] = self.edit_system_entry.get_text().strip()
        updated_config["temperature"] = self.current_inspector_temperature()
        updated_config["max_tokens"] = self.current_inspector_max_tokens()
        updated_config["expression"] = self.current_condition_expression()
        if node_key == "trigger":
            updated_config["trigger_mode"] = self.selected_trigger_mode()
            updated_config["trigger_value"] = self.current_trigger_value()
        else:
            updated_config["trigger_mode"] = ""
            updated_config["trigger_value"] = ""
        self.apply_action_controls_to_config(updated_config, node.node_type)
        self.apply_node_execution_controls_to_config(updated_config, node.node_type)
        return {
            key: value
            for key, value in updated_config.items()
            if value and (key != "provider" or value != "inherit")
        }

    def required_field_value(
        self,
        config: dict[str, str],
        field_name: str,
        *,
        integration_key: str = "",
        app_settings: dict[str, str] | None = None,
    ) -> str:
        key = str(field_name).strip().lower()
        candidates = [key, *self.REQUIRED_FIELD_ALIASES.get(key, [])]
        for candidate in candidates:
            value = str(config.get(candidate, "")).strip()
            if value:
                return value
        if key in {"spreadsheet_id", "range"}:
            payload_raw = str(config.get("payload", "")).strip()
            if payload_raw:
                try:
                    payload = json.loads(payload_raw)
                except Exception:
                    payload = None
                if isinstance(payload, dict):
                    payload_value = str(payload.get(key, "")).strip()
                    if payload_value:
                        return payload_value
        if integration_key and isinstance(app_settings, dict) and app_settings:
            try:
                fallback = self.validation_service._required_field_value(
                    config,
                    key,
                    integration_key=integration_key,
                    app_settings=app_settings,
                )
                if str(fallback).strip():
                    return str(fallback).strip()
            except Exception:
                pass
        return ""

    def missing_required_action_fields(
        self,
        config: dict[str, str],
        app_settings: dict[str, str] | None = None,
    ) -> list[str]:
        integration_key = str(config.get("integration", "standard")).strip().lower() or "standard"
        integration = self.integration_registry.get_integration(integration_key)
        if not integration:
            return ["integration"]

        missing: list[str] = []
        required_fields = integration.get("required_fields", [])
        if not isinstance(required_fields, list):
            return missing
        for raw_field in required_fields:
            field = str(raw_field).strip().lower()
            if not field:
                continue
            if not self.required_field_value(
                config,
                field,
                integration_key=integration_key,
                app_settings=app_settings,
            ):
                missing.append(field)
        return missing

    def action_field_key_for_requirement(self, required_field: str) -> str:
        field = str(required_field).strip().lower()
        mapping = {
            "url": "endpoint",
            "webhook_url": "endpoint",
            "script_url": "endpoint",
            "connection_url": "endpoint",
            "method": "method",
            "headers": "headers",
            "payload": "payload",
            "text": "message",
            "message": "message",
            "content": "message",
            "approval_message": "message",
            "api_key": "api_key",
            "auth_token": "auth_token",
            "location": "location",
            "units": "units",
            "path": "path",
            "command": "command",
            "to": "to",
            "from": "from",
            "subject": "subject",
            "chat_id": "chat_id",
            "account_sid": "account_sid",
            "domain": "domain",
            "spreadsheet_id": "payload",
            "range": "payload",
            "sql": "payload",
            "query": "payload",
            "integration": "integration",
        }
        return mapping.get(field, "payload")

    def build_action_inline_validation_issues(
        self,
        integration_key: str,
        merged: dict[str, str],
        missing_fields: list[str],
        app_settings: dict[str, str],
    ) -> list[tuple[str, str, str]]:
        issues: list[tuple[str, str, str]] = []

        for field in missing_fields:
            target_field = self.action_field_key_for_requirement(field)
            issues.append(
                (
                    target_field,
                    "error",
                    f"Missing required field: {field}",
                )
            )

        endpoint_value = self.required_field_value(
            merged,
            "url",
            integration_key=integration_key,
            app_settings=app_settings,
        )
        connection_value = self.required_field_value(
            merged,
            "connection_url",
            integration_key=integration_key,
            app_settings=app_settings,
        )
        http_endpoint_integrations = {
            "http_request",
            "http_post",
            "slack_webhook",
            "discord_webhook",
            "teams_webhook",
            "google_apps_script",
            "google_calendar_api",
            "outlook_graph",
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
            "resend_email",
            "mailgun_email",
        }
        if (
            endpoint_value
            and integration_key in http_endpoint_integrations
            and not endpoint_value.startswith(("http://", "https://"))
        ):
            issues.append(("endpoint", "error", "Endpoint must begin with http:// or https://"))

        if integration_key == "postgres_sql" and connection_value:
            lowered = connection_value.lower()
            if not lowered.startswith(("postgres://", "postgresql://")):
                issues.append(
                    ("endpoint", "error", "Postgres connection URL must begin with postgres:// or postgresql://")
                )
        if integration_key == "mysql_sql" and connection_value:
            lowered = connection_value.lower()
            if not lowered.startswith(("mysql://", "mysql2://")):
                issues.append(
                    ("endpoint", "error", "MySQL connection URL must begin with mysql:// or mysql2://")
                )
        if integration_key == "redis_command" and connection_value:
            lowered = connection_value.lower()
            if not lowered.startswith(("redis://", "rediss://")):
                issues.append(
                    ("endpoint", "error", "Redis connection URL must begin with redis:// or rediss://")
                )

        if integration_key in {"http_request", "http_post"}:
            method_value = str(merged.get("method", "POST")).strip().upper()
            valid_methods = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}
            if method_value and method_value not in valid_methods:
                issues.append(("method", "error", f"Unsupported HTTP method: {method_value}"))

        headers_raw = str(merged.get("headers", "")).strip()
        if headers_raw and integration_key in {
            "http_request",
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "google_calendar_api",
            "outlook_graph",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
        }:
            try:
                parsed_headers = json.loads(headers_raw)
                if not isinstance(parsed_headers, dict):
                    issues.append(("headers", "error", "Headers must be a JSON object."))
            except Exception:
                issues.append(("headers", "error", "Headers must be valid JSON."))

        payload_raw = str(merged.get("payload", "")).strip()
        if payload_raw and integration_key in {
            "http_request",
            "http_post",
            "google_apps_script",
            "google_sheets",
            "google_calendar_api",
            "notion_api",
            "airtable_api",
            "hubspot_api",
            "stripe_api",
            "github_rest",
            "gitlab_api",
            "google_drive_api",
            "dropbox_api",
            "shopify_api",
            "webflow_api",
            "supabase_api",
            "openrouter_api",
            "linear_api",
            "outlook_graph",
            "jira_api",
            "asana_api",
            "clickup_api",
            "trello_api",
            "monday_api",
            "zendesk_api",
            "pipedrive_api",
            "salesforce_api",
            "telegram_bot",
            "twilio_sms",
            "resend_email",
            "mailgun_email",
        }:
            try:
                json.loads(payload_raw)
            except Exception:
                issues.append(("payload", "error", "Payload must be valid JSON for this integration."))

        if integration_key in {"postgres_sql", "mysql_sql", "sqlite_sql"}:
            sql_value = payload_raw or self.required_field_value(
                merged,
                "sql",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            if sql_value:
                lowered_sql = sql_value.strip().lower()
                if len(sql_value.strip()) < 6:
                    issues.append(("payload", "warning", "SQL query appears very short."))
                elif not lowered_sql.startswith(
                    ("select", "insert", "update", "delete", "create", "alter", "drop", "with", "pragma")
                ):
                    issues.append(("payload", "warning", "SQL does not start with a common statement keyword."))
            if integration_key == "sqlite_sql":
                path_value = self.required_field_value(
                    merged,
                    "path",
                    integration_key=integration_key,
                    app_settings=app_settings,
                )
                if path_value and not path_value.lower().endswith((".db", ".sqlite", ".sqlite3")):
                    issues.append(("path", "warning", "SQLite DB path usually ends with .db or .sqlite"))

        if integration_key == "redis_command":
            redis_cmd = self.required_field_value(
                merged,
                "command",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            if redis_cmd.lower().startswith("redis-cli"):
                issues.append(
                    (
                        "command",
                        "warning",
                        "Use raw Redis command (for example 'ping'); redis-cli is added automatically.",
                    )
                )

        if integration_key == "s3_cli":
            s3_cmd = self.required_field_value(
                merged,
                "command",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            lowered = s3_cmd.strip().lower()
            if lowered and not (lowered.startswith("s3 ") or lowered.startswith("aws ")):
                issues.append(
                    (
                        "command",
                        "warning",
                        "S3 command usually starts with 's3 ...' or 'aws s3 ...'.",
                    )
                )

        if integration_key in {"gmail_send", "resend_email", "mailgun_email"}:
            to_value = self.required_field_value(
                merged,
                "to",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            if to_value and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", to_value):
                issues.append(("to", "error", "Recipient email format looks invalid"))
            from_value = self.required_field_value(
                merged,
                "from",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            if from_value and from_value != "me" and not re.match(
                r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
                from_value,
            ):
                issues.append(("from", "error", "Sender email format looks invalid"))

        if integration_key == "twilio_sms":
            from_value = self.required_field_value(
                merged,
                "from",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            to_value = self.required_field_value(
                merged,
                "to",
                integration_key=integration_key,
                app_settings=app_settings,
            )
            phone_pattern = re.compile(r"^\+?[0-9][0-9\-\s]{6,}$")
            if from_value and not phone_pattern.match(from_value):
                issues.append(("from", "error", "Twilio from number format looks invalid"))
            if to_value and not phone_pattern.match(to_value):
                issues.append(("to", "error", "Twilio to number format looks invalid"))

        timeout_raw = str(merged.get("timeout_sec", "")).strip()
        if timeout_raw:
            try:
                timeout_value = float(timeout_raw)
                if timeout_value < 0:
                    issues.append(("timeout_sec", "error", "Timeout must be >= 0"))
                elif timeout_value > 180:
                    issues.append(
                        ("timeout_sec", "warning", "Timeout is high and may slow workflow responsiveness")
                    )
            except ValueError:
                issues.append(("timeout_sec", "error", "Timeout must be numeric"))

        return issues

    def clear_node_test_result(self):
        self.node_test_status_label.set_text("")
        self.node_test_result_summary_label.set_text("No node test has been run yet.")
        self.node_test_result_output_buffer.set_text("")
        self.node_test_result_state_chip.set_text("IDLE")
        self.node_test_result_state_chip.remove_css_class("node-test-state-running")
        self.node_test_result_state_chip.remove_css_class("node-test-state-success")
        self.node_test_result_state_chip.remove_css_class("node-test-state-error")
        self.node_test_result_state_chip.add_css_class("node-test-state-idle")
        self.node_test_result_card.set_visible(False)

    def configure_node_test_controls(self, node_type: str | None):
        node_key = self.node_type_key(node_type or "")
        is_action_like = node_key in {"action", "template"}
        is_ai = node_key == "ai"
        is_condition = node_key == "condition"
        self.action_scaffold_button.set_visible(is_action_like)

        if is_action_like:
            self.test_node_button.set_label("Test Integration Node")
            return
        if is_ai:
            self.test_node_button.set_label("Test AI Node")
            return
        if is_condition:
            self.test_node_button.set_label("Preview Branch")
            return
        self.test_node_button.set_label("Test Selected Node")

    def format_structured_output_preview(self, output: str) -> tuple[str, str]:
        text = str(output).strip()
        if not text:
            return "", ""
        try:
            parsed = json.loads(text)
        except Exception:
            return "", text
        if isinstance(parsed, dict):
            keys = sorted(str(item) for item in parsed.keys())
            preview = ", ".join(keys[:8])
            if len(keys) > 8:
                preview = f"{preview}, +{len(keys) - 8} more"
            summary = f"Structured output detected (JSON object): {preview or 'no keys'}."
            return summary, json.dumps(parsed, indent=2, ensure_ascii=True)
        if isinstance(parsed, list):
            summary = f"Structured output detected (JSON array with {len(parsed)} item(s))."
            return summary, json.dumps(parsed, indent=2, ensure_ascii=True)
        return "Structured output detected (JSON scalar).", json.dumps(parsed, ensure_ascii=True)

    def set_node_test_result(
        self,
        state: str,
        summary: str,
        *,
        output: str = "",
        logs: list[str] | None = None,
    ):
        normalized = str(state).strip().lower() or "idle"
        chip_text = {
            "running": "RUNNING",
            "success": "SUCCESS",
            "error": "ERROR",
            "idle": "IDLE",
        }.get(normalized, normalized.upper())

        self.node_test_result_state_chip.set_text(chip_text)
        self.node_test_result_state_chip.remove_css_class("node-test-state-idle")
        self.node_test_result_state_chip.remove_css_class("node-test-state-running")
        self.node_test_result_state_chip.remove_css_class("node-test-state-success")
        self.node_test_result_state_chip.remove_css_class("node-test-state-error")
        if normalized == "running":
            self.node_test_result_state_chip.add_css_class("node-test-state-running")
        elif normalized == "success":
            self.node_test_result_state_chip.add_css_class("node-test-state-success")
        elif normalized == "error":
            self.node_test_result_state_chip.add_css_class("node-test-state-error")
        else:
            self.node_test_result_state_chip.add_css_class("node-test-state-idle")

        summary_text = str(summary).strip() or "Node test update."
        self.node_test_status_label.set_text(summary_text)
        self.node_test_result_summary_label.set_text(summary_text)

        rendered_blocks: list[str] = []
        trimmed_logs = [str(item).strip() for item in (logs or []) if str(item).strip()]
        if trimmed_logs:
            rendered_blocks.append("Logs:\n" + "\n".join(trimmed_logs[-14:]))
        rendered_output = str(output).strip()
        if rendered_output:
            if len(rendered_output) > 3600:
                rendered_output = f"{rendered_output[:3597]}..."
            rendered_blocks.append("Output:\n" + rendered_output)

        self.node_test_result_output_buffer.set_text("\n\n".join(rendered_blocks))
        self.node_test_result_card.set_visible(True)

    def on_test_selected_node_clicked(self, _button):
        node = self.get_selected_node()
        if not node:
            return

        node_key = self.node_type_key(node.node_type)
        if node_key not in {"action", "template", "ai", "condition"}:
            self.set_node_test_result("error", "Node test is available for action, AI, and condition nodes.")
            return

        temp_node = CanvasNode(
            id=node.id,
            name=self.edit_name_entry.get_text().strip() or node.name,
            node_type=node.node_type,
            detail=self.get_detail_text().strip(),
            summary=self.edit_summary_entry.get_text().strip(),
            x=node.x,
            y=node.y,
            config=self.build_updated_node_config(node),
        )

        if node_key == "condition":
            self.run_condition_preview_test(temp_node)
            return

        if node_key in {"action", "template"}:
            integration = self.selected_action_integration()
            if not integration:
                self.set_node_test_result("error", "Choose an integration first.")
                return
            missing_fields = self.missing_required_action_fields(temp_node.config)
            if missing_fields:
                missing_label = ", ".join(missing_fields[:3])
                if len(missing_fields) > 3:
                    missing_label = f"{missing_label}, +{len(missing_fields) - 3} more"
                self.set_node_test_result(
                    "error",
                    f"Fill required fields first: {missing_label}",
                )
                return

            self.test_node_button.set_sensitive(False)
            self.set_node_test_result(
                "running",
                f"Testing '{integration}' integration...",
            )
            threading.Thread(
                target=self._run_action_node_test_worker,
                args=(temp_node,),
                daemon=True,
            ).start()
            return

        self.test_node_button.set_sensitive(False)
        self.set_node_test_result(
            "running",
            "Testing AI node with current provider/model settings...",
        )
        threading.Thread(
            target=self._run_ai_node_test_worker,
            args=(temp_node,),
            daemon=True,
        ).start()

    def run_condition_preview_test(self, node: CanvasNode):
        expression = str(node.config.get("expression", "")).strip() or node.detail.strip()
        if not expression:
            self.set_node_test_result("error", "Condition expression is empty.")
            return

        sample_input = self.condition_preview_input_entry.get_text().strip()
        try:
            result = self.execution_engine.evaluate_condition_for_test(expression, sample_input)
        except Exception as error:
            self.set_node_test_result("error", f"Condition preview failed: {error}")
            return

        outgoing = [edge for edge in self.edges if edge.source_node_id == node.id]
        target_id = self.execution_engine.choose_condition_branch_for_test(outgoing, result)
        target_name = ""
        if target_id:
            target_node = self.find_node(target_id)
            target_name = target_node.name if target_node else target_id
        branch_text = "true" if result else "false"
        summary = (
            f"Condition evaluated {branch_text} and routes to '{target_name}'."
            if target_name
            else f"Condition evaluated {branch_text} with no resolved outgoing branch."
        )
        output_lines = [
            f"Expression: {expression}",
            f"Sample Input: {sample_input or '(empty)'}",
            f"Result: {branch_text.upper()}",
            f"Branch Target: {target_name or '(none)'}",
        ]
        self.set_node_test_result(
            "success",
            summary,
            output="\n".join(output_lines),
        )
        self.refresh_condition_branch_preview()

    def _run_action_node_test_worker(self, node: CanvasNode):
        try:
            logs, output = self.execution_engine.execute_action_node_for_test(
                node,
                input_context="Inspector test context",
            )
        except Exception as error:
            GLib.idle_add(self._finish_node_test_error, str(error))
            return
        GLib.idle_add(self._finish_node_test_success, logs, output)

    def _run_ai_node_test_worker(self, node: CanvasNode):
        try:
            logs, output = self.execution_engine.execute_ai_node_for_test(
                node,
                input_context=self.condition_preview_input_entry.get_text().strip(),
            )
        except Exception as error:
            GLib.idle_add(self._finish_node_test_error, str(error))
            return
        GLib.idle_add(self._finish_ai_node_test_success, logs, output)

    def _finish_node_test_success(self, logs: list[str], output: str):
        self.test_node_button.set_sensitive(True)
        summary = logs[-1] if logs else "Node test completed."
        self.set_node_test_result(
            "success",
            summary,
            output=str(output),
            logs=logs,
        )
        return False

    def _finish_ai_node_test_success(self, logs: list[str], output: str):
        self.test_node_button.set_sensitive(True)
        summary = logs[-1] if logs else "AI node test completed."
        structured_summary, rendered_output = self.format_structured_output_preview(output)
        if structured_summary:
            summary = f"{summary} {structured_summary}"
        self.set_node_test_result(
            "success",
            summary,
            output=rendered_output or str(output),
            logs=logs,
        )
        return False

    def _finish_node_test_error(self, error_message: str):
        self.test_node_button.set_sensitive(True)
        self.set_node_test_result(
            "error",
            f"Node test failed: {error_message}",
        )
        return False

    def update_inspector(self, node: CanvasNode):
        incoming = len([edge for edge in self.edges if edge.target_node_id == node.id])
        outgoing = len([edge for edge in self.edges if edge.source_node_id == node.id])
        self.clear_node_field_feedback()

        self.node_name_label.set_text(node.name)
        self.node_type_label.set_text(f"Type: {node.node_type}")
        self.node_position_label.set_text(f"Position: {node.x}, {node.y}")
        self.node_link_label.set_text(f"Links: {incoming} incoming, {outgoing} outgoing")
        self.node_summary_label.set_text(node.summary or "No summary configured.")
        self.node_detail_label.set_text(node.detail or "No detail configured.")

        merged_config = self.parse_detail_directives(node.detail)
        merged_config.update(node.config)

        self.edit_name_entry.set_text(node.name)
        self.edit_summary_entry.set_text(node.summary)
        self.set_detail_text(node.detail)
        self.edit_provider_dropdown.set_selected(
            self.provider_index(merged_config.get("provider", "inherit"))
        )
        self.edit_model_entry.set_text(merged_config.get("model", ""))
        self.edit_bot_entry.set_text(merged_config.get("bot", ""))
        self.edit_bot_chain_entry.set_text(merged_config.get("bot_chain", ""))
        self.edit_system_entry.set_text(merged_config.get("system", ""))
        temp_value = self.parse_float(merged_config.get("temperature", ""), 0.2)
        has_temp = bool(str(merged_config.get("temperature", "")).strip())
        self.edit_temp_override_switch.set_active(has_temp)
        self.edit_temp_scale.set_value(temp_value)
        self.edit_temp_spin.set_value(temp_value)

        token_value = self.parse_int(merged_config.get("max_tokens", ""), 700)
        has_tokens = bool(str(merged_config.get("max_tokens", "")).strip())
        self.edit_tokens_override_switch.set_active(has_tokens)
        self.edit_tokens_scale.set_value(float(token_value))
        self.edit_tokens_spin.set_value(float(token_value))

        self.load_trigger_controls(merged_config, node.detail)
        self.load_condition_controls(merged_config.get("expression", ""))
        if not self.condition_preview_input_entry.get_text().strip():
            self.condition_preview_input_entry.set_text(
                str(node.summary).strip() or "sample workflow output"
            )
        self.load_action_controls(merged_config)
        self.load_node_execution_controls(merged_config, node.node_type)
        self.clear_node_test_result()
        self.configure_node_test_controls(node.node_type)
        self.refresh_condition_branch_preview()
        self.update_inspector_adjustment_states()
        self.update_action_integration_section_visibility(node.node_type)
        self.update_sidebar_mode()

    def clear_inspector(self):
        self.node_name_label.set_text("No node selected")
        self.node_type_label.set_text("Type: —")
        self.node_position_label.set_text("Position: —")
        self.node_link_label.set_text("Links: —")
        self.node_summary_label.set_text("Select a node to inspect its details.")
        self.node_detail_label.set_text("")

        self.edit_name_entry.set_text("")
        self.edit_summary_entry.set_text("")
        self.set_detail_text("")
        self.detail_expander.set_expanded(False)
        self.trigger_mode_dropdown.set_selected(self.trigger_mode_index("manual"))
        self.trigger_interval_scale.set_value(300)
        self.trigger_interval_spin.set_value(300)
        self.trigger_webhook_entry.set_text("")
        self.trigger_watch_path_entry.set_text("")
        self.trigger_cron_entry.set_text("")
        self.trigger_value_entry.set_text("")
        self.action_template_dropdown.set_selected(self.action_template_index("generic_action"))
        self.update_action_template_hint()
        self.sync_action_category_state("notify")
        self.edit_provider_dropdown.set_selected(0)
        self.edit_model_entry.set_text("")
        self.edit_bot_entry.set_text("")
        self.edit_bot_chain_entry.set_text("")
        self.edit_system_entry.set_text("")
        self.edit_temp_override_switch.set_active(False)
        self.edit_temp_scale.set_value(0.2)
        self.edit_temp_spin.set_value(0.2)
        self.edit_tokens_override_switch.set_active(False)
        self.edit_tokens_scale.set_value(700)
        self.edit_tokens_spin.set_value(700)
        self.edit_condition_mode_dropdown.set_selected(0)
        self.edit_condition_value_entry.set_text("")
        self.edit_condition_min_len_scale.set_value(120)
        self.edit_condition_min_len_spin.set_value(120)
        self.condition_preview_input_entry.set_text("")
        self.condition_preview_label.set_text("Select a condition node to preview branch routing.")
        self.action_integration_dropdown.set_selected(
            self.action_integration_index("standard")
        )
        self.action_endpoint_entry.set_text("")
        self.action_method_dropdown.set_selected(self.action_method_index("POST"))
        self.action_message_entry.set_text("")
        self.action_to_entry.set_text("")
        self.action_from_entry.set_text("")
        self.action_subject_entry.set_text("")
        self.action_chat_id_entry.set_text("")
        self.action_account_sid_entry.set_text("")
        self.action_auth_token_entry.set_text("")
        self.action_domain_entry.set_text("")
        self.action_username_entry.set_text("")
        self.set_action_payload_text("")
        self.action_headers_entry.set_text("")
        self.action_api_key_entry.set_text("")
        self.action_location_entry.set_text("")
        self.action_units_dropdown.set_selected(0)
        self.action_path_entry.set_text("")
        self.action_command_entry.set_text("")
        self.action_timeout_spin.set_value(0.0)
        self.apply_node_execution_defaults_for_context("Action", "standard", announce=False)
        self.node_execution_hint_label.set_text("")
        self.clear_node_test_result()
        self.test_node_button.set_sensitive(False)
        self.configure_node_test_controls(None)
        self.update_trigger_controls_state()
        self.update_condition_controls_state()
        self.update_inspector_adjustment_states()
        self.update_action_integration_section_visibility(None)
        self.update_action_integration_field_visibility()
        self.clear_action_field_feedback()
        self.clear_node_field_feedback()
        self.update_sidebar_mode()

    def update_sidebar_mode(self):
        has_selected = self.get_selected_node() is not None
        self.workflow_mode_scroll.set_visible(not has_selected)
        self.node_mode_scroll.set_visible(has_selected)
        if has_selected:
            self.scroll_scroller_to_top(self.node_mode_scroll)
        else:
            self.scroll_scroller_to_top(self.workflow_mode_scroll)

    def update_action_integration_section_visibility(self, node_type: str | None):
        node_key = self.node_type_key(node_type or "")
        is_trigger = node_key == "trigger"
        is_action_like = node_key in {"action", "template"}
        is_ai = node_key == "ai"
        is_condition = node_key == "condition"

        self.trigger_section.set_visible(is_trigger)
        self.action_integration_section.set_visible(is_action_like)
        self.node_test_section.set_visible(node_key in {"action", "template", "ai", "condition"})

        show_advanced = node_key in {"action", "template", "ai", "condition"}
        self.detail_expander.set_visible(show_advanced)

        show_ai_fields = is_ai
        self.provider_label.set_visible(show_ai_fields)
        self.edit_provider_dropdown.set_visible(show_ai_fields)
        self.edit_model_entry.set_visible(show_ai_fields)
        self.edit_bot_entry.set_visible(show_ai_fields)
        self.edit_bot_chain_entry.set_visible(show_ai_fields)
        self.edit_system_entry.set_visible(show_ai_fields)
        self.temp_title.set_visible(show_ai_fields)
        self.edit_temp_override_switch.set_visible(show_ai_fields)
        self.temp_adjust_row.set_visible(show_ai_fields)
        self.max_tokens_title.set_visible(show_ai_fields)
        self.edit_tokens_override_switch.set_visible(show_ai_fields)
        self.max_tokens_adjust_row.set_visible(show_ai_fields)

        self.condition_title.set_visible(is_condition)
        self.condition_mode_row.set_visible(is_condition)
        self.condition_value_row.set_visible(
            is_condition and self.selected_condition_mode() in {"contains", "equals", "not_contains", "regex", "raw"}
        )
        self.condition_min_len_field_row.set_visible(
            is_condition and self.selected_condition_mode() == "min_len"
        )
        self.configure_node_test_controls(node_type)
        self.update_trigger_controls_state()
        self.update_condition_controls_state()

    def scroll_scroller_to_top(self, scroller: Gtk.ScrolledWindow):
        try:
            adjustment = scroller.get_vadjustment()
            if adjustment:
                adjustment.set_value(adjustment.get_lower())
        except Exception:
            pass

    def on_temp_override_toggled(self, _switch, _param):
        self.update_inspector_adjustment_states()

    def on_tokens_override_toggled(self, _switch, _param):
        self.update_inspector_adjustment_states()

    def update_inspector_adjustment_states(self):
        temp_enabled = self.edit_temp_override_switch.get_active()
        self.edit_temp_scale.set_sensitive(temp_enabled)
        self.edit_temp_spin.set_sensitive(temp_enabled)

        tokens_enabled = self.edit_tokens_override_switch.get_active()
        self.edit_tokens_scale.set_sensitive(tokens_enabled)
        self.edit_tokens_spin.set_sensitive(tokens_enabled)

    def on_temp_scale_changed(self, scale: Gtk.Scale):
        value = round(scale.get_value(), 2)
        if abs(self.edit_temp_spin.get_value() - value) > 0.005:
            self.edit_temp_spin.set_value(value)

    def on_temp_spin_changed(self, spin: Gtk.SpinButton):
        value = round(spin.get_value(), 2)
        if abs(self.edit_temp_scale.get_value() - value) > 0.005:
            self.edit_temp_scale.set_value(value)

    def on_tokens_scale_changed(self, scale: Gtk.Scale):
        value = int(scale.get_value())
        if self.edit_tokens_spin.get_value_as_int() != value:
            self.edit_tokens_spin.set_value(value)

    def on_tokens_spin_changed(self, spin: Gtk.SpinButton):
        value = spin.get_value_as_int()
        if int(self.edit_tokens_scale.get_value()) != value:
            self.edit_tokens_scale.set_value(value)

    def on_condition_mode_changed(self, *_args):
        self.update_condition_controls_state()

    def on_trigger_interval_scale_changed(self, scale: Gtk.Scale):
        value = int(scale.get_value())
        if self.trigger_interval_spin.get_value_as_int() != value:
            self.trigger_interval_spin.set_value(value)

    def on_trigger_interval_spin_changed(self, spin: Gtk.SpinButton):
        value = spin.get_value_as_int()
        if int(self.trigger_interval_scale.get_value()) != value:
            self.trigger_interval_scale.set_value(value)

    def sync_trigger_mode_quick_state(self, mode: str):
        normalized = str(mode).strip().lower()
        if normalized not in self.trigger_mode_quick_buttons:
            normalized = "manual"
        self.syncing_trigger_mode_quick = True
        for key, button in self.trigger_mode_quick_buttons.items():
            button.set_active(key == normalized)
        self.syncing_trigger_mode_quick = False

    def on_trigger_mode_quick_toggled(self, button: Gtk.ToggleButton, mode_key: str):
        if self.syncing_trigger_mode_quick:
            return
        if not button.get_active():
            if not any(item.get_active() for item in self.trigger_mode_quick_buttons.values()):
                self.sync_trigger_mode_quick_state(self.selected_trigger_mode())
            return

        self.sync_trigger_mode_quick_state(mode_key)
        self.trigger_mode_dropdown.set_selected(self.trigger_mode_index(mode_key))

    def on_trigger_preset_clicked(self, _button: Gtk.Button, mode_key: str, mode_value: str):
        mode = str(mode_key).strip().lower()
        value = str(mode_value).strip()
        self.trigger_mode_dropdown.set_selected(self.trigger_mode_index(mode))

        if mode == "schedule_interval":
            interval = max(5, self.parse_int(value, 300))
            self.trigger_interval_scale.set_value(interval)
            self.trigger_interval_spin.set_value(interval)
        elif mode == "webhook":
            self.trigger_webhook_entry.set_text(value or "/incoming")
        elif mode == "file_watch":
            self.trigger_watch_path_entry.set_text(value or "/tmp/watch-folder")
        elif mode == "cron":
            self.trigger_cron_entry.set_text(value or "*/15 * * * *")
        else:
            self.trigger_value_entry.set_text(value)

        self.update_trigger_controls_state()
        self.set_status(f"Trigger preset applied: {mode.replace('_', ' ')}.")

    def on_trigger_mode_changed(self, *_args):
        self.update_trigger_controls_state()

    def selected_trigger_mode(self) -> str:
        index = self.trigger_mode_dropdown.get_selected()
        if 0 <= index < len(self.TRIGGER_MODE_OPTIONS):
            return self.TRIGGER_MODE_OPTIONS[index]
        return "manual"

    def trigger_mode_index(self, value: str) -> int:
        normalized = str(value).strip().lower()
        if normalized in self.TRIGGER_MODE_OPTIONS:
            return self.TRIGGER_MODE_OPTIONS.index(normalized)
        return 0

    def update_trigger_controls_state(self):
        mode = self.selected_trigger_mode()
        self.sync_trigger_mode_quick_state(mode)

        self.trigger_interval_field_row.set_visible(mode == "schedule_interval")
        self.trigger_webhook_row.set_visible(mode == "webhook")
        self.trigger_watch_path_row.set_visible(mode == "file_watch")
        self.trigger_cron_row.set_visible(mode == "cron")
        show_generic = mode not in {"manual", "schedule_interval", "webhook", "file_watch", "cron"}
        self.trigger_value_row.set_visible(show_generic)

        if mode == "manual":
            self.trigger_hint_label.set_text(
                "Manual trigger starts the workflow when launched by a user action."
            )
        elif mode == "schedule_interval":
            self.trigger_hint_label.set_text("Runs workflow on a fixed interval.")
        elif mode == "webhook":
            self.trigger_hint_label.set_text("Starts when matching webhook payload arrives.")
        elif mode == "file_watch":
            self.trigger_hint_label.set_text("Starts when the watched file/folder changes.")
        elif mode == "cron":
            self.trigger_hint_label.set_text("Runs using cron schedule syntax.")
        else:
            self.trigger_value_entry.set_placeholder_text("Trigger value")
            self.trigger_hint_label.set_text("Set trigger value for this mode.")
        self.apply_trigger_validation_feedback()

    def build_trigger_inline_validation_issues(
        self,
        mode: str,
    ) -> list[tuple[str, str, str]]:
        issues: list[tuple[str, str, str]] = []
        normalized = str(mode).strip().lower()
        trigger_value = self.current_trigger_value()

        if normalized not in self.TRIGGER_MODE_OPTIONS:
            issues.append(
                (
                    "trigger_mode",
                    "error",
                    f"Unsupported trigger mode '{normalized or 'unknown'}'.",
                )
            )
            return issues

        if normalized == "schedule_interval":
            try:
                interval = float(trigger_value or "0")
                if interval <= 0:
                    issues.append(("trigger_interval", "error", "Interval must be greater than zero."))
            except ValueError:
                issues.append(("trigger_interval", "error", "Interval must be numeric."))
        elif normalized == "cron":
            cron_value = self.trigger_cron_entry.get_text().strip()
            if not cron_value:
                issues.append(("trigger_cron", "error", "Cron expression is required."))
            elif not self.looks_like_cron(cron_value):
                issues.append(
                    (
                        "trigger_cron",
                        "error",
                        "Cron expression should contain 5 or 6 fields.",
                    )
                )
        elif normalized == "webhook":
            webhook_path = self.trigger_webhook_entry.get_text().strip()
            if not webhook_path:
                issues.append(("trigger_webhook", "warning", "Webhook path is empty; default will be used."))
            elif not webhook_path.startswith("/"):
                issues.append(("trigger_webhook", "warning", "Webhook path should start with '/'."))
        elif normalized == "file_watch":
            watch_path = self.trigger_watch_path_entry.get_text().strip()
            if not watch_path:
                issues.append(("trigger_watch_path", "warning", "Watch path is empty; default will be used."))
        elif normalized not in {"manual"} and not trigger_value:
            issues.append(("trigger_value", "error", "Trigger value is required for this mode."))

        return issues

    def apply_trigger_validation_feedback(self) -> list[tuple[str, str, str]]:
        trigger_keys = {
            "trigger_mode",
            "trigger_interval",
            "trigger_webhook",
            "trigger_watch_path",
            "trigger_cron",
            "trigger_value",
        }
        self.clear_node_field_feedback(trigger_keys)

        if not self.trigger_section.get_visible():
            return []

        issues = self.build_trigger_inline_validation_issues(self.selected_trigger_mode())
        for field_key, severity, message in issues:
            self.set_node_field_feedback(field_key, message, severity)
        return issues

    def load_trigger_controls(self, merged_config: dict[str, str], detail_text: str):
        mode = str(merged_config.get("trigger_mode", "")).strip().lower()
        value = str(merged_config.get("trigger_value", "")).strip()

        detail = str(detail_text).strip()
        if detail.startswith("trigger:"):
            mode = detail.split(":", 1)[1].strip().lower() or mode or "manual"
        elif detail.startswith("interval:"):
            mode = "schedule_interval"
            value = detail.split(":", 1)[1].strip()
        elif detail.startswith("webhook:"):
            mode = "webhook"
            value = detail.split(":", 1)[1].strip()
        elif detail.startswith("file_watch:"):
            mode = "file_watch"
            value = detail.split(":", 1)[1].strip()
        elif detail.startswith("cron:"):
            mode = "cron"
            value = detail.split(":", 1)[1].strip()

        if not mode:
            mode = "manual"

        self.trigger_mode_dropdown.set_selected(self.trigger_mode_index(mode))
        interval_seconds = max(5, self.parse_int(value, 300))
        self.trigger_interval_scale.set_value(interval_seconds)
        self.trigger_interval_spin.set_value(interval_seconds)
        self.trigger_webhook_entry.set_text(value if mode == "webhook" else "")
        self.trigger_watch_path_entry.set_text(value if mode == "file_watch" else "")
        self.trigger_cron_entry.set_text(value if mode == "cron" else "")
        self.trigger_value_entry.set_text(value)
        self.update_trigger_controls_state()

    def current_trigger_value(self) -> str:
        mode = self.selected_trigger_mode()
        if mode == "schedule_interval":
            return str(max(5, self.trigger_interval_spin.get_value_as_int()))
        if mode == "webhook":
            return self.trigger_webhook_entry.get_text().strip()
        if mode == "file_watch":
            return self.trigger_watch_path_entry.get_text().strip()
        if mode == "cron":
            return self.trigger_cron_entry.get_text().strip()
        return self.trigger_value_entry.get_text().strip()

    def current_trigger_detail(self) -> str:
        mode = self.selected_trigger_mode()
        value = self.current_trigger_value()
        if mode == "manual":
            return "trigger:manual"
        if mode == "schedule_interval":
            return f"interval:{value or '60'}"
        if mode == "webhook":
            return f"webhook:{value or '/incoming'}"
        if mode == "file_watch":
            return f"file_watch:{value or '/tmp'}"
        if mode == "cron":
            return f"cron:{value or '*/15 * * * *'}"
        return f"trigger:{mode}"

    def update_condition_controls_state(self):
        mode = self.selected_condition_mode()
        condition_visible = bool(self.condition_mode_row.get_visible())
        needs_value = mode in {"contains", "equals", "not_contains", "regex", "raw"}
        needs_min_len = mode == "min_len"
        self.edit_condition_value_entry.set_sensitive(condition_visible and needs_value)
        self.condition_value_row.set_visible(condition_visible and needs_value)
        self.condition_min_len_field_row.set_visible(condition_visible and needs_min_len)
        self.condition_preview_input_row.set_visible(condition_visible)
        self.condition_preview_label.set_visible(condition_visible)
        self.edit_condition_min_len_scale.set_sensitive(condition_visible and needs_min_len)
        self.edit_condition_min_len_spin.set_sensitive(condition_visible and needs_min_len)

        if not needs_value:
            self.edit_condition_value_entry.set_text("")
        self.apply_condition_validation_feedback()
        self.refresh_condition_branch_preview()

    def refresh_condition_branch_preview(self):
        if not self.condition_mode_row.get_visible():
            self.condition_preview_label.set_text("")
            return

        node = self.get_selected_node()
        if not node or self.node_type_key(node.node_type) != "condition":
            self.condition_preview_label.set_text(
                "Select a condition node to preview branch routing."
            )
            return

        expression = self.current_condition_expression().strip()
        if not expression:
            self.condition_preview_label.set_text(
                "Define a condition expression to preview true/false routing."
            )
            return

        sample_input = self.condition_preview_input_entry.get_text().strip()
        try:
            result = self.execution_engine.evaluate_condition_for_test(
                expression,
                sample_input,
            )
        except Exception as error:
            self.condition_preview_label.set_text(f"Condition preview error: {error}")
            return

        outgoing = [edge for edge in self.edges if edge.source_node_id == node.id]
        target_id = self.execution_engine.choose_condition_branch_for_test(outgoing, result)
        branch_text = "TRUE" if result else "FALSE"
        if target_id:
            target_node = self.find_node(target_id)
            target_name = target_node.name if target_node else target_id
            self.condition_preview_label.set_text(
                f"Preview result: {branch_text} -> '{target_name}'."
            )
            return
        self.condition_preview_label.set_text(
            f"Preview result: {branch_text} with no outgoing branch target."
        )

    def build_condition_inline_validation_issues(
        self,
        mode: str,
        expression: str,
    ) -> list[tuple[str, str, str]]:
        issues: list[tuple[str, str, str]] = []
        normalized = str(mode).strip().lower()
        if normalized not in self.CONDITION_MODE_OPTIONS:
            issues.append(
                (
                    "condition_mode",
                    "error",
                    f"Unsupported condition mode '{normalized or 'unknown'}'.",
                )
            )
            return issues

        if normalized in {"contains", "equals", "not_contains", "regex", "raw"}:
            if not expression:
                issues.append(("condition_value", "error", "Condition value is required."))
            elif normalized == "regex":
                try:
                    re.compile(expression)
                except re.error:
                    issues.append(("condition_value", "error", "Regex pattern is invalid."))
        elif normalized == "min_len":
            min_len_value = self.edit_condition_min_len_spin.get_value_as_int()
            if min_len_value <= 0:
                issues.append(("condition_min_len", "error", "Minimum length must be greater than zero."))
        return issues

    def apply_condition_validation_feedback(self) -> list[tuple[str, str, str]]:
        condition_keys = {
            "condition_mode",
            "condition_value",
            "condition_min_len",
        }
        self.clear_node_field_feedback(condition_keys)

        if not self.condition_mode_row.get_visible():
            return []

        mode = self.selected_condition_mode()
        expression = self.edit_condition_value_entry.get_text().strip()
        issues = self.build_condition_inline_validation_issues(mode, expression)
        for field_key, severity, message in issues:
            self.set_node_field_feedback(field_key, message, severity)
        return issues

    def on_condition_min_len_scale_changed(self, scale: Gtk.Scale):
        value = int(scale.get_value())
        if self.edit_condition_min_len_spin.get_value_as_int() != value:
            self.edit_condition_min_len_spin.set_value(value)

    def on_condition_min_len_spin_changed(self, spin: Gtk.SpinButton):
        value = spin.get_value_as_int()
        if int(self.edit_condition_min_len_scale.get_value()) != value:
            self.edit_condition_min_len_scale.set_value(value)

    def selected_condition_mode(self) -> str:
        index = self.edit_condition_mode_dropdown.get_selected()
        if 0 <= index < len(self.CONDITION_MODE_OPTIONS):
            return self.CONDITION_MODE_OPTIONS[index]
        return "contains"

    def condition_mode_index(self, value: str) -> int:
        normalized = str(value).strip().lower()
        if normalized in self.CONDITION_MODE_OPTIONS:
            return self.CONDITION_MODE_OPTIONS.index(normalized)
        return 0

    def current_condition_expression(self) -> str:
        mode = self.selected_condition_mode()
        if mode in {"true", "false"}:
            return mode
        if mode == "min_len":
            return f"min_len:{self.edit_condition_min_len_spin.get_value_as_int()}"
        value = self.edit_condition_value_entry.get_text().strip()
        if mode == "raw":
            return value
        if not value:
            return ""
        return f"{mode}:{value}"

    def load_condition_controls(self, expression: str):
        expr = str(expression).strip()
        if not expr:
            self.edit_condition_mode_dropdown.set_selected(self.condition_mode_index("contains"))
            self.edit_condition_value_entry.set_text("")
            self.edit_condition_min_len_scale.set_value(120)
            self.edit_condition_min_len_spin.set_value(120)
            self.update_condition_controls_state()
            return

        lower_expr = expr.lower()
        if lower_expr in {"true", "false"}:
            self.edit_condition_mode_dropdown.set_selected(self.condition_mode_index(lower_expr))
            self.edit_condition_value_entry.set_text("")
            self.update_condition_controls_state()
            return

        if ":" in expr:
            key, value = expr.split(":", 1)
            mode = key.strip().lower()
            payload = value.strip()
            if mode in {"contains", "equals", "not_contains", "regex"}:
                self.edit_condition_mode_dropdown.set_selected(self.condition_mode_index(mode))
                self.edit_condition_value_entry.set_text(payload)
                self.update_condition_controls_state()
                return
            if mode == "min_len":
                min_len = self.parse_int(payload, 120)
                self.edit_condition_mode_dropdown.set_selected(self.condition_mode_index(mode))
                self.edit_condition_min_len_scale.set_value(float(min_len))
                self.edit_condition_min_len_spin.set_value(float(min_len))
                self.update_condition_controls_state()
                return

        self.edit_condition_mode_dropdown.set_selected(self.condition_mode_index("raw"))
        self.edit_condition_value_entry.set_text(expr)
        self.update_condition_controls_state()

    def current_inspector_temperature(self) -> str:
        if not self.edit_temp_override_switch.get_active():
            return ""
        return f"{self.edit_temp_spin.get_value():.2f}"

    def current_inspector_max_tokens(self) -> str:
        if not self.edit_tokens_override_switch.get_active():
            return ""
        return str(self.edit_tokens_spin.get_value_as_int())

    def parse_float(self, value: str, fallback: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    def parse_int(self, value: str, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    def looks_like_cron(self, value: str) -> bool:
        text = str(value).strip()
        if not text:
            return False
        parts = [item for item in text.split() if item]
        if len(parts) not in {5, 6}:
            return False
        for part in parts:
            if not re.match(r"^[\d\*/,\-\?LW#A-Za-z]+$", part):
                return False
        return True
