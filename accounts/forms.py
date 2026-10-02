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
    first_name = forms.CharField(max_length=50, error_messages={"required": "Please input your name.", "max_length": "Names too long (cannot over 50 alphabet)"})
    last_name = forms.CharField(max_length=50, error_messages={"required": "Please input you last name", "max_length": "Lastname too long (cannot over 50 alphabet)"})
    nickname = forms.CharField(max_length=30, error_messages={"required": "Please input you nickname", "max_length": "Nickname too long (cannot over 30 alphabet)"})
    pin = forms.CharField(strip=False, error_messages={"required": "Please input you password"})
    pin_confirm = forms.CharField(strip=False, error_messages={"required": "Please input password again for confirm"})
    consent = forms.BooleanField(error_messages={"required": "You must check the box consenting to the collection of facial images before signing up."})

    def clean_first_name(self):
        return _clean_name_field(self.cleaned_data["first_name"], "Name")

    def clean_last_name(self):
        return _clean_name_field(self.cleaned_data["last_name"], "Lastname")

    def clean_nickname(self):
        return _clean_name_field(self.cleaned_data["nickname"], "Nicknames")

    def clean_pin(self):
        pin = self.cleaned_data["pin"]
        if not PIN_PATTERN.match(pin):
            raise forms.ValidationError("Password is number 4 to 6 digits")
        return pin

    def clean(self):
        cleaned = super().clean()
        pin, confirm = cleaned.get("pin"), cleaned.get("pin_confirm")
        if pin and confirm and pin != confirm:
            self.add_error("pin_confirm", "password in the fields don't same.")
        return cleaned
class ChangeFaceForm(forms.Form):
    pin = forms.CharField(strip=False, error_messages={"required":"Please fill in your password."})
    def clean_pin(self):
        pin = self.cleaned_data["pin"]
        if not PIN_PATTERN.match(pin):
            raise forms.ValidationError("Password must be 4-6 digits only.")
        return pin