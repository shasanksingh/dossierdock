# ModelShip architecture

```text
modelship.toml
      |
      v
Configuration validation ----> structured diagnostics (`modelship doctor`)
      |                                      |
      v                                      v
Build and release plan (`modelship plan`)   developer / CI feedback
      |
      v
GitHub Actions generator (`modelship workflow github`)
      |
      v
tests -> container build -> selected registry / deployment adapter
```

## Design principles

### Provider-neutral core

The core package has no cloud SDK dependency and contains no remote credentials. A user can validate an application and generate CI locally before deciding whether the final destination is a Docker host, a container registry, or a cloud platform.

### Secure defaults

The manifest identifies build inputs and a health endpoint only. Secrets belong in the CI platform's secret store. Workflow generation uses immutable commit image tags rather than mutable release names.

### Adapter boundary

Remote deployment will be implemented behind adapters. Each adapter will declare its required credentials, perform a health check after deployment, and expose rollback behavior. This separation means AWS learning and deployment support can be introduced without making the base CLI AWS-specific.

## Initial extension points

- `local`: validates a local Docker build contract.
- `ssh`: planned release adapter with signed artifact transfer, health check, and rollback.
- `aws`: planned separately as a learning project and later as an optional adapter.
- `observability`: planned hooks for logs, metrics, traces, and release status.
