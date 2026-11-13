#!/usr/bin/env python3
"""
Blackboard LMS Automated Course Sync, Announcements & Deadline Sentinel
University LMS Portal Sentinel

Automatically monitors enrolled courses, syncs course materials and assignment briefs,
tracks grades and deadlines, and dispatches instant alerts.

Zero-quota Hermes watchdog: outputs to stdout and dispatches notifications only when updates occur.
"""

import os
import sys
import json
import html
import re
import time
import hashlib
import shutil
import stat
import subprocess
import tempfile
import urllib.request
import urllib.parse
import http.cookiejar
import copy
import plistlib
import zipfile
import zlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

# Ensure UTF-8 output on Windows consoles to prevent cp1252 UnicodeEncodeError on Arabic strings
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

KEYRING_SERVICE = "BlackboardSentinel"


def get_keyring_password(username):
    """Retrieve password securely from system keyring/credential store."""
    if not username:
        return ""
    try:
        import keyring
        pwd = keyring.get_password(KEYRING_SERVICE, username)
        return pwd or ""
    except Exception:
        return ""


def set_keyring_password(username, password):
    """Store password securely in system keyring/credential store."""
    if not username:
        return False
    try:
        import keyring
        keyring.set_password(KEYRING_SERVICE, username, password)
        return True
    except Exception:
        return False


def delete_keyring_password(username):
    """Delete password from system keyring/credential store."""
    if not username:
        return False
    try:
        import keyring
        try:
            keyring.delete_password(KEYRING_SERVICE, username)
            return True
        except Exception:
            return False
    except Exception:
        return False


def load_env_file(filepath, override=False, _seen_keys=None):
    """Load key-value pairs from a .env file into os.environ."""
    if not os.path.isfile(filepath):
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if not k:
                    continue
                if _seen_keys is not None and k in _seen_keys:
                    continue
                if override or k not in os.environ:
                    os.environ[k] = v
                if _seen_keys is not None:
                    _seen_keys.add(k)
    except Exception:
        pass


def init_config(override=False):
    """Discover environment configuration from local .env, Hermes, or system paths."""
    is_frozen = getattr(sys, "frozen", False)
    candidates = []
    if is_frozen:
        if sys.platform == "win32":
            appdata = os.getenv("APPDATA", os.path.expanduser("~"))
            candidates.append(os.path.join(appdata, "BlackboardSentinel", ".env"))
        elif sys.platform == "darwin":
            candidates.append(os.path.expanduser("~/Library/Application Support/BlackboardSentinel/.env"))
        candidates.append(os.path.join(os.getcwd(), ".env"))
        candidates.append(os.path.expanduser("~/.hermes/.env"))
    else:
        candidates = [
            os.path.join(os.getcwd(), ".env"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        ]
        if sys.platform == "win32":
            appdata = os.getenv("APPDATA", os.path.expanduser("~"))
            candidates.append(os.path.join(appdata, "BlackboardSentinel", ".env"))
        elif sys.platform == "darwin":
            candidates.append(os.path.expanduser("~/Library/Application Support/BlackboardSentinel/.env"))
        candidates.append(os.path.expanduser("~/.hermes/.env"))

    seen_keys = set()
    for c in candidates:
        if os.path.isfile(c):
            load_env_file(c, override=override, _seen_keys=seen_keys)

    global LMS_URL, USER_ID, PASSWORD, STUDENT_USER_ID, LMS_STORAGE_DIR, LMS_COURSES, TRAY_THEME, STATE_DIR, STATE_FILE, LOGS_DIR, KEEP_ALL_ANNOUNCEMENTS, EXPAND_ZIPS, DELETE_ORIGINAL_ZIP, MAX_FILE_BYTES, MAX_WORKERS

    LMS_URL = os.getenv("LMS_URL", "").rstrip("/")
    USER_ID = os.getenv("LMS_USER_ID", "")
    PASSWORD = os.getenv("LMS_PASSWORD", "")
    if override and USER_ID and "LMS_PASSWORD" not in seen_keys:
        keyring_pwd = get_keyring_password(USER_ID)
        if keyring_pwd:
            PASSWORD = keyring_pwd
    if not PASSWORD and USER_ID:
        PASSWORD = get_keyring_password(USER_ID)
    elif PASSWORD and USER_ID:
        try:
            if not get_keyring_password(USER_ID):
                set_keyring_password(USER_ID, PASSWORD)
        except Exception:
            pass
    STUDENT_USER_ID = os.getenv("LMS_STUDENT_ID", "")
    LMS_STORAGE_DIR = os.path.normpath(os.path.expanduser(os.getenv("LMS_STORAGE_DIR") or "~/Documents/University"))
    LMS_COURSES = os.getenv("LMS_COURSES", "")
    TRAY_THEME = os.getenv("TRAY_THEME", "auto")
    KEEP_ALL_ANNOUNCEMENTS = os.getenv("LMS_KEEP_ALL_ANNOUNCEMENTS", "false").lower() in ("true", "1", "yes")
    EXPAND_ZIPS = os.getenv("LMS_EXPAND_ZIPS", "false").lower() in ("true", "1", "yes")
    DELETE_ORIGINAL_ZIP = os.getenv("LMS_DELETE_ORIGINAL_ZIP", "false").lower() in ("true", "1", "yes")

    # Size-based skip rule: files larger than this many MB are not downloaded. 0 (default) = disabled.
    try:
        MAX_FILE_BYTES = int(max(0.0, float(os.getenv("LMS_MAX_FILE_SIZE_MB", "0") or 0)) * 1024 * 1024)
    except ValueError:
        MAX_FILE_BYTES = 0

    # Parallel course checking: number of worker threads.
    # 0 (default) = unlimited (one worker per task, hard-capped at 16); 1 = sequential.
    try:
        MAX_WORKERS = max(0, int(os.getenv("LMS_MAX_WORKERS", "0") or 0))
    except ValueError:
        MAX_WORKERS = 0

    hermes_state = os.path.normpath(os.path.expanduser("~/.hermes/state"))
    if os.path.exists(hermes_state) or os.path.exists(os.path.expanduser("~/.hermes")):
        STATE_DIR = hermes_state
        LOGS_DIR = os.path.normpath(os.path.expanduser("~/.hermes/logs"))
    elif sys.platform == "win32":
        local_appdata = os.getenv("LOCALAPPDATA", os.path.expanduser("~"))
        STATE_DIR = os.path.join(local_appdata, "BlackboardSentinel", "state")
        LOGS_DIR = os.path.join(local_appdata, "BlackboardSentinel", "logs")
    elif sys.platform == "darwin":
        base_support = os.path.expanduser("~/Library/Application Support/BlackboardSentinel")
        STATE_DIR = os.path.join(base_support, "state")
        LOGS_DIR = os.path.expanduser("~/Library/Logs/BlackboardSentinel")
    else:
        STATE_DIR = os.path.expanduser("~/.blackboard-sentinel/state")
        LOGS_DIR = os.path.expanduser("~/.blackboard-sentinel/logs")

    STATE_FILE = os.path.join(STATE_DIR, "lms_tracker_state.json")


def _parallel_map(fn, items):
    """Run fn over items on up to MAX_WORKERS threads (0 = unlimited, capped at 16), preserving input order."""
    items = list(items)
    cap = 16 if MAX_WORKERS == 0 else MAX_WORKERS
    workers = max(1, min(cap, len(items)))
    if workers == 1:
        return [fn(i) for i in items]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(fn, items))


def _get_ssl_context():
    """Return an SSLContext with working CA certificates (handles macOS python.org/frozen bundles)."""
    import ssl
    env_ca = os.getenv("SSL_CERT_FILE")
    if env_ca and os.path.isfile(env_ca):
        return ssl.create_default_context(cafile=env_ca)
    paths = ssl.get_default_verify_paths()
    has_default_ca = bool(
        (paths.cafile and os.path.isfile(paths.cafile))
        or (paths.openssl_cafile and os.path.isfile(paths.openssl_cafile))
    )
    if sys.platform == "darwin" and not has_default_ca:
        if os.path.isfile("/etc/ssl/cert.pem"):
            return ssl.create_default_context(cafile="/etc/ssl/cert.pem")
        try:
            import certifi
            return ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
    return ssl.create_default_context()


