from django.contrib import admin
from .models import NotificationTemplate, NotificationPreference, NotificationHistory

admin.site.register(NotificationTemplate)
admin.site.register(NotificationPreference)
admin.site.register(NotificationHistory)