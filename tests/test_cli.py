from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from dossierdock.cli import main
from dossierdock.config import load_config
from dossierdock.doctor import run_doctor


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
            self.assertTrue((root / "dossierdock.toml").is_file())

            code, _, errors = self._call(["init", "--path", str(root)])
            self.assertEqual(code, 2)
            self.assertIn("Refusing to overwrite", errors)

    def test_init_template_loads_as_a_multi_agent_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            code, _, _ = self._call(["init", "--path", str(root)])
            self.assertEqual(code, 0)
            config = load_config(root / "dossierdock.toml")
            self.assertEqual(config.replicas, 1)
            self.assertEqual(config.agents[0].name, "request-router")

    def test_doctor_and_plan_accept_valid_container_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._call(["init", "--path", str(root)])
            (root / "Dockerfile").write_text("FROM python:3.11-slim\n", encoding="utf-8")
            report = run_doctor(root / "dossierdock.toml")
            self.assertTrue(report.healthy)

            code, output, _ = self._call(["plan", "--config", str(root / "dossierdock.toml")])
            self.assertEqual(code, 0)
            self.assertIn("docker build", output)
            self.assertIn("http://localhost:8000/health", output)

    def test_workflow_generation_is_explicit_and_repeat_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / ".github" / "workflows" / "dossierdock.yml"
            code, _, _ = self._call(["workflow", "github", "--output", str(destination)])
            self.assertEqual(code, 0)
            content = destination.read_text(encoding="utf-8")
            self.assertIn("docker build", content)
            self.assertIn("dossierdock doctor", content)

            code, _, errors = self._call(["workflow", "github", "--output", str(destination)])
            self.assertEqual(code, 2)
            self.assertIn("Refusing to overwrite", errors)

    def test_agent_graph_and_manifests_are_secret_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._call(["init", "--path", str(root)])
            manifest = root / "dossierdock.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "required_env = []",
                    "required_env = [\"MODEL_API_KEY\"]",
                )
                + """

[[agents]]
name = "planner"
role = "Plans the requested task"
depends_on = []
healthcheck = "/health"
timeout_seconds = 20

[[agents]]
name = "executor"
role = "Executes the approved task"
depends_on = ["planner"]
healthcheck = "/health"
timeout_seconds = 30
""",
                encoding="utf-8",
            )
            code, output, _ = self._call(["graph", "--config", str(manifest)])
            self.assertEqual(code, 0)
            self.assertLess(output.index("planner"), output.index("executor"))

            kubernetes = root / "k8s.yaml"
            code, _, _ = self._call(
                ["manifest", "kubernetes", "--config", str(manifest), "--output", str(kubernetes)]
            )
            self.assertEqual(code, 0)
            content = kubernetes.read_text(encoding="utf-8")
            self.assertIn("secretKeyRef", content)
            self.assertIn("key: MODEL_API_KEY", content)
            self.assertNotIn("do-not-copy-this", content)

            compose = root / "compose.yml"
            code, _, _ = self._call(["manifest", "compose", "--config", str(manifest), "--output", str(compose)])
            self.assertEqual(code, 0)
            self.assertIn("${MODEL_API_KEY:?Set MODEL_API_KEY}", compose.read_text(encoding="utf-8"))

    def test_public_api_without_auth_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._call(["init", "--path", str(root)])
            manifest = root / "dossierdock.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace("public_api = false", "public_api = true"),
                encoding="utf-8",
            )
            report = run_doctor(manifest)
            access_policy = next(check for check in report.checks if check.name == "access_policy")
            self.assertEqual(access_policy.status, "error")

    def test_dossier_captures_release_evidence_without_secret_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._call(["init", "--path", str(root)])
            (root / "Dockerfile").write_text(
                "FROM python:3.12-slim\nUSER 10001\nHEALTHCHECK CMD python -c \"print('ok')\"\n",
                encoding="utf-8",
            )
            (root / ".dockerignore").write_text(".env\n", encoding="utf-8")
            (root / "app.py").write_text('@app.get("/health")\ndef health(): pass\n', encoding="utf-8")
            (root / "requirements.txt").write_text("fastapi==0.0.0\n", encoding="utf-8")
            manifest = root / "dossierdock.toml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8")
                .replace('readiness_path = "/ready"', 'readiness_path = "/health"')
                .replace('metrics_path = "/metrics"', 'metrics_path = "/health"'),
                encoding="utf-8",
            )
            destination = root / "evidence.json"

            code, output, _ = self._call(
                ["dossier", "--config", str(root / "dossierdock.toml"), "--output", str(destination)]
            )

            self.assertEqual(code, 0)
            self.assertIn("Created release dossier", output)
            dossier = json.loads(destination.read_text(encoding="utf-8"))
            self.assertEqual(dossier["release_readiness"], "ready")
            self.assertEqual(dossier["ai_service_contract"]["service_kind"], "ai-api")
            self.assertNotIn("do-not-copy-this", json.dumps(dossier))

    def test_unignored_env_file_blocks_release(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._call(["init", "--path", str(root)])
            (root / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
            (root / ".env").write_text("SERVICE_TOKEN=do-not-copy-this\n", encoding="utf-8")
            report = run_doctor(root / "dossierdock.toml")
            self.assertFalse(report.healthy)
            exposure = next(check for check in report.checks if check.name == "secret_exposure")
            self.assertEqual(exposure.status, "error")
            self.assertNotIn("do-not-copy-this", exposure.message)
