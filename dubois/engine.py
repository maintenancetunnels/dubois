"""Probe execution: thread-pool (sync) and asyncio (async)."""
from __future__ import annotations

import asyncio
import os
import sys
from concurrent.futures import Future
from dataclasses import dataclass, replace
from time import monotonic
from typing import Any

import requests
from requests_futures.sessions import FuturesSession

from dubois.classify import classify_http
from dubois.enrich import extract_profile
from dubois.notify import QueryNotify
from dubois.probe import (
    HEAD_FALLBACK_CODES,
    Probe,
    build_probe,
    random_absent_username,
)
from dubois.result import QueryResult, QueryStatus

DEFAULT_WORKERS_SYNC = 20
DEFAULT_WORKERS_ASYNC = 50
DEFAULT_TIMEOUT = 60  # library/test default; CLI uses 10
LIMIT_PER_HOST = 3


class DuboisFuturesSession(FuturesSession):
    def request(self, method, url, hooks=None, *args, **kwargs):
        if hooks is None:
            hooks = {}
        start = monotonic()

        def response_time(resp, *args, **kwargs):
            resp.elapsed = monotonic() - start

        try:
            if isinstance(hooks["response"], list):
                hooks["response"].insert(0, response_time)
            elif isinstance(hooks["response"], tuple):
                hooks["response"] = list(hooks["response"])
                hooks["response"].insert(0, response_time)
            else:
                hooks["response"] = [response_time, hooks["response"]]
        except KeyError:
            hooks["response"] = [response_time]

        return super().request(method, url, hooks=hooks, *args, **kwargs)


def get_response(request_future, error_type, social_network):
    """Wait on a requests future. Used by tests and the sync engine."""
    response = None
    error_context = "General Unknown Error"
    exception_text = None
    try:
        response = request_future.result()
        if response.status_code:
            error_context = None
    except requests.exceptions.HTTPError as errh:
        error_context = "HTTP Error"
        exception_text = str(errh)
    except requests.exceptions.ProxyError as errp:
        error_context = "Proxy Error"
        exception_text = str(errp)
    except requests.exceptions.ConnectionError as errc:
        error_context = "Error Connecting"
        exception_text = str(errc)
    except requests.exceptions.Timeout as errt:
        error_context = "Timeout Error"
        exception_text = str(errt)
    except requests.exceptions.RequestException as err:
        error_context = "Unknown Error"
        exception_text = str(err)
    except UnicodeError as err:
        error_context = "Encoding Error"
        exception_text = str(err)

    return response, error_context, exception_text


@dataclass
class ProbeOutcome:
    probe: Probe
    status_code: int | None
    text: str
    elapsed: float | None
    error_text: str | None
    exception_text: str | None = None


def _empty_site_result(net_info: dict, result: QueryResult) -> dict[str, Any]:
    return {
        "url_main": net_info.get("urlMain"),
        "url_user": result.site_url_user,
        "status": result,
        "http_status": "",
        "response_text": "",
        "profile": None,
    }


def _store_outcome(
    probe: Probe,
    net_info: dict,
    outcome: ProbeOutcome,
    *,
    keep_response_text: bool,
    dump_response: bool,
) -> dict[str, Any]:
    status, context = classify_http(
        status_code=outcome.status_code,
        text=outcome.text,
        error_type=probe.error_type,
        error_msg=probe.error_msg,
        error_code=probe.error_code,
        error_text=outcome.error_text,
        claimed_msg=probe.claimed_msg,
        claimed_code=probe.claimed_code,
    )
    if dump_response:
        _dump_response(probe, outcome, status)

    result = QueryResult(
        username=probe.username,
        site_name=probe.site_name,
        site_url_user=probe.url_user,
        status=status,
        query_time=outcome.elapsed,
        context=context,
    )
    http_status: Any = outcome.status_code if outcome.status_code is not None else "?"
    response_text = ""
    if keep_response_text or dump_response:
        try:
            response_text = outcome.text.encode("utf-8")
        except Exception:
            response_text = ""
    profile = None
    if status is QueryStatus.CLAIMED and outcome.text:
        facts = extract_profile(outcome.text, probe.url_user)
        if any((facts.title, facts.display_name, facts.bio, facts.image, facts.links)):
            profile = facts.as_dict()
            result.context = facts.one_line() or result.context
    return {
        "url_main": net_info.get("urlMain"),
        "url_user": probe.url_user,
        "status": result,
        "http_status": http_status,
        "response_text": response_text,
        "profile": profile,
    }


