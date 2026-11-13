"""
Blackboard Sentinel - Native macOS AppKit Configuration & Info Windows
Uses native Cocoa/AppKit controls for full macOS Light/Dark Mode support,
SF Pro typography, smooth NSScrollView scrolling, and zero Tk Aqua artifacts.
"""

import os
import sys
import threading

import AppKit
import Foundation
import objc
from PyObjCTools import AppHelper

import config_gui


class FlippedView(AppKit.NSView):
    """NSView using top-left origin coordinates for clean top-down layout."""

    def isFlipped(self):
        return True


def _make_label(text, frame, font=None, color=None, alignment=None, wrap=False):
    lbl = AppKit.NSTextField.alloc().initWithFrame_(frame)
    lbl.setStringValue_(text or "")
    lbl.setBezeled_(False)
    lbl.setDrawsBackground_(False)
    lbl.setEditable_(False)
    lbl.setSelectable_(False)
    if font is not None:
        lbl.setFont_(font)
    if color is not None:
        lbl.setTextColor_(color)
    if alignment is not None:
        lbl.setAlignment_(alignment)
    if wrap:
        lbl.setLineBreakMode_(AppKit.NSLineBreakByWordWrapping)
        if lbl.cell():
            lbl.cell().setWraps_(True)
    return lbl


def _make_box(frame):
    box = AppKit.NSBox.alloc().initWithFrame_(frame)
    box.setBoxType_(AppKit.NSBoxPrimary)
    box.setTitlePosition_(AppKit.NSNoTitle)
    return box


def _make_checkbox(title, frame, checked=False, target=None, action=None):
    btn = AppKit.NSButton.alloc().initWithFrame_(frame)
    btn.setButtonType_(AppKit.NSButtonTypeSwitch)
    btn.setTitle_(title)
    btn.setFont_(AppKit.NSFont.systemFontOfSize_(13))
    btn.setState_(AppKit.NSControlStateValueOn if checked else AppKit.NSControlStateValueOff)
    if target is not None and action is not None:
        btn.setTarget_(target)
        btn.setAction_(action)
    return btn


def _make_push_button(title, frame, target=None, action=None, primary=False):
    btn = AppKit.NSButton.alloc().initWithFrame_(frame)
    btn.setButtonType_(AppKit.NSButtonTypeMomentaryPushIn)
    btn.setBezelStyle_(AppKit.NSBezelStyleRounded)
    btn.setTitle_(title)
    btn.setFont_(AppKit.NSFont.systemFontOfSize_(13))
    if primary:
        btn.setKeyEquivalent_("\r")
    if target is not None and action is not None:
        btn.setTarget_(target)
        btn.setAction_(action)
    return btn


def _load_app_icon():
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    png_path = os.path.join(base_dir, "assets", "icon_app.png")
    if os.path.isfile(png_path):
        img = AppKit.NSImage.alloc().initWithContentsOfFile_(png_path)
        if img is not None:
            return img
    return None


def _install_standard_menus(app):
    """Install minimal App, Edit, and Window menus so Cmd+C/V/X/A/W/Q work natively."""
    menubar = AppKit.NSMenu.alloc().init()

    # App menu
    app_menu_item = AppKit.NSMenuItem.alloc().init()
    menubar.addItem_(app_menu_item)
    app_menu = AppKit.NSMenu.alloc().init()
    app_menu.addItemWithTitle_action_keyEquivalent_("Quit Blackboard Sentinel", "terminate:", "q")
    app_menu_item.setSubmenu_(app_menu)

    # Edit menu
    edit_menu_item = AppKit.NSMenuItem.alloc().init()
    menubar.addItem_(edit_menu_item)
    edit_menu = AppKit.NSMenu.alloc().initWithTitle_("Edit")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Undo", "undo:", "z")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Redo", "redo:", "Z")
    edit_menu.addItem_(AppKit.NSMenuItem.separatorItem())
    edit_menu.addItemWithTitle_action_keyEquivalent_("Cut", "cut:", "x")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Copy", "copy:", "c")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Paste", "paste:", "v")
    edit_menu.addItemWithTitle_action_keyEquivalent_("Select All", "selectAll:", "a")
    edit_menu_item.setSubmenu_(edit_menu)

    # Window menu
    win_menu_item = AppKit.NSMenuItem.alloc().init()
    menubar.addItem_(win_menu_item)
    win_menu = AppKit.NSMenu.alloc().initWithTitle_("Window")
    win_menu.addItemWithTitle_action_keyEquivalent_("Close Window", "performClose:", "w")
    win_menu_item.setSubmenu_(win_menu)

    app.setMainMenu_(menubar)


def _stop_nsapp_loop(app):
    app.stop_(app)
    event = AppKit.NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(
        AppKit.NSApplicationDefined,
        AppKit.NSPoint(0, 0),
        0,
        0.0,
        0,
        None,
        0,
        0,
        0,
    )
    app.postEvent_atStart_(event, False)


