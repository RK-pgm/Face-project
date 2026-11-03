import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


if os.environ.get("DATABASE_URL_UNPOOLED"):
    os.environ["DATABASE_URL"] = os.environ["DATABASE_URL_UNPOOLED"]

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.management import execute_from_command_line


execute_from_command_line(["manage.py", "migrate", "--noinput"])
