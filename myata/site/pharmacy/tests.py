"""Небольшие проверки проекта. Запуск: python manage.py test pharmacy"""
from datetime import date, timedelta
from decimal import Decimal
from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Manufacturer, Medicine, Order, Pharmacy, Prescription, Stock


class PharmacySiteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("buyer", password="StrongStudyPass123")
        self.manufacturer = Manufacturer.objects.create(name="Тест", country="Россия")
        self.pharmacy = Pharmacy.objects.create(
            name="Учебная аптека", address="Тестовая улица, 1",
            phone="+79001234567", schedule="09:00–21:00"
        )
        self.medicine = Medicine.objects.create(
            name="Проверочный препарат", description="Описание",
            substance="Тестовое вещество", form="Таблетки", dosage="200 мг",
            price=Decimal("125.00"), prescription_required=False,
            manufacturer=self.manufacturer,
        )
        Stock.objects.create(medicine=self.medicine, pharmacy=self.pharmacy, quantity=10, available=True)

    def test_pages_and_search(self):
        self.assertEqual(self.client.get(reverse("pharmacy:home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("pharmacy:about")).status_code, 200)
        result = self.client.get(reverse("pharmacy:search"), {"q": "Тестовое вещество"})
        self.assertContains(result, "Проверочный препарат")

    def test_catalog_filters(self):
        response = self.client.get(reverse("pharmacy:catalog"), {"rx": "yes"})
        self.assertNotContains(response, "Проверочный препарат")
        response = self.client.get(reverse("pharmacy:catalog"), {"rx": "no"})
        self.assertContains(response, "Проверочный препарат")
        ajax = self.client.get(reverse("pharmacy:catalog"), {"q": "Проверочный"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertContains(ajax, "Проверочный препарат")

    def test_pagination_is_twenty(self):
        Medicine.objects.bulk_create([
            Medicine(name=f"Товар {i:02}", substance="Тест", form="Таблетки", dosage="10 мг",
                     price=Decimal("50.00"), manufacturer=self.manufacturer)
            for i in range(20)
        ])
        response = self.client.get(reverse("pharmacy:catalog"))
        self.assertEqual(len(response.context["page_obj"]), 20)
        self.assertEqual(response.context["page_obj"].paginator.num_pages, 2)

    def test_cart_and_order(self):
        self.client.post(reverse("pharmacy:cart_add", args=[self.medicine.pk]))
        response = self.client.get(reverse("pharmacy:cart"))
        self.assertContains(response, "125,00")
        self.client.force_login(self.user)
        response = self.client.post(reverse("pharmacy:checkout"), {
            "customer_name": "Учебный покупатель",
            "phone": "+79001234567",
            "pharmacy": self.pharmacy.pk,
        })
        self.assertRedirects(response, reverse("pharmacy:orders"))
        self.assertEqual(Order.objects.filter(user=self.user).count(), 1)
        self.assertEqual(Stock.objects.get(medicine=self.medicine).quantity, 9)

    def test_prescription_is_required_and_staff_access(self):
        self.medicine.prescription_required = True
        self.medicine.save(update_fields=["prescription_required"])
        self.client.force_login(self.user)
        self.client.post(reverse("pharmacy:cart_add", args=[self.medicine.pk]))
        data = {"customer_name": "Тест", "phone": "+79001234567", "pharmacy": self.pharmacy.pk}
        response = self.client.post(reverse("pharmacy:checkout"), data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.client.get(reverse("pharmacy:pharmacist")).status_code, 403)

        with TemporaryDirectory() as temp:
            with override_settings(MEDIA_ROOT=temp):
                today = date.today()
                data.update({
                    "prescription_number": "TEST-REC",
                    "issue_date": today.isoformat(),
                    "valid_until": (today + timedelta(days=14)).isoformat(),
                    "prescription_file": SimpleUploadedFile("study.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf"),
                })
                response = self.client.post(reverse("pharmacy:checkout"), data)
                self.assertRedirects(response, reverse("pharmacy:orders"))
                self.assertEqual(Prescription.objects.count(), 1)
                self.user.is_staff = True
                self.user.save(update_fields=["is_staff"])
                prescription = Prescription.objects.first()
                response = self.client.post(reverse("pharmacy:review_prescription", args=[prescription.pk]), {"status": "Подтверждён"})
                self.assertRedirects(response, reverse("pharmacy:pharmacist"))
                prescription.refresh_from_db()
                self.assertEqual(prescription.status, "Подтверждён")
