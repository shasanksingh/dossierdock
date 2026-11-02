# ModelShip CLI

`modelship` is a provider-neutral command-line tool that prepares containerized AI services for repeatable delivery. It validates a small deployment manifest, inspects the Docker build inputs, produces a delivery plan, and generates a GitHub Actions workflow.

The first release deliberately does **not** own cloud credentials or send a deployment anywhere. That makes it a safe foundation for teams that want a clear, reviewable path from an AI service to a container build and CI pipeline. Remote targets (SSH, AWS, and other providers) can be added as opt-in adapters rather than built into every command.

## What it does today

- Creates a portable `modelship.toml` manifest.
- Checks the Dockerfile, health endpoint, and deployment metadata before CI runs.
- Prints a deterministic build and release plan as text or JSON.
- Writes a GitHub Actions workflow that tests the project and builds an immutable container image.
- Uses only the Python standard library at runtime.

## Quick start

```bash
python -m pip install -e .
modelship init --path .
modelship doctor
modelship plan
modelship workflow github --output .github/workflows/modelship.yml
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
```

The manifest contains no credentials. Keep provider credentials in the CI platform's secret store and add a target adapter only when you are ready to deploy.

## Commands

| Command | Purpose |
| --- | --- |
| `modelship init` | Create a starter manifest. |
| `modelship doctor` | Report deployment-readiness issues. |
| `modelship plan` | Show the container build and health-check plan. |
| `modelship workflow github` | Create a GitHub Actions CI workflow. |

## Project layout

```text
src/modelship/       CLI, config loader, checks, workflow templates
tests/               Standard-library unit tests
examples/            A deployable manifest example
docs/                Architecture and contributor notes
```

## Roadmap

1. Docker build and local smoke-test adapters.
2. SSH release adapter with rollback and health verification.
3. Separate AWS deployment adapter and learning guide.
4. Pluggable observability hooks for logs, metrics, and tracing.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). This project is released under the [MIT License](LICENSE).
