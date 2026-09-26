import unicodedata


def clean_text(value):
    """
    ทำความสะอาดข้อความที่ผู้ใช้พิมพ์ (ชื่อ นามสกุล ชื่อเล่น)
    - ตัดช่องว่างหัวท้าย และยุบช่องว่างซ้อนให้เหลือช่องเดียว
    - แปลงเป็นรูปแบบ Unicode มาตรฐาน (NFC) เพื่อให้ตัวอักษรไทยที่พิมพ์คนละเครื่องเทียบกันได้
    - คืนค่า None ถ้ามีอักขระควบคุมที่มองไม่เห็น (เช่น \\n, \\x00)

    หมายเหตุ: ตั้งใจไม่ใช้ regex \\w เพราะมันไม่นับสระ/วรรณยุกต์ไทยเป็นตัวอักษร
    """
    if not isinstance(value, str):
        return None
    value = unicodedata.normalize("NFC", value)
    if any(unicodedata.category(ch).startswith("C") for ch in value):
        return None
    return " ".join(value.split())
