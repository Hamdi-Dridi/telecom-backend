from django.contrib import admin

from .models import (
    ActivityLog, IndicatorThreshold, KPI, KPIDomain, KPIGroup, KPIPlan, KPIResult, Period, Region, ScoreSnapshot,
)


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ['name']


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ['label', 'month', 'year', 'order']
    ordering = ['order']


@admin.register(KPIDomain)
class KPIDomainAdmin(admin.ModelAdmin):
    list_display = ['name']


@admin.register(KPIGroup)
class KPIGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'domain']
    list_filter = ['domain']


@admin.register(KPI)
class KPIAdmin(admin.ModelAdmin):
    list_display = ['name', 'domain', 'group', 'weight', 'is_custom', 'is_retired']
    list_filter = ['domain', 'is_custom', 'is_retired']
    search_fields = ['name']


@admin.register(KPIResult)
class KPIResultAdmin(admin.ModelAdmin):
    list_display = ['kpi', 'period', 'region', 'realisation', 'objectif', 'validation']
    list_filter = ['period', 'region', 'validation']
    search_fields = ['kpi__name']


@admin.register(IndicatorThreshold)
class IndicatorThresholdAdmin(admin.ModelAdmin):
    list_display = ['label', 'kpi', 'green_min', 'orange_min']


@admin.register(KPIPlan)
class KPIPlanAdmin(admin.ModelAdmin):
    list_display = ['kpi', 'target', 'created_by', 'created_at']


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['text', 'user', 'created_at']


@admin.register(ScoreSnapshot)
class ScoreSnapshotAdmin(admin.ModelAdmin):
    list_display = ['period', 'region', 'global_score']
