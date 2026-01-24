# Upwork Adapter - Tutorial

Guide complet pour configurer et utiliser l'adapter Upwork avec Freelance Notify.

## Prérequis

- Python 3.10+
- Firefox installé
- Compte Upwork actif
- Config `config.json` déjà en place (Discord webhook, API key Anthropic)

## Installation

### 1. Initialiser le submodule

```bash
cd freelance-notify
git submodule update --init --recursive
```

### 2. Installer les dépendances

```bash
pip install -r requirements-upwork.txt
```

### 3. Installer Firefox pour Playwright

```bash
playwright install firefox
```

## Configuration Firefox

L'adapter Upwork nécessite une session Firefox authentifiée car Upwork bloque les bots.

### Trouver ton profil Firefox

```bash
# Windows
dir %APPDATA%\Mozilla\Firefox\Profiles\

# Linux/Mac
ls ~/.mozilla/firefox/
```

Tu verras quelque chose comme `abc123.default-release`.

### Se connecter à Upwork

1. Ouvre Firefox normalement
2. Va sur https://www.upwork.com
3. Connecte-toi à ton compte
4. **Important** : Coche "Remember me" / "Rester connecté"
5. Ferme Firefox

## Utilisation

### Scrape + Notification Discord

```bash
python upwork_adapter.py --query "python automation" --num-jobs 20
```

### Dry Run (test sans notif)

```bash
python upwork_adapter.py --query "VBA excel" --dry-run
```

### Queries suggérées

```bash
# Tes spécialités
python upwork_adapter.py --query "VBA automation"
python upwork_adapter.py --query "Excel macro"
python upwork_adapter.py --query "Python scripting"
python upwork_adapter.py --query "API integration"
python upwork_adapter.py --query "Discord bot"

# AI/LLM
python upwork_adapter.py --query "ChatGPT integration"
python upwork_adapter.py --query "LLM API"
python upwork_adapter.py --query "AI automation"
```

## Fonctionnement

```
┌─────────────────────────────────────────────────────────────┐
│                    upwork_adapter.py                        │
├─────────────────────────────────────────────────────────────┤
│  1. Appelle le scraper Upwork (submodule)                   │
│  2. Filtre les jobs déjà vus (seen_upwork_jobs.json)        │
│  3. Match nos skills (files/keywords/skills_index.json)     │
│  4. Calcule le poids total                                  │
│  5. Si poids >= min_weight → Score avec Claude Haiku        │
│  6. Si score >= min_score → Notifie Discord                 │
│  7. PAS d'auto-post de proposal                             │
└─────────────────────────────────────────────────────────────┘
```

## Fichiers

| Fichier | Description |
|---------|-------------|
| `upwork_adapter.py` | Wrapper (notre code) |
| `adapters/upwork/` | Submodule (leur code) |
| `seen_upwork_jobs.json` | Jobs déjà traités |
| `requirements-upwork.txt` | Dépendances Playwright |

## Troubleshooting

### "Cloudflare blocked"

Upwork utilise Cloudflare pour bloquer les bots. Solutions :
1. Utilise le profil Firefox avec session active
2. Ne lance pas trop de requêtes (--num-jobs 20 max)
3. Attends quelques heures si bloqué

### "Not logged in"

1. Ouvre Firefox manuellement
2. Va sur upwork.com
3. Connecte-toi
4. Ferme Firefox
5. Relance le script

### "Firefox profile not found"

Vérifie le chemin dans `adapters/upwork/test_with_firefox_profile.py` et ajuste si nécessaire.

### Import errors

```bash
# Réinstalle les deps
pip install -r requirements-upwork.txt --force-reinstall

# Vérifie le submodule
git submodule update --init --recursive
```

## Cron (Local seulement)

Tu peux automatiser sur ta machine locale (pas le serveur) :

```bash
# Windows Task Scheduler ou cron WSL
# Toutes les 2 heures pendant les heures de travail
0 9,11,13,15,17 * * 1-5 cd /path/to/freelance-notify && python upwork_adapter.py --query "VBA automation"
```

**Note** : Ne fonctionne que si Firefox reste connecté à Upwork.

## Mettre à jour le submodule

Quand le repo upstream a des updates :

```bash
cd adapters/upwork
git fetch origin
git pull origin main
cd ../..
git add adapters/upwork
git commit -m "Update Upwork submodule"
git push
```

## Différences avec Codeur.com

| Aspect | Codeur.com | Upwork |
|--------|------------|--------|
| Scraping | RSS (simple) | Playwright (browser) |
| Auth | Non requis | Session Firefox |
| Serveur | ✅ Oui | ❌ Local seulement |
| Cron | Toutes les 30min | Manuel ou local |
| Anti-bot | Léger | Cloudflare agressif |