def _dump_response(probe: Probe, outcome: ProbeOutcome, query_status: QueryStatus) -> None:
    print("+++++++++++++++++++++")
    print(f"TARGET NAME   : {probe.site_name}")
    print(f"USERNAME      : {probe.username}")
    print(f"TARGET URL    : {probe.url_user}")
    print(f"TEST METHOD   : {probe.error_type}")
    if probe.error_code is not None:
        print(f"STATUS CODES  : {probe.error_code}")
    print("Results...")
    if outcome.status_code is not None:
        print(f"RESPONSE CODE : {outcome.status_code}")
    if probe.error_msg is not None:
        print(f"ERROR TEXT    : {probe.error_msg}")
    print(">>>>> BEGIN RESPONSE TEXT")
    print(outcome.text)
    print("<<<<< END RESPONSE TEXT")
    print("VERDICT       : " + str(query_status))
    print("+++++++++++++++++++++")


def _should_fallback_head(probe: Probe, outcome: ProbeOutcome) -> bool:
    if probe.method != "HEAD":
        return False
    if outcome.status_code is None:
        return False
    return outcome.status_code in HEAD_FALLBACK_CODES


def _proxy_dict(proxy: str | None) -> dict[str, str] | None:
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


def _is_socks_proxy(proxy: str | None) -> bool:
    if not proxy:
        return False
    return proxy.lower().startswith("socks")


def _elapsed_of(response) -> float | None:
    try:
        elapsed = response.elapsed
    except AttributeError:
        return None
    if elapsed is None:
        return None
    if hasattr(elapsed, "total_seconds"):
        return elapsed.total_seconds()
    try:
        return float(elapsed)
    except (TypeError, ValueError):
        return None


def _text_of(response) -> str:
    try:
        return response.text or ""
    except Exception:
        return ""


def _body_kwargs(payload: Any) -> dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, (dict, list)):
        return {"json": payload}
    return {"data": payload}


def _dispatch_sync(
    session: DuboisFuturesSession,
    probe: Probe,
    timeout: float,
    proxy: str | None,
) -> Future:
    kwargs: dict[str, Any] = {
        "url": probe.url_probe,
        "headers": probe.headers,
        "allow_redirects": probe.allow_redirects,
        "timeout": timeout,
        **_body_kwargs(probe.payload),
    }
    proxies = _proxy_dict(proxy)
    if proxies:
        kwargs["proxies"] = proxies
    method = probe.method.lower()
    request_fn = getattr(session, method)
    return request_fn(**kwargs)


def _outcome_from_future(probe: Probe, future: Future) -> ProbeOutcome:
    response, error_text, exception_text = get_response(
        request_future=future,
        error_type=probe.error_type,
        social_network=probe.site_name,
    )
    status_code = None
    text = ""
    elapsed = None
    if response is not None:
        try:
            status_code = response.status_code
        except Exception:
            status_code = None
        text = _text_of(response)
        elapsed = _elapsed_of(response)
        if error_text is None and status_code:
            error_text = None
    return ProbeOutcome(
        probe=probe,
        status_code=status_code,
        text=text,
        elapsed=elapsed if isinstance(elapsed, (int, float)) else elapsed,
        error_text=error_text,
        exception_text=exception_text,
    )


def _run_sync(
    probes: list[Probe],
    timeout: float,
    proxy: str | None,
    workers: int,
) -> dict[tuple[str, bool], ProbeOutcome]:
    underlying = requests.session()
    max_workers = min(workers, max(len(probes), 1))
    session = DuboisFuturesSession(max_workers=max_workers, session=underlying)
    futures: dict[tuple[str, bool], tuple[Probe, Future]] = {}
    try:
        for probe in probes:
            future = _dispatch_sync(session, probe, timeout, proxy)
            futures[(probe.site_name, probe.is_control)] = (probe, future)

        outcomes: dict[tuple[str, bool], ProbeOutcome] = {}
        for key, (probe, future) in futures.items():
            outcome = _outcome_from_future(probe, future)
            if _should_fallback_head(probe, outcome):
                retry = replace(probe, method="GET")
                retry_future = _dispatch_sync(session, retry, timeout, proxy)
                outcome = _outcome_from_future(retry, retry_future)
                outcome.probe = probe
            outcomes[key] = outcome
        return outcomes
    except KeyboardInterrupt:
        executor = getattr(session, "executor", None)
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)
        raise
    finally:
        executor = getattr(session, "executor", None)
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)
        underlying.close()


