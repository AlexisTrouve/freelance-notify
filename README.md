# Freelance Notify

Bot de surveillance automatique des plateformes freelance avec notifications Discord et scoring IA.

Actuellement supporté : **Codeur.com**

Roadmap : Malt, Upwork, Freelance.com (voir [TODO.md](TODO.md))

## Features

- **Scraping RSS** - Surveillance automatique des nouveaux projets
- **Filtrage intelligent** - Par mots-clés, budget, catégories
- **Scoring IA** - Évaluation automatique avec Claude Haiku 4.5
- **Profil dynamique** - Assemblage de profil basé sur les skills matchés
- **Système de poids** - Pré-filtrage avant appel IA (économise des tokens)
- **Skills négatifs** - Pénaliser les technos non désirées
- **Statistiques rolling** - Analyse du marché sur 30 jours
- **Rapport hebdomadaire** - Résumé Discord automatique chaque lundi
- **Anti-détection** - User-agents réalistes, jitter, délais aléatoires

## Architecture

```
freelance-notify/
├── scraper.py              # Script principal
├── config.json             # Configuration (non versionné)
├── config.example.json     # Template de configuration
├── requirements.txt        # Dépendances Python
├── files/
│   ├── profile.md          # Profil freelancer de base
│   ├── skill_stats.json    # Statistiques rolling 30j
│   └── keywords/
│       ├── skills_index.json         # Index des skills avec scores/poids
│       ├── tech_keywords_detector.json # Détection de technos inconnues
│       ├── vba.md                     # Profil skill VBA
│       ├── python.md                  # Profil skill Python
│       └── ...                        # Autres profils skills
├── seen_projects.json      # IDs des projets déjà traités
└── cron.log               # Logs d'exécution
```

## Installation

### 1. Cloner le repo

```bash
git clone https://github.com/YOUR_USERNAME/freelance-notify.git
cd freelance-notify
```

### 2. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 3. Configurer

```bash
cp config.example.json config.json
nano config.json
```

Modifier :
- `discord_webhook_url` : Webhook Discord
- `anthropic_api_key` : Clé API Anthropic (pour scoring IA)
- `filters.keywords` : Mots-clés à surveiller

### 4. Créer le profil freelancer

```bash
nano files/profile.md
```

Décrire ton profil, compétences, expérience.

### 5. Tester

```bash
# Dry run (sans notifications)
python scraper.py --dry-run --no-jitter

# Debug (voir le matching détaillé)
python scraper.py --debug --no-jitter

# Stats
python scraper.py --stats
```

## Configuration

### config.json

```json
{
  "discord_webhook_url": "https://discord.com/api/webhooks/...",
  "anthropic_api_key": "sk-ant-api03-...",
  "check_interval_minutes": 30,
  "stealth": {
    "enabled": true,
    "jitter_minutes": 5,
    "min_delay_seconds": 1,
    "max_delay_seconds": 3
  },
  "ai_scoring": {
    "enabled": true,
    "min_score": 5,
    "min_weight": 5,
    "model": "claude-haiku-4-5-20251001"
  },
  "profile_file": "files/profile.md",
  "filters": {
    "keywords": ["python", "api", "vba", "excel"],
    "exclude_keywords": ["wordpress"],
    "min_budget": 100,
    "max_budget": null
  },
  "max_projects_per_notification": 10,
  "seen_projects_file": "seen_projects.json"
}
```

### Options

| Option | Description |
|--------|-------------|
| `stealth.enabled` | Activer les mesures anti-détection |
| `stealth.jitter_minutes` | Variation aléatoire au démarrage (0-N min) |
| `ai_scoring.enabled` | Activer le scoring IA |
| `ai_scoring.min_score` | Score minimum pour notifier (1-10) |
| `ai_scoring.min_weight` | Poids minimum pour appeler l'IA |
| `filters.keywords` | Au moins un doit matcher |
| `filters.exclude_keywords` | Exclure si présent |

## Système de Skills

### Principe

Chaque skill a :
- **Score** (0-10) : Ton niveau de compétence/intérêt
- **Poids** : Points calculés selon le score
- **Keywords** : Mots-clés qui déclenchent le match
- **Profil** : Description détaillée (fichier .md)

