import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "ไม่พบ Django — ลืมเปิด venv หรือยังไม่ได้ pip install -r requirements.txt หรือเปล่า?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
