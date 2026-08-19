# Telecom Performance Analytics — backend Django

API REST (Django + Django REST Framework) pour l'app React. Implémente les 10 entités
(Role, User, Region, Period, KPIDomain, KPIGroup, KPI, KPIResult, ScoreSnapshot,
IndicatorThreshold) en vraies tables relationnelles, avec les permissions par rôle :

- **Administrateur** : CRUD complet sur Users, Roles, Regions, Periods, KPIDomains,
  KPIGroups, KPIs, IndicatorThresholds.
- **Regional Manager** : CRUD sur KPIResult uniquement (réalisation, objectif,
  commentaire, validation) — c'est la page Objectifs.
- **Viewer** : lecture seule sur tout.

## ⚠️ Important — non testé en conditions réelles

Cet environnement n'a pas accès à internet pour `pip install django`, donc **je n'ai
pas pu lancer le serveur ni exécuter les tests moi-même** (contrairement à la version
React, que j'ai pu tester dans un vrai navigateur). Ce que j'ai fait à la place :

- Vérifié la syntaxe de **chaque fichier Python** (`py_compile`, zéro erreur).
- Relu chaque référence croisée entre modèles/serializers/vues à la main (noms de
  champs, `unique_together`, clés étrangères, permissions).

**Fais tourner `python manage.py check` et `python manage.py test` (si tu ajoutes des
tests) dès l'installation, avant de considérer que c'est prêt pour la prod.** C'est du
code neuf, pas encore éprouvé par une vraie exécution.

## Installation

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows : venv\Scripts\activate
pip install -r requirements.txt

python manage.py makemigrations accounts kpi
python manage.py migrate
python manage.py seed_data        # charge les 10 fichiers JSON dans la base

python manage.py runserver
```

L'API tourne sur `http://localhost:8000/api/`. Le compte admin de démo créé par
`seed_data` : `amine.derbali@exemple.tn` / `admin123`.

(Optionnel) Pour te créer un autre compte admin par la ligne de commande :
```bash
python manage.py createsuperuser
```

## Structure

```
backend/
├── manage.py
├── requirements.txt
├── telecom_analytics/       # settings, urls racine, wsgi/asgi
├── accounts/                 # Role, User (email comme identifiant), permissions par rôle
│   ├── models.py
│   ├── serializers.py
│   ├── views.py              # signup/login/logout/me + CRUD utilisateurs (admin)
│   ├── permissions.py        # IsAdmin, IsAdminOrReadOnly, IsManagerOrAdmin
│   └── urls.py
└── kpi/                      # les 9 autres entités + moteur de scoring
    ├── models.py              # Region, Period, KPIDomain, KPIGroup, KPI, KPIResult,
    │                            IndicatorThreshold, KPIPlan, ActivityLog, ScoreSnapshot
    ├── scoring.py             # Taux = Réalisation/Objectif, Score = Poids × Taux, Statut
    ├── serializers.py
    ├── views.py               # CRUD viewsets + agrégations Vue d'ensemble/Historique + import/export/reset
    ├── urls.py
    ├── fixtures/*.json        # les mêmes 10 fichiers JSON que la version React
    └── management/commands/seed_data.py
```

## Authentification

Token simple (DRF `TokenAuthentication`) — envoie `Authorization: Token <clé>` sur
chaque requête après connexion.

```bash
# Connexion
curl -X POST http://localhost:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"amine.derbali@exemple.tn","password":"admin123"}'
# → {"token": "...", "user": {...}}

# Inscription (statut "pending" jusqu'à approbation par un admin)
curl -X POST http://localhost:8000/api/auth/signup/ \
  -H "Content-Type: application/json" \
  -d '{"first_name":"Test","last_name":"User","email":"test@exemple.tn","password":"secret123","region":"Grand Tunis"}'

# Profil courant
curl http://localhost:8000/api/auth/me/ -H "Authorization: Token <clé>"

# Déconnexion (invalide le token)
curl -X POST http://localhost:8000/api/auth/logout/ -H "Authorization: Token <clé>"
```

## Endpoints principaux

| Méthode | URL | Rôle requis | Description |
|---|---|---|---|
| GET/POST | `/api/users/` | Admin | Liste / création directe |
| POST | `/api/users/{id}/approve/` | Admin | Approuve une demande, attribue un rôle |
| POST | `/api/users/{id}/reject/` | Admin | Refuse une demande (supprime) |
| POST | `/api/users/{id}/toggle_suspend/` | Admin | Suspend / réactive |
| GET | `/api/roles/` | Tous | Liste des rôles |
| GET/POST/PATCH/DELETE | `/api/regions/`, `/api/periods/`, `/api/domains/`, `/api/groups/`, `/api/thresholds/` | Admin en écriture, tous en lecture | CRUD |
| POST | `/api/periods/add_next/` | Admin | Ajoute le mois suivant au calendrier glissant |
| GET/POST/PATCH/DELETE | `/api/kpis/` | Admin en écriture, tous en lecture | Catalogue des indicateurs |
| POST | `/api/kpis/{id}/retire/` `/restore/` | Admin | Retirer / restaurer |
| GET/PATCH | `/api/kpi-results/?period=<id>&region=<name>` | Manager+Admin en écriture, tous en lecture | Page Objectifs — Poids/Objectif/Réalisation/Taux/Score calculés à la volée |
| GET/POST/DELETE | `/api/plans/` | Admin | Planifier un objectif sur plusieurs mois × sites |
| GET | `/api/dashboard/overview/?period=<id>&region=<name>` | Tous | Tout ce qu'il faut pour Vue d'ensemble en un appel |
| GET | `/api/dashboard/history/?region=<name>&mode=monthly\|yearly` | Tous | Séries pour Historique |
| GET | `/api/export/csv/`, `/api/export/json/` | Tous | Export |
| POST | `/api/import/` (multipart, champ `file`) | Manager+Admin | Import CSV — met à jour les indicateurs connus, **enregistre automatiquement les noms inconnus comme nouveaux indicateurs** |
| POST | `/api/reset/` | Admin | Retire tous les indicateurs et vide les données (comptes utilisateurs non touchés) |

Toutes les vues de listing/detail suivent les conventions standard de DRF
(`ModelViewSet` → GET liste, POST création, GET/PATCH/DELETE détail par id).

## Notes de conception

- **KPIResult est vraiment par région** (contrairement à la version React qui simule
  ça côté client avec un facteur régional) — chaque `(KPI, Period, Region)` a sa
  propre ligne en base, donc un Regional Manager qui modifie sa région n'affecte
  jamais les autres régions. C'est la modélisation correcte, permise ici parce
  qu'un vrai backend peut stocker `N × périodes × régions` lignes sans que ça
  pèse sur le bundle JS envoyé au navigateur.
- **Import CSV** : mêmes règles que côté React — un nom d'indicateur déjà connu
  met à jour sa ligne KPIResult ; un nom inconnu crée un nouveau KPI (avec
  Domaine/Sous-groupe/Poids si les colonnes sont présentes) et ses lignes
  KPIResult pour toutes les périodes × régions existantes.
- **Reset** retire (masque) tous les indicateurs au lieu de les supprimer — même
  logique que le bouton "Réinitialiser les données" côté React.
