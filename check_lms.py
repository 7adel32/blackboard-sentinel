#!/usr/bin/env python3
"""
Blackboard LMS Automated Course Sync, Announcements & Deadline Sentinel
University LMS Portal Sentinel

Monitored Courses:
  - 601 CSC: أساسيات الذكاء الاصطناعي (د. عماد الحربي) -> AI FUNDAMENTALS
  - 602 CSC: الرياضيات الحاسوبية (د. محمد زيشان عالم) -> Mathematics for Machine Learning
  - 605 CSC: البرمجة المتقدمة وإطارات برمجة (د. أحمد مباركي) -> advanced programming
  - 608 CSC: طرق بحث (د. محمد الوكيل) -> research methods

Zero-quota Hermes watchdog: outputs to stdout and dispatches to Telegram only when updates occur.
"""

import os
import sys
import json
import html
import re
import subprocess
import urllib.request
import urllib.parse
import http.cookiejar
from datetime import datetime, timezone, timedelta

# Configuration
LMS_URL = os.getenv("LMS_URL", "https://lms.ut.edu.sa")
USER_ID = os.getenv("LMS_USER_ID", "")
PASSWORD = os.getenv("LMS_PASSWORD", "")
STUDENT_USER_ID = os.getenv("LMS_STUDENT_ID", "")

STATE_DIR = os.path.expanduser("~/.hermes/state")
STATE_FILE = os.path.join(STATE_DIR, "lms_tracker_state.json")
LOGS_DIR = os.path.expanduser("~/.hermes/logs")

# Course mappings with lecturer names and target directories
LMS_STORAGE_DIR = os.path.expanduser(os.getenv("LMS_STORAGE_DIR", "~/Documents/University"))

def get_courses_map(client):
    """Dynamically discover enrolled courses from Blackboard and map subfolders named after each course."""
    courses_map = {}
    try:
        user_courses = client.get_json("/learn/api/public/v1/users/me/courses")
        for enrollment in user_courses.get("results", []):
            cid = enrollment.get("courseId")
            if not cid:
                continue
            cinfo = client.get_json(f"/learn/api/public/v3/courses/{cid}") or {}
            raw_name = cinfo.get("name") or cinfo.get("courseId") or cid
            # Clean course name for folder path (remove invalid filesystem characters)
            clean_name = re.sub(r'[/\\?%*:|"<>]', ' ', raw_name)
            clean_name = re.sub(r'\s+', ' ', clean_name).strip()
            
            code_m = re.search(r'([0-9]{3}\s+[A-Za-z]+|[A-Za-z]+\s+[0-9]{3})', clean_name)
            code = code_m.group(0) if code_m else ""
            
            target_dir = os.path.join(LMS_STORAGE_DIR, clean_name)
            courses_map[cid] = {
                "id": cid,
                "code": code,
                "name": clean_name,
                "dir": target_dir,
                "doctor": ""
            }
    except Exception as e:
        print(f"Error discovering courses: {e}", file=sys.stderr)
    return courses_map


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
AST_TZ = timezone(timedelta(hours=3))


def send_telegram(text):
    if not text:
        return
    try:
        subprocess.run(
            ["hermes", "send", text],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


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
        "seen_links": []
    }


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp_path = STATE_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, STATE_FILE)


