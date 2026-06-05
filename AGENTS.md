# FRIK — Agent & Contributor Conventions

This file governs how AI agents and human contributors work in this repo.
It extends the global agent behavior rules. Where this file conflicts with
global rules, **this file wins** for project-specific concerns.

---

## Test-Driven Development is mandatory

Every change to production code must follow this sequence — no exceptions:

```
1. Write a failing test that describes the desired behavior.
2. Confirm the test fails for the right reason.
3. Write the minimum code to make the test pass.
4. Refactor. Keep tests green.
```

**Never write production code first.** If you find yourself writing
implementation before a test exists, stop and write the test.

### What this means in practice

- **New feature?** Write `tests/` first. The test file (and failing assertion)
  must exist in the same commit as, or before, the implementation.
- **Bug fix?** Write a regression test that reproduces the bug before touching
  the source. The test must fail on the unfixed code.
- **Refactor?** Tests must already exist and must remain green throughout. If
  they don't exist yet, write them before refactoring.
- **API endpoint?** Write `tests/api/test_app.py` cases (TestClient) before
  the route handler.

### Test placement

```
tests/
  sources/      # unit tests for frik/sources/*.py
  api/          # FastAPI TestClient tests for frik/api/app.py
  conftest.py   # shared fixtures — add here, don't duplicate
  test_cli.py   # CLI argument parsing and command dispatch
```

Mirror the source layout exactly. A new file `frik/sources/foo.py` gets
`tests/sources/test_foo.py`.

### Coverage gate

CI enforces **70% branch coverage minimum** (see `pyproject.toml`
`[tool.pytest.ini_options]`). TDD will naturally keep you above this. If
coverage drops, the PR does not merge.

The 70% floor is intentionally conservative for early development. Raise it
as the codebase matures — do not lower it.

### Regression tests are not optional

Any test that proves a specific bug existed and was fixed must be kept
forever. Mark it with a comment explaining what it guards against:

```python
def test_hourly_wage_multiplier_is_2080():
    # Regression: multiplier was accidentally set to 2000 in early draft,
    # causing ~3.8% undercount on all hourly-wage annual conversions.
    assert UNIT_TO_ANNUAL["Hour"] == 2080.0
```

---

## Project layout

```
frik/
  api/          # FastAPI app, Pydantic models
  sources/      # data source modules (bls.py, h1b.py, postings.py, ...)
  cli.py        # CLI entry point — thin wrappers over sources/
  __main__.py   # enables python -m frik
tests/
pyproject.toml  # deps, pytest config, coverage config, ruff config
.github/
  workflows/
    tests.yml   # CI: lint (ruff) + pytest on Python 3.11 and 3.12
.pre-commit-config.yaml  # ruff only (tests run in CI, not pre-commit)
```

### Adding a new data source

1. Create `frik/sources/<name>.py`.
2. Create `tests/sources/test_<name>.py` with failing tests **first**.
3. Implement until tests pass.
4. Add API endpoint(s) in `frik/api/app.py` with corresponding
   `tests/api/test_app.py` cases.
5. Add CLI subcommand in `frik/cli.py`.
6. Add `tests/test_cli.py` cases for the new subcommand.

---

## Dependencies

- Runtime deps go in `[project] dependencies` in `pyproject.toml`.
- API-only deps go in `[project.optional-dependencies] api`.
- Dev/test deps go in `[project.optional-dependencies] dev`.
- Do not add a dependency that duplicates functionality already in stdlib
  or an existing dep. Check before adding.

## Code style

Enforced by `ruff` (see `[tool.ruff]` in `pyproject.toml`). Run before
committing:

```bash
ruff check . --fix
ruff format .
```

Pre-commit hook runs this automatically if installed:
```bash
pip install pre-commit
pre-commit install
```

## Running tests

```bash
# Full suite with coverage report
pytest

# Fast (no coverage) during active TDD loop
pytest --no-cov -x -q

# Single file
pytest tests/sources/test_bls.py -v
```
