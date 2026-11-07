"""
Blackboard Sentinel - Native Configuration & Setup Dialog
Supports credential configuration, subject selection (recent to ancient),
and Light/Dark tray theme preferences.
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import check_lms


def get_default_config_path():
    if sys.platform == "darwin":
        config_dir = os.path.expanduser("~/Library/Application Support/BlackboardSentinel")
    elif sys.platform == "win32":
        appdata = os.getenv("APPDATA", os.path.expanduser("~"))
        config_dir = os.path.join(appdata, "BlackboardSentinel")
    else:
        config_dir = os.path.expanduser("~/.blackboard-sentinel")
    os.makedirs(config_dir, exist_ok=True)
    return os.path.join(config_dir, ".env")


def load_existing_config():
    paths = [
        os.path.join(os.getcwd(), ".env"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        get_default_config_path()
    ]
    data = {
        "LMS_URL": "",
        "LMS_USER_ID": "",
        "LMS_PASSWORD": "",
        "LMS_STORAGE_DIR": os.path.join(os.path.expanduser("~"), "Documents", "University"),
        "LMS_COURSES": "",
        "TRAY_THEME": "auto",
        "LMS_KEEP_ALL_ANNOUNCEMENTS": "false",
        "LMS_HERMES_MESSAGING": "false",
        "LMS_EXPAND_ZIPS": "false",
        "LMS_DELETE_ORIGINAL_ZIP": "false",
        "LMS_MAX_FILE_SIZE_MB": "0"
    }
    for p in paths:
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k in data:
                            data[k] = v
                break
            except Exception:
                pass
    if not data.get("LMS_PASSWORD") and data.get("LMS_USER_ID"):
        keyring_pwd = check_lms.get_keyring_password(data["LMS_USER_ID"])
        if keyring_pwd:
            data["LMS_PASSWORD"] = keyring_pwd
    return data


def show_config_dialog(on_saved_callback=None, parent=None):
    root = tk.Toplevel(parent) if parent else tk.Tk()
    root.title("Blackboard Sentinel - Setup")
    root.geometry("560x720")
    root.minsize(500, 560)

    # Use high-contrast app icon for title bar
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    ico_path = os.path.join(base_dir, "assets", "icon_app.ico")
    png_path = os.path.join(base_dir, "assets", "icon_app.png")
    if sys.platform == "win32" and os.path.exists(ico_path):
        try:
            root.iconbitmap(ico_path)
        except Exception:
            pass
    elif os.path.exists(png_path):
        try:
            img = tk.PhotoImage(file=png_path)
            root.iconphoto(True, img)
            root._icon_photo_ref = img
        except Exception:
            pass

    bg_color = "#F8FAFC"
    card_bg = "#FFFFFF"
    accent_color = "#2563EB"
    root.configure(bg=bg_color)

    current_data = load_existing_config()
    is_settings = bool(current_data.get("LMS_URL") and current_data.get("LMS_USER_ID") and current_data.get("LMS_PASSWORD"))
    next_text = "Apply Settings" if is_settings else "Connect & Choose Subjects ->"
    if is_settings:
        root.title("Blackboard Sentinel - Settings")

    # Dynamic state
    discovered_courses = []
    course_vars = {}
    saved_flag = {"saved": False}

    # Container frames
    step1_frame = tk.Frame(root, bg=bg_color)
    step2_frame = tk.Frame(root, bg=bg_color)

    # =========================================================================
    # STEP 1: CREDENTIALS & STORAGE & THEME
    # =========================================================================
    header1 = tk.Frame(step1_frame, bg=bg_color, padx=24, pady=16)
    header1.pack(fill="x")

    lbl_t1 = tk.Label(header1, text=("Blackboard Sentinel Settings" if is_settings else "Blackboard Sentinel Configuration"), font=("Segoe UI", 13, "bold"), bg=bg_color, fg="#0F172A")
    lbl_t1.pack(anchor="w")
    lbl_s1 = tk.Label(header1, text="Enter your LMS credentials and choose your course storage folder.", font=("Segoe UI", 9), bg=bg_color, fg="#64748B")
    lbl_s1.pack(anchor="w", pady=(2, 0))

    form1 = tk.Frame(step1_frame, bg=card_bg, padx=20, pady=16, highlightthickness=1, highlightbackground="#E2E8F0")
    form1.pack(fill="both", expand=True, padx=24, pady=(0, 16))

    # 1. LMS URL
    tk.Label(form1, text="Blackboard LMS Base URL", font=("Segoe UI", 9, "bold"), bg=card_bg, fg="#334155").pack(anchor="w")
    url_var = tk.StringVar(value=current_data.get("LMS_URL", ""))
    url_entry = ttk.Entry(form1, textvariable=url_var, font=("Segoe UI", 9))
    url_entry.pack(fill="x", pady=(3, 10))

    # 2. Student ID
    tk.Label(form1, text="Username / Student ID", font=("Segoe UI", 9, "bold"), bg=card_bg, fg="#334155").pack(anchor="w")
    user_var = tk.StringVar(value=current_data.get("LMS_USER_ID", ""))
    user_entry = ttk.Entry(form1, textvariable=user_var, font=("Segoe UI", 9))
    user_entry.pack(fill="x", pady=(3, 10))

    # 3. Password
    tk.Label(form1, text="Password", font=("Segoe UI", 9, "bold"), bg=card_bg, fg="#334155").pack(anchor="w")
    pass_var = tk.StringVar(value=current_data.get("LMS_PASSWORD", ""))
    pass_entry = ttk.Entry(form1, textvariable=pass_var, show="•", font=("Segoe UI", 9))
    pass_entry.pack(fill="x", pady=(3, 6))

    # Web portal login option (for MFA / SSO portals)
    portal_opt_frame = tk.Frame(form1, bg=card_bg)
    portal_opt_frame.pack(fill="x", pady=(0, 10))

    btn_web_login = tk.Button(
        portal_opt_frame,
        text="Sign In Through Web Portal (SSO / MFA)",
        font=("Segoe UI", 9),
        bg="#F1F5F9",
        fg="#1E293B",
        activebackground="#E2E8F0",
        relief="solid",
        bd=1,
        padx=10,
        pady=4,
        cursor="hand2"
    )
    btn_web_login.pack(anchor="w")

    disclaimer_lbl = tk.Label(
        portal_opt_frame,
        text="Disclaimer: Web portal sign-in uses browser session cookies and may require periodic re-authentication when the university SSO session expires.",
        font=("Segoe UI", 8),
        bg=card_bg,
        fg="#D97706",
        wraplength=480,
        justify="left"
    )
    disclaimer_lbl.pack(anchor="w", pady=(3, 0))

    # 4. Storage Folder
    tk.Label(form1, text="Course Files Storage Folder", font=("Segoe UI", 9, "bold"), bg=card_bg, fg="#334155").pack(anchor="w")
    folder_frame = tk.Frame(form1, bg=card_bg)
    folder_frame.pack(fill="x", pady=(3, 10))

    folder_var = tk.StringVar(value=current_data.get("LMS_STORAGE_DIR", ""))
    folder_entry = ttk.Entry(folder_frame, textvariable=folder_var, font=("Segoe UI", 9))
    folder_entry.pack(side="left", fill="x", expand=True)

    def browse_folder():
        chosen = filedialog.askdirectory(initialdir=folder_var.get() or os.path.expanduser("~"), title="Select Course Storage Folder")
        if chosen:
            folder_var.set(chosen)

    ttk.Button(folder_frame, text="Browse...", command=browse_folder).pack(side="right", padx=(6, 0))

    # 5. Tray Theme Selection
    tk.Label(form1, text="System Tray Icon Theme", font=("Segoe UI", 9, "bold"), bg=card_bg, fg="#334155").pack(anchor="w")
    theme_var = tk.StringVar(value=current_data.get("TRAY_THEME", "auto"))
    theme_combo = ttk.Combobox(
        form1,
        textvariable=theme_var,
        values=["auto (Match Windows Taskbar)", "dark (White icon on dark taskbar)", "light (Dark icon on light taskbar)"],
        state="readonly",
        font=("Segoe UI", 9)
    )
    # Set display value
    cur_t = current_data.get("TRAY_THEME", "auto")
    if cur_t == "dark":
        theme_combo.current(1)
    elif cur_t == "light":
        theme_combo.current(2)
    else:
        theme_combo.current(0)
    theme_combo.pack(fill="x", pady=(3, 8))

    # 6. Keep All Announcements Option
    keep_announcements_var = tk.BooleanVar(
        value=current_data.get("LMS_KEEP_ALL_ANNOUNCEMENTS", "false").lower() in ("true", "1", "yes")
    )
    chk_ann = ttk.Checkbutton(
        form1,
        text="Keep all lecturer announcements (.docx)",
        variable=keep_announcements_var
    )
    chk_ann.pack(anchor="w", pady=(6, 2))

    hermes_var = tk.BooleanVar(
        value=current_data.get("LMS_HERMES_MESSAGING", "false").lower() in ("true", "1", "yes")
    )
    chk_hermes = ttk.Checkbutton(
        form1,
        text="Send updates via Hermes messaging",
        variable=hermes_var
    )
    chk_hermes.pack(anchor="w", pady=(2, 2))

    # 7. Zip Expansion & Delete Original Zip Options (disabled by default)
    expand_zips_var = tk.BooleanVar(
        value=current_data.get("LMS_EXPAND_ZIPS", "false").lower() in ("true", "1", "yes")
    )
    delete_zip_var = tk.BooleanVar(
        value=current_data.get("LMS_DELETE_ORIGINAL_ZIP", "false").lower() in ("true", "1", "yes")
    )

    zip_row = tk.Frame(form1, bg=card_bg)
    zip_row.pack(fill="x", pady=(4, 1))
    chk_expand_zips = ttk.Checkbutton(
        zip_row,
        text="Expand imported .zip archives (<name>_zip)",
        variable=expand_zips_var
    )
    chk_expand_zips.pack(side="left")
    tk.Label(
        zip_row,
        text="Note: Compute intensive — not suitable for low-power machines",
        font=("Segoe UI", 8),
        bg=card_bg,
        fg="#D97706"
    ).pack(side="left", padx=(8, 0))

    chk_delete_zip = ttk.Checkbutton(
        form1,
        text="Delete original .zip file after decompression",
        variable=delete_zip_var
    )
    chk_delete_zip.pack(anchor="w", padx=(20, 0), pady=(1, 2))

    def _sync_delete_zip_state(*_args):
        if expand_zips_var.get():
            chk_delete_zip.config(state="normal")
        else:
            chk_delete_zip.config(state="disabled")

    expand_zips_var.trace_add("write", _sync_delete_zip_state)
    _sync_delete_zip_state()

    # 8. Optional size cap (off by default)
    size_frame = tk.Frame(form1, bg=card_bg)
    size_frame.pack(fill="x", pady=(8, 2))
    tk.Label(size_frame, text="Skip files larger than (MB, 0 = off)", font=("Segoe UI", 9, "bold"), bg=card_bg, fg="#334155").pack(side="left")
    max_mb_var = tk.StringVar(value=current_data.get("LMS_MAX_FILE_SIZE_MB", "0") or "0")
    ttk.Entry(size_frame, textvariable=max_mb_var, width=8, font=("Segoe UI", 9)).pack(side="right")

    btn_bar1 = tk.Frame(step1_frame, bg=bg_color, padx=24, pady=8)
    btn_bar1.pack(fill="x", side="bottom")

    status_lbl1 = tk.Label(btn_bar1, text="", font=("Segoe UI", 9), bg=bg_color, fg="#64748B")
    status_lbl1.pack(side="left")

    btn_next = tk.Button(
        btn_bar1,
        text=next_text,
        font=("Segoe UI", 9, "bold"),
        bg=accent_color,
        fg="#FFFFFF",
        relief="flat",
        padx=16,
        pady=6,
        cursor="hand2"
    )
    btn_next.pack(side="right")

    btn_choose = tk.Button(
        btn_bar1,
        text="Choose Subjects",
        font=("Segoe UI", 9),
        bg="#E2E8F0",
        fg="#334155",
        relief="flat",
        padx=12,
        pady=6,
        cursor="hand2"
    )
    if is_settings:
        btn_choose.pack(side="right", padx=(0, 8))

    # =========================================================================
    # STEP 2: SUBJECT SELECTION (RECENT TO ANCIENT)
    # =========================================================================
    header2 = tk.Frame(step2_frame, bg=bg_color, padx=24, pady=14)
    header2.pack(fill="x")

    lbl_t2 = tk.Label(header2, text="Select Courses to Monitor", font=("Segoe UI", 13, "bold"), bg=bg_color, fg="#0F172A")
    lbl_t2.pack(anchor="w")
    lbl_s2 = tk.Label(header2, text="Sorted recent to ancient. Uncheck archived or completed subjects.", font=("Segoe UI", 9), bg=bg_color, fg="#64748B")
    lbl_s2.pack(anchor="w", pady=(2, 0))

    # Toolbar (Select all, deselect, top 5)
    toolbar = tk.Frame(step2_frame, bg=bg_color, padx=24, pady=4)
    toolbar.pack(fill="x")

    count_lbl = tk.Label(toolbar, text="0 selected", font=("Segoe UI", 9, "bold"), bg=bg_color, fg="#2563EB")
    count_lbl.pack(side="left")

    def update_selected_count(*args):
        cnt = sum(1 for v in course_vars.values() if v.get())
        count_lbl.config(text=f"{cnt} of {len(course_vars)} selected")

    def select_all():
        for v in course_vars.values():
            v.set(True)
        update_selected_count()

    def deselect_all():
        for v in course_vars.values():
            v.set(False)
        update_selected_count()

    def select_top_5():
        for i, (cid, v) in enumerate(course_vars.items()):
            v.set(i < 5)
        update_selected_count()

    ttk.Button(toolbar, text="Top 5 Recent", command=select_top_5).pack(side="right", padx=(4, 0))
    ttk.Button(toolbar, text="Deselect All", command=deselect_all).pack(side="right", padx=(4, 0))
    ttk.Button(toolbar, text="Select All", command=select_all).pack(side="right")

    # Scrollable Subjects Card
    card2 = tk.Frame(step2_frame, bg=card_bg, highlightthickness=1, highlightbackground="#E2E8F0")
    card2.pack(fill="both", expand=True, padx=24, pady=8)

    canvas = tk.Canvas(card2, bg=card_bg, highlightthickness=0)
    scrollbar = ttk.Scrollbar(card2, orient="vertical", command=canvas.yview)
    scroll_frame = tk.Frame(canvas, bg=card_bg)

    scroll_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

    def _on_canvas_configure(event):
        canvas.itemconfig(canvas_window, width=event.width)

    canvas.bind("<Configure>", _on_canvas_configure)
    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # Mousewheel scrolling
    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    btn_bar2 = tk.Frame(step2_frame, bg=bg_color, padx=24, pady=10)
    btn_bar2.pack(fill="x", side="bottom")

    btn_back = tk.Button(
        btn_bar2,
        text="< Back",
        font=("Segoe UI", 9),
        bg="#E2E8F0",
        fg="#334155",
        relief="flat",
        padx=12,
        pady=6,
        cursor="hand2"
    )
    btn_back.pack(side="left")

    btn_save = tk.Button(
        btn_bar2,
        text=("Done" if is_settings else "Save & Start Sentinel"),
        font=("Segoe UI", 9, "bold"),
        bg=accent_color,
        fg="#FFFFFF",
        relief="flat",
        padx=16,
        pady=6,
        cursor="hand2"
    )
    btn_save.pack(side="right")

    # =========================================================================
    # ACTIONS & LOGIC
    # =========================================================================
    def go_to_step2():
        raw_url = url_var.get().strip().rstrip("/")
        lms_user = user_var.get().strip()
        lms_pass = pass_var.get().strip()

        if not raw_url or not lms_user or not lms_pass:
            messagebox.showerror("Missing Information", "Please enter LMS URL, Student ID, and Password.", parent=root)
            return

        # Instant Client-Side Regex Validation (<1ms, no network delay)
        # Accepts 'lms.university.edu' as well as 'https://lms.university.edu'
        if not check_lms.URL_REGEX.match(raw_url):
            messagebox.showerror(
                "Invalid Address",
                f"'{raw_url}' is not a valid web address.\n\nPlease enter your university LMS domain (e.g. lms.university.edu or https://lms.university.edu).",
                parent=root
            )
            return

        clean_url = raw_url if raw_url.startswith(("http://", "https://")) else f"https://{raw_url}"
        url_var.set(clean_url)
        lms_url = clean_url

        status_lbl1.config(text="Verifying portal and logging into Blackboard...", fg="#2563EB")
        btn_next.config(state="disabled", text=("Connecting..." if not is_settings else next_text))
        btn_choose.config(state="disabled")
        root.update()

        def _fetch_worker():
            try:
                # 1. Fast pre-flight check of URL & Blackboard Ultra gateway (max 3.0s)
                check_lms.validate_blackboard_url(lms_url, timeout=3.0)
                # 2. Login check
                check_lms.LMS_URL = lms_url
                client = check_lms.LMSClient(lms_user, lms_pass)
                client.login()
                # 3. Fetch courses
                courses = check_lms.fetch_all_available_courses(client)
                root.after(0, _on_fetch_success, courses)
            except Exception as e:
                err_msg = str(e)
                root.after(0, _on_fetch_error, err_msg)

        threading.Thread(target=_fetch_worker, daemon=True).start()

    def _on_fetch_error(err_msg):
        btn_next.config(state="normal", text=next_text)
        btn_choose.config(state="normal")
        status_lbl1.config(text="")
        messagebox.showerror("Connection Error", f"Failed to connect to Blackboard:\n{err_msg}", parent=root)

    def _on_web_login_click():
        raw_url = url_var.get().strip().rstrip("/")
        if not raw_url:
            messagebox.showerror(
                "Missing LMS URL",
                "Please enter your university LMS Base URL first (e.g. lms.university.edu).",
                parent=root
            )
            return

        if not check_lms.URL_REGEX.match(raw_url):
            messagebox.showerror(
                "Invalid Address",
                f"'{raw_url}' is not a valid web address.\n\nPlease enter your university LMS domain (e.g. lms.university.edu or https://lms.university.edu).",
                parent=root
            )
            return

        clean_url = raw_url if raw_url.startswith(("http://", "https://")) else f"https://{raw_url}"
        url_var.set(clean_url)

        status_lbl1.config(text="Launching web portal in browser...", fg="#2563EB")
        btn_next.config(state="disabled")
        btn_choose.config(state="disabled")
        btn_web_login.config(state="disabled")
        root.update()

        def _web_worker():
            try:
                check_lms.validate_blackboard_url(clean_url, timeout=3.0)
                check_lms.LMS_URL = clean_url

                def _status_cb(msg):
                    root.after(0, lambda: status_lbl1.config(text=msg))

                client, me = check_lms.run_browser_login_flow(clean_url, on_status_update=_status_cb)
                if me:
                    if me.get("userName") and not user_var.get().strip():
                        root.after(0, lambda: user_var.set(me["userName"]))
                    if me.get("studentId") and not user_var.get().strip():
                        root.after(0, lambda: user_var.set(me["studentId"]))

                courses = check_lms.fetch_all_available_courses(client)
                root.after(0, _on_web_login_success, courses)
            except Exception as e:
                err_msg = str(e)
                root.after(0, _on_web_login_error, err_msg)

        threading.Thread(target=_web_worker, daemon=True).start()

    def _on_web_login_error(err_msg):
        btn_next.config(state="normal", text=next_text)
        btn_choose.config(state="normal")
        btn_web_login.config(state="normal")
        status_lbl1.config(text="")
        messagebox.showerror("Web Portal Login", f"Web portal sign-in was not completed:\n{err_msg}", parent=root)

    def _on_web_login_success(courses):
        btn_web_login.config(state="normal")
        _on_fetch_success(courses)

    def _on_fetch_success(courses):
        nonlocal discovered_courses
        discovered_courses = courses
        btn_next.config(state="normal", text=next_text)
        btn_choose.config(state="normal")
        status_lbl1.config(text="")

        if not courses:
            messagebox.showwarning("No Courses", "No enrolled courses found for this user account.", parent=root)
            return

        # Populate scroll_frame
        for w in scroll_frame.winfo_children():
            w.destroy()
        course_vars.clear()

        # Check existing configured courses
        existing_allowed = set()
        if current_data.get("LMS_COURSES"):
            existing_allowed = set(x.strip() for x in current_data["LMS_COURSES"].split(",") if x.strip())

        for idx, c in enumerate(courses):
            cid = c["id"]
            # Default checked: if previously selected, or if first time, select top 5
            is_checked = (cid in existing_allowed) if existing_allowed else (idx < 5)
            var = tk.BooleanVar(value=is_checked)
            var.trace_add("write", update_selected_count)
            course_vars[cid] = var

            row = tk.Frame(scroll_frame, bg=card_bg, padx=12, pady=6)
            row.pack(fill="x", expand=True)

            cb = tk.Checkbutton(
                row,
                text=c["display_name"],
                variable=var,
                bg=card_bg,
                fg="#0F172A",
                activebackground=card_bg,
                font=("Segoe UI", 9),
                anchor="w",
                justify="left"
            )
            cb.pack(side="left", fill="x", expand=True)

        update_selected_count()

        # Switch views
        step1_frame.pack_forget()
        step2_frame.pack(fill="both", expand=True)

    btn_web_login.config(command=_on_web_login_click)

    def go_back_to_step1():
        step2_frame.pack_forget()
        step1_frame.pack(fill="both", expand=True)

    def save_final_config():
        lms_url = url_var.get().strip().rstrip("/")
        lms_user = user_var.get().strip()
        lms_pass = pass_var.get().strip()
        lms_folder = folder_var.get().strip() or os.path.join(os.path.expanduser("~"), "Documents", "University")

        # Parse theme
        theme_raw = theme_var.get().lower()
        if "light" in theme_raw:
            theme_choice = "light"
        elif "dark" in theme_raw:
            theme_choice = "dark"
        else:
            theme_choice = "auto"

        if is_settings and not course_vars:
            selected_cids = [x.strip() for x in current_data.get("LMS_COURSES", "").split(",") if x.strip()]
        else:
            selected_cids = [cid for cid, v in course_vars.items() if v.get()]
        if not selected_cids and not is_settings:
            if not messagebox.askyesno("No Courses Selected", "You have not selected any courses to monitor. Continue anyway?", parent=root):
                return

        courses_str = ",".join(selected_cids)
        keep_ann = "true" if keep_announcements_var.get() else "false"
        hermes_msg = "true" if hermes_var.get() else "false"
        expand_zips = "true" if expand_zips_var.get() else "false"
        delete_zip = "true" if delete_zip_var.get() else "false"
        try:
            max_mb = max(0.0, float(max_mb_var.get().strip() or 0))
        except ValueError:
            max_mb = 0.0
        max_mb_str = f"{max_mb:g}"
        os.makedirs(lms_folder, exist_ok=True)

        # Store password securely in system keyring
        if lms_user and lms_pass:
            check_lms.set_keyring_password(lms_user, lms_pass)

        # Do not persist LMS_PASSWORD in plain text in .env
        env_content = f"""# Blackboard Sentinel Configuration
