import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk

from src.services.template_marketplace_service import TemplateMarketplaceService
from src.ui import build_icon_title, build_icon_section, wrap_horizontal_row


class MarketplaceView(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add_css_class("page-root")
        self.add_css_class("marketplace-root")

        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(6)
        self.set_margin_end(6)

        self.marketplace = TemplateMarketplaceService()
        self.template_type_options: list[str] = []
        self.loading_type_filter = False

        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        header_box.add_css_class("page-hero")

        subtitle = Gtk.Label(
            label="Install local template packs and reuse ready-made nodes for workflows."
        )
        subtitle.set_wrap(True)
        subtitle.set_halign(Gtk.Align.START)
        subtitle.add_css_class("dim-label")

        header_box.append(
            build_icon_title(
                "Template Marketplace",
                "folder-download-symbolic",
            )
        )
        header_box.append(subtitle)

        install_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)

        self.path_entry = Gtk.Entry()
        self.path_entry.set_hexpand(True)
        self.path_entry.set_placeholder_text("Path to template pack JSON")

        install_button = Gtk.Button(label="Install Pack")
        install_button.connect("clicked", self.on_install_pack)
        install_button.add_css_class("suggested-action")

        refresh_button = Gtk.Button(label="Refresh")
        refresh_button.connect("clicked", self.on_refresh_clicked)

        install_row.append(self.path_entry)
        install_row.append(install_button)
        install_row.append(refresh_button)

        self.status_label = Gtk.Label(label="")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.add_css_class("dim-label")
        self.status_label.add_css_class("inline-status")

        self.summary_label = Gtk.Label(label="")
        self.summary_label.set_wrap(True)
        self.summary_label.set_halign(Gtk.Align.START)
        self.summary_label.add_css_class("dim-label")
        self.summary_label.add_css_class("inline-status")

        filters_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        filters_row.add_css_class("canvas-toolbar-row")
        filters_row.add_css_class("compact-toolbar-row")
        filters_row.add_css_class("page-action-bar")

        self.search_entry = Gtk.Entry()
        self.search_entry.set_hexpand(True)
        self.search_entry.set_placeholder_text("Search templates by name, pack, type, or summary")
        self.search_entry.connect("changed", self.on_filters_changed)

        self.type_dropdown = Gtk.DropDown.new_from_strings(["All Types"])
        self.type_dropdown.connect("notify::selected", self.on_type_filter_changed)

        reset_filters_button = Gtk.Button(label="Reset")
        reset_filters_button.add_css_class("compact-action-button")
        reset_filters_button.connect("clicked", self.on_reset_filters)

        filters_row.append(self.search_entry)
        filters_row.append(self.type_dropdown)
        filters_row.append(reset_filters_button)

        section_title = build_icon_section(
            "Templates",
            "view-list-symbolic",
        )

        self.empty_label = Gtk.Label(label="No templates found.")
        self.empty_label.add_css_class("dim-label")
        self.empty_label.add_css_class("empty-state-label")
        self.empty_label.set_halign(Gtk.Align.START)

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        scroll = Gtk.ScrolledWindow()
        scroll.set_hexpand(True)
        scroll.set_vexpand(True)
        scroll.set_child(self.list_box)

        install_panel = Gtk.Frame()
        install_panel.add_css_class("panel-card")
        install_panel.add_css_class("entity-form-panel")
        install_panel.set_child(wrap_horizontal_row(install_row))

        self.append(header_box)
        self.append(install_panel)
        self.append(self.status_label)
        self.append(self.summary_label)
        self.append(filters_row)
        self.append(section_title)
        self.append(self.empty_label)
        self.append(scroll)

        self.refresh_list()

    def on_install_pack(self, _button):
        path_value = self.path_entry.get_text().strip()
        if not path_value:
            self.status_label.set_text("Enter a pack file path first.")
            return

        ok, message = self.marketplace.install_pack_from_file(path_value)
        self.status_label.set_text(message)
        if ok:
            self.path_entry.set_text("")
            self.refresh_list()

    def on_refresh_clicked(self, _button):
        self.refresh_list()
        self.status_label.set_text("Template marketplace refreshed.")

    def on_filters_changed(self, *_args):
        self.refresh_list()

    def on_type_filter_changed(self, *_args):
        if self.loading_type_filter:
            return
        self.refresh_list()

    def on_reset_filters(self, _button):
        self.search_entry.set_text("")
        self.loading_type_filter = True
        self.type_dropdown.set_selected(0)
        self.loading_type_filter = False
        self.refresh_list()

    def selected_template_type_filter(self) -> str:
        index = self.type_dropdown.get_selected()
        if index <= 0:
            return "all"
        type_index = index - 1
        if 0 <= type_index < len(self.template_type_options):
            return self.template_type_options[type_index]
        return "all"

    def rebuild_type_dropdown(self, templates: list[dict]):
        current_type = self.selected_template_type_filter()
        unique_types = sorted(
            {
                str(item.get("node_type", "")).strip()
                for item in templates
                if str(item.get("node_type", "")).strip()
            },
            key=str.lower,
        )
        self.template_type_options = unique_types
        labels = ["All Types"] + unique_types
        replacement = Gtk.DropDown.new_from_strings(labels)
        replacement.connect("notify::selected", self.on_type_filter_changed)

        selected_index = 0
        if current_type in unique_types:
            selected_index = unique_types.index(current_type) + 1
        self.loading_type_filter = True
        replacement.set_selected(selected_index)
        self.loading_type_filter = False

        parent = self.type_dropdown.get_parent()
        if isinstance(parent, Gtk.Box):
            parent.remove(self.type_dropdown)
            parent.insert_child_after(replacement, self.search_entry)
        self.type_dropdown = replacement

    def filtered_templates(self, templates: list[dict]) -> list[dict]:
        query = self.search_entry.get_text().strip().lower()
        type_filter = self.selected_template_type_filter().lower()
        filtered: list[dict] = []
        for template in templates:
            node_type = str(template.get("node_type", "")).strip()
            if type_filter != "all" and node_type.lower() != type_filter:
                continue

            if query:
                haystack = " ".join(
                    [
                        str(template.get("name", "")).lower(),
                        str(template.get("node_type", "")).lower(),
                        str(template.get("summary", "")).lower(),
                        str(template.get("detail", "")).lower(),
                        str(template.get("pack_name", "")).lower(),
                    ]
                )
                if query not in haystack:
                    continue
            filtered.append(template)
        return filtered

    def refresh_list(self):
        child = self.list_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.list_box.remove(child)
            child = next_child

        packs = self.marketplace.list_packs()
        templates = self.marketplace.list_templates()
        self.rebuild_type_dropdown(templates)
        visible_templates = self.filtered_templates(templates)

        self.summary_label.set_text(
            f"Installed packs: {len(packs)}  •  Showing {len(visible_templates)} of {len(templates)} templates"
        )
        self.empty_label.set_visible(len(visible_templates) == 0)

        for template in visible_templates:
            self.list_box.append(self.build_card(template))

    def build_card(self, template: dict) -> Gtk.Frame:
        frame = Gtk.Frame()
        frame.add_css_class("list-card")
        frame.add_css_class("entity-card")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)

        title = Gtk.Label(
            label=f"{template.get('name', '')}  ({template.get('node_type', '')})"
        )
        title.add_css_class("heading")
        title.set_halign(Gtk.Align.START)

        summary = Gtk.Label(label=template.get("summary", ""))
        summary.set_wrap(True)
        summary.set_halign(Gtk.Align.START)

        detail_preview = template.get("detail", "")
        detail = Gtk.Label(label=f"Default detail: {detail_preview}")
        detail.set_wrap(True)
        detail.set_halign(Gtk.Align.START)
        detail.add_css_class("dim-label")

        pack_meta = Gtk.Label(label=f"Pack: {template.get('pack_name', 'Unknown')}")
        pack_meta.set_halign(Gtk.Align.START)
        pack_meta.add_css_class("dim-label")

        box.append(title)
        box.append(summary)
        box.append(detail)
        box.append(pack_meta)
        frame.set_child(box)
        return frame
