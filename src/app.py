import gi
from pathlib import Path

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, Gdk

from src.window import MainWindow


class SixXProtocolStudioApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="com.sixxprotocol.studio")
        self._styles_loaded = False

    def do_activate(self):
        self.ensure_styles_loaded()
        window = self.props.active_window
        if not window:
            window = MainWindow(application=self)
        window.present()

    def ensure_styles_loaded(self):
        if self._styles_loaded:
            return

        display = Gdk.Display.get_default()
        if display is None:
            return

        assets_dir = Path(__file__).resolve().parent / "assets"
        css_candidates = [
            assets_dir / "style.css",
            assets_dir / "app_theme.css",
        ]

        css_path = next((path for path in css_candidates if path.exists()), None)
        if css_path is None:
            return

        provider = Gtk.CssProvider()
        provider.load_from_path(str(css_path))
        Gtk.StyleContext.add_provider_for_display(
            display,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )
        self._styles_loaded = True
