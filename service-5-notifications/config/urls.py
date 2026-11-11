from django.contrib import admin
from django.urls import path
from notifications.views import (
    home_dashboard,
    send_absence_alert,
    student_notifications,
    update_preferences,
    mark_as_read,
)

urlpatterns = [
    path('', home_dashboard),
    path('admin/', admin.site.urls),
    path('api/notifications/alert/', send_absence_alert),
    path('api/notifications/student/<int:etudiant_id>/', student_notifications),
    path('api/notifications/preferences/', update_preferences),
    path('api/notifications/read/<int:notif_id>/', mark_as_read),
]