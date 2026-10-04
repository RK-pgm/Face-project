import json
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.db.models import Sum
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST
from . import faces, security, sheets
from .decorators import SESSION_KEY, person_login_required
from .forms import PIN_PATTERN, ChangeFaceForm, RegisterForm, SaleForm
from .models import LoginLog, Person
from .textutil import clean_text

logger = logging.getLogger(__name__)
GENERIC_FAIL_MESSAGE = "Sign-in failed."
ACTIVE_LOGIN_LOG_KEY = "active_login_log_id"
_dummy_hash = None
def _get_dummy_hash():
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = make_password("000000")
    return _dummy_hash


def _read_json(request):
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def home(request):
    if request.session.get(SESSION_KEY):
        return redirect("dashboard")
    return redirect("login")

@require_http_methods(["GET", "POST"])
def register(request):
    if request.method == "GET":
        return render(request, "accounts/register.html")

    payload = _read_json(request)
    if payload is None:
        return JsonResponse({"ok": False, "errors": {"__all__": "The submitted data is invalid."}}, status=400)


    form_data = {k: v for k, v in payload.items() if isinstance(v, (str, bool))}
    form = RegisterForm(form_data)
    errors = {}
    if not form.is_valid():
        errors = {field: msgs[0] for field, msgs in form.errors.items()}


    descriptor = photo_file = None
    try:
        descriptor = faces.parse_descriptor(payload.get("descriptor"))
        photo_file = faces.photo_from_data_url(payload.get("photo"))
    except faces.FaceDataError:
        errors["face"] = "Face data is invalid. Please take the photo again."

    if errors:
        return JsonResponse({"ok": False, "errors": errors}, status=400)

    cd = form.cleaned_data
    now = timezone.now()
    person = Person(
        first_name=cd["first_name"],
        last_name=cd["last_name"],
        nickname=cd["nickname"],
        pin_hash=make_password(cd["pin"]),
        face_descriptor=descriptor,
        consent_pdpa=True,
        consent_at=now,
        created_at=now,
    )
    person.face_photo.save("face.jpg", photo_file, save=False)
    person.save()

    messages.success(
        request,
        f"Registration complete. Your member ID is {person.member_code}. Sign in with your name, PIN, and face.",
    )
    return JsonResponse({"ok": True, "redirect": "/"})