def _show_alert(window, title, message, style=AppKit.NSAlertStyleWarning):
    alert = AppKit.NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_(message)
    alert.setAlertStyle_(style)
    alert.addButtonWithTitle_("OK")
    if window is not None:
        alert.beginSheetModalForWindow_completionHandler_(window, None)
    else:
        alert.runModal()


def _ask_yes_no(window, title, message):
    alert = AppKit.NSAlert.alloc().init()
    alert.setMessageText_(title)
    alert.setInformativeText_(message)
    alert.setAlertStyle_(AppKit.NSAlertStyleWarning)
    alert.addButtonWithTitle_("Continue")
    alert.addButtonWithTitle_("Cancel")
    return alert.runModal() == AppKit.NSAlertFirstButtonReturn


class _WindowCloseDelegate(Foundation.NSObject):
    def windowWillClose_(self, notification):
        _stop_nsapp_loop(AppKit.NSApplication.sharedApplication())


class _ConfigController(Foundation.NSObject):
    def initWithState_(self, state):
        self = objc.super(_ConfigController, self).init()
        if self is None:
            return None
        self.state = state
        return self

    def windowWillClose_(self, notification):
        _stop_nsapp_loop(AppKit.NSApplication.sharedApplication())

    @objc.IBAction
    def onBrowseFolder_(self, sender):
        panel = AppKit.NSOpenPanel.openPanel()
        panel.setCanChooseFiles_(False)
        panel.setCanChooseDirectories_(True)
        panel.setCanCreateDirectories_(True)
        panel.setAllowsMultipleSelection_(False)
        panel.setTitle_("Select Course Storage Folder")
        cur_dir = os.path.expanduser(self.state["folder_field"].stringValue().strip() or "~")
        if os.path.isdir(cur_dir):
            panel.setDirectoryURL_(Foundation.NSURL.fileURLWithPath_(cur_dir))
        if panel.runModal() == AppKit.NSModalResponseOK:
            url = panel.URL()
            if url is not None:
                self.state["folder_field"].setStringValue_(url.path())

    @objc.IBAction
    def onToggleExpandZips_(self, sender):
        enabled = sender.state() == AppKit.NSControlStateValueOn
        self.state["chk_delete_zip"].setEnabled_(enabled)

    @objc.IBAction
    def onWebLogin_(self, sender):
        import check_lms

        raw_url = self.state["url_field"].stringValue().strip().rstrip("/")
        if not raw_url:
            _show_alert(
                self.state["window"],
                "Missing LMS URL",
                "Please enter your university LMS Base URL first (e.g. lms.university.edu).",
            )
            return
        if not check_lms.URL_REGEX.match(raw_url):
            _show_alert(
                self.state["window"],
                "Invalid Address",
                f"'{raw_url}' is not a valid web address.\n\nPlease enter your university LMS domain (e.g. lms.university.edu or https://lms.university.edu).",
            )
            return

        clean_url = raw_url if raw_url.startswith(("http://", "https://")) else f"https://{raw_url}"
        self.state["url_field"].setStringValue_(clean_url)
        self._set_busy(True, "Launching web portal in browser...")

        def _worker():
            try:
                check_lms.validate_blackboard_url(clean_url, timeout=3.0)
                check_lms.LMS_URL = clean_url

                def _status_cb(msg):
                    AppHelper.callAfter(lambda m=msg: self.state["status_lbl"].setStringValue_(m))

                client, me = check_lms.run_browser_login_flow(clean_url, on_status_update=_status_cb)
                if me:
                    detected_user = me.get("userName") or me.get("studentId") or ""
                    if detected_user:
                        def _fill_user():
                            if not self.state["user_field"].stringValue().strip():
                                self.state["user_field"].setStringValue_(detected_user)
                        AppHelper.callAfter(_fill_user)
                courses = check_lms.fetch_all_available_courses(client)
                AppHelper.callAfter(lambda c=courses: self._on_fetch_success(c))
            except Exception as exc:
                err_msg = str(exc)
                AppHelper.callAfter(lambda m=err_msg: self._on_fetch_error("Web Portal Login", f"Web portal sign-in was not completed:\n{m}"))

        threading.Thread(target=_worker, daemon=True).start()

    @objc.IBAction
    def onNextOrApply_(self, sender):
        if self.state["is_settings"]:
            import check_lms
            raw_url = self.state["url_field"].stringValue().strip().rstrip("/")
            lms_user = self.state["user_field"].stringValue().strip()
            lms_pass = self.state["pass_field"].stringValue().strip()
            if not raw_url:
                _show_alert(self.state["window"], "Missing Information", "Please enter LMS URL.")
                return
            if not check_lms.has_valid_browser_session() and not (lms_user and lms_pass):
                _show_alert(
                    self.state["window"],
                    "Missing Information",
                    "Please enter Student ID and Password, or use 'Sign In Through Web Portal'.",
                )
                return
            self._save_final_config()
        else:
            self.onChooseSubjects_(sender)

    @objc.IBAction
    def onChooseSubjects_(self, sender):
        import check_lms

        raw_url = self.state["url_field"].stringValue().strip().rstrip("/")
        lms_user = self.state["user_field"].stringValue().strip()
        lms_pass = self.state["pass_field"].stringValue().strip()

        if not raw_url:
            _show_alert(self.state["window"], "Missing Information", "Please enter LMS URL.")
            return
        if not check_lms.has_valid_browser_session() and (not lms_user or not lms_pass):
            _show_alert(
                self.state["window"],
                "Missing Information",
                "Please enter Student ID and Password, or use 'Sign In Through Web Portal'.",
            )
            return
        if not check_lms.URL_REGEX.match(raw_url):
            _show_alert(
                self.state["window"],
                "Invalid Address",
                f"'{raw_url}' is not a valid web address.\n\nPlease enter your university LMS domain (e.g. lms.university.edu or https://lms.university.edu).",
            )
            return

        clean_url = raw_url if raw_url.startswith(("http://", "https://")) else f"https://{raw_url}"
        self.state["url_field"].setStringValue_(clean_url)
        self._set_busy(True, "Verifying portal and logging into Blackboard...")

        def _worker():
            try:
                check_lms.validate_blackboard_url(clean_url, timeout=3.0)
                check_lms.LMS_URL = clean_url
                client = check_lms.LMSClient(lms_user, lms_pass)
                client.login()
                courses = check_lms.fetch_all_available_courses(client)
                AppHelper.callAfter(lambda c=courses: self._on_fetch_success(c))
            except Exception as exc:
                err_msg = str(exc)
                AppHelper.callAfter(lambda m=err_msg: self._on_fetch_error("Connection Error", f"Failed to connect to Blackboard:\n{m}"))

        threading.Thread(target=_worker, daemon=True).start()

    def _set_busy(self, busy, status_text=""):
        spinner = self.state["spinner"]
        if busy:
            spinner.setHidden_(False)
            spinner.startAnimation_(None)
        else:
            spinner.stopAnimation_(None)
            spinner.setHidden_(True)
        self.state["status_lbl"].setStringValue_(status_text)
        self.state["btn_next"].setEnabled_(not busy)
        self.state["btn_choose"].setEnabled_(not busy)
        self.state["btn_web_login"].setEnabled_(not busy)

    def _on_fetch_error(self, title, msg):
        self._set_busy(False, "")
        _show_alert(self.state["window"], title, msg)

    def _on_fetch_success(self, courses):
        self._set_busy(False, "")
        if not courses:
            _show_alert(self.state["window"], "No Courses", "No enrolled courses found for this user account.")
            return

        doc_view = self.state["course_doc_view"]
        for sub in list(doc_view.subviews()):
            sub.removeFromSuperview()
        self.state["course_buttons"].clear()

        existing_allowed = set()
        if self.state["current_data"].get("LMS_COURSES"):
            existing_allowed = {
                x.strip() for x in self.state["current_data"]["LMS_COURSES"].split(",") if x.strip()
            }

        row_h = 28
        pad_y = 8
        doc_w = max(460, self.state["course_scroll"].contentSize().width)
        total_h = max(320, pad_y * 2 + len(courses) * row_h)
        doc_view.setFrame_(Foundation.NSMakeRect(0, 0, doc_w, total_h))

        for idx, c in enumerate(courses):
            cid = c["id"]
            is_checked = (cid in existing_allowed) if existing_allowed else (idx < 5)
            btn = _make_checkbox(
                c["display_name"],
                Foundation.NSMakeRect(12, pad_y + idx * row_h, doc_w - 24, 24),
                checked=is_checked,
                target=self,
                action="onCourseCheckboxChanged:",
            )
            btn.setAutoresizingMask_(AppKit.NSViewWidthSizable)
            doc_view.addSubview_(btn)
            self.state["course_buttons"][cid] = btn

        self._update_selected_count()
        self.state["step1_view"].setHidden_(True)
        self.state["step2_view"].setHidden_(False)

    @objc.IBAction
    def onCourseCheckboxChanged_(self, sender):
        self._update_selected_count()

    def _update_selected_count(self):
        btns = self.state["course_buttons"]
        cnt = sum(1 for b in btns.values() if b.state() == AppKit.NSControlStateValueOn)
        self.state["count_lbl"].setStringValue_(f"{cnt} of {len(btns)} selected")

    @objc.IBAction
    def onSelectAll_(self, sender):
        for b in self.state["course_buttons"].values():
            b.setState_(AppKit.NSControlStateValueOn)
        self._update_selected_count()

    @objc.IBAction
    def onDeselectAll_(self, sender):
        for b in self.state["course_buttons"].values():
            b.setState_(AppKit.NSControlStateValueOff)
        self._update_selected_count()

    @objc.IBAction
    def onSelectTop5_(self, sender):
        for i, b in enumerate(self.state["course_buttons"].values()):
            b.setState_(AppKit.NSControlStateValueOn if i < 5 else AppKit.NSControlStateValueOff)
        self._update_selected_count()

    @objc.IBAction
    def onBackToStep1_(self, sender):
        self.state["step2_view"].setHidden_(True)
        self.state["step1_view"].setHidden_(False)

    @objc.IBAction
    def onStep2Done_(self, sender):
        if self.state["is_settings"]:
            self.onBackToStep1_(sender)
        else:
            self._save_final_config()

    def _save_final_config(self):
        import check_lms

        raw_url = self.state["url_field"].stringValue().strip().rstrip("/")
        lms_url = raw_url if raw_url.startswith(("http://", "https://")) else f"https://{raw_url}"
        lms_user = self.state["user_field"].stringValue().strip()
        lms_pass = self.state["pass_field"].stringValue().strip()
        lms_folder = self.state["folder_field"].stringValue().strip() or os.path.join(
            os.path.expanduser("~"), "Documents", "University"
        )

        theme_title = self.state["theme_popup"].titleOfSelectedItem().lower()
        if "light" in theme_title:
            theme_choice = "light"
        elif "dark" in theme_title:
            theme_choice = "dark"
        else:
            theme_choice = "auto"

        course_btns = self.state["course_buttons"]
        if self.state["is_settings"] and not course_btns:
            selected_cids = [
                x.strip() for x in self.state["current_data"].get("LMS_COURSES", "").split(",") if x.strip()
            ]
        else:
            selected_cids = [
                cid for cid, b in course_btns.items() if b.state() == AppKit.NSControlStateValueOn
            ]

        if not selected_cids and not self.state["is_settings"]:
            if not _ask_yes_no(
                self.state["window"],
                "No Courses Selected",
                "You have not selected any courses to monitor. Continue anyway?",
            ):
                return

        courses_str = ",".join(selected_cids)
        keep_ann = "true" if self.state["chk_ann"].state() == AppKit.NSControlStateValueOn else "false"
        hermes_msg = "true" if self.state["chk_hermes"].state() == AppKit.NSControlStateValueOn else "false"
        expand_zips = "true" if self.state["chk_expand_zips"].state() == AppKit.NSControlStateValueOn else "false"
        delete_zip = "true" if self.state["chk_delete_zip"].state() == AppKit.NSControlStateValueOn else "false"
        try:
            max_mb = max(0.0, float(self.state["max_mb_field"].stringValue().strip() or 0))
        except ValueError:
            max_mb = 0.0
        max_mb_str = f"{max_mb:g}"

        os.makedirs(os.path.expanduser(lms_folder), exist_ok=True)
        if lms_user and lms_pass:
            check_lms.set_keyring_password(lms_user, lms_pass)

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
        appdata_env = config_gui.get_default_config_path()
        try:
            with open(appdata_env, "w", encoding="utf-8") as f:
                f.write(env_content)
        except Exception:
            pass

        if not getattr(sys, "frozen", False):
            local_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
            try:
                with open(local_env, "w", encoding="utf-8") as f:
                    f.write(env_content)
            except Exception:
                pass

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

        check_lms.init_config(override=True)
        self.state["saved"] = True
        self.state["window"].close()
        if self.state["on_saved_callback"]:
            self.state["on_saved_callback"]()


