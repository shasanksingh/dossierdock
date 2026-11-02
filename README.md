# DossierDock

`dossierdock` is a provider-neutral **release-evidence CLI for containerized AI services**. It does more than produce a build command: it checks the service contract, image hardening signals, health-route evidence, and local-secret exposure, then writes a portable release dossier for a pull request, CI artifact, or operational handover.

The first release deliberately does **not** own cloud credentials or send a deployment anywhere. That makes it a safe foundation for teams that want a clear, reviewable path from an AI service to a container build and CI pipeline. Remote targets (SSH, AWS, and other providers) can be added as opt-in adapters rather than built into every command.

## Why it is different

Most deployment tools build or deploy an image. DossierDock focuses on answering: **“What evidence says this AI service is ready to release?”**

It produces a small, provider-neutral `release-dossier.json` containing only safe metadata: the service contract, health endpoint, manifest hash, blockers, review items, and checks performed. No API key, connection string, or secret value is collected or written to the dossier.

This makes the tool useful before choosing AWS, Docker, Kubernetes, a VM, or another delivery target.

## What it does today

- Creates a portable `dossierdock.toml` manifest.
- Checks the Dockerfile, health endpoint, AI-service metadata, and deployment metadata before CI runs.
- Reviews root-container execution, missing Docker health checks, and common credential files that are not ignored.
- Looks for evidence that the declared HTTP health route exists in application source.
- Writes a portable release dossier suitable for CI artifacts and release reviews.
- Prints a deterministic build and release plan as text or JSON.
- Writes a GitHub Actions workflow that tests the project and builds an immutable container image.
- Uses only the Python standard library at runtime.

## Quick start

```bash
python -m pip install -e .
dossierdock init --path .
dossierdock doctor
dossierdock plan
dossierdock dossier
dossierdock workflow github --output .github/workflows/dossierdock.yml
```

Add a health endpoint to your API, then build it locally:

```bash
docker build -t my-ai-service:dev .
docker run --rm -p 8000:8000 my-ai-service:dev
```

## Manifest

```toml
[app]
name = "my-ai-service"
dockerfile = "Dockerfile"
context = "."
image = "my-ai-service"
healthcheck = "/health"
port = 8000

[deployment]
target = "local"
environment = "development"

[ai]
service_kind = "ai-api"
model_provider = "external"
telemetry = "open-telemetry"
```

The manifest contains no credentials. Keep provider credentials in the CI platform's secret store and add a target adapter only when you are ready to deploy.

## Commands

| Command | Purpose |
| --- | --- |
| `dossierdock init` | Create a starter manifest. |
| `dossierdock doctor` | Report release-readiness issues and checks. |
| `dossierdock plan` | Show the container build and health-check plan. |
| `dossierdock dossier` | Write reviewable, secret-free release evidence as JSON. |
| `dossierdock workflow github` | Create a GitHub Actions CI workflow. |

## Release dossier

```bash
dossierdock dossier --output .dossierdock/release-dossier.json
```

The dossier records the application, declared AI-service contract, health URL, SHA-256 fingerprint of the manifest, blockers, and review items. Generated GitHub Actions workflows upload it as a build artifact so the release evidence stays with the exact CI run that built the image.

## Project layout

```text
src/dossierdock/     CLI, config loader, checks, workflow templates
tests/               Standard-library unit tests
examples/            A deployable manifest example
docs/                Architecture and contributor notes
```

## Roadmap

1. Docker build and local smoke-test adapters.
2. OpenTelemetry-compatible deployment annotations and release events.
3. SSH release adapter with rollback and health verification.
4. Separate AWS deployment adapter and learning guide.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). This project is released under the [MIT License](LICENSE).
