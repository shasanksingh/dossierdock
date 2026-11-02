"""Portable release-evidence generation for AI services."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Any

from modelship.doctor import DoctorReport


DOSSIER_SCHEMA_VERSION = "1.0"


def build_dossier(report: DoctorReport) -> dict[str, Any]:
    """Build a shareable deployment dossier without reading or exposing secrets."""
    if report.config is None:
        return {
            "schema_version": DOSSIER_SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "release_readiness": "blocked",
            "blockers": [check.as_dict() for check in report.checks if check.status == "error"],
            "review_items": [check.as_dict() for check in report.checks if check.status == "warning"],
        }

    config = report.config
    digest = hashlib.sha256(config.config_path.read_bytes()).hexdigest()
    blockers = [check.as_dict() for check in report.checks if check.status == "error"]
    review_items = [check.as_dict() for check in report.checks if check.status == "warning"]
    return {
        "schema_version": DOSSIER_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_readiness": "ready" if not blockers and not review_items else "review" if not blockers else "blocked",
        "application": {
            "name": config.name,
            "image": config.image,
            "environment": config.environment,
            "target": config.target,
            "healthcheck": f"http://localhost:{config.port}{config.healthcheck}",
        },
        "ai_service_contract": {
            "service_kind": config.service_kind,
            "model_provider": config.model_provider,
            "telemetry": config.telemetry,
        },
        "manifest_sha256": digest,
        "blockers": blockers,
        "review_items": review_items,
        "checks": [check.as_dict() for check in report.checks],
    }