def show_config_dialog_mac(on_saved_callback=None):
    import check_lms

    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    _install_standard_menus(app)

    check_lms.init_config()
    current_data = config_gui.load_existing_config()
    has_sso_session = check_lms.has_valid_browser_session()
    is_settings = bool(
        current_data.get("LMS_URL")
        and (has_sso_session or (current_data.get("LMS_USER_ID") and current_data.get("LMS_PASSWORD")))
    )

    win_w, win_h = 580, 688
    style = (
        AppKit.NSWindowStyleMaskTitled
        | AppKit.NSWindowStyleMaskClosable
        | AppKit.NSWindowStyleMaskMiniaturizable
    )
    window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        Foundation.NSMakeRect(0, 0, win_w, win_h),
        style,
        AppKit.NSBackingStoreBuffered,
        False,
    )
    window.setTitle_("Blackboard Sentinel - Settings" if is_settings else "Blackboard Sentinel - Setup")
    window.center()

    root_view = FlippedView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, win_w, win_h))
    window.setContentView_(root_view)

    state = {
        "window": window,
        "current_data": current_data,
        "is_settings": is_settings,
        "saved": False,
        "on_saved_callback": on_saved_callback,
        "course_buttons": {},
    }
    controller = _ConfigController.alloc().initWithState_(state)
    window.setDelegate_(controller)

    # =========================================================================
    # STEP 1 VIEW
    # =========================================================================
    step1 = FlippedView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, win_w, win_h))
    root_view.addSubview_(step1)
    state["step1_view"] = step1

    pad = 24
    inner_w = win_w - pad * 2
    y = 20

    # Header with app icon
    icon_img = _load_app_icon()
    title_x = pad
    if icon_img is not None:
        iv = AppKit.NSImageView.alloc().initWithFrame_(Foundation.NSMakeRect(pad, y, 42, 42))
        iv.setImage_(icon_img)
        step1.addSubview_(iv)
        title_x = pad + 54

    step1.addSubview_(
        _make_label(
            "Blackboard Sentinel Settings" if is_settings else "Blackboard Sentinel Setup",
            Foundation.NSMakeRect(title_x, y, win_w - title_x - pad, 24),
            font=AppKit.NSFont.boldSystemFontOfSize_(17),
            color=AppKit.NSColor.labelColor(),
        )
    )
    step1.addSubview_(
        _make_label(
            "Configure your university LMS credentials, storage folder, and sync preferences.",
            Foundation.NSMakeRect(title_x, y + 24, win_w - title_x - pad, 18),
            font=AppKit.NSFont.systemFontOfSize_(12),
            color=AppKit.NSColor.secondaryLabelColor(),
        )
    )
    y += 58

    # Card 1: Account & Portal
    card1_h = 204
    card1 = _make_box(Foundation.NSMakeRect(pad, y, inner_w, card1_h))
    step1.addSubview_(card1)
    c1_view = FlippedView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, inner_w, card1_h))
    card1.setContentView_(c1_view)

    cx, cw = 16, inner_w - 32
    cy = 12

    c1_view.addSubview_(_make_label("Blackboard LMS Base URL", Foundation.NSMakeRect(cx, cy, cw, 16), font=AppKit.NSFont.boldSystemFontOfSize_(12), color=AppKit.NSColor.labelColor()))
    cy += 18
    url_field = AppKit.NSTextField.alloc().initWithFrame_(Foundation.NSMakeRect(cx, cy, cw, 24))
    url_field.setPlaceholderString_("https://lms.university.edu")
    url_field.setStringValue_(current_data.get("LMS_URL", ""))
    c1_view.addSubview_(url_field)
    cy += 32

    half_w = (cw - 12) / 2
    c1_view.addSubview_(_make_label("Username / Student ID", Foundation.NSMakeRect(cx, cy, half_w, 16), font=AppKit.NSFont.boldSystemFontOfSize_(12), color=AppKit.NSColor.labelColor()))
    c1_view.addSubview_(_make_label("Password", Foundation.NSMakeRect(cx + half_w + 12, cy, half_w, 16), font=AppKit.NSFont.boldSystemFontOfSize_(12), color=AppKit.NSColor.labelColor()))
    cy += 18

    user_field = AppKit.NSTextField.alloc().initWithFrame_(Foundation.NSMakeRect(cx, cy, half_w, 24))
    user_field.setPlaceholderString_("Student ID")
    user_field.setStringValue_(current_data.get("LMS_USER_ID", ""))
    c1_view.addSubview_(user_field)

    pass_field = AppKit.NSSecureTextField.alloc().initWithFrame_(Foundation.NSMakeRect(cx + half_w + 12, cy, half_w, 24))
    pass_field.setPlaceholderString_("Stored in macOS Keychain")
    pass_field.setStringValue_(current_data.get("LMS_PASSWORD", ""))
    c1_view.addSubview_(pass_field)
    cy += 34

    btn_web_login = _make_push_button(
        "Sign In Through Web Portal (SSO / MFA)",
        Foundation.NSMakeRect(cx - 2, cy, 270, 28),
        target=controller,
        action="onWebLogin:",
    )
    c1_view.addSubview_(btn_web_login)
    cy += 30

    c1_view.addSubview_(
        _make_label(
            "Web portal sign-in uses browser session cookies and may require re-authentication when SSO expires.",
            Foundation.NSMakeRect(cx, cy, cw, 30),
            font=AppKit.NSFont.systemFontOfSize_(11),
            color=AppKit.NSColor.secondaryLabelColor(),
            wrap=True,
        )
    )

    y += card1_h + 12

    # Card 2: Storage & Appearance
    card2_h = 126
    card2 = _make_box(Foundation.NSMakeRect(pad, y, inner_w, card2_h))
    step1.addSubview_(card2)
    c2_view = FlippedView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, inner_w, card2_h))
    card2.setContentView_(c2_view)

    cy = 12
    c2_view.addSubview_(_make_label("Course Files Storage Folder", Foundation.NSMakeRect(cx, cy, cw, 16), font=AppKit.NSFont.boldSystemFontOfSize_(12), color=AppKit.NSColor.labelColor()))
    cy += 18
    folder_field = AppKit.NSTextField.alloc().initWithFrame_(Foundation.NSMakeRect(cx, cy, cw - 96, 24))
    folder_field.setStringValue_(current_data.get("LMS_STORAGE_DIR", ""))
    c2_view.addSubview_(folder_field)

    btn_browse = _make_push_button(
        "Browse…",
        Foundation.NSMakeRect(cx + cw - 88, cy - 2, 90, 28),
        target=controller,
        action="onBrowseFolder:",
    )
    c2_view.addSubview_(btn_browse)
    cy += 34

    c2_view.addSubview_(_make_label("Menu Bar Icon Theme", Foundation.NSMakeRect(cx, cy, cw, 16), font=AppKit.NSFont.boldSystemFontOfSize_(12), color=AppKit.NSColor.labelColor()))
    cy += 18
    theme_popup = AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(Foundation.NSMakeRect(cx - 2, cy, cw + 4, 26), False)
    theme_popup.addItemsWithTitles_([
        "Auto (Match macOS Appearance)",
        "Dark (White icon on dark menu bar)",
        "Light (Dark icon on light menu bar)",
    ])
    cur_t = (current_data.get("TRAY_THEME") or "auto").lower().strip()
    if cur_t == "dark":
        theme_popup.selectItemAtIndex_(1)
    elif cur_t == "light":
        theme_popup.selectItemAtIndex_(2)
    else:
        theme_popup.selectItemAtIndex_(0)
    c2_view.addSubview_(theme_popup)

    y += card2_h + 12

    # Card 3: Sync Options
    card3_h = 192
    card3 = _make_box(Foundation.NSMakeRect(pad, y, inner_w, card3_h))
    step1.addSubview_(card3)
    c3_view = FlippedView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, inner_w, card3_h))
    card3.setContentView_(c3_view)

    cy = 12
    chk_ann = _make_checkbox(
        "Keep all lecturer announcements (.docx)",
        Foundation.NSMakeRect(cx, cy, cw, 22),
        checked=current_data.get("LMS_KEEP_ALL_ANNOUNCEMENTS", "false").lower() in ("true", "1", "yes"),
    )
    c3_view.addSubview_(chk_ann)
    cy += 26

    chk_hermes = _make_checkbox(
        "Send updates via Hermes messaging",
        Foundation.NSMakeRect(cx, cy, cw, 22),
        checked=current_data.get("LMS_HERMES_MESSAGING", "false").lower() in ("true", "1", "yes"),
    )
    c3_view.addSubview_(chk_hermes)
    cy += 26

    expand_checked = current_data.get("LMS_EXPAND_ZIPS", "false").lower() in ("true", "1", "yes")
    chk_expand_zips = _make_checkbox(
        "Expand imported .zip archives (<name>_zip)",
        Foundation.NSMakeRect(cx, cy, cw, 22),
        checked=expand_checked,
        target=controller,
        action="onToggleExpandZips:",
    )
    c3_view.addSubview_(chk_expand_zips)
    cy += 20

    c3_view.addSubview_(
        _make_label(
            "Note: Compute intensive — not suitable for low-power machines",
            Foundation.NSMakeRect(cx + 22, cy, cw - 22, 16),
            font=AppKit.NSFont.systemFontOfSize_(11),
            color=AppKit.NSColor.systemOrangeColor(),
        )
    )
    cy += 22

    chk_delete_zip = _make_checkbox(
        "Delete original .zip file after decompression",
        Foundation.NSMakeRect(cx + 20, cy, cw - 20, 22),
        checked=current_data.get("LMS_DELETE_ORIGINAL_ZIP", "false").lower() in ("true", "1", "yes"),
    )
    chk_delete_zip.setEnabled_(expand_checked)
    c3_view.addSubview_(chk_delete_zip)
    cy += 34

    c3_view.addSubview_(
        _make_label(
            "Skip files larger than (MB, 0 = off)",
            Foundation.NSMakeRect(cx, cy + 3, cw - 100, 18),
            font=AppKit.NSFont.boldSystemFontOfSize_(12),
            color=AppKit.NSColor.labelColor(),
        )
    )
    max_mb_field = AppKit.NSTextField.alloc().initWithFrame_(Foundation.NSMakeRect(cx + cw - 84, cy, 84, 24))
    max_mb_field.setAlignment_(AppKit.NSTextAlignmentRight)
    max_mb_field.setStringValue_(current_data.get("LMS_MAX_FILE_SIZE_MB", "0") or "0")
    c3_view.addSubview_(max_mb_field)

    # Bottom bar Step 1
    bar_y = win_h - 50
    spinner = AppKit.NSProgressIndicator.alloc().initWithFrame_(Foundation.NSMakeRect(pad, bar_y + 4, 18, 18))
    spinner.setStyle_(AppKit.NSProgressIndicatorStyleSpinning)
    spinner.setDisplayedWhenStopped_(False)
    spinner.setHidden_(True)
    step1.addSubview_(spinner)

    status_lbl = _make_label(
        "",
        Foundation.NSMakeRect(pad + 24, bar_y + 5, 220, 18),
        font=AppKit.NSFont.systemFontOfSize_(12),
        color=AppKit.NSColor.systemBlueColor(),
    )
    step1.addSubview_(status_lbl)

    next_title = "Apply Settings" if is_settings else "Connect & Choose Subjects"
    next_w = 136 if is_settings else 210
    btn_next = _make_push_button(
        next_title,
        Foundation.NSMakeRect(win_w - pad - next_w, bar_y, next_w, 32),
        target=controller,
        action="onNextOrApply:",
        primary=True,
    )
    step1.addSubview_(btn_next)

    btn_choose = _make_push_button(
        "Choose Subjects…",
        Foundation.NSMakeRect(win_w - pad - next_w - 150, bar_y, 142, 32),
        target=controller,
        action="onChooseSubjects:",
    )
    if not is_settings:
        btn_choose.setHidden_(True)
    step1.addSubview_(btn_choose)

    # Tab order
    url_field.setNextKeyView_(user_field)
    user_field.setNextKeyView_(pass_field)
    pass_field.setNextKeyView_(folder_field)
    folder_field.setNextKeyView_(max_mb_field)
    max_mb_field.setNextKeyView_(url_field)

    # =========================================================================
    # STEP 2 VIEW (Course Selection)
    # =========================================================================
    step2 = FlippedView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, win_w, win_h))
    step2.setHidden_(True)
    root_view.addSubview_(step2)
    state["step2_view"] = step2

    y2 = 20
    step2.addSubview_(
        _make_label(
            "Select Courses to Monitor",
            Foundation.NSMakeRect(pad, y2, inner_w, 24),
            font=AppKit.NSFont.boldSystemFontOfSize_(17),
            color=AppKit.NSColor.labelColor(),
        )
    )
    step2.addSubview_(
        _make_label(
            "Sorted recent to ancient. Uncheck archived or completed subjects.",
            Foundation.NSMakeRect(pad, y2 + 24, inner_w, 18),
            font=AppKit.NSFont.systemFontOfSize_(12),
            color=AppKit.NSColor.secondaryLabelColor(),
        )
    )
    y2 += 54

    count_lbl = _make_label(
        "0 selected",
        Foundation.NSMakeRect(pad, y2 + 5, 180, 18),
        font=AppKit.NSFont.boldSystemFontOfSize_(12),
        color=AppKit.NSColor.systemBlueColor(),
    )
    step2.addSubview_(count_lbl)

    step2.addSubview_(_make_push_button("Top 5 Recent", Foundation.NSMakeRect(win_w - pad - 114, y2, 114, 28), target=controller, action="onSelectTop5:"))
    step2.addSubview_(_make_push_button("Deselect All", Foundation.NSMakeRect(win_w - pad - 224, y2, 104, 28), target=controller, action="onDeselectAll:"))
    step2.addSubview_(_make_push_button("Select All", Foundation.NSMakeRect(win_w - pad - 318, y2, 88, 28), target=controller, action="onSelectAll:"))
    y2 += 38

    scroll_h = win_h - y2 - 66
    course_scroll = AppKit.NSScrollView.alloc().initWithFrame_(Foundation.NSMakeRect(pad, y2, inner_w, scroll_h))
    course_scroll.setHasVerticalScroller_(True)
    course_scroll.setBorderType_(AppKit.NSBezelBorder)
    course_scroll.setDrawsBackground_(True)
    course_scroll.setBackgroundColor_(AppKit.NSColor.controlBackgroundColor())
    course_doc_view = FlippedView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, inner_w - 16, scroll_h))
    course_scroll.setDocumentView_(course_doc_view)
    step2.addSubview_(course_scroll)

    btn_back = _make_push_button("Back", Foundation.NSMakeRect(pad, bar_y, 88, 32), target=controller, action="onBackToStep1:")
    step2.addSubview_(btn_back)

    save_title = "Done" if is_settings else "Save & Start Sentinel"
    save_w = 100 if is_settings else 184
    btn_save = _make_push_button(
        save_title,
        Foundation.NSMakeRect(win_w - pad - save_w, bar_y, save_w, 32),
        target=controller,
        action="onStep2Done:",
        primary=True,
    )
    step2.addSubview_(btn_save)

    state.update({
        "url_field": url_field,
        "user_field": user_field,
        "pass_field": pass_field,
        "folder_field": folder_field,
        "theme_popup": theme_popup,
        "chk_ann": chk_ann,
        "chk_hermes": chk_hermes,
        "chk_expand_zips": chk_expand_zips,
        "chk_delete_zip": chk_delete_zip,
        "max_mb_field": max_mb_field,
        "spinner": spinner,
        "status_lbl": status_lbl,
        "btn_next": btn_next,
        "btn_choose": btn_choose,
        "btn_web_login": btn_web_login,
        "count_lbl": count_lbl,
        "course_scroll": course_scroll,
        "course_doc_view": course_doc_view,
    })

    window.makeKeyAndOrderFront_(None)
    window.makeFirstResponder_(url_field)
    app.activateIgnoringOtherApps_(True)
    app.run()

    return state["saved"]


