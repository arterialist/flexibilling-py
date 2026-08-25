# Contributing to FlexiBilling

## Development setup

Install `uv`, clone the repository, and create the development environment:

```bash
uv sync --group testing --group lint --group dev
uv run pre-commit install
```

Check the optional integrations in the same environment:

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

Keep framework, ORM, cache, and payment SDKs out of the core package. Put an
integration in `src/flexibilling/adapters` or `src/flexibilling/integrations`
and declare its dependencies as an optional extra.

Use generic customers, services, assets, and usage records in documentation
examples. Do not include application-specific names in the package or its
adapters.

## Documentation

Build the documentation site with MkDocs Material:

```bash
uv run mkdocs serve
uv run mkdocs build --strict
```

Pages live under `docs/`. Update `mkdocs.yml` when adding a page. The
`docs.yaml` workflow publishes the site to GitHub Pages when a documentation
file or the MkDocs configuration changes on `main`.

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
