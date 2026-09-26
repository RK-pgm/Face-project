import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from . import faces, security, sheets
from .decorators import SESSION_KEY, person_login_required
from .forms import PIN_PATTERN, RegisterForm
from .models import LoginLog, Person
from .textutil import clean_text

logger = logging.getLogger(__name__)

# ข้อความกลาง ๆ ตอนล็อกอินไม่ผ่าน — ตั้งใจไม่บอกว่าผิดที่ชื่อ, PIN หรือใบหน้า
# เพื่อไม่ให้คนร้ายรู้ว่าเดาถูกไปกี่ส่วนแล้ว
GENERIC_FAIL_MESSAGE = "ข้อมูลไม่ถูกต้อง"

# ค่า PIN แฮชปลอม ไว้ตรวจเมื่อ "ไม่มีชื่อนี้ในระบบ" เพื่อให้ใช้เวลาตอบใกล้เคียงกับกรณีมีชื่อจริง
# (กันการเดาว่าชื่อไหนมีอยู่ โดยจับเวลาที่ระบบตอบ) คำนวณครั้งแรกที่ใช้แล้วจำไว้
_dummy_hash = None


def _get_dummy_hash():
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = make_password("000000")
    return _dummy_hash


def _read_json(request):
    """อ่าน body ที่เป็น JSON คืนค่า dict หรือ None ถ้าอ่านไม่ได้"""
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def home(request):
    if request.session.get(SESSION_KEY):
        return redirect("dashboard")
    return redirect("login")


# ---------------------------------------------------------------------------
# สมัครสมาชิก
# ---------------------------------------------------------------------------
@require_http_methods(["GET", "POST"])
def register(request):
    if request.method == "GET":
        return render(request, "accounts/register.html")

    payload = _read_json(request)
    if payload is None:
        return JsonResponse({"ok": False, "errors": {"__all__": "ข้อมูลที่ส่งมาไม่ถูกต้อง"}}, status=400)

    # รับเฉพาะค่าที่เป็นข้อความ/จริง-เท็จ (กัน PIN ถูกส่งมาเป็นตัวเลขแล้วเลข 0 นำหน้าหาย)
    form_data = {k: v for k, v in payload.items() if isinstance(v, (str, bool))}
    form = RegisterForm(form_data)
    errors = {}
    if not form.is_valid():
        errors = {field: msgs[0] for field, msgs in form.errors.items()}

    # ตรวจข้อมูลใบหน้า: descriptor 128 ค่า + รูปถ่าย
    descriptor = photo_file = None
    try:
        descriptor = faces.parse_descriptor(payload.get("descriptor"))
        photo_file = faces.photo_from_data_url(payload.get("photo"))
    except faces.FaceDataError:
        errors["face"] = "ข้อมูลใบหน้าไม่ถูกต้อง กรุณาถ่ายรูปใหม่อีกครั้ง"

    if errors:
        return JsonResponse({"ok": False, "errors": errors}, status=400)

    cd = form.cleaned_data
    now = timezone.now()
    person = Person(
        first_name=cd["first_name"],
        last_name=cd["last_name"],
        nickname=cd["nickname"],
        pin_hash=make_password(cd["pin"]),  # เก็บเป็นแฮช ไม่เก็บ PIN ตรง ๆ
        face_descriptor=descriptor,
        consent_pdpa=True,
        consent_at=now,
        created_at=now,
    )
    person.face_photo.save("face.jpg", photo_file, save=False)  # ชื่อไฟล์จริงถูกสุ่มใน models.face_photo_path
    person.save()

    messages.success(
        request,
        f"สมัครสมาชิกสำเร็จ รหัสสมาชิกของคุณคือ {person.member_code} — ต่อไปเข้าสู่ระบบด้วยชื่อ รหัสตัวเลข และใบหน้า",
    )
    return JsonResponse({"ok": True, "redirect": "/login/"})


