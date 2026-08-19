import csv
import io
import json
from datetime import datetime

from django.db import transaction
from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin, IsAdminOrReadOnly, IsManagerOrAdmin
from .models import (
    ActivityLog, IndicatorThreshold, KPI, KPIDomain, KPIGroup, KPIPlan, KPIResult, Period, Region, ScoreSnapshot,
)
from .scoring import STATUT_LABELS, score, statut, taux_pct
from .serializers import (
    ActivityLogSerializer, IndicatorThresholdSerializer, KPIDomainSerializer, KPIGroupSerializer,
    KPIPlanSerializer, KPIResultSerializer, KPISerializer, PeriodSerializer, RegionSerializer,
    ScoreSnapshotSerializer,
)

MONTH_NAMES_FR = ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre']


def log_activity(text, user=None):
    ActivityLog.objects.create(text=text, user=user)


def _region_for(request):
    name = request.query_params.get('region') or request.data.get('region')
    if not name:
        return Region.objects.first()
    # Case-insensitive match: region names are free-typed in Django admin,
    # so "Grand Tunis" vs "grand tunis" shouldn't silently 400 an import.
    # (Matches how indicator names are already matched during CSV import.)
    return Region.objects.filter(name__iexact=name.strip()).first()


def _period_for(request):
    pid = request.query_params.get('period') or request.data.get('period')
    if pid:
        return Period.objects.filter(pk=pid).first()
    return Period.objects.order_by('-order').first()


class RegionViewSet(viewsets.ModelViewSet):
    queryset = Region.objects.all()
    serializer_class = RegionSerializer
    permission_classes = [IsAdminOrReadOnly]


class PeriodViewSet(viewsets.ModelViewSet):
    queryset = Period.objects.all()
    serializer_class = PeriodSerializer
    permission_classes = [IsAdminOrReadOnly]

    @action(detail=False, methods=['post'])
    def add_next(self, request):
        """Adds the month right after the latest one on record — used by the
        rolling calendar when an admin plans an objective for a month that
        doesn't exist yet."""
        last = Period.objects.order_by('-order').first()
        if not last:
            return Response({'detail': 'Aucune période existante.'}, status=400)
        idx = MONTH_NAMES_FR.index(last.label.split(' ')[0])
        year = last.year
        next_idx = (idx + 1) % 12
        next_year = year + 1 if idx == 11 else year
        label = f'{MONTH_NAMES_FR[next_idx]} {next_year}'
        period, created = Period.objects.get_or_create(
            label=label, defaults={'month': next_idx + 1, 'year': next_year, 'order': last.order + 1}
        )
        return Response(PeriodSerializer(period).data, status=201 if created else 200)


class KPIDomainViewSet(viewsets.ModelViewSet):
    queryset = KPIDomain.objects.all()
    serializer_class = KPIDomainSerializer
    permission_classes = [IsAdminOrReadOnly]


class KPIGroupViewSet(viewsets.ModelViewSet):
    queryset = KPIGroup.objects.select_related('domain').all()
    serializer_class = KPIGroupSerializer
    permission_classes = [IsAdminOrReadOnly]


class IndicatorThresholdViewSet(viewsets.ModelViewSet):
    queryset = IndicatorThreshold.objects.all()
    serializer_class = IndicatorThresholdSerializer
    permission_classes = [IsAdminOrReadOnly]


class KPIViewSet(viewsets.ModelViewSet):
    """Admin manages the indicator catalogue itself (name, weight, domain,
    group, retire/restore). KPIResult (below) is where Regional Managers do
    their day-to-day work."""
    queryset = KPI.objects.select_related('domain', 'group').all()
    serializer_class = KPISerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('active_only') == 'true':
            qs = qs.filter(is_retired=False)
        return qs

    def perform_create(self, serializer):
        kpi = serializer.save(is_custom=True, created_by=self.request.user)
        log_activity(f'Nouvel indicateur créé : « {kpi.name} » ({kpi.domain.name} · {kpi.group.name})', self.request.user)
        # Seed a KPIResult row for every existing (period × region) so the
        # new indicator immediately has somewhere to store data.
        rows = [
            KPIResult(kpi=kpi, period=p, region=r, realisation=0, objectif=100)
            for p in Period.objects.all() for r in Region.objects.all()
        ]
        KPIResult.objects.bulk_create(rows, ignore_conflicts=True)

    @action(detail=True, methods=['post'])
    def retire(self, request, pk=None):
        kpi = self.get_object()
        kpi.is_retired = True
        kpi.save()
        log_activity(f'Indicateur retiré : « {kpi.name} »', request.user)
        return Response(KPISerializer(kpi).data)

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        kpi = self.get_object()
        kpi.is_retired = False
        kpi.save()
        log_activity(f'Indicateur restauré : « {kpi.name} »', request.user)
        return Response(KPISerializer(kpi).data)


