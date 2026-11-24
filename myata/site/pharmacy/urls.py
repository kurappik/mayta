from django.urls import path
from . import views

app_name = "pharmacy"

urlpatterns = [
    path("", views.home, name="home"),
    path("catalog/", views.catalog, name="catalog"),
    path("search/", views.search, name="search"),
    path("product/<int:pk>/", views.product, name="product"),
    path("cart/", views.cart, name="cart"),
    path("cart/add/<int:pk>/", views.add_to_cart, name="cart_add"),
    path("cart/update/<int:pk>/", views.update_cart, name="cart_update"),
    path("checkout/", views.checkout, name="checkout"),
    path("login/", views.sign_in, name="login"),
    path("register/", views.register, name="register"),
    path("logout/", views.sign_out, name="logout"),
    path("profile/", views.profile, name="profile"),
    path("orders/", views.orders, name="orders"),
    path("about/", views.about, name="about"),
    path("pharmacist/", views.pharmacist, name="pharmacist"),
    path("pharmacist/prescription/<int:pk>/", views.review_prescription, name="review_prescription"),
    path("prescription/<int:pk>/file/", views.prescription_file, name="prescription_file"),
    path("staff/", views.staff_panel, name="staff"),
    path("staff/medicine/add/", views.create_medicine, name="medicine_add"),
]
