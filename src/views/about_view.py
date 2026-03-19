import gi

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, Gdk

from src.ui import build_icon_title, build_icon_section


class AboutView(Gtk.Box):
    WEBSITE_URL = "https://synryzen.com"
    GITHUB_URL = "https://github.com/synryzen/6X-Protocol"
    SUPPORT_EMAIL = "6X-Protocol@gmail.com"

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add_css_class("page-root")
        self.add_css_class("about-root")

        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(6)
        self.set_margin_end(6)

        hero_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        hero_box.add_css_class("page-hero")
        hero_box.add_css_class("about-hero")

        hero_kicker = Gtk.Label(label="6X-PROTOCOL STUDIO")
        hero_kicker.add_css_class("hero-kicker")
        hero_kicker.set_halign(Gtk.Align.START)

        hero_subtitle = Gtk.Label(
            label=(
                "Local-first automation platform by Matthew C Elliott. "
                "Use this free Linux app to power workflows and discover the wider Synryzen app ecosystem."
            )
        )
        hero_subtitle.set_wrap(True)
        hero_subtitle.set_halign(Gtk.Align.START)
        hero_subtitle.add_css_class("dim-label")

        hero_box.append(hero_kicker)
        hero_box.append(build_icon_title("About 6X-Protocol Studio", "help-about-symbolic"))
        hero_box.append(hero_subtitle)

        details_grid = Gtk.Grid()
        details_grid.set_column_spacing(12)
        details_grid.set_row_spacing(12)
        details_grid.set_hexpand(True)
        details_grid.set_vexpand(True)
        details_grid.add_css_class("about-grid")

        details_grid.attach(self.build_identity_card(), 0, 0, 1, 1)
        details_grid.attach(self.build_marketing_card(), 1, 0, 1, 1)

        self.status_label = Gtk.Label(label="")
        self.status_label.add_css_class("dim-label")
        self.status_label.add_css_class("inline-status")
        self.status_label.set_halign(Gtk.Align.START)

        self.append(hero_box)
        self.append(details_grid)
        self.append(self.status_label)

    def build_identity_card(self) -> Gtk.Frame:
        frame = Gtk.Frame()
        frame.add_css_class("panel-card")
        frame.add_css_class("about-card")
        frame.set_hexpand(True)
        frame.set_vexpand(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        box.append(build_icon_section("Creator & Support", "avatar-default-symbolic"))
        box.append(self.build_info_row("Developer", "Matthew C Elliott"))
        box.append(
            self.build_info_row(
                "Website",
                self.WEBSITE_URL,
                open_uri=self.WEBSITE_URL,
                copy_value=self.WEBSITE_URL,
            )
        )
        box.append(
            self.build_info_row(
                "GitHub",
                self.GITHUB_URL,
                open_uri=self.GITHUB_URL,
                copy_value=self.GITHUB_URL,
            )
        )
        box.append(
            self.build_info_row(
                "Support Email",
                self.SUPPORT_EMAIL,
                open_uri=f"mailto:{self.SUPPORT_EMAIL}",
                copy_value=self.SUPPORT_EMAIL,
            )
        )

        frame.set_child(box)
        return frame

    def build_marketing_card(self) -> Gtk.Frame:
        frame = Gtk.Frame()
        frame.add_css_class("panel-card")
        frame.add_css_class("about-card")
        frame.set_hexpand(True)
        frame.set_vexpand(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)

        box.append(build_icon_section("Promotion Path", "megaphone-symbolic"))

        lead = Gtk.Label(
            label=(
                "Use 6X-Protocol Studio as your free lead magnet, then route users to your "
                "premium iOS and macOS apps from the GitHub page and release notes."
            )
        )
        lead.set_wrap(True)
        lead.set_halign(Gtk.Align.START)
        lead.add_css_class("dim-label")
        box.append(lead)

        for line in [
            "1. Keep Linux download links first and frictionless.",
            "2. Add an \"Explore Matthew's Apps\" section on GitHub Pages.",
            "3. Use in-app About links for website, support, and app catalog.",
            "4. Add App Store links + screenshots once available.",
        ]:
            item = Gtk.Label(label=line)
            item.set_wrap(True)
            item.set_halign(Gtk.Align.START)
            item.add_css_class("about-bullet")
            box.append(item)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.add_css_class("compact-toolbar-row")

        website_button = Gtk.Button(label="Open Website")
        website_button.add_css_class("compact-action-button")
        website_button.connect("clicked", lambda _b: self.open_uri(self.WEBSITE_URL))

        github_button = Gtk.Button(label="Open GitHub")
        github_button.add_css_class("compact-action-button")
        github_button.connect("clicked", lambda _b: self.open_uri(self.GITHUB_URL))

        actions.append(website_button)
        actions.append(github_button)
        box.append(actions)

        frame.set_child(box)
        return frame

    def build_info_row(
        self,
        label: str,
        value: str,
        *,
        open_uri: str = "",
        copy_value: str = "",
    ) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        row.add_css_class("about-info-row")

        key_label = Gtk.Label(label=label)
        key_label.set_halign(Gtk.Align.START)
        key_label.add_css_class("heading")

        value_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        value_row.set_hexpand(True)

        value_label = Gtk.Label(label=value)
        value_label.set_halign(Gtk.Align.START)
        value_label.set_hexpand(True)
        value_label.set_wrap(True)
        value_label.set_selectable(True)
        value_label.add_css_class("about-value")

        value_row.append(value_label)

        if open_uri:
            open_button = Gtk.Button(label="Open")
            open_button.add_css_class("compact-action-button")
            open_button.connect("clicked", lambda _b, uri=open_uri: self.open_uri(uri))
            value_row.append(open_button)

        if copy_value:
            copy_button = Gtk.Button(label="Copy")
            copy_button.add_css_class("compact-action-button")
            copy_button.connect(
                "clicked",
                lambda _b, text=copy_value: self.copy_to_clipboard(text),
            )
            value_row.append(copy_button)

        row.append(key_label)
        row.append(value_row)
        return row

    def open_uri(self, uri: str):
        target = str(uri).strip()
        if not target:
            return
        try:
            root = self.get_root()
            window = root if isinstance(root, Gtk.Window) else None
            Gtk.show_uri(window, target, Gdk.CURRENT_TIME)
            self.status_label.set_text(f"Opened: {target}")
        except Exception:
            self.status_label.set_text(f"Could not open: {target}")

    def copy_to_clipboard(self, text: str):
        value = str(text).strip()
        if not value:
            return
        try:
            provider = Gdk.ContentProvider.new_for_value(value)
            self.get_clipboard().set(provider)
            self.status_label.set_text(f"Copied: {value}")
        except Exception:
            self.status_label.set_text("Copy failed. Please copy manually.")
