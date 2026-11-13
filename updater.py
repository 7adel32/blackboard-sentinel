"""Silent GitHub Releases auto-updater for Blackboard Sentinel on Windows."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

import app_meta
import check_lms

USER_AGENT = f"{app_meta.APP_NAME}/{app_meta.APP_VERSION}"
DEFAULT_INSTALLER_ASSET = "BlackboardSentinelSetup.exe"
_VERSION_RE = re.compile(r"(\d+)")


class _CrossHostAuthStripRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Strip Authorization header when following redirects to a different host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new_req = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new_req is None:
            return None
        old_host = urllib.parse.urlparse(req.full_url).hostname or ""
        new_host = urllib.parse.urlparse(newurl).hostname or ""
        if old_host.lower() != new_host.lower():
            for header_name in list(new_req.headers.keys()):
                if header_name.lower() == "authorization":
                    del new_req.headers[header_name]
            for header_name in list(new_req.unredirected_hdrs.keys()):
                if header_name.lower() == "authorization":
                    del new_req.unredirected_hdrs[header_name]
        return new_req


def _build_opener() -> urllib.request.OpenerDirector:
    ssl_ctx = check_lms._get_ssl_context()
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl_ctx),
        _CrossHostAuthStripRedirectHandler(),
    )


def parse_version(version_str: str) -> tuple[int, ...]:
    """Parse a semantic version or git tag like 'v1.2.3' into an integer tuple."""
    cleaned = str(version_str or "").strip().lstrip("vV")
    if not cleaned:
        return (0,)
    # Drop pre-release/build suffixes before comparing numeric segments.
    core = re.split(r"[-+]", cleaned, maxsplit=1)[0]
    parts = [int(match) for match in _VERSION_RE.findall(core)]
    return tuple(parts) if parts else (0,)


def is_newer_version(latest: str, current: str | None = None) -> bool:
    """Return True if `latest` represents a strictly newer version than `current`."""
    current_val = app_meta.APP_VERSION if current is None else current
    latest_parts = list(parse_version(latest))
    current_parts = list(parse_version(current_val))
    width = max(len(latest_parts), len(current_parts))
    latest_parts.extend([0] * (width - len(latest_parts)))
    current_parts.extend([0] * (width - len(current_parts)))
    return tuple(latest_parts) > tuple(current_parts)


def _select_installer_asset(assets: list[dict], asset_name: str = DEFAULT_INSTALLER_ASSET) -> dict | None:
    for asset in assets or []:
        if asset.get("name") == asset_name:
            return asset
    for asset in assets or []:
        name = str(asset.get("name") or "").lower()
        if name.endswith("setup.exe") or (name.endswith(".exe") and "cli" not in name):
            return asset
    return None


def _api_headers(token: str = "", accept: str = "application/vnd.github+json") -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def check_for_update(
    current_version: str | None = None,
    repo: str | None = None,
    token: str | None = None,
    timeout: int = 15,
) -> dict | None:
    """Query GitHub Releases for a newer Windows installer release.

    Returns a metadata dict with keys: version, tag_name, asset_name,
    download_url, release_url, notes, is_api_asset; or None if up to date / unavailable.
    """
    target_repo = (repo if repo is not None else app_meta.GITHUB_REPO).strip()
    if not target_repo:
        return None
    auth_token = (token if token is not None else app_meta.GITHUB_TOKEN).strip()
    url = f"https://api.github.com/repos/{target_repo}/releases/latest"
    req = urllib.request.Request(url, headers=_api_headers(auth_token))
    opener = _build_opener()
    with opener.open(req, timeout=timeout) as resp:
        payload = json.loads(resp.read().decode("utf-8"))

    tag_name = str(payload.get("tag_name") or "").strip()
    if not tag_name or not is_newer_version(tag_name, current_version):
        return None

    asset = _select_installer_asset(payload.get("assets") or [])
    if not asset:
        return None

    if auth_token and asset.get("url"):
        download_url = str(asset["url"])
        is_api_asset = True
    else:
        download_url = str(asset.get("browser_download_url") or asset.get("url") or "")
        is_api_asset = bool(not asset.get("browser_download_url") and asset.get("url"))

    if not download_url:
        return None

    return {
        "version": tag_name.lstrip("vV"),
        "tag_name": tag_name,
        "asset_name": str(asset.get("name") or DEFAULT_INSTALLER_ASSET),
        "download_url": download_url,
        "release_url": str(payload.get("html_url") or ""),
        "notes": str(payload.get("body") or ""),
        "is_api_asset": is_api_asset,
    }


def download_installer(
    update_info: dict,
    token: str | None = None,
    timeout: int = 120,
    dest_dir: str | None = None,
) -> str:
    """Download the installer asset to a temporary file and return its path."""
    download_url = str(update_info["download_url"])
    asset_name = os.path.basename(str(update_info.get("asset_name") or DEFAULT_INSTALLER_ASSET)) or DEFAULT_INSTALLER_ASSET
    auth_token = (token if token is not None else app_meta.GITHUB_TOKEN).strip()

    accept = "application/octet-stream" if update_info.get("is_api_asset") else "*/*"
    headers = _api_headers(auth_token, accept=accept)
    req = urllib.request.Request(download_url, headers=headers)
    opener = _build_opener()

    target_root = dest_dir or os.path.join(tempfile.gettempdir(), f"{app_meta.APP_NAME}_update")
    os.makedirs(target_root, exist_ok=True)
    target_path = os.path.join(target_root, asset_name)
    part_path = target_path + ".part"

    with opener.open(req, timeout=timeout) as resp, open(part_path, "wb") as handle:
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            handle.write(chunk)

    os.replace(part_path, target_path)
    return target_path


def launch_silent_installer(
    installer_path: str,
    before_exit_callback: Callable[[], None] | None = None,
    exit_process: bool = True,
) -> subprocess.Popen:
    """Spawn the Inno Setup installer detached cleanly and exit this process."""
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        )

    proc = subprocess.Popen(
        [
            installer_path,
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/FORCECLOSEAPPLICATIONS",
            "/NORESTART",
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        creationflags=creation_flags,
    )

    if before_exit_callback is not None:
        try:
            before_exit_callback()
        except Exception:
            pass

    if exit_process:
        os._exit(0)

    return proc


def perform_silent_update(
    current_version: str | None = None,
    repo: str | None = None,
    token: str | None = None,
    before_exit_callback: Callable[[], None] | None = None,
) -> dict | None:
    """Check for a newer release, download its installer, and run it silently."""
    if sys.platform != "win32":
        return None
    update_info = check_for_update(current_version=current_version, repo=repo, token=token)
    if not update_info:
        return None
    installer_path = download_installer(update_info, token=token)
    update_info["installer_path"] = installer_path
    launch_silent_installer(installer_path, before_exit_callback=before_exit_callback, exit_process=True)
    return update_info
