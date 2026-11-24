"""Учебные тестовые данные для онлайн-аптеки «Мята».

Положите файл рядом с manage.py и запустите в PowerShell:
python manage.py shell -c "exec(open('fill_remaining.py', encoding='utf-8').read())"

Файл не удаляет существующие записи. Повторный запуск не создаёт
дубликаты для перечисленных ниже тестовых препаратов, остатков и заказов.
"""

from base64 import b64decode
from datetime import timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.utils import timezone

from pharmacy.models import (
    Manufacturer,
    Pharmacy,
    Medicine,
    Stock,
    Order,
    OrderItem,
    Prescription,
)


def status_value(model, display_name):
    """Получить значение статуса по русской подписи (работает и с TextChoices)."""
    field = model._meta.get_field("status")
    for value, label in field.flatchoices:
        if str(label) == display_name:
            return value
    return display_name


# 1. Проверяем производителей и аптеки, добавленные ранее.
manufacturer_names = ["Фармстандарт", "Озон Фармацевтика", "Биннофарм Групп"]
manufacturers = {
    name: Manufacturer.objects.get_or_create(
        name=name, defaults={"country": "Россия"}
    )[0]
    for name in manufacturer_names
}

pharmacies = {
    name: Pharmacy.objects.get(name=name)
    for name in ("Мята №1", "Мята №2", "Мята №3")
}

# 2. Препараты: название, действующее вещество, форма, дозировка,
#    цена (условная), необходимость рецепта, производитель.
medicine_rows = [
    ("Парацетамол", "Парацетамол", "Таблетки", "500 мг", "120.00", False, "Фармстандарт"),
    ("Ибупрофен", "Ибупрофен", "Таблетки", "200 мг", "180.00", False, "Озон Фармацевтика"),
    ("Цетиризин", "Цетиризин", "Таблетки", "10 мг", "210.00", False, "Биннофарм Групп"),
    ("Витамин C", "Аскорбиновая кислота", "Таблетки", "500 мг", "160.00", False, "Фармстандарт"),
    ("Амоксициллин", "Амоксициллин", "Капсулы", "500 мг", "320.00", True, "Озон Фармацевтика"),
]

medicines = {}
for name, substance, form, dosage, price, rx, maker in medicine_rows:
    medicine, _ = Medicine.objects.get_or_create(
        name=name,
        defaults={
            "description": "Учебная запись для проверки базы данных.",
            "substance": substance,
            "form": form,
            "dosage": dosage,
            "price": Decimal(price),
            "prescription_required": rx,
            "manufacturer": manufacturers[maker],
        },
    )
    medicines[name] = medicine

# 3. Остатки. Уникальная пара — препарат + аптека.
stock_rows = [
    ("Парацетамол", "Мята №1", 25),
    ("Ибупрофен", "Мята №1", 15),
    ("Цетиризин", "Мята №2", 30),
    ("Витамин C", "Мята №2", 40),
    ("Амоксициллин", "Мята №3", 12),
    ("Парацетамол", "Мята №3", 50),
]
for medicine_name, pharmacy_name, quantity in stock_rows:
    Stock.objects.get_or_create(
        medicine=medicines[medicine_name],
        pharmacy=pharmacies[pharmacy_name],
        defaults={"quantity": quantity, "available": True},
    )

# 4. Заказы. Статусы определяются по choices используемой версии модели.
order1, _ = Order.objects.get_or_create(
    number="TEST-ORD-001",
    defaults={
        "customer_name": "Тестовый покупатель 1",
        "phone": "+79000000111",
        "status": status_value(Order, "Создан"),
        "pharmacy": pharmacies["Мята №1"],
    },
)
order2, _ = Order.objects.get_or_create(
    number="TEST-ORD-002",
    defaults={
        "customer_name": "Тестовый покупатель 2",
        "phone": "+79000000222",
        "status": status_value(Order, "Ожидает проверки"),
        "pharmacy": pharmacies["Мята №3"],
    },
)

# 5. Позиции заказов. В разных версиях models.py поле цены
#    называлось price или unit_price — предусмотрены оба случая.
order_item_field_names = {f.name for f in OrderItem._meta.fields}
price_field = next(
    (field for field in ("unit_price", "price", "price_at_order") if field in order_item_field_names),
    None,
)
if price_field is None:
    raise RuntimeError("В OrderItem не найдено поле цены: price или unit_price.")

order_item_rows = [
    (order1, "Парацетамол", 2, "120.00"),
    (order1, "Ибупрофен", 1, "180.00"),
    (order2, "Амоксициллин", 1, "320.00"),
]
for order, medicine_name, quantity, price in order_item_rows:
    unit_price = Decimal(price)
    OrderItem.objects.get_or_create(
        order=order,
        medicine=medicines[medicine_name],
        defaults={
            "quantity": quantity,
            price_field: unit_price,
            "total_price": unit_price * quantity,
        },
    )

# 6. Один учебный рецепт и настоящий (но НЕ медицинский) тестовый PNG-файл.
#    Маленькое пустое изображение — лишь проверка загрузки, НЕ рецепт врача.
today = timezone.localdate()
prescription, created = Prescription.objects.get_or_create(
    number="TEST-REC-001",
    defaults={
        "issue_date": today - timedelta(days=7),
        "valid_until": today + timedelta(days=30),
        "status": status_value(Prescription, "Ожидает проверки"),
        "order": order2,
        "file": "recipes/test_prescription.png",
    },
)
if created or not prescription.file.storage.exists(prescription.file.name):
    png_data = b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAMAAAADCAIAAADZSiLoAAAAF0lEQVR4nGP8+vUrAwMDAwMDEwMMIFgAUNwC5Q7LFJ4AAAAASUVORK5CYII="
    )
    prescription.file.save("test_prescription.png", ContentFile(png_data), save=True)

print("\nУчебные данные добавлены (существующие совпадения не дублируются):")
for model in (Medicine, Stock, Order, OrderItem, Prescription):
    print(f"  {model._meta.verbose_name_plural}: {model.objects.count()}")
print("\nЗаказ TEST-ORD-001: 2 × 120 + 1 × 180 = 420 руб.")
print("Заказ TEST-ORD-002: 1 × 320 = 320 руб.")
print("Тестовый PNG рецепта:", prescription.file.name)
