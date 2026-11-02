"""Versioned templates for generated CI workflows."""

from __future__ import annotations


GITHUB_ACTIONS_WORKFLOW = """name: ModelShip CI

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
      - name: Install project and ModelShip
        run: |
          python -m pip install --upgrade pip
          python -m pip install modelship-cli
          if [ -f requirements.txt ]; then python -m pip install -r requirements.txt; fi
      - name: Run project tests
        run: |
          if [ -d tests ]; then python -m unittest discover -s tests -v; fi
      - name: Validate container delivery inputs
        run: modelship doctor
      - name: Build immutable container image
        run: docker build --tag ${{ github.repository }}:${{ github.sha }} .
"""
