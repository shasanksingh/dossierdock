"""Versioned templates for generated CI workflows."""

from __future__ import annotations


GITHUB_ACTIONS_WORKFLOW = """name: DossierDock CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: \"3.11\"
      - name: Install project and DossierDock
        run: |
          python -m pip install --upgrade pip
          python -m pip install dossierdock
          if [ -f requirements.txt ]; then python -m pip install -r requirements.txt; fi
      - name: Run project tests
        run: |
          if [ -d tests ]; then python -m unittest discover -s tests -v; fi
      - name: Validate container delivery inputs
        run: dossierdock doctor
      - name: Create release-evidence dossier
        run: dossierdock dossier --force
      - name: Preserve release evidence
        uses: actions/upload-artifact@v4
        with:
          name: dossierdock-release-dossier
          path: .dossierdock/release-dossier.json
      - name: Build immutable container image
        run: docker build --tag ${{ github.repository }}:${{ github.sha }} .
"""
