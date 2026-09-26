from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
]

# หมายเหตุด้านความเป็นส่วนตัว:
# เราตั้งใจ "ไม่" เปิดโฟลเดอร์ media/ ให้เข้าถึงผ่าน URL ตรง ๆ
# รูปใบหน้าเป็นข้อมูลส่วนบุคคล จึงส่งผ่าน view ชื่อ my_photo (accounts/views.py)
# ซึ่งให้ดูได้เฉพาะรูปของ "ตัวเองที่ล็อกอินอยู่" เท่านั้น
