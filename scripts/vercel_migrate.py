import os


if os.environ.get("DATABASE_URL_UNPOOLED"):
    os.environ["DATABASE_URL"] = os.environ["DATABASE_URL_UNPOOLED"]

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.management import execute_from_command_line


execute_from_command_line(["manage.py", "migrate", "--noinput"])
