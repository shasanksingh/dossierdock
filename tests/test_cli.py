from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from modelship.cli import main
from modelship.doctor import run_doctor


class CliTests(unittest.TestCase):
    def _call(self, arguments: list[str]) -> tuple[int, str, str]:
        output, errors = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = main(arguments)
        return code, output.getvalue(), errors.getvalue()

    def test_init_creates_manifest_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            code, output, _ = self._call(["init", "--path", str(root)])
            self.assertEqual(code, 0)
            self.assertIn("Created", output)
            self.assertTrue((root / "modelship.toml").is_file())

            code, _, errors = self._call(["init", "--path", str(root)])
            self.assertEqual(code, 2)
            self.assertIn("Refusing to overwrite", errors)

    def test_doctor_and_plan_accept_valid_container_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._call(["init", "--path", str(root)])
            (root / "Dockerfile").write_text("FROM python:3.11-slim\n", encoding="utf-8")
            report = run_doctor(root / "modelship.toml")
            self.assertTrue(report.healthy)

            code, output, _ = self._call(["plan", "--config", str(root / "modelship.toml")])
            self.assertEqual(code, 0)
            self.assertIn("docker build", output)
            self.assertIn("http://localhost:8000/health", output)

    def test_workflow_generation_is_explicit_and_repeat_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / ".github" / "workflows" / "modelship.yml"
            code, _, _ = self._call(["workflow", "github", "--output", str(destination)])
            self.assertEqual(code, 0)
            content = destination.read_text(encoding="utf-8")
            self.assertIn("docker build", content)
            self.assertIn("modelship doctor", content)

            code, _, errors = self._call(["workflow", "github", "--output", str(destination)])
            self.assertEqual(code, 2)
            self.assertIn("Refusing to overwrite", errors)