### Table des poids

| Score | Poids | Interprétation |
|-------|-------|----------------|
| 0 | -10 | Skill négatif (éviter) |
| 1-3 | -5 à -1 | Faible intérêt |
| 4-5 | 0 à +2 | Neutre |
| 6-7 | +4 à +7 | Bon |
| 8-10 | +12 à +20 | Excellent |

### Ajouter un skill

1. Créer le fichier profil :
```bash
nano files/keywords/nouveau_skill.md
```

2. Ajouter dans `files/keywords/skills_index.json` :
```json
"nouveau_skill": {
  "score": 8,
  "weight": 12,
  "keywords": ["keyword1", "keyword2"],
  "profile_file": "nouveau_skill.md"
}
```

### Skills négatifs

Pour pénaliser certaines technos :
```json
"php": {
  "score": 0,
  "weight": -10,
  "keywords": ["php", "laravel", "symfony"],
  "profile_file": "php.md"
}
```

## Commandes

```bash
# Run normal (avec jitter)
python scraper.py

# Dry run (test sans notifs)
python scraper.py --dry-run --no-jitter

# Debug (matching détaillé par job)
python scraper.py --debug --no-jitter

# Afficher les statistiques
python scraper.py --stats

# Envoyer le rapport hebdo Discord
python scraper.py --weekly-report --no-jitter
```

## Statistiques

Le bot collecte automatiquement des stats sur le marché :

- **Skills connus** : Fréquence de chaque skill dans les jobs
- **Tendances** : Comparaison 7j vs 7j précédents
- **Keywords inconnus** : Technos détectées mais non indexées
- **Rolling 30 jours** : Nettoyage automatique des vieilles données

### Consulter les stats

```bash
python scraper.py --stats
```

Output :
```
===========================================================================
  STATISTIQUES DES SKILLS - Codeur.com (Rolling 30 jours)
===========================================================================

  Jobs analyses: 450 (30j) | 120 (7j) | 98 (7j precedents)

  SKILLS CONNUS (30 jours):
  Skill              30j     7j    Trend   Prev 7j
  -----------------------------------------------------------------------
    python             45     15     +25%        12
    api                32     10     -10%        11
    ecommerce          28      8      NEW         0
```

## Cron Setup

### Scraping toutes les 30 minutes

```bash
crontab -e
```

```cron
*/30 * * * * cd /path/to/freelance-notify && /usr/bin/python3 scraper.py >> cron.log 2>&1
```

### Rapport hebdomadaire (lundi 9h)

```cron
0 9 * * 1 cd /path/to/freelance-notify && /usr/bin/python3 scraper.py --weekly-report --no-jitter >> cron.log 2>&1
```

## Discord Webhook

1. Paramètres du channel Discord
2. Intégrations > Webhooks > Nouveau Webhook
3. Copier l'URL
4. Coller dans `config.json`

### Notifications

- **Projets** : Embed avec titre, budget, score IA, skills matchés
- **Rapport hebdo** : Résumé des tendances, top skills, keywords à indexer

## Déploiement

### Serveur actuel

- **IP** : `57.131.33.10`
- **User** : `debian`
- **Path** : `/home/debian/freelance-notify`

### Déployer les changements

```bash
scp scraper.py debian@57.131.33.10:/home/debian/freelance-notify/
scp files/keywords/*.json debian@57.131.33.10:/home/debian/freelance-notify/files/keywords/
```

## Logs

```bash
# Voir les derniers logs
tail -f cron.log

# Logs du jour
grep "$(date +%Y-%m-%d)" cron.log
```

## Troubleshooting

### Pas de projets trouvés

- Vérifier les keywords dans `config.json`
- Tester avec `--debug` pour voir le matching

### Score IA toujours bas

- Vérifier que `files/profile.md` est bien rempli
- Ajuster les profils skills dans `files/keywords/*.md`

### Rate limiting Discord

- Discord limite à 30 requêtes/minute par webhook
- Le bot espace automatiquement les envois

## License

MIT
