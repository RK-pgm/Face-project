import base64
import json
import random
import tempfile
from io import BytesIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from django.urls import reverse
from PIL import Image

from . import faces, sheets
from .models import LoginLog, LoginThrottle, Person


def make_descriptor(seed, noise=0.0):
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



FAST_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
_TEST_MEDIA = tempfile.TemporaryDirectory(prefix="face_login_test_media_")
TEST_MEDIA_ROOT = _TEST_MEDIA.name


@override_settings(SHEETS_USE_THREAD=False, MEDIA_ROOT=TEST_MEDIA_ROOT, PASSWORD_HASHERS=FAST_HASHERS)
class BaseCase(TestCase):
    def register(self, client=None, seed=1, **overrides):
        data = dict(REGISTER_OK, descriptor=make_descriptor(seed), photo=make_photo_data_url(), **overrides)
        return post_json(client or self.client, reverse("register"), data)

    def login(self, name="สมชาย", pin="1234", descriptor=None, client=None):
        descriptor = descriptor if descriptor is not None else make_descriptor(1, noise=0.005)

        with self.captureOnCommitCallbacks(execute=True):
            return post_json(client or self.client, reverse("login"),
                             {"name": name, "pin": pin, "descriptor": descriptor})

    def sign_out(self, client=None):
        with self.captureOnCommitCallbacks(execute=True):
            return (client or self.client).post(reverse("logout"))


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
        self.client = Client()

    def test_success_needs_name_pin_and_face(self):
        with mock.patch("accounts.views.sheets.enqueue_sync") as enqueue:
            response = self.login()
            enqueue.assert_not_called()
            self.sign_out()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        log = LoginLog.objects.get(success=True)
        self.assertEqual(log.sheet_status, LoginLog.SheetStatus.PENDING)
        self.assertIsNotNone(log.logged_out_at)
        enqueue.assert_called_once()

    def test_dashboard_records_payment_for_active_visit(self):
        self.login()
        response = self.client.post(reverse("dashboard"), {"amount": "12.50", "payment_method": "transfer"})
        self.assertRedirects(response, reverse("dashboard"))
        log = LoginLog.objects.get(success=True)
        self.assertEqual(str(log.amount), "12.50")
        self.assertEqual(log.payment_method, "transfer")
        self.assertEqual(log.recorded_by, "สมชาย ใจดี")

    def test_name_is_case_insensitive_and_trims_spaces(self):
        self.assertEqual(self.login(name="  สมชาย  ").status_code, 200)

    def test_wrong_pin_gives_generic_message(self):
        response = self.login(pin="9999")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["message"], "Sign-in failed.")
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)

    def test_someone_elses_face_rejected(self):
        response = self.login(descriptor=make_descriptor(2))
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["message"], "Sign-in failed.")

    def test_unknown_name_gives_same_message(self):
        response = self.login(name="ไม่มีชื่อนี้")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["message"], "Sign-in failed.")

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
        blocked = self.login()
        self.assertEqual(blocked.status_code, 429)
        self.assertTrue(blocked.json()["locked"])
        self.assertIn("minute", blocked.json()["message"])

    def test_lock_expires(self):
        for _ in range(5):
            self.login(pin="0000")
        LoginThrottle.objects.update(locked_until=None)
        self.assertEqual(self.login().status_code, 200)

    def test_lock_also_applies_to_unknown_names(self):

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
        self.assertEqual(self.login().status_code, 200)

    def test_failures_are_logged_and_visible_on_dashboard(self):
        self.login(pin="0000")
        self.login()
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "Failed")
        self.assertContains(response, "Successful")
        person = Person.objects.get()
        self.assertEqual(person.logs.filter(success=False).count(), 1)
        self.assertEqual(person.logs.get(success=False).fail_reason, "pin")

    def test_two_people_same_first_name_are_told_apart_by_pin_and_face(self):
        other = Client()
        self.register(client=other, seed=5, last_name="คนอื่น", pin="7777", pin_confirm="7777")
        self.assertEqual(Person.objects.count(), 2)
        me = Client()
        self.assertEqual(self.login(pin="7777", descriptor=make_descriptor(5, 0.005), client=me).status_code, 200)

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
        self.assertTrue(mine.startswith(b"\xff\xd8"))

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


