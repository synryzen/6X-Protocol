import gi
import uuid

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

from src.models.workflow import Workflow
from src.services.run_execution_service import get_run_execution_service
from src.services.workflow_store import WorkflowStore
from src.ui import build_icon_title, build_icon_section


class WorkflowsView(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("page-root")
        self.add_css_class("workflows-root")

        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(6)
        self.set_margin_end(6)

        self.store = WorkflowStore()
        self.run_execution_service = get_run_execution_service()
        self.workflows = self.store.load_workflows()
        self.graph_filter = "all"
        self.workflow_presets: list[dict[str, str]] = [
            {
                "label": "Slack Alert Workflow",
                "name": "Slack Alert",
                "trigger": "interval:300",
                "action": "Post update to Slack webhook",
            },
            {
                "label": "HTTP Sync Workflow",
                "name": "HTTP Sync",
                "trigger": "webhook:incoming",
                "action": "Forward payload with HTTP request",
            },
            {
                "label": "AI Review Workflow",
                "name": "AI Review",
                "trigger": "interval:900",
                "action": "Run local AI review and summary",
            },
        ]

        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        header_box.add_css_class("page-hero")

        subtitle = Gtk.Label(
            label="Create and manage reusable workflow definitions for your automation system."
        )
        subtitle.set_wrap(True)
        subtitle.set_halign(Gtk.Align.START)
        subtitle.add_css_class("dim-label")

        header_box.append(
            build_icon_title(
                "Workflows",
                "network-workgroup-symbolic",
            )
        )
        header_box.append(subtitle)

        self.name_entry = Gtk.Entry()
        self.name_entry.set_placeholder_text("Workflow name")

        self.trigger_entry = Gtk.Entry()
        self.trigger_entry.set_placeholder_text("Trigger  •  Example: Schedule, Webhook, Folder Watcher")

        self.action_entry = Gtk.Entry()
        self.action_entry.set_placeholder_text("Action  •  Example: Run Script, Send Request, Notify User")

        add_button = Gtk.Button(label="Add Workflow")
        add_button.connect("clicked", self.on_add_workflow)
        add_button.set_halign(Gtk.Align.START)
        add_button.add_css_class("suggested-action")
        add_button.add_css_class("compact-action-button")

        clear_form_button = Gtk.Button(label="Clear Form")
        clear_form_button.connect("clicked", self.on_clear_form)
        clear_form_button.add_css_class("compact-action-button")

        form_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        form_box.set_margin_top(6)
        form_box.set_margin_bottom(6)
        form_box.set_margin_start(6)
        form_box.set_margin_end(6)

        form_title = Gtk.Label(label="New Workflow")
        form_title.add_css_class("title-3")
        form_title.set_halign(Gtk.Align.START)

        form_description = Gtk.Label(
            label="Define the basic structure of a workflow. We will add advanced editing later."
        )
        form_description.set_wrap(True)
        form_description.set_halign(Gtk.Align.START)
        form_description.add_css_class("dim-label")

        self.workflow_preset_dropdown = Gtk.DropDown.new_from_strings(
            [item["label"] for item in self.workflow_presets]
        )
        self.workflow_preset_dropdown.set_hexpand(True)

        apply_preset_button = Gtk.Button(label="Apply Preset")
        apply_preset_button.add_css_class("compact-action-button")
        apply_preset_button.connect("clicked", self.on_apply_workflow_preset)

        preset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        preset_row.add_css_class("canvas-toolbar-row")
        preset_row.add_css_class("compact-toolbar-row")
        preset_row.add_css_class("page-action-bar")
        preset_row.append(self.workflow_preset_dropdown)
        preset_row.append(apply_preset_button)

        form_box.append(form_title)
        form_box.append(form_description)
        form_box.append(preset_row)
        form_box.append(self.name_entry)
        form_box.append(self.trigger_entry)
        form_box.append(self.action_entry)
        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        action_row.add_css_class("entity-action-row")
        action_row.add_css_class("compact-action-row")
        action_row.append(add_button)
        action_row.append(clear_form_button)
        form_box.append(action_row)

        form_frame = Gtk.Frame()
        form_frame.add_css_class("panel-card")
        form_frame.add_css_class("entity-form-panel")
        form_frame.set_child(form_box)

        section_title = build_icon_section(
            "Saved Workflows",
            "view-list-symbolic",
        )

        self.empty_label = Gtk.Label(
            label="No workflows yet. Create your first workflow above."
        )
        self.empty_label.set_halign(Gtk.Align.START)
        self.empty_label.add_css_class("dim-label")
        self.empty_label.add_css_class("empty-state-label")

        self.status_label = Gtk.Label(label="")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.add_css_class("dim-label")
        self.status_label.add_css_class("inline-status")

        list_controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        list_controls.add_css_class("canvas-toolbar-row")
        list_controls.add_css_class("compact-toolbar-row")
        list_controls.add_css_class("page-action-bar")

        self.search_entry = Gtk.Entry()
        self.search_entry.set_hexpand(True)
        self.search_entry.set_placeholder_text("Search workflows by name, trigger, or action")
        self.search_entry.connect("changed", self.on_filter_changed)

        self.graph_filter_row = self.build_graph_filter_row()
        self.reset_filters_button = Gtk.Button(label="Reset")
        self.reset_filters_button.add_css_class("compact-action-button")
        self.reset_filters_button.connect("clicked", self.on_reset_filters)
        list_controls.append(self.search_entry)
        list_controls.append(self.graph_filter_row)
        list_controls.append(self.reset_filters_button)

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        self.append(header_box)
        self.append(list_controls)
        self.append(form_frame)
        self.append(section_title)
        self.append(self.empty_label)
        self.append(self.status_label)
        self.append(self.list_box)

        self.refresh_list()

    def on_apply_workflow_preset(self, _button):
        index = self.workflow_preset_dropdown.get_selected()
        if index < 0 or index >= len(self.workflow_presets):
            self.status_label.set_text("Select a preset first.")
            return
        preset = self.workflow_presets[index]
        self.name_entry.set_text(preset.get("name", ""))
        self.trigger_entry.set_text(preset.get("trigger", ""))
        self.action_entry.set_text(preset.get("action", ""))
        self.status_label.set_text(f"Preset loaded: {preset.get('label', 'Workflow Preset')}.")

    def on_add_workflow(self, button):
        name = self.name_entry.get_text().strip()
        trigger = self.trigger_entry.get_text().strip()
        action = self.action_entry.get_text().strip()

        if not name or not trigger or not action:
            self.status_label.set_text("Name, trigger, and action are required.")
            return

        workflow = Workflow(
            id=str(uuid.uuid4()),
            name=name,
            trigger=trigger,
            action=action,
        )

        self.workflows.append(workflow)
        self.store.save_workflows(self.workflows)

        self.clear_form_fields()
        self.status_label.set_text(f"Workflow '{workflow.name}' created.")

        self.refresh_list()

    def on_clear_form(self, _button):
        self.clear_form_fields()
        self.status_label.set_text("Workflow form cleared.")

    def clear_form_fields(self):
        self.name_entry.set_text("")
        self.trigger_entry.set_text("")
        self.action_entry.set_text("")

    def on_delete_workflow(self, button, workflow_id):
        self.workflows = [workflow for workflow in self.workflows if workflow.id != workflow_id]
        self.store.save_workflows(self.workflows)
        self.status_label.set_text("Workflow deleted.")
        self.refresh_list()

    def on_run_workflow(self, button, workflow_id):
        workflow = next(
            (item for item in self.workflows if item.id == workflow_id),
            None,
        )
        if not workflow:
            self.status_label.set_text("Workflow not found.")
            return

        run = self.run_execution_service.start_workflow_run(workflow)
        self.status_label.set_text(
            f"Run started for '{workflow.name}' with status {run.status.upper()}."
        )
        self.refresh_list()

    def build_graph_filter_row(self) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.add_css_class("segmented-row")
        row.add_css_class("compact-segmented-row")

        self.graph_filter_buttons: dict[str, Gtk.ToggleButton] = {}
        for key, label in [
            ("all", "All"),
            ("graph", "Graph"),
            ("empty", "Empty"),
        ]:
            button = Gtk.ToggleButton(label=label)
            button.add_css_class("segmented-button")
            button.add_css_class("compact-segmented-button")
            button.connect("toggled", self.on_graph_filter_toggled, key)
            row.append(button)
            self.graph_filter_buttons[key] = button

        self.graph_filter_buttons["all"].set_active(True)
        return row

    def on_graph_filter_toggled(self, button: Gtk.ToggleButton, key: str):
        if not button.get_active():
            if not any(item.get_active() for item in self.graph_filter_buttons.values()):
                button.set_active(True)
            return

        for other_key, other in self.graph_filter_buttons.items():
            if other_key != key and other.get_active():
                other.set_active(False)
        self.graph_filter = key
        self.refresh_list()

    def on_filter_changed(self, *_args):
        self.refresh_list()

    def on_reset_filters(self, _button):
        self.search_entry.set_text("")
        self.graph_filter_buttons["all"].set_active(True)
        self.refresh_list()

    def filtered_workflows(self) -> list[Workflow]:
        query = self.search_entry.get_text().strip().lower()
        filtered: list[Workflow] = []
        for workflow in self.workflows:
            graph = workflow.normalized_graph()
            node_count = len(graph.get("nodes", []))
            if self.graph_filter == "graph" and node_count == 0:
                continue
            if self.graph_filter == "empty" and node_count > 0:
                continue

            if query:
                haystack = (
                    f"{workflow.name} {workflow.trigger} {workflow.action}"
                ).strip().lower()
                if query not in haystack:
                    continue
            filtered.append(workflow)
        return filtered

    def refresh_list(self):
        if not hasattr(self, "list_box"):
            return
        child = self.list_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.list_box.remove(child)
            child = next_child

        visible_workflows = self.filtered_workflows()
        has_workflows = len(visible_workflows) > 0
        self.empty_label.set_visible(not has_workflows)

        for workflow in visible_workflows:
            self.list_box.append(self.build_workflow_card(workflow))

    def build_workflow_card(self, workflow: Workflow) -> Gtk.Frame:
        graph = workflow.normalized_graph()
        node_count = len(graph.get("nodes", []))
        edge_count = len(graph.get("edges", []))

        frame = Gtk.Frame()
        frame.add_css_class("list-card")
        frame.add_css_class("entity-card")
        frame.add_css_class("workflow-card")
        tone_class = self.workflow_tone_class(workflow.trigger, workflow.action, node_count)
        frame.add_css_class(tone_class)

        outer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer_box.set_margin_top(8)
        outer_box.set_margin_bottom(8)
        outer_box.set_margin_start(8)
        outer_box.set_margin_end(8)

        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        title_row.add_css_class("entity-action-row")
        title_row.add_css_class("compact-action-row")
        title_row.add_css_class("entity-card-title-row")
        title_row.add_css_class("workflow-title-row")
        title_row.add_css_class(f"{tone_class}-title")

        name_label = Gtk.Label(label=workflow.name)
        name_label.add_css_class("title-3")
        name_label.set_halign(Gtk.Align.START)
        name_label.set_hexpand(True)

        run_button = Gtk.Button(label="Run")
        run_button.connect("clicked", self.on_run_workflow, workflow.id)
        run_button.add_css_class("suggested-action")
        run_button.add_css_class("compact-action-button")

        delete_button = Gtk.Button(label="Delete")
        delete_button.connect("clicked", self.on_delete_workflow, workflow.id)
        delete_button.add_css_class("compact-action-button")

        title_row.append(name_label)
        title_row.append(run_button)
        title_row.append(delete_button)

        chip_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        chip_row.set_halign(Gtk.Align.START)
        chip_row.add_css_class("workflow-chip-row")

        trigger_chip = Gtk.Label(label=f"Trigger • {workflow.trigger}")
        trigger_chip.add_css_class("status-chip")
        trigger_chip.add_css_class("workflow-meta-chip")
        trigger_chip.add_css_class("workflow-chip-trigger")

        action_chip = Gtk.Label(label=f"Action • {workflow.action}")
        action_chip.add_css_class("status-chip")
        action_chip.add_css_class("workflow-meta-chip")
        action_chip.add_css_class("workflow-chip-action")

        nodes_chip = Gtk.Label(label=f"Nodes {node_count}")
        nodes_chip.add_css_class("status-chip")
        nodes_chip.add_css_class("workflow-meta-chip")
        nodes_chip.add_css_class("workflow-chip-nodes")

        links_chip = Gtk.Label(label=f"Links {edge_count}")
        links_chip.add_css_class("status-chip")
        links_chip.add_css_class("workflow-meta-chip")
        links_chip.add_css_class("workflow-chip-links")

        meta_grid = Gtk.Grid()
        meta_grid.set_column_spacing(12)
        meta_grid.set_row_spacing(10)

        trigger_title = Gtk.Label(label="Trigger")
        trigger_title.add_css_class("heading")
        trigger_title.set_halign(Gtk.Align.START)

        trigger_value = Gtk.Label(label=workflow.trigger)
        trigger_value.set_halign(Gtk.Align.START)
        trigger_value.set_wrap(True)
        trigger_value.add_css_class("dim-label")

        action_title = Gtk.Label(label="Action")
        action_title.add_css_class("heading")
        action_title.set_halign(Gtk.Align.START)

        action_value = Gtk.Label(label=workflow.action)
        action_value.set_halign(Gtk.Align.START)
        action_value.set_wrap(True)
        action_value.add_css_class("dim-label")

        graph_title = Gtk.Label(label="Graph")
        graph_title.add_css_class("heading")
        graph_title.set_halign(Gtk.Align.START)

        graph_value = Gtk.Label(
            label=f"{node_count} node(s), {edge_count} link(s)"
        )
        graph_value.set_halign(Gtk.Align.START)
        graph_value.set_wrap(True)
        graph_value.add_css_class("dim-label")

        graph_chip = Gtk.Label(
            label="Graph Ready" if node_count > 0 else "Graph Empty"
        )
        graph_chip.add_css_class("status-chip")
        graph_chip.add_css_class("workflow-meta-chip")
        graph_chip.add_css_class("workflow-chip-ready" if node_count > 0 else "workflow-chip-empty")

        chip_row.append(trigger_chip)
        chip_row.append(action_chip)
        chip_row.append(nodes_chip)
        chip_row.append(links_chip)
        chip_row.append(graph_chip)

        meta_grid.attach(trigger_title, 0, 0, 1, 1)
        meta_grid.attach(trigger_value, 0, 1, 1, 1)
        meta_grid.attach(action_title, 1, 0, 1, 1)
        meta_grid.attach(action_value, 1, 1, 1, 1)
        meta_grid.attach(graph_title, 2, 0, 1, 1)
        meta_grid.attach(graph_value, 2, 1, 1, 1)

        outer_box.append(title_row)
        outer_box.append(chip_row)
        outer_box.append(meta_grid)

        frame.set_child(outer_box)
        return frame

    def workflow_tone_class(self, trigger: str, action: str, node_count: int) -> str:
        if node_count <= 0:
            return "workflow-tone-empty"

        trigger_text = str(trigger).strip().lower()
        action_text = str(action).strip().lower()

        if any(token in action_text for token in ["ai", "model", "llm", "bot"]):
            return "workflow-tone-ai"
        if "webhook" in trigger_text:
            return "workflow-tone-webhook"
        if any(token in trigger_text for token in ["schedule", "interval", "cron"]):
            return "workflow-tone-schedule"
        if "manual" in trigger_text:
            return "workflow-tone-manual"
        return "workflow-tone-default"
