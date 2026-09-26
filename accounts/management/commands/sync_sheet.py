from django.core.management.base import BaseCommand

from accounts import sheets
from accounts.models import LoginLog


class Command(BaseCommand):
    help = "ส่งประวัติการล็อกอินที่ยังค้างอยู่ (รอส่ง/ส่งไม่สำเร็จ) ขึ้น Google Sheet"

    def handle(self, *args, **options):
        if not sheets.is_configured():
            self.stderr.write("ยังไม่ได้ตั้งค่า Google Sheet (ดู .env.example และ README.md)")
            return
        sent, failed = sheets.sync_pending_logs()
        left = LoginLog.objects.filter(
            success=True, sheet_status__in=["pending", "failed", "sending"]
        ).count()
        self.stdout.write(f"ส่งสำเร็จ {sent} แถว, ล้มเหลว {failed}, ยังค้างอยู่ {left}")