class LMSClient:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.cj = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))

    def login(self):
        req = urllib.request.Request(f"{LMS_URL}/webapps/login/", headers={"User-Agent": USER_AGENT})
        with self.opener.open(req) as resp:
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

        with self.opener.open(post_req) as resp:
            final_url = resp.geturl()
            if "login" in final_url.lower():
                raise RuntimeError(f"LMS login failed: redirected to {final_url}")
        self.student_user_id = ""
        try:
            me_data = self.get_json("/learn/api/public/v1/users/me")
            if me_data and "id" in me_data:
                self.student_user_id = me_data["id"]
        except Exception:
            pass
        return True

    def get_json(self, path_or_url):
        url = path_or_url if path_or_url.startswith("http") else f"{LMS_URL}{path_or_url}"
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*"
        })
        try:
            with self.opener.open(req) as resp:
                return json.loads(resp.read().decode("utf-8", errors="ignore"))
        except Exception:
            return None

    def download_file(self, path_or_url, dest_path):
        url = path_or_url if path_or_url.startswith("http") else f"{LMS_URL}{path_or_url}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        tmp_dest = dest_path + ".part"
        with self.opener.open(req) as resp, open(tmp_dest, "wb") as f:
            cl = resp.headers.get("Content-Length")
            expected_bytes = int(cl) if cl and cl.isdigit() else None
            downloaded = 0
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

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
        self.student_user_id = ""
        try:
            me_data = self.get_json("/learn/api/public/v1/users/me")
            if me_data and "id" in me_data:
                self.student_user_id = me_data["id"]
        except Exception:
            pass
        return True

    # 2. Content item / file / folder with request keywords in title
    if any(re.search(pat, title_norm) for pat in REQUEST_KEYWORDS):
        self.student_user_id = ""
        try:
            me_data = self.get_json("/learn/api/public/v1/users/me")
            if me_data and "id" in me_data:
                self.student_user_id = me_data["id"]
        except Exception:
            pass
        return True

    return False


def get_request_folder_name(raw_title):
    """Return sanitized Blackboard request name for folder creation."""
    name = sanitize_filename(raw_title)
    name = re.sub(r"\.(ipynb|pdf|docx?|pptx?|xlsx?|zip|rar|py|txt|csv)$", "", name, flags=re.IGNORECASE)
    name = name.rstrip(". ").strip()
    return name or "Request"


