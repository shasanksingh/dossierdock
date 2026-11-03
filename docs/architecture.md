# DossierDock architecture

```text
dossierdock.toml
      |
      v
Configuration validation ----> release-readiness diagnostics (`dossierdock doctor`)
      |                                      |
      v                                      v
Build and release plan (`dossierdock plan`)   developer / CI feedback
      |
      v
Secret-free release dossier (`dossierdock dossier`)
      |
      v
GitHub Actions generator (`dossierdock workflow github`)
      |
      v
tests -> dossier artifact -> container build -> selected registry / deployment adapter
```

## Design principles

### Provider-neutral core

The core package has no cloud SDK dependency and contains no remote credentials. A user can validate an application and generate CI locally before deciding whether the final destination is a Docker host, a container registry, or a cloud platform.

### Release evidence, not just deployment commands

DossierDock produces a portable release dossier that explains what was checked, the declared AI service contract, the build health endpoint, blockers, review items, and a SHA-256 fingerprint of the manifest. It intentionally contains no secrets or runtime tokens.

### Secure defaults

The manifest identifies build inputs and a health endpoint only. Secrets belong in the CI platform's secret store. Workflow generation uses immutable commit image tags rather than mutable release names.

### Adapter boundary

Remote deployment will be implemented behind adapters. Each adapter will declare its required credentials, perform a health check after deployment, and expose rollback behavior. This separation means AWS learning and deployment support can be introduced without making the base CLI AWS-specific.

## Initial extension points

- `local`: validates a local Docker build and release-evidence contract.
- `ssh`: planned release adapter with signed artifact transfer, health check, and rollback.
- `aws`: planned separately as a learning project and later as an optional adapter.
- `observability`: planned hooks for logs, metrics, traces, and release status.

## v0.2 deployment-contract flow

```text
dossierdock.toml
      |
      +--> Runtime contract (health, readiness, liveness, metrics, workers)
      +--> Deployment contract (target, replicas, resources, public access)
      +--> AI contract (provider metadata, model IDs, telemetry)
      +--> Agent graph (roles, dependencies, per-agent health and timeouts)
      |
      v
dossierdock doctor
      |
      +--> container and base-image checks
      +--> secret-reference and public-access policy checks
      +--> observability and dependency-lock checks
      +--> acyclic agent topology validation
      |
      +--> dossierdock graph ----------> deterministic startup runbook
      +--> dossierdock dossier --------> secret-free release evidence
      +--> dossierdock manifest compose -> Compose starter
      +--> dossierdock manifest kubernetes -> Deployment + Service
```

Generated manifests are deliberately review artifacts, not remote deployment commands. They reference secret names and keys but never create or expose secret values. Applying infrastructure remains explicit in the team's approved CI/CD process.
