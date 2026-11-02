"""Join owned work before propagating cancellation to its owner."""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def await_owned(future):
    """Wait without transferring cancellation; the caller must join on exit."""
    await asyncio.wait({future})
    return future.result()


async def await_settled(future, *, propagate_cancel: bool = True):
    """Repeated owner cancellation must not abandon an in-progress cleanup.

    The caller owns ``future``. Cancellation is deferred, never suppressed;
    exceptions from settled work are retrieved even when cancellation wins.
    """
    interrupted = None
    while not future.done():
        try:
            await asyncio.wait({future})
        except asyncio.CancelledError as exc:
            interrupted = exc
        except BaseException:
            break
    if interrupted is not None and propagate_cancel:
        if not future.cancelled():
            failure = future.exception()
            if failure is not None:
                raise failure from interrupted
        raise interrupted
    return future.result()


async def cancel_and_wait(tasks, *, reason: str):
    tasks = tuple(tasks)
    for task in tasks:
        if not task.done() and not task.cancelling():
            task.cancel(reason)
    if tasks:
        results = await await_settled(asyncio.gather(*tasks, return_exceptions=True))
        for task, result in zip(tasks, results):
            if isinstance(result, Exception):
                logger.error("owned task ended with an error during %s: %s", reason, task.get_name(), exc_info=result)
        return results
    return []


async def run_blocking(function, *args, **kwargs):
    """Keep a thread owned until it really exits; cancelling its Future is insufficient."""
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs), name="owned-blocking-call")
    try:
        return await await_owned(task)
    except asyncio.CancelledError:
        await await_settled(asyncio.gather(task, return_exceptions=True), propagate_cancel=False)
        raise
