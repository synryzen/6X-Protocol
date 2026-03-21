import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gio", "2.0")

from gi.repository import Gtk, Gdk, Gio


DEFAULT_ICON_FALLBACKS = (
    "applications-system-symbolic",
    "application-x-executable-symbolic",
    "preferences-system-symbolic",
    "image-missing",
)


def _expand_icon_candidate(name: str) -> list[str]:
    value = str(name).strip()
    if not value:
        return []

    variants = [value]
    if value.endswith("-symbolic"):
        variants.append(value[: -len("-symbolic")])
    else:
        variants.append(f"{value}-symbolic")

    deduped: list[str] = []
    seen: set[str] = set()
    for item in variants:
        if item and item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def resolve_icon_name(
    icon_name: str,
    fallbacks: tuple[str, ...] | list[str] | None = None,
) -> str:
    candidates: list[str] = []
    primary = str(icon_name).strip()
    candidates.extend(_expand_icon_candidate(primary))
    if fallbacks:
        for item in fallbacks:
            candidates.extend(_expand_icon_candidate(str(item)))
    for fallback in DEFAULT_ICON_FALLBACKS:
        candidates.extend(_expand_icon_candidate(fallback))

    display = Gdk.Display.get_default()
    if not display:
        return candidates[0] if candidates else "image-missing"

    theme = Gtk.IconTheme.get_for_display(display)
    for candidate in candidates:
        try:
            if theme.has_icon(candidate):
                return candidate
        except Exception:
            continue
    return "image-missing"


def icon_candidates(
    icon_name: str,
    fallbacks: tuple[str, ...] | list[str] | None = None,
) -> list[str]:
    candidates: list[str] = []
    primary = str(icon_name).strip()
    candidates.extend(_expand_icon_candidate(primary))
    if fallbacks:
        for item in fallbacks:
            candidates.extend(_expand_icon_candidate(str(item)))
    for fallback in DEFAULT_ICON_FALLBACKS:
        candidates.extend(_expand_icon_candidate(fallback))
    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        if item and item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def create_icon(
    icon_name: str,
    css_class: str | None = None,
    fallbacks: tuple[str, ...] | list[str] | None = None,
) -> Gtk.Image:
    candidates = icon_candidates(icon_name, fallbacks=fallbacks)
    icon: Gtk.Image
    if candidates:
        try:
            themed = Gio.ThemedIcon.new_from_names(candidates)
            icon = Gtk.Image.new_from_gicon(themed)
        except Exception:
            resolved = resolve_icon_name(icon_name, fallbacks=fallbacks)
            icon = Gtk.Image.new_from_icon_name(resolved)
    else:
        icon = Gtk.Image.new_from_icon_name("image-missing")
    if css_class:
        icon.add_css_class(css_class)
    return icon


def build_icon_title(title: str, icon_name: str) -> Gtk.Box:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    row.add_css_class("title-icon-row")

    icon = create_icon(icon_name, css_class="title-icon")

    label = Gtk.Label(label=title)
    label.add_css_class("title-1")
    label.set_halign(Gtk.Align.START)

    row.append(icon)
    row.append(label)
    return row


def build_icon_section(title: str, icon_name: str, level: str = "title-3") -> Gtk.Box:
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    row.add_css_class("section-icon-row")

    icon = create_icon(icon_name, css_class="section-icon")

    label = Gtk.Label(label=title)
    label.add_css_class(level)
    label.set_halign(Gtk.Align.START)

    row.append(icon)
    row.append(label)
    return row


def build_labeled_field(text: str, widget: Gtk.Widget, compact: bool = False) -> Gtk.Box:
    row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    row.add_css_class("settings-field-row")
    if compact:
        row.add_css_class("settings-field-compact")

    if compact:
        header_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = Gtk.Label(label=text)
        label.add_css_class("heading")
        label.set_halign(Gtk.Align.START)
        label.set_hexpand(True)
        header_row.append(label)
        header_row.append(widget)
        row.append(header_row)
        return row

    label = Gtk.Label(label=text)
    label.add_css_class("heading")
    label.set_halign(Gtk.Align.START)

    row.append(label)
    row.append(widget)
    return row


def wrap_horizontal_row(
    row: Gtk.Widget,
    css_class: str = "canvas-row-scroll",
) -> Gtk.ScrolledWindow:
    scroller = Gtk.ScrolledWindow()
    scroller.add_css_class(css_class)
    scroller.set_hexpand(True)
    scroller.set_vexpand(False)
    scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
    scroller.set_child(row)
    return scroller