def to_windows_path(wsl_path):
    try:
        res = subprocess.run(
            ["wslpath", "-w", wsl_path],
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return wsl_path


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
            target_dir = find_target_subfolder(base_dir, context)

        target_path = os.path.join(target_dir, fname_clean)

        # Revision Detection (Item 1)
        bb_ts = None
        if item_modified:
            try:
                bb_ts = datetime.fromisoformat(item_modified.replace("Z", "+00:00")).timestamp()
            except Exception:
                pass

        is_revision = False
        if os.path.exists(target_path):
            local_ts = os.path.getmtime(target_path)
            prev_mtime = seen_files_mtime.get(file_key)
            if bb_ts and local_ts and (bb_ts > local_ts + 60 or (prev_mtime and item_modified != prev_mtime)):
                is_revision = True
            else:
                seen_files_set.add(file_key)
                if item_modified:
                    seen_files_mtime[file_key] = item_modified
                if request_ctx is not None and fname_clean not in request_ctx["files"]:
                    request_ctx["files"].append(fname_clean)
                return
        elif file_key in seen_files_set or (request_ctx is None and fname_lower in existing_files_lower):
            seen_files_set.add(file_key)
            if item_modified:
                seen_files_mtime[file_key] = item_modified
            return

        try:
            client.download_file(download_url, target_path)
            if bb_ts:
                try:
                    os.utime(target_path, (bb_ts, bb_ts))
                except Exception:
                    pass
            seen_files_set.add(file_key)
            if item_modified:
                seen_files_mtime[file_key] = item_modified
            existing_files_lower.add(fname_lower)
            if request_ctx is not None and fname_clean not in request_ctx["files"]:
                request_ctx["files"].append(fname_clean)
            rel_saved = os.path.relpath(target_path, "/mnt/c/Users/Percent/Documents")
            downloads.append({
                "course": f"{info['name']} ({info['code']})",
                "doctor": info["doctor"],
                "file": fname_clean,
                "saved": rel_saved,
                "is_request": request_ctx is not None,
                "is_update": is_revision
            })
        except Exception as dl_err:
            sys.stderr.write(f"Download error for {fname_clean}: {dl_err}\n")

    def extract_and_download_item_files(item, path_hint, request_ctx=None):
        item_id = item.get("id")
        title = item.get("title", "")
        handler = item.get("contentHandler", {}) or {}
        item_modified = item.get("modified")

        # 1. Direct attachments
        att_data = client.get_json(f"/learn/api/public/v1/courses/{cid}/contents/{item_id}/attachments")
        if att_data and "results" in att_data:
            for att in att_data["results"]:
                att_id = att.get("id")
                fname = att.get("fileName") or title
                dl_url = f"/learn/api/public/v1/courses/{cid}/contents/{item_id}/attachments/{att_id}/download"
                process_file_candidate(item_id, att_id, fname, dl_url, path_hint or title, item_modified=item_modified, request_ctx=request_ctx)

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
                        process_file_candidate(item_id, f"emb_{emb_name}", emb_name, emb_url, path_hint or title, item_modified=item_modified, request_ctx=request_ctx)
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

    def traverse_contents(parent_id=None, path_hint="", active_request=None):
        url = f"/learn/api/public/v1/courses/{cid}/contents" if parent_id is None else f"/learn/api/public/v1/courses/{cid}/contents/{parent_id}/children"
        data = client.get_json(url)
        if not data or "results" not in data:
            return

        for item in data["results"]:
            title = item.get("title", "")
            item_id = item.get("id")
            handler = item.get("contentHandler", {}) or {}
            handler_id = handler.get("id", "")

            current_req = active_request
            started_new_req_scope = False

            if current_req is None and is_request_item(item, path_hint):
                req_key = f"{cid}_{item_id}"
                req_folder_name = get_request_folder_name(title)
                req_dir = os.path.join(base_dir, req_folder_name)
                llm_dir = os.path.join(base_dir, f"{req_folder_name} llm")
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
                    "llm_dir": llm_dir,
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
                    shortcut_fn = f"{clean_lt}.url"
                    t_dir = find_target_subfolder(base_dir, path_hint or title) if current_req is None else current_req["req_dir"]
                    os.makedirs(t_dir, exist_ok=True)
                    sc_path = os.path.join(t_dir, shortcut_fn)
                    try:
                        with open(sc_path, "w", encoding="utf-8") as sf:
                            sf.write(f"[InternetShortcut]\nURL={l_url}\n")
                        rel_sc = os.path.relpath(sc_path, "/mnt/c/Users/Percent/Documents")
                        external_links.append({
                            "course": f"{info['name']} ({info['code']})",
                            "doctor": info["doctor"],
                            "title": l_title,
                            "url": l_url,
                            "saved": rel_sc
                        })
                    except Exception:
                        pass

            if "folder" in handler_id:
                traverse_contents(item_id, title, active_request=current_req)
            else:
                extract_and_download_item_files(item, path_hint or title, request_ctx=current_req)

            if started_new_req_scope and current_req is not None:
                seen_requests_set.add(current_req["req_key"])
                if current_req["is_new"]:
                    os.makedirs(current_req["req_dir"], exist_ok=True)
                    os.makedirs(current_req["llm_dir"], exist_ok=True)
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


def check_deadlines(client, state):
    deadline_alerts = []
    now = datetime.now(timezone.utc)
    since_str = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    until_str = (now + timedelta(days=35)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    candidates = {}

    # Source 1: Blackboard Calendar Items (within 35 days)
    cal = client.get_json(f"/learn/api/public/v1/calendars/items?since={since_str}&until={until_str}")
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
    for cid, cinfo in courses_dict.items():
        cols = client.get_json(f"/learn/api/public/v2/courses/{cid}/gradebook/columns")
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
        courses_dict = courses_map if courses_map is not None else get_courses_map(client)
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
                    "remaining": remaining_str
                })
                break

    state["alerted_deadlines"] = alerted_map
    return deadline_alerts


