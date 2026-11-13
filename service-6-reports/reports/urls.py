from django.urls import path

from .views import (
    DashboardPageView,
    DashboardSummaryView,
    ExcelExportView,
    HealthView,
    NonAssuredSessionsView,
    PdfExportView,
    StudentStatsView,
    SyncView,
)

urlpatterns = [
    path('health/', HealthView.as_view(), name='health'),
    path(
        'dashboard/',
        DashboardPageView.as_view(),
        name='dashboard',
    ),
    path(
        'dashboard/summary/',
        DashboardSummaryView.as_view(),
        name='dashboard-summary',
    ),
    path(
        'non-assured-sessions/',
        NonAssuredSessionsView.as_view(),
        name='non-assured-sessions',
    ),
    path(
        'student/<str:matricule>/',
        StudentStatsView.as_view(),
        name='student-stats',
    ),
    path('sync/', SyncView.as_view(), name='sync'),
    path('export/excel/', ExcelExportView.as_view(), name='export-excel'),
    path('export/pdf/', PdfExportView.as_view(), name='export-pdf'),
]
