"""Assertion helpers for the Tier-1 test suite (docs/adr/0025)."""

from __future__ import annotations

import threading

from django.urls import reverse


def _url(name_or_path: str, **kwargs) -> str:
    if name_or_path.startswith("/"):
        return name_or_path
    return reverse(name_or_path, kwargs=kwargs or None)


def assert_login_required(client, name_or_path: str, **kwargs) -> None:
    resp = client.get(_url(name_or_path, **kwargs))
    assert resp.status_code == 302, f"expected redirect, got {resp.status_code}"
    assert reverse("accounts:login") in resp["Location"]


def assert_forbidden(client, name_or_path: str, **kwargs) -> None:
    resp = client.get(_url(name_or_path, **kwargs))
    assert resp.status_code == 403, f"expected 403, got {resp.status_code}"


def assert_not_found(client, name_or_path: str, **kwargs) -> None:
    resp = client.get(_url(name_or_path, **kwargs))
    assert resp.status_code == 404, f"expected 404, got {resp.status_code}"


def run_concurrently(fn, n: int = 10):
    """Run ``fn()`` in ``n`` threads; return the list of results (or raised exc)."""
    results: list = [None] * n
    barrier = threading.Barrier(n)

    def worker(i: int) -> None:
        barrier.wait()
        try:
            results[i] = fn()
        except Exception as exc:
            results[i] = exc

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results