async def _fetch_one(session, probe: Probe, timeout: float, proxy: str | None, sem: asyncio.Semaphore) -> ProbeOutcome:
    import aiohttp

    async with sem:
        start = monotonic()
        try:
            timeout_cfg = aiohttp.ClientTimeout(total=timeout)
            kwargs: dict[str, Any] = {
                "method": probe.method,
                "url": probe.url_probe,
                "headers": probe.headers,
                "allow_redirects": probe.allow_redirects,
                "timeout": timeout_cfg,
                "proxy": proxy,
                **_body_kwargs(probe.payload),
            }
            async with session.request(**kwargs) as resp:
                status = resp.status
                if probe.method == "HEAD" and status in HEAD_FALLBACK_CODES:
                    async with session.request(
                        method="GET",
                        url=probe.url_probe,
                        headers=probe.headers,
                        allow_redirects=probe.allow_redirects,
                        timeout=timeout_cfg,
                        proxy=proxy,
                        **_body_kwargs(probe.payload),
                    ) as retry:
                        text = await retry.text(errors="replace")
                        return ProbeOutcome(
                            probe=probe,
                            status_code=retry.status,
                            text=text,
                            elapsed=monotonic() - start,
                            error_text=None,
                        )
                text = "" if probe.method == "HEAD" else await resp.text(errors="replace")
                return ProbeOutcome(
                    probe=probe,
                    status_code=status,
                    text=text,
                    elapsed=monotonic() - start,
                    error_text=None,
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            name = type(exc).__name__
            if "Timeout" in name:
                ctx = "Timeout Error"
            elif "Proxy" in name:
                ctx = "Proxy Error"
            elif "Connect" in name:
                ctx = "Error Connecting"
            elif "Unicode" in name:
                ctx = "Encoding Error"
            else:
                ctx = "Unknown Error"
            return ProbeOutcome(
                probe=probe,
                status_code=None,
                text="",
                elapsed=None,
                error_text=ctx,
                exception_text=str(exc),
            )


async def _run_async_coro(
    probes: list[Probe],
    timeout: float,
    proxy: str | None,
    workers: int,
) -> dict[tuple[str, bool], ProbeOutcome]:
    import aiohttp

    connector = aiohttp.TCPConnector(
        limit=workers,
        limit_per_host=LIMIT_PER_HOST,
        ttl_dns_cache=300,
    )
    sem = asyncio.Semaphore(workers)
    timeout_cfg = aiohttp.ClientTimeout(total=timeout)
    async with aiohttp.ClientSession(connector=connector, timeout=timeout_cfg) as session:
        tasks = [
            asyncio.create_task(_fetch_one(session, probe, timeout, proxy, sem))
            for probe in probes
        ]
        try:
            gathered = await asyncio.gather(*tasks, return_exceptions=False)
        except (KeyboardInterrupt, asyncio.CancelledError):
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
    outcomes: dict[tuple[str, bool], ProbeOutcome] = {}
    for outcome in gathered:
        outcomes[(outcome.probe.site_name, outcome.probe.is_control)] = outcome
    return outcomes


def _ensure_windows_loop_policy() -> None:
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass


def _run_async(
    probes: list[Probe],
    timeout: float,
    proxy: str | None,
    workers: int,
) -> dict[tuple[str, bool], ProbeOutcome]:
    _ensure_windows_loop_policy()
    try:
        return asyncio.run(_run_async_coro(probes, timeout, proxy, workers))
    except KeyboardInterrupt:
        raise


def _choose_engine(engine: str, proxy: str | None) -> str:
    if engine == "sync":
        return "sync"
    if _is_socks_proxy(proxy):
        return "sync"
    try:
        import aiohttp  # noqa: F401
    except ImportError:
        return "sync"
    return "async"


def _build_probe_list(
    username: str,
    site_data: dict[str, dict],
    query_notify: QueryNotify,
    results_total: dict[str, dict[str, Any]],
    calibrate: bool,
) -> list[Probe]:
    probes: list[Probe] = []
    for site_name, net_info in site_data.items():
        built = build_probe(site_name, net_info, username)
        if isinstance(built, QueryResult):
            results_total[site_name] = _empty_site_result(net_info, built)
            query_notify.update(built)
            continue
        probes.append(built)
        if calibrate:
            control_name = random_absent_username(net_info)
            if control_name:
                control = build_probe(site_name, net_info, control_name, is_control=True)
                if isinstance(control, Probe):
                    probes.append(control)
    return probes


def sherlock(
    username: str,
    site_data: dict,
    query_notify: QueryNotify,
    dump_response: bool = False,
    proxy: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    workers: int | None = None,
    calibrate: bool = False,
    engine: str = "sync",
    keep_response_text: bool = False,
    enrich: bool = True,
) -> dict[str, dict[str, Any]]:
    """Run DuBois analysis for one username.

    Library/tests default to the sync engine. The CLI defaults to async.
    Does not mutate ``site_data``.
    """
    query_notify.start(username)
    results_total: dict[str, dict[str, Any]] = {}
    probes = _build_probe_list(username, site_data, query_notify, results_total, calibrate)
    if enrich:
        probes = [
            replace(probe, method="GET") if probe.method == "HEAD" else probe
            for probe in probes
        ]
    if not probes:
        return results_total

    chosen = _choose_engine(engine, proxy)
    if workers is None:
        workers = DEFAULT_WORKERS_ASYNC if chosen == "async" else DEFAULT_WORKERS_SYNC
    workers = max(1, int(workers))

    if chosen == "async":
        outcomes = _run_async(probes, timeout, proxy, workers)
    else:
        outcomes = _run_sync(probes, timeout, proxy, workers)

    control_status: dict[str, QueryStatus] = {}
    for (site_name, is_control), outcome in outcomes.items():
        if is_control:
            status, _ctx = classify_http(
                status_code=outcome.status_code,
                text=outcome.text,
                error_type=outcome.probe.error_type,
                error_msg=outcome.probe.error_msg,
                error_code=outcome.probe.error_code,
                error_text=outcome.error_text,
                claimed_msg=outcome.probe.claimed_msg,
                claimed_code=outcome.probe.claimed_code,
            )
            control_status[site_name] = status

    for probe in probes:
        if probe.is_control:
            continue
        outcome = outcomes.get((probe.site_name, False))
        if outcome is None:
            continue
        site_result = _store_outcome(
            probe,
            site_data[probe.site_name],
            outcome,
            keep_response_text=keep_response_text,
            dump_response=dump_response,
        )
        result: QueryResult = site_result["status"]
        if (
            calibrate
            and result.status == QueryStatus.CLAIMED
            and control_status.get(probe.site_name) == QueryStatus.CLAIMED
        ):
            result = QueryResult(
                username=result.username,
                site_name=result.site_name,
                site_url_user=result.site_url_user,
                status=QueryStatus.WAF,
                query_time=result.query_time,
                context="Negative control also claimed",
            )
            site_result["status"] = result
        query_notify.update(result)
        results_total[probe.site_name] = site_result

    return results_total


def search(
    username: str,
    *,
    site_data: dict | None = None,
    sites: list[str] | None = None,
    query_notify: QueryNotify | None = None,
    dump_response: bool = False,
    proxy: str | None = None,
    timeout: float = 10,
    workers: int | None = None,
    calibrate: bool = False,
    engine: str = "async",
    nsfw: bool = False,
    local: bool = False,
    honor_exclusions: bool = True,
    keep_response_text: bool = False,
    enrich: bool = True,
) -> dict[str, dict[str, Any]]:
    """Library API. Never calls sys.exit."""
    from dubois.notify import QueryNotify as QN
    from dubois.sites import SitesInformation

    if site_data is None:
        data_path = None
        if local:
            data_path = os.path.join(os.path.dirname(__file__), "resources", "data.json")
        info = SitesInformation(
            data_file_path=data_path,
            honor_exclusions=honor_exclusions,
            do_not_exclude=sites or [],
        )
        if not nsfw:
            info.remove_nsfw_sites(do_not_remove=sites or [])
        site_data = {site.name: site.information for site in info}

    if sites:
        wanted = {name.lower() for name in sites}
        site_data = {
            name: data
            for name, data in site_data.items()
            if name.lower() in wanted
        }
        missing = wanted - {name.lower() for name in site_data}
        if missing:
            raise ValueError(f"Desired sites not found: {', '.join(sorted(missing))}.")

    notify = query_notify if query_notify is not None else QN()
    return sherlock(
        username,
        site_data,
        notify,
        dump_response=dump_response,
        proxy=proxy,
        timeout=timeout,
        workers=workers,
        calibrate=calibrate,
        engine=engine,
        keep_response_text=keep_response_text,
        enrich=enrich,
    )
