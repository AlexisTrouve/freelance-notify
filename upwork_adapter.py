#!/usr/bin/env python3
"""
Upwork Adapter for Freelance Notify
Wraps the Upwork-AI-jobs-applier scraper with our skills/Discord system.
NO auto-posting - just scrape, score, and notify.
"""

import sys
import json
import asyncio
import logging
import argparse
from pathlib import Path
from datetime import datetime

# Add the submodule to path
sys.path.insert(0, str(Path(__file__).parent / 'adapters' / 'upwork'))

from adapters.upwork.src.scraper import UpworkJobScraper
from adapters.upwork.src.utils import read_text_file
import requests
import re

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class UpworkAdapter:
    """
    Adapter that uses Upwork-AI-jobs-applier scraping but our scoring/notification system.
    """

    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self.skills_index = self._load_skills_index()
        self.base_profile = self._load_profile()
        self.seen_jobs = self._load_seen_jobs()
        self.scraper = UpworkJobScraper(batch_size=3)  # Lower batch for stability

    def _load_config(self, config_path: str) -> dict:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _load_skills_index(self) -> dict:
        skills_path = Path('files/keywords/skills_index.json')
        if skills_path.exists():
            with open(skills_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"skills": {}, "weight_table": {}}

    def _load_profile(self) -> str:
        profile_path = Path(self.config.get('profile_file', 'files/profile.md'))
        if profile_path.exists():
            with open(profile_path, 'r', encoding='utf-8') as f:
                return f.read()
        return ""

    def _load_seen_jobs(self) -> set:
        seen_file = Path('seen_upwork_jobs.json')
        if seen_file.exists():
            with open(seen_file, 'r') as f:
                return set(json.load(f))
        return set()

    def _save_seen_jobs(self):
        seen_file = Path('seen_upwork_jobs.json')
        with open(seen_file, 'w') as f:
            json.dump(list(self.seen_jobs), f)

    def _match_skills(self, text: str) -> list[dict]:
        """Match job text against skill keywords (same as main scraper)"""
        text_lower = text.lower()
        matched = []

        for skill_name, skill_data in self.skills_index.get('skills', {}).items():
            keywords = skill_data.get('keywords', [])
            for keyword in keywords:
                keyword_lower = keyword.lower()
                pattern = r'\b' + re.escape(keyword_lower) + r'\b'
                if re.search(pattern, text_lower):
                    matched.append({
                        'name': skill_name,
                        'score': skill_data.get('score', 0),
                        'weight': skill_data.get('weight', 0),
                        'matched_keyword': keyword
                    })
                    break

        return matched

    def _calculate_total_weight(self, matched_skills: list[dict]) -> int:
        return sum(skill.get('weight', 0) for skill in matched_skills)

    def _assemble_profile(self, matched_skills: list[dict]) -> str:
        """Assemble dynamic profile from matched skills"""
        parts = []

        if self.base_profile:
            parts.append("# Freelancer Profile\n")
            parts.append(self.base_profile)
            parts.append("\n---\n")

        if matched_skills:
            parts.append("# Relevant Skills for this Project\n")
            sorted_skills = sorted(matched_skills, key=lambda x: x.get('weight', 0), reverse=True)

            for skill in sorted_skills:
                skill_path = Path('files/keywords') / f"{skill['name']}.md"
                if skill_path.exists():
                    with open(skill_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        parts.append(f"\n## {skill['name'].upper()} (Score: {skill['score']}/10)\n")
                        parts.append(content)

        return "\n".join(parts)

    def score_job_with_ai(self, job: dict, dynamic_profile: str) -> dict:
        """Score a job using Claude Haiku with our dynamic profile"""
        api_key = self.config.get('anthropic_api_key')
        if not api_key:
            return job

        scoring_config = self.config.get('ai_scoring', {})
        if not scoring_config.get('enabled', False):
            return job

        try:
            job_text = f"""
Title: {job.get('title', 'N/A')}
Description: {job.get('description', 'N/A')}
Budget/Rate: {job.get('payment_rate', 'N/A')}
Experience Level: {job.get('experience_level', 'N/A')}
Job Type: {job.get('job_type', 'N/A')}
Client Location: {job.get('client_location', 'N/A')}
Client History: {job.get('client_total_spent', 'N/A')} spent, {job.get('client_jobs_posted', 'N/A')} jobs posted
URL: {job.get('link', 'N/A')}
"""

            prompt = f"""You are a job matching expert. Score this job from 1-10 based on fit with the freelancer profile.

Freelancer Profile:
{dynamic_profile}

IMPORTANT: Respond with ONLY a JSON object:
{{"score": <number>, "reason": "<brief explanation>"}}
"""

            response = requests.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'Content-Type': 'application/json',
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01'
                },
                json={
                    'model': scoring_config.get('model', 'claude-haiku-4-5-20251001'),
                    'max_tokens': 200,
                    'temperature': 0.1,
                    'system': prompt,
                    'messages': [
                        {'role': 'user', 'content': f"Score this job:\n\n{job_text}"}
                    ]
                },
                timeout=30
            )
            response.raise_for_status()

            result = response.json()
            content = result.get('content', [{}])[0].get('text', '{}')

            # Parse response
            json_content = content
            if '```' in content:
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
                if json_match:
                    json_content = json_match.group(1)

            score_data = json.loads(json_content)
            job['ai_score'] = score_data.get('score', 0)
            job['ai_reason'] = score_data.get('reason', '')

        except Exception as e:
            logger.error(f"Error scoring job: {e}")
            job['ai_score'] = 0
            job['ai_reason'] = str(e)

        return job

    def send_discord_notification(self, jobs: list[dict]):
        """Send jobs to Discord webhook"""
        webhook_url = self.config.get('discord_webhook_url')
        if not webhook_url or 'YOUR_WEBHOOK' in webhook_url:
            logger.warning("Discord webhook not configured")
            return

        embeds = []
        for job in jobs[:10]:
            ai_score = job.get('ai_score', 0)
            if ai_score >= 8:
                color = 3066993  # Green
            elif ai_score >= 6:
                color = 3447003  # Blue
            else:
                color = 15105570  # Orange

            embed = {
                "title": f"[Upwork] {job.get('title', 'New Job')[:200]}",
                "url": job.get('link'),
                "color": color,
                "fields": [],
                "timestamp": datetime.now().isoformat()
            }

            if job.get('description'):
                embed["description"] = job['description'][:500]

            if ai_score > 0:
                embed["fields"].append({
                    "name": "🎯 AI Score",
                    "value": f"**{ai_score}/10**",
                    "inline": True
                })

            matched_skills = job.get('matched_skills', [])
            if matched_skills:
                skills_text = ", ".join(matched_skills[:5])
                embed["fields"].append({
                    "name": "🔧 Skills",
                    "value": skills_text,
                    "inline": True
                })

            if job.get('payment_rate'):
                embed["fields"].append({
                    "name": "💰 Rate",
                    "value": job['payment_rate'],
                    "inline": True
                })

            if job.get('experience_level'):
                embed["fields"].append({
                    "name": "📊 Level",
                    "value": job['experience_level'],
                    "inline": True
                })

            if job.get('client_total_spent'):
                embed["fields"].append({
                    "name": "👤 Client",
                    "value": f"${job['client_total_spent']} spent",
                    "inline": True
                })

            if job.get('ai_reason'):
                embed["footer"] = {"text": f"💡 {job['ai_reason'][:200]}"}

            embeds.append(embed)

        if not embeds:
            return

        payload = {
            "content": f"**{len(embeds)} new Upwork job(s) found**",
            "embeds": embeds
        }

        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"Sent {len(embeds)} Upwork jobs to Discord")
        except requests.RequestException as e:
            logger.error(f"Error sending to Discord: {e}")

    async def scrape_and_notify(self, search_query: str, num_jobs: int = 20):
        """Main method: scrape Upwork, apply our scoring, notify Discord"""
        logger.info(f"Scraping Upwork for: {search_query}")

        # Scrape using their code
        jobs = await self.scraper.scrape_upwork_data(search_query, num_jobs)
        logger.info(f"Scraped {len(jobs)} jobs from Upwork")

        # Filter already seen
        new_jobs = [j for j in jobs if j.get('job_id') not in self.seen_jobs]
        logger.info(f"Found {len(new_jobs)} new jobs")

        if not new_jobs:
            return []

        # Apply our skills matching and scoring
        scoring_config = self.config.get('ai_scoring', {})
        min_weight = scoring_config.get('min_weight', 5)
        min_score = scoring_config.get('min_score', 5)

        scored_jobs = []
        for job in new_jobs:
            # Build text for matching
            text = f"{job.get('title', '')} {job.get('description', '')} {job.get('required_skills', '')}"

            # Match skills
            matched_skills = self._match_skills(text)
            total_weight = self._calculate_total_weight(matched_skills)

            job['matched_skills'] = [s['name'] for s in matched_skills]
            job['total_weight'] = total_weight

            # Skip if weight too low
            if total_weight < min_weight:
                logger.debug(f"Skipping '{job.get('title', '')[:50]}...' - weight {total_weight} < {min_weight}")
                continue

            # Score with AI using dynamic profile
            dynamic_profile = self._assemble_profile(matched_skills)
            job = self.score_job_with_ai(job, dynamic_profile)

            if job.get('ai_score', 0) >= min_score:
                scored_jobs.append(job)
                logger.info(f"  ✓ {job.get('title', '')[:50]}... - Score: {job.get('ai_score')}/10")

            # Mark as seen
            if job.get('job_id'):
                self.seen_jobs.add(job['job_id'])

        self._save_seen_jobs()

        # Send to Discord
        if scored_jobs:
            self.send_discord_notification(scored_jobs)

        logger.info(f"Upwork scrape complete: {len(scored_jobs)} jobs passed scoring")
        return scored_jobs

    def run(self, search_query: str, num_jobs: int = 20):
        """Sync wrapper for async scrape"""
        return asyncio.run(self.scrape_and_notify(search_query, num_jobs))


def main():
    parser = argparse.ArgumentParser(description='Upwork Adapter for Freelance Notify')
    parser.add_argument('--config', default='config.json', help='Config file path')
    parser.add_argument('--query', default='VBA automation', help='Search query')
    parser.add_argument('--num-jobs', type=int, default=20, help='Number of jobs to scrape')
    parser.add_argument('--dry-run', action='store_true', help='Scrape but do not notify')
    args = parser.parse_args()

    adapter = UpworkAdapter(config_path=args.config)

    if args.dry_run:
        async def dry_run():
            jobs = await adapter.scraper.scrape_upwork_data(args.query, args.num_jobs)
            print(f"\nScraped {len(jobs)} jobs from Upwork:\n")
            for i, job in enumerate(jobs[:5], 1):
                print(f"{i}. {job.get('title', 'N/A')}")
                print(f"   Rate: {job.get('payment_rate', 'N/A')}")
                print(f"   Level: {job.get('experience_level', 'N/A')}")
                print(f"   URL: {job.get('link', 'N/A')}")
                print()
        asyncio.run(dry_run())
    else:
        adapter.run(args.query, args.num_jobs)


if __name__ == "__main__":
    main()
