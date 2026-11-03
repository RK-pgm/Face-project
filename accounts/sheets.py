import json
import logging
import re
import threading
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.utils import timezone

from .models import LoginLog

logger = logging.getLogger(__name__)


HEADER_ROW = ["Sign-in time", "Name", "Nickname", "Member ID", "Sign-out time", "Amount (baht)", "Payment method"]
MEMBER_HEADER_ROW = ["Registration time", "Member ID", "Full name", "Nickname", "Face data consent"]
STUCK_AFTER = timedelta(minutes=5)

_worker_lock = threading.Lock()
_worksheet = None
_members_worksheet = None


def is_configured():
    has_key = bool(settings.GOOGLE_SERVICE_ACCOUNT_FILE or settings.GOOGLE_SERVICE_ACCOUNT_JSON)
    return bool(settings.GOOGLE_SHEET_ID and has_key)


def _get_worksheet():
    global _worksheet
    if _worksheet is not None:
        return _worksheet

    import gspread

    if settings.GOOGLE_SERVICE_ACCOUNT_JSON:
        client = gspread.service_account_from_dict(json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON))
    else:
        client = gspread.service_account(filename=settings.GOOGLE_SERVICE_ACCOUNT_FILE)
    try:
        client.set_timeout(15)
    except AttributeError:
        pass

    spreadsheet = client.open_by_key(settings.GOOGLE_SHEET_ID)
    if settings.GOOGLE_SHEET_WORKSHEET:
        if settings.GOOGLE_SHEET_WORKSHEET == "Members":
            raise ValueError("GOOGLE_SHEET_WORKSHEET must be the activity tab, not Members.")
        worksheet = spreadsheet.worksheet(settings.GOOGLE_SHEET_WORKSHEET)
    else:
        worksheet = spreadsheet.sheet1

    current_header = worksheet.get("A1:G1")
    if not current_header or current_header[0] != HEADER_ROW:
        worksheet.update(range_name="A1:G1", values=[HEADER_ROW], value_input_option="RAW")

    _worksheet = worksheet
    return _worksheet


def _get_members_worksheet():
    global _members_worksheet
    if _members_worksheet is not None:
        return _members_worksheet

    import gspread
    from gspread.exceptions import WorksheetNotFound

    client = (
        gspread.service_account_from_dict(json.loads(settings.GOOGLE_SERVICE_ACCOUNT_JSON))
        if settings.GOOGLE_SERVICE_ACCOUNT_JSON
        else gspread.service_account(filename=settings.GOOGLE_SERVICE_ACCOUNT_FILE)
    )
    try:
        client.set_timeout(15)
    except AttributeError:
        pass
    spreadsheet = client.open_by_key(settings.GOOGLE_SHEET_ID)
    try:
        worksheet = spreadsheet.worksheet("Members")
    except WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title="Members", rows=1000, cols=len(MEMBER_HEADER_ROW))

    current_header = worksheet.get("A1:E1")
    if not current_header or current_header[0] != MEMBER_HEADER_ROW:
        worksheet.update(range_name="A1:E1", values=[MEMBER_HEADER_ROW], value_input_option="RAW")
    _members_worksheet = worksheet
    return worksheet


def _forget_connection():
    global _worksheet, _members_worksheet
    _worksheet = None
    _members_worksheet = None


def sync_member(member_id):
    if not is_configured():
        return False

    from .models import Person

    try:
        person = Person.objects.get(pk=member_id)
        worksheet = _get_members_worksheet()
        row = [
            timezone.localtime(person.created_at).strftime("%Y-%m-%d %H:%M:%S"),
            person.member_code,
            person.full_name,
            person.nickname,
            "Yes" if person.consent_pdpa else "No",
        ]
        found = worksheet.find(person.member_code, in_column=2)
        if found:
            worksheet.update(
                range_name=f"A{found.row}:E{found.row}", values=[row], value_input_option="RAW"
            )
        else:
            worksheet.append_row(row, value_input_option="RAW")
        Person.objects.filter(pk=person.pk).update(
            sheet_synced_at=timezone.now(), sheet_error=""
        )
        return True
    except Exception as exc:
        _forget_connection()
        logger.warning("Google Sheets member upload failed: %s", type(exc).__name__)
        Person.objects.filter(pk=member_id).update(
            sheet_error=f"{type(exc).__name__}: {exc}"[:200]
        )
        return False


