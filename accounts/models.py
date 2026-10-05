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
    raise RuntimeError("Could not generate a unique member ID.")


def face_photo_path(instance, filename):

    return f"faces/{uuid.uuid4().hex}.jpg"


class Person(models.Model):

    first_name = models.CharField("First name", max_length=50)
    last_name = models.CharField("Last name", max_length=50)
    nickname = models.CharField("Nickname", max_length=30)
    member_code = models.CharField("Member ID", max_length=12, unique=True, default=generate_member_code)
    pin_hash = models.CharField("PIN hash", max_length=128)
    face_photo = models.ImageField("Face photo", upload_to=face_photo_path)
    face_descriptor = models.JSONField("Face descriptor (128 values)")
    consent_pdpa = models.BooleanField("Consent to face data storage", default=False)
    consent_at = models.DateTimeField("Consent time", null=True, blank=True)

    created_at = models.DateTimeField("Registration date", default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Member"
        verbose_name_plural = "Member"

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.member_code})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class LoginLog(models.Model):

    class SheetStatus(models.TextChoices):
        NOT_NEEDED = "not_needed", "Not required"
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed (will retry)"

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        TRANSFER = "transfer", "Bank transfer"

    person = models.ForeignKey(Person, null=True, blank=True, on_delete=models.CASCADE, related_name="logs")
    attempted_name = models.CharField("Entered name", max_length=50, blank=True)
    created_at = models.DateTimeField("Time", default=timezone.now, db_index=True)
    logged_out_at = models.DateTimeField("Sign-out time", null=True, blank=True)
    success = models.BooleanField("Successful")

    fail_reason = models.CharField("Internal reason", max_length=20, blank=True)

    sheet_status = models.CharField(
        "Sheet status", max_length=12, choices=SheetStatus.choices, default=SheetStatus.NOT_NEEDED
    )
    sheet_attempts = models.PositiveSmallIntegerField("Attempt count", default=0)
    sheet_last_try = models.DateTimeField("Last attempt", null=True, blank=True)
    sheet_error = models.CharField("Latest sheet error", max_length=200, blank=True)

    amount = models.DecimalField("Amount (baht)", max_digits=9, decimal_places=2, null=True, blank=True)
    payment_method = models.CharField("Payment method", max_length=10, choices=PaymentMethod.choices, blank=True)
    recorded_by = models.CharField("Recorded by", max_length=150, blank=True)
    recorded_at = models.DateTimeField("Recorded at", null=True, blank=True)
    sheet_row = models.PositiveIntegerField("Google Sheets row", null=True, blank=True)

    @property
    def needs_sale_entry(self):
        return self.success and self.amount is None

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Sign-in history"
        verbose_name_plural = "Sign-in history"

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {'Successful' if self.success else 'Failed'}"


class LoginThrottle(models.Model):

    key = models.CharField(max_length=60, unique=True)
    failed_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.key
