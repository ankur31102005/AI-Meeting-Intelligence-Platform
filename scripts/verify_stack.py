"""
End-to-end stack verification — run AFTER `make up` to confirm every
service is wired correctly:

    python scripts/verify_stack.py

Checks: API liveness -> API readiness (Postgres+Redis) -> MinIO -> ChromaDB
-> Celery round-trip (broker -> worker -> result backend).
"""

import sys
import urllib.error
import urllib.request

API = "http://localhost:8000/api/v1"
GREEN, RED, RESET = "\033[92m", "\033[91m", "\033[0m"


def check(name: str, fn) -> bool:
    try:
        fn()
        print(f"  {GREEN}PASS{RESET}  {name}")
        return True
    except Exception as exc:  # noqa: BLE001 — report every failure kind
        print(f"  {RED}FAIL{RESET}  {name}: {exc}")
        return False


def http_ok(url: str, expect: int = 200) -> None:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310 — localhost only
            got = resp.status
    except urllib.error.HTTPError as e:
        got = e.code
    if got != expect:
        raise AssertionError(f"expected HTTP {expect}, got {got}")


def celery_roundtrip() -> None:
    # Imported lazily so the HTTP checks run even without backend deps installed.
    sys.path.insert(0, "backend")
    from app.workers.celery_app import celery_app

    result = celery_app.send_task("system.ping").get(timeout=10)
    if result != "pong":
        raise AssertionError(f"expected 'pong', got {result!r}")


def main() -> int:
    print("\nVerifying AI Meeting Intelligence Platform stack...\n")
    results = [
        check("API liveness            (backend up)", lambda: http_ok(f"{API}/health")),
        check("API readiness           (postgres + redis)", lambda: http_ok(f"{API}/health/ready")),
        check("MinIO                   (object storage)",
              lambda: http_ok("http://localhost:9000/minio/health/live")),
        check("ChromaDB                (vector store)",
              lambda: http_ok("http://localhost:8001/api/v2/heartbeat")),
        check("Celery round-trip       (broker -> worker -> result)", celery_roundtrip),
    ]
    failed = results.count(False)
    print(f"\n{len(results) - failed}/{len(results)} checks passed\n")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
