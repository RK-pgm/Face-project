"""
ตรวจข้อมูลฟอร์มสมัครสมาชิก

หน้าเว็บส่งข้อมูลมาเป็น JSON (ผ่าน fetch) เราจึงเอา dict มาใส่ Form ของ Django
เพื่อใช้ระบบตรวจข้อมูลที่ตรวจมาให้แล้ว แทนที่จะเขียน if/else เอง
"""
import re

from django import forms

from .textutil import clean_text

PIN_PATTERN = re.compile(r"^\d{4,6}$")


def _clean_name_field(value, label):
    cleaned = clean_text(value)
    if not cleaned:
        raise forms.ValidationError(f"กรุณากรอก{label}ให้ถูกต้อง")
    return cleaned


class RegisterForm(forms.Form):
    first_name = forms.CharField(max_length=50, error_messages={"required": "กรุณากรอกชื่อ", "max_length": "ชื่อยาวเกินไป (ไม่เกิน 50 ตัวอักษร)"})
    last_name = forms.CharField(max_length=50, error_messages={"required": "กรุณากรอกนามสกุล", "max_length": "นามสกุลยาวเกินไป (ไม่เกิน 50 ตัวอักษร)"})
    nickname = forms.CharField(max_length=30, error_messages={"required": "กรุณากรอกชื่อเล่น", "max_length": "ชื่อเล่นยาวเกินไป (ไม่เกิน 30 ตัวอักษร)"})
    pin = forms.CharField(strip=False, error_messages={"required": "กรุณากรอกรหัสตัวเลข"})
    pin_confirm = forms.CharField(strip=False, error_messages={"required": "กรุณากรอกรหัสตัวเลขอีกครั้งเพื่อยืนยัน"})
    consent = forms.BooleanField(error_messages={"required": "ต้องติ๊กยินยอมให้เก็บภาพใบหน้าก่อนสมัคร"})

    def clean_first_name(self):
        return _clean_name_field(self.cleaned_data["first_name"], "ชื่อ")

    def clean_last_name(self):
        return _clean_name_field(self.cleaned_data["last_name"], "นามสกุล")

    def clean_nickname(self):
        return _clean_name_field(self.cleaned_data["nickname"], "ชื่อเล่น")

    def clean_pin(self):
        pin = self.cleaned_data["pin"]
        if not PIN_PATTERN.match(pin):
            raise forms.ValidationError("รหัสต้องเป็นตัวเลข 4-6 หลักเท่านั้น")
        return pin

    def clean(self):
        cleaned = super().clean()
        pin, confirm = cleaned.get("pin"), cleaned.get("pin_confirm")
        if pin and confirm and pin != confirm:
            self.add_error("pin_confirm", "รหัสตัวเลขสองช่องไม่ตรงกัน")
        return cleaned
