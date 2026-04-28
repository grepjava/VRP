"""CUDA stream lifecycle management for concurrent cuOpt execution."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from queue import Empty, Queue
from threading import Lock

from core.gpu_memory import SolverError

logger = logging.getLogger(__name__)


class CUDAStreamManager:
    """Manages CUDA streams for concurrent cuOpt execution"""

    def __init__(self, num_streams: int):
        self.num_streams = num_streams
        self.streams = []
        self.stream_lock = Lock()
        self.available_streams = Queue()

        try:
            import cupy as cp
            for i in range(num_streams):
                stream = cp.cuda.Stream(non_blocking=True)
                self.streams.append(stream)
                self.available_streams.put(i)
            logger.info(f"✅ Created {num_streams} CUDA streams")
        except Exception as e:
            logger.warning(f"⚠️ Failed to create CUDA streams: {e}")
            for i in range(num_streams):
                self.streams.append(None)
                self.available_streams.put(i)

    @contextmanager
    def get_stream(self, timeout: float = 30.0):
        """Get an available CUDA stream"""
        try:
            stream_id = self.available_streams.get(timeout=timeout)
            stream = self.streams[stream_id]
            try:
                yield stream_id, stream
            finally:
                self.available_streams.put(stream_id)
        except Empty:
            raise SolverError(f"No CUDA streams available within {timeout}s")

    def synchronize_all(self):
        """Synchronize all CUDA streams"""
        try:
            import cupy as cp
            for stream in self.streams:
                if stream is not None:
                    stream.synchronize()
        except Exception as e:
            logger.warning(f"Failed to synchronize CUDA streams: {e}")
