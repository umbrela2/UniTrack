from django.conf import settings
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.views.static import serve
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

FRONTEND_DIR = settings.BASE_DIR / "frontend"


def health_check(request):
    return JsonResponse({"status": "ok", "service": "service-3-academic"}, status=200)


urlpatterns = [
    path("health/", health_check, name="health-check"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/academic/", include("academics.urls")),
    path("api/", include("academics.urls")),
    path(
        "ui/",
        serve,
        {"path": "index.html", "document_root": FRONTEND_DIR},
    ),
    re_path(
        r"^ui/(?P<path>.+)$",
        serve,
        {"document_root": FRONTEND_DIR},
    ),
]
