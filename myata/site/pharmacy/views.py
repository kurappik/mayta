from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.http import FileResponse, Http404, HttpResponseBadRequest, JsonResponse
from django.utils.http import url_has_allowed_host_and_scheme
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import CheckoutForm, MedicineForm, RegisterForm, ReviewForm
from .models import Manufacturer, Medicine, Order, OrderItem, Pharmacy, Prescription, Stock


def cart_data(request):
    saved = request.session.get("cart", {})
    items = []
    total = Decimal("0.00")
    for key, quantity in saved.items():
        try:
            medicine = Medicine.objects.get(pk=int(key))
            quantity = int(quantity)
        except (Medicine.DoesNotExist, ValueError, TypeError):
            continue
        if not 1 <= quantity <= 99:
            continue
        subtotal = medicine.price * quantity
        items.append({"medicine": medicine, "quantity": quantity, "subtotal": subtotal})
        total += subtotal
    return items, total


def home(request):
    medicines = Medicine.objects.select_related("manufacturer").order_by("name")[:4]
    forms = Medicine.objects.order_by("form").values_list("form", flat=True).distinct()[:4]
    return render(request, "index.html", {"medicines": medicines, "forms": forms})


def medicine_search(qs, request):
    query = request.GET.get("q", "").strip()
    form = request.GET.get("form", "").strip()
    rx = request.GET.get("rx", "")
    sort = request.GET.get("sort", "name")
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(substance__icontains=query))
    if form:
        qs = qs.filter(form=form)
    if rx == "yes":
        qs = qs.filter(prescription_required=True)
    elif rx == "no":
        qs = qs.filter(prescription_required=False)
    if sort not in ("name", "price", "-price"):
        sort = "name"
    return qs.order_by(sort, "pk"), {"q": query, "selected_form": form, "rx": rx, "sort": sort}


def results_page(request, template):
    qs, filters = medicine_search(Medicine.objects.select_related("manufacturer"), request)
    page = Paginator(qs, 20).get_page(request.GET.get("page"))
    context = {**filters, "page_obj": page, "forms": Medicine.objects.order_by("form").values_list("form", flat=True).distinct()}
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        # AJAX только для фильтров: вернём фрагмент без повторной шапки.
        return render(request, "_product_results.html", context)
    return render(request, template, context)


def catalog(request):
    return results_page(request, "catalog.html")


def search(request):
    return results_page(request, "search.html")


def product(request, pk):
    medicine = get_object_or_404(Medicine.objects.select_related("manufacturer"), pk=pk)
    stocks = medicine.stocks.select_related("pharmacy").filter(available=True, quantity__gt=0)
    analogs = Medicine.objects.filter(substance__iexact=medicine.substance).exclude(pk=pk)[:4]
    return render(request, "product.html", {"medicine": medicine, "stocks": stocks, "analogs": analogs})


def cart(request):
    items, total = cart_data(request)
    return render(request, "cart.html", {"items": items, "total": total})


@require_POST
def add_to_cart(request, pk):
    medicine = get_object_or_404(Medicine, pk=pk)
    if not medicine.stocks.filter(available=True, quantity__gt=0).exists():
        messages.error(request, "Пока нет доступного остатка этого препарата.")
        return redirect("pharmacy:product", pk=pk)
    cart_items = request.session.get("cart", {})
    cart_items[str(pk)] = min(99, int(cart_items.get(str(pk), 0)) + 1)
    request.session["cart"] = cart_items
    messages.success(request, f"{medicine.name} добавлен в корзину.")
    return redirect("pharmacy:cart")


