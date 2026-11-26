from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from attendance.health import health

urlpatterns = [
    path("health/", health),                                   # health-check Consul / Traefik
    path("api/attendance/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/attendance/docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("api/attendance/", include("attendance.urls")),
]
