from django.contrib import admin
from .models import LoginLog, LoginThrottle, Person
@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):

    list_display = ("member_code", "first_name", "last_name", "nickname", "created_at", "consent_pdpa")
    search_fields = ("member_code", "first_name", "last_name", "nickname")
    exclude = ("pin_hash", "face_descriptor")
    readonly_fields = ("member_code", "created_at", "consent_at")

@admin.register(LoginLog)
class LoginLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "person", "attempted_name", "success", "fail_reason", "sheet_status", "sheet_attempts")
    list_filter = ("success", "sheet_status")
    readonly_fields = ("created_at",)

@admin.register(LoginThrottle)
class LoginThrottleAdmin(admin.ModelAdmin):
    list_display = ("key", "failed_count", "locked_until", "updated_at")