def enqueue_member_sync(member_id):
    if not is_configured():
        return
    if settings.SHEETS_USE_THREAD:
        threading.Thread(
            target=sync_member, args=(member_id,), name="sheet-member-sync", daemon=True
        ).start()
    else:
        sync_member(member_id)


def sync_pending_members(limit=200):
    if not is_configured():
        return 0, 0

    from .models import Person

    sent = failed = 0
    for member_id in Person.objects.filter(sheet_synced_at__isnull=True).order_by("created_at").values_list(
        "pk", flat=True
    )[:limit]:
        if sync_member(member_id):
            sent += 1
        else:
            failed += 1
            break
    return sent, failed


def _row_for(log):
    person = log.person
    signed_in = timezone.localtime(log.created_at).strftime("%Y-%m-%d %H:%M:%S")
    signed_out = timezone.localtime(log.logged_out_at).strftime("%Y-%m-%d %H:%M:%S") if log.logged_out_at else ""
    return [signed_in, person.full_name, person.nickname, person.member_code, signed_out,
            str(log.amount) if log.amount is not None else "",
            log.get_payment_method_display() if log.payment_method else ""]


def sync_pending_logs(limit=200):
    if not is_configured():
        return 0, 0

    sent = failed = 0
    with _worker_lock:
        now = timezone.now()
        waiting = (
            LoginLog.objects.filter(success=True, logged_out_at__isnull=False)
            .filter(
                Q(sheet_status__in=[LoginLog.SheetStatus.PENDING, LoginLog.SheetStatus.FAILED])
                | Q(sheet_status=LoginLog.SheetStatus.SENDING, sheet_last_try__lt=now - STUCK_AFTER)
            )
            .select_related("person")
            .order_by("created_at")[:limit]
        )
        for log in list(waiting):

            claimed = LoginLog.objects.filter(
                pk=log.pk, sheet_status=log.sheet_status, sheet_last_try=log.sheet_last_try
            ).update(sheet_status=LoginLog.SheetStatus.SENDING, sheet_last_try=timezone.now())
            if not claimed:
                continue
            try:
                worksheet = _get_worksheet()
                if log.sheet_row:
                    worksheet.update(
                        range_name=f"A{log.sheet_row}:G{log.sheet_row}",
                        values=[_row_for(log)],
                        value_input_option="RAW",
                    )
                else:
                    result = worksheet.append_row(_row_for(log), value_input_option="RAW")
                    updated_range = result.get("updates", {}).get("updatedRange", "") if isinstance(result, dict) else ""
                    match = re.search(r"![A-Z]+(\d+):", updated_range)
                    log.sheet_row = int(match.group(1)) if match else len(worksheet.get_all_values())

            except Exception as exc:
                _forget_connection()
                LoginLog.objects.filter(pk=log.pk).update(
                    sheet_status=LoginLog.SheetStatus.FAILED,
                    sheet_attempts=log.sheet_attempts + 1,
                    sheet_error=f"{type(exc).__name__}: {exc}"[:200],
                )
                logger.warning("Google Sheets upload failed; it will be retried: %s", type(exc).__name__)
                failed += 1
                break
            LoginLog.objects.filter(pk=log.pk).update(
                sheet_status=LoginLog.SheetStatus.SENT,
                sheet_attempts=log.sheet_attempts + 1,
                sheet_error="",
                sheet_row=log.sheet_row,
            )
            sent += 1
    return sent, failed


def _thread_main():
    try:
        sync_pending_logs()
    except Exception:
        logger.exception("Google Sheets worker failed")
    finally:
        connection.close()


def enqueue_sync():
    if not is_configured():
        return
    if settings.SHEETS_USE_THREAD:
        threading.Thread(target=_thread_main, name="sheet-sync", daemon=True).start()
    else:
        sync_pending_logs()