class KPIResultViewSet(viewsets.ModelViewSet):
    """This is the KPIResult CRUD surface: Regional Managers edit
    realisation/objectif/comment/validation for their KPIs here; Admins can
    too; Viewers get read-only access."""
    queryset = KPIResult.objects.select_related('kpi', 'kpi__domain', 'kpi__group', 'period', 'region').all()
    serializer_class = KPIResultSerializer
    permission_classes = [IsManagerOrAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        period = self.request.query_params.get('period')
        region = self.request.query_params.get('region')
        active_only = self.request.query_params.get('active_only')
        if period:
            qs = qs.filter(period_id=period)
        if region:
            qs = qs.filter(region__name=region)
        if active_only == 'true':
            qs = qs.filter(kpi__is_retired=False)
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx

    def perform_update(self, serializer):
        result = serializer.save()
        log_activity(
            f'Réalisation mise à jour : « {result.kpi.name} » → {result.realisation} '
            f'({result.period.label} · {result.region.name})',
            self.request.user,
        )


class KPIPlanViewSet(viewsets.ModelViewSet):
    """Bulk-apply an objective across several months × several sites at
    once. Applying a plan writes/overwrites the .objectif field on every
    matching KPIResult row (creating it first if it doesn't exist yet)."""
    queryset = KPIPlan.objects.prefetch_related('periods', 'regions').select_related('kpi').all()
    serializer_class = KPIPlanSerializer
    permission_classes = [IsAdmin]

    def perform_create(self, serializer):
        plan = serializer.save(created_by=self.request.user)
        for period in plan.periods.all():
            for region in plan.regions.all():
                KPIResult.objects.update_or_create(
                    kpi=plan.kpi, period=period, region=region,
                    defaults={'objectif': plan.target},
                )
        log_activity(
            f'Objectif planifié : « {plan.kpi.name} » → {plan.target} '
            f'({plan.periods.count()} mois × {plan.regions.count()} site(s))',
            self.request.user,
        )

    def perform_destroy(self, instance):
        # Clearing the plan does not retroactively wipe the objectif values
        # it set — same behaviour as removing a plan in the frontend only
        # detaches the plan record, the KPIResult rows are left as-is here
        # to avoid silently corrupting since-edited data.
        instance.delete()


class ActivityLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ActivityLog.objects.all()[:30]
    serializer_class = ActivityLogSerializer
    permission_classes = [IsAuthenticated]


class ScoreSnapshotViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ScoreSnapshot.objects.all()
    serializer_class = ScoreSnapshotSerializer
    permission_classes = [IsAuthenticated]


# ---------------------------------------------------------------------
# Dashboard aggregation — everything Vue d'ensemble / Historique need in
# one call each, computed server-side from live KPIResult rows.
# ---------------------------------------------------------------------
def _kpi_row_view(result):
    return {
        'kpi_id': result.kpi_id,
        'domain': result.kpi.domain.name,
        'group': result.kpi.group.name,
        'name': result.kpi.name,
        'weight': result.kpi.weight,
        'realisation': result.realisation,
        'objectif': result.objectif,
        'taux': taux_pct(result.objectif, result.realisation),
        'score': score(result.kpi.weight, result.objectif, result.realisation),
        'statut': statut(result.kpi, result.objectif, result.realisation),
        'statut_label': STATUT_LABELS[statut(result.kpi, result.objectif, result.realisation)],
        'comment': result.comment,
        'validation': result.validation,
    }


class OverviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period = _period_for(request)
        region = _region_for(request)
        if not period or not region:
            return Response({'detail': 'Aucune période ou région disponible.'}, status=400)

        results = (
            KPIResult.objects.select_related('kpi', 'kpi__domain', 'kpi__group')
            .filter(period=period, region=region, kpi__is_retired=False)
        )
        rows = [_kpi_row_view(r) for r in results]

        red = sum(1 for r in rows if r['statut'] == 'red')
        orange = sum(1 for r in rows if r['statut'] == 'orange')
        green = sum(1 for r in rows if r['statut'] == 'green')
        global_score = round(sum(r['realisation'] for r in rows) / len(rows), 1) if rows else 0

        domains = {}
        for r in rows:
            domains.setdefault(r['domain'], []).append(r['realisation'])
        domain_scores = [
            {'domain': d, 'avg': round(sum(vals) / len(vals), 1), 'count': len(vals)}
            for d, vals in domains.items()
        ]

        top5 = sorted(rows, key=lambda r: r['taux'], reverse=True)[:5]
        bottom5 = sorted(rows, key=lambda r: r['taux'])[:5]

        validated = sum(1 for r in rows if r['validation'] == 'validated')

        return Response({
            'period': PeriodSerializer(period).data,
            'region': RegionSerializer(region).data,
            'stats': {'total': len(rows), 'red': red, 'orange': orange, 'green': green, 'global_score': global_score},
            'domain_scores': domain_scores,
            'kpis': rows,
            'top_performing': top5,
            'lowest_performing': bottom5,
            'validation': {'validated': validated, 'pending': len(rows) - validated, 'total': len(rows)},
            'recent_activity': ActivityLogSerializer(ActivityLog.objects.all()[:6], many=True).data,
        })


class HistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        region = _region_for(request)
        mode = request.query_params.get('mode', 'monthly')  # 'monthly' | 'yearly'
        periods = list(Period.objects.order_by('order'))
        domains = list(KPIDomain.objects.values_list('name', flat=True))

        def score_at(period):
            vals = list(
                KPIResult.objects.filter(period=period, region=region, kpi__is_retired=False)
                .values_list('realisation', flat=True)
            )
            return round(sum(vals) / len(vals), 1) if vals else 0

        def domain_score_at(period, domain_name):
            vals = list(
                KPIResult.objects.filter(
                    period=period, region=region, kpi__is_retired=False, kpi__domain__name=domain_name
                ).values_list('realisation', flat=True)
            )
            return round(sum(vals) / len(vals), 1) if vals else None

        if mode == 'yearly':
            years = sorted({p.year for p in periods})
            score_series = {'labels': [str(y) for y in years], 'values': []}
            for y in years:
                yp = [p for p in periods if p.year == y]
                vals = [score_at(p) for p in yp]
                score_series['values'].append(round(sum(vals) / len(vals), 1) if vals else 0)
            domain_series = {}
            for d in domains:
                values = []
                for y in years:
                    yp = [p for p in periods if p.year == y]
                    vals = [v for v in (domain_score_at(p, d) for p in yp) if v is not None]
                    values.append(round(sum(vals) / len(vals), 1) if vals else 0)
                domain_series[d] = {'labels': [str(y) for y in years], 'values': values}
        else:
            labels = [p.label for p in periods]
            score_series = {'labels': labels, 'values': [score_at(p) for p in periods]}
            domain_series = {
                d: {'labels': labels, 'values': [domain_score_at(p, d) or 0 for p in periods]}
                for d in domains
            }

        return Response({'score_series': score_series, 'domain_series': domain_series})


# ---------------------------------------------------------------------
# Export / Import
# ---------------------------------------------------------------------
EXPORT_FIELDS = ['Domaine', 'Sous-groupe', 'Indicateur', 'Poids (%)', 'Objectif', 'Réalisation', 'Taux (%)', 'Score', 'Statut', 'Commentaire', 'Validation']


def _export_rows(period, region):
    results = (
        KPIResult.objects.select_related('kpi', 'kpi__domain', 'kpi__group')
        .filter(period=period, region=region, kpi__is_retired=False)
    )
    rows = []
    for r in results:
        st = statut(r.kpi, r.objectif, r.realisation)
        rows.append({
            'Domaine': r.kpi.domain.name, 'Sous-groupe': r.kpi.group.name, 'Indicateur': r.kpi.name,
            'Poids (%)': r.kpi.weight, 'Objectif': r.objectif, 'Réalisation': r.realisation,
            'Taux (%)': taux_pct(r.objectif, r.realisation), 'Score': score(r.kpi.weight, r.objectif, r.realisation),
            'Statut': STATUT_LABELS[st],
            'Commentaire': r.comment, 'Validation': 'Validé' if r.validation == 'validated' else 'En attente',
        })
    return rows


class ExportCSVView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period = _period_for(request)
        region = _region_for(request)
        rows = _export_rows(period, region)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=EXPORT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        response = Response(buf.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="objectifs_{period.label}_{region.name}.csv"'
        return response


class ExportJSONView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period = _period_for(request)
        region = _region_for(request)
        rows = _export_rows(period, region)
        response = Response(rows)
        response['Content-Disposition'] = f'attachment; filename="objectifs_{period.label}_{region.name}.json"'
        return response


def _find_column(row, candidates):
    lower_map = {str(k).strip().lower(): v for k, v in row.items()}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


def _parse_number(v):
    if v is None or v == '':
        return None
    try:
        return float(str(v).replace(',', '.').replace('%', '').strip())
    except ValueError:
        return None


class ImportView(APIView):
    """Accepts a CSV file. Rows matching an existing KPI (by name) update
    its KPIResult for the given period/region; unmatched names are
    registered as brand-new indicators automatically."""
    permission_classes = [IsManagerOrAdmin]
    parser_classes = [MultiPartParser]

    @transaction.atomic
    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'detail': 'Aucun fichier fourni.'}, status=400)
        period = _period_for(request)
        region = _region_for(request)
        if not period or not region:
            return Response({'detail': 'Période ou région invalide.'}, status=400)

        try:
            text = file.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            return Response({'detail': "Impossible de lire ce fichier — utilisez un CSV encodé en UTF-8, ou exportez d'abord depuis l'app."}, status=400)

        reader = csv.DictReader(io.StringIO(text))
        updated, created, skipped = 0, 0, 0
        seen_in_batch = {}

        for row in reader:
            name = (_find_column(row, ['Indicateur', 'Name', 'KPI']) or '').strip()
            value = _parse_number(_find_column(row, ['Réalisation', 'Realisation', 'Value', 'Valeur']))
            target = _parse_number(_find_column(row, ['Objectif', 'Objectif (%)', 'Target']))
            domain_name = (_find_column(row, ['Domaine', 'Domain']) or 'Commercial').strip() or 'Commercial'
            group_name = (_find_column(row, ['Sous-groupe', 'Sous groupe', 'Group']) or 'Import').strip() or 'Import'
            weight = _parse_number(_find_column(row, ['Poids', 'Poids (%)', 'Weight']))

            if not name or value is None:
                skipped += 1
                continue

            key = name.strip().lower()
            # Match by name regardless of retired status: importing real
            # data for an indicator that was hidden by "Réinitialiser les
            # données" should revive it with the new value, not spawn a
            # confusing duplicate with the same name.
            kpi = seen_in_batch.get(key) or KPI.objects.filter(name__iexact=name).first()

            if kpi:
                if kpi.is_retired:
                    kpi.is_retired = False
                    kpi.save(update_fields=['is_retired'])
                KPIResult.objects.update_or_create(
                    kpi=kpi, period=period, region=region,
                    defaults={
                        'realisation': value,
                        **({'objectif': target} if target is not None else {}),
                        'updated_by': request.user,
                    },
                )
                updated += 1
            else:
                domain, _ = KPIDomain.objects.get_or_create(name=domain_name)
                group, _ = KPIGroup.objects.get_or_create(domain=domain, name=group_name)
                kpi = KPI.objects.create(
                    domain=domain, group=group, name=name, weight=weight or 1,
                    is_custom=True, created_by=request.user,
                )
                seen_in_batch[key] = kpi
                for p in Period.objects.all():
                    for r in Region.objects.all():
                        KPIResult.objects.get_or_create(
                            kpi=kpi, period=p, region=r,
                            defaults={'realisation': 0, 'objectif': 100},
                        )
                KPIResult.objects.filter(kpi=kpi, period=period, region=region).update(
                    realisation=value, objectif=target if target is not None else 100, updated_by=request.user,
                )
                created += 1

        if updated or created:
            log_activity(f'Import : {updated} mise(s) à jour, {created} créé(s), {skipped} ignorée(s)', request.user)

        return Response({'updated': updated, 'created': created, 'skipped': skipped, 'total': updated + created + skipped})


class ResetDataView(APIView):
    """Hides every indicator (retire, same mechanism as the manual
    Retirer button) and wipes overrides/plans/activity — leaves user
    accounts completely untouched. Mirrors the frontend's clearAllData()."""
    permission_classes = [IsAdmin]

    @transaction.atomic
    def post(self, request):
        KPI.objects.update(is_retired=True)
        KPIResult.objects.update(realisation=0, objectif=100, comment='', validation=KPIResult.Validation.PENDING)
        KPIPlan.objects.all().delete()
        ActivityLog.objects.all().delete()
        log_activity('Toutes les données ont été réinitialisées.', request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
