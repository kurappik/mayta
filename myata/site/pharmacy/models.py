from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db.models import F, Q
from django.utils import timezone

class Manufacturer(models.Model):
    name = models.CharField("Название", max_length=150)
    country = models.CharField("Страна", max_length=100)
    contacts = models.CharField("Контакты", max_length=150, blank=True)
    
    class Meta:
        verbose_name = "Производитель"
        verbose_name_plural = "Производители"
        ordering = ["name"]
        
    def __str__(self):
        return self.name


class Pharmacy(models.Model):
    name = models.CharField("Название", max_length=150)
    address = models.CharField("Адрес", max_length=150)
    phone = models.CharField("Телефон", max_length=20)
    schedule = models.CharField("График", max_length=150)

    class Meta:
        verbose_name = "Аптека"
        verbose_name_plural = "Аптеки"
        ordering = ["name"]

    def __str__(self):
        return self.name
   

class Medicine(models.Model):
    name = models.CharField("Название", max_length=150)
    description = models.TextField("Описание", max_length=2000, blank=True)
    substance = models.CharField("Действующее вещество", max_length=150)
    form = models.CharField("Форма выпуска", max_length=100)
    dosage = models.CharField("Дозировка", max_length=50)
    price = models.DecimalField("Цена", max_digits=10, decimal_places=2)
    prescription_required = models.BooleanField("Требуется рецепт", default=False)

    manufacturer = models.ForeignKey(
        Manufacturer,
        on_delete=models.PROTECT,
        related_name="medicines",
        verbose_name="Производитель"
    )

    pharmacies = models.ManyToManyField("Pharmacy",
        through="Stock",
        through_fields=("medicine", "pharmacy"),
        related_name="medicines"
    )

    class Meta:
        verbose_name = "Препарат"
        verbose_name_plural = "Препараты"
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gt=0),
                name="medicine_price_gt_0"
            )
        ]

    def __str__(self):
        return f"{self.name}, {self.dosage}"


class Stock(models.Model):
    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.CASCADE,
        related_name="stocks"
    )

    pharmacy = models.ForeignKey(
        "Pharmacy",
        on_delete=models.CASCADE,
        related_name="stocks"
    )

    quantity = models.PositiveIntegerField(
        "Количество", default=0
    )
    available = models.BooleanField(
        "Доступность", default=False
    )
    updated_at = models.DateTimeField(
        "Дата обновления", auto_now=True
    )

    class Meta:
        verbose_name = "Остаток в аптеке"
        verbose_name_plural = "Остатки в аптеках"
        ordering = ["pharmacy_id", "medicine_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["medicine", "pharmacy"],
                name="unique_medicine_pharmacy"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gte=0),
                name="stock_quantity_gte_0"
            )
        ]

    def __str__(self):
        return f"{self.medicine.name}: {self.quantity} шт."   


class Order(models.Model):
    number = models.CharField(
        "Номер заказа",
        max_length=30,
        unique=True
    )

    date = models.DateTimeField(
        "Дата заказа",
        auto_now_add=True
    )

    customer_name = models.CharField(
        "Имя покупателя",
        max_length=100
    )

    phone = models.CharField(
        "Телефон",
        max_length=20
    )

    status = models.CharField(
        "Статус заказа",
        max_length=30,
        choices=[
            ("Создан", "Создан"),
            ("Ожидает проверки", "Ожидает проверки"),
            ("Подтверждён", "Подтверждён"),
            ("Отклонён", "Отклонён"),
            ("Готов к выдаче", "Готов к выдаче")
        ],
        default="Создан"
    )

    pharmacy = models.ForeignKey(
        "Pharmacy",
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name="Аптека"
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="pharmacy_orders",
        null=True, blank=True,
        verbose_name="Покупатель (аккаунт)"
    )

    medicines = models.ManyToManyField(
        "Medicine",
        through="OrderItem",
        through_fields=("order", "medicine"),
        related_name="orders",
        verbose_name="Препараты заказа"
    )

    class Meta:
        verbose_name = "Заказ"
        verbose_name_plural = "Заказы"
        ordering = ["-date"]

    def __str__(self):
        return f"Заказ №{self.number}"


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="Заказ"
    )

    medicine = models.ForeignKey(
        Medicine,
        on_delete=models.PROTECT,
        related_name="order_items",
        verbose_name="Препарат"
    )

    quantity = models.PositiveIntegerField(
        "Количество",
        default=1
    )

    price = models.DecimalField(
        "Цена на момент заказа",
        max_digits=10,
        decimal_places=2
    )

    total_price = models.DecimalField(
        "Общая стоимость",
        max_digits=10,
        decimal_places=2
    )

    class Meta:
        verbose_name = "Позиция заказа"
        verbose_name_plural = "Позиции заказов"
        ordering = ["id"]

        constraints = [
            models.UniqueConstraint(
                fields=["order", "medicine"],
                name="unique_order_medicine"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="order_item_quantity_gt_0"
            ),
            models.CheckConstraint(
                condition=models.Q(price__gt=0),
                name="order_item_price_gt_0"
            ),
            models.CheckConstraint(
                condition=models.Q(total_price__gt=0),
                name="order_item_total_gt_0"
            )
        ]

    def __str__(self):
        return f"{self.medicine.name} — {self.quantity} шт."


class Prescription(models.Model):
    number = models.CharField(
        "Номер рецепта",
        max_length=50
    )

    issue_date = models.DateField("Дата выдачи")

    valid_until = models.DateField("Срок действия")

    file = models.FileField(
        "Файл рецепта",
        upload_to="recipes/"
    )

    status = models.CharField(
        "Статус проверки",
        max_length=30,
        choices=[
            ("Ожидает проверки", "Ожидает проверки"),
            ("Подтверждён", "Подтверждён"),
            ("Отклонён", "Отклонён")
        ],
        default="Ожидает проверки"
    )

    order = models.ForeignKey(
        "Order",
        on_delete=models.CASCADE,
        related_name="prescriptions",
        verbose_name="Заказ"
    )

    class Meta:
        verbose_name = "Рецепт"
        verbose_name_plural = "Рецепты"
        ordering = ["-issue_date"]

        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    valid_until__gte=models.F("issue_date")
                ),
                name="prescription_valid_dates"
            )
        ]

    def __str__(self):
        return f"Рецепт №{self.number}"
