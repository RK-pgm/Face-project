from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import LoginThrottle

def throttle_key(name):
    return name.casefold()[:60]


def lock_seconds_left(key):
    row = LoginThrottle.objects.filter(key=key).first()
    if row and row.locked_until:
        left = (row.locked_until - timezone.now()).total_seconds()
        if left > 0:
            return int(left) + 1
    return 0

def record_failure(key):
    now = timezone.now()
    window = timedelta(minutes=settings.LOGIN_FAIL_WINDOW_MINUTES)
    with transaction.atomic():
        row, _ = LoginThrottle.objects.select_for_update().get_or_create(key=key)
        if now - row.updated_at > window:
            row.failed_count = 0 
        row.failed_count += 1
        row.updated_at = now
        if row.failed_count >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
            row.locked_until = now + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
            row.failed_count = 0
        row.save()


def reset(key):
    LoginThrottle.objects.filter(key=key).delete()
