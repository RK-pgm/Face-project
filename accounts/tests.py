"""
ชุดทดสอบอัตโนมัติ — รันด้วย:  py manage.py test

ทดสอบฝั่ง Django ทั้งหมด (สมัคร, ล็อกอิน, ล็อกชั่วคราว, ส่งชีต ฯลฯ)
ส่วนที่ต้องใช้กล้องจริง (face-api.js) ต้องทดสอบด้วยมือตามขั้นตอนใน README.md
"""
import base64
import json
import random
from io import BytesIO
from unittest import mock

from django.contrib.auth.hashers import check_password
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from . import faces, sheets
from .models import LoginLog, LoginThrottle, Person


def make_descriptor(seed, noise=0.0):
    """สร้าง descriptor ปลอม 128 ค่า (seed เดียวกัน = 'ใบหน้าเดียวกัน', noise = ความคลาดเคลื่อนตอนสแกนซ้ำ)"""
    rng = random.Random(seed)
    base = [rng.uniform(-0.2, 0.2) for _ in range(128)]
    if noise:
        noise_rng = random.Random(seed * 1000 + 7)
        base = [v + noise_rng.uniform(-noise, noise) for v in base]
    return base


def make_photo_data_url(fmt="JPEG"):
    image = Image.new("RGB", (640, 480), (120, 160, 200))
    buffer = BytesIO()
    image.save(buffer, format=fmt)
    mime = "image/jpeg" if fmt == "JPEG" else "image/png"
    return f"data:{mime};base64," + base64.b64encode(buffer.getvalue()).decode()


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type="application/json")


REGISTER_OK = {
    "first_name": "สมชาย", "last_name": "ใจดี", "nickname": "ชาย",
    "pin": "1234", "pin_confirm": "1234", "consent": True,
}


# ใช้แฮชแบบเร็วเฉพาะตอนรันเทสต์ (ของจริงใช้ PBKDF2 ที่ช้าโดยตั้งใจ) เพื่อให้เทสต์เสร็จไวขึ้น
FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@override_settings(SHEETS_USE_THREAD=False, MEDIA_ROOT="/tmp/face_login_test_media", PASSWORD_HASHERS=FAST_HASHERS)
class BaseCase(TestCase):
    def register(self, client=None, seed=1, **overrides):
        data = dict(REGISTER_OK, descriptor=make_descriptor(seed), photo=make_photo_data_url(), **overrides)
        return post_json(client or self.client, reverse("register"), data)

    def login(self, name="สมชาย", pin="1234", descriptor=None, client=None):
        descriptor = descriptor if descriptor is not None else make_descriptor(1, noise=0.005)
        # TestCase ครอบทุกอย่างไว้ใน transaction ที่ไม่ commit จริง จึงต้องสั่งให้รัน on_commit เอง
        with self.captureOnCommitCallbacks(execute=True):
            return post_json(client or self.client, reverse("login"),
                             {"name": name, "pin": pin, "descriptor": descriptor})


