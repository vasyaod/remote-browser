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
import base64
import json
import os
import pathlib
import sys
import time
from typing import Any, Iterable, Optional, Set, Tuple

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


def _looks_like_jwt(token: str) -> bool:
    # Very lightweight heuristic: JWTs typically have 3 dot-separated segments.
    if not token or not isinstance(token, str):
        return False
    parts = token.split(".")
    return len(parts) == 3 and all(parts)


def _load_json_file(path: pathlib.Path) -> Optional[dict[str, Any]]:
    try:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001 - best-effort local loading
        return None


def _extract_from_dockerhub_config(cfg: dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Best-effort extraction from ~/.dockerhub/config.json.

    We support a few common shapes:
    - {"username": "...", "token": "..."}  (token may be PAT or JWT depending on tooling)
    - {"auth": {"username": "...", "token": "..."}}  (nested)
    - {"dockerhub": {"username": "...", "token": "..."}} (nested)
    """

    def pick(d: dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        u = d.get("username") or d.get("user")
        t = d.get("token") or d.get("access_token") or d.get("password")
        return (u if isinstance(u, str) else None, t if isinstance(t, str) else None)

    username, token = pick(cfg)
    if not username or not token:
        for key in ("auth", "dockerhub", "docker_hub", "credentials"):
            nested = cfg.get(key)
            if isinstance(nested, dict):
                u2, t2 = pick(nested)
                username = username or u2
                token = token or t2

    jwt_token: Optional[str] = None
    if token and _looks_like_jwt(token):
        jwt_token = token
    elif isinstance(cfg.get("jwt"), str) and _looks_like_jwt(cfg["jwt"]):
        jwt_token = cfg["jwt"]

    return username, token, jwt_token


def _extract_from_docker_config(cfg: dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    Best-effort extraction from ~/.docker/config.json.

    Works only when creds are stored inline under auths.*.auth (base64 "user:pass").
    If you use an OS keychain/credsStore, this will likely return (None, None).
    """
    auths = cfg.get("auths")
    if not isinstance(auths, dict):
        return None, None

    candidates = (
        "https://index.docker.io/v1/",
        "https://registry-1.docker.io/v2/",
        "registry-1.docker.io",
        "docker.io",
    )
    for key in candidates:
        entry = auths.get(key)
        if not isinstance(entry, dict):
            continue
        auth_b64 = entry.get("auth")
        if not isinstance(auth_b64, str) or not auth_b64:
            continue
        try:
            decoded = base64.b64decode(auth_b64).decode("utf-8", errors="ignore")
            if ":" not in decoded:
                continue
            username, password = decoded.split(":", 1)
            return username or None, password or None
        except Exception:  # noqa: BLE001
            continue

    return None, None


def load_dockerhub_credentials(
    dockerhub_config_path: pathlib.Path,
    docker_config_path: pathlib.Path,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Load Docker Hub credentials from common local config locations.

    Returns: (username, password_or_pat, jwt_token)
    """
    cfg = _load_json_file(dockerhub_config_path)
    if cfg:
        u, t, jwt = _extract_from_dockerhub_config(cfg)
        if u or t or jwt:
            return u, t, jwt

    docker_cfg = _load_json_file(docker_config_path)
    if docker_cfg:
        u, p = _extract_from_docker_config(docker_cfg)
        if u or p:
            return u, p, None

    return None, None, None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readme", default="README.md", help="Path to README file (default: README.md)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail (exit 1) if README sync cannot be completed (including Docker Hub 5xx). "
        "Default behavior is best-effort (non-fatal) for CI pipelines.",
    )
    parser.add_argument(
        "--dockerhub-config",
        default="~/.dockerhub/config.json",
        help="Path to Docker Hub config (default: ~/.dockerhub/config.json)",
    )
    parser.add_argument(
        "--docker-config",
        default="~/.docker/config.json",
        help="Path to Docker config (default: ~/.docker/config.json)",
    )
    args = parser.parse_args()

    image_name = os.environ.get("IMAGE_NAME")
    if not image_name:
        print("ERROR: missing required env var: IMAGE_NAME", file=sys.stderr)
        return 1

    with open(args.readme, "r", encoding="utf-8") as f:
        readme_content = f.read()

    # Prefer env vars (CI), but allow local config fallback (~/.dockerhub, ~/.docker).
    username = os.environ.get("DOCKERHUB_USERNAME")
    password = os.environ.get("DOCKERHUB_TOKEN")
    jwt_token = os.environ.get("DOCKERHUB_JWT")

    if not username or (not password and not jwt_token):
        u2, p2, jwt2 = load_dockerhub_credentials(
            pathlib.Path(os.path.expanduser(args.dockerhub_config)).resolve(),
            pathlib.Path(os.path.expanduser(args.docker_config)).resolve(),
        )
        username = username or u2
        password = password or p2
        jwt_token = jwt_token or jwt2

    if not username:
        print("ERROR: missing Docker Hub username (DOCKERHUB_USERNAME or local config)", file=sys.stderr)
        return 1

    # If we already have a JWT (e.g. stored in ~/.dockerhub), skip the flaky login endpoint.
    if not jwt_token:
        if not password:
            print("ERROR: missing Docker Hub token/password (DOCKERHUB_TOKEN or local config)", file=sys.stderr)
            return 1

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
            return 1 if args.strict else 0

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
        return 1 if args.strict else 0

    if response.status_code in (200, 201):
        print("✓ Docker Hub README updated successfully", flush=True)
        return 0

    print(f"WARN: Docker Hub README update returned status={response.status_code}", flush=True)
    print(f"Response: {response.text}", flush=True)
    if response.status_code in (401, 403):
        return 1
    return 1 if args.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())