class _InfoActionHandler(Foundation.NSObject):
    def initWithWindow_(self, window):
        self = objc.super(_InfoActionHandler, self).init()
        if self is None:
            return None
        self.window = window
        return self

    @objc.IBAction
    def onClose_(self, sender):
        self.window.close()

    def windowWillClose_(self, notification):
        _stop_nsapp_loop(AppKit.NSApplication.sharedApplication())


def show_info_window_mac(title, content):
    app = AppKit.NSApplication.sharedApplication()
    app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    _install_standard_menus(app)

    win_w, win_h = 620, 480
    style = (
        AppKit.NSWindowStyleMaskTitled
        | AppKit.NSWindowStyleMaskClosable
        | AppKit.NSWindowStyleMaskMiniaturizable
        | AppKit.NSWindowStyleMaskResizable
    )
    window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        Foundation.NSMakeRect(0, 0, win_w, win_h),
        style,
        AppKit.NSBackingStoreBuffered,
        False,
    )
    window.setMinSize_(Foundation.NSMakeSize(440, 320))
    window.setTitle_(title)
    window.center()

    content_view = window.contentView()
    pad = 20

    handler = _InfoActionHandler.alloc().initWithWindow_(window)
    window.setDelegate_(handler)

    # Bottom Close button
    btn_close = _make_push_button(
        "Close",
        Foundation.NSMakeRect(win_w - pad - 92, 16, 92, 32),
        target=handler,
        action="onClose:",
        primary=True,
    )
    btn_close.setAutoresizingMask_(AppKit.NSViewMinXMargin | AppKit.NSViewMaxYMargin)
    content_view.addSubview_(btn_close)

    # Header
    header_y = win_h - 48
    icon_img = _load_app_icon()
    title_x = pad
    if icon_img is not None:
        iv = AppKit.NSImageView.alloc().initWithFrame_(Foundation.NSMakeRect(pad, header_y - 2, 30, 30))
        iv.setImage_(icon_img)
        iv.setAutoresizingMask_(AppKit.NSViewMinYMargin)
        content_view.addSubview_(iv)
        title_x = pad + 40

    lbl = _make_label(
        title,
        Foundation.NSMakeRect(title_x, header_y, win_w - title_x - pad, 24),
        font=AppKit.NSFont.boldSystemFontOfSize_(16),
        color=AppKit.NSColor.labelColor(),
    )
    lbl.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewMinYMargin)
    content_view.addSubview_(lbl)

    # Scrollable NSTextView
    scroll_y = 60
    scroll_h = win_h - scroll_y - 56
    scroll_view = AppKit.NSScrollView.alloc().initWithFrame_(Foundation.NSMakeRect(pad, scroll_y, win_w - pad * 2, scroll_h))
    scroll_view.setHasVerticalScroller_(True)
    scroll_view.setBorderType_(AppKit.NSBezelBorder)
    scroll_view.setAutoresizingMask_(AppKit.NSViewWidthSizable | AppKit.NSViewHeightSizable)

    text_view = AppKit.NSTextView.alloc().initWithFrame_(Foundation.NSMakeRect(0, 0, win_w - pad * 2 - 16, scroll_h))
    text_view.setEditable_(False)
    text_view.setSelectable_(True)
    text_view.setDrawsBackground_(True)
    text_view.setBackgroundColor_(AppKit.NSColor.textBackgroundColor())
    text_view.setTextColor_(AppKit.NSColor.labelColor())
    text_view.setFont_(AppKit.NSFont.monospacedSystemFontOfSize_weight_(12.5, 0.0))
    text_view.setTextContainerInset_(Foundation.NSMakeSize(10, 10))
    text_view.setVerticallyResizable_(True)
    text_view.setHorizontallyResizable_(False)
    text_view.setMinSize_(Foundation.NSMakeSize(0, scroll_h))
    text_view.setMaxSize_(Foundation.NSMakeSize(1e7, 1e7))
    if text_view.textContainer() is not None:
        text_view.textContainer().setWidthTracksTextView_(True)
    text_view.setString_(content or "")
    text_view.setAutoresizingMask_(AppKit.NSViewWidthSizable)

    scroll_view.setDocumentView_(text_view)
    content_view.addSubview_(scroll_view)

    window.makeKeyAndOrderFront_(None)
    app.activateIgnoringOtherApps_(True)
    app.run()
