# Contributing to FlexiBilling

## Development setup

Install `uv`, clone the repository, and create the development environment with:

```bash
uv sync --group testing --group lint --group dev
uv run pre-commit install
```

The optional integrations can be smoke-tested in the same environment:

```bash
uv run --extra fastapi python -c "import fastapi; print(fastapi.__version__)"
uv run --extra redis python -c "import redis; print(redis.__version__)"
uv run --extra sqlalchemy python -c "import sqlalchemy; print(sqlalchemy.__version__)"
```

## Checks before opening a pull request

```bash
uv run pytest
uv run ruff check src tests examples
uv run ruff format src tests examples --check
uv run pyright --project pyproject.toml src/flexibilling
uv build
uv run mkdocs build --strict
```

Keep the core package independent from framework, ORM, cache, and payment SDK
dependencies. Add integrations under `src/flexibilling/adapters` or
`src/flexibilling/integrations` and declare their dependencies as optional
extras.

Documentation examples must use generic customers, services, assets, and usage
records. Keep application-specific vocabulary out of the package and its
reference adapters.

## Documentation

The documentation site is built with MkDocs Material:

```bash
uv run mkdocs serve
uv run mkdocs build --strict
```

Pages live under `docs/`. Update the navigation in `mkdocs.yml` when adding a
page. The `docs.yaml` workflow deploys the site to GitHub Pages on pushes to
`main` that change documentation or the MkDocs configuration.

## Releasing

1. Update `src/flexibilling/__about__.py` and the release section in
   `CHANGELOG.md`.
2. Run the full check list above and review the generated `dist/` artifacts.
3. Commit the release and create an annotated version tag, for example:

   ```bash
   git tag -a v0.1.0 -m "Release v0.1.0"
   git push origin main --follow-tags
   ```

4. Create a published GitHub Release for the tag. The release workflow builds
   the wheel and source distribution and publishes them to PyPI through OIDC
   trusted publishing.

Before the first release, configure the PyPI trusted publisher for the
`arterialist/flexibilling` repository and the `pypi` GitHub environment. No
long-lived PyPI API token is required.
