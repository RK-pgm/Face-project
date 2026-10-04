from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path("login/", views.login_view, name="login"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("logout/", views.logout_view, name="logout"),
    path("me/photo/", views.my_photo, name="my_photo"),
    path("me/change-face/", views.change_face, name="change_face"),
    path("counter/", views.counter_queue, name="counter_queue"),
    path("counter/<int:log_id>/", views.record_sale, name="record_sale"),
    path("reports/daily/", views.daily_report, name="daily_report"),
]
