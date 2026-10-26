"""Send steady authenticated traffic and record every failed request (stdlib only).

Used for two demos (see k8s/README.md):
  * rolling update / rollback: run this while `kubectl rollout restart|undo` happens
  * HPA: run with more workers to create CPU load and watch `kubectl get hpa -w`

    python scripts/traffic_check.py --base-url http://127.0.0.1:8080 \
        --credentials-file .env.credentials --seconds 120 --workers 4

Prints a summary (status code counts, failures with timestamps) and exits 1
if any request failed, so "zero failed requests" is a measured result.
"""
import argparse
import json
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone

PATHS = ["/api/inventory/products", "/api/inventory/stats", "/api/orders?limit=20", "/api/orders/stats"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--credentials-file", required=True)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    creds = dict(line.split("=", 1) for line in open(args.credentials_file, encoding="utf-8").read().split())
    login = urllib.request.Request(args.base_url + "/api/auth/login", method="POST",
                                   data=json.dumps({"username": creds["STAFF_USER"],
                                                    "password": creds["STAFF_PASSWORD"]}).encode(),
                                   headers={"Content-Type": "application/json"})
    token = json.load(urllib.request.urlopen(login, timeout=10))["access_token"]

    counts, failures, lock = Counter(), [], threading.Lock()
    deadline = time.monotonic() + args.seconds

    def worker(n: int):
        i = n
        while time.monotonic() < deadline:
            path = PATHS[i % len(PATHS)]
            i += 1
            req = urllib.request.Request(args.base_url + path, headers={"Authorization": f"Bearer {token}"})
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    code = resp.status
            except urllib.error.HTTPError as err:
                code = err.code
            except OSError as err:
                code = type(err).__name__
            with lock:
                counts[code] += 1
                if code != 200:
                    failures.append((datetime.now(timezone.utc).strftime("%H:%M:%S.%f")[:-3], path, code))

    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    threads = [threading.Thread(target=worker, args=(n,)) for n in range(args.workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total = sum(counts.values())
    print(f"started {started}, {args.seconds}s, {args.workers} workers, {total} requests")
    print("status counts:", dict(counts))
    for ts, path, code in failures[:20]:
        print(f"  FAILED {ts} {path} -> {code}")
    print(f"failed requests: {len(failures)}")
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
