"""
src/engine/crawler.py

Producer/consumer engine:
  - A single producer fills a work queue with (query, model) pairs.
  - N worker coroutines pull from the queue, respect the circuit breaker
    and adaptive concurrency limit, call the API with retries, and push
    successful results to the storage writer + metrics tracker.

API key handling: the key is read once by main.py from the environment and
passed in via `headers`. It is never logged, never written to disk, and
never accepted as a CLI argument.
"""

import asyncio
import hashlib
import random
import time
import httpx

from src.engine.circuit_breaker import CircuitBreaker
from src.engine.scheduler import AdaptiveSemaphore
from src.storage.database import Database
from src.storage.writer import AtomicJsonlWriter
from src.utils.metrics import MetricsTracker


def query_hash(query: str, model: str) -> str:
    return hashlib.sha256(f"{query}|{model}".encode("utf-8")).hexdigest()[:16]


class Crawler:
    def __init__(self, *, base_url: str, headers: dict, models: list[str],
                 db: Database, writer: AtomicJsonlWriter,
                 metrics: MetricsTracker, logger,
                 max_retries: int = 5, retry_base_delay: float = 2.0,
                 request_timeout: float = 60.0, connect_timeout: float = 10.0,
                 circuit_breaker: CircuitBreaker | None = None,
                 scheduler: AdaptiveSemaphore | None = None):
        self.base_url = base_url
        self.headers = headers
        self.models = models
        self.db = db
        self.writer = writer
        self.metrics = metrics
        self.logger = logger
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.timeout = httpx.Timeout(request_timeout, connect=connect_timeout)

        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.scheduler = scheduler

        self.queue: asyncio.Queue = asyncio.Queue()

    async def enqueue_all(self, queries: list[str]):
        for q in queries:
            for m in self.models:
                await self.queue.put((q, m))

    async def _call_api(self, client: httpx.AsyncClient, query: str, model: str):
        """Single API call attempt with retry/backoff. Returns response_json or None."""
        for attempt in range(self.max_retries):
            try:
                resp = await client.post(
                    self.base_url,
                    json={"model": model, "messages": [{"role": "user", "content": query}]},
                    timeout=self.timeout,
                )

                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code in (429, 500, 502, 503, 504):
                    delay = (2 ** attempt) + random.random()
                    self.logger.warning(
                        "Retryable status %s for model=%s attempt=%s, sleeping %.1fs",
                        resp.status_code, model, attempt, delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                # Non-retryable (e.g. 400/401/404): stop trying this call.
                self.logger.error("Fatal status %s for model=%s: %s",
                                   resp.status_code, model, resp.text[:300])
                return None

            except (httpx.TimeoutException, httpx.TransportError) as e:
                delay = (2 ** attempt) + random.random()
                self.logger.warning("Network error for model=%s attempt=%s: %s, sleeping %.1fs",
                                     model, attempt, e, delay)
                await asyncio.sleep(delay)

        return None

    async def worker(self, client: httpx.AsyncClient, worker_id: int = 0):
        while True:
            item = await self.queue.get()
            if item is None:
                self.queue.task_done()
                break

            query, model = item
            try:
                await self._process_one(client, query, model)
            except Exception:
                self.logger.exception("Unhandled error processing item worker=%s model=%s",
                                       worker_id, model)
            finally:
                self.queue.task_done()

    async def _process_one(self, client: httpx.AsyncClient, query: str, model: str):
        q_hash = query_hash(query, model)

        if await self.db.is_done(q_hash):
            return

        if not await self.circuit_breaker.allow_request(model):
            # Circuit is open for this model; requeue for a later pass
            # instead of dropping the work item.
            await self.queue.put((query, model))
            await asyncio.sleep(1.0)
            return

        if self.scheduler:
            await self.scheduler.acquire()

        try:
            response_json = await self._call_api(client, query, model)
        finally:
            if self.scheduler:
                self.scheduler.release()

        if response_json is None:
            await self.circuit_breaker.record_failure(model)
            if self.scheduler:
                await self.scheduler.report_failure()
            return

        await self.circuit_breaker.record_success(model)
        if self.scheduler:
            await self.scheduler.report_success()

        choice = (response_json.get("choices") or [{}])[0].get("message", {})
        record = {
            "query": query,
            "model": model,
            "query_hash": q_hash,
            "content": choice.get("content", ""),
            "timestamp": time.time(),
        }
        await self.writer.put(record)
        await self.db.mark_done(q_hash, model, record["timestamp"])

        usage_record = self.metrics.compute(model, response_json)
        await self.db.record_usage(usage_record)

    async def run(self, queries: list[str], num_workers: int):
        await self.enqueue_all(queries)

        limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
        async with httpx.AsyncClient(limits=limits, headers=self.headers) as client:
            workers = [
                asyncio.create_task(self.worker(client, worker_id=i))
                for i in range(num_workers)
            ]
            await self.queue.join()

            # Signal shutdown
            for _ in workers:
                await self.queue.put(None)
            await asyncio.gather(*workers, return_exceptions=True)
