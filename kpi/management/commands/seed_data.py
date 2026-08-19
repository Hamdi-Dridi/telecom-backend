import json
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Role, User
from kpi.models import IndicatorThreshold, KPI, KPIDomain, KPIGroup, KPIResult, Period, Region, ScoreSnapshot

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / 'fixtures'


def _load(name):
    with open(FIXTURES_DIR / name, encoding='utf-8') as f:
        return json.load(f)


class Command(BaseCommand):
    help = (
        'Loads seed data from kpi/fixtures/*.json into the database. Safe to '
        're-run — existing rows are matched by their natural key and updated '
        'in place.\n\n'
        'By default loads everything, including demo indicators and sample '
        'values (roles, users, regions, periods, domains, groups, kpis, '
        'kpi_results, score_snapshots, indicator_thresholds).\n\n'
        'Pass --minimal to load only the structural/required data — roles, '
        'regions, periods, domains, groups, and the admin account — with NO '
        'demo indicators or sample values. Use this when you want to start '
        'from a clean dashboard and add your own KPIs via Excel/CSV import '
        'or manually in the app.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--minimal', action='store_true',
            help='Skip demo KPIs, KPI results, thresholds, and score snapshots — real-data setup.',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        minimal = options['minimal']

        self.stdout.write('Loading roles…')
        for r in _load('roles.json'):
            Role.objects.update_or_create(
                key=r['key'], defaults={'name': r['name'], 'description': r.get('description', ''), 'permissions': r.get('permissions', [])}
            )

        self.stdout.write('Loading regions…')
        region_by_id = {}
        for r in _load('regions.json'):
            obj, _ = Region.objects.update_or_create(name=r['name'])
            region_by_id[r['id']] = obj

        self.stdout.write('Loading periods…')
        period_by_id = {}
        for p in _load('periods.json'):
            obj, _ = Period.objects.update_or_create(
                label=p['label'], defaults={'month': p['month'], 'year': p['year'], 'order': p['order']}
            )
            period_by_id[p['id']] = obj

        self.stdout.write('Loading domains…')
        domain_by_id = {}
        for d in _load('domains.json'):
            obj, _ = KPIDomain.objects.update_or_create(name=d['name'])
            domain_by_id[d['id']] = obj

        self.stdout.write('Loading groups…')
        group_by_id = {}
        for g in _load('groups.json'):
            domain = domain_by_id[g['domainId']]
            obj, _ = KPIGroup.objects.update_or_create(domain=domain, name=g['name'])
            group_by_id[g['id']] = obj

        if minimal:
            self.stdout.write('--minimal: skipping demo KPIs, KPI results, thresholds, score snapshots.')
        else:
            self.stdout.write('Loading KPIs…')
            kpi_by_id = {}
            for k in _load('kpis.json'):
                domain = domain_by_id[k['domainId']]
                group = group_by_id[k['groupId']]
                obj, _ = KPI.objects.update_or_create(
                    domain=domain, group=group, name=k['name'],
                    defaults={'unit': k.get('unit', '%'), 'weight': k.get('weight', 1), 'is_retired': not k.get('active', True)},
                )
                kpi_by_id[k['id']] = obj

            self.stdout.write('Loading KPI results (one per KPI × period, applied to every region)…')
            count = 0
            for res in _load('kpi_results.json'):
                kpi = kpi_by_id[res['kpiId']]
                period = period_by_id[res['periodId']]
                for region in region_by_id.values():
                    KPIResult.objects.update_or_create(
                        kpi=kpi, period=period, region=region,
                        defaults={
                            'realisation': res['realisation'], 'objectif': res.get('objectif', 100),
                            'comment': res.get('comment', ''), 'validation': res.get('validation', 'pending'),
                        },
                    )
                    count += 1
            self.stdout.write(f'  {count} KPIResult rows.')

            self.stdout.write('Loading indicator thresholds…')
            for t in _load('indicator_thresholds.json'):
                IndicatorThreshold.objects.update_or_create(
                    kpi=None if t.get('kpiId') is None else kpi_by_id.get(t['kpiId']),
                    defaults={'green_min': t['greenMin'], 'orange_min': t['orangeMin'], 'label': t.get('label', '')},
                )

            self.stdout.write('Loading score snapshots…')
            for s in _load('score_snapshots.json'):
                ScoreSnapshot.objects.update_or_create(
                    period=period_by_id[s['periodId']], region=region_by_id[s['regionId']],
                    defaults={
                        'global_score': s['globalScore'], 'commercial_score': s.get('commercialScore'),
                        'technique_score': s.get('techniqueScore'), 'strategique_score': s.get('strategiqueScore'),
                        'financier_score': s.get('financierScore'),
                    },
                )

        self.stdout.write('Loading seed admin user…')
        for u in _load('users.json'):
            role = Role.objects.get(key='admin')
            region = region_by_id.get(u.get('regionId'))
            if not User.objects.filter(email__iexact=u['email']).exists():
                user = User(
                    email=u['email'], first_name=u['firstName'], last_name=u['lastName'],
                    role=role, region=region, status=User.Status.ACTIVE, is_staff=True, is_superuser=True,
                )
                user.set_password(u['password'])
                user.save()
                self.stdout.write(f"  Created {u['email']} / {u['password']}")
            else:
                self.stdout.write(f"  {u['email']} already exists, skipped.")

        self.stdout.write(self.style.SUCCESS('Seed data loaded successfully.'))
