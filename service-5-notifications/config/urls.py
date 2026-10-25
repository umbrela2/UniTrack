from django.contrib import admin
from django.urls import path
from notifications.views import send_absence_alert, student_notifications

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/notifications/alert/', send_absence_alert),
    path('api/notifications/student/<int:etudiant_id>/', student_notifications),
]