class ChangeFaceTests(BaseCase):
    def setUp(self):
        self.register(seed=1)
        self.client = Client()
        self.login()

    def change_face(self, pin="1234", seed=2, client=None):
        return post_json(client or self.client, reverse("change_face"), {
            "pin": pin, "descriptor": make_descriptor(seed), "photo": make_photo_data_url(),
        })

    def test_requires_login(self):
        response = Client().get(reverse("change_face"))
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)

    def test_page_renders_when_logged_in(self):
        response = self.client.get(reverse("change_face"))
        self.assertEqual(response.status_code, 200)

    def test_wrong_pin_is_rejected_and_face_unchanged(self):
        before = Person.objects.get().face_descriptor
        response = self.change_face(pin="9999")
        self.assertEqual(response.status_code, 400)
        self.assertIn("pin", response.json()["errors"])
        self.assertEqual(Person.objects.get().face_descriptor, before)

    def test_correct_pin_updates_descriptor_and_replaces_photo(self):
        person = Person.objects.get()
        old_photo_name = person.face_photo.name
        response = self.change_face(seed=42)
        self.assertEqual(response.status_code, 200)
        person.refresh_from_db()
        self.assertEqual(person.face_descriptor, make_descriptor(42))
        self.assertNotEqual(person.face_photo.name, old_photo_name)
        self.assertFalse(person.face_photo.storage.exists(old_photo_name))

    def test_new_face_can_log_in_afterwards(self):
        self.change_face(seed=42)
        self.client.post(reverse("logout"))
        response = self.login(descriptor=make_descriptor(42, noise=0.005))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])

    def test_bad_pin_attempts_lock_out(self):
        for _ in range(5):
            self.change_face(pin="0000")
        response = self.change_face(pin="1234")
        self.assertEqual(response.status_code, 429)
        self.assertTrue(response.json()["locked"])
        self.assertEqual(
            Person.objects.get().face_descriptor,
            make_descriptor(1),
        )

    def test_invalid_face_data_is_rejected(self):
        response = post_json(self.client, reverse("change_face"), {"pin": "1234", "descriptor": [1, 2], "photo": "x"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("face", response.json()["errors"])


@override_settings(PASSWORD_HASHERS=FAST_HASHERS)
class CounterTests(BaseCase):

    def setUp(self):
        self.client = Client()
        self.register(seed=1)
        self.login()
        self.log = LoginLog.objects.get(success=True)
        self.client.post(reverse("logout"))

        User = get_user_model()
        self.staff = User.objects.create_user("mae", password="staffpass123", is_staff=True)
        self.staff_client = Client()
        self.staff_client.login(username="mae", password="staffpass123")

    def test_anonymous_cannot_reach_counter_or_report(self):
        for name, args in (("counter_queue", []), ("record_sale", [self.log.id]), ("daily_report", [])):
            response = self.client.get(reverse(name, args=args))
            self.assertEqual(response.status_code, 302)
            self.assertIn("/admin/login/", response["Location"])

    def test_member_session_alone_cannot_reach_counter(self):

        self.login()
        response = self.client.get(reverse("counter_queue"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_non_staff_django_user_is_rejected(self):
        User = get_user_model()
        User.objects.create_user("intern", password="pass12345", is_staff=False)
        c = Client()
        c.login(username="intern", password="pass12345")
        self.assertEqual(c.get(reverse("counter_queue")).status_code, 302)

    def test_new_login_appears_in_pending_queue(self):
        response = self.staff_client.get(reverse("counter_queue"))
        self.assertContains(response, "สมชาย")
        self.assertContains(response, "No sales have been recorded today.")

    def test_record_sale_updates_log_and_leaves_queue(self):
        response = self.staff_client.post(reverse("record_sale", args=[self.log.id]),
                                           {"amount": "45.50", "payment_method": "cash"})
        self.assertRedirects(response, reverse("counter_queue"))
        self.log.refresh_from_db()
        self.assertEqual(str(self.log.amount), "45.50")
        self.assertEqual(self.log.payment_method, "cash")
        self.assertEqual(self.log.recorded_by, "mae")
        self.assertIsNotNone(self.log.recorded_at)

        queue = self.staff_client.get(reverse("counter_queue"))
        self.assertContains(queue, "No sales waiting to be recorded.")
        self.assertFalse(LoginLog.objects.get(pk=self.log.id).needs_sale_entry)

    def test_record_sale_rejects_negative_amount(self):
        response = self.staff_client.post(reverse("record_sale", args=[self.log.id]),
                                           {"amount": "-5", "payment_method": "cash"})
        self.assertEqual(response.status_code, 200)
        self.log.refresh_from_db()
        self.assertIsNone(self.log.amount)

    def test_record_sale_requires_payment_method(self):
        response = self.staff_client.post(reverse("record_sale", args=[self.log.id]), {"amount": "10"})
        self.assertEqual(response.status_code, 200)
        self.log.refresh_from_db()
        self.assertIsNone(self.log.amount)

    def test_can_edit_an_already_recorded_sale(self):
        self.staff_client.post(reverse("record_sale", args=[self.log.id]), {"amount": "10", "payment_method": "cash"})
        self.staff_client.post(reverse("record_sale", args=[self.log.id]), {"amount": "99", "payment_method": "transfer"})
        self.log.refresh_from_db()
        self.assertEqual(str(self.log.amount), "99.00")
        self.assertEqual(self.log.payment_method, "transfer")

    def test_daily_report_totals(self):
        self.staff_client.post(reverse("record_sale", args=[self.log.id]), {"amount": "30", "payment_method": "cash"})

        other = Client()
        self.register(client=other, seed=9, first_name="สมหญิง")
        self.login(name="สมหญิง", descriptor=make_descriptor(9, noise=0.005), client=other)
        other.post(reverse("logout"))
        second_log = LoginLog.objects.filter(success=True).exclude(pk=self.log.id).get()
        self.staff_client.post(reverse("record_sale", args=[second_log.id]), {"amount": "20", "payment_method": "transfer"})

        response = self.staff_client.get(reverse("daily_report"))
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        self.assertEqual(ctx["visitor_count"], 2)
        self.assertEqual(float(ctx["total_amount"]), 50.0)
        by_label = {row["label"]: float(row["amount"]) for row in ctx["totals_by_method"]}
        self.assertEqual(by_label["Cash"], 30.0)
        self.assertEqual(by_label["Bank transfer"], 20.0)

    def test_daily_report_for_other_date_is_empty(self):
        self.staff_client.post(reverse("record_sale", args=[self.log.id]), {"amount": "30", "payment_method": "cash"})
        response = self.staff_client.get(reverse("daily_report"), {"date": "2020-01-01"})
        self.assertEqual(response.context["visitor_count"], 0)
        self.assertEqual(float(response.context["total_amount"]), 0.0)

    def test_member_dashboard_shows_own_purchase_amount(self):
        self.staff_client.post(reverse("record_sale", args=[self.log.id]), {"amount": "45.5", "payment_method": "cash"})
        self.login()
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "45.5")
        self.assertContains(response, "Cash")


@override_settings(
    SHEETS_USE_THREAD=False, GOOGLE_SHEET_ID="sheet123",
    GOOGLE_SERVICE_ACCOUNT_FILE="/tmp/fake.json", MEDIA_ROOT=TEST_MEDIA_ROOT,
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
            log = LoginLog.objects.get(success=True)
            log.amount = "27.50"
            log.payment_method = LoginLog.PaymentMethod.CASH
            log.save(update_fields=["amount", "payment_method"])
            self.sign_out()
        worksheet.append_row.assert_called_once()
        row, kwargs = worksheet.append_row.call_args
        values = row[0]
        person = Person.objects.get()
        self.assertEqual(values[1:4], [person.full_name, person.nickname, person.member_code])
        self.assertEqual(values[5:], ["27.50", "Cash"])
        self.assertRegex(values[4], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        self.assertRegex(values[0], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
        self.assertEqual(kwargs["value_input_option"], "RAW")
        self.assertNotIn("1234", " ".join(map(str, values)))
        self.assertEqual(LoginLog.objects.get(success=True).sheet_status, "sent")

    def test_row_uses_bangkok_time(self):
        person = Person.objects.get()
        log = LoginLog.objects.create(person=person, success=True, sheet_status="pending")
        import datetime
        log.created_at = datetime.datetime(2026, 1, 1, 0, 30, tzinfo=datetime.timezone.utc)
        self.assertEqual(sheets._row_for(log)[0], "2026-01-01 07:30:00")

    def test_sheet_failure_does_not_break_login_and_is_retried_later(self):
        worksheet = mock.MagicMock()
        worksheet.append_row.side_effect = ConnectionError("network down")
        with mock.patch.object(sheets, "_get_worksheet", return_value=worksheet):
            response = self.login()
            self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
            self.sign_out()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 302)
        log = LoginLog.objects.get(success=True)
        self.assertEqual(log.sheet_status, "failed")
        self.assertEqual(log.sheet_attempts, 1)
        self.assertIn("ConnectionError", log.sheet_error)


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
            self.sign_out()
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
            LoginLog.objects.create(
                person=person,
                success=True,
                logged_out_at=timezone.now(),
                sheet_status="pending",
            )
        worksheet = mock.MagicMock()
        worksheet.append_row.side_effect = [None, RuntimeError("quota"), None]
        with mock.patch.object(sheets, "_get_worksheet", return_value=worksheet):
            sent, failed = sheets.sync_pending_logs()
        self.assertEqual((sent, failed), (1, 1))
        self.assertEqual(worksheet.append_row.call_count, 2)
        self.assertEqual(LoginLog.objects.filter(sheet_status="pending").count(), 1)

    def test_stuck_sending_rows_are_recovered(self):
        import datetime
        person = Person.objects.get()
        LoginLog.objects.create(person=person, success=True, sheet_status="sending",
                                logged_out_at=timezone.now(),
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
