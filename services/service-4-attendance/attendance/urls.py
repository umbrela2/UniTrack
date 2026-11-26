from django.urls import include, path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("seances", views.SeanceViewSet, basename="seance")

urlpatterns = [
    path("v1/", include(router.urls)),
    path("v1/me/attendance/", views.MyAttendanceView.as_view()),
    path("v1/me/alerts/", views.MyAlertsView.as_view()),
    path("v1/history/", views.HistoryView.as_view()),
    path("v1/dashboard/", views.DashboardView.as_view()),
    path("v1/settings/", views.SettingsView.as_view()),
]