def find_local_chromium_browser():
    """Find installed Edge or Chrome executable on Windows/macOS/Linux."""
    if sys.platform == "win32":
        candidates = [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
        ]
    elif sys.platform == "darwin":
        candidates = [
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        ]
    else:
        candidates = [
            "/usr/bin/google-chrome",
            "/usr/bin/microsoft-edge",
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser"
        ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def run_browser_login_flow(portal_url, on_status_update=None, timeout_seconds=300):
    """
    Launch an embedded browser webview window allowing SSO/MFA authentication.
    Monitors authenticated Blackboard session cookies and extracts them into LMSClient.
    """
    browser_bin = find_local_chromium_browser()
    if not browser_bin:
        raise RuntimeError("No supported Chromium browser (Edge/Chrome) was found for web portal sign-in.")

    clean_url = portal_url if portal_url.startswith(("http://", "https://")) else f"https://{portal_url}"
    login_target_url = f"{clean_url.rstrip('/')}/webapps/login/"

    import tempfile
    import base64
    import struct
    import subprocess
    import socket

    # Allocate free local port
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    debug_port = s.getsockname()[1]
    s.close()

    temp_profile = tempfile.mkdtemp(prefix="bb_sentinel_browser_")

    cmd = [
        browser_bin,
        f"--app={login_target_url}",
        f"--remote-debugging-port={debug_port}",
        f"--user-data-dir={temp_profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=720,820"
    ]

    if on_status_update:
        on_status_update("Opening web login portal...")

    proc = subprocess.Popen(cmd)

    # Helper: read JSON from CDP HTTP endpoint
    def cdp_get_json(endpoint):
        req = urllib.request.Request(f"http://127.0.0.1:{debug_port}{endpoint}", headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return json.loads(resp.read().decode("utf-8"))

    start_time = time.time()
    ws_sock = None
    captured_cookies = []

    try:
        # Wait for CDP endpoint to be ready
        target_ws_url = None
        while time.time() - start_time < 15.0:
            if proc.poll() is not None:
                raise RuntimeError("Browser window was closed before sign-in completed.")
            try:
                pages = cdp_get_json("/json")
                for p in pages:
                    if p.get("type") == "page" and p.get("webSocketDebuggerUrl"):
                        target_ws_url = p["webSocketDebuggerUrl"]
                        break
                if target_ws_url:
                    break
            except Exception:
                pass
            time.sleep(0.5)

        if not target_ws_url:
            raise RuntimeError("Failed to attach to browser login window.")

        # Connect to CDP websocket using pure standard library
        ws_path = "/" + target_ws_url.split("/", 3)[3]
        ws_sock = socket.socket()
        ws_sock.settimeout(3.0)
        ws_sock.connect(("127.0.0.1", debug_port))

        key = base64.b64encode(os.urandom(16)).decode("ascii")
        ws_req = (
            f"GET {ws_path} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{debug_port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        ws_sock.sendall(ws_req.encode("ascii"))
        hs_resp = b""
        while b"\r\n\r\n" not in hs_resp:
            chunk = ws_sock.recv(1024)
            if not chunk:
                break
            hs_resp += chunk
        if b"101 " not in hs_resp:
            raise RuntimeError("Failed WebSocket handshake with browser debugger.")

        def ws_send(msg_dict):
            payload = json.dumps(msg_dict).encode("utf-8")
            mask = os.urandom(4)
            length = len(payload)
            if length <= 125:
                hdr = bytearray([0x81, 0x80 | length])
            elif length <= 65535:
                hdr = bytearray([0x81, 0x80 | 126]) + struct.pack(">H", length)
            else:
                hdr = bytearray([0x81, 0x80 | 127]) + struct.pack(">Q", length)
            hdr += mask
            masked = bytearray(payload[i] ^ mask[i % 4] for i in range(length))
            ws_sock.sendall(bytes(hdr + masked))

        def ws_recv():
            hdr = ws_sock.recv(2)
            if len(hdr) < 2:
                return None
            b1, b2 = hdr[0], hdr[1]
            length = b2 & 0x7F
            if length == 126:
                length = struct.unpack(">H", ws_sock.recv(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", ws_sock.recv(8))[0]
            buf = b""
            while len(buf) < length:
                c = ws_sock.recv(min(4096, length - len(buf)))
                if not c:
                    break
                buf += c
            return json.loads(buf.decode("utf-8"))

        if on_status_update:
            on_status_update("Waiting for SSO / MFA authentication to complete in browser...")

        # Poll cookies periodically until authenticated Blackboard session cookies appear
        msg_id = 1
        authenticated = False
        login_poll_start = time.time()

        while time.time() - login_poll_start < timeout_seconds:
            if proc.poll() is not None:
                # Browser was closed
                break

            msg_id += 1
            ws_send({"id": msg_id, "method": "Network.getCookies"})
            try:
                resp = ws_recv()
                if resp and "result" in resp and "cookies" in resp["result"]:
                    cookies = resp["result"]["cookies"]
                    cookie_names = {c.get("name"): c.get("value") for c in cookies}
                    has_session = any(k in cookie_names for k in ("JSESSIONID", "bb_session", "session_id"))
                    
                    if has_session:
                        # Verify session works against /learn/api/public/v1/users/me
                        cj = http.cookiejar.CookieJar()
                        for c in cookies:
                            cj.set_cookie(http.cookiejar.Cookie(
                                version=0,
                                name=c.get("name"),
                                value=c.get("value"),
                                port=None,
                                port_specified=False,
                                domain=c.get("domain", "").lstrip("."),
                                domain_specified=bool(c.get("domain")),
                                domain_initial_dot=c.get("domain", "").startswith("."),
                                path=c.get("path", "/"),
                                path_specified=True,
                                secure=bool(c.get("secure")),
                                expires=int(c.get("expires", 0)) if c.get("expires", 0) > 0 else None,
                                discard=False,
                                comment=None,
                                comment_url=None,
                                rest={}
                            ))
                        test_opener = urllib.request.build_opener(
                            urllib.request.HTTPSHandler(context=_get_ssl_context()),
                            urllib.request.HTTPCookieProcessor(cj),
                        )
                        test_req = urllib.request.Request(
                            f"{clean_url.rstrip('/')}/learn/api/public/v1/users/me",
                            headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
                        )
                        try:
                            with test_opener.open(test_req, timeout=3.0) as verify_resp:
                                if verify_resp.status == 200:
                                    me = json.loads(verify_resp.read().decode("utf-8"))
                                    if me.get("id"):
                                        authenticated = True
                                        captured_cookies = cookies
                                        break
                        except Exception:
                            pass
            except Exception:
                pass

            time.sleep(1.0)

        if not authenticated:
            raise RuntimeError("Authentication was not completed or the browser was closed.")

        # Save cookies to persistent cookie jar
        cookie_file = get_cookie_file_path()
        os.makedirs(os.path.dirname(cookie_file), exist_ok=True)
        lwp_cj = http.cookiejar.LWPCookieJar(cookie_file)
        for c in captured_cookies:
            lwp_cj.set_cookie(http.cookiejar.Cookie(
                version=0,
                name=c.get("name"),
                value=c.get("value"),
                port=None,
                port_specified=False,
                domain=c.get("domain", "").lstrip("."),
                domain_specified=bool(c.get("domain")),
                domain_initial_dot=c.get("domain", "").startswith("."),
                path=c.get("path", "/"),
                path_specified=True,
                secure=bool(c.get("secure")),
                expires=int(c.get("expires", 0)) if c.get("expires", 0) > 0 else None,
                discard=False,
                comment=None,
                comment_url=None,
                rest={}
            ))
        lwp_cj.save(ignore_discard=True, ignore_expires=True)

        # Create client and query me
        client = LMSClient()
        me = client.get_json("/learn/api/public/v1/users/me")
        return client, me
    finally:
        if ws_sock:
            try:
                ws_sock.close()
            except Exception:
                pass
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        import shutil
        try:
            shutil.rmtree(temp_profile, ignore_errors=True)
        except Exception:
            pass


def get_cookie_file_path():
    """Return the persistent cookie jar file path."""
    if STATE_DIR:
        return os.path.join(STATE_DIR, "session_cookies.txt")
    if sys.platform == "darwin":
        base_dir = os.path.expanduser("~/Library/Application Support/BlackboardSentinel")
    elif sys.platform == "win32":
        appdata = os.getenv("APPDATA", os.path.expanduser("~"))
        base_dir = os.path.join(appdata, "BlackboardSentinel")
    else:
        base_dir = os.path.expanduser("~/.blackboard-sentinel")
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, "session_cookies.txt")


def has_valid_browser_session():
    """Check if a saved cookie file exists and has content."""
    cookie_file = get_cookie_file_path()
    return os.path.isfile(cookie_file) and os.path.getsize(cookie_file) > 10


def is_configured():
    return bool(LMS_URL and (has_valid_browser_session() or (USER_ID and PASSWORD)))


# Initial configuration bootstrap on module load
init_config()

def fetch_all_available_courses(client):
    """Fetch all courses the user was ever enrolled in, sorted recent-to-ancient."""
    discovered = []
    try:
        user_courses = client.get_paginated_json("/learn/api/public/v1/users/me/courses")
        if not user_courses or "results" not in user_courses:
            return []
        for enrollment in user_courses.get("results", []):
            cid = enrollment.get("courseId")
            if not cid:
                continue
            cinfo = client.get_json(f"/learn/api/public/v3/courses/{cid}") or {}
            raw_name = cinfo.get("name") or cinfo.get("courseId") or cid
            clean_name = re.sub(r'[/\\?%*:|"<>]', ' ', raw_name)
            clean_name = re.sub(r'\s+', ' ', clean_name).strip()

            code_m = re.search(r'([0-9]{3}\s+[A-Za-z]+|[A-Za-z]+\s+[0-9]{3})', clean_name)
            code = code_m.group(0) if code_m else ""

            created_raw = cinfo.get("created") or enrollment.get("created") or cinfo.get("modified") or ""
            date_display = ""
            if created_raw:
                try:
                    dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
                    date_display = dt.strftime("%b %Y")
                except Exception:
                    date_display = created_raw[:10]

            display = f"{code}: {clean_name}" if code and code not in clean_name else clean_name
            if date_display:
                display = f"{display}  [{date_display}]"

            discovered.append({
                "id": cid,
                "code": code,
                "name": clean_name,
                "created": created_raw,
                "date_display": date_display,
                "display_name": display
            })
    except Exception as e:
        sys.stderr.write(f"Error fetching course list: {e}\n")

    # Sort recent to ancient
    discovered.sort(key=lambda c: c.get("created") or "", reverse=True)
    return discovered


# Canonical Course Mappings: folder names and instructors
CANONICAL_COURSE_MAP = {
    "601 CSC": {"folder": "AI FUNDAMENTALS", "doctor": "د. عماد الحربي"},
    "602 CSC": {"folder": "Mathematics for Machine Learning", "doctor": "د. محمد زيشان عالم"},
    "605 CSC": {"folder": "advanced programming", "doctor": "د. أحمد مباركي"},
    "608 CSC": {"folder": "research methods", "doctor": "د. محمد الوكيل"},
}


def get_courses_map(client):
    """Dynamically discover enrolled courses from Blackboard, filtered by LMS_COURSES if configured.
    Maps courses to user's canonical folders (e.g. 'AI FUNDAMENTALS') if present, falling back to LMS_STORAGE_DIR."""
    courses_map = {}
    allowed_ids = set()
    courses_cfg = os.getenv("LMS_COURSES", "").strip()
    if courses_cfg:
        allowed_ids = set(x.strip() for x in courses_cfg.split(",") if x.strip())

    default_storage = os.path.normpath(os.path.expanduser("~/Documents/University"))
    configured_storage = os.path.normpath(os.path.abspath(LMS_STORAGE_DIR)) if LMS_STORAGE_DIR else ""
    storage_is_custom = bool(configured_storage and configured_storage != default_storage)

    # Detect user's main Documents folder where canonical course folders live (only for default storage)
    if storage_is_custom:
        doc_candidates = [os.getenv("LMS_DOCUMENTS_DIR", ""), configured_storage]
    else:
        doc_candidates = [
            os.getenv("LMS_DOCUMENTS_DIR", ""),
            "/mnt/c/Users/Percent/Documents",
            r"C:\Users\Percent\Documents",
            os.path.expanduser("~/Documents"),
            os.path.abspath(os.path.join(LMS_STORAGE_DIR, "..")) if LMS_STORAGE_DIR else ""
        ]
    canonical_root = next((d for d in doc_candidates if d and os.path.isdir(os.path.join(d, "AI FUNDAMENTALS"))), None)

    try:
        user_courses = client.get_paginated_json("/learn/api/public/v1/users/me/courses")
        for enrollment in (user_courses or {}).get("results", []):
            cid = enrollment.get("courseId")
            if not cid:
                continue
            if allowed_ids and cid not in allowed_ids:
                continue

            cinfo = client.get_json(f"/learn/api/public/v3/courses/{cid}") or {}
            raw_name = cinfo.get("name") or cinfo.get("courseId") or cid
            clean_name = re.sub(r'[/\\?%*:|"<>]', ' ', raw_name)
            clean_name = re.sub(r'\s+', ' ', clean_name).strip()
            
            code_m = re.search(r'([0-9]{3}\s+[A-Za-z]+|[A-Za-z]+\s+[0-9]{3})', clean_name)
            code = code_m.group(0) if code_m else ""

            # Check if canonical mapping exists
            canonical = CANONICAL_COURSE_MAP.get(code)
            if canonical and canonical_root and os.path.isdir(os.path.join(canonical_root, canonical["folder"])):
                target_dir = os.path.join(canonical_root, canonical["folder"])
                doctor = canonical.get("doctor", "")
            else:
                target_dir = os.path.join(LMS_STORAGE_DIR, clean_name)
                doctor = canonical.get("doctor", "") if canonical else ""

            courses_map[cid] = {
                "id": cid,
                "code": code,
                "name": clean_name,
                "dir": target_dir,
                "doctor": doctor
            }
    except Exception as e:
        print(f"Error discovering courses: {e}", file=sys.stderr)
    return courses_map


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
AST_TZ = timezone(timedelta(hours=3))


def send_to_chat(text, platform=None):
    if not text:
        return
    # When running directly inside a Hermes cron job, stdout is captured and delivered automatically to origin.
    # Out-of-band callers or standalone executions dispatch directly via hermes send:
    if os.getenv("HERMES_JOB_ID"):
        return

    target_platform = platform or os.getenv("HERMES_CHAT_PLATFORM", "whatsapp").strip().lower()

    # Attempt send via hermes CLI directly (WSL / Linux)
    try:
        cmd = ["hermes", "send", "--to", target_platform, text]
        res = subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0:
            return
    except Exception:
        pass

    # If on Windows, delegate to WSL hermes where gateway is active
    if sys.platform == "win32":
        try:
            cmd = ["wsl.exe", "-e", "hermes", "send", "--to", target_platform, text]
            res = subprocess.run(
                cmd,
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if res.returncode == 0:
                return
        except Exception:
            pass


def send_windows_toast(title, message):
    if sys.platform != "win32":
        return
    safe_title = title.replace("'", "''").replace("\n", " ")
    lines = [l.strip() for l in message.strip().split("\n") if l.strip()]
    safe_msg = (" - ".join(lines[:2]) if lines else "Updates detected").replace("'", "''")
    if len(safe_msg) > 160:
        safe_msg = safe_msg[:157] + "..."
    ps_script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $textNodes = $template.GetElementsByTagName('text')
    $textNodes.Item(0).AppendChild($template.CreateTextNode('{safe_title}')) | Out-Null
    $textNodes.Item(1).AppendChild($template.CreateTextNode('{safe_msg}')) | Out-Null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Blackboard Sentinel').Show($toast)
    """
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )
    except Exception:
        pass


def send_macos_notification(title, message):
    if sys.platform != "darwin":
        return
    lines = [l.strip() for l in message.strip().split("\n") if l.strip()]
    safe_msg = (" - ".join(lines[:2]) if lines else "Updates detected")
    if len(safe_msg) > 160:
        safe_msg = safe_msg[:157] + "..."
    script = """
    on run argv
        display notification (item 2 of argv) with title (item 1 of argv) sound name "default"
    end run
    """
    try:
        subprocess.run(["osascript", "-e", script, title, safe_msg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    except Exception:
        pass


def send_notification(text, title="Blackboard Sentinel"):
    if not text:
        return
    # 1. Hermes / Chat push (opt-in, default off)
    if os.getenv("LMS_HERMES_MESSAGING", "false").strip().lower() in ("true", "1", "yes"):
        send_to_chat(text)
    # 2. Windows Native Toast alert
    if sys.platform == "win32":
        send_windows_toast(title, text)
    # 3. macOS Native Notification Center alert
    elif sys.platform == "darwin":
        send_macos_notification(title, text)


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "seen_files": [],
        "seen_files_mtime": {},
        "seen_requests": [],
        "alerted_deadlines": {},
        "seen_announcements": [],
        "seen_grades": {},
        "seen_links": [],
        "expanded_zips": {}
    }


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp_path = STATE_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, STATE_FILE)


DEFAULT_TIMEOUT = 6

URL_REGEX = re.compile(
    r"^(?:https?://)?"
    r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,}"
    r"(?::\d{1,5})?"
    r"(?:/.*)?$",
    re.IGNORECASE
)


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevent automated multi-hop redirect chains that can cause 30+ second hangs."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_blackboard_url(url, timeout=3.0):
    """
    Two-layer pre-flight validation of the Blackboard LMS URL:
      Layer 1: Instant client-side regex check (<1ms)
      Layer 2: Fast Blackboard Learn Ultra signature probe (max 3.0s hard ceiling)
    Accepts both 'lms.university.edu' and 'https://lms.university.edu'.
    """
    raw = (url or "").strip().rstrip("/")
    if not raw:
        raise ValueError("LMS URL cannot be empty.")

    if not URL_REGEX.match(raw):
        raise ValueError(
            f"'{raw}' is not a valid web address.\n\n"
            "Please enter your university LMS domain (e.g. lms.university.edu or https://lms.university.edu)."
        )

    clean = raw if raw.startswith(("http://", "https://")) else f"https://{raw}"

    parsed = urllib.parse.urlparse(clean)
    host = parsed.hostname
    port = parsed.port or (443 if clean.startswith("https") else 80)
    if not host:
        raise ValueError(f"Invalid domain in URL: '{clean}'")

    result = {"error": None, "done": False}

    def _probe_worker():
        import socket
        try:
            # 1. Fast socket connectivity & DNS resolution check (max timeout)
            try:
                s = socket.create_connection((host, port), timeout=timeout)
                s.close()
            except socket.gaierror:
                result["error"] = ValueError(f"Domain does not exist or DNS lookup failed for '{host}'. Please verify spelling.")
                return
            except (socket.timeout, TimeoutError):
                result["error"] = ValueError(f"Connection to '{host}' timed out after {int(timeout)} seconds. Server is unreachable.")
                return
            except ConnectionRefusedError:
                result["error"] = ValueError(f"Connection refused by '{host}'. No web service is running on port {port}.")
                return
            except Exception as e:
                result["error"] = ValueError(f"Could not reach '{host}': {e}")
                return

            # 2. Probe Blackboard Learn Ultra portal signature
            probe_url = f"{clean}/webapps/login/"
            cj = http.cookiejar.CookieJar()
            opener = urllib.request.build_opener(
                NoRedirectHandler(),
                urllib.request.HTTPSHandler(context=_get_ssl_context()),
                urllib.request.HTTPCookieProcessor(cj),
            )
            req = urllib.request.Request(probe_url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            })

            headers_str = ""
            content = ""
            try:
                with opener.open(req, timeout=timeout) as resp:
                    headers_str = str(resp.headers).lower()
                    content = resp.read(32768).decode("utf-8", errors="ignore").lower()
            except urllib.error.HTTPError as e:
                headers_str = str(e.headers).lower() if e.headers else ""
                try:
                    content = e.read(32768).decode("utf-8", errors="ignore").lower()
                except Exception:
                    content = ""
                # If 404 on /webapps/login/ without BB signature, definitely not Blackboard
                if e.code == 404 and "blackboard" not in headers_str and "bb" not in headers_str:
                    result["error"] = ValueError(
                        f"Connected to '{host}', but '/webapps/login/' was not found (HTTP 404).\n\n"
                        "This server is running, but it does not host a Blackboard Learn LMS."
                    )
                    return
            except urllib.error.URLError as e:
                reason = str(e.reason).lower()
                if "timed out" in reason:
                    result["error"] = ValueError(f"Connection to '{host}' timed out after {int(timeout)} seconds. Server is unreachable.")
                elif "connection refused" in reason:
                    result["error"] = ValueError(f"Connection refused by '{host}'.")
                elif "certificate" in reason or "ssl" in reason:
                    result["error"] = ValueError(f"SSL certificate error connecting to '{host}': {e.reason}")
                else:
                    result["error"] = ValueError(f"Could not connect to '{host}': {e.reason}")
                return

            bb_indicators = ["blackboard", "nonceutil", "bb-root", "loginform", "learn/api", "bb_product", "jsessionid"]
            has_sig = any(k in content for k in bb_indicators) or any(k in headers_str for k in ["blackboard", "jsessionid", "bb-"])

            if not has_sig:
                result["error"] = ValueError(
                    f"Connected to '{host}', but this does NOT appear to be a Blackboard Learn Ultra portal.\n\n"
                    "No Blackboard gateway signatures were detected. Please ensure you entered your university LMS login portal URL (e.g. lms.university.edu)."
                )
                return

            result["done"] = True
        except Exception as ex:
            result["error"] = ex

    import threading
    t = threading.Thread(target=_probe_worker, daemon=True)
    t.start()
    t.join(timeout=timeout + 0.5)

    if not result["done"]:
        if result["error"]:
            raise result["error"]
        raise ValueError(f"Connection to '{host}' timed out after {int(timeout)} seconds. Server is unreachable.")

    return clean


class FileTooLargeError(Exception):
    """Raised when a file exceeds the user-configured size cap (LMS_MAX_FILE_SIZE_MB)."""

    def __init__(self, size_bytes):
        super().__init__(f"{size_bytes} bytes exceeds the configured size limit")
        self.size_bytes = size_bytes


class LMSClient:
    def __init__(self, username="", password=""):
        self.username = username
        self.password = password
        self.cookie_file = get_cookie_file_path()
        self.cj = http.cookiejar.LWPCookieJar(self.cookie_file)
        # Attempt to load existing persistent cookies if available
        if os.path.exists(self.cookie_file):
            try:
                self.cj.load(ignore_discard=True, ignore_expires=True)
            except Exception:
                pass
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=_get_ssl_context()),
            urllib.request.HTTPCookieProcessor(self.cj),
        )
        self._columns_cache = {}

    def save_cookies(self):
        """Persist cookies to disk."""
        try:
            os.makedirs(os.path.dirname(self.cookie_file), exist_ok=True)
            self.cj.save(ignore_discard=True, ignore_expires=True)
        except Exception:
            pass

    def get_columns(self, cid):
        """Gradebook column list for a course, fetched at most once per client (shared by grades and deadlines)."""
        if cid not in self._columns_cache:
            self._columns_cache[cid] = self.get_paginated_json(f"/learn/api/public/v2/courses/{cid}/gradebook/columns")
        return self._columns_cache[cid]

    def login(self, timeout=DEFAULT_TIMEOUT):
        validate_blackboard_url(LMS_URL, timeout=5)

        # Check if saved browser session cookies are already valid
        if os.path.exists(self.cookie_file):
            try:
                me_data = self.get_json("/learn/api/public/v1/users/me", timeout=timeout)
                if me_data and "id" in me_data:
                    self.student_user_id = me_data["id"]
                    if me_data.get("userName") and not self.username:
                        self.username = me_data["userName"]
                    return True
            except Exception:
                pass

        if not self.username or not self.password:
            raise ValueError(
                "Browser session expired or credentials missing. Please sign in again or use 'Sign in through web portal'."
            )

        req = urllib.request.Request(f"{LMS_URL}/webapps/login/", headers={"User-Agent": USER_AGENT})
        with self.opener.open(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        nonce_m = re.search(r'name="blackboard\.platform\.security\.NonceUtil\.nonce\.ajax"\s+value="([^"]+)"', html)
        nonce = nonce_m.group(1) if nonce_m else ""

        post_data = {
            "user_id": self.username,
            "password": self.password,
            "login": "تسجيل الدخول",
            "action": "login",
            "new_loc": ""
        }
        if nonce:
            post_data["blackboard.platform.security.NonceUtil.nonce.ajax"] = nonce

        data = urllib.parse.urlencode(post_data).encode("utf-8")
        post_req = urllib.request.Request(
            f"{LMS_URL}/webapps/login/",
            data=data,
            headers={
                "User-Agent": USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": f"{LMS_URL}/webapps/login/",
                "Origin": LMS_URL
            }
        )

        with self.opener.open(post_req, timeout=timeout) as resp:
            final_url = resp.geturl()
            if "login" in final_url.lower() or "relogin" in final_url.lower() or "loginerror" in final_url.lower():
                raise ValueError("Invalid username or password. Please check your student ID and password.")
        self.save_cookies()
        self.student_user_id = ""
        try:
            me_data = self.get_json("/learn/api/public/v1/users/me")
            if me_data and "id" in me_data:
                self.student_user_id = me_data["id"]
        except Exception:
            pass
        return True

    def get_json(self, path_or_url, timeout=DEFAULT_TIMEOUT):
        url = path_or_url if path_or_url.startswith("http") else f"{LMS_URL}{path_or_url}"
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*"
        })
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="ignore"))
        except Exception:
            return None

    def get_paginated_json(self, path_or_url, timeout=DEFAULT_TIMEOUT, max_pages=50):
        """Fetch a Blackboard REST collection and follow paging.nextPage links."""
        data = self.get_json(path_or_url, timeout=timeout)
        if not isinstance(data, dict) or "results" not in data:
            return data
        all_results = list(data.get("results") or [])
        seen_urls = {path_or_url}
        next_page = (data.get("paging") or {}).get("nextPage")
        pages = 1
        while next_page and next_page not in seen_urls and pages < max_pages:
            seen_urls.add(next_page)
            page_data = self.get_json(next_page, timeout=timeout)
            pages += 1
            if not isinstance(page_data, dict) or "results" not in page_data:
                break
            all_results.extend(page_data.get("results") or [])
            next_page = (page_data.get("paging") or {}).get("nextPage")
        return {"results": all_results}

    def download_file(self, path_or_url, dest_path, max_bytes=0, timeout=60):
        url = path_or_url if path_or_url.startswith("http") else f"{LMS_URL}{path_or_url}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        tmp_dest = dest_path + ".part"
        with self.opener.open(req, timeout=timeout) as resp:
            cl = resp.headers.get("Content-Length")
            expected_bytes = int(cl) if cl and cl.isdigit() else None
            if max_bytes and expected_bytes is not None and expected_bytes > max_bytes:
                raise FileTooLargeError(expected_bytes)
            downloaded = 0
            with open(tmp_dest, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if max_bytes and downloaded > max_bytes:
                        break

        if max_bytes and downloaded > max_bytes:
            # Size was not advertised up front; abort once the cap is exceeded.
            try:
                os.remove(tmp_dest)
            except Exception:
                pass
            raise FileTooLargeError(downloaded)

        if expected_bytes is not None and downloaded != expected_bytes:
            if os.path.exists(tmp_dest):
                try:
                    os.remove(tmp_dest)
                except Exception:
                    pass
            raise IOError(f"Incomplete download for {dest_path}: got {downloaded} bytes, expected {expected_bytes}")

        os.replace(tmp_dest, dest_path)


def clean_html(text):
    if not text:
        return ""
    clean = re.sub(r'(?is)<style.*?>.*?</style>', '', text)
    clean = re.sub(r'(?is)<script.*?>.*?</script>', '', clean)
    clean = re.sub(r'<br\s*/?>', '\n', clean)
    clean = re.sub(r'</p>', '\n\n', clean)
    clean = re.sub(r'<[^>]+>', ' ', clean)
    clean = re.sub(r'&nbsp;', ' ', clean)
    clean = re.sub(r'&amp;', '&', clean)
    clean = re.sub(r'&lt;', '<', clean)
    clean = re.sub(r'&gt;', '>', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def extract_structured_text(raw_html):
    """Convert Blackboard HTML instructions/body into readable multi-line Markdown text."""
    if not raw_html:
        return ""
    text = re.sub(r'(?is)<style.*?>.*?</style>', '', raw_html)
    text = re.sub(r'(?is)<script.*?>.*?</script>', '', text)
    text = re.sub(r'(?i)<br\s*/?>', '\n', text)
    text = re.sub(r'(?i)</p>', '\n\n', text)
    text = re.sub(r'(?i)</div>', '\n', text)
    text = re.sub(r'(?i)</h[1-6]>', '\n\n', text)
    text = re.sub(r'(?i)<li[^>]*>', '\n- ', text)
    text = re.sub(r'(?i)</li>', '\n', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    lines = [re.sub(r'[ \t]+', ' ', ln).strip() for ln in text.splitlines()]
    cleaned_lines = []
    blank_count = 0
    for ln in lines:
        if not ln:
            blank_count += 1
            if blank_count <= 1:
                cleaned_lines.append("")
        else:
            blank_count = 0
            cleaned_lines.append(ln)
    return "\n".join(cleaned_lines).strip()


def sanitize_filename(fn):
    if not fn:
        return ""
    # Strip invisible RTL / LTR formatting characters
    fn = re.sub(r'[\u200e\u200f\u202a-\u202e]', '', fn).strip()
    # Strip dangerous characters for Windows NTFS
    return re.sub(r'[\\/*?:"<>|]', '_', fn)


REQUEST_KEYWORDS = [
    r"\bproject\b", r"\bprojects\b",
    r"\bhomework\b", r"\bhw\d*\b",
    r"\bassignment\b", r"\bassignments\b",
    r"\btask\b", r"\btasks\b",
    r"\bexercise\b", r"\bexercises\b", r"\bexercies\b",
    r"\blab\b", r"\blabs\b",
    r"\bworksheet\b", r"\bproblem\s*set\b",
    r"مشروع", r"واجب", r"تكليف", r"تمرين", r"تمارين", r"مهمة", r"عملي"
]

EXCLUDE_KEYWORDS = [
    r"\bsolution\b", r"\bsolutions\b",
    r"\brevision\b", r"\bsyllabus\b",
    r"\borientation\b", r"\bguideline\b", r"\bguidelines\b",
    r"\bdescription\b", r"\bslides\b",
    r"\bmock\s*midterm\b", r"\bmid\s*term\b", r"\bfinal\s*exam\b",
    r"\blecture\s*examples?\b", r"\bexample\s*\d+\b"
]

NON_REQUEST_PARENTS = [
    "lectures", "lecture", "lecture examples", "slides and course contents",
    "course material", "course description", "very important instructions"
]


def is_request_item(item, parent_title=""):
    """Determine if a Blackboard item is a request (project, homework, task, exercise, assignment, lab)."""
    title = item.get("title", "") or ""
    title_clean = re.sub(r"[\u200e\u200f\u202a-\u202e]", "", title).strip()
    title_norm = re.sub(r"[_\-.]+", " ", title_clean.lower())
    parent_lower = (parent_title or "").strip().lower()

    handler = item.get("contentHandler", {}) or {}
    handler_id = (handler.get("id", "") or "").lower()

    if any(p in parent_lower for p in NON_REQUEST_PARENTS):
        return False

    if any(re.search(pat, title_norm) for pat in EXCLUDE_KEYWORDS):
        return False

    # 1. Blackboard Assessment / Assignment / Submission item
    if any(x in handler_id for x in ["asmt", "assignment", "turnitin"]):
        return True

    # 2. Content item / file / folder with request keywords in title
    if any(re.search(pat, title_norm) for pat in REQUEST_KEYWORDS):
        return True

    return False


def is_request_announcement(title, body="", attached_files=None):
    """Determine if an announcement represents an actionable assignment, homework, task, exercise, or project."""
    title_clean = re.sub(r"[\u200e\u200f\u202a-\u202e]", "", title or "").strip()
    title_norm = re.sub(r"[_\-.]+", " ", title_clean.lower())
    body_clean = re.sub(r"[\u200e\u200f\u202a-\u202e]", "", body or "").strip()
    body_norm = re.sub(r"[_\-.]+", " ", body_clean.lower())

    if any(re.search(pat, title_norm) for pat in EXCLUDE_KEYWORDS):
        return False

    if any(re.search(pat, title_norm) for pat in REQUEST_KEYWORDS):
        return True

    for pat in REQUEST_KEYWORDS:
        if re.search(pat, body_norm):
            return True

    if attached_files:
        for af in attached_files:
            af_name = (af.get("filename") or "") if isinstance(af, dict) else str(af)
            af_clean = re.sub(r"[\u200e\u200f\u202a-\u202e]", "", af_name).strip()
            af_norm = re.sub(r"[_\-.]+", " ", af_clean.lower())
            if any(re.search(pat, af_norm) for pat in REQUEST_KEYWORDS):
                return True

    return False


def get_request_folder_name(raw_title):
    """Return sanitized Blackboard request name for folder creation."""
    name = sanitize_filename(raw_title)
    name = re.sub(r"\.(ipynb|pdf|docx?|pptx?|xlsx?|zip|rar|py|txt|csv)$", "", name, flags=re.IGNORECASE)
    name = name.rstrip(". ").strip()
    return name or "Request"


def to_windows_path(path):
    if sys.platform == "win32":
        return os.path.normpath(path)
    try:
        res = subprocess.run(
            ["wslpath", "-w", path],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return path


def get_existing_filenames_on_disk(base_dir):
    existing = set()
    if os.path.exists(base_dir):
        for root, dirs, files in os.walk(base_dir):
            if ".venv" in root or ".idea" in root or "node_modules" in root:
                continue
            for f in files:
                cleaned = re.sub(r'[\u200e\u200f\u202a-\u202e]', '', f).strip().lower()
                existing.add(cleaned)
    return existing


def find_target_subfolder(base_dir, context_hint):
    if not os.path.exists(base_dir) or not context_hint:
        return base_dir
    hint_clean = re.sub(r'[^a-zA-Z0-9\u0600-\u06FF]+', ' ', context_hint).strip().lower()
    for entry in os.listdir(base_dir):
        full = os.path.join(base_dir, entry)
        if os.path.isdir(full):
            if entry.startswith(".") or entry in ["node_modules", "data"]:
                continue
            entry_clean = re.sub(r'[^a-zA-Z0-9\u0600-\u06FF]+', ' ', entry).strip().lower()
            if entry_clean and (entry_clean in hint_clean or hint_clean in entry_clean):
                return full
    return base_dir


_ZIP_MAX_DEPTH = 3
_ZIP_MAX_ENTRIES = 10_000
_ZIP_MAX_BYTES = 2 * 1024 * 1024 * 1024
_ZIP_BOMB_RATIO = 100
_ZIP_BOMB_MIN_BYTES = 100 * 1024 * 1024
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_OS_JUNK_NAMES = {"__macosx", ".ds_store", "thumbs.db", "desktop.ini"}
_GENERIC_WRAPPER_DIRS = {
    "files", "file", "folder", "folders", "content", "contents",
    "archive", "archives", "root", "extracted", "output",
    "download", "downloads", "upload", "uploads", "attachment", "attachments",
}
_GENERIC_DOC_WORDS = {
    "slide", "slides", "lecture", "lectures", "lec", "lecs", "note", "notes",
    "doc", "docs", "document", "documents", "file", "files", "attachment", "attachments",
    "report", "paper", "assignment", "assignments", "hw", "homework", "lab", "labs",
    "task", "tasks", "exercise", "exercises", "project", "solution", "solutions", "sol",
    "answer", "answers", "handout", "worksheet", "syllabus", "outline", "summary",
    "review", "guide", "instruction", "instructions", "readme", "index", "main", "app",
    "code", "script", "data", "dataset", "sheet", "table", "presentation", "deck",
    "exam", "quiz", "midterm", "final", "test", "practice", "sample", "example",
    "template", "untitled", "new", "download", "scan", "page", "part", "ch", "chapter",
    "week", "module", "unit", "lesson", "session", "section", "output", "result",
    "draft", "version", "ver", "copy", "updated", "revised", "v",
    "ملف", "محاضرة", "واجب", "ملخص", "سلايدات", "مستند", "حل", "تقرير", "ورقة", "نموذج",
}


def _win_long_path(path):
    """Add the Windows extended-length prefix when an absolute path approaches MAX_PATH."""
    if sys.platform != "win32":
        return path
    abspath = os.path.abspath(path)
    if abspath.startswith("\\\\?\\") or len(abspath) < 240:
        return path
    if abspath.startswith("\\\\"):
        return "\\\\?\\UNC\\" + abspath.lstrip("\\")
    return "\\\\?\\" + abspath


def _rmtree_readonly_safe(path):
    """Remove a directory tree even when extracted archive entries are marked read-only."""
    target = _win_long_path(path)
    if not os.path.exists(target):
        return

    def _make_writable(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
            func(p)
        except Exception:
            pass

    if sys.version_info >= (3, 12):
        shutil.rmtree(target, onexc=_make_writable)
    else:
        shutil.rmtree(target, onerror=_make_writable)


def _decode_zip_member_name(member):
    """Recover UTF-8, CP1256 (Arabic), or CP1252 filenames when the zip UTF-8 flag is unset."""
    name = member.filename
    if (member.flag_bits & 0x800) or name.isascii():
        return name
    try:
        raw = name.encode("cp437")
    except UnicodeEncodeError:
        return name
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    # Box-drawing / Greek / math chars are strong indicators of CP1256 or CP1252 bytes decoded as CP437
    has_cp437_artifacts = any(
        ("\u2500" <= ch <= "\u259f") or ("\u0391" <= ch <= "\u03c9") or ("\u2200" <= ch <= "\u22ff")
        for ch in name
    )
    if has_cp437_artifacts:
        try:
            cp1256_text = raw.decode("cp1256")
            if any("\u0600" <= ch <= "\u06ff" for ch in cp1256_text):
                return cp1256_text
        except UnicodeDecodeError:
            pass
        try:
            cp1252_text = raw.decode("cp1252")
            if cp1252_text.isprintable():
                return cp1252_text
        except UnicodeDecodeError:
            pass
    return name


def _sanitize_zip_segment(seg):
    """Sanitize a single path segment for safe Windows and POSIX filesystem extraction."""
    seg = re.sub(r"[\u200e\u200f\u202a-\u202e]", "", seg)
    seg = re.sub(r'[\\/*?:"<>|\x00-\x1f]', "_", seg).strip()
    seg = seg.rstrip(". ")
    if not seg:
        return "_"
    stem = seg.split(".", 1)[0].upper()
    if stem in _WINDOWS_RESERVED_NAMES:
        seg = f"_{seg}"
    return seg


def _parse_zip_member_parts(raw_name):
    """Normalize an archive path into sanitized segments, returning None for traversal or OS junk."""
    normalized = raw_name.replace("\\", "/")
    if re.match(r"^[a-zA-Z]:", normalized):
        normalized = normalized[2:]
    normalized = normalized.lstrip("/")
    raw_parts = [p for p in normalized.split("/") if p and p != "."]
    if not raw_parts or any(p == ".." for p in raw_parts):
        return None
    for idx, part in enumerate(raw_parts):
        low = part.lower()
        if low in _OS_JUNK_NAMES:
            return None
        if idx == len(raw_parts) - 1 and low.startswith("._"):
            return None
    return [_sanitize_zip_segment(p) for p in raw_parts]


def _norm_archive_name(name):
    """Normalize a folder or document stem for fuzzy matching across separators."""
    return re.sub(r"[^a-z0-9\u0600-\u06ff]+", "", name.lower())


def _is_generic_doc_name(filename, zip_stem):
    """Return True when a single extracted document has a generic name lacking zip context."""
    doc_stem, _ = os.path.splitext(filename)
    norm_doc = _norm_archive_name(doc_stem)
    norm_zip = _norm_archive_name(zip_stem)
    if norm_zip and len(norm_zip) >= 3 and (norm_doc == norm_zip or norm_zip in norm_doc):
        return False
    if not norm_doc or len(norm_doc) <= 3 or norm_doc.isdigit():
        return True
    tokens = [t for t in re.split(r"[^a-zA-Z0-9\u0600-\u06ff]+", doc_stem.lower()) if t]
    meaningful_tokens = [t for t in tokens if not t.isdigit() and not re.fullmatch(r"v\d+", t)]
    if not meaningful_tokens:
        return True
    return all(t in _GENERIC_DOC_WORDS for t in meaningful_tokens)


def _collapse_common_dirs(dir_chains, zip_stem):
    """
    Compute the common directory chain shared by all archive files, strip directories
    matching the zip stem or generic wrappers, and collapse multi-level single-child
    chains down to at most the innermost distinct directory.
    """
    if not dir_chains:
        return [], 0
    common = list(dir_chains[0])
    for chain in dir_chains[1:]:
        limit = min(len(common), len(chain))
        i = 0
        while i < limit and common[i] == chain[i]:
            i += 1
        common = common[:i]
        if not common:
            break
    if not common:
        return [], 0

    norm_zip = _norm_archive_name(zip_stem)
    distinct = [
        d for d in common
        if _norm_archive_name(d) != norm_zip and d.lower() not in _GENERIC_WRAPPER_DIRS
    ]
    kept_prefix = [distinct[-1]] if distinct else []
    return kept_prefix, len(common)


def _files_identical(path_a, path_b):
    """Return True if two files exist and have identical size and SHA-256 content."""
    pa = _win_long_path(path_a)
    pb = _win_long_path(path_b)
    if not (os.path.isfile(pa) and os.path.isfile(pb)):
        return False
    if os.path.getsize(pa) != os.path.getsize(pb):
        return False

    def _sha256(p):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    return _sha256(pa) == _sha256(pb)


def _merge_tree_into(src_dir, dst_dir):
    """Move extracted contents from staging directory into dst_dir, overwriting colliding files."""
    os.makedirs(_win_long_path(dst_dir), exist_ok=True)
    for root, dirs, files in os.walk(src_dir):
        rel_root = os.path.relpath(root, src_dir)
        dst_root = dst_dir if rel_root == "." else os.path.join(dst_dir, rel_root)
        os.makedirs(_win_long_path(dst_root), exist_ok=True)
        for d in dirs:
            os.makedirs(_win_long_path(os.path.join(dst_root, d)), exist_ok=True)
        for fname in files:
            src_file = _win_long_path(os.path.join(root, fname))
            dst_file = _win_long_path(os.path.join(dst_root, fname))
            if os.path.isdir(dst_file):
                _rmtree_readonly_safe(dst_file)
            os.replace(src_file, dst_file)


def _inspect_zip_plan(zf, zip_stem, budget):
    """
    Validate archive members against encryption, symlink, and zip-bomb limits, then
    classify the extraction layout as 'encrypted', 'bomb', 'empty', 'single_doc', or 'dir'.
    """
    valid_files = []
    for member in zf.infolist():
        if member.flag_bits & 0x1:
            return "encrypted", [], []
        mode = (member.external_attr >> 16) & 0o170000
        if stat.S_ISLNK(mode):
            continue
        decoded_name = _decode_zip_member_name(member)
        if member.is_dir() or decoded_name.replace("\\", "/").endswith("/"):
            continue
        parts = _parse_zip_member_parts(decoded_name)
        if not parts:
            continue
        if budget["entries_used"] + len(valid_files) + 1 > budget["max_entries"]:
            return "bomb", [], []
        if member.file_size < 0 or budget["bytes_used"] + member.file_size > budget["max_bytes"]:
            return "bomb", [], []
        if (
            member.file_size > _ZIP_BOMB_MIN_BYTES
            and member.compress_size > 0
            and (member.file_size / member.compress_size) > _ZIP_BOMB_RATIO
        ):
            return "bomb", [], []
        valid_files.append((member, parts))

    if not valid_files:
        return "empty", [], []

    kept_prefix, strip_len = _collapse_common_dirs([parts[:-1] for _, parts in valid_files], zip_stem)
    planned = [(member, kept_prefix + parts[strip_len:]) for member, parts in valid_files]

    if len(planned) == 1 and not kept_prefix and len(planned[0][1]) == 1:
        only_name = planned[0][1][0]
        if not only_name.lower().endswith(".zip") and not _is_generic_doc_name(only_name, zip_stem):
            return "single_doc", planned, []

    return "dir", planned, []


def get_zip_extract_dir(zip_path):
    """Return the target extraction folder '<stem>_zip' in the same directory as zip_path."""
    parent = os.path.dirname(zip_path)
    base = os.path.basename(zip_path)
    stem, ext = os.path.splitext(base)
    if ext.lower() == ".zip":
        return os.path.join(parent, f"{stem}_zip")
    return os.path.join(parent, f"{base}_zip")


def _resolve_recorded_zip_path(expanded_zips, key, base_dir, fallback_zip_path=None):
    """Resolve a previously expanded zip target (file or directory) if it still exists on disk."""
    val = expanded_zips.get(key) if expanded_zips else None
    if val:
        candidate = val if os.path.isabs(val) else os.path.join(base_dir, val)
        if os.path.exists(_win_long_path(candidate)):
            return candidate
    if fallback_zip_path and fallback_zip_path.lower().endswith(".zip"):
        fallback_dir = get_zip_extract_dir(fallback_zip_path)
        if os.path.isdir(_win_long_path(fallback_dir)):
            return fallback_dir
    return None


def _record_expanded_zip_path(expanded_zips, key, base_dir, dest_path):
    """Persist the expanded file or directory path relative to the course directory when possible."""
    if not dest_path:
        return
    try:
        rel = os.path.relpath(dest_path, base_dir)
        expanded_zips[key] = dest_path if rel.startswith("..") else rel
    except ValueError:
        expanded_zips[key] = dest_path


def expand_zip_archive(zip_path, bb_ts=None, allow_overwrite=False, _depth=0, _budget=None):
    """
    Smartly expand a .zip archive when EXPAND_ZIPS is enabled.

    Handles single-folder unwrapping, multi-level single-child chain collapsing,
    preserving differently-named inner folders inside '<stem>_zip', keeping generic
    single documents inside '<stem>_zip', unwrapping descriptive single documents,
    skipping empty/encrypted/corrupt archives without deletion, recursive nested
    zips (up to _ZIP_MAX_DEPTH), OS junk filtering, and zip-slip/zip-bomb guards.
    Returns the final extracted file or folder path on success, or None.
    """
    if not EXPAND_ZIPS or not zip_path.lower().endswith(".zip") or not os.path.isfile(zip_path):
        return None
    if _depth > _ZIP_MAX_DEPTH:
        return None

    budget = _budget if _budget is not None else {
        "entries_used": 0,
        "bytes_used": 0,
        "max_entries": _ZIP_MAX_ENTRIES,
        "max_bytes": _ZIP_MAX_BYTES,
    }
    parent_dir = os.path.dirname(os.path.abspath(zip_path)) or "."
    zip_stem = os.path.splitext(os.path.basename(zip_path))[0]
    extract_dir = get_zip_extract_dir(zip_path)
    staging_dir = None

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            plan_kind, planned, _ = _inspect_zip_plan(zf, zip_stem, budget)
            if plan_kind in ("empty", "encrypted", "bomb"):
                if plan_kind == "bomb":
                    sys.stderr.write(f"Skipped zip archive {os.path.basename(zip_path)}: size/entry limit exceeded\n")
                return None

            os.makedirs(_win_long_path(parent_dir), exist_ok=True)
            staging_dir = tempfile.mkdtemp(prefix=".tmp_zip_", dir=parent_dir)
            real_stage = os.path.realpath(staging_dir)

            for member, rel_parts in planned:
                budget["entries_used"] += 1
                dest_path = os.path.realpath(os.path.join(staging_dir, *rel_parts))
                if dest_path != real_stage and not dest_path.startswith(real_stage + os.sep):
                    continue
                os.makedirs(_win_long_path(os.path.dirname(dest_path)), exist_ok=True)
                with zf.open(member, "r") as src, open(_win_long_path(dest_path), "wb") as dst:
                    while True:
                        chunk = src.read(65536)
                        if not chunk:
                            break
                        budget["bytes_used"] += len(chunk)
                        if budget["bytes_used"] > budget["max_bytes"]:
                            raise ValueError("Archive uncompressed size exceeded safety budget")
                        dst.write(chunk)
                try:
                    dt = member.date_time
                    if dt and dt[0] >= 1980:
                        ts = time.mktime((dt[0], dt[1], dt[2], dt[3], dt[4], dt[5], 0, 0, -1))
                        os.utime(_win_long_path(dest_path), (ts, ts))
                except Exception:
                    pass

        if _depth < _ZIP_MAX_DEPTH:
            nested_zips = []
            for root, _dirs, files in os.walk(staging_dir):
                for fname in files:
                    if fname.lower().endswith(".zip"):
                        nested_zips.append(os.path.join(root, fname))
            for nz in nested_zips:
                expand_zip_archive(
                    nz,
                    bb_ts=bb_ts,
                    allow_overwrite=True,
                    _depth=_depth + 1,
                    _budget=budget,
                )

        final_dest = extract_dir
        if plan_kind == "single_doc":
            doc_name = planned[0][1][0]
            staged_doc = os.path.join(staging_dir, doc_name)
            candidate_doc = os.path.join(parent_dir, doc_name)
            if os.path.exists(_win_long_path(candidate_doc)):
                if os.path.isfile(_win_long_path(candidate_doc)) and (
                    allow_overwrite or _files_identical(staged_doc, candidate_doc)
                ):
                    os.replace(_win_long_path(staged_doc), _win_long_path(candidate_doc))
                    final_dest = candidate_doc
                else:
                    # Do not overwrite an unrelated file; keep safely inside <stem>_zip
                    _merge_tree_into(staging_dir, extract_dir)
                    final_dest = extract_dir
            else:
                os.replace(_win_long_path(staged_doc), _win_long_path(candidate_doc))
                final_dest = candidate_doc
        else:
            _merge_tree_into(staging_dir, extract_dir)
            final_dest = extract_dir

        if bb_ts:
            try:
                os.utime(_win_long_path(final_dest), (bb_ts, bb_ts))
            except Exception:
                pass
        if DELETE_ORIGINAL_ZIP:
            try:
                os.remove(_win_long_path(zip_path))
            except Exception:
                pass
        return final_dest
    except (zipfile.BadZipFile, RuntimeError, zlib.error, EOFError, OSError, ValueError) as e:
        sys.stderr.write(f"Error expanding zip archive {os.path.basename(zip_path)}: {e}\n")
        return None
    finally:
        if staging_dir and os.path.exists(_win_long_path(staging_dir)):
            try:
                _rmtree_readonly_safe(staging_dir)
            except Exception:
                pass


def check_and_download_course_files(client, cid, info, state):
    downloads = []
    new_requests = []
    external_links = []
    base_dir = info["dir"]
    existing_files_lower = get_existing_filenames_on_disk(base_dir)
    seen_files_set = set(state.get("seen_files", []))
    seen_files_mtime = state.setdefault("seen_files_mtime", {})
    seen_requests_set = set(state.get("seen_requests", []))
    seen_links_set = set(state.get("seen_links", []))
    skipped_large = state.setdefault("skipped_large", {})
    expanded_zips = state.setdefault("expanded_zips", {})

    cloud_link_re = re.compile(
        r'href=["\'](https?://(?:www\.)?(?:drive\.google\.com|docs\.google\.com|sharepoint\.com|1drv\.ms|onedrive\.live\.com|youtube\.com|youtu\.be|colab\.research\.google\.com|kaltura\.com|github\.com)[^\s"\'<>]+)["\']',
        re.IGNORECASE
    )

    def process_file_candidate(item_id, file_id, raw_fname, download_url, context, item_modified=None, request_ctx=None):
        fname_clean = sanitize_filename(raw_fname)
        if not fname_clean:
            return

        file_key = f"{cid}_{item_id}_{file_id}_{fname_clean}"
        fname_lower = fname_clean.lower()

        if request_ctx is not None:
            target_dir = request_ctx["req_dir"]
        else:
            if "csc605.zip" in fname_lower and "lecture 1.ipynb" in existing_files_lower:
                seen_files_set.add(file_key)
                if item_modified:
                    seen_files_mtime[file_key] = item_modified
                return
            target_dir = os.path.join(base_dir, context) if context else base_dir
            if context:
                flat_root_path = os.path.join(base_dir, fname_clean)
                if not os.path.exists(os.path.join(target_dir, fname_clean)) and os.path.exists(flat_root_path):
                    try:
                        import shutil
                        os.makedirs(target_dir, exist_ok=True)
                        shutil.move(flat_root_path, os.path.join(target_dir, fname_clean))
                    except Exception:
                        pass

        target_path = os.path.join(target_dir, fname_clean)
        recorded_zip_dest = (
            _resolve_recorded_zip_path(expanded_zips, file_key, base_dir, fallback_zip_path=target_path)
            if fname_lower.endswith(".zip")
            else None
        )

        # Revision Detection (Item 1)
        bb_ts = None
        if item_modified:
            try:
                bb_ts = datetime.fromisoformat(item_modified.replace("Z", "+00:00")).timestamp()
            except Exception:
                pass

        is_revision = False
        existing_check_path = target_path if os.path.exists(target_path) else recorded_zip_dest
        if existing_check_path:
            local_ts = os.path.getmtime(existing_check_path)
            prev_mtime = seen_files_mtime.get(file_key)
            if bb_ts and local_ts and (bb_ts > local_ts + 60 or (prev_mtime and item_modified != prev_mtime)):
                is_revision = True
            else:
                seen_files_set.add(file_key)
                if item_modified:
                    seen_files_mtime[file_key] = item_modified
                present_name = os.path.basename(existing_check_path)
                if request_ctx is not None and present_name not in request_ctx["files"]:
                    request_ctx["files"].append(present_name)
                return

        # Size-based skip (disabled unless LMS_MAX_FILE_SIZE_MB > 0)
        if MAX_FILE_BYTES and skipped_large.get(file_key, 0) > MAX_FILE_BYTES:
            return

        try:
            client.download_file(download_url, target_path, max_bytes=MAX_FILE_BYTES)
            skipped_large.pop(file_key, None)
            if bb_ts:
                try:
                    os.utime(target_path, (bb_ts, bb_ts))
                except Exception:
                    pass
            extracted_dest = expand_zip_archive(
                target_path,
                bb_ts=bb_ts,
                allow_overwrite=is_revision or (recorded_zip_dest is not None),
            )
            if extracted_dest:
                _record_expanded_zip_path(expanded_zips, file_key, base_dir, extracted_dest)
            final_saved_path = extracted_dest if (extracted_dest and DELETE_ORIGINAL_ZIP) else target_path
            seen_files_set.add(file_key)
            if item_modified:
                seen_files_mtime[file_key] = item_modified
            existing_files_lower.add(fname_lower)
            if request_ctx is not None:
                rec_name = os.path.basename(final_saved_path)
                if rec_name not in request_ctx["files"]:
                    request_ctx["files"].append(rec_name)
            try:
                rel_saved = os.path.relpath(final_saved_path, LMS_STORAGE_DIR)
            except ValueError:
                rel_saved = final_saved_path
            downloads.append({
                "course": f"{info['name']} ({info['code']})",
                "doctor": info["doctor"],
                "file": fname_clean,
                "saved": rel_saved,
                "is_request": request_ctx is not None,
                "is_update": is_revision
            })
        except FileTooLargeError as big:
            skipped_large[file_key] = big.size_bytes
            sys.stderr.write(f"Skipped {fname_clean}: {big.size_bytes / 1048576:.1f} MB exceeds limit of {MAX_FILE_BYTES / 1048576:.1f} MB\n")
        except Exception as dl_err:
            sys.stderr.write(f"Download error for {fname_clean}: {dl_err}\n")

    def extract_and_download_item_files(item, path_hint, request_ctx=None):
        item_id = item.get("id")
        title = item.get("title", "")
        handler = item.get("contentHandler", {}) or {}
        item_modified = item.get("modified")

        # 1. Direct attachments
        att_data = client.get_paginated_json(f"/learn/api/public/v1/courses/{cid}/contents/{item_id}/attachments")
        if att_data and "results" in att_data:
            for att in att_data["results"]:
                att_id = att.get("id")
                fname = att.get("fileName") or title
                dl_url = f"/learn/api/public/v1/courses/{cid}/contents/{item_id}/attachments/{att_id}/download"
                process_file_candidate(item_id, att_id, fname, dl_url, path_hint, item_modified=item_modified, request_ctx=request_ctx)

        # 2. Embedded data-bbfile attachments in instructions or body
        for html_source in [handler.get("instructions", ""), item.get("body", "")]:
            if not html_source:
                continue
            bb_files = re.findall(r'data-bbfile="([^"]+)"', html_source)
            for bf in bb_files:
                try:
                    clean_bf = urllib.parse.unquote(bf).replace("&quot;", '"')
                    obj = json.loads(clean_bf)
                    emb_name = obj.get("fileName") or obj.get("displayName") or obj.get("linkName")
                    emb_url = obj.get("resourceUrl")
                    if emb_name and emb_url:
                        process_file_candidate(item_id, f"emb_{emb_name}", emb_name, emb_url, path_hint, item_modified=item_modified, request_ctx=request_ctx)
                except Exception:
                    pass

    def collect_item_text_instructions(item, request_ctx):
        handler = item.get("contentHandler", {}) or {}
        for label, raw_html in [
            ("Instructions", handler.get("instructions", "")),
            ("Description / Body", item.get("body", "")),
            ("Details", item.get("description", ""))
        ]:
            txt = extract_structured_text(raw_html)
            if txt and txt not in request_ctx["instructions_parts"]:
                request_ctx["instructions_parts"].append(txt)

    def traverse_contents(parent_id=None, current_rel_dir="", active_request=None):
        url = f"/learn/api/public/v1/courses/{cid}/contents" if parent_id is None else f"/learn/api/public/v1/courses/{cid}/contents/{parent_id}/children"
        data = client.get_paginated_json(url)
        if not data or "results" not in data:
            return

        for item in data["results"]:
            title = item.get("title", "")
            item_id = item.get("id")
            handler = item.get("contentHandler", {}) or {}
            handler_id = handler.get("id", "")
            clean_item_title = sanitize_filename(title)

            current_req = active_request
            started_new_req_scope = False

            if current_req is None and is_request_item(item, current_rel_dir):
                req_key = f"{cid}_{item_id}"
                req_folder_name = get_request_folder_name(title)
                req_dir = os.path.join(base_dir, req_folder_name)
                is_new_req = req_key not in seen_requests_set
                current_req = {
                    "req_key": req_key,
                    "cid": cid,
                    "item_id": item_id,
                    "course_name": info["name"],
                    "course_code": info["code"],
                    "doctor": info["doctor"],
                    "raw_title": re.sub(r'[\u200e\u200f\u202a-\u202e]', "", title).strip(),
                    "req_folder_name": req_folder_name,
                    "req_dir": req_dir,
                    "created": item.get("created", ""),
                    "is_new": is_new_req,
                    "instructions_parts": [],
                    "files": []
                }
                started_new_req_scope = True

            if current_req is not None:
                collect_item_text_instructions(item, current_req)

            # External Links Detection (Item 2)
            found_links = []
            if handler.get("url"):
                found_links.append((title or "External Link", handler.get("url")))
            elif item.get("url"):
                found_links.append((title or "External Link", item.get("url")))

            for src_html in [handler.get("instructions", ""), item.get("body", "")]:
                if src_html:
                    for cl_match in cloud_link_re.findall(src_html):
                        found_links.append((title or "Cloud Resource", cl_match))

            for l_title, l_url in found_links:
                link_key = f"{cid}_{item_id}_{l_url}"
                if link_key not in seen_links_set:
                    seen_links_set.add(link_key)
                    clean_lt = sanitize_filename(l_title or "External Resource")
                    if current_req is not None:
                        t_dir = current_req["req_dir"]
                    elif current_rel_dir:
                        t_dir = os.path.join(base_dir, current_rel_dir)
                    else:
                        t_dir = os.path.join(base_dir, "Announcements")
                    try:
                        sc_path = _write_web_shortcut(t_dir, clean_lt, l_url)
                        try:
                            rel_sc = os.path.relpath(sc_path, LMS_STORAGE_DIR)
                        except ValueError:
                            rel_sc = sc_path
                        external_links.append({
                            "course": f"{info['name']} ({info['code']})",
                            "doctor": info["doctor"],
                            "title": l_title,
                            "url": l_url,
                            "saved": rel_sc
                        })
                    except Exception:
                        pass

            is_container = "folder" in handler_id.lower() or item.get("hasChildren")
            if is_container:
                child_rel_dir = os.path.join(current_rel_dir, clean_item_title) if current_rel_dir else clean_item_title
                traverse_contents(item_id, current_rel_dir=child_rel_dir, active_request=current_req)
            else:
                extract_and_download_item_files(item, current_rel_dir, request_ctx=current_req)

            if started_new_req_scope and current_req is not None:
                seen_requests_set.add(current_req["req_key"])
                if current_req["is_new"]:
                    os.makedirs(current_req["req_dir"], exist_ok=True)
                    for existing_fn in os.listdir(current_req["req_dir"]):
                        if existing_fn != "blackboard_instructions.md" and existing_fn not in current_req["files"]:
                            current_req["files"].append(existing_fn)

                    instructions_text = "\n\n".join(current_req["instructions_parts"]).strip()
                    current_req["instructions_text"] = instructions_text

                    inst_md_path = os.path.join(current_req["req_dir"], "blackboard_instructions.md")
                    with open(inst_md_path, "w", encoding="utf-8") as f:
                        f.write(f"# {current_req['raw_title']}\n\n")
                        f.write(f"- **Course**: {current_req['course_name']} ({current_req['course_code']})\n")
                        f.write(f"- **Instructor**: {current_req['doctor']}\n")
                        if current_req.get("created"):
                            f.write(f"- **Posted**: {current_req['created']}\n")
                        if current_req["files"]:
                            f.write(f"- **Downloaded Files**: {', '.join(current_req['files'])}\n")
                        f.write("\n## Blackboard Instructions\n\n")
                        f.write(instructions_text if instructions_text else "*(No text instructions provided in Blackboard body; refer to the downloaded files in this folder.)*\n")

                    new_requests.append(current_req)

    traverse_contents()
    state["seen_files"] = list(seen_files_set)
    state["seen_files_mtime"] = seen_files_mtime
    state["seen_requests"] = list(seen_requests_set)
    state["seen_links"] = list(seen_links_set)
    return downloads, new_requests, external_links


def submission_status(grade_entry):
    """Classify a gradebook entry as GRADED, SUBMITTED, NOT SUBMITTED, or UNVERIFIED (no gradebook record)."""
    if not grade_entry:
        return "UNVERIFIED"
    if grade_entry.get("status") == "Graded" or grade_entry.get("score") is not None:
        return "GRADED"
    # An open/in-progress attempt without final submission is still NOT SUBMITTED
    if grade_entry.get("attempt_status") == "InProgress":
        return "NOT SUBMITTED"
    if grade_entry.get("status") == "NeedsGrading" or grade_entry.get("attempt_status") in ("NeedsGrading", "Submitted", "Completed"):
        return "SUBMITTED"
    return "NOT SUBMITTED"


def check_deadlines(client, state, courses_map=None):
    deadline_alerts = []
    now = datetime.now(timezone.utc)
    since_str = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    until_str = (now + timedelta(days=35)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    candidates = {}

    # Source 1: Blackboard Calendar Items (within 35 days)
    cal = client.get_paginated_json(f"/learn/api/public/v1/calendars/items?since={since_str}&until={until_str}")
    if cal and "results" in cal:
        for it in cal["results"]:
            due_str = it.get("end") or it.get("start")
            if not due_str:
                continue
            item_id = it.get("id") or f"{it.get('calendarId')}_{it.get('title')}"
            candidates[item_id] = {
                "id": it.get("id", item_id),
                "cid": it.get("calendarId"),
                "title": it.get("title"),
                "due_str": due_str
            }

    # Source 2: Course Gradebook Columns (ensures items not on calendar are captured)
    courses_dict = courses_map if courses_map is not None else get_courses_map(client)
    dl_cids = list(courses_dict.keys())
    dl_cols = _parallel_map(client.get_columns, dl_cids)
    for cid, cols in zip(dl_cids, dl_cols):
        if cols and "results" in cols:
            for c in cols["results"]:
                grading = c.get("grading", {})
                due_str = grading.get("due")
                if due_str:
                    col_id = c.get("id")
                    if col_id not in candidates:
                        candidates[col_id] = {
                            "id": col_id,
                            "cid": cid,
                            "title": c.get("name"),
                            "due_str": due_str
                        }

    # Cache everything needed to evaluate reminders later without touching the network
    state["deadline_cache"] = {
        "items": [dict(v, key=k) for k, v in candidates.items()],
        "courses": {
            cid: {"name": c.get("name", ""), "code": c.get("code", ""), "doctor": c.get("doctor", "")}
            for cid, c in courses_dict.items()
        },
    }

    return _deadline_alerts(candidates, state, courses_dict, now)


def check_cached_reminders(state):
    """Fire T-72h / T-24h / T-3h style reminders from the local deadline cache. Makes no network calls."""
    cache = state.get("deadline_cache") or {}
    items = cache.get("items") or []
    if not items:
        return []
    candidates = {i.get("key") or i.get("id"): i for i in items}
    return _deadline_alerts(candidates, state, cache.get("courses", {}), datetime.now(timezone.utc))


def _deadline_alerts(candidates, state, courses_dict, now):
    deadline_alerts = []
    alerted_map = state.get("alerted_deadlines", {})
    seen_grades = state.get("seen_grades", {})

    for item_id, item_data in candidates.items():
        cid = item_data["cid"]
        col_id = item_data.get("id") or item_id

        # Skip if student has already completed or received a grade for this item
        grade_entry = seen_grades.get(f"{cid}_{col_id}")
        if not grade_entry:
            for k, v in seen_grades.items():
                if k.startswith(f"{cid}_") and v.get("name", "").strip().lower() == item_data["title"].strip().lower():
                    grade_entry = v
                    break

        if grade_entry:
            g_status = grade_entry.get("status")
            g_score = grade_entry.get("score")
            # If graded, scored, or submitted (NeedsGrading), user has already completed it
            if g_status in ("Graded", "NeedsGrading") or g_score is not None:
                continue

        due_str = item_data["due_str"]
        try:
            due_dt = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
        except Exception:
            continue

        hours_left = (due_dt - now).total_seconds() / 3600.0
        if hours_left < 0:
            continue

        item_alerts = alerted_map.get(item_id, [])
        cal_id = item_data["cid"]
        course_info = courses_dict.get(cal_id, {"name": item_data.get("title", "Course"), "code": "", "doctor": ""})

        thresholds = [
            (168, "7d", "7 days"),
            (72, "3d", "3 days"),
            (24, "1d", "1 day"),
            (12, "12h", "12 hours"),
            (3, "3h", "3 hours")
        ]

        for limit_h, tag, label in thresholds:
            if hours_left <= limit_h and tag not in item_alerts:
                item_alerts.append(tag)
                alerted_map[item_id] = item_alerts

                due_ast = due_dt.astimezone(AST_TZ)
                formatted_due = due_ast.strftime("%A, %b %d at %I:%M %p")

                if hours_left < 1:
                    remaining_str = f"{int(hours_left * 60)} minutes left"
                elif hours_left < 24:
                    remaining_str = f"{int(hours_left)} hours left"
                else:
                    remaining_str = f"{hours_left / 24.0:.1f} days left"

                deadline_alerts.append({
                    "course": f"{course_info['name']} ({course_info.get('code', '')})",
                    "doctor": course_info.get("doctor", ""),
                    "task": item_data["title"],
                    "due": formatted_due,
                    "remaining": remaining_str,
                    "submission": submission_status(grade_entry)
                })
                break

    state["alerted_deadlines"] = alerted_map
    return deadline_alerts


def parse_announcement_media(body_html):
    """Extract attached files and external URLs from announcement HTML body."""
    if not body_html:
        return [], []

    attachments = []
    links = []
    seen_urls = set()

    known_file_exts = (
        ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
        ".zip", ".rar", ".7z", ".tar", ".gz", ".csv", ".txt", ".py", ".ipynb"
    )

    a_pattern = re.compile(r"<a\s+([^>]+)>(.*?)</a>", re.IGNORECASE | re.DOTALL)
    for match in a_pattern.finditer(body_html):
        attrs_str = match.group(1)
        inner_text = re.sub(r"<[^>]+>", "", match.group(2)).strip()

        href_m = re.search(r"href=[\x27\"]([^\x27\"]+)[\x27\"]", attrs_str, re.IGNORECASE)
        href = html.unescape(href_m.group(1).strip()) if href_m else ""

        bbfile_m = re.search(r"data-bbfile=[\x27\"]([^\x27\"]+)[\x27\"]", attrs_str, re.IGNORECASE)
        bbtype_m = re.search(r"data-bbtype=[\x27\"]([^\x27\"]+)[\x27\"]", attrs_str, re.IGNORECASE)

        is_attachment = False
        filename = ""
        file_url = href

        if bbfile_m:
            try:
                raw_json = html.unescape(bbfile_m.group(1))
                info = json.loads(raw_json)
                filename = info.get("fileName") or info.get("displayName") or ""
                file_url = info.get("resourceUrl") or file_url
                is_attachment = True
            except Exception:
                pass

        if not is_attachment and bbtype_m and bbtype_m.group(1).lower() == "attachment":
            is_attachment = True

        if not is_attachment and "bbcswebdav" in href.lower():
            is_attachment = True

        clean_url_path = urllib.parse.unquote(href.split("?")[0].rstrip("/"))
        if not is_attachment and any(clean_url_path.lower().endswith(ext) for ext in known_file_exts):
            is_attachment = True

        if is_attachment:
            if not filename:
                if inner_text and any(inner_text.lower().endswith(ext) for ext in known_file_exts):
                    filename = inner_text
                else:
                    filename = clean_url_path.split("/")[-1]
            if file_url and file_url not in seen_urls:
                seen_urls.add(file_url)
                attachments.append({"filename": filename, "url": file_url})
        elif href.startswith(("http://", "https://")):
            if not any(ign in href.lower() for ign in ["w3.org", "javascript:", ".png", ".jpg", ".jpeg", ".gif", ".svg"]):
                if href not in seen_urls:
                    seen_urls.add(href)
                    links.append({"title": inner_text or "External Link", "url": href})

    # Also detect plain text URLs
    for raw_u in re.findall(r"https?://[^\s<>\"'\)]+", body_html):
        u_clean = raw_u.strip().rstrip(".,;)>\"'")
        if u_clean.startswith(("http://", "https://")) and u_clean not in seen_urls:
            if not any(ign in u_clean.lower() for ign in ["bbcswebdav", "w3.org", "javascript:", ".png", ".jpg", ".jpeg", ".gif", ".svg"]):
                seen_urls.add(u_clean)
                links.append({"title": "External Link", "url": u_clean})

    return attachments, links


def _write_web_shortcut(target_dir, clean_name, url):
    """Write a clickable browser shortcut (.webloc on macOS, .url elsewhere) and return its path."""
    os.makedirs(target_dir, exist_ok=True)
    safe_name = sanitize_filename(clean_name) or "External Link"
    if sys.platform == "darwin":
        sc_path = os.path.join(target_dir, f"{safe_name}.webloc")
        with open(sc_path, "wb") as sf:
            sf.write(plistlib.dumps({"URL": url}))
        return sc_path
    sc_path = os.path.join(target_dir, f"{safe_name}.url")
    with open(sc_path, "w", encoding="utf-8", newline="") as sf:
        sf.write(f"[InternetShortcut]\r\nURL={url}\r\n")
    return sc_path


def get_link_shortcut_name(url, title=""):
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc or "link"
    path = parsed.path.strip("/")
    if "forms.office.com" in host or "forms.microsoft.com" in host:
        code = path.split("/")[-1] if path else "Form"
        return f"Microsoft Forms ({code})"
    if "login.microsoftonline.com" in host:
        return "Microsoft Online Login"
    if "drive.google.com" in host:
        return "Google Drive"
    if "docs.google.com" in host:
        return "Google Docs"
    if title and len(title) <= 40:
        return sanitize_filename(title)
    snippet = path.replace("/", "_")[:30]
    return sanitize_filename(f"{host}_{snippet}" if snippet else host)


def save_announcement_doc(dest_path, ann_title, ann_date, ann_body, course_name, doctor, links=None, attached_files=None):
    try:
        import docx
        doc = docx.Document()
        doc.add_heading(ann_title or "Announcement", level=1)
        meta = []
        if course_name:
            meta.append(f"Course: {course_name}")
        if doctor:
            meta.append(f"Instructor: {doctor}")
        if ann_date:
            meta.append(f"Date: {ann_date}")
        if meta:
            doc.add_paragraph(" | ".join(meta))

        doc.add_heading("Announcement Text", level=2)
        for p in (ann_body or "").split("\n\n"):
            p_clean = p.strip()
            if p_clean:
                doc.add_paragraph(p_clean)

        if attached_files:
            doc.add_heading("Attached Files", level=2)
            for af in attached_files:
                doc.add_paragraph(f"- {af}")

        if links:
            doc.add_heading("Included Links", level=2)
            for l in links:
                doc.add_paragraph(f"- {l}")
        doc.save(dest_path)
    except Exception:
        # Fallback to markdown if python-docx fails
        md_path = os.path.splitext(dest_path)[0] + ".md"
        try:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(f"# {ann_title}\n\nCourse: {course_name} | Date: {ann_date}\n\n{ann_body}\n\n")
                if attached_files:
                    f.write("## Attached Files\n" + "\n".join(f"- {af}" for af in attached_files) + "\n\n")
                if links:
                    f.write("## Included Links\n" + "\n".join(f"- {l}" for l in links) + "\n\n")
        except Exception:
            pass


def check_announcements(client, cid, info, state, new_requests=None):
    new_announcements = []
    seen = set(state.get("seen_announcements", []))

    # Fetch from both course announcements and course portal announcements
    ann_candidates = []
    seen_ann_ids = set()

    for ep in [
        f"/learn/api/public/v1/courses/{cid}/announcements",
        f"/learn/api/public/v1/announcements?courseId={cid}"
    ]:
        data = client.get_paginated_json(ep)
        if data and "results" in data:
            for ann in data["results"]:
                aid = ann.get("id")
                if aid and aid not in seen_ann_ids:
                    seen_ann_ids.add(aid)
                    ann_candidates.append(ann)

    base_dir = info.get("dir") or os.path.join(LMS_STORAGE_DIR, sanitize_filename(info["name"]))

    for ann in ann_candidates:
        ann_id = ann.get("id")
        avail_start = ((ann.get("availability") or {}).get("duration") or {}).get("start", "")
        created_raw = ann.get("created") or ann.get("modified") or avail_start or ""
        formatted_date = ""
        if created_raw:
            try:
                dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00")).astimezone(AST_TZ)
                formatted_date = dt.strftime("%A, %b %d at %I:%M %p")
            except Exception:
                formatted_date = created_raw

        raw_title = ann.get("title") or "Announcement"
        clean_title = sanitize_filename(raw_title)
        body_html = ann.get("body", "")
        body_clean = clean_html(body_html)
        attached_files, links = parse_announcement_media(body_html)

        should_save_to_disk = KEEP_ALL_ANNOUNCEMENTS or bool(attached_files) or bool(links)
        if should_save_to_disk:
            ann_dir = os.path.join(base_dir, "Announcements")
            os.makedirs(ann_dir, exist_ok=True)
            doc_path = os.path.join(ann_dir, f"{clean_title}.docx")
            if not os.path.exists(doc_path):
                save_announcement_doc(
                    dest_path=doc_path,
                    ann_title=raw_title,
                    ann_date=formatted_date,
                    ann_body=body_clean,
                    course_name=info["name"],
                    doctor=info["doctor"],
                    links=[l["url"] for l in links],
                    attached_files=[af["filename"] for af in attached_files]
                )

            # Download all attached files into Announcements/
            expanded_zips = state.setdefault("expanded_zips", {})
            for af in attached_files:
                target_fname = sanitize_filename(af["filename"] or "attachment")
                target_path = os.path.join(ann_dir, target_fname)
                ann_zip_key = f"{cid}_ann_{ann_id}_{target_fname}"
                recorded_ann_zip = (
                    _resolve_recorded_zip_path(expanded_zips, ann_zip_key, base_dir, fallback_zip_path=target_path)
                    if target_fname.lower().endswith(".zip")
                    else None
                )
                already_present = os.path.exists(target_path) or (recorded_ann_zip is not None)
                if not already_present:
                    try:
                        client.download_file(af["url"], target_path, max_bytes=MAX_FILE_BYTES)
                        extracted_dest = expand_zip_archive(target_path)
                        if extracted_dest:
                            _record_expanded_zip_path(expanded_zips, ann_zip_key, base_dir, extracted_dest)
                    except FileTooLargeError as big:
                        sys.stderr.write(f"Skipped announcement attachment {target_fname}: {big.size_bytes / 1048576:.1f} MB exceeds limit\n")
                    except Exception as e:
                        sys.stderr.write(f"Error downloading announcement attachment {target_fname}: {e}\n")

            # Save external URLs as clickable web shortcuts (.webloc on macOS, .url elsewhere)
            for l_item in links:
                l_url = l_item["url"]
                s_name = get_link_shortcut_name(l_url, l_item.get("title", ""))
                ext = ".webloc" if sys.platform == "darwin" else ".url"
                sc_path = os.path.join(ann_dir, f"{s_name}{ext}")
                if not os.path.exists(sc_path):
                    try:
                        _write_web_shortcut(ann_dir, s_name, l_url)
                    except Exception:
                        pass

        # Check if announcement qualifies as an actionable request (homework, assignment, project, task, exercise)
        if is_request_announcement(raw_title, body_clean, attached_files):
            req_key = f"ann_{cid}_{ann_id}"
            seen_requests_set = set(state.get("seen_requests", []))
            if req_key not in seen_requests_set:
                req_folder_name = get_request_folder_name(raw_title)
                req_dir = os.path.join(base_dir, req_folder_name)
                os.makedirs(req_dir, exist_ok=True)

                import shutil
                doc_path_src = os.path.join(base_dir, "Announcements", f"{clean_title}.docx")
                if os.path.exists(doc_path_src):
                    try:
                        shutil.copy2(doc_path_src, os.path.join(req_dir, f"{clean_title}.docx"))
                    except Exception:
                        pass

                req_files = []
                ann_dir_src = os.path.join(base_dir, "Announcements")
                expanded_zips = state.setdefault("expanded_zips", {})
                for af in attached_files:
                    af_fname = sanitize_filename(af.get("filename") or "attachment")
                    src_af = os.path.join(ann_dir_src, af_fname)
                    dst_af = os.path.join(req_dir, af_fname)
                    if os.path.exists(src_af):
                        try:
                            shutil.copy2(src_af, dst_af)
                        except Exception:
                            pass
                    ann_zip_key = f"{cid}_ann_{ann_id}_{af_fname}"
                    src_expanded = (
                        _resolve_recorded_zip_path(expanded_zips, ann_zip_key, base_dir, fallback_zip_path=src_af)
                        if af_fname.lower().endswith(".zip")
                        else None
                    )
                    dst_expanded = None
                    if src_expanded:
                        dst_expanded = os.path.join(req_dir, os.path.basename(src_expanded))
                        try:
                            if os.path.isdir(src_expanded):
                                shutil.copytree(src_expanded, dst_expanded, dirs_exist_ok=True)
                            elif os.path.isfile(src_expanded):
                                shutil.copy2(src_expanded, dst_expanded)
                        except Exception:
                            dst_expanded = None
                    rec_af_name = os.path.basename(dst_expanded) if (dst_expanded and os.path.exists(dst_expanded) and not os.path.exists(dst_af)) else af_fname
                    if rec_af_name not in req_files:
                        req_files.append(rec_af_name)

                doc_fname = f"{clean_title}.docx"
                if doc_fname not in req_files and os.path.exists(os.path.join(req_dir, doc_fname)):
                    req_files.insert(0, doc_fname)

                inst_md_path = os.path.join(req_dir, "blackboard_instructions.md")
                with open(inst_md_path, "w", encoding="utf-8") as f:
                    f.write(f"# {raw_title}\n\n")
                    f.write(f"- **Course**: {info['name']} ({info['code']})\n")
                    f.write(f"- **Instructor**: {info['doctor']}\n")
                    if formatted_date:
                        f.write(f"- **Posted**: {formatted_date}\n")
                    f.write("- **Source**: Course Announcement\n")
                    if req_files:
                        f.write(f"- **Files**: {', '.join(req_files)}\n")
                    f.write("\n## Blackboard Announcement Instructions\n\n")
                    f.write(body_clean if body_clean else "*(No inline text; refer to the attached files in this folder.)*\n")

                seen_requests_set.add(req_key)
                state["seen_requests"] = list(seen_requests_set)

                ann_req = {
                    "req_key": req_key,
                    "cid": cid,
                    "item_id": ann_id,
                    "course_name": info["name"],
                    "course_code": info["code"],
                    "doctor": info["doctor"],
                    "raw_title": re.sub(r'[\u200e\u200f\u202a-\u202e]', "", raw_title).strip(),
                    "req_folder_name": req_folder_name,
                    "req_dir": req_dir,
                    "created": created_raw,
                    "is_new": True,
                    "instructions_parts": [body_clean] if body_clean else [],
                    "instructions_text": body_clean,
                    "files": req_files,
                    "llm_dir": os.path.join(req_dir, "Solution"),
                    "source_type": "announcement"
                }
                if new_requests is not None:
                    new_requests.append(ann_req)

        if not ann_id or ann_id in seen:
            continue

        seen.add(ann_id)
        new_announcements.append({
            "course": f"{info['name']} ({info['code']})",
            "doctor": info["doctor"],
            "title": raw_title,
            "date": formatted_date,
            "body": body_clean,
            "attachments": [af["filename"] for af in attached_files if af.get("filename")],
            "links": [l["url"] for l in links if l.get("url")]
        })

    state["seen_announcements"] = list(seen)
    return new_announcements


def check_grades(client, state, courses_map=None, student_user_id=None):
    grade_alerts = []
    seen_grades = state.get("seen_grades", {})
    is_initialized = bool(seen_grades)
    target_uid = student_user_id or getattr(client, "student_user_id", "") or STUDENT_USER_ID

    courses_dict = courses_map if courses_map is not None else get_courses_map(client)
    course_items = list(courses_dict.items())

    # Stage 1: fetch gradebook columns for all courses in parallel
    col_lists = _parallel_map(lambda ci: client.get_columns(ci[0]), course_items)

    tasks = []
    for (cid, info), cols in zip(course_items, col_lists):
        if not cols or "results" not in cols:
            continue
        for col in cols["results"]:
            tasks.append((cid, info, col))

    # Stage 2: fetch the student's grade for every column in parallel
    grade_results = _parallel_map(
        lambda t: client.get_json(f"/learn/api/public/v2/courses/{t[0]}/gradebook/columns/{t[2].get('id')}/users/{target_uid}"),
        tasks
    )

    # Stage 2b: inspect attempt status for pending items to verify real submission vs in-progress draft
    attempt_tasks = []
    for (cid, info, col), grade_data in zip(tasks, grade_results):
        status = grade_data.get("status") if grade_data else None
        if status == "NeedsGrading" or (grade_data and grade_data.get("displayGrade", {}).get("score") is None):
            attempt_tasks.append((cid, col.get("id")))
        else:
            attempt_tasks.append(None)

    attempt_results = _parallel_map(
        lambda at: client.get_paginated_json(f"/learn/api/public/v1/courses/{at[0]}/gradebook/columns/{at[1]}/attempts") if at else None,
        attempt_tasks
    )

    # Stage 3: compare against saved state sequentially (deterministic order, no shared-state races)
    for (cid, info, col), grade_data, att_data in zip(tasks, grade_results, attempt_results):
        col_id = col.get("id")
        col_name = col.get("name") or "Grade Item"
        grade_key = f"{cid}_{col_id}"

        if not grade_data:
            continue

        status = grade_data.get("status")
        dg = grade_data.get("displayGrade", {})
        score = dg.get("score")
        possible = dg.get("possible")
        feedback_raw = grade_data.get("feedback", "")
        feedback = clean_html(feedback_raw)

        prev = seen_grades.get(grade_key)

        trigger_alert = False
        if prev is not None:
            prev_score = prev.get("score")
            prev_status = prev.get("status")
            prev_feedback = prev.get("feedback")

            score_posted = (prev_score is None and score is not None)
            score_changed = (prev_score is not None and score is not None and prev_score != score)
            feedback_added = (not prev_feedback and bool(feedback))
            status_changed_to_graded = (prev_status != "Graded" and status == "Graded")

            if score_posted or score_changed or feedback_added or (status_changed_to_graded and score is not None):
                trigger_alert = True
        elif is_initialized and (score is not None or status == "Graded"):
            # Newly discovered column that already has a posted score/grade
            trigger_alert = True

        if trigger_alert:
            pct_str = ""
            if score is not None and possible and possible > 0:
                pct = (score / possible) * 100.0
                pct_str = f" ({pct:.1f}%)"

            score_str = f"{score} / {possible}{pct_str}" if (score is not None and possible) else (f"{score}" if score is not None else "Graded")
            grade_alerts.append({
                "course": f"{info['name']} ({info['code']})",
                "doctor": info["doctor"],
                "task": col_name,
                "score_str": score_str,
                "status": status or "Graded",
                "feedback": feedback
            })

        attempt_status = None
        if att_data and "results" in att_data and att_data["results"]:
            attempt_status = att_data["results"][-1].get("status")

        seen_grades[grade_key] = {
            "course": f"{info['name']} ({info['code']})",
            "name": col_name,
            "score": score,
            "possible": possible,
            "status": status,
            "attempt_status": attempt_status,
            "feedback": feedback
        }

    state["seen_grades"] = seen_grades
    return grade_alerts


_COURSE_LIST_KEYS = ("seen_files", "seen_requests", "seen_links", "seen_announcements")
_COURSE_DICT_KEYS = ("seen_files_mtime", "skipped_large", "expanded_zips")


def _sync_course(client, cid, info, state):
    """Sync one course against a private copy of the state so courses can run concurrently."""
    local = {}
    for k in _COURSE_LIST_KEYS:
        local[k] = list(state.get(k, []))
    for k in _COURSE_DICT_KEYS:
        # Only copy keys that belong to this course (prefixed by cid) to avoid stale overwrites during merge
        prefix = f"{cid}_"
        local[k] = {k2: v2 for k2, v2 in state.get(k, {}).items() if k2.startswith(prefix)}

    new_reqs_local = []
    dl, new_reqs, ext_links = check_and_download_course_files(client, cid, info, local)
    new_reqs_local.extend(new_reqs)
    ann = check_announcements(client, cid, info, local, new_requests=new_reqs_local)
    return {"downloads": dl, "requests": new_reqs_local, "links": ext_links, "announcements": ann, "state": local}


def _merge_course_state(state, local):
    for k in _COURSE_LIST_KEYS:
        existing = state.setdefault(k, [])
        known = set(existing)
        for v in local.get(k, []):
            if v not in known:
                existing.append(v)
                known.add(v)
    for k in _COURSE_DICT_KEYS:
        state.setdefault(k, {}).update(local.get(k, {}))


def sync_all_courses(client, state, courses_dict):
    """Sync every course (parallel per LMS_MAX_WORKERS) and merge results into state.
    Returns (downloads, new_requests, announcements, external_links)."""
    all_downloads, all_new_requests, all_announcements, all_external_links = [], [], [], []
    course_items = list(courses_dict.items())
    course_results = _parallel_map(lambda ci: _sync_course(client, ci[0], ci[1], state), course_items)
    for res in course_results:
        _merge_course_state(state, res["state"])
        all_downloads.extend(res["downloads"])
        all_new_requests.extend(res["requests"])
        all_external_links.extend(res["links"])
        all_announcements.extend(res["announcements"])
    return all_downloads, all_new_requests, all_announcements, all_external_links


def main():
    init_config()
    if not is_configured():
        print("Error: LMS_URL, LMS_USER_ID, and LMS_PASSWORD must be configured in .env or environment.", file=sys.stderr)
        sys.exit(1)

    state = load_state()
    client = LMSClient(USER_ID, PASSWORD)

    try:
        client.login()
    except Exception as e:
        sys.stderr.write(f"LMS login error: {e}\n")
        sys.exit(1)

    courses_dict = get_courses_map(client)
    all_downloads, all_new_requests, all_announcements, all_external_links = sync_all_courses(client, state, courses_dict)

    all_grades = check_grades(client, state, courses_map=courses_dict)
    all_deadlines = check_deadlines(client, state, courses_map=courses_dict)
    save_state(state)

    messages = format_update_messages(
        all_downloads=all_downloads,
        all_new_requests=all_new_requests,
        all_announcements=all_announcements,
        all_grades=all_grades,
        all_deadlines=all_deadlines,
        all_external_links=all_external_links
    )

    # Output to stdout and push notifications if updates exist (zero quota / silent otherwise)
    manual_mode = "--manual" in sys.argv or "-m" in sys.argv
    if messages:
        combined_text = "\n\n---\n\n".join(messages).strip()
        print(combined_text)
        send_notification(combined_text)
    elif manual_mode:
        msg = "[Status] **LMS Sentinel Check Completed**\nAll courses are up to date. No new requests, materials, deadlines, or grade changes detected."
        print(msg)

    # Check if a detached request solver hook exists (e.g. solver.py in ~/.hermes/scripts/)
    if all_new_requests:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        solver_script = os.path.join(script_dir, "solver.py")
        if os.path.exists(solver_script):
            try:
                os.makedirs(LOGS_DIR, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                queue_file = os.path.join(LOGS_DIR, f"pending_requests_{ts}.json")
                with open(queue_file, "w", encoding="utf-8") as qf:
                    json.dump(all_new_requests, qf, ensure_ascii=False, indent=2)
                subprocess.Popen(
                    [sys.executable, solver_script, queue_file],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except Exception as se:
                sys.stderr.write(f"Solver hook dispatch error: {se}\n")



def format_update_messages(all_downloads, all_new_requests, all_announcements, all_grades, all_deadlines, all_external_links):
    messages = []

    # 1. New requests alert
    if all_new_requests:
        msg_parts = ["[New Request] **New Course Request Detected**"]
        for r in all_new_requests:
            try:
                rel_req = os.path.relpath(r["req_dir"], LMS_STORAGE_DIR)
            except ValueError:
                rel_req = r["req_dir"]
            files_str = ", ".join(f"`{f}`" for f in r["files"]) if r["files"] else "*(Text instructions only)*"
            inst_preview = r.get("instructions_text", "")
            if len(inst_preview) > 350:
                inst_preview = inst_preview[:350] + "..."
            inst_line = f"\n  *Instructions*: {inst_preview}" if inst_preview else ""
            msg_parts.append(
                f"• *Course*: {r['course_name']} ({r['course_code']})\n"
                f"  *Instructor*: {r['doctor']}\n"
                f"  *Request*: **{r['raw_title']}**\n"
                f"  *Request Folder*: `{rel_req}`\n"
                f"  *Files*: {files_str}{inst_line}"
            )
        messages.append("\n\n".join(msg_parts))

    # 2. New downloads alert & updated revisions
    brand_new_downloads = [d for d in all_downloads if not d.get("is_request") and not d.get("is_update")]
    updated_downloads = [d for d in all_downloads if d.get("is_update")]

    if brand_new_downloads:
        msg_parts = ["[Download] **New Course Material Downloaded**"]
        for d in brand_new_downloads:
            msg_parts.append(
                f"• *Course*: {d['course']}\n"
                f"  *Instructor*: {d['doctor']}\n"
                f"  *File*: `{d['file']}`\n"
                f"  *Saved to*: `{d['saved']}`"
            )
        messages.append("\n\n".join(msg_parts))

    if updated_downloads:
        msg_parts = ["[Update] **Course Material Updated (Revised Version)**"]
        for d in updated_downloads:
            msg_parts.append(
                f"• *Course*: {d['course']}\n"
                f"  *Instructor*: {d['doctor']}\n"
                f"  *File*: `{d['file']}`\n"
                f"  *Saved to*: `{d['saved']}`"
            )
        messages.append("\n\n".join(msg_parts))

    # 2b. External links & cloud resources
    if all_external_links:
        msg_parts = ["[Resource] **New Course Link / Cloud Resource**"]
        for l in all_external_links:
            msg_parts.append(
                f"• *Course*: {l['course']}\n"
                f"  *Instructor*: {l['doctor']}\n"
                f"  *Title*: **{l['title']}**\n"
                f"  *URL*: {l['url']}\n"
                f"  *Saved Shortcut*: `{l['saved']}`"
            )
        messages.append("\n\n".join(msg_parts))

    # 3. Approaching deadlines alert
    if all_deadlines:
        msg_parts = ["[Deadline] **Upcoming Assignment / Project Deadline**"]
        for dl in all_deadlines:
            doc_str = f" ({dl['doctor']})" if dl.get('doctor') else ""
            msg_parts.append(
                f"• *Course*: {dl['course']}{doc_str}\n"
                f"  *Task*: **{dl['task']}**\n"
                f"  *Due*: {dl['due']} ({dl['remaining']})\n"
                f"  *Status*: **{dl.get('submission', 'UNVERIFIED')}**"
            )
        messages.append("\n\n".join(msg_parts))

    # 4. Grade Posted / Updated alert
    if all_grades:
        msg_parts = ["[Grade] **New Grade Posted / Updated**"]
        for g in all_grades:
            fb_part = f"\n  *Feedback*: {g['feedback']}" if g['feedback'] else ""
            msg_parts.append(
                f"• *Course*: {g['course']}\n"
                f"  *Instructor*: {g['doctor']}\n"
                f"  *Assessment*: **{g['task']}**\n"
                f"  *Grade*: **{g['score_str']}**{fb_part}"
            )
        messages.append("\n\n".join(msg_parts))

    # 5. New announcements alert
    if all_announcements:
        msg_parts = ["[Announcement] **New Blackboard Announcement**"]
        for an in all_announcements:
            date_line = f"*Posted*: {an['date']}\n" if an.get('date') else ""
            att_line = ""
            if an.get("attachments"):
                att_line = f"*Attached Files*: {', '.join(an['attachments'])}\n"
            links_line = ""
            if an.get("links"):
                links_line = f"*Links*: {', '.join(an['links'])}\n"
            msg_parts.append(
                f"*Course*: {an['course']}\n"
                f"*Instructor*: {an['doctor']}\n"
                f"{date_line}"
                f"*Title*: **{an['title']}**\n"
                f"{att_line}{links_line}\n"
                f"{an['body']}"
            )
        messages.append("\n\n---\n\n".join(msg_parts))

    return messages




if __name__ == "__main__":
    main()
