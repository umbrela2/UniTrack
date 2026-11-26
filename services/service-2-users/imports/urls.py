from django.urls import path

from .views import ImportCreateView, ImportDetailView

urlpatterns = [
    path("users/import/", ImportCreateView.as_view(), name="import-create"),
    path("users/import/<uuid:pk>/", ImportDetailView.as_view(), name="import-detail"),
]
