# Framework integrations

## FastAPI

Install the optional extra:

```bash
uv add "flexibilling[fastapi]"
```

The middleware reads `request.state.customer_id` and creates a request-scoped
billing context. A host authentication middleware should set that value first.
An optional `request.state.billing_reference_id` is copied into the context.

```python
from fastapi import FastAPI

from flexibilling.integrations.fastapi import BillingMiddleware, require_balance_http

app = FastAPI()
app.add_middleware(BillingMiddleware)


@app.get("/resource")
async def read_resource(customer_id: str):
    await require_balance_http(
        customer_id,
        ["units"],
        cache=cache,
        repository=repository,
    )
    return {"status": "ok"}
```

`json_response_factory` can be passed to `BillingDecorators` when route
decorators should return a JSON 402 response instead of raising a billing
exception.

## Decorators and sessions

```python
from flexibilling import BillingDecorators
from flexibilling.integrations.fastapi import json_response_factory

billing = BillingDecorators(
    service=service,
    usage_repository=usage_repository,
    response_factory=json_response_factory,
)


@billing.requires("units", min_amount=1)
async def run_operation(customer_id: str) -> dict[str, str]:
    return {"status": "complete"}
```

Use `billing.consumes("units", amount=1)` when an operation should be charged
before it runs and automatically refunded if it raises.

## Background worker

The worker drains pending usage records from the repository. Its transaction
factory should create a session with the host's commit/rollback policy:

```python
from flexibilling import BillingWorker

worker = BillingWorker(
    service,
    repository,
    transaction_factory=session_factory,
    poll_interval=2.0,
    batch_size=50,
)

await worker.run_once()
```

Use `await worker.run()` for a long-lived poller and call `worker.stop()` during
graceful shutdown.

## Prometheus metrics

Install the optional extra:

```bash
uv add "flexibilling[metrics]"
```

Importing `flexibilling.metrics` registers counters, histograms, and gauges with
the default Prometheus registry. The package catches metrics errors so telemetry
cannot block billing. Expose the registry through the host application's normal
metrics endpoint.
