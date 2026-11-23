from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("departements", views.DepartementViewSet)
router.register("groupes", views.GroupeViewSet)
router.register("modules", views.ModuleViewSet)
router.register("salles", views.SalleViewSet)
router.register("seances", views.SeanceViewSet, basename="seance")

urlpatterns = [
    path("structure/options/", views.StructureOptionsView.as_view()),
    path("timetable/check-conflicts/", views.CheckConflictsView.as_view()),
    path("timetable/week/", views.WeekView.as_view()),
    path("", include(router.urls)),
]
