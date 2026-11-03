from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django.utils import timezone

from .models import LoginLog, LoginThrottle, Person


class FaceAdminSite(admin.AdminSite):
    site_header = "Face Sign-in · Member Studio"
    site_title = "Member Studio"
    index_title = "Member operations"
    index_template = "admin/face_index.html"

    def index(self, request, extra_context=None):
        today = timezone.localdate()
        successful_today = LoginLog.objects.filter(success=True, created_at__date=today)
        context = {
            "member_total": Person.objects.count(),
            "checkins_today": successful_today.count(),
            "sales_waiting": successful_today.filter(amount__isnull=True).count(),
            "sheets_attention": LoginLog.objects.filter(
                success=True,
                sheet_status__in=[
                    LoginLog.SheetStatus.PENDING,
                    LoginLog.SheetStatus.SENDING,
                    LoginLog.SheetStatus.FAILED,
                ],
            ).count(),
            "recent_activity": LoginLog.objects.filter(success=True)
            .select_related("person")[:5],
            "pending_sales": successful_today.filter(amount__isnull=True)
            .select_related("person")[:5],
            "today": today,
        }
        context.update(extra_context or {})
        return super().index(request, extra_context=context)


face_admin_site = FaceAdminSite(name="admin")
face_admin_site.register(get_user_model(), UserAdmin)
face_admin_site.register(Group)


@admin.register(Person, site=face_admin_site)
class PersonAdmin(admin.ModelAdmin):

    list_display = (
        "member_code", "first_name", "last_name", "nickname", "created_at",
        "consent_pdpa", "sheet_synced_at",
    )
    search_fields = ("member_code", "first_name", "last_name", "nickname")

    exclude = ("pin_hash", "face_descriptor")
    readonly_fields = ("member_code", "created_at", "consent_at", "sheet_synced_at", "sheet_error")

    def has_add_permission(self, request):
        # Member creation must go through the face/PIN consent registration flow.
        return False


@admin.register(LoginLog, site=face_admin_site)
class LoginLogAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "person", "attempted_name", "success", "fail_reason",
        "amount", "payment_method", "sheet_status", "sheet_attempts",
    )
    list_filter = ("success", "sheet_status", "payment_method")
    readonly_fields = ("created_at",)


@admin.register(LoginThrottle, site=face_admin_site)
class LoginThrottleAdmin(admin.ModelAdmin):

    list_display = ("key", "failed_count", "locked_until", "updated_at")
