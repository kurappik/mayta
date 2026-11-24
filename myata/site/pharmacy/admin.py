from django.contrib import admin
from .models import Manufacturer, Pharmacy, Medicine, Stock, Order, OrderItem, Prescription


@admin.register(Manufacturer)
class ManufacturerAdmin(admin.ModelAdmin):
    list_display = ("name", "country")
    search_fields = ("name",)


@admin.register(Pharmacy)
class PharmacyAdmin(admin.ModelAdmin):
    list_display = ("name", "address", "schedule")


@admin.register(Medicine)
class MedicineAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "manufacturer", "prescription_required")
    list_filter = ("prescription_required", "form")
    search_fields = ("name", "substance")


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ("medicine", "pharmacy", "quantity", "available", "updated_at")
    list_filter = ("pharmacy", "available")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "customer_name", "pharmacy", "status", "date")
    list_filter = ("status",)
    search_fields = ("number", "customer_name", "phone")
    inlines = [OrderItemInline]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ("order", "medicine", "quantity", "price", "total_price")


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ("number", "order", "status", "issue_date", "valid_until")
    list_filter = ("status",)
