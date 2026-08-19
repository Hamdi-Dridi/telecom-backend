"""
Scoring engine shared by every serializer/view that needs to compute
Taux de réalisation, Score, or Statut from a KPIResult.

Business rules (mirrors the frontend exactly):
    Taux de réalisation = Réalisation / Objectif
    Score               = Poids × Taux de réalisation
    Statut               = red   if Taux < Objectif × (orange_min/100)
                            orange if Taux < Objectif × (green_min/100)
                            green  otherwise
"""
from .models import IndicatorThreshold


def taux_ratio(objectif, realisation):
    if not objectif:
        return 0.0
    return realisation / objectif


def taux_pct(objectif, realisation):
    return round(taux_ratio(objectif, realisation) * 1000) / 10


def score(weight, objectif, realisation):
    return round(taux_ratio(objectif, realisation) * weight * 10) / 10


def default_threshold():
    th = IndicatorThreshold.objects.filter(kpi__isnull=True).first()
    if th:
        return th
    return IndicatorThreshold(kpi=None, green_min=100, orange_min=80, label='Seuils par défaut')


def threshold_for(kpi):
    th = IndicatorThreshold.objects.filter(kpi=kpi).first()
    return th or default_threshold()


def statut(kpi, objectif, realisation):
    th = threshold_for(kpi)
    orange_cut = objectif * (th.orange_min / 100)
    green_cut = objectif * (th.green_min / 100)
    if realisation < orange_cut:
        return 'red'
    if realisation < green_cut:
        return 'orange'
    return 'green'


STATUT_LABELS = {'red': 'Sous objectif', 'orange': 'En approche', 'green': 'Atteint'}
