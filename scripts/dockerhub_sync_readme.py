#!/usr/bin/env python3
"""
Sync local README.md to Docker Hub repository description.

Behavior:
- Uses Docker Hub JWT login endpoint to get a token
- Retries on flaky upstream statuses (429/5xx) with exponential backoff
- If Docker Hub is unstable (login/update keeps 5xx), prints diagnostics and exits 0 (non-fatal)
- If credentials/permissions are wrong (401/403), exits 1 (fail)
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Iterable, Optional, Set

import requests


RETRYABLE_STATUSES_DEFAULT: Set[int] = {429, 500, 502, 503, 504}


def request_with_retries(
    method: str,
    url: str,
    *,
    max_attempts: int = 6,
    timeout: int = 15,
    retry_statuses: Optional[Set[int]] = None,
    **kwargs,
) -> requests.Response:
    """
    Retry helper for flaky upstream endpoints.
    Retries on network errors and specific HTTP statuses (e.g. 429/5xx).
    """
    retry_statuses = retry_statuses or RETRYABLE_STATUSES_DEFAULT

    last_exc: Optional[BaseException] = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)
            if resp.status_code in retry_statuses:
                body_preview = (resp.text or "")[:500]
                raise RuntimeError(f"retryable_status={resp.status_code} body={body_preview}")
            return resp
        except Exception as e:  # noqa: BLE001 - ok in a CLI script
            last_exc = e
            if attempt == max_attempts:
                raise
            sleep_s = min(30, 2**attempt)
            print(
                f"WARN: request failed ({attempt}/{max_attempts}) {method} {url}: {e}. "
                f"Retrying in {sleep_s}s...",
                flush=True,
            )
            time.sleep(sleep_s)

    assert last_exc is not None
    raise last_exc


def print_connectivity_diagnostics() -> None:
    """
    Helps distinguish "runner has no internet" vs "Docker Hub is returning 5xx".
    """
    checks: Iterable[tuple[str, str]] = [
        ("docker_hub_api_root", "https://hub.docker.com/v2/"),
        ("docker_registry_v2", "https://registry-1.docker.io/v2/"),
        ("docker_status", "https://www.dockerstatus.com/api/v2/status.json"),
    ]
    for name, url in checks:
        try:
            r = requests.get(url, timeout=10)
            preview = (r.text or "")[:200].replace("\n", "\\n")
            print(f"DIAG: {name} status={r.status_code} url={url} body_preview={preview}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"DIAG: {name} error={e} url={url}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readme", default="README.md", help="Path to README file (default: README.md)")
    args = parser.parse_args()

    username = os.environ.get("DOCKERHUB_USERNAME")
    password = os.environ.get("DOCKERHUB_TOKEN")
    image_name = os.environ.get("IMAGE_NAME")

    missing = [k for k, v in (("DOCKERHUB_USERNAME", username), ("DOCKERHUB_TOKEN", password), ("IMAGE_NAME", image_name)) if not v]
    if missing:
        print(f"ERROR: missing required env vars: {', '.join(missing)}", file=sys.stderr)
        return 1

    with open(args.readme, "r", encoding="utf-8") as f:
        readme_content = f.read()

    # Login to get JWT token
    login_url = "https://hub.docker.com/v2/users/login/"
    try:
        login_response = request_with_retries(
            "POST",
            login_url,
            json={"username": username, "password": password},
        )
    except Exception as e:  # noqa: BLE001
        # Docker Hub occasionally returns transient 5xx here; don't fail the whole build on that.
        print(f"WARN: Docker Hub login failed after retries: {e}", flush=True)
        print_connectivity_diagnostics()
        print("WARN: Skipping README sync due to Docker Hub login instability.", flush=True)
        return 0

    if login_response.status_code != 200:
        # Non-retryable failure (e.g. 401/403). This should fail so secrets can be fixed.
        print(f"ERROR: Docker Hub auth failed: status={login_response.status_code}", file=sys.stderr)
        print(f"Response: {login_response.text}", file=sys.stderr)
        return 1

    jwt_token = login_response.json().get("token")
    if not jwt_token:
        print("ERROR: Docker Hub login succeeded but no JWT token returned", file=sys.stderr)
        return 1

    # Update Docker Hub repository description using JWT token
    repo_url = f"https://hub.docker.com/v2/repositories/{username}/{image_name}/"
    headers = {"Content-Type": "application/json", "Authorization": f"JWT {jwt_token}"}
    data = {"full_description": readme_content}

    try:
        response = request_with_retries("PATCH", repo_url, headers=headers, json=data)
    except Exception as e:  # noqa: BLE001
        print(f"WARN: Docker Hub README update failed after retries: {e}", flush=True)
        print("WARN: Skipping README sync failure (image already pushed).", flush=True)
        return 0

    if response.status_code in (200, 201):
        print("✓ Docker Hub README updated successfully", flush=True)
        return 0

    print(f"WARN: Docker Hub README update returned status={response.status_code}", flush=True)
    print(f"Response: {response.text}", flush=True)
    if response.status_code in (401, 403):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


