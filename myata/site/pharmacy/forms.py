from datetime import date
from pathlib import Path
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Medicine, Pharmacy


class RegisterForm(UserCreationForm):
    email = forms.EmailField(label="Электронная почта", required=False)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")
        labels = {"username": "Логин"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.help_text = ""


class CheckoutForm(forms.Form):
    customer_name = forms.CharField(label="Ваше имя", max_length=100)
    phone = forms.CharField(label="Телефон", max_length=20)
    pharmacy = forms.ModelChoiceField(label="Аптека самовывоза", queryset=Pharmacy.objects.none())
    prescription_number = forms.CharField(label="Номер рецепта", max_length=50, required=False)
    issue_date = forms.DateField(
        label="Дата выдачи", required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    valid_until = forms.DateField(
        label="Срок действия", required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    prescription_file = forms.FileField(
        label="Фото или PDF рецепта", required=False,
        widget=forms.ClearableFileInput(attrs={"accept": ".pdf,.jpg,.jpeg,.png"}),
    )

    def __init__(self, *args, pharmacies=None, has_prescription=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.has_prescription = has_prescription
        self.fields["pharmacy"].queryset = pharmacies if pharmacies is not None else Pharmacy.objects.none()
        self.fields["pharmacy"].label_from_instance = lambda obj: f"{obj.name} — {obj.address}"
        prescription_fields = ("prescription_number", "issue_date", "valid_until", "prescription_file")
        if has_prescription:
            for key in prescription_fields:
                self.fields[key].required = True
        else:
            for key in prescription_fields:
                self.fields.pop(key)

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if sum(ch.isdigit() for ch in phone) < 10:
            raise forms.ValidationError("Укажи номер телефона не менее чем с 10 цифрами.")
        return phone

    def clean(self):
        cleaned = super().clean()
        if self.has_prescription:
            issue_date = cleaned.get("issue_date")
            valid_until = cleaned.get("valid_until")
            file = cleaned.get("prescription_file")
            if issue_date and issue_date > date.today():
                self.add_error("issue_date", "Дата выдачи не может быть в будущем.")
            if valid_until and issue_date and valid_until < issue_date:
                self.add_error("valid_until", "Срок действия не может быть раньше даты выдачи.")
            if valid_until and valid_until < date.today():
                self.add_error("valid_until", "Срок действия рецепта истёк.")
            if file:
                if Path(file.name).suffix.lower() not in (".pdf", ".jpg", ".jpeg", ".png"):
                    self.add_error("prescription_file", "Допустимы только PDF, JPG и PNG.")
                if file.size > 10 * 1024 * 1024:
                    self.add_error("prescription_file", "Файл должен быть не больше 10 МБ.")
        return cleaned


class MedicineForm(forms.ModelForm):
    class Meta:
        model = Medicine
        fields = ("name", "description", "substance", "form", "dosage", "price", "manufacturer", "prescription_required")


class ReviewForm(forms.Form):
    status = forms.ChoiceField(
        label="Результат проверки",
        choices=[("Подтверждён", "Подтвердить"), ("Отклонён", "Отклонить")],
    )
