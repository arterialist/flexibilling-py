# Development and releases

## Local setup

Install `uv`, clone the repository, and run:

```bash
uv sync --group testing --group lint --group dev
uv run pre-commit install
```

Run the full local check set:

```bash
uv run pytest
uv run ruff check src tests
uv run ruff format src tests --check
uv run pyright --project pyproject.toml src/flexibilling
python -m build
uv run mkdocs build --strict
```

Serve the docs locally while editing:

```bash
uv run mkdocs serve
```

Then open `http://127.0.0.1:8000/`.

## Repository layout

```text
src/flexibilling/              core package
src/flexibilling/adapters/     in-memory, Redis, and SQLAlchemy adapters
src/flexibilling/engine/       rating, waterfall, and gatekeeper logic
src/flexibilling/integrations/ optional framework integrations
tests/                          unit and adapter tests
examples/                       runnable generic examples
docs/                           MkDocs documentation
```

## CI and documentation publishing

Pull requests and pushes to `main` run lint, type checks, tests on Python 3.11,
3.12, and 3.13, and a source/wheel build. The documentation workflow builds and
publishes the MkDocs site to GitHub Pages when docs or `mkdocs.yml` changes.

## PyPI release

1. Update `src/flexibilling/__about__.py` and the relevant section in
   `CHANGELOG.md`.
2. Run the full local check set and inspect `dist/`.
3. Create and push an annotated tag:

   ```bash
   git tag -a v0.1.0 -m "Release v0.1.0"
   git push origin main --follow-tags
   ```

4. Create a published GitHub Release for the tag.

The release workflow publishes to PyPI through OIDC trusted publishing. Before
the first release, configure the `arterialist/flexibilling` GitHub repository as
a PyPI trusted publisher and create the `pypi` GitHub environment. No long-lived
PyPI API token is needed.
