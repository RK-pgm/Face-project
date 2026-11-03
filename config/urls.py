from django.urls import include, path
from accounts.admin import face_admin_site

urlpatterns = [
    path("admin/", face_admin_site.urls),
    path("", include("accounts.urls")),
]

