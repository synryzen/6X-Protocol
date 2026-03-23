import unittest
from types import SimpleNamespace
import time

try:
    from src.views.canvas_view import CanvasView, Gdk
    from src.models.canvas_node import CanvasNode
    from src.models.canvas_edge import CanvasEdge
    CANVAS_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - CI fallback when gi is unavailable
    CanvasView = None  # type: ignore[assignment]
    Gdk = None  # type: ignore[assignment]
    CanvasNode = None  # type: ignore[assignment]
    CanvasEdge = None  # type: ignore[assignment]
    CANVAS_IMPORT_ERROR = exc


class _FakeWidget:
    def __init__(self, translated):
        self._translated = translated

    def translate_coordinates(self, _dest, _x, _y):
        return self._translated


class _FailingWidget:
    def translate_coordinates(self, _dest, _x, _y):
        raise RuntimeError("boom")


class _FakeGesture:
    def __init__(self, widget):
        self._widget = widget

    def get_widget(self):
        return self._widget


class _FakeDragGesture(_FakeGesture):
    def __init__(self, widget, state=0):
        super().__init__(widget)
        self._state = state
        self.claimed = False

    def get_current_event_state(self):
        return self._state

    def set_state(self, _state):
        self.claimed = True


class _BrokenSizeWidget:
    def get_allocated_width(self):
        raise RuntimeError("width unavailable")

    def get_allocated_height(self):
        raise RuntimeError("height unavailable")


class _FakeAdjustment:
    def __init__(self, value: float):
        self._value = float(value)

    def get_value(self):
        return self._value


class _FakeScroll:
    def __init__(self, hadj: float, vadj: float):
        self._hadj = _FakeAdjustment(hadj)
        self._vadj = _FakeAdjustment(vadj)

    def get_hadjustment(self):
        return self._hadj

    def get_vadjustment(self):
        return self._vadj


class CanvasCoordinateTranslationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if CanvasView is None:
            raise unittest.SkipTest(
                f"Canvas GTK tests require gi runtime; unavailable in this environment ({CANVAS_IMPORT_ERROR})"
            )

    def setUp(self):
        # Exercise the helper directly without bootstrapping full GTK view state.
        self.view = CanvasView.__new__(CanvasView)
        self.view.canvas_scroll = None
        self.view.node_drag_last_pointer_stage = None

    def test_translate_widget_coordinates_accepts_gtk4_two_tuple(self):
        source = _FakeWidget((42.5, 64.0))
        result = self.view.translate_widget_coordinates(source, object(), 1.0, 2.0)
        self.assertEqual((42.5, 64.0), result)

    def test_translate_widget_coordinates_accepts_legacy_three_tuple(self):
        source = _FakeWidget((True, 17.0, 33.0))
        result = self.view.translate_widget_coordinates(source, object(), 1.0, 2.0)
        self.assertEqual((17.0, 33.0), result)

    def test_translate_widget_coordinates_rejects_failed_legacy_tuple(self):
        source = _FakeWidget((False, 17.0, 33.0))
        result = self.view.translate_widget_coordinates(source, object(), 1.0, 2.0)
        self.assertIsNone(result)

    def test_translate_widget_coordinates_accepts_nested_success_tuple(self):
        source = _FakeWidget((True, (11.0, 19.0)))
        result = self.view.translate_widget_coordinates(source, object(), 1.0, 2.0)
        self.assertEqual((11.0, 19.0), result)

    def test_translate_widget_coordinates_accepts_success_point_object(self):
        source = _FakeWidget((True, SimpleNamespace(x=14.0, y=26.5)))
        result = self.view.translate_widget_coordinates(source, object(), 1.0, 2.0)
        self.assertEqual((14.0, 26.5), result)

    def test_translate_widget_coordinates_accepts_list_shape(self):
        source = _FakeWidget([77.0, 31.25])
        result = self.view.translate_widget_coordinates(source, object(), 1.0, 2.0)
        self.assertEqual((77.0, 31.25), result)

    def test_translate_widget_coordinates_handles_short_success_tuple(self):
        source = _FakeWidget((True, 17.0))
        result = self.view.translate_widget_coordinates(source, object(), 1.0, 2.0)
        self.assertIsNone(result)

    def test_translate_widget_coordinates_handles_errors(self):
        source = _FailingWidget()
        result = self.view.translate_widget_coordinates(source, object(), 1.0, 2.0)
        self.assertIsNone(result)

    def test_parse_gesture_point_accepts_legacy_shape(self):
        result = self.view.parse_gesture_point((True, 25.0, 31.0))
        self.assertEqual((25.0, 31.0), result)

    def test_parse_gesture_point_accepts_two_value_shape(self):
        result = self.view.parse_gesture_point((25.0, 31.0))
        self.assertEqual((25.0, 31.0), result)

    def test_parse_gesture_point_accepts_point_object(self):
        result = self.view.parse_gesture_point(SimpleNamespace(x=9.5, y=12.25))
        self.assertEqual((9.5, 12.25), result)

    def test_parse_gesture_point_rejects_false_flag(self):
        result = self.view.parse_gesture_point((False, 25.0, 31.0))
        self.assertIsNone(result)

    def test_stage_pointer_from_node_drag_begin_prefers_translated_coordinates(self):
        self.view.fixed = object()
        self.view.translate_widget_coordinates = lambda *_args, **_kwargs: (140.0, 260.0)
        self.view.to_screen = lambda value: int(round(value))
        node = SimpleNamespace(x=80, y=120)
        pointer = self.view.stage_pointer_from_node_drag_begin(
            _FakeGesture(object()),
            12.0,
            16.0,
            node,
        )
        self.assertEqual((140.0, 260.0), pointer)

    def test_stage_pointer_from_node_drag_begin_falls_back_to_node_origin_offset(self):
        self.view.fixed = object()
        self.view.translate_widget_coordinates = lambda *_args, **_kwargs: None
        self.view.to_screen = lambda value: int(round(float(value) * 2.0))
        node = SimpleNamespace(x=40, y=60)
        pointer = self.view.stage_pointer_from_node_drag_begin(
            _FakeGesture(object()),
            8.5,
            9.25,
            node,
        )
        self.assertEqual((88.5, 129.25), pointer)

    def test_is_port_drag_stale_true_when_active_without_activity_timestamp(self):
        self.view.port_drag_active = True
        self.view.port_drag_last_activity_monotonic = 0.0
        self.assertTrue(self.view.is_port_drag_stale())

    def test_is_port_drag_stale_false_when_recent_activity_exists(self):
        self.view.port_drag_active = True
        self.view.port_drag_last_activity_monotonic = time.monotonic()
        self.assertFalse(self.view.is_port_drag_stale())

    def test_is_node_drag_stale_true_when_active_without_activity_timestamp(self):
        self.view.node_drag_active = True
        self.view.node_drag_last_activity_monotonic = 0.0
        self.assertTrue(self.view.is_node_drag_stale())

    def test_is_node_drag_stale_false_when_recent_activity_exists(self):
        self.view.node_drag_active = True
        self.view.node_drag_last_activity_monotonic = time.monotonic()
        self.assertFalse(self.view.is_node_drag_stale())

    def test_node_screen_geometry_falls_back_when_widget_size_raises(self):
        self.view.to_screen = lambda value: int(round(float(value) * 2.0))
        self.view.card_screen_width = lambda: 320
        self.view.card_screen_height = lambda: 160
        node = SimpleNamespace(id="n1", x=20, y=30)
        self.view.node_widgets = {"n1": _BrokenSizeWidget()}
        self.assertEqual(
            (40.0, 60.0, 320.0, 160.0),
            self.view.node_screen_geometry(node),
        )

    def test_stage_drag_begin_prefers_observed_stage_point_when_offsets_zero(self):
        self.view.STAGE_WIDTH = 4000
        self.view.STAGE_HEIGHT = 2400
        self.view.port_drag_active = False
        self.view.link_preview_source_id = None
        self.view.node_drag_active = False
        self.view.selected_node_ids = set()
        self.view.is_port_drag_stale = lambda: False
        self.view.reset_port_drag_state = lambda: None
        self.view.reset_node_drag_state = lambda: None
        self.view.gesture_stage_point = lambda _gesture: (312.0, 188.0)
        observed_points: list[tuple[int, int]] = []
        self.view.find_node_at_point = (
            lambda x, y, exclude_node_id=None: observed_points.append((x, y)) or None
        )
        gesture = _FakeDragGesture(object(), state=Gdk.ModifierType(0))
        self.view.on_stage_select_drag_begin(gesture, 0.0, 0.0)
        self.assertEqual([(312, 188)], observed_points)

    def test_output_handle_grab_radius_is_tight_without_hover(self):
        self.view.node_output_handle_local_anchor = lambda _node_id=None: (100.0, 50.0)
        self.view.hovered_port_node_id = None
        self.view.hovered_port_kind = None
        # 17px away from anchor should not trigger link-drag mode by default.
        self.assertFalse(self.view.is_output_handle_grab(117.0, 50.0, "n1"))

    def test_output_handle_grab_radius_expands_when_hovered(self):
        self.view.node_output_handle_local_anchor = lambda _node_id=None: (100.0, 50.0)
        self.view.hovered_port_node_id = "n1"
        self.view.hovered_port_kind = "out"
        # Same point becomes valid when the connector is explicitly hovered.
        self.assertTrue(self.view.is_output_handle_grab(117.0, 50.0, "n1"))

    def test_stage_drag_begin_starts_node_drag_fallback_when_hitting_node(self):
        self.view.STAGE_WIDTH = 4000
        self.view.STAGE_HEIGHT = 2400
        self.view.port_drag_active = False
        self.view.link_preview_source_id = None
        self.view.node_drag_active = False
        self.view.selected_node_id = None
        self.view.selected_node_ids = set()
        self.view.stage_drag_node_id = None
        self.view.stage_drag_origin = {}
        self.view.hovered_port_kind = None
        self.view.hovered_port_node_id = None
        self.view.suppress_stage_click_once = False
        self.view.is_port_drag_stale = lambda: False
        self.view.reset_port_drag_state = lambda: None
        self.view.reset_node_drag_state = lambda: None
        self.view.gesture_stage_point = lambda _gesture: None
        node = SimpleNamespace(id="n1", node_type="Action", x=180, y=240)
        self.view.find_node_at_point = lambda _x, _y, exclude_node_id=None: node
        self.view.node_screen_geometry = lambda _node: (180.0, 240.0, 320.0, 160.0)
        self.view.is_output_handle_grab = lambda _x, _y, _node_id=None: False
        link_drag_calls: list[tuple[str, float, float]] = []
        self.view.begin_output_link_drag = (
            lambda node_id, pointer_x=None, pointer_y=None: link_drag_calls.append(
                (node_id, pointer_x, pointer_y)
            )
        )
        drag_calls: list[dict] = []

        def _record_start_node_drag(node_id, **kwargs):
            drag_calls.append({"node_id": node_id, **kwargs})

        self.view.start_node_drag = _record_start_node_drag
        gesture = _FakeDragGesture(object(), state=Gdk.ModifierType(0))
        self.view.on_stage_select_drag_begin(gesture, 220.0, 320.0)

        self.assertTrue(gesture.claimed)
        self.assertEqual("n1", self.view.stage_drag_node_id)
        self.assertEqual({"start_x": 220.0, "start_y": 320.0}, self.view.stage_drag_origin)
        self.assertEqual([], link_drag_calls)
        self.assertEqual(1, len(drag_calls))
        self.assertEqual("n1", drag_calls[0]["node_id"])
        self.assertEqual("stage", drag_calls[0]["drag_driver"])
        self.assertEqual(220.0, drag_calls[0]["pointer_stage_x"])
        self.assertEqual(320.0, drag_calls[0]["pointer_stage_y"])

    def test_stage_drag_begin_prefers_link_drag_when_output_handle_is_hit(self):
        self.view.STAGE_WIDTH = 4000
        self.view.STAGE_HEIGHT = 2400
        self.view.port_drag_active = False
        self.view.link_preview_source_id = None
        self.view.node_drag_active = False
        self.view.selected_node_id = None
        self.view.selected_node_ids = set()
        self.view.stage_drag_node_id = None
        self.view.stage_drag_origin = {}
        self.view.hovered_port_kind = None
        self.view.hovered_port_node_id = None
        self.view.suppress_stage_click_once = False
        self.view.is_port_drag_stale = lambda: False
        self.view.reset_port_drag_state = lambda: None
        self.view.reset_node_drag_state = lambda: None
        self.view.gesture_stage_point = lambda _gesture: None
        node = SimpleNamespace(id="n1", node_type="Action", x=180, y=240)
        self.view.find_node_at_point = lambda _x, _y, exclude_node_id=None: node
        self.view.node_screen_geometry = lambda _node: (180.0, 240.0, 320.0, 160.0)
        self.view.is_output_handle_grab = lambda _x, _y, _node_id=None: True
        link_drag_calls: list[tuple[str, float, float]] = []
        self.view.begin_output_link_drag = (
            lambda node_id, pointer_x=None, pointer_y=None: link_drag_calls.append(
                (node_id, pointer_x, pointer_y)
            )
        )
        drag_calls: list[dict] = []
        self.view.start_node_drag = lambda node_id, **kwargs: drag_calls.append(
            {"node_id": node_id, **kwargs}
        )
        gesture = _FakeDragGesture(object(), state=Gdk.ModifierType(0))
        self.view.on_stage_select_drag_begin(gesture, 220.0, 320.0)

        self.assertTrue(gesture.claimed)
        self.assertTrue(self.view.suppress_stage_click_once)
        self.assertIsNone(self.view.stage_drag_node_id)
        self.assertEqual({}, self.view.stage_drag_origin)
        self.assertEqual([("n1", 220.0, 320.0)], link_drag_calls)
        self.assertEqual([], drag_calls)

    def test_stage_drag_begin_normalizes_pointer_to_stage_for_scrolled_canvas(self):
        self.view.STAGE_WIDTH = 4000
        self.view.STAGE_HEIGHT = 2400
        self.view.port_drag_active = False
        self.view.link_preview_source_id = None
        self.view.node_drag_active = False
        self.view.selected_node_id = None
        self.view.selected_node_ids = set()
        self.view.stage_drag_node_id = None
        self.view.stage_drag_origin = {}
        self.view.hovered_port_kind = None
        self.view.hovered_port_node_id = None
        self.view.suppress_stage_click_once = False
        self.view.canvas_scroll = _FakeScroll(100, 50)
        self.view.is_port_drag_stale = lambda: False
        self.view.reset_port_drag_state = lambda: None
        self.view.reset_node_drag_state = lambda: None
        self.view.gesture_stage_point = lambda _gesture: None
        node = SimpleNamespace(id="n1", node_type="Action", x=300, y=340)
        self.view.find_node_at_point = lambda _x, _y, exclude_node_id=None: node
        self.view.node_screen_geometry = lambda _node: (300.0, 340.0, 320.0, 160.0)
        self.view.is_output_handle_grab = lambda _x, _y, _node_id=None: False
        drag_calls: list[dict] = []
        self.view.start_node_drag = lambda node_id, **kwargs: drag_calls.append(
            {"node_id": node_id, **kwargs}
        )

        gesture = _FakeDragGesture(object(), state=Gdk.ModifierType(0))
        self.view.on_stage_select_drag_begin(gesture, 220.0, 320.0)

        self.assertTrue(gesture.claimed)
        self.assertEqual("n1", self.view.stage_drag_node_id)
        self.assertEqual({"start_x": 320.0, "start_y": 370.0}, self.view.stage_drag_origin)
        self.assertEqual(1, len(drag_calls))
        self.assertEqual(320.0, drag_calls[0]["pointer_stage_x"])
        self.assertEqual(370.0, drag_calls[0]["pointer_stage_y"])

    def test_stage_drag_begin_retries_node_hit_with_observed_stage_point(self):
        self.view.STAGE_WIDTH = 4000
        self.view.STAGE_HEIGHT = 2400
        self.view.port_drag_active = False
        self.view.link_preview_source_id = None
        self.view.node_drag_active = False
        self.view.selected_node_id = None
        self.view.selected_node_ids = set()
        self.view.stage_drag_node_id = None
        self.view.stage_drag_origin = {}
        self.view.hovered_port_kind = None
        self.view.hovered_port_node_id = None
        self.view.suppress_stage_click_once = False
        self.view.is_port_drag_stale = lambda: False
        self.view.reset_port_drag_state = lambda: None
        self.view.reset_node_drag_state = lambda: None
        self.view.gesture_stage_point = lambda _gesture: (520.0, 420.0)
        node = SimpleNamespace(id="n1", node_type="Action", x=480, y=360)
        hit_attempts: list[tuple[int, int]] = []

        def _find_node(x, y, exclude_node_id=None):
            del exclude_node_id
            hit_attempts.append((int(x), int(y)))
            if int(x) == 520 and int(y) == 420:
                return node
            return None

        self.view.find_node_at_point = _find_node
        self.view.node_screen_geometry = lambda _node: (480.0, 360.0, 320.0, 160.0)
        self.view.is_output_handle_grab = lambda _x, _y, _node_id=None: False
        drag_calls: list[dict] = []
        self.view.start_node_drag = lambda node_id, **kwargs: drag_calls.append(
            {"node_id": node_id, **kwargs}
        )

        gesture = _FakeDragGesture(object(), state=Gdk.ModifierType(0))
        self.view.on_stage_select_drag_begin(gesture, 220.0, 320.0)

        self.assertEqual([(220, 320), (520, 420)], hit_attempts[:2])
        self.assertTrue(gesture.claimed)
        self.assertEqual("n1", self.view.stage_drag_node_id)
        self.assertEqual({"start_x": 520.0, "start_y": 420.0}, self.view.stage_drag_origin)
        self.assertEqual(1, len(drag_calls))
        self.assertEqual(520.0, drag_calls[0]["pointer_stage_x"])
        self.assertEqual(420.0, drag_calls[0]["pointer_stage_y"])

    def test_stage_drag_begin_does_not_interrupt_active_node_owned_drag(self):
        self.view.STAGE_WIDTH = 4000
        self.view.STAGE_HEIGHT = 2400
        self.view.port_drag_active = False
        self.view.link_preview_source_id = None
        self.view.node_drag_active = True
        self.view.node_drag_driver = "node"
        self.view.drag_origin = {"node_id": "n1"}
        self.view.stage_drag_node_id = None
        self.view.stage_drag_origin = {}
        self.view.is_port_drag_stale = lambda: False
        self.view.is_node_drag_stale = lambda: False
        self.view.reset_port_drag_state = lambda: None
        reset_calls: list[bool] = []
        self.view.reset_node_drag_state = lambda: reset_calls.append(True)
        self.view.gesture_stage_point = lambda _gesture: None
        self.view.find_node_at_point = lambda *_args, **_kwargs: None

        gesture = _FakeDragGesture(object(), state=Gdk.ModifierType(0))
        self.view.on_stage_select_drag_begin(gesture, 220.0, 320.0)

        self.assertEqual([], reset_calls)
        self.assertFalse(gesture.claimed)
        self.assertIsNone(self.view.stage_drag_node_id)

    def test_find_node_at_point_uses_viewport_offset_candidate_when_needed(self):
        node = CanvasNode(
            id="n1",
            name="Node",
            node_type="Action",
            detail="",
            summary="",
            x=300,
            y=200,
        )
        self.view.nodes = [node]
        self.view.node_widgets = {}
        self.view.to_screen = lambda value: int(round(value))
        self.view.card_screen_width = lambda: 120
        self.view.card_screen_height = lambda: 80
        self.view.canvas_scroll = _FakeScroll(100, 50)

        # Viewport-relative pointer coordinates should still hit node bounds by
        # trying stage candidates with scroll-offset adjustments.
        hit = self.view.find_node_at_point(200, 150)
        self.assertIsNotNone(hit)
        self.assertEqual("n1", hit.id if hit else "")

    def test_stage_pointer_motion_fallback_updates_stalled_node_drag(self):
        self.view.port_drag_active = False
        self.view.node_drag_active = True
        self.view.node_drag_driver = "node"
        self.view.drag_origin = {"node_id": "n1"}
        self.view.node_drag_last_activity_monotonic = time.monotonic() - 0.2
        self.view.is_node_drag_stale = lambda: False
        calls: list[tuple[str, float, float, bool]] = []

        self.view.apply_active_node_drag_position = (
            lambda node_id, x, y, live_snap_enabled=False: calls.append(
                (node_id, float(x), float(y), bool(live_snap_enabled))
            )
        )
        controller = _FakeDragGesture(object(), state=Gdk.ModifierType.BUTTON1_MASK)
        self.view.on_stage_pointer_motion(controller, 440.0, 320.0)

        self.assertEqual(1, len(calls))
        self.assertEqual(("n1", 440.0, 320.0, False), calls[0])

    def test_stage_pointer_motion_resolves_scrolled_stage_coordinates(self):
        self.view.port_drag_active = False
        self.view.node_drag_active = True
        self.view.node_drag_driver = "stage"
        self.view.drag_origin = {
            "node_id": "n1",
            "pointer_stage_x": 340.0,
            "pointer_stage_y": 280.0,
        }
        self.view.node_drag_last_pointer_stage = (340.0, 280.0)
        self.view.canvas_scroll = _FakeScroll(100, 50)
        self.view.is_node_drag_stale = lambda: False
        calls: list[tuple[str, float, float, bool]] = []

        self.view.apply_active_node_drag_position = (
            lambda node_id, x, y, live_snap_enabled=False: calls.append(
                (node_id, float(x), float(y), bool(live_snap_enabled))
            )
        )
        controller = _FakeDragGesture(object(), state=Gdk.ModifierType.BUTTON1_MASK)
        self.view.on_stage_pointer_motion(controller, 260.0, 230.0)

        self.assertEqual(1, len(calls))
        # Raw motion (260,230) is viewport-like; with scroll offsets this should map
        # to stage coordinates near previous drag pointer (360,280).
        self.assertEqual(("n1", 360.0, 280.0, False), calls[0])

    def test_stage_pointer_motion_does_not_duplicate_recent_node_drag_updates(self):
        self.view.port_drag_active = False
        self.view.node_drag_active = True
        self.view.node_drag_driver = "node"
        self.view.drag_origin = {"node_id": "n1"}
        self.view.node_drag_last_activity_monotonic = time.monotonic()
        self.view.is_node_drag_stale = lambda: False
        calls: list[tuple[str, float, float, bool]] = []

        self.view.apply_active_node_drag_position = (
            lambda node_id, x, y, live_snap_enabled=False: calls.append(
                (node_id, float(x), float(y), bool(live_snap_enabled))
            )
        )
        controller = _FakeDragGesture(object(), state=Gdk.ModifierType.BUTTON1_MASK)
        self.view.on_stage_pointer_motion(controller, 440.0, 320.0)

        self.assertEqual([], calls)

    def test_stage_pointer_motion_resets_node_drag_when_primary_button_released(self):
        self.view.port_drag_active = False
        self.view.node_drag_active = True
        self.view.node_drag_driver = "node"
        self.view.drag_origin = {"node_id": "n1"}
        self.view.node_drag_last_activity_monotonic = time.monotonic() - 0.2
        self.view.is_node_drag_stale = lambda: False
        calls: list[tuple[str, float, float, bool]] = []
        reset_calls: list[bool] = []
        self.view.apply_active_node_drag_position = (
            lambda node_id, x, y, live_snap_enabled=False: calls.append(
                (node_id, float(x), float(y), bool(live_snap_enabled))
            )
        )
        self.view.reset_node_drag_state = lambda: reset_calls.append(True)

        controller = _FakeDragGesture(object(), state=Gdk.ModifierType(0))
        self.view.on_stage_pointer_motion(controller, 440.0, 320.0)

        self.assertEqual([True], reset_calls)
        self.assertEqual([], calls)

    def test_stage_pointer_motion_resets_port_drag_when_primary_button_released(self):
        self.view.port_drag_active = True
        self.view.link_preview_source_id = "n1"
        self.view.pending_link_source_id = "n1"
        self.view.node_drag_active = False
        reset_calls: list[bool] = []
        self.view.reset_port_drag_state = lambda: reset_calls.append(True)
        self.view.active_drag_target = lambda *_args, **_kwargs: None
        self.view.update_link_preview_position = lambda *_args, **_kwargs: None
        self.view.set_link_hover_target = lambda *_args, **_kwargs: None

        controller = _FakeDragGesture(object(), state=Gdk.ModifierType(0))
        self.view.on_stage_pointer_motion(controller, 440.0, 320.0)

        self.assertEqual([True], reset_calls)

    def test_canvas_stage_click_retries_hit_with_observed_stage_point(self):
        self.view.STAGE_WIDTH = 4000
        self.view.STAGE_HEIGHT = 2400
        self.view.grab_focus = lambda: None
        self.view.card_screen_width = lambda: 320
        self.view.is_node_drag_stale = lambda: False
        self.view.reset_node_drag_state = lambda: None
        self.view.port_drag_active = False
        self.view.link_preview_source_id = None
        self.view.pending_link_source_id = None
        self.view.suppress_stage_click_once = False
        self.view.selected_node_id = None
        self.view.selected_node_ids = set()
        self.view.port_drag_origin = {}
        self.view.gesture_stage_point = lambda _gesture: (640.0, 480.0)
        node = SimpleNamespace(id="n1", name="Node One")
        hit_attempts: list[tuple[int, int]] = []

        def _find_node(x, y, exclude_node_id=None):
            del exclude_node_id
            hit_attempts.append((int(x), int(y)))
            if int(x) == 640 and int(y) == 480:
                return node
            return None

        self.view.find_node_at_point = _find_node
        self.view.set_single_selection = lambda node_id: (
            setattr(self.view, "selected_node_id", node_id),
            setattr(self.view, "selected_node_ids", {node_id}),
        )
        self.view.apply_selection_set_visual_state = lambda *_args, **_kwargs: None
        inspector_calls: list[str] = []
        self.view.update_inspector = lambda selected: inspector_calls.append(str(selected.id))
        self.view.clear_inspector = lambda: inspector_calls.append("clear")
        self.view.update_control_state = lambda: None
        self.view.link_layer = SimpleNamespace(queue_draw=lambda: None)
        self.view.valid_link_target_at = lambda *_args, **_kwargs: None
        self.view.finalize_link_preview_at = lambda *_args, **_kwargs: None

        gesture = _FakeGesture(object())
        self.view.on_canvas_stage_clicked(gesture, 1, 120.0, 160.0)

        self.assertEqual([(640, 480)], hit_attempts[:1])
        self.assertEqual("n1", self.view.selected_node_id)
        self.assertEqual({"n1"}, self.view.selected_node_ids)
        self.assertEqual(["n1"], inspector_calls)

    def test_default_auto_link_source_prefers_selected_trigger_when_tail_open(self):
        trigger = CanvasNode(
            id="t1",
            name="Trigger",
            node_type="Trigger",
            detail="",
            summary="",
            x=80,
            y=80,
        )
        action = CanvasNode(
            id="a1",
            name="Action",
            node_type="Action",
            detail="",
            summary="",
            x=320,
            y=80,
        )
        self.view.nodes = [trigger, action]
        self.view.edges = []
        self.view.selected_node_id = "t1"
        self.assertEqual("t1", self.view.default_auto_link_source_id("Action"))

    def test_default_auto_link_source_ignores_for_incoming_trigger(self):
        trigger = CanvasNode(
            id="t1",
            name="Trigger",
            node_type="Trigger",
            detail="",
            summary="",
            x=80,
            y=80,
        )
        self.view.nodes = [trigger]
        self.view.edges = []
        self.view.selected_node_id = "t1"
        self.assertEqual("", self.view.default_auto_link_source_id("Trigger"))

    def test_default_auto_link_source_falls_back_to_open_non_trigger_tail(self):
        trigger = CanvasNode(
            id="t1",
            name="Trigger",
            node_type="Trigger",
            detail="",
            summary="",
            x=80,
            y=80,
        )
        action_one = CanvasNode(
            id="a1",
            name="Action 1",
            node_type="Action",
            detail="",
            summary="",
            x=320,
            y=80,
        )
        action_two = CanvasNode(
            id="a2",
            name="Action 2",
            node_type="Action",
            detail="",
            summary="",
            x=560,
            y=80,
        )
        self.view.nodes = [trigger, action_one, action_two]
        self.view.edges = [
            CanvasEdge(id="e1", source_node_id="t1", target_node_id="a1", condition=""),
        ]
        self.view.selected_node_id = "t1"
        self.assertEqual("a2", self.view.default_auto_link_source_id("Action"))


if __name__ == "__main__":
    unittest.main()