@require_POST
def update_cart(request, pk):
    medicine = get_object_or_404(Medicine, pk=pk)
    try:
        quantity = int(request.POST.get("quantity", ""))
    except (ValueError, TypeError):
        return HttpResponseBadRequest("Укажи целое количество.")
    if quantity < 0 or quantity > 99:
        return HttpResponseBadRequest("Количество должно быть от 0 до 99.")
    saved = request.session.get("cart", {})
    if quantity == 0:
        saved.pop(str(pk), None)
    else:
        saved[str(pk)] = quantity
    request.session["cart"] = saved
    items, total = cart_data(request)
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "ok": True, "total": f"{total:.2f}",
            "item_total": f"{medicine.price * quantity:.2f}",
            "quantity": quantity,
            "count": sum(item["quantity"] for item in items),
        })
    messages.success(request, "Корзина обновлена.")
    return redirect("pharmacy:cart")


def available_pharmacies(items):
    pharmacies = Pharmacy.objects.all()
    for item in items:
        pharmacies = pharmacies.filter(
            stocks__medicine=item["medicine"],
            stocks__available=True,
            stocks__quantity__gte=item["quantity"],
        )
    return pharmacies.distinct()


@login_required
def checkout(request):
    items, total = cart_data(request)
    if not items:
        messages.error(request, "Корзина пуста.")
        return redirect("pharmacy:cart")
    pharmacies = available_pharmacies(items)
    needs_recipe = any(item["medicine"].prescription_required for item in items)
    if request.method == "POST":
        form = CheckoutForm(request.POST, request.FILES, pharmacies=pharmacies, has_prescription=needs_recipe)
        if form.is_valid():
            pharmacy = form.cleaned_data["pharmacy"]
            try:
                with transaction.atomic():
                    # Проверяем остатки повторно перед записью заказа
                    for item in items:
                        stock = Stock.objects.select_for_update().filter(
                            medicine=item["medicine"], pharmacy=pharmacy,
                            available=True, quantity__gte=item["quantity"]
                        ).first()
                        if stock is None:
                            raise ValueError(f"Недостаточно товара «{item['medicine'].name}» в выбранной аптеке.")
                    order = Order.objects.create(
                        number="MYA-" + uuid4().hex[:12].upper(),
                        user=request.user,
                        customer_name=form.cleaned_data["customer_name"],
                        phone=form.cleaned_data["phone"],
                        pharmacy=pharmacy,
                        status="Ожидает проверки" if needs_recipe else "Создан",
                    )
                    for item in items:
                        OrderItem.objects.create(
                            order=order,
                            medicine=item["medicine"],
                            quantity=item["quantity"],
                            price=item["medicine"].price,
                            total_price=item["subtotal"],
                        )
                        stock = Stock.objects.get(medicine=item["medicine"], pharmacy=pharmacy)
                        stock.quantity -= item["quantity"]
                        stock.available = stock.quantity > 0
                        stock.save()
                    if needs_recipe:
                        Prescription.objects.create(
                            order=order,
                            number=form.cleaned_data["prescription_number"],
                            issue_date=form.cleaned_data["issue_date"],
                            valid_until=form.cleaned_data["valid_until"],
                            file=form.cleaned_data["prescription_file"],
                            status="Ожидает проверки",
                        )
            except ValueError as exc:
                form.add_error("pharmacy", str(exc))
            else:
                request.session["cart"] = {}
                messages.success(request, f"Заказ {order.number} создан. Его статус можно проверить в личном кабинете.")
                return redirect("pharmacy:orders")
    else:
        form = CheckoutForm(
            pharmacies=pharmacies, has_prescription=needs_recipe,
            initial={"customer_name": request.user.get_full_name() or request.user.username},
        )
    return render(request, "checkout.html", {
        "form": form, "items": items, "total": total,
        "needs_recipe": needs_recipe, "has_pharmacies": pharmacies.exists(),
    })


def sign_in(request):
    if request.user.is_authenticated:
        return redirect("pharmacy:profile")
    next_page = request.POST.get("next") or request.GET.get("next", "")
    if request.method == "POST":
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            messages.success(request, "Вход выполнен.")
            if url_has_allowed_host_and_scheme(next_page, allowed_hosts={request.get_host()}):
                return redirect(next_page)
            return redirect("pharmacy:profile")
    else:
        form = AuthenticationForm(request)
    return render(request, "login.html", {"form": form, "next": next_page})


