import gi
import threading
import uuid

gi.require_version("Gtk", "4.0")

from gi.repository import Gtk, GLib

from src.models.bot import Bot
from src.services.ai_service import AIService
from src.services.bot_store import BotStore
from src.services.settings_store import SettingsStore
from src.ui import build_icon_title, build_icon_section, build_labeled_field, create_icon


class BotsView(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.add_css_class("page-root")
        self.add_css_class("bots-root")

        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.set_margin_start(6)
        self.set_margin_end(6)

        self.store = BotStore()
        self.settings_store = SettingsStore()
        self.ai_service = AIService(settings_store=self.settings_store)
        self.bots = self.store.load_bots()
        self.settings = self.settings_store.load_settings()
        self.editing_bot_id: str | None = None
        self.provider_filter = "all"
        self.bot_presets: list[dict[str, str]] = [
            {
                "label": "Support Assistant",
                "name": "Support Assistant",
                "role": "Handle support questions with clear next actions.",
                "provider": "local",
            },
            {
                "label": "Workflow Reviewer",
                "name": "Workflow Reviewer",
                "role": "Review workflow outputs and flag risky or incomplete steps.",
                "provider": "openai",
            },
            {
                "label": "Ops Summarizer",
                "name": "Ops Summarizer",
                "role": "Summarize runs, failures, and operational signals for daily review.",
                "provider": "anthropic",
            },
        ]

        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        header_box.add_css_class("page-hero")

        subtitle = Gtk.Label(
            label="Define reusable AI bots with a role, provider, and model. These bot profiles will later be callable from workflows and AI nodes."
        )
        subtitle.set_wrap(True)
        subtitle.set_halign(Gtk.Align.START)
        subtitle.add_css_class("dim-label")

        header_box.append(
            build_icon_title(
                "Bots",
                "system-users-symbolic",
            )
        )
        header_box.append(subtitle)

        self.name_entry = Gtk.Entry()
        self.name_entry.set_placeholder_text("Bot name")

        self.role_entry = Gtk.Entry()
        self.role_entry.set_placeholder_text("Role  •  Example: Support Assistant, File Summarizer, Workflow Helper")

        self.provider_dropdown = Gtk.DropDown.new_from_strings(
            ["local", "openai", "anthropic"]
        )
        self.provider_dropdown.set_selected(
            self.provider_index(self.settings.get("preferred_provider", "local"))
        )

        self.model_entry = Gtk.Entry()
        self.model_entry.set_placeholder_text("Model name  •  Example: llama3.1, gpt-4.1, claude-sonnet-4")
        self.model_entry.set_text(self.settings.get("default_local_model", ""))

        self.temperature_override_switch = Gtk.Switch()
        self.temperature_override_switch.connect(
            "notify::active",
            self.on_temperature_override_toggled,
        )
        self.temperature_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            0.0,
            2.0,
            0.01,
        )
        self.temperature_scale.set_draw_value(False)
        self.temperature_scale.set_hexpand(True)
        self.temperature_spin = Gtk.SpinButton.new_with_range(0.0, 2.0, 0.01)
        self.temperature_spin.set_digits(2)
        self.temperature_spin.set_numeric(True)
        self.temperature_spin.set_width_chars(5)
        self.temperature_scale.connect("value-changed", self.on_temperature_scale_changed)
        self.temperature_spin.connect("value-changed", self.on_temperature_spin_changed)
        temperature_adjust_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        temperature_adjust_row.add_css_class("settings-adjust-row")
        temperature_adjust_row.append(self.temperature_scale)
        temperature_adjust_row.append(self.temperature_spin)

        self.max_tokens_override_switch = Gtk.Switch()
        self.max_tokens_override_switch.connect(
            "notify::active",
            self.on_max_tokens_override_toggled,
        )
        self.max_tokens_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL,
            64,
            64000,
            32,
        )
        self.max_tokens_scale.set_draw_value(False)
        self.max_tokens_scale.set_hexpand(True)
        self.max_tokens_spin = Gtk.SpinButton.new_with_range(64, 64000, 32)
        self.max_tokens_spin.set_digits(0)
        self.max_tokens_spin.set_numeric(True)
        self.max_tokens_spin.set_width_chars(6)
        self.max_tokens_scale.connect("value-changed", self.on_max_tokens_scale_changed)
        self.max_tokens_spin.connect("value-changed", self.on_max_tokens_spin_changed)
        max_tokens_adjust_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        max_tokens_adjust_row.add_css_class("settings-adjust-row")
        max_tokens_adjust_row.append(self.max_tokens_scale)
        max_tokens_adjust_row.append(self.max_tokens_spin)

        self.bot_preset_dropdown = Gtk.DropDown.new_from_strings(
            [item["label"] for item in self.bot_presets]
        )
        self.bot_preset_dropdown.set_hexpand(True)

        apply_bot_preset_button = Gtk.Button(label="Apply Preset")
        apply_bot_preset_button.add_css_class("compact-action-button")
        apply_bot_preset_button.connect("clicked", self.on_apply_bot_preset)

        bot_preset_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bot_preset_row.add_css_class("canvas-toolbar-row")
        bot_preset_row.add_css_class("compact-toolbar-row")
        bot_preset_row.add_css_class("page-action-bar")
        bot_preset_row.append(self.bot_preset_dropdown)
        bot_preset_row.append(apply_bot_preset_button)

        self.save_button = Gtk.Button(label="Add Bot")
        self.save_button.connect("clicked", self.on_add_bot)
        self.save_button.set_halign(Gtk.Align.START)
        self.save_button.add_css_class("suggested-action")
        self.save_button.add_css_class("compact-action-button")

        self.cancel_edit_button = Gtk.Button(label="Cancel Edit")
        self.cancel_edit_button.connect("clicked", self.on_cancel_edit)
        self.cancel_edit_button.set_halign(Gtk.Align.START)
        self.cancel_edit_button.set_visible(False)
        self.cancel_edit_button.add_css_class("compact-action-button")

        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_row.add_css_class("compact-action-row")
        action_row.append(self.save_button)
        action_row.append(self.cancel_edit_button)

        self.test_prompt_buffer = Gtk.TextBuffer()
        self.test_prompt_view = Gtk.TextView(buffer=self.test_prompt_buffer)
        self.test_prompt_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.test_prompt_view.set_size_request(-1, 74)
        self.test_prompt_buffer.set_text(
            "Give me a short response proving this bot configuration is working."
        )

        test_prompt_frame = Gtk.Frame()
        test_prompt_frame.add_css_class("canvas-edit-detail-frame")
        test_prompt_frame.set_child(self.test_prompt_view)

        self.test_output_buffer = Gtk.TextBuffer()
        self.test_output_view = Gtk.TextView(buffer=self.test_output_buffer)
        self.test_output_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.test_output_view.set_editable(False)
        self.test_output_view.set_cursor_visible(False)
        self.test_output_view.set_size_request(-1, 100)

        test_output_frame = Gtk.Frame()
        test_output_frame.add_css_class("canvas-edit-detail-frame")
        test_output_frame.set_child(self.test_output_view)

        self.test_status_label = Gtk.Label(label="")
        self.test_status_label.set_halign(Gtk.Align.START)
        self.test_status_label.set_wrap(True)
        self.test_status_label.add_css_class("dim-label")
        self.test_status_label.add_css_class("inline-status")

        self.run_form_test_button = Gtk.Button(label="Run Draft Bot Test")
        self.run_form_test_button.connect("clicked", self.on_run_form_test)
        self.run_form_test_button.add_css_class("suggested-action")
        self.run_form_test_button.add_css_class("compact-action-button")

        clear_test_button = Gtk.Button(label="Clear Output")
        clear_test_button.connect("clicked", self.on_clear_test_output)
        clear_test_button.add_css_class("compact-action-button")

        test_action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        test_action_row.add_css_class("compact-action-row")
        test_action_row.append(self.run_form_test_button)
        test_action_row.append(clear_test_button)

        editor_shell = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        editor_shell.set_margin_top(6)
        editor_shell.set_margin_bottom(6)
        editor_shell.set_margin_start(6)
        editor_shell.set_margin_end(6)

        editor_top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        editor_top_row.add_css_class("settings-panel-row")
        editor_top_row.set_homogeneous(True)

        profile_panel = self.build_form_panel(
            "Bot Profile",
            "avatar-default-symbolic",
            [
                build_labeled_field("Profile Preset", bot_preset_row),
                build_labeled_field("Bot Name", self.name_entry),
                build_labeled_field("Bot Role", self.role_entry),
                build_labeled_field("Provider", self.provider_dropdown),
                build_labeled_field("Model", self.model_entry),
                action_row,
            ],
        )
        profile_panel.set_hexpand(True)

        tuning_panel = self.build_form_panel(
            "Model Tuning",
            "preferences-system-symbolic",
            [
                build_labeled_field(
                    "Override Temperature",
                    self.temperature_override_switch,
                    compact=True,
                ),
                build_labeled_field("Temperature", temperature_adjust_row),
                build_labeled_field(
                    "Override Max Tokens",
                    self.max_tokens_override_switch,
                    compact=True,
                ),
                build_labeled_field("Max Tokens", max_tokens_adjust_row),
            ],
        )
        tuning_panel.set_hexpand(True)

        editor_top_row.append(profile_panel)
        editor_top_row.append(tuning_panel)
        editor_shell.append(editor_top_row)

        test_panel = self.build_form_panel(
            "Bot Test Console",
            "system-search-symbolic",
            [
                build_labeled_field("Draft Test Prompt", test_prompt_frame),
                test_action_row,
                self.test_status_label,
                build_labeled_field("Draft Test Output", test_output_frame),
            ],
        )
        editor_shell.append(test_panel)

        form_frame = Gtk.Frame()
        form_frame.add_css_class("panel-card")
        form_frame.add_css_class("entity-form-panel")
        form_frame.set_child(editor_shell)

        section_title = build_icon_section(
            "Saved Bots",
            "avatar-default-symbolic",
        )

        self.empty_label = Gtk.Label(
            label="No bots yet. Create your first bot above."
        )
        self.empty_label.set_halign(Gtk.Align.START)
        self.empty_label.add_css_class("dim-label")
        self.empty_label.add_css_class("empty-state-label")

        self.status_label = Gtk.Label(label="")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.add_css_class("dim-label")
        self.status_label.add_css_class("inline-status")

        list_controls_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        list_controls_row.add_css_class("canvas-toolbar-row")
        list_controls_row.add_css_class("compact-toolbar-row")
        list_controls_row.add_css_class("page-action-bar")

        self.search_entry = Gtk.Entry()
        self.search_entry.set_hexpand(True)
        self.search_entry.set_placeholder_text("Search bots by name, role, model, or provider")
        self.search_entry.connect("changed", self.on_filters_changed)

        self.provider_filter_row = self.build_provider_filter_row()
        self.reset_filters_button = Gtk.Button(label="Reset")
        self.reset_filters_button.add_css_class("compact-action-button")
        self.reset_filters_button.connect("clicked", self.on_reset_filters)

        list_controls_row.append(self.search_entry)
        list_controls_row.append(self.provider_filter_row)
        list_controls_row.append(self.reset_filters_button)

        self.list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        self.append(header_box)
        self.append(list_controls_row)
        self.append(form_frame)
        self.append(section_title)
        self.append(self.empty_label)
        self.append(self.status_label)
        self.append(self.list_box)

        self.update_tuning_override_states()
        self.refresh_list()

    def on_apply_bot_preset(self, _button):
        index = self.bot_preset_dropdown.get_selected()
        if index < 0 or index >= len(self.bot_presets):
            self.status_label.set_text("Select a preset first.")
            return
        preset = self.bot_presets[index]
        self.name_entry.set_text(preset.get("name", ""))
        self.role_entry.set_text(preset.get("role", ""))
        self.provider_dropdown.set_selected(self.provider_index(preset.get("provider", "local")))
        self.status_label.set_text(f"Preset loaded: {preset.get('label', 'Bot Preset')}.")

    def provider_index(self, value: str) -> int:
        values = ["local", "openai", "anthropic"]
        return values.index(value) if value in values else 0

    def selected_provider(self) -> str:
        values = ["local", "openai", "anthropic"]
        index = self.provider_dropdown.get_selected()
        return values[index] if 0 <= index < len(values) else "local"

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
        body.set_margin_top(7)
        body.set_margin_bottom(7)
        body.set_margin_start(7)
        body.set_margin_end(7)
        body.append(build_icon_section(title, icon_name, level="heading"))

        for row in rows:
            body.append(row)

        panel.set_child(body)
        return panel

    def on_add_bot(self, button):
        name = self.name_entry.get_text().strip()
        role = self.role_entry.get_text().strip()
        provider = self.selected_provider()
        model = self.model_entry.get_text().strip()
        temperature, max_tokens = self.current_tuning_values()

        if not name or not role or not model:
            self.status_label.set_text("Name, role, and model are required.")
            return

        duplicate = next(
            (
                bot
                for bot in self.bots
                if bot.name.strip().lower() == name.lower()
                and bot.id != (self.editing_bot_id or "")
            ),
            None,
        )
        if duplicate:
            self.status_label.set_text("A bot with that name already exists.")
            return

        if self.editing_bot_id:
            updated = False
            for index, bot in enumerate(self.bots):
                if bot.id == self.editing_bot_id:
                    self.bots[index] = Bot(
                        id=bot.id,
                        name=name,
                        role=role,
                        provider=provider,
                        model=model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    updated = True
                    break
            if not updated:
                self.status_label.set_text("Could not find the bot to update.")
                return
            self.status_label.set_text("Bot updated.")
        else:
            bot = Bot(
                id=str(uuid.uuid4()),
                name=name,
                role=role,
                provider=provider,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            self.bots.append(bot)
            self.status_label.set_text("Bot created.")

        self.store.save_bots(self.bots)
        self.reset_form()

        self.refresh_list()

    def on_delete_bot(self, button, bot_id):
        self.bots = [bot for bot in self.bots if bot.id != bot_id]
        self.store.save_bots(self.bots)
        if self.editing_bot_id == bot_id:
            self.reset_form()
        self.status_label.set_text("Bot deleted.")
        self.refresh_list()

    def on_edit_bot(self, _button, bot_id):
        bot = next((item for item in self.bots if item.id == bot_id), None)
        if not bot:
            self.status_label.set_text("Bot not found.")
            return

        self.editing_bot_id = bot.id
        self.name_entry.set_text(bot.name)
        self.role_entry.set_text(bot.role)
        self.provider_dropdown.set_selected(self.provider_index(bot.provider))
        self.model_entry.set_text(bot.model)
        self.temperature_override_switch.set_active(bool(bot.temperature.strip()))
        resolved_temp = self.parse_float(bot.temperature, 0.2)
        self.temperature_scale.set_value(resolved_temp)
        self.temperature_spin.set_value(resolved_temp)
        self.max_tokens_override_switch.set_active(bool(bot.max_tokens.strip()))
        resolved_tokens = self.parse_int(bot.max_tokens, 700)
        self.max_tokens_scale.set_value(float(resolved_tokens))
        self.max_tokens_spin.set_value(float(resolved_tokens))
        self.update_tuning_override_states()
        self.save_button.set_label("Save Bot")
        self.cancel_edit_button.set_visible(True)
        self.status_label.set_text(f"Editing '{bot.name}'.")

    def on_cancel_edit(self, _button):
        self.reset_form()
        self.refresh_list()

    def on_run_form_test(self, _button):
        prompt = self.test_prompt_buffer.get_text(
            self.test_prompt_buffer.get_start_iter(),
            self.test_prompt_buffer.get_end_iter(),
            False,
        ).strip()
        if not prompt:
            self.test_status_label.set_text("Enter a test prompt first.")
            return

        role = self.role_entry.get_text().strip()
        provider = self.selected_provider()
        model = self.model_entry.get_text().strip()
        name = self.name_entry.get_text().strip() or "Draft Bot"

        if not role or not model:
            self.test_status_label.set_text("Role and model are required to run a draft bot test.")
            return

        draft_bot = Bot(
            id=self.editing_bot_id or "draft-bot",
            name=name,
            role=role,
            provider=provider,
            model=model,
            temperature=self.current_tuning_values()[0],
            max_tokens=self.current_tuning_values()[1],
        )
        self.run_bot_test(draft_bot, prompt, context_label="Draft bot")

    def on_clear_test_output(self, _button):
        self.test_status_label.set_text("")
        self.test_output_buffer.set_text("")

    def run_bot_test(self, bot: Bot, prompt: str, context_label: str):
        self.run_form_test_button.set_sensitive(False)
        self.test_status_label.set_text(f"Running AI test for {context_label}...")
        self.test_output_buffer.set_text("")
        threading.Thread(
            target=self._run_bot_test_worker,
            args=(bot, prompt, context_label),
            daemon=True,
        ).start()

    def _run_bot_test_worker(self, bot: Bot, prompt: str, context_label: str):
        try:
            result = self.ai_service.generate_with_metadata(
                prompt=prompt,
                bot=bot,
                system_prompt=bot.role,
            )
        except Exception as error:
            GLib.idle_add(self._finish_bot_test_error, context_label, str(error))
            return
        GLib.idle_add(self._finish_bot_test_success, context_label, result)

    def _finish_bot_test_success(self, context_label: str, result: dict[str, str]):
        self.run_form_test_button.set_sensitive(True)
        provider = result.get("provider", "unknown")
        model = result.get("model", "unknown")
        latency_ms = result.get("latency_ms", "0")
        response = result.get("response", "")

        self.test_status_label.set_text(
            f"{context_label} test passed  •  {provider}/{model}  •  {latency_ms} ms"
        )
        self.test_output_buffer.set_text(response)
        return False

    def _finish_bot_test_error(self, context_label: str, error_message: str):
        self.run_form_test_button.set_sensitive(True)
        self.test_status_label.set_text(f"{context_label} test failed: {error_message}")
        return False

    def reset_form(self):
        self.editing_bot_id = None
        self.name_entry.set_text("")
        self.role_entry.set_text("")
        self.provider_dropdown.set_selected(
            self.provider_index(self.settings.get("preferred_provider", "local"))
        )
        self.model_entry.set_text(self.settings.get("default_local_model", ""))
        self.temperature_override_switch.set_active(False)
        self.temperature_scale.set_value(0.2)
        self.temperature_spin.set_value(0.2)
        self.max_tokens_override_switch.set_active(False)
        self.max_tokens_scale.set_value(700)
        self.max_tokens_spin.set_value(700)
        self.update_tuning_override_states()
        self.save_button.set_label("Add Bot")
        self.cancel_edit_button.set_visible(False)

    def on_filters_changed(self, *_args):
        self.refresh_list()

    def build_provider_filter_row(self) -> Gtk.Box:
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.add_css_class("segmented-row")
        row.add_css_class("compact-segmented-row")

        self.provider_filter_buttons: dict[str, Gtk.ToggleButton] = {}
        for key, label in [
            ("all", "All"),
            ("local", "Local"),
            ("openai", "OpenAI"),
            ("anthropic", "Anthropic"),
        ]:
            button = Gtk.ToggleButton(label=label)
            button.add_css_class("segmented-button")
            button.add_css_class("compact-segmented-button")
            button.connect("toggled", self.on_provider_filter_toggled, key)
            row.append(button)
            self.provider_filter_buttons[key] = button

        self.provider_filter_buttons["all"].set_active(True)
        return row

    def on_provider_filter_toggled(self, button: Gtk.ToggleButton, key: str):
        if not button.get_active():
            if not any(item.get_active() for item in self.provider_filter_buttons.values()):
                button.set_active(True)
            return

        for other_key, other in self.provider_filter_buttons.items():
            if other_key != key and other.get_active():
                other.set_active(False)
        self.provider_filter = key
        self.refresh_list()

    def on_reset_filters(self, _button):
        self.search_entry.set_text("")
        self.provider_filter_buttons["all"].set_active(True)
        self.refresh_list()

    def filtered_bots(self) -> list[Bot]:
        query = self.search_entry.get_text().strip().lower()
        provider_filter = self.provider_filter

        filtered: list[Bot] = []
        for bot in self.bots:
            if provider_filter != "all" and bot.provider.strip().lower() != provider_filter:
                continue
            if query:
                haystack = (
                    f"{bot.name} {bot.role} {bot.provider} {bot.model} "
                    f"{bot.temperature} {bot.max_tokens}"
                ).strip().lower()
                if query not in haystack:
                    continue
            filtered.append(bot)
        return filtered

    def refresh_list(self):
        if not hasattr(self, "list_box"):
            return
        child = self.list_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.list_box.remove(child)
            child = next_child

        visible_bots = self.filtered_bots()
        has_bots = len(visible_bots) > 0
        self.empty_label.set_visible(not has_bots)

        for bot in visible_bots:
            self.list_box.append(self.build_bot_card(bot))

    def build_bot_card(self, bot: Bot) -> Gtk.Frame:
        frame = Gtk.Frame()
        frame.add_css_class("list-card")
        frame.add_css_class("entity-card")
        frame.add_css_class("bot-card")
        tone_class = self.bot_tone_class(bot.provider)
        frame.add_css_class(tone_class)

        outer_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer_box.set_margin_top(8)
        outer_box.set_margin_bottom(8)
        outer_box.set_margin_start(8)
        outer_box.set_margin_end(8)

        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title_row.add_css_class("compact-action-row")
        title_row.add_css_class("entity-card-title-row")
        title_row.add_css_class("bot-title-row")
        title_row.add_css_class(f"{tone_class}-title")

        name_label = Gtk.Label(label=bot.name)
        name_label.add_css_class("title-3")
        name_label.set_halign(Gtk.Align.START)
        name_label.set_hexpand(True)

        edit_button = Gtk.Button(label="Edit")
        edit_button.connect("clicked", self.on_edit_bot, bot.id)
        edit_button.add_css_class("compact-action-button")

        test_button = Gtk.Button(label="Test")
        test_button.add_css_class("suggested-action")
        test_button.add_css_class("compact-action-button")
        test_button.connect("clicked", self.on_test_existing_bot, bot.id)

        delete_button = Gtk.Button(label="Delete")
        delete_button.connect("clicked", self.on_delete_bot, bot.id)
        delete_button.add_css_class("compact-action-button")

        title_row.append(name_label)
        title_row.append(edit_button)
        title_row.append(test_button)
        title_row.append(delete_button)

        meta_grid = Gtk.Grid()
        meta_grid.set_column_spacing(12)
        meta_grid.set_row_spacing(10)

        role_title = Gtk.Label(label="Role")
        role_title.add_css_class("heading")
        role_title.set_halign(Gtk.Align.START)

        role_value = Gtk.Label(label=bot.role)
        role_value.set_halign(Gtk.Align.START)
        role_value.set_wrap(True)
        role_value.add_css_class("dim-label")

        provider_title = Gtk.Label(label="Provider")
        provider_title.add_css_class("heading")
        provider_title.set_halign(Gtk.Align.START)

        provider_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        provider_icon = create_icon(
            self.provider_icon_name(bot.provider),
            css_class="provider-icon",
        )

        provider_value = Gtk.Label(label=bot.provider)
        provider_value.set_halign(Gtk.Align.START)
        provider_value.set_wrap(True)
        provider_value.add_css_class("provider-chip")
        provider_value.add_css_class(f"provider-{bot.provider.strip().lower()}")
        provider_box.append(provider_icon)
        provider_box.append(provider_value)

        model_title = Gtk.Label(label="Model")
        model_title.add_css_class("heading")
        model_title.set_halign(Gtk.Align.START)

        model_value = Gtk.Label(label=bot.model)
        model_value.set_halign(Gtk.Align.START)
        model_value.set_wrap(True)
        model_value.add_css_class("dim-label")

        tuning_value = Gtk.Label(
            label=(
                f"Temp: {bot.temperature or '0.2'}  •  "
                f"Max tokens: {bot.max_tokens or '700'}"
            )
        )
        tuning_value.set_halign(Gtk.Align.START)
        tuning_value.set_wrap(True)
        tuning_value.add_css_class("inline-status")
        tuning_value.add_css_class("bot-tuning-chip")

        meta_grid.attach(role_title, 0, 0, 1, 1)
        meta_grid.attach(role_value, 0, 1, 1, 1)
        meta_grid.attach(provider_title, 1, 0, 1, 1)
        meta_grid.attach(provider_box, 1, 1, 1, 1)
        meta_grid.attach(model_title, 2, 0, 1, 1)
        meta_grid.attach(model_value, 2, 1, 1, 1)
        meta_grid.attach(tuning_value, 0, 2, 3, 1)

        outer_box.append(title_row)
        outer_box.append(meta_grid)

        frame.set_child(outer_box)
        return frame

    def bot_tone_class(self, provider: str) -> str:
        normalized = str(provider).strip().lower()
        if normalized == "local":
            return "bot-tone-local"
        if normalized == "openai":
            return "bot-tone-openai"
        if normalized == "anthropic":
            return "bot-tone-anthropic"
        return "bot-tone-default"

    def on_test_existing_bot(self, _button, bot_id: str):
        bot = next((item for item in self.bots if item.id == bot_id), None)
        if not bot:
            self.test_status_label.set_text("Bot not found for testing.")
            return

        prompt = self.test_prompt_buffer.get_text(
            self.test_prompt_buffer.get_start_iter(),
            self.test_prompt_buffer.get_end_iter(),
            False,
        ).strip()
        if not prompt:
            prompt = "Reply briefly so I can verify this bot configuration."
            self.test_prompt_buffer.set_text(prompt)

        self.run_bot_test(bot, prompt, context_label=f"Bot '{bot.name}'")

    def provider_icon_name(self, provider: str) -> str:
        normalized = provider.strip().lower()
        if normalized == "openai":
            return "network-server-symbolic"
        if normalized == "anthropic":
            return "dialog-information-symbolic"
        return "computer-symbolic"

    def validate_tuning_fields(self, temperature: str, max_tokens: str) -> str:
        if temperature:
            try:
                temp_value = float(temperature)
            except ValueError:
                return "Temperature must be a number (example: 0.2)."
            if temp_value < 0.0 or temp_value > 2.0:
                return "Temperature must be between 0.0 and 2.0."

        if max_tokens:
            try:
                token_value = int(max_tokens)
            except ValueError:
                return "Max tokens must be a whole number."
            if token_value < 64 or token_value > 64000:
                return "Max tokens must be between 64 and 64000."

        return ""

    def on_temperature_override_toggled(self, _switch, _param):
        self.update_tuning_override_states()

    def on_max_tokens_override_toggled(self, _switch, _param):
        self.update_tuning_override_states()

    def update_tuning_override_states(self):
        temp_enabled = self.temperature_override_switch.get_active()
        self.temperature_scale.set_sensitive(temp_enabled)
        self.temperature_spin.set_sensitive(temp_enabled)
        tokens_enabled = self.max_tokens_override_switch.get_active()
        self.max_tokens_scale.set_sensitive(tokens_enabled)
        self.max_tokens_spin.set_sensitive(tokens_enabled)

    def on_temperature_scale_changed(self, scale: Gtk.Scale):
        value = round(scale.get_value(), 2)
        if abs(self.temperature_spin.get_value() - value) > 0.005:
            self.temperature_spin.set_value(value)

    def on_temperature_spin_changed(self, spin: Gtk.SpinButton):
        value = round(spin.get_value(), 2)
        if abs(self.temperature_scale.get_value() - value) > 0.005:
            self.temperature_scale.set_value(value)

    def on_max_tokens_scale_changed(self, scale: Gtk.Scale):
        value = int(scale.get_value())
        if self.max_tokens_spin.get_value_as_int() != value:
            self.max_tokens_spin.set_value(value)

    def on_max_tokens_spin_changed(self, spin: Gtk.SpinButton):
        value = spin.get_value_as_int()
        if int(self.max_tokens_scale.get_value()) != value:
            self.max_tokens_scale.set_value(value)

    def current_tuning_values(self) -> tuple[str, str]:
        temperature = ""
        if self.temperature_override_switch.get_active():
            temperature = f"{self.temperature_spin.get_value():.2f}"

        max_tokens = ""
        if self.max_tokens_override_switch.get_active():
            max_tokens = str(self.max_tokens_spin.get_value_as_int())

        return temperature, max_tokens

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