# ---------------------------------------------------------------------------
# ล็อกอิน (ต้องผ่านครบ 3 อย่าง: ชื่อ + PIN + ใบหน้า)
# ---------------------------------------------------------------------------
def _fail(name, person, reason, throttle_key=None):
    """บันทึกว่าล้มเหลว + นับจำนวนครั้งที่ผิด + ตอบข้อความกลาง ๆ"""
    LoginLog.objects.create(
        person=person,
        attempted_name=name[:50],
        success=False,
        fail_reason=reason,
        sheet_status=LoginLog.SheetStatus.NOT_NEEDED,
    )
    if throttle_key:
        security.record_failure(throttle_key)
    return JsonResponse({"ok": False, "message": GENERIC_FAIL_MESSAGE}, status=401)


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == "GET":
        if request.session.get(SESSION_KEY):
            return redirect("dashboard")
        return render(request, "accounts/login.html")

    payload = _read_json(request)
    if payload is None:
        return JsonResponse({"ok": False, "message": "ข้อมูลที่ส่งมาไม่ถูกต้อง"}, status=400)

    name = clean_text(payload.get("name")) or ""
    pin = payload.get("pin") if isinstance(payload.get("pin"), str) else ""
    key = security.throttle_key(name)

    # 1) ถ้าชื่อนี้ถูกล็อกอยู่ ตอบเลยโดยไม่ตรวจอะไรต่อ (ผู้ร้ายจะได้เดาเพิ่มไม่ได้)
    seconds_left = security.lock_seconds_left(key) if name else 0
    if seconds_left:
        LoginLog.objects.create(attempted_name=name[:50], success=False, fail_reason="locked")
        minutes = max(1, -(-seconds_left // 60))  # ปัดขึ้น
        return JsonResponse(
            {"ok": False, "locked": True, "message": f"ลองผิดหลายครั้งเกินไป กรุณารอประมาณ {minutes} นาทีแล้วลองใหม่"},
            status=429,
        )

    # 2) ตรวจรูปแบบข้อมูลที่ส่งมา
    try:
        descriptor = faces.parse_descriptor(payload.get("descriptor"))
    except faces.FaceDataError:
        descriptor = None
    if not name or not PIN_PATTERN.match(pin) or descriptor is None:
        return _fail(name, None, "format", key if name else None)

    # 3) หาสมาชิกที่ชื่อตรงกัน (อาจมีชื่อซ้ำกันได้ จึงเป็น list)
    candidates = list(Person.objects.filter(first_name__iexact=name))
    if not candidates:
        check_password(pin, _get_dummy_hash())  # ใช้เวลาใกล้เคียงกับกรณีมีชื่อจริง
        return _fail(name, None, "no_user", key)

    # 4) ตรวจ PIN ของทุกคนที่ชื่อตรง แล้วเทียบใบหน้า "แบบ 1:1" กับคนที่ PIN ถูกเท่านั้น
    #    (ไม่ค้นหาใบหน้านี้ทั้งฐานข้อมูล จึงไม่ใช่การ "หาว่าคุณคือใคร" แต่เป็นการ "ยืนยันว่าคุณคือคนนี้จริงไหม")
    matched, best_distance = None, None
    pin_ok_people = [p for p in candidates if check_password(pin, p.pin_hash)]
    for person in pin_ok_people:
        distance = faces.face_distance(descriptor, person.face_descriptor)
        logger.info("face distance member=%s distance=%.3f threshold=%.2f",
                    person.member_code, distance, settings.FACE_MATCH_THRESHOLD)
        if faces.is_same_person(distance) and (best_distance is None or distance < best_distance):
            matched, best_distance = person, distance

    if matched is None:
        only_one = candidates[0] if len(candidates) == 1 else None
        return _fail(name, only_one, "face" if pin_ok_people else "pin", key)

    # 5) ผ่านครบทุกอย่าง → สร้าง session ใหม่ (cycle_key กัน session fixation)
    request.session.cycle_key()
    request.session[SESSION_KEY] = matched.pk
    security.reset(key)

    # บันทึกลง DB ก่อน แล้วค่อยส่งชีตหลังบันทึกเสร็จ (ถ้าชีตพัง การล็อกอินก็ยังสำเร็จ)
    LoginLog.objects.create(
        person=matched,
        attempted_name=name[:50],
        success=True,
        sheet_status=LoginLog.SheetStatus.PENDING,
    )
    transaction.on_commit(sheets.enqueue_sync)

    return JsonResponse({"ok": True, "redirect": "/dashboard/"})


# ---------------------------------------------------------------------------
# Dashboard / ออกจากระบบ / รูปของตัวเอง
# ---------------------------------------------------------------------------
@person_login_required
def dashboard(request):
    person = request.person
    recent_success = list(person.logs.filter(success=True)[:2])  # [ครั้งนี้, ครั้งก่อนหน้า]
    context = {
        "last_login": recent_success[0].created_at if recent_success else None,
        "previous_login": recent_success[1].created_at if len(recent_success) > 1 else None,
        "logs": person.logs.all()[:30],
    }
    return render(request, "accounts/dashboard.html", context)


@require_POST
def logout_view(request):
    request.session.flush()  # ล้าง session ทั้งหมด
    messages.success(request, "ออกจากระบบเรียบร้อยแล้ว")
    return redirect("login")


@person_login_required
def my_photo(request):
    """ส่งรูปหน้าของผู้ที่ล็อกอินอยู่เท่านั้น (ไม่มีทางเปิดดูรูปของคนอื่น)"""
    photo = request.person.face_photo
    if not photo:
        raise Http404
    response = FileResponse(photo.open("rb"), content_type="image/jpeg")
    response["Cache-Control"] = "private, no-store"
    return response