def _fail(name, person, reason, throttle_key=None):
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
        return JsonResponse({"ok": False, "message": "The submitted data is invalid."}, status=400)

    name = clean_text(payload.get("name")) or ""
    pin = payload.get("pin") if isinstance(payload.get("pin"), str) else ""
    key = security.throttle_key(name)


    seconds_left = security.lock_seconds_left(key) if name else 0
    if seconds_left:
        LoginLog.objects.create(attempted_name=name[:50], success=False, fail_reason="locked")
        minutes = max(1, -(-seconds_left // 60))
        return JsonResponse(
            {"ok": False, "locked": True, "message": f"Too many failed attempts. Please wait about {minutes} minute(s) and try again."},
            status=429,
        )

    try:
        descriptor = faces.parse_descriptor(payload.get("descriptor"))
    except faces.FaceDataError:
        descriptor = None
    if not name or not PIN_PATTERN.match(pin) or descriptor is None:
        return _fail(name, None, "format", key if name else None)


    candidates = list(Person.objects.filter(first_name__iexact=name))
    if not candidates:
        check_password(pin, _get_dummy_hash())
        return _fail(name, None, "no_user", key)

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


    request.session.cycle_key()
    request.session[SESSION_KEY] = matched.pk
    security.reset(key)


    login_log = LoginLog.objects.create(
        person=matched,
        attempted_name=name[:50],
        success=True,
        sheet_status=LoginLog.SheetStatus.PENDING,
    )
    request.session[ACTIVE_LOGIN_LOG_KEY] = login_log.pk

    return JsonResponse({"ok": True, "redirect": "/dashboard/"})

@person_login_required
@require_http_methods(["GET", "POST"])
def dashboard(request):
    person = request.person
    active_log_id = request.session.get(ACTIVE_LOGIN_LOG_KEY)
    active_log = LoginLog.objects.filter(
        pk=active_log_id,
        person=person,
        success=True,
    ).first() if active_log_id else None

    if request.method == "POST":
        if active_log is None:
            messages.error(request, "Your active sign-in record could not be found. Please sign in again.")
            return redirect("login")
        form = SaleForm(request.POST)
        if form.is_valid():
            active_log.amount = form.cleaned_data["amount"]
            active_log.payment_method = form.cleaned_data["payment_method"]
            active_log.recorded_by = person.full_name
            active_log.recorded_at = timezone.now()
            fields = ["amount", "payment_method", "recorded_by", "recorded_at"]
            if active_log.logged_out_at:
                active_log.sheet_status = LoginLog.SheetStatus.PENDING
                fields.append("sheet_status")
            active_log.save(update_fields=fields)
            if active_log.logged_out_at:
                transaction.on_commit(sheets.enqueue_sync)
            messages.success(request, "Payment details saved.")
            return redirect("dashboard")
    else:
        initial = {}
        if active_log and active_log.amount is not None:
            initial = {"amount": active_log.amount, "payment_method": active_log.payment_method}
        form = SaleForm(initial=initial)

    recent_success = list(person.logs.filter(success=True)[:2])
    context = {
        "last_login": recent_success[0].created_at if recent_success else None,
        "previous_login": recent_success[1].created_at if len(recent_success) > 1 else None,
        "logs": person.logs.all()[:30],
        "sale_form": form,
        "active_log": active_log,
    }
    return render(request, "accounts/dashboard.html", context)


@require_POST
def logout_view(request):
    active_log_id = request.session.get(ACTIVE_LOGIN_LOG_KEY)
    if active_log_id:
        updated = LoginLog.objects.filter(
            pk=active_log_id,
            success=True,
            logged_out_at__isnull=True,
        ).update(
            logged_out_at=timezone.now(),
            sheet_status=LoginLog.SheetStatus.PENDING,
        )
        if updated:
            transaction.on_commit(sheets.enqueue_sync)
    request.session.flush()
    messages.success(request, "You have been signed out.")
    return redirect("login")


@person_login_required
def my_photo(request):
    photo = request.person.face_photo
    if not photo:
        raise Http404
    response = FileResponse(photo.open("rb"), content_type="image/jpeg")
    response["Cache-Control"] = "private, no-store"
    return response

@person_login_required
@require_http_methods(["GET", "POST"])
def change_face(request):
    if request.method == "GET":
        return render(request, "accounts/change_face.html")

    person = request.person


    key = "changeface:" + person.member_code
    seconds_left = security.lock_seconds_left(key)
    if seconds_left:
        minutes = max(1, -(-seconds_left // 60))
        return JsonResponse(
            {"ok": False, "locked": True, "message": f"Too many failed attempts. Please wait about {minutes} minute(s) and try again."},
            status=429,
        )

    payload = _read_json(request)
    if payload is None:
        return JsonResponse({"ok": False, "errors": {"__all__": "The submitted data is invalid."}}, status=400)

    form = ChangeFaceForm({k: v for k, v in payload.items() if isinstance(v, str)})
    errors = {}
    if not form.is_valid():
        errors = {field: msgs[0] for field, msgs in form.errors.items()}
    elif not check_password(form.cleaned_data["pin"], person.pin_hash):
        security.record_failure(key)
        errors["pin"] = "The current PIN is incorrect."

    descriptor = photo_file = None
    try:
        descriptor = faces.parse_descriptor(payload.get("descriptor"))
        photo_file = faces.photo_from_data_url(payload.get("photo"))
    except faces.FaceDataError:
        errors["face"] = "Face data is invalid. Please take the photo again."

    if errors:
        return JsonResponse({"ok": False, "errors": errors}, status=400)

    security.reset(key)
    old_name = person.face_photo.name
    storage = person.face_photo.storage
    person.face_descriptor = descriptor
    person.face_photo.save("face.jpg", photo_file, save=False)
    person.save()
    if old_name:
        storage.delete(old_name)

    messages.success(request, "Your sign-in face has been updated.")
    return JsonResponse({"ok": True, "redirect": "/dashboard/"})

@staff_member_required
def counter_queue(request):
    today = timezone.localdate()
    logs_today = LoginLog.objects.filter(success=True, created_at__date=today)
    context = {
        "today": today,
        "pending": logs_today.filter(amount__isnull=True).order_by("created_at"),
        "recorded": logs_today.filter(amount__isnull=False).order_by("-recorded_at"),
    }
    return render(request, "accounts/counter_queue.html", context)


@staff_member_required
@require_http_methods(["GET", "POST"])
def record_sale(request, log_id):
    log = get_object_or_404(LoginLog, pk=log_id, success=True)

    if request.method == "POST":
        form = SaleForm(request.POST)
        if form.is_valid():
            log.amount = form.cleaned_data["amount"]
            log.payment_method = form.cleaned_data["payment_method"]
            log.recorded_by = request.user.get_username()
            log.recorded_at = timezone.now()
            fields = ["amount", "payment_method", "recorded_by", "recorded_at"]
            if log.logged_out_at:
                log.sheet_status = LoginLog.SheetStatus.PENDING
                fields.append("sheet_status")
            log.save(update_fields=fields)
            if log.logged_out_at:
                transaction.on_commit(sheets.enqueue_sync)
            messages.success(request, f"Saved {log.amount:.2f} baht for {log.attempted_name}.")
            return redirect("counter_queue")
    else:
        initial = {}
        if log.amount is not None:
            initial = {"amount": log.amount, "payment_method": log.payment_method}
        form = SaleForm(initial=initial)

    return render(request, "accounts/record_sale.html", {"form": form, "log": log})


@staff_member_required
def daily_report(request):
    date_str = request.GET.get("date", "")
    today = timezone.localdate()
    try:
        selected_date = timezone.datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else today
    except ValueError:
        selected_date = today

    logs_that_day = LoginLog.objects.filter(success=True, created_at__date=selected_date)
    sales = logs_that_day.filter(amount__isnull=False).order_by("created_at")
    totals_by_method = {
        code: sales.filter(payment_method=code).aggregate(total=Sum("amount"))["total"] or 0
        for code, _ in LoginLog.PaymentMethod.choices
    }

    context = {
        "selected_date": selected_date,
        "is_today": selected_date == today,
        "visitor_count": logs_that_day.values("person").distinct().count(),
        "pending_count": logs_that_day.filter(amount__isnull=True).count(),
        "sales": sales,
        "total_amount": sum(totals_by_method.values()),
        "totals_by_method": [
            {"label": label, "amount": totals_by_method[code]} for code, label in LoginLog.PaymentMethod.choices
        ],
    }
    return render(request, "accounts/daily_report.html", context)