def register(request):
    if request.user.is_authenticated:
        return redirect("pharmacy:profile")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Аккаунт создан.")
            return redirect("pharmacy:profile")
    else:
        form = RegisterForm()
    return render(request, "register.html", {"form": form})


@require_POST
def sign_out(request):
    logout(request)
    messages.success(request, "Вы вышли из аккаунта.")
    return redirect("pharmacy:home")


@login_required
def profile(request):
    my_orders = Order.objects.filter(user=request.user).select_related("pharmacy")[:3]
    return render(request, "profile.html", {"orders": my_orders})


@login_required
def orders(request):
    my_orders = (Order.objects.filter(user=request.user)
                 .select_related("pharmacy")
                 .prefetch_related("items__medicine", "prescriptions"))
    return render(request, "orders.html", {"orders": my_orders})


def about(request):
    return render(request, "about.html")


def is_pharmacist(user):
    return user.is_authenticated and (user.is_staff or user.groups.filter(name="Фармацевты").exists())


@login_required
def pharmacist(request):
    if not is_pharmacist(request.user):
        raise PermissionDenied
    prescriptions = Prescription.objects.select_related("order", "order__pharmacy").all()
    return render(request, "pharmacist.html", {"prescriptions": prescriptions})


@login_required
@require_POST
def review_prescription(request, pk):
    if not is_pharmacist(request.user):
        raise PermissionDenied
    prescription = get_object_or_404(Prescription.objects.select_related("order"), pk=pk)
    form = ReviewForm(request.POST)
    if form.is_valid():
        with transaction.atomic():
            prescription.status = form.cleaned_data["status"]
            prescription.save(update_fields=["status"])
            order = prescription.order
            statuses = list(order.prescriptions.values_list("status", flat=True))
            if "Отклонён" in statuses:
                order.status = "Отклонён"
            elif statuses and all(s == "Подтверждён" for s in statuses):
                order.status = "Подтверждён"
            else:
                order.status = "Ожидает проверки"
            order.save(update_fields=["status"])
        messages.success(request, "Результат проверки сохранён.")
    else:
        messages.error(request, "Выбери допустимый статус проверки.")
    return redirect("pharmacy:pharmacist")


@login_required
def prescription_file(request, pk):
    prescription = get_object_or_404(Prescription.objects.select_related("order"), pk=pk)
    if not (is_pharmacist(request.user) or prescription.order.user_id == request.user.id):
        raise PermissionDenied
    try:
        opened_file = prescription.file.open("rb")
    except OSError:
        raise Http404("Файл не найден")
    return FileResponse(opened_file, as_attachment=True, filename=Path(prescription.file.name).name)


@login_required
def staff_panel(request):
    if not request.user.is_staff:
        raise PermissionDenied
    stats = {
        "medicines": Medicine.objects.count(),
        "pharmacies": Pharmacy.objects.count(),
        "orders": Order.objects.count(),
    }
    medicines = Medicine.objects.select_related("manufacturer")[:30]
    return render(request, "admin.html", {"stats": stats, "medicines": medicines, "form": MedicineForm()})


@login_required
@require_POST
def create_medicine(request):
    if not request.user.is_staff:
        raise PermissionDenied
    form = MedicineForm(request.POST)
    if form.is_valid():
        medicine = form.save()
        messages.success(request, f"Препарат «{medicine.name}» добавлен.")
        return redirect("pharmacy:staff")
    stats = {"medicines": Medicine.objects.count(), "pharmacies": Pharmacy.objects.count(), "orders": Order.objects.count()}
    return render(request, "admin.html", {"stats": stats, "medicines": Medicine.objects.select_related("manufacturer")[:30], "form": form}, status=400)
