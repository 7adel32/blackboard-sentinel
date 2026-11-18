import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class TestCourseMessagesFeature(unittest.TestCase):
    def test_download_messages_disabled_by_default(self):
        import check_lms

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            old_val = os.environ.pop("LMS_DOWNLOAD_MESSAGES", None)
            old_alias = os.environ.pop("DOWNLOAD_MESSAGES", None)
            try:
                os.chdir(tmp)
                with mock.patch.object(check_lms, "get_keyring_password", return_value=""), \
                     mock.patch.object(check_lms, "set_keyring_password", return_value=True):
                    check_lms.init_config(override=True)
                    self.assertFalse(check_lms.DOWNLOAD_MESSAGES)

                fake_client = mock.MagicMock()
                course_dir = os.path.join(tmp, "Course 601")
                info = {"id": "_c1_1", "code": "601 CSC", "name": "Course 601", "dir": course_dir, "doctor": "Dr. Test"}
                state = {"seen_messages": []}
                alerts = check_lms.check_course_messages(fake_client, state, courses_map={"_c1_1": info})
                self.assertEqual(alerts, [])
                fake_client.get_paginated_json.assert_not_called()
                self.assertFalse(os.path.exists(os.path.join(course_dir, "messages")))
            finally:
                os.chdir(old_cwd)
                if old_val is not None:
                    os.environ["LMS_DOWNLOAD_MESSAGES"] = old_val
                if old_alias is not None:
                    os.environ["DOWNLOAD_MESSAGES"] = old_alias
                check_lms.init_config(override=True)

    def test_check_messages_generates_thread_and_index_html_with_attachment_badges(self):
        import check_lms

        with tempfile.TemporaryDirectory() as tmp:
            course_dir = os.path.join(tmp, "University", "Research Methods")
            os.makedirs(course_dir, exist_ok=True)
            info = {
                "id": "_c1_1",
                "code": "608 CSC",
                "name": "Research Methods",
                "dir": course_dir,
                "doctor": "Dr. Lecturer",
            }

            fake_client = mock.MagicMock()
            fake_client.student_user_id = "_stu_1"

            def fake_paginated(url):
                if url == "/learn/api/public/v1/courses/_c1_1/users?expand=user":
                    return {
                        "results": [
                            {
                                "userId": "_inst_1",
                                "courseRoleId": "Instructor",
                                "user": {"id": "_inst_1", "name": {"given": "Dr.", "family": "Lecturer"}},
                            },
                            {
                                "userId": "_stu_2",
                                "courseRoleId": "Student",
                                "user": {"id": "_stu_2", "name": {"given": "Peer", "family": "Student"}},
                            },
                        ]
                    }
                if url == "/learn/api/v1/courses/_c1_1/conversations":
                    return {
                        "results": [
                            {
                                "id": "_conv_lect",
                                "subject": "Project Feedback",
                                "updatedDate": "2026-11-16T13:56:44.240Z",
                                "participantIds": ["_inst_1", "_stu_1"],
                            },
                            {
                                "id": "_conv_peer",
                                "subject": "Peer Chat",
                                "updatedDate": "2026-11-16T10:00:00.000Z",
                                "participantIds": ["_stu_2", "_stu_1"],
                            },
                        ]
                    }
                if url == "/learn/api/v1/courses/_c1_1/conversations/_conv_lect/messages":
                    return {
                        "results": [
                            {
                                "id": "_m1",
                                "senderId": "_stu_1",
                                "sender": {"id": "_stu_1", "givenName": "Me"},
                                "postDate": "2026-11-15T09:00:00.000Z",
                                "body": {"displayText": "<p>Hello Doctor, attached is my draft.</p>"},
                                "attachments": [{"fileName": "draft_v1.pdf"}],
                            },
                            {
                                "id": "_m2",
                                "senderId": "_inst_1",
                                "sender": {"id": "_inst_1", "givenName": "Dr.", "familyName": "Lecturer"},
                                "postDate": "2026-11-16T13:56:44.240Z",
                                "body": {
                                    "displayText": (
                                        '<p dir="rtl">راجع الملاحظات.</p>'
                                        '<a data-bbfile="{&quot;fileName&quot;:&quot;rubric.docx&quot;}">rubric.docx</a>'
                                    )
                                },
                            },
                        ]
                    }
                if url == "/learn/api/v1/courses/_c1_1/conversations/_conv_peer/messages":
                    return {
                        "results": [
                            {
                                "id": "_m3",
                                "senderId": "_stu_2",
                                "sender": {"id": "_stu_2", "givenName": "Peer", "familyName": "Student"},
                                "postDate": "2026-11-16T10:00:00.000Z",
                                "body": {"displayText": "<p>Hey classmate</p>"},
                            }
                        ]
                    }
                return {"results": []}

            fake_client.get_paginated_json.side_effect = fake_paginated

            state = {"seen_messages": []}
            old_dl = check_lms.DOWNLOAD_MESSAGES
            old_storage = check_lms.LMS_STORAGE_DIR
            try:
                check_lms.DOWNLOAD_MESSAGES = True
                check_lms.LMS_STORAGE_DIR = os.path.join(tmp, "University")

                alerts = check_lms.check_course_messages(fake_client, state, courses_map={"_c1_1": info})
                self.assertEqual(len(alerts), 2)
                self.assertEqual({a["sender"] for a in alerts}, {"Me", "Dr. Lecturer"})

                msg_dir = os.path.join(course_dir, "messages")
                index_html = pathlib.Path(os.path.join(msg_dir, "index.html")).read_text(encoding="utf-8")
                thread_html = pathlib.Path(os.path.join(msg_dir, "Project Feedback.html")).read_text(encoding="utf-8")

                self.assertIn("Project Feedback.html", index_html)
                self.assertNotIn("Peer Chat", index_html)
                self.assertFalse(os.path.exists(os.path.join(msg_dir, "Peer Chat.html")))

                self.assertIn("Hello Doctor, attached is my draft.", thread_html)
                self.assertIn("راجع الملاحظات.", thread_html)
                self.assertIn("📎 draft_v1.pdf", thread_html)
                self.assertIn("📎 rubric.docx", thread_html)
                fake_client.download_file.assert_not_called()

                # Second run should not duplicate alerts, and should re-create deleted HTML
                os.remove(os.path.join(msg_dir, "Project Feedback.html"))
                alerts_second = check_lms.check_course_messages(fake_client, state, courses_map={"_c1_1": info})
                self.assertEqual(alerts_second, [])
                self.assertTrue(os.path.isfile(os.path.join(msg_dir, "Project Feedback.html")))
            finally:
                check_lms.DOWNLOAD_MESSAGES = old_dl
                check_lms.LMS_STORAGE_DIR = old_storage

    def test_format_update_messages_and_config_gui_defaults(self):
        import check_lms
        import config_gui

        # 6-argument backwards compatibility
        msgs6 = check_lms.format_update_messages([], [], [], [], [], [])
        self.assertEqual(msgs6, [])

        # 7-argument message formatting
        msgs7 = check_lms.format_update_messages(
            [], [], [], [], [], [],
            all_course_messages=[{
                "course": "Research Methods (608 CSC)",
                "doctor": "Dr. Lecturer",
                "sender": "Dr. Lecturer",
                "subject": "Project Feedback",
                "date": "Monday, Nov 16 at 04:56 PM",
                "body": "Please clarify section 2.",
                "attachments": ["notes.pdf"],
                "saved": os.path.join("Research Methods", "messages", "Project Feedback.html"),
            }],
        )
        self.assertEqual(len(msgs7), 1)
        self.assertIn("[Message]", msgs7[0])
        self.assertIn("notes.pdf", msgs7[0])

        with tempfile.TemporaryDirectory() as tmp:
            env_path = os.path.join(tmp, ".env")
            with open(env_path, "w", encoding="utf-8") as f:
                f.write('LMS_URL="https://lms.example.edu"\n')
            old_cwd = os.getcwd()
            try:
                os.chdir(tmp)
                with mock.patch("os.path.isfile", side_effect=lambda p: os.path.abspath(p) == os.path.abspath(env_path)):
                    cfg = config_gui.load_existing_config()
                self.assertEqual(cfg["LMS_DOWNLOAD_MESSAGES"], "false")

                with open(env_path, "a", encoding="utf-8") as f:
                    f.write('LMS_DOWNLOAD_MESSAGES="true"\n')
                with mock.patch("os.path.isfile", side_effect=lambda p: os.path.abspath(p) == os.path.abspath(env_path)):
                    cfg2 = config_gui.load_existing_config()
                self.assertEqual(cfg2["LMS_DOWNLOAD_MESSAGES"], "true")
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
