from django.core.management.base import BaseCommand

from accounts import sheets
from accounts.models import LoginLog


class Command(BaseCommand):
    help = "Upload pending sign-in logs to Google Sheets."

    def handle(self, *args, **options):
        if not sheets.is_configured():
            self.stderr.write("Google Sheets is not configured. See .env.example and README.md.")
            return
        sent, failed = sheets.sync_pending_logs()
        left = LoginLog.objects.filter(
            success=True,
            logged_out_at__isnull=False,
            sheet_status__in=["pending", "failed", "sending"],
        ).count()
        self.stdout.write(f"Uploaded {sent} rows; {failed} failed; {left} remain pending.")
