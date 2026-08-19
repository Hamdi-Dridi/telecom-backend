from rest_framework import serializers

from .models import (
    ActivityLog, IndicatorThreshold, KPI, KPIDomain, KPIGroup, KPIPlan, KPIResult, Period, Region, ScoreSnapshot,
)
from .scoring import STATUT_LABELS, score, statut, taux_pct


class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = ['id', 'name']


class PeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Period
        fields = ['id', 'label', 'month', 'year', 'order']


class KPIDomainSerializer(serializers.ModelSerializer):
    class Meta:
        model = KPIDomain
        fields = ['id', 'name']


class KPIGroupSerializer(serializers.ModelSerializer):
    domain = serializers.SlugRelatedField(slug_field='name', queryset=KPIDomain.objects.all())

    class Meta:
        model = KPIGroup
        fields = ['id', 'domain', 'name']


class IndicatorThresholdSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndicatorThreshold
        fields = ['id', 'kpi', 'green_min', 'orange_min', 'label']


class KPISerializer(serializers.ModelSerializer):
    # Plain name strings in and out (not IDs) — matches how the frontend's
    # "+ Créer un nouvel indicateur" form and CSV import both work: you
    # type/provide a domain and sub-group name, and it's fine if that name
    # doesn't exist as a KPIDomain/KPIGroup row yet. create()/update() below
    # resolve-or-create them, exactly like the CSV import path already does
    # — so both ways of adding a real indicator behave the same way.
    domain = serializers.CharField()
    group = serializers.CharField()

    class Meta:
        model = KPI
        fields = ['id', 'domain', 'group', 'name', 'unit', 'weight', 'is_custom', 'is_retired', 'created_at']
        read_only_fields = ['id', 'is_custom', 'created_at']

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep['domain'] = instance.domain.name
        rep['group'] = instance.group.name
        return rep

    def create(self, validated_data):
        domain_name = validated_data.pop('domain')
        group_name = validated_data.pop('group')
        domain, _ = KPIDomain.objects.get_or_create(name=domain_name)
        group, _ = KPIGroup.objects.get_or_create(domain=domain, name=group_name)
        return KPI.objects.create(domain=domain, group=group, **validated_data)

    def update(self, instance, validated_data):
        domain_name = validated_data.pop('domain', None)
        group_name = validated_data.pop('group', None)
        if domain_name is not None:
            domain, _ = KPIDomain.objects.get_or_create(name=domain_name)
            instance.domain = domain
        if group_name is not None:
            domain_for_group = instance.domain
            group, _ = KPIGroup.objects.get_or_create(domain=domain_for_group, name=group_name)
            instance.group = group
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class KPIResultSerializer(serializers.ModelSerializer):
    kpi_name = serializers.CharField(source='kpi.name', read_only=True)
    domain = serializers.CharField(source='kpi.domain.name', read_only=True)
    group = serializers.CharField(source='kpi.group.name', read_only=True)
    period_label = serializers.CharField(source='period.label', read_only=True)
    region_name = serializers.CharField(source='region.name', read_only=True)
    weight = serializers.FloatField(source='kpi.weight', read_only=True)
    taux = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()
    statut = serializers.SerializerMethodField()
    statut_label = serializers.SerializerMethodField()

    class Meta:
        model = KPIResult
        fields = [
            'id', 'kpi', 'kpi_name', 'domain', 'group', 'period', 'period_label', 'region', 'region_name',
            'weight', 'realisation', 'objectif', 'comment', 'validation', 'taux', 'score', 'statut',
            'statut_label', 'updated_at',
        ]
        read_only_fields = ['id', 'updated_at']

    def get_taux(self, obj):
        return taux_pct(obj.objectif, obj.realisation)

    def get_score(self, obj):
        return score(obj.kpi.weight, obj.objectif, obj.realisation)

    def get_statut(self, obj):
        return statut(obj.kpi, obj.objectif, obj.realisation)

    def get_statut_label(self, obj):
        return STATUT_LABELS[self.get_statut(obj)]

    def save(self, **kwargs):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            kwargs.setdefault('updated_by', request.user)
        return super().save(**kwargs)


class KPIPlanSerializer(serializers.ModelSerializer):
    kpi_name = serializers.CharField(source='kpi.name', read_only=True)
    periods = serializers.PrimaryKeyRelatedField(many=True, queryset=Period.objects.all())
    regions = serializers.PrimaryKeyRelatedField(many=True, queryset=Region.objects.all())

    class Meta:
        model = KPIPlan
        fields = ['id', 'kpi', 'kpi_name', 'target', 'periods', 'regions', 'created_at']
        read_only_fields = ['id', 'created_at']


class ActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityLog
        fields = ['id', 'text', 'created_at']


class ScoreSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScoreSnapshot
        fields = [
            'id', 'period', 'region', 'global_score', 'commercial_score',
            'technique_score', 'strategique_score', 'financier_score', 'computed_at',
        ]