class RegisterTests(BaseCase):
    def test_register_success_hashes_pin_and_creates_member_code(self):
        response = self.register()
        self.assertEqual(response.status_code, 200)
        person = Person.objects.get()
        self.assertNotEqual(person.pin_hash, "1234")
        self.assertTrue(check_password("1234", person.pin_hash))
        self.assertRegex(person.member_code, r"^MB-[0-9A-Z]{6}$")
        self.assertTrue(person.consent_pdpa and person.consent_at)
        self.assertEqual(len(person.face_descriptor), 128)
        self.assertTrue(person.face_photo.name.startswith("faces/"))

    def test_member_codes_are_unique(self):
        self.register(first_name="ก")
        self.register(first_name="ข")
        codes = list(Person.objects.values_list("member_code", flat=True))
        self.assertEqual(len(set(codes)), 2)

    def test_consent_is_required(self):
        response = self.register(consent=False)
        self.assertEqual(response.status_code, 400)
        self.assertIn("consent", response.json()["errors"])
        self.assertEqual(Person.objects.count(), 0)

    def test_pin_must_be_4_to_6_digits(self):
        for bad in ("123", "1234567", "12a4", "abcd", ""):
            response = self.register(pin=bad, pin_confirm=bad)
            self.assertEqual(response.status_code, 400, bad)
        self.assertEqual(Person.objects.count(), 0)

    def test_pin_confirmation_must_match(self):
        response = self.register(pin_confirm="4321")
        self.assertEqual(response.status_code, 400)
        self.assertIn("pin_confirm", response.json()["errors"])

    def test_pin_sent_as_number_is_rejected(self):
        # ถ้าส่งเป็นตัวเลข (ไม่ใช่ข้อความ) เลข 0 นำหน้าจะหาย จึงไม่รับ
        response = self.register(pin=1234, pin_confirm=1234)
        self.assertEqual(response.status_code, 400)

    def test_bad_descriptor_rejected(self):
        for bad in (None, [0.1] * 127, ["a"] * 128, [99] * 128, [0] * 128):
            data = dict(REGISTER_OK, descriptor=bad, photo=make_photo_data_url())
            response = post_json(self.client, reverse("register"), data)
            self.assertEqual(response.status_code, 400, str(bad)[:30])
        self.assertEqual(Person.objects.count(), 0)

    def test_bad_photo_rejected(self):
        for bad in (None, "hello", "data:image/jpeg;base64,@@@@", "data:image/jpeg;base64," + base64.b64encode(b"not an image").decode()):
            data = dict(REGISTER_OK, descriptor=make_descriptor(1), photo=bad)
            response = post_json(self.client, reverse("register"), data)
            self.assertEqual(response.status_code, 400, str(bad)[:30])

    def test_control_characters_in_name_rejected(self):
        response = self.register(first_name="สม\nชาย")
        self.assertEqual(response.status_code, 400)

    def test_thai_names_with_vowel_marks_are_accepted(self):
        response = self.register(first_name="ศิริพร", last_name="เก่งกาจ", nickname="ปุ๊กกี้")
        self.assertEqual(response.status_code, 200)

    def test_malformed_json(self):
        response = self.client.post(reverse("register"), data="{oops", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_register_requires_csrf(self):
        strict = Client(enforce_csrf_checks=True)
        data = dict(REGISTER_OK, descriptor=make_descriptor(1), photo=make_photo_data_url())
        response = post_json(strict, reverse("register"), data)
        self.assertEqual(response.status_code, 403)

    def test_stored_photo_is_reencoded_jpeg(self):
        self.register()
        person = Person.objects.get()
        with person.face_photo.open("rb") as fh:
            image = Image.open(fh)
            self.assertEqual(image.format, "JPEG")
            self.assertLessEqual(max(image.size), 480)


class LoginTests(BaseCase):
    def setUp(self):
        self.register(seed=1)
        self.client = Client()  # ผู้ใช้ใหม่ที่ยังไม่ล็อกอิน

    def test_success_needs_name_pin_and_face(self):
        with mock.patch("accounts.views.sheets.enqueue_sync") as enqueue:
            response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        log = LoginLog.objects.get(success=True)
        self.assertEqual(log.sheet_status, LoginLog.SheetStatus.PENDING)
        enqueue.assert_called_once()

    def test_name_is_case_insensitive_and_trims_spaces(self):
        self.assertEqual(self.login(name="  สมชาย  ").status_code, 200)

    def test_wrong_pin_gives_generic_message(self):
        response = self.login(pin="9999")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["message"], "ข้อมูลไม่ถูกต้อง")
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_someone_elses_face_rejected(self):
        response = self.login(descriptor=make_descriptor(2))  # คนละใบหน้า
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["message"], "ข้อมูลไม่ถูกต้อง")

    def test_unknown_name_gives_same_message(self):
        response = self.login(name="ไม่มีชื่อนี้")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["message"], "ข้อมูลไม่ถูกต้อง")

    def test_all_failures_look_identical_to_the_client(self):
        bodies = {
            json.dumps(self.login(pin="9999").json()),
            json.dumps(self.login(descriptor=make_descriptor(2)).json()),
            json.dumps(self.login(name="xyz").json()),
        }
        self.assertEqual(len(bodies), 1)

    def test_threshold_boundary(self):
        stored = Person.objects.get().face_descriptor
        def shifted(distance):
            v = list(stored)
            v[0] += distance
            return v
        with self.settings(FACE_MATCH_THRESHOLD=0.5):
            self.assertEqual(self.login(descriptor=shifted(0.49)).status_code, 200)
            self.client = Client()
            self.assertEqual(self.login(descriptor=shifted(0.51)).status_code, 401)

    def test_threshold_is_configurable(self):
        stored = Person.objects.get().face_descriptor
        v = list(stored); v[0] += 0.55
        with self.settings(FACE_MATCH_THRESHOLD=0.6):
            self.assertEqual(self.login(descriptor=v).status_code, 200)

    def test_lock_after_five_failures_then_even_correct_login_is_blocked(self):
        for _ in range(5):
            self.assertEqual(self.login(pin="0000").status_code, 401)
        blocked = self.login()  # ข้อมูลถูกต้องแต่ถูกล็อกอยู่
        self.assertEqual(blocked.status_code, 429)
        self.assertTrue(blocked.json()["locked"])
        self.assertIn("นาที", blocked.json()["message"])

    def test_lock_expires(self):
        for _ in range(5):
            self.login(pin="0000")
        LoginThrottle.objects.update(locked_until=None)
        self.assertEqual(self.login().status_code, 200)

    def test_lock_also_applies_to_unknown_names(self):
        # ล็อกด้วยเหมือนกัน เพื่อไม่ให้รู้ว่าชื่อไหนมีอยู่จริง
        for _ in range(5):
            self.login(name="ผีสาง")
        self.assertEqual(self.login(name="ผีสาง").status_code, 429)

    def test_success_resets_failure_counter(self):
        for _ in range(4):
            self.login(pin="0000")
        self.assertEqual(self.login().status_code, 200)
        self.client = Client()
        for _ in range(4):
            self.login(pin="0000")
        self.assertEqual(self.login().status_code, 200)  # ยังไม่ถูกล็อก

    def test_failures_are_logged_and_visible_on_dashboard(self):
        self.login(pin="0000")
        self.login()
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "ไม่สำเร็จ")
        self.assertContains(response, "สำเร็จ")
        person = Person.objects.get()
        self.assertEqual(person.logs.filter(success=False).count(), 1)
        self.assertEqual(person.logs.get(success=False).fail_reason, "pin")

    def test_two_people_same_first_name_are_told_apart_by_pin_and_face(self):
        other = Client()
        self.register(client=other, seed=5, last_name="คนอื่น", pin="7777", pin_confirm="7777")
        self.assertEqual(Person.objects.count(), 2)
        me = Client()
        self.assertEqual(self.login(pin="7777", descriptor=make_descriptor(5, 0.005), client=me).status_code, 200)
        # เข้าด้วย PIN ของคนหนึ่ง แต่หน้าของอีกคน ต้องไม่ผ่าน
        again = Client()
        self.assertEqual(self.login(pin="7777", descriptor=make_descriptor(1, 0.005), client=again).status_code, 401)

    def test_malformed_login_payloads(self):
        for payload in ({}, {"name": "สมชาย"}, {"name": "สมชาย", "pin": "1234"},
                        {"name": "สมชาย", "pin": 1234, "descriptor": make_descriptor(1)},
                        {"name": ["x"], "pin": "1234", "descriptor": make_descriptor(1)}):
            response = post_json(self.client, reverse("login"), payload)
            self.assertIn(response.status_code, (401, 429), str(payload)[:40])

    def test_login_requires_csrf(self):
        strict = Client(enforce_csrf_checks=True)
        response = post_json(strict, reverse("login"), {"name": "สมชาย", "pin": "1234", "descriptor": make_descriptor(1)})
        self.assertEqual(response.status_code, 403)

    def test_session_key_changes_on_login(self):
        self.client.get(reverse("login"))
        before = self.client.session.session_key
        self.login()
        self.assertNotEqual(self.client.session.session_key, before)


