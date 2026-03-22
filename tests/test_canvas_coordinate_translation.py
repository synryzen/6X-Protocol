import unittest
from types import SimpleNamespace
import time

from src.views.canvas_view import CanvasView


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


class _BrokenSizeWidget:
    def get_allocated_width(self):
        raise RuntimeError("width unavailable")

    def get_allocated_height(self):
        raise RuntimeError("height unavailable")


class CanvasCoordinateTranslationTests(unittest.TestCase):
    def setUp(self):
        # Exercise the helper directly without bootstrapping full GTK view state.
        self.view = CanvasView.__new__(CanvasView)

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


if __name__ == "__main__":
    unittest.main()