def check_announcements(client, cid, info, state):
    new_announcements = []
    seen = set(state.get("seen_announcements", []))
    data = client.get_json(f"/learn/api/public/v1/courses/{cid}/announcements")
    if not data or "results" not in data:
        return new_announcements

    for ann in data["results"]:
        ann_id = ann.get("id")
        if not ann_id or ann_id in seen:
            continue

        seen.add(ann_id)
        created_raw = ann.get("created", "")
        formatted_date = ""
        if created_raw:
            try:
                dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00")).astimezone(AST_TZ)
                formatted_date = dt.strftime("%A, %b %d at %I:%M %p")
            except Exception:
                formatted_date = created_raw

        body_clean = clean_html(ann.get("body", ""))
        new_announcements.append({
            "course": f"{info['name']} ({info['code']})",
            "doctor": info["doctor"],
            "title": ann.get("title"),
            "date": formatted_date,
            "body": body_clean
        })

    state["seen_announcements"] = list(seen)
    return new_announcements


def check_grades(client, state, courses_map=None, student_user_id=None):
    grade_alerts = []
    seen_grades = state.get("seen_grades", {})
    is_initialized = bool(seen_grades)

    courses_dict = courses_map if courses_map is not None else get_courses_map(client)
    for cid, info in courses_dict.items():
        cols = client.get_json(f"/learn/api/public/v2/courses/{cid}/gradebook/columns")
        if not cols or "results" not in cols:
            continue

        for col in cols["results"]:
            col_id = col.get("id")
            col_name = col.get("name") or "Grade Item"
            grade_key = f"{cid}_{col_id}"

            grade_data = target_uid = student_user_id or getattr(client, "student_user_id", "") or STUDENT_USER_ID
            grade_data = client.get_json(f"/learn/api/public/v2/courses/{cid}/gradebook/columns/{col_id}/users/{target_uid}")
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

            seen_grades[grade_key] = {
                "course": f"{info['name']} ({info['code']})",
                "name": col_name,
                "score": score,
                "possible": possible,
                "status": status,
                "feedback": feedback
            }

    state["seen_grades"] = seen_grades
    return grade_alerts


