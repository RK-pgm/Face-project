"""
ตั้งค่าโปรเจ็ค "ระบบล็อกอินด้วยใบหน้า + ชื่อ + รหัสตัวเลข"

ค่าที่เป็นความลับหรือเปลี่ยนตามเครื่อง อ่านจาก environment variable
(ดู .env.example) เพื่อไม่ต้องเขียนลงในโค้ดที่อาจเผลอเอาขึ้น GitHub
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv():
    """
    อ่านไฟล์ .env แบบง่าย ๆ (บรรทัดละ KEY=VALUE) โดยไม่ต้องติดตั้งไลบรารีเพิ่ม
    ค่าที่ตั้งไว้ใน environment จริงของเครื่องจะมีลำดับสำคัญกว่า
    """
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _env_bool(name, default):
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# ความปลอดภัยพื้นฐาน
# ---------------------------------------------------------------------------
# ตอนพัฒนาบนเครื่องตัวเองใช้ค่า dev ได้ แต่ถ้าจะเอาขึ้นเซิร์ฟเวอร์จริงต้องตั้ง
# DJANGO_SECRET_KEY เองและปิด DEBUG (DJANGO_DEBUG=0)
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-key-เปลี่ยนก่อนใช้งานจริง-change-me")
DEBUG = _env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"] + [
    h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",  # ป้องกัน CSRF
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "accounts.context_processors.current_person",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# ฐานข้อมูล: SQLite (เป็นไฟล์ db.sqlite3 ในโฟลเดอร์โปรเจ็ค ไม่ต้องติดตั้งอะไรเพิ่ม)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        # รอสูงสุด 20 วินาทีถ้าฐานข้อมูลถูกล็อก (เพราะมี thread ส่งชีตเขียนพร้อมกัน)
        "OPTIONS": {"timeout": 20},
    }
}

AUTH_PASSWORD_VALIDATORS = []  # ผู้ใช้ทั่วไปของเราใช้ PIN ตัวเลข ตรวจรูปแบบเองใน forms.py

# ---------------------------------------------------------------------------
# ภาษา / เวลา
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "th"
TIME_ZONE = "Asia/Bangkok"
USE_I18N = True
USE_TZ = True  # เก็บเวลาใน DB เป็น UTC แล้วแปลงเป็น Asia/Bangkok ตอนแสดงผล

# ---------------------------------------------------------------------------
# ไฟล์ static และ media
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]  # face-api.js, โมเดล, Bootstrap, ฟอนต์ อยู่ที่นี่

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"  # รูปใบหน้าถูกบันทึกที่นี่ (ไม่เปิดให้เข้าตรง ๆ ดู config/urls.py)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Session (ใช้ควบคุมการล็อกอิน)
# ---------------------------------------------------------------------------
SESSION_COOKIE_AGE = 60 * 60 * 2  # อยู่ในระบบได้ 2 ชั่วโมง
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# ถ้าเอาขึ้น HTTPS จริง ให้เปิดสองบรรทัดนี้:
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True

# ภาพใบหน้าถูกส่งมาเป็น base64 ใน JSON (ประมาณ 50-300 KB) เผื่อไว้ 5 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# ---------------------------------------------------------------------------
# การเทียบใบหน้า
# ---------------------------------------------------------------------------
# ระยะ Euclidean ระหว่าง descriptor 128 ค่า: "น้อยกว่า" ค่านี้ถึงจะถือว่าเป็นคนเดียวกัน
# ยิ่งน้อย = เข้มงวดขึ้น (กันคนอื่นได้ดีขึ้น แต่เจ้าของอาจโดนปฏิเสธบ่อยขึ้น)
# ค่าเริ่มต้นของ face-api.js คือ 0.6 — เราเลือก 0.5 ให้เข้มกว่าเล็กน้อย
# (เหตุผลอยู่ใน README.md หัวข้อ "ทำไม threshold 0.5")
FACE_MATCH_THRESHOLD = float(os.environ.get("FACE_MATCH_THRESHOLD", "0.5"))

# ---------------------------------------------------------------------------
# กันเดารหัส: ผิดเกินกำหนดให้ล็อกชั่วคราว
# ---------------------------------------------------------------------------
LOGIN_MAX_FAILED_ATTEMPTS = 5   # ผิดได้กี่ครั้งก่อนถูกล็อก
LOGIN_LOCK_MINUTES = 5          # ล็อกนานกี่นาที
LOGIN_FAIL_WINDOW_MINUTES = 15  # ถ้าไม่ผิดซ้ำเกินเวลานี้ ให้เริ่มนับครั้งที่ผิดใหม่

# ---------------------------------------------------------------------------
# Google Sheet (ฟรี) — ถ้าไม่ตั้งค่า ระบบยังใช้งานได้ปกติ แค่ยังไม่ส่งขึ้นชีต
# ---------------------------------------------------------------------------
# ID ของชีต = ข้อความยาว ๆ ใน URL ระหว่าง /d/ กับ /edit
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "")
# ชื่อแท็บในชีต (เว้นว่าง = ใช้แท็บแรก)
GOOGLE_SHEET_WORKSHEET = os.environ.get("GOOGLE_SHEET_WORKSHEET", "")
# วิธีที่ 1 (แนะนำ): พาธไฟล์ key ของ Service Account ที่เก็บ "นอก" โฟลเดอร์โปรเจ็ค
GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "")
# วิธีที่ 2: ใส่เนื้อหา JSON ทั้งก้อนใน environment variable
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
# ส่งขึ้นชีตด้วย thread แยกไม่ให้หน้าเว็บค้าง (ตอนรันเทสต์จะปิด)
SHEETS_USE_THREAD = True

# ---------------------------------------------------------------------------
# Log ในหน้าจอ terminal
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "[{levelname}] {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "loggers": {
        # แสดงระยะห่างใบหน้าของแต่ละครั้งที่ล็อกอิน (เฉพาะใน terminal ไม่ส่งกลับไปที่เบราว์เซอร์)
        # เอาไว้ปรับ FACE_MATCH_THRESHOLD ให้เหมาะกับกล้องและแสงของคุณ
        "accounts": {"handlers": ["console"], "level": "INFO"},
    },
}
