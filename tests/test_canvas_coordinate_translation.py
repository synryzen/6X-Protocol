import unittest

from src.views.canvas_view import CanvasView


class _FakeWidget:
    def __init__(self, translated):
        self._translated = translated

    def translate_coordinates(self, _dest, _x, _y):
        return self._translated


class _FailingWidget:
    def translate_coordinates(self, _dest, _x, _y):
        raise RuntimeError("boom")


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

    def test_translate_widget_coordinates_handles_errors(self):
        source = _FailingWidget()
        result = self.view.translate_widget_coordinates(source, object(), 1.0, 2.0)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
