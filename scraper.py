#!/usr/bin/env python3
"""
Codeur.com Project Scraper
Fetches new projects from RSS feed and sends notifications to Discord
With AI scoring using Claude Haiku 4.5
"""

import requests
import xml.etree.ElementTree as ET
import json
import re
import random
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Scoring prompt (same as Upwork scraper for consistency)
SCORE_JOBS_PROMPT = """
You are a job matching expert specializing in pairing freelancers with the most suitable jobs.
Your task is to evaluate each job based on the following criteria:

1. **Relevance to Freelancer Profile**: Assess how closely the job matches the skills, experience, and qualifications outlined in the freelancer's profile.
2. **Complexity of the Project**: Determine the complexity level of the job and how it aligns with the freelancer's expertise.
3. **Rate**: If the job's rate is provided evaluate the compensation compared to industry standards otherwise ignore it.
4. **Client History**: Consider the client's previous hiring history, totals amount spent, active jobs and longevity on the platform (if available).

For each job, assign a score from 1 to 10 based on the above criteria, with 10 being the best match.

IMPORTANT: Respond with ONLY a JSON object in this exact format, nothing else:
{{"score": <number>, "reason": "<brief explanation>"}}

Freelancer Profile:
<profile>
{profile}
</profile>
"""

class CodeurScraper:
    BASE_URL = "https://www.codeur.com"
    RSS_URL = "https://www.codeur.com/projects.rss"

    # Pool of realistic User-Agents (RSS readers + browsers)
    USER_AGENTS = [
        # RSS readers (legitimate)
        'Feedly/1.0 (+http://www.feedly.com/fetcher.html)',
        'NewsBlur Feed Fetcher - 1 subscriber',
        'Inoreader/1.0 (+https://www.inoreader.com)',
        'Feedbin feed-id:12345 - 1 subscriber',
        # Browsers (fallback)
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0',
    ]

    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self.seen_projects = self._load_seen_projects()
        self.session = requests.Session()
        self._setup_session()
        self.base_profile = self._load_profile()
        self.skills_index = self._load_skills_index()
        self.tech_keywords_detector = self._load_tech_keywords_detector()
        self.skill_stats = self._load_skill_stats()
        self.anthropic_api_key = self.config.get('anthropic_api_key') or os.environ.get('ANTHROPIC_API_KEY')

    def _setup_session(self):
        """Configure session with random realistic headers"""
        self.session.headers.update({
            'User-Agent': random.choice(self.USER_AGENTS),
            'Accept': 'application/rss+xml, application/xml, text/xml, */*',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache',
        })

    def _load_config(self, config_path: str) -> dict:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _load_profile(self) -> str:
        """Load base freelancer profile for AI scoring"""
        profile_path = Path(self.config.get('profile_file', 'files/profile.md'))
        if profile_path.exists():
            with open(profile_path, 'r', encoding='utf-8') as f:
                return f.read()
        logger.warning(f"Profile not found at {profile_path}, AI scoring disabled")
        return ""

    def _load_skills_index(self) -> dict:
        """Load skills index for dynamic profile assembly"""
        skills_path = Path('files/keywords/skills_index.json')
        if skills_path.exists():
            with open(skills_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        logger.warning(f"Skills index not found at {skills_path}")
        return {"skills": {}, "weight_table": {}}

    def _load_tech_keywords_detector(self) -> list:
        """Load list of tech keywords for detecting unknown technologies"""
        detector_path = Path('files/keywords/tech_keywords_detector.json')
        if detector_path.exists():
            with open(detector_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('tech_keywords', [])
        return []

    def _load_skill_stats(self) -> dict:
        """Load skill statistics with daily data structure"""
        stats_path = Path('files/skill_stats.json')
        if stats_path.exists():
            with open(stats_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Migrate old format if needed
                if 'daily_data' not in data:
                    return self._migrate_old_stats(data)
                return data
        return {
            "last_updated": None,
            "daily_data": {},  # {"2026-01-24": {"jobs": [...], "skills": {...}, "unknown": {...}}}
            "analyzed_jobs": {}  # {"job_id": "2026-01-24"} to track which day each job was counted
        }

    def _migrate_old_stats(self, old_data: dict) -> dict:
        """Migrate old cumulative format to new daily format"""
        today = datetime.now().strftime('%Y-%m-%d')
        return {
            "last_updated": old_data.get('last_updated'),
            "daily_data": {
                today: {
                    "jobs_count": old_data.get('total_jobs_analyzed', 0),
                    "skills": {k: v['count'] for k, v in old_data.get('known_skills', {}).items()},
                    "unknown": {k: v['count'] for k, v in old_data.get('unknown_keywords', {}).items()}
                }
            },
            "analyzed_jobs": {job_id: today for job_id in old_data.get('analyzed_jobs', [])}
        }

    def _save_skill_stats(self):
        """Save skill statistics and cleanup old data (keep 30 days)"""
        stats_path = Path('files/skill_stats.json')
        self.skill_stats['last_updated'] = datetime.now().isoformat()

        # Cleanup: keep only last 30 days of daily data
        cutoff_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        self.skill_stats['daily_data'] = {
            date: data for date, data in self.skill_stats.get('daily_data', {}).items()
            if date >= cutoff_date
        }

        # Cleanup analyzed_jobs: remove jobs older than 30 days
        self.skill_stats['analyzed_jobs'] = {
            job_id: date for job_id, date in self.skill_stats.get('analyzed_jobs', {}).items()
            if date >= cutoff_date
        }

        with open(stats_path, 'w', encoding='utf-8') as f:
            json.dump(self.skill_stats, f, indent=2, ensure_ascii=False)

    def _get_all_known_keywords(self) -> set:
        """Get all keywords from skills index"""
        known = set()
        for skill_data in self.skills_index.get('skills', {}).values():
            for kw in skill_data.get('keywords', []):
                known.add(kw.lower())
        return known

    def _detect_unknown_tech_keywords(self, text: str) -> list[str]:
        """Detect tech keywords that are not in our skills index"""
        text_lower = text.lower()
        known_keywords = self._get_all_known_keywords()
        found_unknown = []

        for tech_kw in self.tech_keywords_detector:
            tech_kw_lower = tech_kw.lower()
            # Skip if already in our known skills
            if tech_kw_lower in known_keywords:
                continue
            # Use word boundary matching
            pattern = r'\b' + re.escape(tech_kw_lower) + r'\b'
            if re.search(pattern, text_lower):
                found_unknown.append(tech_kw)

        return found_unknown

    def _update_skill_stats(self, matched_skills: list[dict], unknown_keywords: list[str], job_id: str):
        """Update skill statistics with matched skills and unknown keywords (daily granularity)"""
        today = datetime.now().strftime('%Y-%m-%d')

        # Initialize structures if needed
        if 'analyzed_jobs' not in self.skill_stats:
            self.skill_stats['analyzed_jobs'] = {}
        if 'daily_data' not in self.skill_stats:
            self.skill_stats['daily_data'] = {}

        # Skip if already analyzed
        if job_id in self.skill_stats['analyzed_jobs']:
            return

        # Mark job as analyzed today
        self.skill_stats['analyzed_jobs'][job_id] = today

        # Initialize today's data if needed
        if today not in self.skill_stats['daily_data']:
            self.skill_stats['daily_data'][today] = {
                'jobs_count': 0,
                'skills': {},
                'unknown': {}
            }

        day_data = self.skill_stats['daily_data'][today]
        day_data['jobs_count'] += 1

        # Update skills for today
        for skill in matched_skills:
            skill_name = skill['name']
            if skill_name not in day_data['skills']:
                day_data['skills'][skill_name] = 0
            day_data['skills'][skill_name] += 1

        # Update unknown keywords for today
        for kw in unknown_keywords:
            kw_lower = kw.lower()
            if kw_lower not in day_data['unknown']:
                day_data['unknown'][kw_lower] = 0
            day_data['unknown'][kw_lower] += 1

    def _match_skills(self, text: str) -> list[dict]:
        """Match job text against skill keywords, return matched skills with weights"""
        text_lower = text.lower()
        matched = []

        for skill_name, skill_data in self.skills_index.get('skills', {}).items():
            keywords = skill_data.get('keywords', [])
            for keyword in keywords:
                keyword_lower = keyword.lower()
                # Use word boundary matching to avoid false positives
                # e.g., "c" shouldn't match "commerce", "go" shouldn't match "logo"
                pattern = r'\b' + re.escape(keyword_lower) + r'\b'
                if re.search(pattern, text_lower):
                    matched.append({
                        'name': skill_name,
                        'score': skill_data.get('score', 0),
                        'weight': skill_data.get('weight', 0),
                        'profile_file': skill_data.get('profile_file', ''),
                        'matched_keyword': keyword
                    })
                    break  # One match per skill is enough

        return matched

    def _calculate_total_weight(self, matched_skills: list[dict]) -> int:
        """Calculate total weight from matched skills"""
        return sum(skill.get('weight', 0) for skill in matched_skills)

    def _assemble_profile(self, matched_skills: list[dict]) -> str:
        """Assemble dynamic profile from matched skills + project reports"""
        parts = []

        # Add base profile header if exists
        if self.base_profile:
            parts.append("# Profil Freelancer\n")
            parts.append(self.base_profile)
            parts.append("\n---\n")

        # Add matched skill profiles
        if matched_skills:
            parts.append("# Compétences pertinentes pour ce projet\n")

            # Sort by weight (highest first)
            sorted_skills = sorted(matched_skills, key=lambda x: x.get('weight', 0), reverse=True)

            for skill in sorted_skills:
                profile_file = skill.get('profile_file', '')
                if profile_file:
                    skill_path = Path('files/keywords') / profile_file
                    if skill_path.exists():
                        with open(skill_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            parts.append(f"\n## {skill['name'].upper()} (Score: {skill['score']}/10)\n")
                            parts.append(content)

        # Add relevant project reports based on matched skills
        project_reports = self._get_relevant_projects(matched_skills)
        if project_reports:
            parts.append("\n---\n")
            parts.append("# Projets Portfolio Pertinents\n")
            for project_content in project_reports:
                parts.append(f"\n{project_content}\n")

        return "\n".join(parts)

    def _get_relevant_projects(self, matched_skills: list[dict]) -> list[str]:
        """Get project reports based on matched skills"""
        project_files = set()  # Use set to avoid duplicates

        for skill in matched_skills:
            skill_name = skill.get('name', '')
            # Get skill data from skills_index
            skill_data = self.skills_index.get('skills', {}).get(skill_name, {})
            projects = skill_data.get('projects', [])

            # Add all project files for this skill
            for project_file in projects:
                project_files.add(project_file)

        # Load and return project contents
        project_contents = []
        project_dir = Path(__file__).parent / 'files' / 'portfolio'

        for project_file in sorted(project_files):  # Sort for consistent ordering
            project_path = project_dir / project_file
            if project_path.exists():
                try:
                    with open(project_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        project_contents.append(content)
                except Exception as e:
                    logger.debug(f"Could not load project report {project_file}: {e}")
            else:
                logger.debug(f"Project report not found: {project_path}")

        return project_contents

    def _load_seen_projects(self) -> set:
        seen_file = Path(self.config.get('seen_projects_file', 'seen_projects.json'))
        if seen_file.exists():
            with open(seen_file, 'r') as f:
                return set(json.load(f))
        return set()

    def _save_seen_projects(self):
        seen_file = Path(self.config.get('seen_projects_file', 'seen_projects.json'))
        with open(seen_file, 'w') as f:
            json.dump(list(self.seen_projects), f)

    def _random_delay(self):
        """Add random delay to appear more human-like"""
        stealth = self.config.get('stealth', {})
        if not stealth.get('enabled', True):
            return
        min_sec = stealth.get('min_delay_seconds', 1)
        max_sec = stealth.get('max_delay_seconds', 3)
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)

    def score_project_with_ai(self, project: dict) -> dict:
        """Score a project using Claude Haiku 4.5 with dynamic profile"""
        if not self.anthropic_api_key:
            return project  # Return unchanged if no API key

        scoring_config = self.config.get('ai_scoring', {})
        if not scoring_config.get('enabled', False):
            return project

        try:
            # Build job description for scoring
            job_text = f"""
Title: {project.get('title', 'N/A')}
Description: {project.get('description', 'N/A')}
Budget: {project.get('budget_text', 'N/A')}
Categories: {project.get('category', 'N/A')}
URL: {project.get('url', 'N/A')}
"""
            # Match skills and calculate weight
            full_text = f"{project.get('title', '')} {project.get('description', '')} {project.get('category', '')}"
            matched_skills = self._match_skills(full_text)
            total_weight = self._calculate_total_weight(matched_skills)

            # Store matched skills info in project
            project['matched_skills'] = [s['name'] for s in matched_skills]
            project['total_weight'] = total_weight

            # Check weight threshold (default 5 = at least one decent skill match)
            min_weight = scoring_config.get('min_weight', 5)
            if total_weight < min_weight:
                logger.debug(f"Skipping AI scoring for '{project['title'][:50]}...' - weight {total_weight} < {min_weight}")
                project['ai_score'] = 0
                project['ai_reason'] = f"Poids insuffisant ({total_weight} < {min_weight})"
                return project

            # Assemble dynamic profile based on matched skills
            dynamic_profile = self._assemble_profile(matched_skills)
            if not dynamic_profile:
                dynamic_profile = self.base_profile

            logger.debug(f"Matched skills for '{project['title'][:30]}...': {[s['name'] for s in matched_skills]} (weight: {total_weight})")

            # Call Claude Haiku API
            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'Content-Type': 'application/json',
                    'x-api-key': self.anthropic_api_key,
                    'anthropic-version': '2023-06-01'
                },
                json={
                    'model': scoring_config.get('model', 'claude-haiku-4-5-20251001'),
                    'max_tokens': 200,
                    'temperature': 0.1,
                    'system': SCORE_JOBS_PROMPT.format(profile=dynamic_profile),
                    'messages': [
                        {'role': 'user', 'content': f"Score this job:\n\n{job_text}"}
                    ]
                },
                timeout=30
            )
            response.raise_for_status()

            result = response.json()
            content = result.get('content', [{}])[0].get('text', '{}')

            # Parse JSON response (may be wrapped in markdown code blocks)
            try:
                # Remove markdown code blocks if present
                json_content = content
                if '```' in content:
                    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
                    if json_match:
                        json_content = json_match.group(1)

                score_data = json.loads(json_content)
                project['ai_score'] = score_data.get('score', 0)
                project['ai_reason'] = score_data.get('reason', '')
                logger.debug(f"Scored '{project['title']}': {project['ai_score']}/10")
            except json.JSONDecodeError:
                # Try to extract score from text
                score_match = re.search(r'"score"\s*:\s*(\d+)', content)
                if score_match:
                    project['ai_score'] = int(score_match.group(1))
                    reason_match = re.search(r'"reason"\s*:\s*"([^"]+)"', content)
                    if reason_match:
                        project['ai_reason'] = reason_match.group(1)
                else:
                    logger.warning(f"Could not parse AI score for '{project['title']}'")

        except requests.RequestException as e:
            logger.error(f"Error calling Anthropic API: {e}")
        except Exception as e:
            logger.error(f"Error scoring project: {e}")

        return project

    def score_projects(self, projects: list[dict]) -> list[dict]:
        """Score multiple projects with AI and filter by minimum score"""
        scoring_config = self.config.get('ai_scoring', {})
        if not scoring_config.get('enabled', False):
            return projects

        min_score = scoring_config.get('min_score', 7)
        scored = []

        logger.info(f"Scoring {len(projects)} projects with AI (min score: {min_score})...")

        for project in projects:
            project = self.score_project_with_ai(project)

            ai_score = project.get('ai_score', 0)
            if ai_score >= min_score:
                scored.append(project)
                logger.info(f"  ✓ {project['title'][:50]}... - Score: {ai_score}/10")
            else:
                logger.debug(f"  ✗ {project['title'][:50]}... - Score: {ai_score}/10 (below threshold)")

            # Small delay between API calls
            time.sleep(0.5)

        logger.info(f"AI scoring complete: {len(scored)}/{len(projects)} projects passed (>= {min_score}/10)")
        return scored

    def scrape_projects(self) -> list[dict]:
        """Fetch projects from Codeur.com RSS feed"""
        projects = []

        try:
            # Random delay before request
            self._random_delay()

            # Rotate User-Agent for each request
            self.session.headers['User-Agent'] = random.choice(self.USER_AGENTS)

            logger.info("Fetching RSS feed...")
            response = self.session.get(self.RSS_URL, timeout=30)

            # Handle rate limiting gracefully
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                logger.warning(f"Rate limited. Waiting {retry_after}s...")
                time.sleep(retry_after)
                return []

            response.raise_for_status()

            root = ET.fromstring(response.content)
            items = root.findall('.//item')

            logger.info(f"Found {len(items)} projects in RSS feed")

            for item in items:
                project = self._parse_rss_item(item)
                if project and project.get('id'):
                    projects.append(project)

        except requests.RequestException as e:
            logger.error(f"Error fetching RSS feed: {e}")
        except ET.ParseError as e:
            logger.error(f"Error parsing RSS XML: {e}")
        except Exception as e:
            logger.error(f"Error processing RSS: {e}")

        return projects

    def _parse_rss_item(self, item) -> Optional[dict]:
        """Parse an RSS item element"""
        try:
            title = item.findtext('title', '').strip()
            link = item.findtext('link', '').strip()
            guid = item.findtext('guid', '').strip()
            description_html = item.findtext('description', '').strip()
            pub_date = item.findtext('pubDate', '').strip()

            if not guid or not link:
                return None

            # Parse description to extract budget and categories
            budget_text = ""
            category = ""
            description = ""

            if description_html:
                # Extract budget: "Budget : XXX €"
                budget_match = re.search(r'Budget\s*:\s*([^<-]+?)(?:\s*-|<)', description_html)
                if budget_match:
                    budget_text = budget_match.group(1).strip()

                # Extract categories
                cat_match = re.search(r'Catégories?\s*:\s*([^<]+?)(?:</p>|<)', description_html)
                if cat_match:
                    category = cat_match.group(1).strip()

                # Extract description text (after the budget/category line)
                desc_match = re.search(r'</p>\s*<p>\s*(.+?)\s*</p>\s*<p>\s*<a', description_html, re.DOTALL)
                if desc_match:
                    description = re.sub(r'<[^>]+>', '', desc_match.group(1)).strip()
                    description = description.replace('&#39;', "'").replace('&amp;', '&')

            # Clean up title
            title = title.replace('&#39;', "'").replace('&amp;', '&')

            return {
                'id': guid,
                'title': title,
                'description': description,
                'url': link,
                'budget': self._parse_budget(budget_text),
                'budget_text': budget_text,
                'category': category,
                'pub_date': pub_date,
                'scraped_at': datetime.now().isoformat()
            }

        except Exception as e:
            logger.debug(f"Error parsing RSS item: {e}")
            return None

    def _parse_budget(self, budget_text: str) -> Optional[int]:
        """Extract numeric budget from text"""
        if not budget_text:
            return None
        # Find numbers in the text
        numbers = re.findall(r'(\d+(?:\s*\d+)*)', budget_text.replace(' ', ''))
        if numbers:
            try:
                return int(numbers[0].replace(' ', ''))
            except ValueError:
                pass
        return None

    def filter_projects(self, projects: list[dict]) -> list[dict]:
        """Filter projects based on config criteria"""
        filters = self.config.get('filters', {})
        keywords = [k.lower() for k in filters.get('keywords', [])]
        exclude_keywords = [k.lower() for k in filters.get('exclude_keywords', [])]
        min_budget = filters.get('min_budget')
        max_budget = filters.get('max_budget')

        filtered = []

        for project in projects:
            # Skip already seen
            if project['id'] in self.seen_projects:
                continue

            text = f"{project.get('title', '')} {project.get('description', '')} {project.get('category', '')}".lower()

            # Check exclude keywords first
            if exclude_keywords and any(kw in text for kw in exclude_keywords):
                logger.debug(f"Excluded project {project['id']}: matches exclude keyword")
                continue

            # Check include keywords (if specified, at least one must match)
            if keywords and not any(kw in text for kw in keywords):
                logger.debug(f"Excluded project {project['id']}: no keyword match")
                continue

            # Check budget
            budget = project.get('budget')
            if min_budget and budget and budget < min_budget:
                logger.debug(f"Excluded project {project['id']}: budget too low")
                continue
            if max_budget and budget and budget > max_budget:
                logger.debug(f"Excluded project {project['id']}: budget too high")
                continue

            filtered.append(project)

        return filtered

    def send_discord_notification(self, projects: list[dict]):
        """Send notification to Discord webhook"""
        webhook_url = self.config.get('discord_webhook_url')
        if not webhook_url or 'YOUR_WEBHOOK' in webhook_url:
            logger.warning("Discord webhook not configured")
            return

        max_projects = self.config.get('max_projects_per_notification', 10)
        projects = projects[:max_projects]

        if not projects:
            logger.info("No new projects to notify")
            return

        # Build embed for each project
        embeds = []
        for project in projects:
            # Color based on AI score (green = high, blue = medium, orange = low)
            ai_score = project.get('ai_score', 0)
            if ai_score >= 8:
                color = 3066993  # Green
            elif ai_score >= 6:
                color = 3447003  # Blue
            else:
                color = 15105570  # Orange

            embed = {
                "title": project.get('title', 'Nouveau projet')[:256],
                "url": project.get('url'),
                "color": color,
                "fields": [],
                "timestamp": datetime.now().isoformat()
            }

            if project.get('description'):
                embed["description"] = project['description'][:500]

            # AI Score field (if scored)
            if ai_score > 0:
                embed["fields"].append({
                    "name": "🎯 Score AI",
                    "value": f"**{ai_score}/10**",
                    "inline": True
                })

            # Matched skills field
            matched_skills = project.get('matched_skills', [])
            if matched_skills:
                skills_text = ", ".join(matched_skills[:5])
                if len(matched_skills) > 5:
                    skills_text += f" (+{len(matched_skills) - 5})"
                embed["fields"].append({
                    "name": "🔧 Skills",
                    "value": skills_text,
                    "inline": True
                })

            if project.get('budget_text'):
                embed["fields"].append({
                    "name": "💰 Budget",
                    "value": project['budget_text'],
                    "inline": True
                })

            if project.get('category'):
                embed["fields"].append({
                    "name": "📁 Categorie",
                    "value": project['category'][:100],
                    "inline": True
                })

            # AI reason as footer (if available)
            if project.get('ai_reason'):
                embed["footer"] = {"text": f"💡 {project['ai_reason'][:200]}"}

            embeds.append(embed)

        # Discord allows max 10 embeds per message
        for i in range(0, len(embeds), 10):
            batch = embeds[i:i+10]
            payload = {
                "content": f"**{len(batch)} nouveau(x) projet(s) sur Codeur.com**" if i == 0 else None,
                "embeds": batch
            }

            try:
                response = requests.post(webhook_url, json=payload, timeout=10)
                response.raise_for_status()
                logger.info(f"Sent {len(batch)} projects to Discord")
                time.sleep(1)  # Rate limiting
            except requests.RequestException as e:
                logger.error(f"Error sending to Discord: {e}")

    def mark_as_seen(self, projects: list[dict]):
        """Mark projects as seen"""
        for project in projects:
            self.seen_projects.add(project['id'])
        self._save_seen_projects()

    def send_weekly_report(self):
        """Generate and send weekly stats report to Discord"""
        webhook_url = self.config.get('discord_webhook_url')
        if not webhook_url or 'YOUR_WEBHOOK' in webhook_url:
            logger.warning("Discord webhook not configured")
            return

        daily_data = self.skill_stats.get('daily_data', {})
        if not daily_data:
            logger.warning("No stats data available for weekly report")
            return

        # Calculate date ranges
        today = datetime.now()
        dates_7d = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
        dates_prev_7d = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7, 14)]
        dates_30d = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(30)]

        # Aggregate data
        def aggregate_period(dates):
            jobs = 0
            skills = {}
            unknown = {}
            for date in dates:
                if date in daily_data:
                    day = daily_data[date]
                    jobs += day.get('jobs_count', 0)
                    for skill, count in day.get('skills', {}).items():
                        skills[skill] = skills.get(skill, 0) + count
                    for kw, count in day.get('unknown', {}).items():
                        unknown[kw] = unknown.get(kw, 0) + count
            return jobs, skills, unknown

        jobs_7d, skills_7d, unknown_7d = aggregate_period(dates_7d)
        jobs_prev_7d, skills_prev_7d, _ = aggregate_period(dates_prev_7d)
        jobs_30d, skills_30d, unknown_30d = aggregate_period(dates_30d)

        # Trend calculation
        def trend_emoji(current, previous):
            if previous == 0:
                return "🆕" if current > 0 else ""
            diff_pct = ((current - previous) / previous) * 100
            if diff_pct > 20:
                return "📈"
            elif diff_pct < -20:
                return "📉"
            return "➡️"

        def trend_text(current, previous):
            if previous == 0:
                return "NEW" if current > 0 else "-"
            diff_pct = ((current - previous) / previous) * 100
            if diff_pct > 0:
                return f"+{diff_pct:.0f}%"
            return f"{diff_pct:.0f}%"

        # Build embed
        embed = {
            "title": "📊 Rapport Hebdomadaire - Codeur.com",
            "color": 5814783,  # Purple
            "fields": [],
            "footer": {"text": f"Periode: {dates_7d[-1]} → {dates_7d[0]}"},
            "timestamp": datetime.now().isoformat()
        }

        # Jobs overview
        jobs_trend = trend_text(jobs_7d, jobs_prev_7d)
        embed["description"] = f"**{jobs_7d}** jobs analyses cette semaine ({jobs_trend} vs semaine precedente)\n**{jobs_30d}** jobs sur 30 jours"

        # Top skills this week (max 10)
        if skills_7d:
            sorted_skills = sorted(skills_7d.items(), key=lambda x: x[1], reverse=True)[:10]
            skills_lines = []
            for skill, count in sorted_skills:
                prev_count = skills_prev_7d.get(skill, 0)
                emoji = trend_emoji(count, prev_count)
                trend = trend_text(count, prev_count)
                skills_lines.append(f"{emoji} **{skill}**: {count} ({trend})")

            embed["fields"].append({
                "name": "🔧 Top Skills (7j)",
                "value": "\n".join(skills_lines[:5]),
                "inline": True
            })
            if len(skills_lines) > 5:
                embed["fields"].append({
                    "name": "​",  # Zero-width space for alignment
                    "value": "\n".join(skills_lines[5:10]),
                    "inline": True
                })

        # Emerging skills (NEW this week)
        new_skills = [s for s in skills_7d.keys() if skills_prev_7d.get(s, 0) == 0]
        if new_skills:
            new_skills_sorted = sorted(new_skills, key=lambda s: skills_7d[s], reverse=True)[:5]
            new_text = ", ".join([f"**{s}** ({skills_7d[s]})" for s in new_skills_sorted])
            embed["fields"].append({
                "name": "🆕 Skills emergents",
                "value": new_text,
                "inline": False
            })

        # Top unknown keywords (potential new skills)
        if unknown_7d:
            sorted_unknown = sorted(unknown_7d.items(), key=lambda x: x[1], reverse=True)[:5]
            unknown_text = ", ".join([f"{kw} ({count})" for kw, count in sorted_unknown])
            embed["fields"].append({
                "name": "❓ Keywords a indexer",
                "value": unknown_text,
                "inline": False
            })

        # Send to Discord
        payload = {"embeds": [embed]}
        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info("Weekly report sent to Discord")
        except requests.RequestException as e:
            logger.error(f"Error sending weekly report to Discord: {e}")

    def collect_skill_stats(self, projects: list[dict]):
        """Collect skill statistics from all projects"""
        for project in projects:
            text = f"{project.get('title', '')} {project.get('description', '')} {project.get('category', '')}"
            matched_skills = self._match_skills(text)
            unknown_keywords = self._detect_unknown_tech_keywords(text)
            self._update_skill_stats(matched_skills, unknown_keywords, project['id'])

        # Save stats after processing
        self._save_skill_stats()
        total_jobs = sum(d.get('jobs_count', 0) for d in self.skill_stats.get('daily_data', {}).values())
        logger.info(f"Skill stats updated: {total_jobs} total jobs analyzed (30 day rolling)")

    def run(self):
        """Main run method"""
        logger.info("Starting Codeur.com scraper...")

        # Scrape projects
        projects = self.scrape_projects()
        logger.info(f"Scraped {len(projects)} projects")

        # Collect skill stats on ALL projects (for market analysis)
        self.collect_skill_stats(projects)

        # Filter projects by keywords/budget
        new_projects = self.filter_projects(projects)
        logger.info(f"Found {len(new_projects)} new matching projects")

        # AI scoring (if enabled)
        if new_projects and self.config.get('ai_scoring', {}).get('enabled', False):
            new_projects = self.score_projects(new_projects)

        # Send notifications
        if new_projects:
            # Mark as seen FIRST to prevent duplicates if script crashes
            self.mark_as_seen(new_projects)
            self.send_discord_notification(new_projects)

        logger.info("Scraper run complete")
        return new_projects


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Codeur.com Project Scraper')
    parser.add_argument('--config', default='config.json', help='Config file path')
    parser.add_argument('--dry-run', action='store_true', help='Dry run without notifications')
    parser.add_argument('--no-jitter', action='store_true', help='Skip startup jitter')
    parser.add_argument('--debug', action='store_true', help='Show detailed skill matching debug info')
    parser.add_argument('--stats', action='store_true', help='Display skill statistics')
    parser.add_argument('--weekly-report', action='store_true', help='Send weekly stats report to Discord')
    args = parser.parse_args()

    # Load config first to get jitter settings
    with open(args.config, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # Apply startup jitter (randomize cron execution time)
    stealth = config.get('stealth', {})
    if stealth.get('enabled', True) and not args.no_jitter and not args.dry_run:
        jitter_minutes = stealth.get('jitter_minutes', 5)
        jitter_seconds = random.uniform(0, jitter_minutes * 60)
        logger.info(f"Startup jitter: waiting {jitter_seconds:.0f}s...")
        time.sleep(jitter_seconds)

    scraper = CodeurScraper(config_path=args.config)

    if args.stats:
        # Display skill statistics with rolling 30-day window
        stats = scraper.skill_stats
        daily_data = stats.get('daily_data', {})

        # Calculate date ranges
        today = datetime.now()
        dates_30d = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(30)]
        dates_7d = dates_30d[:7]
        dates_prev_7d = dates_30d[7:14]

        # Aggregate data for different periods
        def aggregate_period(dates):
            jobs = 0
            skills = {}
            unknown = {}
            for date in dates:
                if date in daily_data:
                    day = daily_data[date]
                    jobs += day.get('jobs_count', 0)
                    for skill, count in day.get('skills', {}).items():
                        skills[skill] = skills.get(skill, 0) + count
                    for kw, count in day.get('unknown', {}).items():
                        unknown[kw] = unknown.get(kw, 0) + count
            return jobs, skills, unknown

        jobs_30d, skills_30d, unknown_30d = aggregate_period(dates_30d)
        jobs_7d, skills_7d, unknown_7d = aggregate_period(dates_7d)
        jobs_prev_7d, skills_prev_7d, _ = aggregate_period(dates_prev_7d)

        print(f"\n{'='*75}")
        print(f"  STATISTIQUES DES SKILLS - Codeur.com (Rolling 30 jours)")
        print(f"{'='*75}")
        print(f"\n  Derniere MAJ: {stats.get('last_updated', 'N/A')[:19] if stats.get('last_updated') else 'N/A'}")
        print(f"  Periode: {dates_30d[-1]} -> {dates_30d[0]}")
        print(f"\n  Jobs analyses: {jobs_30d} (30j) | {jobs_7d} (7j) | {jobs_prev_7d} (7j precedents)")

        # Trend indicator
        def trend(current, previous):
            if previous == 0:
                return "NEW" if current > 0 else ""
            diff = current - previous
            pct = (diff / previous) * 100
            if diff > 0:
                return f"+{pct:.0f}%"
            elif diff < 0:
                return f"{pct:.0f}%"
            return "="

        # Skills sorted by 30d count with 7d trend
        if skills_30d:
            print(f"\n  {'-'*71}")
            print(f"  SKILLS CONNUS (30 jours):")
            print(f"  {'Skill':<15} {'30j':>6} {'7j':>6} {'Trend':>8}  {'Prev 7j':>8}")
            print(f"  {'-'*71}")
            sorted_skills = sorted(skills_30d.items(), key=lambda x: x[1], reverse=True)[:25]
            for skill_name, count_30d in sorted_skills:
                count_7d = skills_7d.get(skill_name, 0)
                count_prev = skills_prev_7d.get(skill_name, 0)
                trend_str = trend(count_7d, count_prev)
                print(f"    {skill_name:<15} {count_30d:>5} {count_7d:>6} {trend_str:>8}  {count_prev:>8}")

        # Unknown keywords
        if unknown_30d:
            print(f"\n  {'-'*71}")
            print(f"  KEYWORDS TECH INCONNUS (a indexer potentiellement):")
            print(f"  {'Keyword':<20} {'30j':>6} {'7j':>6}")
            print(f"  {'-'*71}")
            sorted_unknown = sorted(unknown_30d.items(), key=lambda x: x[1], reverse=True)[:20]
            for kw, count_30d in sorted_unknown:
                count_7d = unknown_7d.get(kw, 0)
                print(f"    {kw:<20} {count_30d:>5} {count_7d:>6}")

        # Daily breakdown (last 7 days)
        print(f"\n  {'-'*71}")
        print(f"  DETAIL JOURNALIER (7 derniers jours):")
        print(f"  {'-'*71}")
        for date in dates_7d:
            if date in daily_data:
                day = daily_data[date]
                top_skills = sorted(day.get('skills', {}).items(), key=lambda x: x[1], reverse=True)[:3]
                skills_str = ", ".join([f"{s[0]}({s[1]})" for s in top_skills])
                print(f"    {date}: {day.get('jobs_count', 0):3} jobs | {skills_str}")
            else:
                print(f"    {date}: -- pas de donnees --")

        print(f"\n{'='*75}\n")
        return

    if args.weekly_report:
        # Send weekly report to Discord
        scraper.send_weekly_report()
        return

    if args.debug:
        # Debug mode: show detailed skill matching for all projects
        projects = scraper.scrape_projects()
        # Collect skill stats on all projects
        scraper.collect_skill_stats(projects)
        filtered = scraper.filter_projects(projects)

        min_weight = config.get('ai_scoring', {}).get('min_weight', 5)

        print(f"\n{'='*60}")
        print(f"  DEBUG MODE - {len(projects)} projets RSS, {len(filtered)} apres filtrage")
        print(f"  Seuil poids minimum: {min_weight}")
        print(f"{'='*60}\n")

        for i, p in enumerate(filtered, 1):
            text = f"{p.get('title', '')} {p.get('description', '')} {p.get('category', '')}"
            matched = scraper._match_skills(text)
            weight = scraper._calculate_total_weight(matched)

            # Determine if would be sent to AI
            will_score = weight >= min_weight

            # Clean text for Windows console (remove emojis/special chars)
            def clean_text(text):
                return text.encode('ascii', 'ignore').decode('ascii') if text else 'N/A'

            print(f"[{i}/{len(filtered)}] {clean_text(p['title'][:55])}...")
            print(f"    Budget: {clean_text(p.get('budget_text', 'N/A'))}")
            print(f"    Categorie: {clean_text(p.get('category', 'N/A')[:50])}")
            print(f"    Description: {clean_text(p.get('description', 'N/A')[:80])}...")
            print()

            if matched:
                print(f"    Skills matches ({len(matched)}):")
                for s in sorted(matched, key=lambda x: x['weight'], reverse=True):
                    print(f"      - {s['name']:12} ('{s['matched_keyword']}') = {s['weight']:+3} pts")
            else:
                print(f"    Skills matches: AUCUN")

            print(f"    ----------------------------------------")
            print(f"    POIDS TOTAL: {weight:+3} pts")
            print(f"    >> HAIKU: {'OUI' if will_score else 'NON (poids < ' + str(min_weight) + ')'}")
            print()

        # Summary
        would_score = [p for p in filtered if scraper._calculate_total_weight(
            scraper._match_skills(f"{p.get('title', '')} {p.get('description', '')} {p.get('category', '')}")) >= min_weight]
        print(f"{'='*60}")
        print(f"  RESUME: {len(would_score)}/{len(filtered)} projets envoyes a Haiku")
        print(f"{'='*60}")

    elif args.dry_run:
        projects = scraper.scrape_projects()
        # Collect skill stats on all projects
        scraper.collect_skill_stats(projects)
        filtered = scraper.filter_projects(projects)
        print(f"\nFound {len(projects)} total projects")
        print(f"After keyword filtering: {len(filtered)} projects")

        # AI scoring in dry-run if enabled
        if filtered and config.get('ai_scoring', {}).get('enabled', False):
            print("\nRunning AI scoring...")
            filtered = scraper.score_projects(filtered)
            print(f"After AI scoring: {len(filtered)} projects (>= {config['ai_scoring'].get('min_score', 7)}/10)")

        for p in filtered[:5]:
            print(f"\n- {p.get('title')}")
            print(f"  URL: {p.get('url')}")
            print(f"  Budget: {p.get('budget_text')}")
            if p.get('ai_score'):
                print(f"  AI Score: {p.get('ai_score')}/10")
                if p.get('ai_reason'):
                    print(f"  Reason: {p.get('ai_reason')}")
    else:
        scraper.run()


if __name__ == "__main__":
    main()
