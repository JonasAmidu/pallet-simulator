#!/usr/bin/env python3
import sys
import time
import socket
import urllib.error
import urllib.request


def main() -> int:
    if len(sys.argv) not in {2, 3}:
        print("usage: wait_for_http.py <url> [timeout_seconds]", file=sys.stderr)
        return 2

    url = sys.argv[1]
    timeout = float(sys.argv[2]) if len(sys.argv) == 3 else 30.0
    deadline = time.monotonic() + timeout
    last_error = "service not ready"

    while time.monotonic() < deadline:
        try:
            remaining = max(1.0, deadline - time.monotonic())
            with urllib.request.urlopen(url, timeout=min(5.0, remaining)) as response:
                body = response.read().decode("utf-8", errors="replace").strip()
                print(f"{url} -> {response.status}")
                if body:
                    print(body[:200])
                return 0
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            ConnectionError,
            TimeoutError,
            socket.timeout,
        ) as exc:
            last_error = str(exc)
            time.sleep(1)

    print(f"Timed out waiting for {url}: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
