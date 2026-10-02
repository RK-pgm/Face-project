import json
import logging
import threading
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.utils import timezone

from .models import LoginLog

logger = logging.getLogger(__name__)

HEADER_ROW = ["Day-time", "Name-lastname", "Nickname", "password"]
STUCK_AFTER = timedelta(minutes=5) 

_worker_lock = threading.Lock() 
_worksheet = None            

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
        worksheet = spreadsheet.worksheet(settings.GOOGLE_SHEET_WORKSHEET)
    else:
        worksheet = spreadsheet.sheet1
    if not worksheet.acell("A1").value:
        worksheet.append_row(HEADER_ROW, value_input_option="RAW")

    _worksheet = worksheet
    return _worksheet


def _forget_connection():
    global _worksheet
    _worksheet = None


def _row_for(log):
    person = log.person
    when = timezone.localtime(log.created_at).strftime("%Y-%m-%d %H:%M:%S")   
    return [when, person.full_name, person.nickname, person.member_code]


def sync_pending_logs(limit=200):
    if not is_configured():
        return 0, 0

    sent = failed = 0
    with _worker_lock:
        now = timezone.now()
        waiting = (
            LoginLog.objects.filter(success=True)
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
                _get_worksheet().append_row(_row_for(log), value_input_option="RAW")
            except Exception as exc:  
                _forget_connection()
                LoginLog.objects.filter(pk=log.pk).update(
                    sheet_status=LoginLog.SheetStatus.FAILED,
                    sheet_attempts=log.sheet_attempts + 1,
                    sheet_error=f"{type(exc).__name__}: {exc}"[:200],
                )
                logger.warning("ส่งขึ้น Google Sheet ไม่สำเร็จ (จะลองใหม่ภายหลัง): %s", type(exc).__name__)
                failed += 1
                break
            LoginLog.objects.filter(pk=log.pk).update(
                sheet_status=LoginLog.SheetStatus.SENT,
                sheet_attempts=log.sheet_attempts + 1,
                sheet_error="",
            )
            sent += 1
    return sent, failed


def _thread_main():
    try:
        sync_pending_logs()
    except Exception: 
        logger.exception("thread ส่งชีตพัง")
    finally:
        connection.close() 


def enqueue_sync():
    if not is_configured():
        return
    if settings.SHEETS_USE_THREAD:
        threading.Thread(target=_thread_main, name="sheet-sync", daemon=True).start()
    else:
        sync_pending_logs()
