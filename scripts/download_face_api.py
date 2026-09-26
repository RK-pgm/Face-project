"""
ดาวน์โหลด face-api.js และไฟล์โมเดลลงโฟลเดอร์ static/vendor/face-api/
(ในไฟล์ zip ของโปรเจ็คนี้มีให้อยู่แล้ว — ใช้สคริปต์นี้เฉพาะเมื่อไฟล์หายหรืออยากดาวน์โหลดใหม่)

รัน:   py scripts/download_face_api.py
ใช้ได้ฟรี ไม่ต้องติดตั้งอะไรเพิ่ม (ใช้ urllib ที่มากับ Python)
"""
import sys
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/vladmandic/face-api/master"
TARGET = Path(__file__).resolve().parent.parent / "static" / "vendor" / "face-api"

FILES = {
    "dist/face-api.js": TARGET / "face-api.js",
}
for model in ("tiny_face_detector_model", "face_landmark_68_model", "face_recognition_model"):
    FILES[f"model/{model}-weights_manifest.json"] = TARGET / "models" / f"{model}-weights_manifest.json"
    FILES[f"model/{model}.bin"] = TARGET / "models" / f"{model}.bin"


def main():
    for remote, local in FILES.items():
        local.parent.mkdir(parents=True, exist_ok=True)
        print(f"กำลังโหลด {remote} ...", end=" ", flush=True)
        try:
            with urllib.request.urlopen(f"{BASE}/{remote}", timeout=60) as response:
                data = response.read()
        except Exception as exc:  # noqa: BLE001
            print(f"ล้มเหลว: {exc}")
            sys.exit(1)
        local.write_bytes(data)
        print(f"เรียบร้อย ({len(data) / 1024:.0f} KB)")
    print("เสร็จแล้ว ไฟล์อยู่ที่", TARGET)


if __name__ == "__main__":
    main()
