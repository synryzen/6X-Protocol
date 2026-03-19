import json
import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GLib

from src.models.run_record import RunRecord
from src.services.run_execution_service import get_run_execution_service
from src.services.run_store import RunStore
from src.services.workflow_store import WorkflowStore
from src.ui import build_icon_title, build_icon_section, create_icon


class RunsView(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("page-root")
        self.add_css_class("runs-root")

        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(6)
        self.set_margin_end(6)

        self.store = RunStore()
        self.workflow_store = WorkflowStore()
        self.run_execution_service = get_run_execution_service()

        self.runs = self.store.load_runs()
        self.workflows = self.workflow_store.load_workflows()
        self.workflow_dropdown: Gtk.DropDown | None = None
        self.status_filter = "all"
        self.selected_run_id: str | None = None
        self.timeline_filter = "all"
        self.suppress_global_sync = False

        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        header_box.add_css_class("page-hero")

        subtitle = Gtk.Label(
            label="Run workflows, review execution history, and retry or stop tracked runs."
        )
        subtitle.set_wrap(True)
        subtitle.set_halign(Gtk.Align.START)
        subtitle.add_css_class("dim-label")

        header_box.append(
            build_icon_title(
                "Runs",
                "document-open-recent-symbolic",
            )
        )
        header_box.append(subtitle)

        global_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        global_controls.add_css_class("canvas-toolbar-row")
        global_controls.add_css_class("compact-toolbar-row")
        global_controls.add_css_class("page-action-bar")

        self.global_search_entry = Gtk.Entry()
        self.global_search_entry.set_hexpand(True)
        self.global_search_entry.set_placeholder_text(
            "Global run search (syncs history + timeline filters)"
        )
        self.global_search_entry.connect("changed", self.on_global_search_changed)

        self.global_search_clear_button = Gtk.Button(label="Clear")
        self.global_search_clear_button.add_css_class("compact-action-button")
        self.global_search_clear_button.connect("clicked", self.on_clear_global_search)

        global_controls.append(self.global_search_entry)
        global_controls.append(self.global_search_clear_button)

        controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        controls_box.add_css_class("canvas-toolbar-row")
        controls_box.add_css_class("compact-toolbar-row")
        controls_box.add_css_class("page-action-bar")

        self.workflow_dropdown_container = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=8
        )
        self.workflow_dropdown_container.set_hexpand(True)

        run_button = Gtk.Button(label="Run Selected Workflow")
        run_button.connect("clicked", self.on_run_selected_workflow)
        run_button.add_css_class("suggested-action")
        run_button.add_css_class("compact-action-button")

        refresh_button = Gtk.Button(label="Refresh")
        refresh_button.connect("clicked", self.on_refresh_clicked)
        refresh_button.add_css_class("compact-action-button")

        controls_box.append(self.workflow_dropdown_container)
        controls_box.append(run_button)
        controls_box.append(refresh_button)

        controls_frame = Gtk.Frame()
        controls_frame.add_css_class("panel-card")
        controls_frame.add_css_class("entity-form-panel")
        controls_frame.set_child(controls_box)
        controls_frame.set_margin_bottom(4)

        section_title = build_icon_section(
            "Run History",
            "media-playlist-shuffle-symbolic",
        )

        history_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        history_controls.add_css_class("canvas-toolbar-row")
        history_controls.add_css_class("compact-toolbar-row")
        history_controls.add_css_class("page-action-bar")

        self.search_entry = Gtk.Entry()
        self.search_entry.set_hexpand(True)
        self.search_entry.set_placeholder_text("Search runs by workflow, summary, or step")
        self.search_entry.connect("changed", self.on_filters_changed)

        self.status_filter_row = self.build_status_filter_row()
        self.reset_filters_button = Gtk.Button(label="Reset")
        self.reset_filters_button.add_css_class("compact-action-button")
        self.reset_filters_button.connect("clicked", self.on_reset_filters)

        history_controls.append(self.search_entry)
        history_controls.append(self.status_filter_row)
        history_controls.append(self.reset_filters_button)

        self.status_label = Gtk.Label(label="")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.add_css_class("dim-label")
        self.status_label.add_css_class("inline-status")

        timeline_title = build_icon_section(
            "Timeline Inspector",
            "view-reveal-symbolic",
        )

        timeline_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        timeline_controls.add_css_class("canvas-toolbar-row")
        timeline_controls.add_css_class("compact-toolbar-row")
        timeline_controls.add_css_class("page-action-bar")

        self.timeline_search_entry = Gtk.Entry()
        self.timeline_search_entry.set_hexpand(True)
        self.timeline_search_entry.set_placeholder_text("Filter timeline events by node, status, or message")
        self.timeline_search_entry.connect("changed", self.on_timeline_filters_changed)

        self.timeline_filter_row = self.build_timeline_filter_row()
        self.timeline_reset_button = Gtk.Button(label="Clear")
        self.timeline_reset_button.add_css_class("compact-action-button")
        self.timeline_reset_button.connect("clicked", self.on_reset_timeline_filters)

        timeline_controls.append(self.timeline_search_entry)
        timeline_controls.append(self.timeline_filter_row)
        timeline_controls.append(self.timeline_reset_button)

        self.timeline_run_label = Gtk.Label(label="Select a run card to inspect timeline events.")
        self.timeline_run_label.set_halign(Gtk.Align.START)
        self.timeline_run_label.add_css_class("dim-label")
        self.timeline_run_label.add_css_class("inline-status")

        self.timeline_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.timeline_list_box.set_hexpand(True)
        self.timeline_events_cache: list[dict[str, str]] = []
        self.selected_timeline_event_index: int = -1

        timeline_scroll = Gtk.ScrolledWindow()
        timeline_scroll.set_hexpand(True)
        timeline_scroll.set_vexpand(False)
        timeline_scroll.set_min_content_height(180)
        timeline_scroll.set_max_content_height(240)
        timeline_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        timeline_scroll.set_child(self.timeline_list_box)

        timeline_detail_title = build_icon_section(
            "Event Details",
            "dialog-information-symbolic",
        )

        self.timeline_detail_summary = Gtk.Label(label="Select a timeline event to inspect details.")
        self.timeline_detail_summary.set_halign(Gtk.Align.START)
        self.timeline_detail_summary.set_wrap(True)
        self.timeline_detail_summary.add_css_class("dim-label")
        self.timeline_detail_summary.add_css_class("inline-status")

        self.timeline_detail_message = Gtk.Label(label="")
        self.timeline_detail_message.set_halign(Gtk.Align.START)
        self.timeline_detail_message.set_wrap(True)
        self.timeline_detail_message.add_css_class("dim-label")
        self.timeline_detail_message.add_css_class("timeline-event-row")

        self.timeline_raw_buffer = Gtk.TextBuffer()
        self.timeline_raw_view = Gtk.TextView(buffer=self.timeline_raw_buffer)
        self.timeline_raw_view.set_editable(False)
        self.timeline_raw_view.set_cursor_visible(False)
        self.timeline_raw_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.timeline_raw_view.set_size_request(-1, 96)

        raw_scroll = Gtk.ScrolledWindow()
        raw_scroll.set_hexpand(True)
        raw_scroll.set_vexpand(False)
        raw_scroll.set_min_content_height(96)
        raw_scroll.set_max_content_height(140)
        raw_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        raw_scroll.set_child(self.timeline_raw_view)

        self.timeline_context_buffer = Gtk.TextBuffer()
        self.timeline_context_view = Gtk.TextView(buffer=self.timeline_context_buffer)
        self.timeline_context_view.set_editable(False)
        self.timeline_context_view.set_cursor_visible(False)
        self.timeline_context_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.timeline_context_view.set_size_request(-1, 84)

        context_scroll = Gtk.ScrolledWindow()
        context_scroll.set_hexpand(True)
        context_scroll.set_vexpand(False)
        context_scroll.set_min_content_height(84)
        context_scroll.set_max_content_height(124)
        context_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        context_scroll.set_child(self.timeline_context_view)

        self.timeline_raw_expander = Gtk.Expander(label="Raw Event JSON")
        self.timeline_raw_expander.set_child(raw_scroll)
        self.timeline_raw_expander.set_expanded(False)

        self.timeline_context_expander = Gtk.Expander(label="Context Snapshot")
        self.timeline_context_expander.set_child(context_scroll)
        self.timeline_context_expander.set_expanded(False)

        self.empty_label = Gtk.Label(label="No runs yet. Run a workflow to create history.")
        self.empty_label.set_halign(Gtk.Align.START)
        self.empty_label.add_css_class("dim-label")
        self.empty_label.add_css_class("empty-state-label")

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        self.append(header_box)
        self.append(global_controls)
        self.append(history_controls)
        self.append(controls_frame)
        self.append(section_title)
        self.append(self.status_label)
        self.append(timeline_title)
        self.append(timeline_controls)
        self.append(self.timeline_run_label)
        self.append(timeline_scroll)
        self.append(timeline_detail_title)
        self.append(self.timeline_detail_summary)
        self.append(self.timeline_detail_message)
        self.append(self.timeline_raw_expander)
        self.append(self.timeline_context_expander)
        self.append(self.empty_label)
        self.append(self.list_box)

        self.reload_workflows()
        self.refresh_list()
        GLib.timeout_add_seconds(2, self.on_timer_refresh)

    def on_global_search_changed(self, *_args):
        if self.suppress_global_sync:
            return
        query = self.global_search_entry.get_text()
        self.suppress_global_sync = True
        try:
            self.search_entry.set_text(query)
            self.timeline_search_entry.set_text(query)
        finally:
            self.suppress_global_sync = False
        self.refresh_list()
        self.refresh_timeline_panel()

    def on_clear_global_search(self, _button):
        self.global_search_entry.set_text("")
        self.on_reset_filters(None)
        self.on_reset_timeline_filters(None)

    def on_timer_refresh(self):
        self.runs = self.store.load_runs()
        self.refresh_list()
        return True

    def rebuild_workflow_dropdown(self, labels: list[str], selected_index: int):
        if self.workflow_dropdown:
            self.workflow_dropdown_container.remove(self.workflow_dropdown)

        self.workflow_dropdown = Gtk.DropDown.new_from_strings(labels)
        self.workflow_dropdown.set_hexpand(True)
        self.workflow_dropdown.set_selected(selected_index)
        self.workflow_dropdown_container.append(self.workflow_dropdown)

    def reload_workflows(self):
        self.workflows = self.workflow_store.load_workflows()

        if not self.workflows:
            self.rebuild_workflow_dropdown(["No workflows found"], 0)
            self.workflow_dropdown.set_sensitive(False)
            return

        labels = [workflow.name for workflow in self.workflows]
        self.rebuild_workflow_dropdown(labels, 0)
        self.workflow_dropdown.set_sensitive(True)

    def on_refresh_clicked(self, _button):
        self.reload_workflows()
        self.runs = self.store.load_runs()
        self.refresh_list()
        self.status_label.set_text("Runs refreshed.")

    def build_status_filter_row(self) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.add_css_class("segmented-row")
        row.add_css_class("compact-segmented-row")

        self.status_filter_buttons: dict[str, Gtk.ToggleButton] = {}
        for key, label in [
            ("all", "All"),
            ("running", "Running"),
            ("success", "Success"),
            ("failed", "Failed"),
            ("waiting_approval", "Approval"),
            ("cancelled", "Cancelled"),
        ]:
            button = Gtk.ToggleButton(label=label)
            button.add_css_class("segmented-button")
            button.add_css_class("compact-segmented-button")
            button.connect("toggled", self.on_status_filter_toggled, key)
            row.append(button)
            self.status_filter_buttons[key] = button

        self.status_filter_buttons["all"].set_active(True)
        return row

    def build_timeline_filter_row(self) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.add_css_class("segmented-row")
        row.add_css_class("compact-segmented-row")

        self.timeline_filter_buttons: dict[str, Gtk.ToggleButton] = {}
        for key, label in [
            ("all", "All"),
            ("success", "Success"),
            ("failed", "Failed"),
            ("waiting_approval", "Approval"),
            ("cancelled", "Cancelled"),
        ]:
            button = Gtk.ToggleButton(label=label)
            button.add_css_class("segmented-button")
            button.add_css_class("compact-segmented-button")
            button.connect("toggled", self.on_timeline_filter_toggled, key)
            row.append(button)
            self.timeline_filter_buttons[key] = button

        self.timeline_filter_buttons["all"].set_active(True)
        return row

    def on_status_filter_toggled(self, button: Gtk.ToggleButton, key: str):
        if not button.get_active():
            if not any(item.get_active() for item in self.status_filter_buttons.values()):
                button.set_active(True)
            return

        for other_key, other in self.status_filter_buttons.items():
            if other_key != key and other.get_active():
                other.set_active(False)
        self.status_filter = key
        self.refresh_list()

    def on_filters_changed(self, *_args):
        self.refresh_list()

    def on_timeline_filters_changed(self, *_args):
        self.refresh_timeline_panel()

    def on_reset_filters(self, _button):
        self.search_entry.set_text("")
        self.status_filter_buttons["all"].set_active(True)
        self.refresh_list()

    def on_timeline_filter_toggled(self, button: Gtk.ToggleButton, key: str):
        if not button.get_active():
            if not any(item.get_active() for item in self.timeline_filter_buttons.values()):
                button.set_active(True)
            return

        for other_key, other in self.timeline_filter_buttons.items():
            if other_key != key and other.get_active():
                other.set_active(False)
        self.timeline_filter = key
        self.refresh_timeline_panel()

    def on_reset_timeline_filters(self, _button):
        self.timeline_search_entry.set_text("")
        self.timeline_filter_buttons["all"].set_active(True)
        self.selected_timeline_event_index = -1
        self.refresh_timeline_panel()

    def get_selected_workflow(self):
        if not self.workflow_dropdown:
            return None

        index = self.workflow_dropdown.get_selected()
        if index < 0 or index >= len(self.workflows):
            return None

        return self.workflows[index]

    def on_run_selected_workflow(self, _button):
        workflow = self.get_selected_workflow()
        if not workflow:
            self.status_label.set_text("Select a valid workflow first.")
            return

        run = self.run_execution_service.start_workflow_run(workflow)
        self.runs = self.store.load_runs()
        self.refresh_list()
        self.status_label.set_text(
            f"Workflow '{workflow.name}' started as {run.status.upper()}."
        )

    def on_delete_run(self, _button, run_id):
        self.runs = [run for run in self.runs if run.id != run_id]
        self.store.save_runs(self.runs)
        self.refresh_list()
        self.status_label.set_text("Run deleted.")

    def on_stop_run(self, _button, run_id):
        ok, message = self.run_execution_service.request_stop(run_id)
        self.runs = self.store.load_runs()
        self.refresh_list()
        self.status_label.set_text(message if ok else f"Stop failed: {message}")

    def on_retry_run(self, _button, run_id):
        target = self.store.get_run_by_id(run_id)
        if not target:
            self.status_label.set_text("Run not found.")
            return

        if not target.workflow_id:
            self.status_label.set_text("Cannot retry this run because no workflow ID was stored.")
            return

        workflow = self.workflow_store.get_workflow_by_id(target.workflow_id)
        if not workflow:
            self.status_label.set_text("Original workflow no longer exists.")
            return

        retried_run = self.run_execution_service.start_workflow_run(workflow)
        self.runs = self.store.load_runs()
        self.refresh_list()
        self.status_label.set_text(
            f"Full retry started for '{workflow.name}' as {retried_run.status.upper()}."
        )

    def on_retry_failed_node(self, _button, run_id):
        ok, message, _run = self.run_execution_service.retry_from_failed_node(run_id)
        self.runs = self.store.load_runs()
        self.refresh_list()
        self.status_label.set_text(message if ok else f"Retry failed: {message}")

    def on_approve_run(self, _button, run_id):
        ok, message, _run = self.run_execution_service.approve_and_resume(run_id)
        self.runs = self.store.load_runs()
        self.refresh_list()
        self.status_label.set_text(message if ok else f"Approve failed: {message}")

    def on_inspect_timeline(self, _button, run_id):
        self.selected_run_id = run_id
        self.selected_timeline_event_index = -1
        self.refresh_timeline_panel()

    def filtered_runs(self) -> list[RunRecord]:
        query = self.search_entry.get_text().strip().lower()
        filtered: list[RunRecord] = []

        for run in self.runs:
            status = run.status.strip().lower()
            if self.status_filter != "all" and status != self.status_filter:
                continue

            if query:
                haystack = (
                    f"{run.workflow_name} {run.summary} "
                    f"{' '.join(run.steps)} "
                    f"{' '.join(item.get('message', '') for item in run.timeline)} "
                    f"{run.started_at} {run.finished_at}"
                ).strip().lower()
                if query not in haystack:
                    continue

            filtered.append(run)
        return filtered

    def refresh_list(self):
        if not hasattr(self, "list_box"):
            return
        child = self.list_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.list_box.remove(child)
            child = next_child

        run_ids = {run.id for run in self.runs}
        if self.selected_run_id and self.selected_run_id not in run_ids:
            self.selected_run_id = None
        if not self.selected_run_id and self.runs:
            self.selected_run_id = self.runs[0].id

        visible_runs = self.filtered_runs()
        has_runs = len(visible_runs) > 0
        self.empty_label.set_visible(not has_runs)

        for run in visible_runs:
            self.list_box.append(self.build_run_card(run))
        self.refresh_timeline_panel()

    def build_run_card(self, run: RunRecord) -> Gtk.Frame:
        frame = Gtk.Frame()
        frame.add_css_class("list-card")
        frame.add_css_class("entity-card")
        frame.add_css_class("run-card")
        tone_class = self.run_tone_class(run.status)
        frame.add_css_class(tone_class)
        if self.selected_run_id == run.id:
            frame.add_css_class("run-card-selected")

        outer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer_box.set_margin_top(8)
        outer_box.set_margin_bottom(8)
        outer_box.set_margin_start(8)
        outer_box.set_margin_end(8)

        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title_row.add_css_class("compact-action-row")
        title_row.add_css_class("entity-card-title-row")
        title_row.add_css_class("run-title-row")
        title_row.add_css_class(f"{tone_class}-title")

        workflow_label = Gtk.Label(label=run.workflow_name or "Unnamed Workflow")
        workflow_label.add_css_class("title-3")
        workflow_label.set_halign(Gtk.Align.START)
        workflow_label.set_hexpand(True)

        status_badge = Gtk.Label(label=run.status.upper())
        status_badge.add_css_class("heading")
        status_badge.add_css_class("status-chip")
        status_badge.add_css_class(self.status_chip_class(run.status))
        status_badge.set_halign(Gtk.Align.END)

        status_icon = create_icon(
            self.status_icon_name(run.status),
            css_class="status-icon",
        )

        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        status_box.add_css_class("status-box")
        status_box.append(status_icon)
        status_box.append(status_badge)

        retry_button = Gtk.Button(label="Retry Full")
        retry_button.set_sensitive(bool(run.workflow_id) and run.status != "running")
        retry_button.connect("clicked", self.on_retry_run, run.id)
        retry_button.add_css_class("compact-action-button")

        retry_failed_button = Gtk.Button(label="Retry Failed Node")
        show_retry_failed = (
            bool(run.workflow_id)
            and run.status == "failed"
            and bool(run.last_failed_node_id)
        )
        retry_failed_button.set_sensitive(show_retry_failed)
        retry_failed_button.set_visible(show_retry_failed)
        retry_failed_button.connect("clicked", self.on_retry_failed_node, run.id)
        retry_failed_button.add_css_class("compact-action-button")

        approve_button = Gtk.Button(label="Approve + Resume")
        show_approve = (
            bool(run.workflow_id)
            and run.status == "waiting_approval"
            and bool(run.pending_approval_node_id)
        )
        approve_button.set_sensitive(show_approve)
        approve_button.set_visible(show_approve)
        approve_button.connect("clicked", self.on_approve_run, run.id)
        approve_button.add_css_class("compact-action-button")

        stop_button = Gtk.Button(label="Stop")
        show_stop = run.status == "running"
        stop_button.set_sensitive(show_stop)
        stop_button.set_visible(show_stop)
        stop_button.connect("clicked", self.on_stop_run, run.id)
        stop_button.add_css_class("compact-action-button")

        delete_button = Gtk.Button(label="Delete")
        delete_button.set_sensitive(run.status != "running")
        delete_button.connect("clicked", self.on_delete_run, run.id)
        delete_button.add_css_class("compact-action-button")

        inspect_button = Gtk.Button(label="Inspect")
        inspect_button.add_css_class("compact-action-button")
        inspect_button.connect("clicked", self.on_inspect_timeline, run.id)

        title_row.append(workflow_label)
        title_row.append(status_box)
        title_row.append(inspect_button)
        title_row.append(retry_button)
        title_row.append(retry_failed_button)
        title_row.append(approve_button)
        title_row.append(stop_button)
        title_row.append(delete_button)

        chip_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        chip_row.set_halign(Gtk.Align.START)
        chip_row.add_css_class("run-chip-row")

        id_chip = Gtk.Label(label=f"Run {run.id[:8] if run.id else 'unknown'}")
        id_chip.add_css_class("status-chip")
        id_chip.add_css_class("run-meta-chip")
        id_chip.add_css_class("run-chip-neutral")

        steps_chip = Gtk.Label(label=f"Steps {len(run.steps)}")
        steps_chip.add_css_class("status-chip")
        steps_chip.add_css_class("run-meta-chip")
        steps_chip.add_css_class("run-chip-steps")

        timeline_label = "Finished" if run.finished_at else "In Progress"
        timeline_chip = Gtk.Label(label=timeline_label)
        timeline_chip.add_css_class("status-chip")
        timeline_chip.add_css_class("run-meta-chip")
        timeline_chip.add_css_class("run-chip-finished" if run.finished_at else "run-chip-running")

        chip_row.append(id_chip)
        chip_row.append(steps_chip)
        chip_row.append(timeline_chip)

        if run.attempt > 1:
            attempt_chip = Gtk.Label(label=f"Attempt {run.attempt}")
            attempt_chip.add_css_class("status-chip")
            attempt_chip.add_css_class("run-meta-chip")
            attempt_chip.add_css_class("run-chip-running")
            chip_row.append(attempt_chip)
        if run.replay_of_run_id:
            replay_chip = Gtk.Label(label=f"Replay of {run.replay_of_run_id[:8]}")
            replay_chip.add_css_class("status-chip")
            replay_chip.add_css_class("run-meta-chip")
            replay_chip.add_css_class("run-chip-neutral")
            chip_row.append(replay_chip)
        if run.pending_approval_node_name:
            approval_chip = Gtk.Label(label=f"Awaiting {run.pending_approval_node_name}")
            approval_chip.add_css_class("status-chip")
            approval_chip.add_css_class("run-meta-chip")
            approval_chip.add_css_class("status-waiting")
            chip_row.append(approval_chip)

        meta_grid = Gtk.Grid()
        meta_grid.set_column_spacing(12)
        meta_grid.set_row_spacing(10)

        started_title = Gtk.Label(label="Started At")
        started_title.add_css_class("heading")
        started_title.set_halign(Gtk.Align.START)

        started_value = Gtk.Label(label=run.started_at)
        started_value.set_halign(Gtk.Align.START)
        started_value.add_css_class("dim-label")

        finished_title = Gtk.Label(label="Finished At")
        finished_title.add_css_class("heading")
        finished_title.set_halign(Gtk.Align.START)

        finished_value = Gtk.Label(label=run.finished_at or "—")
        finished_value.set_halign(Gtk.Align.START)
        finished_value.add_css_class("dim-label")

        summary_title = Gtk.Label(label="Summary")
        summary_title.add_css_class("heading")
        summary_title.set_halign(Gtk.Align.START)

        summary_value = Gtk.Label(label=run.summary)
        summary_value.set_halign(Gtk.Align.START)
        summary_value.set_wrap(True)
        summary_value.add_css_class("dim-label")

        steps_title = Gtk.Label(label="Steps")
        steps_title.add_css_class("heading")
        steps_title.set_halign(Gtk.Align.START)

        steps_text = "\n".join([f"• {step}" for step in run.steps]) if run.steps else "• No steps recorded"
        steps_value = Gtk.Label(label=steps_text)
        steps_value.set_halign(Gtk.Align.START)
        steps_value.set_wrap(True)
        steps_value.add_css_class("dim-label")

        timeline_title = Gtk.Label(label="Timeline")
        timeline_title.add_css_class("heading")
        timeline_title.set_halign(Gtk.Align.START)

        timeline_text = self.format_timeline(run)
        timeline_value = Gtk.Label(label=timeline_text)
        timeline_value.set_halign(Gtk.Align.START)
        timeline_value.set_wrap(True)
        timeline_value.add_css_class("dim-label")

        meta_grid.attach(started_title, 0, 0, 1, 1)
        meta_grid.attach(started_value, 0, 1, 1, 1)
        meta_grid.attach(finished_title, 1, 0, 1, 1)
        meta_grid.attach(finished_value, 1, 1, 1, 1)
        meta_grid.attach(summary_title, 0, 2, 1, 1)
        meta_grid.attach(summary_value, 0, 3, 2, 1)
        meta_grid.attach(steps_title, 0, 4, 1, 1)
        meta_grid.attach(steps_value, 0, 5, 2, 1)
        meta_grid.attach(timeline_title, 0, 6, 1, 1)
        meta_grid.attach(timeline_value, 0, 7, 2, 1)

        outer_box.append(title_row)
        outer_box.append(chip_row)
        outer_box.append(meta_grid)

        frame.set_child(outer_box)
        return frame

    def run_tone_class(self, status: str) -> str:
        normalized = str(status).strip().lower()
        mapping = {
            "success": "run-tone-success",
            "completed": "run-tone-success",
            "finished": "run-tone-success",
            "failed": "run-tone-failed",
            "error": "run-tone-failed",
            "running": "run-tone-running",
            "queued": "run-tone-running",
            "waiting_approval": "run-tone-waiting",
            "cancelled": "run-tone-cancelled",
            "stopped": "run-tone-cancelled",
        }
        return mapping.get(normalized, "run-tone-default")

    def refresh_timeline_panel(self):
        if not hasattr(self, "timeline_list_box"):
            return
        child = self.timeline_list_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.timeline_list_box.remove(child)
            child = next_child

        selected = None
        if self.selected_run_id:
            selected = next((run for run in self.runs if run.id == self.selected_run_id), None)
        if not selected and self.runs:
            selected = self.runs[0]
            self.selected_run_id = selected.id

        if not selected:
            self.timeline_run_label.set_text("Select a run card to inspect timeline events.")
            self.timeline_events_cache = []
            self.selected_timeline_event_index = -1
            self.update_timeline_detail_panel(None)
            empty = Gtk.Label(label="No runs available.")
            empty.set_halign(Gtk.Align.START)
            empty.add_css_class("dim-label")
            empty.add_css_class("empty-state-label")
            self.timeline_list_box.append(empty)
            return

        self.timeline_run_label.set_text(
            f"Timeline for '{selected.workflow_name}' • Run {selected.id[:8]}"
        )
        events = self.filtered_timeline_events(selected)
        self.timeline_events_cache = events
        if not events:
            self.selected_timeline_event_index = -1
            self.update_timeline_detail_panel(None)
            empty = Gtk.Label(label="No timeline events matched the current filters.")
            empty.set_halign(Gtk.Align.START)
            empty.add_css_class("dim-label")
            empty.add_css_class("empty-state-label")
            self.timeline_list_box.append(empty)
            return

        visible_events = events[-24:]
        offset = max(0, len(events) - len(visible_events))
        if self.selected_timeline_event_index < offset or self.selected_timeline_event_index >= len(events):
            self.selected_timeline_event_index = len(events) - 1

        for index, item in enumerate(visible_events, start=offset):
            event_text = self.timeline_event_text(item)
            row_button = Gtk.Button(label=event_text)
            row_button.set_halign(Gtk.Align.FILL)
            row_button.set_hexpand(True)
            row_button.add_css_class("compact-action-button")
            row_button.add_css_class("timeline-event-button")
            if index == self.selected_timeline_event_index:
                row_button.add_css_class("timeline-event-selected")
            row_button.connect("clicked", self.on_timeline_event_selected, index)
            self.timeline_list_box.append(row_button)

        selected_event = (
            events[self.selected_timeline_event_index]
            if 0 <= self.selected_timeline_event_index < len(events)
            else None
        )
        self.update_timeline_detail_panel(selected_event)

    def filtered_timeline_events(self, run: RunRecord) -> list[dict[str, str]]:
        query = self.timeline_search_entry.get_text().strip().lower()
        events = run.timeline if run.timeline else []
        filtered: list[dict[str, str]] = []

        for event in events:
            status = str(event.get("status", "")).strip().lower()
            if self.timeline_filter != "all" and status != self.timeline_filter:
                continue

            if query:
                haystack = (
                    f"{event.get('timestamp', '')} {event.get('node_name', '')} "
                    f"{event.get('status', '')} {event.get('message', '')}"
                ).strip().lower()
                if query not in haystack:
                    continue
            filtered.append(event)
        return filtered

    def timeline_event_text(self, item: dict[str, str]) -> str:
        timestamp = item.get("timestamp", "").strip() or "—"
        node_name = item.get("node_name", "").strip() or item.get("node_id", "").strip() or "Workflow"
        status = item.get("status", "").strip().upper() or "EVENT"
        message = item.get("message", "").strip() or "No details."
        if len(message) > 120:
            message = f"{message[:117]}..."
        attempt = item.get("attempt", "").strip()
        duration = item.get("duration_ms", "").strip()
        extra = []
        if attempt:
            extra.append(f"attempt {attempt}")
        if duration:
            extra.append(f"{duration}ms")
        extra_text = f" ({', '.join(extra)})" if extra else ""
        return f"[{timestamp}] {status} • {node_name}{extra_text} • {message}"

    def on_timeline_event_selected(self, _button, event_index: int):
        self.selected_timeline_event_index = event_index
        selected = (
            self.timeline_events_cache[event_index]
            if 0 <= event_index < len(self.timeline_events_cache)
            else None
        )
        self.update_timeline_detail_panel(selected)
        self.refresh_timeline_panel()

    def update_timeline_detail_panel(self, item: dict[str, str] | None):
        if not item:
            self.timeline_detail_summary.set_text("Select a timeline event to inspect details.")
            self.timeline_detail_message.set_text("")
            self.timeline_raw_buffer.set_text("")
            self.timeline_context_buffer.set_text("")
            self.timeline_raw_expander.set_expanded(False)
            self.timeline_context_expander.set_expanded(False)
            return

        timestamp = item.get("timestamp", "").strip() or "—"
        node_name = item.get("node_name", "").strip() or item.get("node_id", "").strip() or "Workflow"
        status = item.get("status", "").strip().upper() or "EVENT"
        attempt = item.get("attempt", "").strip() or "1"
        duration = item.get("duration_ms", "").strip() or "0"

        self.timeline_detail_summary.set_text(
            f"[{timestamp}] {status} • {node_name} • attempt {attempt} • {duration}ms"
        )
        self.timeline_detail_message.set_text(item.get("message", "").strip() or "No details.")
        self.timeline_raw_buffer.set_text(json.dumps(item, indent=2, ensure_ascii=True))

        context_snapshot = item.get("context_snapshot", "").strip()
        output_preview = item.get("output_preview", "").strip()
        context_parts = []
        if output_preview:
            context_parts.append(f"Output Preview:\n{output_preview}")
        if context_snapshot:
            context_parts.append(f"Context Snapshot:\n{context_snapshot}")
        self.timeline_context_buffer.set_text(
            "\n\n".join(context_parts) if context_parts else "No context snapshot recorded."
        )
        self.timeline_context_expander.set_expanded(bool(context_parts))

    def status_icon_name(self, status: str) -> str:
        normalized = status.strip().lower()
        if normalized == "success":
            return "emblem-ok-symbolic"
        if normalized == "running":
            return "media-playback-start-symbolic"
        if normalized == "waiting_approval":
            return "dialog-warning-symbolic"
        if normalized == "cancelled":
            return "process-stop-symbolic"
        return "dialog-error-symbolic"

    def status_chip_class(self, status: str) -> str:
        normalized = status.strip().lower()
        if normalized == "success":
            return "status-success"
        if normalized == "running":
            return "status-running"
        if normalized == "waiting_approval":
            return "status-waiting"
        if normalized == "cancelled":
            return "status-cancelled"
        return "status-failed"

    def format_timeline(self, run: RunRecord) -> str:
        if not run.timeline:
            return "• No timeline events recorded"

        preview_events = run.timeline[-8:]
        lines = []
        for item in preview_events:
            timestamp = item.get("timestamp", "").strip() or "—"
            node_name = item.get("node_name", "").strip() or item.get("node_id", "").strip() or "Workflow"
            status = item.get("status", "").strip().upper() or "EVENT"
            message = item.get("message", "").strip() or "No details."
            lines.append(f"• [{timestamp}] {status} • {node_name} • {message}")
        return "\n".join(lines)
