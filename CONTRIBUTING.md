# Contributing to DossierDock

Thank you for helping make container delivery easier to review and operate.

## Local setup

```bash
git clone https://github.com/shasanksingh/dossierdock.git
cd dossierdock
python -m venv .venv
.venv\Scripts\activate  # Windows PowerShell
python -m pip install -e .
python -m unittest discover -s tests -v
```

On macOS or Linux, activate with `source .venv/bin/activate`.

## Contribution guidelines

- Keep runtime dependencies optional wherever possible.
- Never print, write, or commit credentials.
- Add a test for every behavior change.
- Keep cloud-provider support behind dedicated adapters.
- Run the full test command before opening a pull request.

## Reporting security issues

Do not open a public issue for a potential vulnerability. Follow [SECURITY.md](SECURITY.md) instead.
