from rest_framework.routers import DefaultRouter

from .views import StudentViewSet, TeacherViewSet, UserViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("students", StudentViewSet, basename="student")
router.register("teachers", TeacherViewSet, basename="teacher")

urlpatterns = router.urls
