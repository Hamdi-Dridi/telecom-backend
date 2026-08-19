from rest_framework.routers import DefaultRouter

from django.urls import path

from .views import (
    ActivityLogViewSet, ExportCSVView, ExportJSONView, HistoryView, ImportView, IndicatorThresholdViewSet,
    KPIDomainViewSet, KPIGroupViewSet, KPIPlanViewSet, KPIResultViewSet, KPIViewSet, OverviewView, PeriodViewSet,
    RegionViewSet, ResetDataView, ScoreSnapshotViewSet,
)

router = DefaultRouter()
router.register('regions', RegionViewSet, basename='region')
router.register('periods', PeriodViewSet, basename='period')
router.register('domains', KPIDomainViewSet, basename='domain')
router.register('groups', KPIGroupViewSet, basename='group')
router.register('thresholds', IndicatorThresholdViewSet, basename='threshold')
router.register('kpis', KPIViewSet, basename='kpi')
router.register('kpi-results', KPIResultViewSet, basename='result')
router.register('plans', KPIPlanViewSet, basename='plan')
router.register('activity', ActivityLogViewSet, basename='activity')
router.register('snapshots', ScoreSnapshotViewSet, basename='snapshot')

urlpatterns = [
    path('dashboard/overview/', OverviewView.as_view()),
    path('dashboard/history/', HistoryView.as_view()),
    path('export/csv/', ExportCSVView.as_view()),
    path('export/json/', ExportJSONView.as_view()),
    path('import/', ImportView.as_view()),
    path('reset/', ResetDataView.as_view()),
] + router.urls
