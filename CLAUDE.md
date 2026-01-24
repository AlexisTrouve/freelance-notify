# Claude Code - Freelance Notify

## Project Overview

Bot de veille multi-plateforme freelance avec scoring IA et notifications Discord.

**Plateformes supportées :**
- Codeur.com (scraper.py) - Production, serveur
- Upwork (upwork_adapter.py) - Local seulement

## Architecture

```
freelance-notify/
├── scraper.py              # Scraper Codeur.com (RSS)
├── upwork_adapter.py       # Wrapper Upwork (Playwright)
├── config.json             # Config (secrets - non versionné)
├── files/
│   ├── profile.md          # Profil freelancer
│   ├── skill_stats.json    # Stats rolling 30j
│   └── keywords/
│       ├── skills_index.json         # Skills avec scores/poids
│       ├── tech_keywords_detector.json
│       └── *.md                      # Profils détaillés par skill
├── adapters/
│   └── upwork/             # Git submodule (ne pas modifier)
└── seen_*.json             # Jobs déjà traités
```

## Key Concepts

### Système de Skills
- Chaque skill a un **score** (0-10) et un **poids** (-10 à +20)
- Le poids total détermine si on appelle l'IA
- Skills négatifs (score=0, poids=-10) pénalisent les jobs

### Profil Dynamique
- Le profil envoyé à Haiku est assemblé dynamiquement
- Base profile + skills matchés = contexte pertinent
- Économise des tokens, meilleur scoring

### Stats Rolling
- Données stockées par jour
- Cleanup auto > 30 jours
- Tendances 7j vs 7j précédents

## Commands

```bash
# Codeur.com
python scraper.py                    # Run normal
python scraper.py --dry-run          # Test
python scraper.py --debug            # Matching détaillé
python scraper.py --stats            # Voir stats
python scraper.py --weekly-report    # Rapport Discord

# Upwork
python upwork_adapter.py --query "python" --num-jobs 20
python upwork_adapter.py --dry-run
```

## Deployment

**Serveur (Codeur.com seulement) :**
- IP: 57.131.33.10
- User: debian
- Path: /home/debian/codeur-notify

```bash
scp scraper.py debian@57.131.33.10:/home/debian/codeur-notify/
scp files/keywords/*.json debian@57.131.33.10:/home/debian/codeur-notify/files/keywords/
```

**Crons serveur :**
```
*/30 * * * * scraper.py              # Scraping
0 9 * * 1    scraper.py --weekly-report  # Rapport lundi
```

## Important Notes

1. **Ne pas modifier `adapters/upwork/`** - C'est un submodule, pull les updates avec `git submodule update`

2. **config.json contient des secrets** - Jamais versionné, utiliser config.example.json

3. **Upwork = local seulement** - Nécessite session Firefox, ne tourne pas sur serveur

4. **Skills index = source de vérité** - Modifier `files/keywords/skills_index.json` pour ajuster le scoring

5. **Keywords bilingues** - FR + EN dans skills_index.json

## Adding a New Skill

1. Créer `files/keywords/new_skill.md` avec description
2. Ajouter dans `files/keywords/skills_index.json`:
```json
"new_skill": {
  "score": 7,
  "weight": 7,
  "keywords": ["keyword1", "keyword2"],
  "profile_file": "new_skill.md"
}
```
3. Déployer sur serveur

## Testing

```bash
# Test Codeur.com
python scraper.py --debug --no-jitter

# Test Upwork (dry-run)
python upwork_adapter.py --query "test" --dry-run

# Voir les stats
python scraper.py --stats
```

## Git Workflow

```bash
# Update Upwork submodule
cd adapters/upwork && git pull origin main && cd ../..
git add adapters/upwork
git commit -m "Update Upwork submodule"

# Deploy to server after changes
git push
scp scraper.py debian@57.131.33.10:/home/debian/codeur-notify/
```