class DashboardTests(BaseCase):
    def setUp(self):
        self.register(seed=1)
        self.client = Client()

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)

    def test_photo_requires_login(self):
        self.assertEqual(self.client.get(reverse("my_photo")).status_code, 302)

    def test_dashboard_content_and_photo_after_login(self):
        self.login()
        response = self.client.get(reverse("dashboard"))
        person = Person.objects.get()
        for text in (person.first_name, person.last_name, person.nickname, person.member_code):
            self.assertContains(response, text)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        photo = self.client.get(reverse("my_photo"))
        self.assertEqual(photo.status_code, 200)
        self.assertEqual(photo["Content-Type"], "image/jpeg")

    def test_person_cannot_see_someone_elses_photo(self):
        other = Client()
        self.register(client=other, seed=9, first_name="อีกคน")
        self.login()
        mine = b"".join(self.client.get(reverse("my_photo")).streaming_content)
        self.assertTrue(mine.startswith(b"\xff\xd8"))  # เป็นไฟล์ JPEG ของตัวเอง
        # ไม่มี URL ที่รับ id ของคนอื่นเลย: my_photo ไม่รับพารามิเตอร์
        self.assertEqual(self.client.get("/me/photo/?id=2").status_code, 200)

    def test_logout_is_post_only_and_clears_session(self):
        self.login()
        self.assertEqual(self.client.get(reverse("logout")).status_code, 405)
        self.client.post(reverse("logout"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_media_files_are_not_publicly_served(self):
        self.login()
        person = Person.objects.get()
        self.assertEqual(Client().get("/media/" + person.face_photo.name).status_code, 404)

    def test_pages_render(self):
        for name in ("login", "register"):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'name="csrf-token"')


@override_settings(
    SHEETS_USE_THREAD=False, GOOGLE_SHEET_ID="sheet123",
    GOOGLE_SERVICE_ACCOUNT_FILE="/tmp/fake.json", MEDIA_ROOT="/tmp/face_login_test_media",
    PASSWORD_HASHERS=FAST_HASHERS,
)
class SheetTests(BaseCase):
    def setUp(self):
        sheets._forget_connection()
        self.register(seed=1)
        self.client = Client()

    def tearDown(self):
        sheets._forget_connection()

    def test_row_contains_expected_fields_and_no_pin(self):
        worksheet = mock.MagicMock()
        with mock.patch.object(sheets, "_get_worksheet", return_value=worksheet):
            self.assertEqual(self.login().status_code, 200)
        worksheet.append_row.assert_called_once()
        row, kwargs = worksheet.append_row.call_args
        values = row[0]
        person = Person.objects.get()
        self.assertEqual(values[1:], [person.full_name, person.nickname, person.member_code])
        self.assertRegex(values[0], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        self.assertEqual(kwargs["value_input_option"], "RAW")
        self.assertNotIn("1234", " ".join(map(str, values)))
        self.assertEqual(LoginLog.objects.get(success=True).sheet_status, "sent")

    def test_row_uses_bangkok_time(self):
        person = Person.objects.get()
        log = LoginLog.objects.create(person=person, success=True, sheet_status="pending")
        from django.utils import timezone
        import datetime
        log.created_at = datetime.datetime(2026, 1, 1, 0, 30, tzinfo=datetime.timezone.utc)
        self.assertEqual(sheets._row_for(log)[0], "2026-01-01 07:30:00")

    def test_sheet_failure_does_not_break_login_and_is_retried_later(self):
        worksheet = mock.MagicMock()
        worksheet.append_row.side_effect = ConnectionError("network down")
        with mock.patch.object(sheets, "_get_worksheet", return_value=worksheet):
            response = self.login()
        self.assertEqual(response.status_code, 200)               # ล็อกอินยังสำเร็จ
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        log = LoginLog.objects.get(success=True)
        self.assertEqual(log.sheet_status, "failed")
        self.assertEqual(log.sheet_attempts, 1)
        self.assertIn("ConnectionError", log.sheet_error)

        # เน็ตกลับมา: ลองส่งใหม่ (เหมือนสั่ง manage.py sync_sheet)
        good = mock.MagicMock()
        with mock.patch.object(sheets, "_get_worksheet", return_value=good):
            sent, failed = sheets.sync_pending_logs()
        self.assertEqual((sent, failed), (1, 0))
        log.refresh_from_db()
        self.assertEqual(log.sheet_status, "sent")
        self.assertEqual(log.sheet_attempts, 2)

    def test_sent_rows_are_not_sent_twice(self):
        worksheet = mock.MagicMock()
        with mock.patch.object(sheets, "_get_worksheet", return_value=worksheet):
            self.login()
            sheets.sync_pending_logs()
            sheets.sync_pending_logs()
        self.assertEqual(worksheet.append_row.call_count, 1)

    def test_failed_logins_are_never_sent(self):
        worksheet = mock.MagicMock()
        with mock.patch.object(sheets, "_get_worksheet", return_value=worksheet):
            self.login(pin="0000")
            sheets.sync_pending_logs()
        worksheet.append_row.assert_not_called()

    def test_stops_at_first_error_and_keeps_order(self):
        person = Person.objects.get()
        for _ in range(3):
            LoginLog.objects.create(person=person, success=True, sheet_status="pending")
        worksheet = mock.MagicMock()
        worksheet.append_row.side_effect = [None, RuntimeError("quota"), None]
        with mock.patch.object(sheets, "_get_worksheet", return_value=worksheet):
            sent, failed = sheets.sync_pending_logs()
        self.assertEqual((sent, failed), (1, 1))
        self.assertEqual(worksheet.append_row.call_count, 2)
        self.assertEqual(LoginLog.objects.filter(sheet_status="pending").count(), 1)

    def test_stuck_sending_rows_are_recovered(self):
        import datetime
        from django.utils import timezone
        person = Person.objects.get()
        LoginLog.objects.create(person=person, success=True, sheet_status="sending",
                                sheet_last_try=timezone.now() - datetime.timedelta(minutes=10))
        worksheet = mock.MagicMock()
        with mock.patch.object(sheets, "_get_worksheet", return_value=worksheet):
            self.assertEqual(sheets.sync_pending_logs(), (1, 0))

    @override_settings(GOOGLE_SHEET_ID="", GOOGLE_SERVICE_ACCOUNT_FILE="", GOOGLE_SERVICE_ACCOUNT_JSON="")
    def test_not_configured_means_login_works_and_rows_wait(self):
        self.assertFalse(sheets.is_configured())
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(LoginLog.objects.get(success=True).sheet_status, "pending")


class FaceHelperTests(TestCase):
    def test_distance_is_euclidean(self):
        a = [0.0] * 128
        b = [0.0] * 128
        b[0] = 0.3
        b[1] = 0.4
        self.assertAlmostEqual(faces.face_distance(a, b), 0.5)

    @override_settings(FACE_MATCH_THRESHOLD=0.5)
    def test_is_same_person_uses_strict_less_than(self):
        self.assertTrue(faces.is_same_person(0.499))
        self.assertFalse(faces.is_same_person(0.5))

    def test_png_is_accepted_and_converted(self):
        file = faces.photo_from_data_url(make_photo_data_url("PNG"))
        self.assertEqual(Image.open(BytesIO(file.read())).format, "JPEG")
