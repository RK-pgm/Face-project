import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


if os.environ.get("DATABASE_URL_UNPOOLED"):
    os.environ["DATABASE_URL"] = os.environ["DATABASE_URL_UNPOOLED"]

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.management import execute_from_command_line
from django.contrib.auth import get_user_model


execute_from_command_line(["manage.py", "migrate", "--noinput"])

# Optionally provision the initial Django admin account from Vercel environment
# variables. Credentials are never stored in the repository or printed to logs.
admin_username = os.environ.get("DJANGO_ADMIN_USERNAME", "").strip()
admin_password = os.environ.get("DJANGO_ADMIN_PASSWORD", "")
if admin_username and admin_password:
    User = get_user_model()
    admin_user, _ = User.objects.get_or_create(username=admin_username)
    admin_user.is_active = True
    admin_user.is_staff = True
    admin_user.is_superuser = True
    admin_user.set_password(admin_password)
    admin_user.save()
    print(f"Administrator account provisioned for username: {admin_username}")
elif admin_username or admin_password:
    raise RuntimeError("Set both DJANGO_ADMIN_USERNAME and DJANGO_ADMIN_PASSWORD to provision an administrator.")
else:
    print("Administrator bootstrap skipped: credentials are not configured.")
