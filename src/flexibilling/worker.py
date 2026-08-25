"""Generic async worker for draining pending usage records."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from time import perf_counter

from .exceptions import BillingError, InsufficientFundsError, NoBillableUsageError
from .metrics import (
    BILLING_WORKER_BATCH_SIZE,
    BILLING_WORKER_CYCLE_DURATION,
    BILLING_WORKER_CYCLES,
    BILLING_WORKER_LAST_SUCCESS,
    BILLING_WORKER_RECORDS,
)
from .models import enum_value
from .ports import BillingRepository, TransactionFactory
from .service import BillingService


@dataclass(frozen=True, slots=True)
class WorkerCycleResult:
    fetched: int
    processed: int
    skipped: int
    failed: int
    retried: int


class BillingWorker:
    """Poll and process a backend's pending usage queue.

    The transaction factory should yield a unit of work whose context manager
    commits or rolls back according to the host backend's policy.
    """

    def __init__(
        self,
        service: BillingService,
        repo: BillingRepository,
        transaction_factory: TransactionFactory,
        *,
        poll_interval: float = 2.0,
        batch_size: int = 50,
    ) -> None:
        self._service = service
        self._repo = repo
        self._transaction_factory = transaction_factory
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._running = False

    async def run_once(self) -> WorkerCycleResult:
        """Run one queue-drain cycle and return explicit outcome counts."""

        started_at = perf_counter()
        processed = skipped = failed = retried = 0
        async with self._transaction_factory() as session:
            records = list(await self._repo.get_pending_records(self._batch_size, session=session))
            BILLING_WORKER_BATCH_SIZE.set(len(records))
            for record in records:
                service = enum_value(record.service)
                try:
                    await self._service.process_record(record, session=session)
                    processed += 1
                    BILLING_WORKER_RECORDS.labels(service, "processed").inc()
                except NoBillableUsageError:
                    skipped += 1
                    BILLING_WORKER_RECORDS.labels(service, "skipped_no_billable_usage").inc()
                    if record.id is not None:
                        await self._repo.mark_record_skipped(record.id, session=session)
                except (InsufficientFundsError, BillingError) as error:
                    failed += 1
                    outcome = (
                        "failed_insufficient_funds"
                        if isinstance(error, InsufficientFundsError)
                        else "failed_billing"
                    )
                    BILLING_WORKER_RECORDS.labels(service, outcome).inc()
                    if record.id is not None:
                        await self._repo.mark_record_failed(record.id, str(error), session=session)
                except Exception:
                    retried += 1
                    BILLING_WORKER_RECORDS.labels(service, "failed_unexpected").inc()

        result = WorkerCycleResult(
            fetched=len(records),
            processed=processed,
            skipped=skipped,
            failed=failed,
            retried=retried,
        )
        BILLING_WORKER_CYCLES.labels("empty" if not result.fetched else "completed").inc()
        BILLING_WORKER_LAST_SUCCESS.set(time.time())
        BILLING_WORKER_CYCLE_DURATION.observe(perf_counter() - started_at)
        return result

    async def run(self) -> None:
        """Poll until ``stop`` is called."""

        self._running = True
        while self._running:
            result = await self.run_once()
            if result.fetched < self._batch_size:
                await asyncio.sleep(self._poll_interval)

    def stop(self) -> None:
        self._running = False
