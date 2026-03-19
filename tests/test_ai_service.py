import unittest

from src.services.ai_service import AIService


class AIServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = AIService()

    def test_normalize_openai_base_url_handles_chat_completions_suffix(self):
        url = self.service._normalize_openai_base_url(
            "https://lm.example.com/v1/chat/completions"
        )
        self.assertEqual(url, "https://lm.example.com/v1")

    def test_normalize_openai_base_url_adds_v1_when_missing(self):
        url = self.service._normalize_openai_base_url("http://localhost:1234")
        self.assertEqual(url, "http://localhost:1234/v1")

    def test_sanitize_model_name_trims_completions_suffix(self):
        model = self.service._sanitize_model_name("nvidia/nemotron-3-nano/v1/chat/completions")
        self.assertEqual(model, "nvidia/nemotron-3-nano")

    def test_local_endpoint_candidates_for_remote_endpoint_keeps_endpoint_only(self):
        candidates = self.service._local_endpoint_candidates(
            backend="lm_studio",
            endpoint="https://lm.msidragon.com/v1/chat/completions",
        )
        self.assertEqual(candidates[0], "https://lm.msidragon.com/v1/chat/completions")
        self.assertEqual(len(candidates), 1)


if __name__ == "__main__":
    unittest.main()