LMS_URL="{lms_url}"
LMS_USER_ID="{lms_user}"
LMS_STORAGE_DIR="{lms_folder}"
LMS_COURSES="{courses_str}"
TRAY_THEME="{theme_choice}"
LMS_KEEP_ALL_ANNOUNCEMENTS="{keep_ann}"
LMS_HERMES_MESSAGING="{hermes_msg}"
LMS_EXPAND_ZIPS="{expand_zips}"
LMS_DELETE_ORIGINAL_ZIP="{delete_zip}"
LMS_MAX_FILE_SIZE_MB="{max_mb_str}"
"""
        # Save to AppData and local .env
        appdata_env = get_default_config_path()
        try:
            with open(appdata_env, "w", encoding="utf-8") as f:
                f.write(env_content)
        except Exception:
            pass

        local_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        try:
            with open(local_env, "w", encoding="utf-8") as f:
                f.write(env_content)
        except Exception:
            pass

        # Update current process environment
        os.environ["LMS_URL"] = lms_url
        os.environ["LMS_USER_ID"] = lms_user
        os.environ["LMS_PASSWORD"] = lms_pass
        os.environ["LMS_STORAGE_DIR"] = lms_folder
        os.environ["LMS_COURSES"] = courses_str
        os.environ["TRAY_THEME"] = theme_choice
        os.environ["LMS_KEEP_ALL_ANNOUNCEMENTS"] = keep_ann
        os.environ["LMS_HERMES_MESSAGING"] = hermes_msg
        os.environ["LMS_EXPAND_ZIPS"] = expand_zips
        os.environ["LMS_DELETE_ORIGINAL_ZIP"] = delete_zip
        os.environ["LMS_MAX_FILE_SIZE_MB"] = max_mb_str

        check_lms.init_config()
        saved_flag["saved"] = True
        root.destroy()
        if on_saved_callback:
            on_saved_callback()

    if is_settings:
        def apply_settings():
            if not url_var.get().strip():
                messagebox.showerror("Missing Information", "Please enter LMS URL.", parent=root)
                return
            if not check_lms.has_valid_browser_session() and not (user_var.get().strip() and pass_var.get().strip()):
                messagebox.showerror("Missing Information", "Please enter Student ID and Password, or use 'Sign In Through Web Portal'.", parent=root)
                return
            save_final_config()
        btn_next.config(command=apply_settings)
        btn_choose.config(command=go_to_step2)
        btn_save.config(command=go_back_to_step1)
    else:
        btn_next.config(command=go_to_step2)
        btn_save.config(command=save_final_config)
    btn_back.config(command=go_back_to_step1)

    # Initial view
    step1_frame.pack(fill="both", expand=True)

    # Center window
    root.update_idletasks()
    width = 560
    height = 670
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")

    root.lift()
    root.attributes("-topmost", True)
    root.after_idle(root.attributes, "-topmost", False)

    if not parent:
        root.mainloop()

    return saved_flag["saved"]


def show_info_window(title, content):
    root = tk.Tk()
    root.title(title)
    root.geometry("560x440")
    root.minsize(400, 300)

    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    ico_path = os.path.join(base_dir, "assets", "icon_app.ico")
    png_path = os.path.join(base_dir, "assets", "icon_app.png")
    if sys.platform == "win32" and os.path.exists(ico_path):
        try:
            root.iconbitmap(ico_path)
        except Exception:
            pass
    elif os.path.exists(png_path):
        try:
            img = tk.PhotoImage(file=png_path)
            root.iconphoto(True, img)
            root._icon_photo_ref = img
        except Exception:
            pass

    bg_color = "#F8FAFC"
    root.configure(bg=bg_color)

    header = tk.Frame(root, bg=bg_color, padx=16, pady=12)
    header.pack(fill="x")

    lbl = tk.Label(header, text=title, font=("Segoe UI", 12, "bold"), bg=bg_color, fg="#0F172A")
    lbl.pack(anchor="w")

    body_frame = tk.Frame(root, bg="#FFFFFF", padx=8, pady=8, highlightthickness=1, highlightbackground="#E2E8F0")
    body_frame.pack(fill="both", expand=True, padx=16, pady=(0, 12))

    scrollbar = ttk.Scrollbar(body_frame)
    scrollbar.pack(side="right", fill="y")

    txt = tk.Text(
        body_frame,
        wrap="word",
        font=("Consolas", 10),
        bg="#FFFFFF",
        fg="#1E293B",
        relief="flat",
        yscrollcommand=scrollbar.set,
        padx=8,
        pady=8
    )
    txt.pack(side="left", fill="both", expand=True)
    scrollbar.config(command=txt.yview)

    txt.insert("1.0", content)
    txt.config(state="disabled")

    btn_frame = tk.Frame(root, bg=bg_color, padx=16, pady=8)
    btn_frame.pack(fill="x", side="bottom")

    btn_close = tk.Button(
        btn_frame,
        text="Close",
        font=("Segoe UI", 9, "bold"),
        bg="#2563EB",
        fg="#FFFFFF",
        relief="flat",
        padx=16,
        pady=4,
        cursor="hand2",
        command=root.destroy
    )
    btn_close.pack(side="right")

    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")

    root.lift()
    root.attributes("-topmost", True)
    root.after_idle(root.attributes, "-topmost", False)
    root.mainloop()


if __name__ == "__main__":
    show_config_dialog()
