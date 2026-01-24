# Freelance Notify

Automated freelance platform monitoring bot with Discord notifications and AI scoring.

Currently supported: **Codeur.com** (French freelance platform)

Roadmap: Malt, Upwork, Freelance.com (see [TODO.md](TODO.md))

## Features

- **RSS Scraping** - Automatic monitoring of new projects
- **Smart Filtering** - By keywords, budget, categories
- **AI Scoring** - Automatic evaluation with Claude Haiku 4.5
- **Dynamic Profile** - Profile assembly based on matched skills
- **Weight System** - Pre-filtering before AI calls (saves tokens)
- **Negative Skills** - Penalize unwanted technologies
- **Rolling Statistics** - 30-day market analysis
- **Weekly Report** - Automatic Discord summary every Monday
- **Anti-Detection** - Realistic user-agents, jitter, random delays

## Architecture

```
freelance-notify/
├── scraper.py              # Main script
├── config.json             # Configuration (not versioned)
├── config.example.json     # Configuration template
├── requirements.txt        # Python dependencies
├── files/
│   ├── profile.md          # Base freelancer profile
│   ├── skill_stats.json    # Rolling 30-day statistics
│   └── keywords/
│       ├── skills_index.json         # Skills index with scores/weights
│       ├── tech_keywords_detector.json # Unknown tech detection
│       ├── vba.md                     # VBA skill profile
│       ├── python.md                  # Python skill profile
│       └── ...                        # Other skill profiles
├── seen_projects.json      # Already processed project IDs
└── cron.log               # Execution logs
```

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/AlexisTrouve/freelance-notify.git
cd freelance-notify
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure

```bash
cp config.example.json config.json
nano config.json
```

Edit:
- `discord_webhook_url`: Discord webhook URL
- `anthropic_api_key`: Anthropic API key (for AI scoring)
- `filters.keywords`: Keywords to monitor

### 4. Create freelancer profile

```bash
nano files/profile.md
```

Describe your profile, skills, experience.

### 5. Test

```bash
# Dry run (no notifications)
python scraper.py --dry-run --no-jitter

# Debug (detailed matching output)
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
| `stealth.enabled` | Enable anti-detection measures |
| `stealth.jitter_minutes` | Random startup variation (0-N min) |
| `ai_scoring.enabled` | Enable AI scoring |
| `ai_scoring.min_score` | Minimum score to notify (1-10) |
| `ai_scoring.min_weight` | Minimum weight to call AI |
| `filters.keywords` | At least one must match |
| `filters.exclude_keywords` | Exclude if present |

## Skills System

### Concept

Each skill has:
- **Score** (0-10): Your competence/interest level
- **Weight**: Points calculated from score
- **Keywords**: Words that trigger the match
- **Profile**: Detailed description (.md file)

### Weight Table

| Score | Weight | Interpretation |
|-------|--------|----------------|
| 0 | -10 | Negative skill (avoid) |
| 1-3 | -5 to -1 | Low interest |
| 4-5 | 0 to +2 | Neutral |
| 6-7 | +4 to +7 | Good |
| 8-10 | +12 to +20 | Excellent |

### Adding a skill

1. Create the profile file:
```bash
nano files/keywords/new_skill.md
```

2. Add to `files/keywords/skills_index.json`:
```json
"new_skill": {
  "score": 8,
  "weight": 12,
  "keywords": ["keyword1", "keyword2"],
  "profile_file": "new_skill.md"
}
```

### Negative skills

To penalize certain technologies:
```json
"php": {
  "score": 0,
  "weight": -10,
  "keywords": ["php", "laravel", "symfony"],
  "profile_file": "php.md"
}
```

## Commands

```bash
# Normal run (with jitter)
python scraper.py

# Dry run (test without notifications)
python scraper.py --dry-run --no-jitter

# Debug (detailed matching per job)
python scraper.py --debug --no-jitter

# Display statistics
python scraper.py --stats

# Send weekly Discord report
python scraper.py --weekly-report --no-jitter
```

## Statistics

The bot automatically collects market stats:

- **Known skills**: Frequency of each skill in jobs
- **Trends**: 7-day vs previous 7-day comparison
- **Unknown keywords**: Detected but unindexed technologies
- **Rolling 30 days**: Automatic cleanup of old data

### View stats

```bash
python scraper.py --stats
```

Output:
```
===========================================================================
  SKILL STATISTICS - Codeur.com (Rolling 30 days)
===========================================================================

  Jobs analyzed: 450 (30d) | 120 (7d) | 98 (prev 7d)

  KNOWN SKILLS (30 days):
  Skill              30d     7d    Trend   Prev 7d
  -----------------------------------------------------------------------
    python             45     15     +25%        12
    api                32     10     -10%        11
    ecommerce          28      8      NEW         0
```

## Cron Setup

### Scraping every 30 minutes

```bash
crontab -e
```

```cron
*/30 * * * * cd /path/to/freelance-notify && /usr/bin/python3 scraper.py >> cron.log 2>&1
```

### Weekly report (Monday 9am)

```cron
0 9 * * 1 cd /path/to/freelance-notify && /usr/bin/python3 scraper.py --weekly-report --no-jitter >> cron.log 2>&1
```

## Discord Webhook

1. Discord channel settings
2. Integrations > Webhooks > New Webhook
3. Copy URL
4. Paste in `config.json`

### Notifications

- **Projects**: Embed with title, budget, AI score, matched skills
- **Weekly report**: Trends summary, top skills, keywords to index

## Deployment

```bash
# Copy files to server
scp scraper.py user@server:/path/to/freelance-notify/
scp files/keywords/*.json user@server:/path/to/freelance-notify/files/keywords/
```

## Logs

```bash
# View latest logs
tail -f cron.log

# Today's logs
grep "$(date +%Y-%m-%d)" cron.log
```

## Troubleshooting

### No projects found

- Check keywords in `config.json`
- Test with `--debug` to see matching

### AI score always low

- Check that `files/profile.md` is properly filled
- Adjust skill profiles in `files/keywords/*.md`

### Discord rate limiting

- Discord limits to 30 requests/minute per webhook
- The bot automatically spaces out requests

## Upwork Adapter (Optional)

The Upwork adapter uses [Upwork-AI-jobs-applier](https://github.com/kaymen99/Upwork-AI-jobs-applier) as a git submodule for scraping, combined with our skills/scoring system.

### Setup

```bash
# Initialize submodule
git submodule update --init --recursive

# Install Upwork dependencies
pip install -r requirements-upwork.txt

# Install Playwright browsers
playwright install firefox
```

### Usage

```bash
# Scrape Upwork and notify Discord
python upwork_adapter.py --query "python automation" --num-jobs 20

# Dry run (no notifications)
python upwork_adapter.py --query "VBA excel" --dry-run
```

### Notes

- **Requires Firefox profile** with active Upwork session (Upwork blocks headless bots)
- **Local only** - Cannot run on server without maintaining browser session
- Uses same `config.json`, skills index, and Discord webhook as main scraper
- No auto-posting of proposals - just scrape, score, and notify

### Update Upstream

```bash
cd adapters/upwork
git pull origin main
cd ../..
git add adapters/upwork
git commit -m "Update Upwork submodule"
```

## License

MIT
