from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from dossierdock.config import ConfigError, load_config


VALID_MANIFEST = """[app]
name = "analytics-api"
dockerfile = "Dockerfile"
context = "."
image = "analytics-api"
healthcheck = "/health"
port = 8000

[deployment]
target = "local"
environment = "test"
"""


class ConfigTests(unittest.TestCase):
    def _manifest(self, text: str) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "dossierdock.toml"
        path.write_text(text, encoding="utf-8")
        return path

    def test_loads_valid_manifest(self) -> None:
        config = load_config(self._manifest(VALID_MANIFEST))
        self.assertEqual(config.name, "analytics-api")
        self.assertEqual(config.port, 8000)
        self.assertEqual(config.healthcheck, "/health")

    def test_rejects_healthcheck_without_leading_slash(self) -> None:
        manifest = self._manifest(VALID_MANIFEST.replace('healthcheck = "/health"', 'healthcheck = "health"'))
        with self.assertRaisesRegex(ConfigError, "must start"):
            load_config(manifest)

    def test_rejects_invalid_port(self) -> None:
        manifest = self._manifest(VALID_MANIFEST.replace("port = 8000", "port = 0"))
        with self.assertRaisesRegex(ConfigError, "between 1 and 65535"):
            load_config(manifest)
