from django.db import models


class Region(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Period(models.Model):
    label = models.CharField(max_length=50, unique=True)
    month = models.PositiveSmallIntegerField()
    year = models.PositiveIntegerField()
    order = models.PositiveIntegerField(unique=True)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return self.label


class KPIDomain(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class KPIGroup(models.Model):
    domain = models.ForeignKey(KPIDomain, on_delete=models.CASCADE, related_name='groups')
    name = models.CharField(max_length=100)

    class Meta:
        unique_together = ['domain', 'name']
        ordering = ['domain__name', 'name']

    def __str__(self):
        return f'{self.domain.name} · {self.name}'


class KPI(models.Model):
    domain = models.ForeignKey(KPIDomain, on_delete=models.CASCADE, related_name='kpis')
    group = models.ForeignKey(KPIGroup, on_delete=models.CASCADE, related_name='kpis')
    name = models.CharField(max_length=200)
    unit = models.CharField(max_length=10, default='%')
    weight = models.FloatField(default=1)
    is_custom = models.BooleanField(default=False)
    is_retired = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='created_kpis'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['domain', 'group', 'name']
        ordering = ['domain__name', 'group__name', 'name']

    def __str__(self):
        return self.name


class KPIResult(models.Model):
    """A single realised value for one (KPI, Period, Region) combination —
    this is the true per-region store the API exposes; it's the analogue of
    the frontend's REGION_FACTOR-adjusted values, done properly server-side."""

    class Validation(models.TextChoices):
        PENDING = 'pending', 'En attente'
        VALIDATED = 'validated', 'Validé'

    kpi = models.ForeignKey(KPI, on_delete=models.CASCADE, related_name='results')
    period = models.ForeignKey(Period, on_delete=models.CASCADE, related_name='results')
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='results')
    realisation = models.FloatField(default=0)
    objectif = models.FloatField(default=100)
    comment = models.TextField(blank=True, default='')
    validation = models.CharField(max_length=20, choices=Validation.choices, default=Validation.PENDING)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        'accounts.User', null=True, blank=True, on_delete=models.SET_NULL, related_name='updated_results'
    )

    class Meta:
        unique_together = ['kpi', 'period', 'region']

    def __str__(self):
        return f'{self.kpi.name} · {self.period.label} · {self.region.name}'


class IndicatorThreshold(models.Model):
    """kpi=None represents the global default threshold applied to every
    indicator that doesn't have its own override."""
    kpi = models.OneToOneField(KPI, null=True, blank=True, on_delete=models.CASCADE, related_name='threshold')
    green_min = models.FloatField(default=100)
    orange_min = models.FloatField(default=80)
    label = models.CharField(max_length=100, blank=True, default='')

    def __str__(self):
        return self.label or (self.kpi.name if self.kpi else 'Seuils par défaut')


class KPIPlan(models.Model):
    """A bulk objective planned across several months × several sites at
    once, from the 'Gestion des indicateurs' screen."""
    kpi = models.ForeignKey(KPI, on_delete=models.CASCADE, related_name='plans')
    target = models.FloatField()
    periods = models.ManyToManyField(Period, related_name='plans')
    regions = models.ManyToManyField(Region, related_name='plans')
    created_by = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class ActivityLog(models.Model):
    text = models.CharField(max_length=500)
    user = models.ForeignKey('accounts.User', null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.text


class ScoreSnapshot(models.Model):
    period = models.ForeignKey(Period, on_delete=models.CASCADE, related_name='snapshots')
    region = models.ForeignKey(Region, on_delete=models.CASCADE, related_name='snapshots')
    global_score = models.FloatField()
    commercial_score = models.FloatField(null=True, blank=True)
    technique_score = models.FloatField(null=True, blank=True)
    strategique_score = models.FloatField(null=True, blank=True)
    financier_score = models.FloatField(null=True, blank=True)
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['period', 'region']
