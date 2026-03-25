import asyncio
import os
import time
import logging

logger = logging.getLogger("itsbo.audit")

class AuditLogger:
    """
    Dedicated logging engine to provide proofs of transmission (audit trails).
    Logs packet structures, sizes, and sequences to prove simulation realism.
    Writes strictly to logs/audit_{session_id}.log.
    Uses asyncio.Queue for non-blocking I/O at high throughputs.
    """
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self._queue = asyncio.Queue()
        self._running = False
        self._writer_task = None
        self._open_files = {}

    def start(self):
        self._running = True
        self._writer_task = asyncio.create_task(self._writer_loop())

    async def stop(self):
        self._running = False
        if self._writer_task:
            await self._queue.put(None)
            await self._writer_task
        for f in self._open_files.values():
            try:
                f.close()
            except Exception:
                pass
        self._open_files.clear()

    def log_event(self, session_id: str, direction: str, event_type: str, details: dict):
        """
        Fire-and-forget logging.
        direction: "UL" or "DL"
        event_type: "Rx_Data", "Tx_MCM", "Tx_Video", "Rx_ACK", etc.
        """
        if not self._running:
            return
            
        timestamp = time.time()
        self._queue.put_nowait((timestamp, session_id, direction, event_type, details))

    async def _writer_loop(self):
        try:
            while self._running or not self._queue.empty():
                item = await self._queue.get()
                if item is None:
                    self._queue.task_done()
                    break
                    
                timestamp, session_id, direction, event_type, details = item
                
                if session_id not in self._open_files:
                    filepath = os.path.join(self.log_dir, f"audit_{session_id}.log")
                    self._open_files[session_id] = open(filepath, "a", encoding="utf-8")
                
                f = self._open_files[session_id]
                det_str = ", ".join(f"{k}={v}" for k, v in details.items())
                log_line = f"[{timestamp:.6f}] [{direction}] [{event_type}] {det_str}\n"
                f.write(log_line)
                
                # To avoid disk bottleneck on every packet, flush only when queue is empty
                if self._queue.empty():
                    f.flush()
                    
                self._queue.task_done()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if self._running:
                logger.error(f"Audit writer error: {e}")

audit_logger = AuditLogger()
