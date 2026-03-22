import asyncio
import threading

_loop = None
_loop_lock = threading.Lock()


def run_async(coroutine):
    global _loop

    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_loop)

    return _loop.run_until_complete(coroutine)
