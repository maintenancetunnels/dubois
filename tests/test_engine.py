import inspect
import sys

from dubois import engine


def test_async_runner_uses_a_worker_pool_not_one_task_per_probe():
    source = inspect.getsource(engine._run_async_coro)
    assert "create_task(worker())" in source
    assert "asyncio.create_task(_fetch_one" not in source


def test_windows_loop_policy_avoids_select_fd_cap():
    source = inspect.getsource(engine._ensure_windows_loop_policy)
    assert "WindowsSelectorEventLoopPolicy" not in source
    if sys.platform == "win32":
        assert "WindowsProactorEventLoopPolicy" in source