def main():


    state = load_state()
    client = LMSClient(USER_ID, PASSWORD)

    try:
        client.login()
    except Exception as e:
        sys.stderr.write(f"LMS login error: {e}\n")
        sys.exit(1)

    all_downloads = []
    all_new_requests = []
    all_announcements = []

    all_external_links = []

    courses_dict = courses_map if courses_map is not None else get_courses_map(client)
    for cid, info in courses_dict.items():
        dl, new_reqs, ext_links = check_and_download_course_files(client, cid, info, state)
        all_downloads.extend(dl)
        all_new_requests.extend(new_reqs)
        all_external_links.extend(ext_links)
        ann = check_announcements(client, cid, info, state)
        all_announcements.extend(ann)

    all_grades = check_grades(client, state)
    all_deadlines = check_deadlines(client, state)
    save_state(state)

    messages = []

    # 1. New requests alert
    if all_new_requests:
        model_id = get_latest_flash_medium_model()
        msg_parts = ["🆕 **New Course Request Detected**"]
        for r in all_new_requests:
            rel_req = os.path.relpath(r["req_dir"], "/mnt/c/Users/Percent/Documents")
            files_str = ", ".join(f"`{f}`" for f in r["files"]) if r["files"] else "*(Text instructions only)*"
            inst_preview = r.get("instructions_text", "")
            if len(inst_preview) > 350:
                inst_preview = inst_preview[:350] + "..."
            inst_line = f"\n  📋 *Instructions*: {inst_preview}" if inst_preview else ""
            msg_parts.append(
                f"• 📚 *Course*: {r['course_name']} ({r['course_code']})\n"
                f"  👨‍🏫 *Instructor*: {r['doctor']}\n"
                f"  📝 *Request*: **{r['raw_title']}**\n"
                f"  📁 *Request Folder*: `{rel_req}`\n"
                f"  📄 *Files*: {files_str}\n"
            )
        messages.append("\n\n".join(msg_parts))

    # 2. New downloads alert & updated revisions
    brand_new_downloads = [d for d in all_downloads if not d.get("is_request") and not d.get("is_update")]
    updated_downloads = [d for d in all_downloads if d.get("is_update")]

    if brand_new_downloads:
        msg_parts = ["📥 **New Course Material Downloaded**"]
        for d in brand_new_downloads:
            msg_parts.append(
                f"• 📚 *Course*: {d['course']}\n"
                f"  👨‍🏫 *Instructor*: {d['doctor']}\n"
                f"  📄 *File*: `{d['file']}`\n"
                f"  📁 *Saved to*: `{d['saved']}`"
            )
        messages.append("\n\n".join(msg_parts))

    if updated_downloads:
        msg_parts = ["🔄 **Course Material Updated (Revised Version)**"]
        for d in updated_downloads:
            msg_parts.append(
                f"• 📚 *Course*: {d['course']}\n"
                f"  👨‍🏫 *Instructor*: {d['doctor']}\n"
                f"  📄 *File*: `{d['file']}`\n"
                f"  📁 *Saved to*: `{d['saved']}`"
            )
        messages.append("\n\n".join(msg_parts))

    # 2b. External links & cloud resources
    if all_external_links:
        msg_parts = ["🔗 **New Course Link / Cloud Resource**"]
        for l in all_external_links:
            msg_parts.append(
                f"• 📚 *Course*: {l['course']}\n"
                f"  👨‍🏫 *Instructor*: {l['doctor']}\n"
                f"  📌 *Title*: **{l['title']}**\n"
                f"  🌐 *URL*: {l['url']}\n"
                f"  📁 *Saved Shortcut*: `{l['saved']}`"
            )
        messages.append("\n\n".join(msg_parts))

    # 3. Approaching deadlines alert
    if all_deadlines:
        msg_parts = ["⏰ **Upcoming Assignment / Project Deadline**"]
        for dl in all_deadlines:
            doc_str = f" ({dl['doctor']})" if dl.get('doctor') else ""
            msg_parts.append(
                f"• 📚 *Course*: {dl['course']}{doc_str}\n"
                f"  📝 *Task*: **{dl['task']}**\n"
                f"  ⏳ *Due*: {dl['due']} ({dl['remaining']})"
            )
        messages.append("\n\n".join(msg_parts))

    # 4. Grade Posted / Updated alert
    if all_grades:
        msg_parts = ["📊 **New Grade Posted / Updated**"]
        for g in all_grades:
            fb_part = f"\n  💬 *Feedback*: {g['feedback']}" if g['feedback'] else ""
            msg_parts.append(
                f"• 📚 *Course*: {g['course']}\n"
                f"  👨‍🏫 *Instructor*: {g['doctor']}\n"
                f"  📝 *Assessment*: **{g['task']}**\n"
                f"  🎯 *Grade*: **{g['score_str']}**{fb_part}"
            )
        messages.append("\n\n".join(msg_parts))

    # 5. New announcements alert
    if all_announcements:
        msg_parts = ["📢 **New Blackboard Announcement**"]
        for an in all_announcements:
            date_line = f"📅 *Posted*: {an['date']}\n" if an.get('date') else ""
            msg_parts.append(
                f"📚 *Course*: {an['course']}\n"
                f"👨‍🏫 *Instructor*: {an['doctor']}\n"
                f"{date_line}"
                f"📌 *Title*: **{an['title']}**\n\n"
                f"{an['body']}"
            )
        messages.append("\n\n---\n\n".join(msg_parts))

    # Output to stdout and push to Telegram if updates exist (zero quota / silent otherwise)
    manual_mode = "--manual" in sys.argv or "-m" in sys.argv
    if messages:
        combined_text = "\n\n---\n\n".join(messages).strip()
        print(combined_text)
        send_telegram(combined_text)
    elif manual_mode:
        msg = "🛡️ **LMS Sentinel Check Completed**\nAll courses are up to date. No new requests, materials, deadlines, or grade changes detected."
        print(msg)




if __name__ == "__main__":
    main()
