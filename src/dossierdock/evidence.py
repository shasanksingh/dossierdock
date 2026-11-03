"""Portable release-evidence generation for AI services."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any

from dossierdock.doctor import DoctorReport
from dossierdock.topology import agent_graph


DOSSIER_SCHEMA_VERSION = "2.0"


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
    deployment_contract = {
        "replicas": config.replicas,
        "public_api": config.public_api,
        "auth_mode": config.auth_mode,
        "resources": {"cpu": config.resource_cpu, "memory": config.resource_memory},
        "runtime": {
            "workers": config.workers,
            "shutdown_seconds": config.shutdown_seconds,
            "readiness_path": config.readiness_path,
            "liveness_path": config.liveness_path,
            "metrics_path": config.metrics_path,
        },
        "required_env": list(config.required_env),
    }
    contract_digest = hashlib.sha256(json.dumps(deployment_contract, sort_keys=True).encode("utf-8")).hexdigest()
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
            "model_ids": list(config.model_ids),
            "telemetry": config.telemetry,
            "traces_enabled": config.traces_enabled,
            "structured_logs": config.structured_logs,
            "agent_graph": agent_graph(config.agents),
        },
        "deployment_contract": deployment_contract,
        "manifest_sha256": digest,
        "deployment_contract_sha256": contract_digest,
        "blockers": blockers,
        "review_items": review_items,
        "checks": [check.as_dict() for check in report.checks],
    }
