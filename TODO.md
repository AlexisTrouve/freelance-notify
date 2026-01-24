# TODO - Codeur.com Auto-Notify Bot

## Roadmap

### v1.1 - Améliorations Stats
- [ ] Export CSV des stats (pour analyse externe)
- [ ] Graphiques ASCII des tendances dans le terminal
- [ ] Rapport mensuel en plus du rapport hebdo
- [ ] Alerte Discord quand un nouveau keyword inconnu dépasse un seuil

### v1.2 - Multi-plateforme
- [ ] Support Malt.fr
- [ ] Support Upwork (adapter le scraper existant)
- [ ] Support Freelance.com
- [ ] Agrégation des stats cross-plateforme

### v1.3 - Intelligence
- [ ] Auto-suggestion de nouveaux skills basée sur les keywords inconnus fréquents
- [ ] Scoring prédictif (ML léger) basé sur l'historique des jobs acceptés
- [ ] Détection de patterns (ex: "les jobs Python paient mieux le lundi")
- [ ] Analyse sémantique des descriptions (clustering de jobs similaires)

### v1.4 - Automatisation
- [ ] Auto-réponse template sur les jobs très bien scorés
- [ ] Intégration calendrier (bloquer des créneaux pour les bons jobs)
- [ ] Webhook entrant pour marquer un job comme "contacté" / "gagné" / "perdu"
- [ ] Suivi du taux de conversion par skill

### v1.5 - Interface
- [ ] Dashboard web simple (Flask/FastAPI)
- [ ] API REST pour les stats
- [ ] Notifications push mobile (via Pushover/Ntfy)
- [ ] Bot Telegram en alternative à Discord

---

## Backlog (idées en vrac)

- [ ] Mode "veille" : scraper moins souvent la nuit
- [ ] Blacklist de clients (par nom ou pattern)
- [ ] Détection de jobs "fake" ou trop vagues
- [ ] Estimation du temps de projet basée sur le budget
- [ ] Comparaison avec les tarifs moyens du marché
- [ ] Export des jobs matchés vers Notion/Airtable
- [ ] Intégration avec un CRM freelance
- [ ] Historique des jobs notifiés (pour ne pas re-notifier un job déjà vu qui repasse)
- [ ] Support multi-langue (jobs en anglais)
- [ ] Proxy rotation pour le scraping intensif

---

## Bugs connus

- [ ] Encodage Windows (caractères spéciaux dans les logs)
- [ ] Le keyword "c" peut encore matcher dans certains contextes edge

---

## Fait (changelog)

### v1.0 - Initial Release
- [x] Scraping RSS Codeur.com
- [x] Filtrage par mots-clés et budget
- [x] Scoring IA avec Claude Haiku 4.5
- [x] Système de profil dynamique (34 skills)
- [x] Poids et skills négatifs
- [x] Statistiques rolling 30 jours
- [x] Rapport hebdomadaire Discord
- [x] Détection de keywords tech inconnus
- [x] Mode debug et dry-run
- [x] Anti-détection (jitter, UA rotation, délais)
