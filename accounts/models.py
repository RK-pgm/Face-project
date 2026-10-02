import secrets
import uuid
from django.db import models
from django.utils import timezone
_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def generate_member_code():
    for _ in range(20):
        code = "MB-" + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
        if not Person.objects.filter(member_code=code).exists():
            return code
    raise RuntimeError("Failed to generate a unique member ID.")


def face_photo_path(instance, filename):
    return f"faces/{uuid.uuid4().hex}.jpg"


class Person(models.Model):

    first_name = models.CharField("Name", max_length=50)
    last_name = models.CharField("Lastname", max_length=50)
    nickname = models.CharField("Nickename", max_length=30)
    member_code = models.CharField("Password member", max_length=12, unique=True, default=generate_member_code)
    pin_hash = models.CharField("PIN (แฮช)", max_length=128)
    face_photo = models.ImageField("Face", upload_to=face_photo_path)
    face_descriptor = models.JSONField("face descriptor (128 ค่า)")
    consent_pdpa = models.BooleanField("Consent to the collection of facial images", default=False)
    consent_at = models.DateTimeField("Time of giving consent", null=True, blank=True)
    created_at = models.DateTimeField("Application Date", default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "member"
        verbose_name_plural = "member"

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.member_code})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class LoginLog(models.Model):
    class SheetStatus(models.TextChoices):
        NOT_NEEDED = "not_needed", "ไม่ต้องส่ง"    
        PENDING = "pending", "รอส่ง"
        SENDING = "sending", "กำลังส่ง"
        SENT = "sent", "Sent finish"
        FAILED = "failed", "Sent error (would try again)"
    person = models.ForeignKey(Person, null=True, blank=True, on_delete=models.CASCADE, related_name="logs")
    attempted_name = models.CharField("Printed Name", max_length=50, blank=True)
    created_at = models.DateTimeField("Time", default=timezone.now, db_index=True)
    success = models.BooleanField("Complete")
    fail_reason = models.CharField("(Internal) Reason", max_length=20, blank=True)
    sheet_status = models.CharField(
        "สถานะส่งชีต", max_length=12, choices=SheetStatus.choices, default=SheetStatus.NOT_NEEDED)
    sheet_attempts = models.PositiveSmallIntegerField("Number of transmission attempts", default=0)
    sheet_last_try = models.DateTimeField("Trying the latest submission.", null=True, blank=True)
    sheet_error = models.CharField("Latest sheet errors", max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "History log in."
        verbose_name_plural = "History log in."

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {'Complete' if self.success else 'Incomplete'}"


class LoginThrottle(models.Model):
    key = models.CharField(max_length=60, unique=True)
    failed_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(default=timezone.now)
    def __str__(self):
        return self.key
