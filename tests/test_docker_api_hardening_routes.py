import ast
import unittest
from pathlib import Path


def parse_module(relative_path: str) -> ast.Module:
    repo_root = Path(__file__).resolve().parents[1]
    source_path = repo_root / relative_path
    source = source_path.read_text(encoding="utf-8")
    return ast.parse(source, filename=str(source_path))


def collect_route_paths(tree: ast.Module) -> set[str]:
    paths: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not isinstance(func, ast.Attribute):
                continue
            if func.attr not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not decorator.args:
                continue
            first = decorator.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                paths.add(first.value)
    return paths


class DockerApiHardeningRouteTests(unittest.TestCase):
    def test_api_exposes_backup_restore_and_observability_routes(self):
        tree = parse_module("docker/api/app/main.py")
        paths = collect_route_paths(tree)
        expected = {
            "/api/v1/observability/summary",
            "/api/v1/observability/runs",
            "/api/v1/admin/backup",
            "/api/v1/admin/restore",
        }
        self.assertTrue(expected.issubset(paths), f"Missing API routes: {sorted(expected - paths)}")

    def test_store_exposes_backup_restore_methods(self):
        tree = parse_module("docker/api/app/storage.py")
        class_defs = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "JsonStore"]
        self.assertTrue(class_defs, "JsonStore class not found in storage.py")
        methods = {
            node.name
            for node in class_defs[0].body
            if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("export_backup", methods)
        self.assertIn("restore_backup", methods)
        self.assertIn("default_backup_path", methods)


if __name__ == "__main__":
    unittest.main()
