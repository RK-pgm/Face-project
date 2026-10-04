import re
from decimal import Decimal

from django import forms

from .models import LoginLog
from .textutil import clean_text

PIN_PATTERN = re.compile(r"^\d{4,6}$")


def _clean_name_field(value, label):
    cleaned = clean_text(value)
    if not cleaned:
        raise forms.ValidationError(f"Please enter a valid {label}.")
    return cleaned


class RegisterForm(forms.Form):
    first_name = forms.CharField(max_length=50, error_messages={"required": "Please enter your first name.", "max_length": "First name must be 50 characters or fewer."})
    last_name = forms.CharField(max_length=50, error_messages={"required": "Please enter your last name.", "max_length": "Last name must be 50 characters or fewer."})
    nickname = forms.CharField(max_length=30, error_messages={"required": "Please enter your nickname.", "max_length": "Nickname must be 30 characters or fewer."})
    pin = forms.CharField(strip=False, error_messages={"required": "Please enter your PIN."})
    pin_confirm = forms.CharField(strip=False, error_messages={"required": "Please re-enter your PIN to confirm."})
    consent = forms.BooleanField(error_messages={"required": "You must consent to face data storage before registering."})

    def clean_first_name(self):
        return _clean_name_field(self.cleaned_data["first_name"], "Name")

    def clean_last_name(self):
        return _clean_name_field(self.cleaned_data["last_name"], "Last name")

    def clean_nickname(self):
        return _clean_name_field(self.cleaned_data["nickname"], "Nickname")

    def clean_pin(self):
        pin = self.cleaned_data["pin"]
        if not PIN_PATTERN.match(pin):
            raise forms.ValidationError("PIN must contain 4 to 6 digits.")
        return pin

    def clean(self):
        cleaned = super().clean()
        pin, confirm = cleaned.get("pin"), cleaned.get("pin_confirm")
        if pin and confirm and pin != confirm:
            self.add_error("pin_confirm", "The PIN entries do not match.")
        return cleaned


class ChangeFaceForm(forms.Form):

    pin = forms.CharField(strip=False, error_messages={"required": "Please enter your current PIN."})

    def clean_pin(self):
        pin = self.cleaned_data["pin"]
        if not PIN_PATTERN.match(pin):
            raise forms.ValidationError("PIN must contain 4 to 6 digits.")
        return pin


class SaleForm(forms.Form):

    amount = forms.DecimalField(
        max_digits=9, decimal_places=2, min_value=Decimal("0"),
        error_messages={"required": "Please enter an amount.", "invalid": "Enter a valid amount.",
                         "min_value": "Amount cannot be negative."},
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "inputmode": "decimal"}),
    )
    payment_method = forms.ChoiceField(
        choices=LoginLog.PaymentMethod.choices,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        error_messages={"required": "Please select a payment method.", "invalid_choice": "Select a valid payment method."},
    )
