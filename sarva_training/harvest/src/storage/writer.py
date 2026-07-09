"""
src/storage/writer.py

Atomic JSONL writer. Buffers records and flushes them as a batch, calling
os.fsync() after each flush so a crash/kill can lose at most one
in-flight batch, not the whole output file. Runs as its own consumer task
reading off an asyncio.Queue, decoupled from the API-calling workers.
"""

import asyncio
import json
import os
from pathlib import Path


class AtomicJsonlWriter:
    def __init__(self, out_path: str, batch_size: int = 20,
                 flush_interval_seconds: float = 2.0):
        self.out_path = Path(out_path)
        self.batch_size = batch_size
        self.flush_interval_seconds = flush_interval_seconds
        self._queue: asyncio.Queue = asyncio.Queue()
        self._file = None
        self._buffer: list[str] = []
        self._stop = False

    async def open(self):
        self._file = self.out_path.open("a", encoding="utf-8")

    async def close(self):
        await self._flush()
        if self._file:
            self._file.close()

    async def put(self, record: dict):
        await self._queue.put(record)

    async def _flush(self):
        if not self._buffer:
            return
        self._file.write("".join(self._buffer))
        self._file.flush()
        os.fsync(self._file.fileno())
        self._buffer.clear()

    async def run(self):
        """Consumer loop: call as an asyncio task. Put `None` to stop."""
        await self.open()
        try:
            while True:
                try:
                    item = await asyncio.wait_for(
                        self._queue.get(), timeout=self.flush_interval_seconds
                    )
                except asyncio.TimeoutError:
                    await self._flush()
                    if self._stop and self._queue.empty():
                        break
                    continue

                if item is None:
                    self._stop = True
                    self._queue.task_done()
                    if self._queue.empty():
                        await self._flush()
                        break
                    continue

                self._buffer.append(json.dumps(item, ensure_ascii=False) + "\n")
                if len(self._buffer) >= self.batch_size:
                    await self._flush()
                self._queue.task_done()
        finally:
            await self._flush()
            if self._file:
                self._file.close()
