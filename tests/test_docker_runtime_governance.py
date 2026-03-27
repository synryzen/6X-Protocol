import importlib.util
import os
import unittest
from pathlib import Path


def load_runtime_governance_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "docker" / "api" / "app" / "runtime_governance.py"
    spec = importlib.util.spec_from_file_location("docker_api_runtime_governance", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load docker/api/app/runtime_governance.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module


class RuntimeGovernanceTests(unittest.TestCase):
    def setUp(self):
        self.module = load_runtime_governance_module()
        self.keys = [
            "SIXPX_IMAGE_TAG",
            "SIXPX_EXPECTED_IMAGE_TAG",
            "SIXPX_IMAGE_DIGEST",
            "SIXPX_RELEASE_CHANNEL",
            "SIXPX_BUILD_SHA",
            "SIXPX_BUILD_DATE",
            "SIXPX_EXPECTED_API_VERSION",
            "SIXPX_EXPECTED_RELEASE_CHANNEL",
            "SIXPX_EXPECTED_BUILD_SHA",
            "SIXPX_MIN_API_VERSION",
            "SIXPX_MAX_API_VERSION",
            "SIXPX_ENFORCE_DIGEST_FOR_GA",
            "SIXPX_ENFORCE_TAG_API_MATCH",
            "SIXPX_MIN_STORE_SCHEMA_VERSION",
            "SIXPX_MAX_STORE_SCHEMA_VERSION",
        ]
        self.original_env = {key: os.environ.get(key) for key in self.keys}

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_governance_status_ok_when_tag_and_build_are_present(self):
        os.environ["SIXPX_IMAGE_TAG"] = "local-dev"
        os.environ["SIXPX_EXPECTED_IMAGE_TAG"] = "local-dev"
        os.environ["SIXPX_RELEASE_CHANNEL"] = "beta"
        os.environ["SIXPX_BUILD_SHA"] = "abc1234"
        snapshot = self.module.runtime_governance_snapshot(
            api_version="0.5.0-preview",
            store_schema_version=3,
        )
        self.assertEqual("ok", snapshot["status"])
        self.assertEqual(0, int(snapshot["issue_count"]))

    def test_governance_flags_image_tag_mismatch(self):
        os.environ["SIXPX_IMAGE_TAG"] = "v0.1.9"
        os.environ["SIXPX_EXPECTED_IMAGE_TAG"] = "v0.2.0"
        os.environ["SIXPX_BUILD_SHA"] = "abc1234"
        snapshot = self.module.runtime_governance_snapshot(
            api_version="0.5.0-preview",
            store_schema_version=3,
        )
        self.assertEqual("error", snapshot["status"])
        codes = {item.get("code") for item in snapshot.get("issues", [])}
        self.assertIn("image_tag_mismatch", codes)

    def test_governance_warns_when_image_tag_missing(self):
        os.environ["SIXPX_IMAGE_TAG"] = ""
        os.environ["SIXPX_BUILD_SHA"] = "abc1234"
        snapshot = self.module.runtime_governance_snapshot(
            api_version="0.5.0-preview",
            store_schema_version=3,
        )
        self.assertEqual("warn", snapshot["status"])
        codes = {item.get("code") for item in snapshot.get("issues", [])}
        self.assertIn("image_tag_missing", codes)

    def test_governance_requires_release_semver_tag_and_digest_for_ga(self):
        os.environ["SIXPX_RELEASE_CHANNEL"] = "ga"
        os.environ["SIXPX_IMAGE_TAG"] = "local-dev"
        os.environ["SIXPX_BUILD_SHA"] = "abc1234"
        os.environ["SIXPX_IMAGE_DIGEST"] = ""
        snapshot = self.module.runtime_governance_snapshot(
            api_version="0.5.0",
            store_schema_version=3,
        )
        self.assertEqual("error", snapshot["status"])
        codes = {item.get("code") for item in snapshot.get("issues", [])}
        self.assertIn("image_digest_missing", codes)
        self.assertIn("image_tag_not_release_semver", codes)

    def test_governance_can_enforce_expected_release_channel_and_build_sha(self):
        os.environ["SIXPX_IMAGE_TAG"] = "v0.5.0"
        os.environ["SIXPX_RELEASE_CHANNEL"] = "beta"
        os.environ["SIXPX_EXPECTED_RELEASE_CHANNEL"] = "ga"
        os.environ["SIXPX_BUILD_SHA"] = "abc1234"
        os.environ["SIXPX_EXPECTED_BUILD_SHA"] = "deadbeef"
        snapshot = self.module.runtime_governance_snapshot(
            api_version="0.5.0",
            store_schema_version=3,
        )
        self.assertEqual("error", snapshot["status"])
        codes = {item.get("code") for item in snapshot.get("issues", [])}
        self.assertIn("release_channel_mismatch", codes)
        self.assertIn("build_sha_mismatch", codes)


if __name__ == "__main__":
    unittest.main()
