"""
src/main.py

Entry point. Loads config/settings.yaml, reads the API key from the
OPENROUTER_API_KEY environment variable (never from CLI args), wires up
storage + engine + metrics, and runs the harvest with graceful shutdown
on SIGINT/SIGTERM.

Usage:
    export OPENROUTER_API_KEY="sk-..."
    python -m src.main --queries queries.txt --config config/settings.yaml
"""

import argparse
import asyncio
import os
import signal
import sys
from pathlib import Path

import yaml

from src.engine.circuit_breaker import CircuitBreaker
from src.engine.scheduler import AdaptiveSemaphore
from src.engine.crawler import Crawler
from src.storage.database import Database
from src.storage.writer import AtomicJsonlWriter
from src.utils.logger import get_logger
from src.utils.metrics import MetricsTracker


def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_args():
    parser = argparse.ArgumentParser(description="Saira Harvest Engine")
    parser.add_argument("--queries", required=True, help="Path to newline-delimited queries file")
    parser.add_argument("--config", default="config/settings.yaml", help="Path to settings.yaml")
    parser.add_argument("--models", default=None,
                         help="Comma-separated model list, overrides config file")
    # Intentionally NO --api-key flag: secrets must come from the environment.
    return parser.parse_args()


async def run(args):
    config = load_config(args.config)

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY environment variable is not set.", file=sys.stderr)
        print("Run: export OPENROUTER_API_KEY='sk-...'", file=sys.stderr)
        sys.exit(1)

    logger = get_logger(
        "saira_harvest",
        level=config["logging"]["level"],
        json_output=config["logging"]["json"],
        log_file=config["logging"].get("file"),
    )

    queries_path = Path(args.queries)
    if not queries_path.exists():
        logger.error("Queries file not found: %s", queries_path)
        sys.exit(1)
    queries = [line for line in queries_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    models = args.models.split(",") if args.models else config["models"]

    db = Database(config["storage"]["db_path"])
    await db.connect()

    writer = AtomicJsonlWriter(
        config["storage"]["output_path"],
        batch_size=config["storage"]["batch_size"],
        flush_interval_seconds=config["storage"]["flush_interval_seconds"],
    )
    writer_task = asyncio.create_task(writer.run())

    metrics = MetricsTracker(pricing=config.get("pricing", {}))

    circuit_breaker = CircuitBreaker(
        failure_threshold=config["circuit_breaker"]["failure_threshold"],
        open_seconds=config["circuit_breaker"]["open_seconds"],
        half_open_max_probes=config["circuit_breaker"]["half_open_max_probes"],
    )

    scheduler = AdaptiveSemaphore(
        start=config["concurrency"]["start_workers"],
        minimum=config["concurrency"]["min_workers"],
        maximum=config["concurrency"]["max_workers"],
        scale_up_streak=config["concurrency"]["scale_up_success_streak"],
        scale_down_streak=config["concurrency"]["scale_down_failure_streak"],
    )

    crawler = Crawler(
        base_url=config["api"]["base_url"],
        headers={"Authorization": f"Bearer {api_key}"},
        models=models,
        db=db,
        writer=writer,
        metrics=metrics,
        logger=logger,
        max_retries=config["api"]["max_retries"],
        retry_base_delay=config["api"]["retry_base_delay"],
        request_timeout=config["api"]["timeout_seconds"],
        connect_timeout=config["api"]["connect_timeout_seconds"],
        circuit_breaker=circuit_breaker,
        scheduler=scheduler,
    )

    stop_event = asyncio.Event()

    def _handle_signal():
        logger.warning("Shutdown signal received, finishing in-flight work...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            pass  # signal handlers unsupported on this platform (e.g. Windows)

    logger.info("Starting harvest: %d queries x %d models, workers=%d",
                len(queries), len(models), config["concurrency"]["start_workers"])

    try:
        harvest_task = asyncio.create_task(
            crawler.run(queries, num_workers=config["concurrency"]["start_workers"])
        )
        stop_task = asyncio.create_task(stop_event.wait())
        done, pending = await asyncio.wait(
            {harvest_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if stop_task in done and not harvest_task.done():
            harvest_task.cancel()
            try:
                await harvest_task
            except asyncio.CancelledError:
                pass
    finally:
        await writer.put(None)
        await writer_task
        summary = await db.cost_summary()
        for row in summary:
            logger.info("Cost summary: %s", row)
        await db.close()
        logger.info("Shutdown complete.")


def main():
    args = parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
