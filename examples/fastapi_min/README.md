# FastAPI example

Install the optional integration, then run the example from the repository root:

```bash
uv sync --group testing --group lint --group dev
uv run --extra fastapi uvicorn examples.fastapi_min.app:app --reload
```

Open <http://127.0.0.1:8000/docs> or query the health endpoint:

```bash
curl -s http://127.0.0.1:8000/health
```
