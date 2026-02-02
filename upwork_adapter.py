#!/usr/bin/env python3
"""
Upwork Adapter for Freelance Notify
Uses Camoufox (stealth Firefox) to bypass Cloudflare.
NO auto-posting - just scrape, score, and notify.
"""

import sys
import json
import asyncio
import logging
import argparse
import os
import hashlib
import random
from pathlib import Path
from datetime import datetime
import requests
import re
try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False  # Linux

from camoufox.async_api import AsyncCamoufox
from camoufox_captcha import solve_captcha
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# User agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


class UpworkAdapter:
    """
    Adapter that scrapes Upwork using Patchright and applies our scoring system.
    """

    def __init__(self, config_path: str = "config.json"):
        self.config = self._load_config(config_path)
        self.skills_index = self._load_skills_index()
        self.base_profile = self._load_profile()
        self.seen_jobs = self._load_seen_jobs()

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
        """Match job text against skill keywords"""
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

    def _extract_job_id(self, url: str) -> str:
        """Extract job ID from URL and hash it"""
        match = re.search(r'/jobs/[^/]+/(\d+)', url)
        if match:
            return hashlib.sha256(match.group(1).encode()).hexdigest()[:16]
        match = re.search(r'apply/([^/?]+)', url)
        if match:
            return hashlib.sha256(match.group(1).encode()).hexdigest()[:16]
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    async def scrape_jobs(self, search_query: str, num_jobs: int = 20, headless: bool = True, num_pages: int = 1) -> list[dict]:
        """Scrape Upwork jobs using Camoufox (stealth Firefox)"""
        jobs = []
        jobs_per_page = min(num_jobs, 15)  # Upwork shows max ~15 per page

        try:
            # Launch Camoufox with stealth settings + captcha solving config
            # Use "virtual" on Linux for Xvfb virtual display
            headless_mode = "virtual" if headless and not HAS_WINSOUND else headless
            async with AsyncCamoufox(
                headless=headless_mode,
                humanize=True,
                i_know_what_im_doing=True,  # Suppress COOP warning
                config={'forceScopeAccess': True},  # Required for captcha solving
                disable_coop=True  # Required for cross-origin iframe access
            ) as browser:
                page = await browser.new_page()

                for page_num in range(1, num_pages + 1):
                    url = f"https://www.upwork.com/nx/search/jobs?q={search_query}&sort=recency&page={page_num}&per_page={jobs_per_page}"
                    logger.info(f"Scraping page {page_num}: {url}")

                    # Navigate to Upwork
                    await page.goto(url, wait_until='domcontentloaded', timeout=60000)

                    # Random delay to appear human
                    await asyncio.sleep(random.uniform(2, 4))

                    # Wait for job tiles to load
                    try:
                        await page.wait_for_selector('section[data-test="JobTile"], h2.job-tile-title', timeout=15000)
                    except:
                        pass  # May not find if no results

                    html = await page.content()

                    # Check for Cloudflare (usually only on first page)
                    cloudflare_wait = 0
                    max_cloudflare_wait = 120  # Wait up to 2 minutes

                    # More specific Cloudflare detection
                    def is_cloudflare_challenge(content):
                        challenge_indicators = ['Just a moment' in content, 'challenge-platform' in content, 'cf-turnstile' in content]
                        has_jobs = 'job-tile' in content.lower() or 'JobTile' in content
                        return any(challenge_indicators) and not has_jobs

                    # Try auto-solving Cloudflare first
                    if is_cloudflare_challenge(html):
                        logger.warning("Cloudflare challenge detected - attempting auto-solve...")

                        try:
                            turnstile = await page.query_selector('[class*="turnstile"], [class*="cf-turnstile"], iframe[src*="challenges.cloudflare"]')
                            if turnstile:
                                logger.info("Found Turnstile widget, attempting auto-solve...")
                                success = await solve_captcha(turnstile, captcha_type="cloudflare", challenge_type="turnstile")
                                if success:
                                    logger.info("Auto-solve succeeded!")
                                    await asyncio.sleep(3)
                                    html = await page.content()
                            else:
                                logger.info("No Turnstile widget found, trying coordinate click...")
                                for frame in page.frames:
                                    if 'challenges.cloudflare.com' in frame.url:
                                        frame_elem = await frame.frame_element()
                                        box = await frame_elem.bounding_box()
                                        if box:
                                            await page.mouse.click(box['x'] + 30, box['y'] + 25)
                                            logger.info("Clicked Cloudflare checkbox by coordinates")
                                            await asyncio.sleep(5)
                                            try:
                                                await page.wait_for_selector('section[data-test="JobTile"]', timeout=10000)
                                                logger.info("Jobs loaded after coordinate click!")
                                            except:
                                                pass
                                            html = await page.content()
                                            break
                        except Exception as e:
                            logger.debug(f"Auto-solve attempt failed: {e}")

                    # If still blocked, wait for manual solve
                    while is_cloudflare_challenge(html):
                        if cloudflare_wait == 0:
                            logger.warning("Auto-solve failed - waiting for manual captcha click...")
                            print("\n" + "="*60)
                            print("  CLOUDFLARE DETECTED - Please click the captcha!")
                            print("="*60 + "\n")
                            if HAS_WINSOUND and not headless:
                                try:
                                    for _ in range(3):
                                        winsound.Beep(1000, 200)
                                        await asyncio.sleep(0.1)
                                except:
                                    pass

                        await asyncio.sleep(5)
                        cloudflare_wait += 5
                        try:
                            html = await page.content()
                        except:
                            await asyncio.sleep(2)
                            html = await page.content() if await page.content() else ""

                        if not is_cloudflare_challenge(html):
                            break
                        if cloudflare_wait >= max_cloudflare_wait:
                            logger.error(f"Cloudflare still blocking after {max_cloudflare_wait}s")
                            return jobs  # Return what we have so far
                        if cloudflare_wait % 15 == 0:
                            logger.info(f"  Waiting for Cloudflare... ({cloudflare_wait}s)")

                    if cloudflare_wait > 0:
                        logger.info("Cloudflare bypassed!")
                        await asyncio.sleep(3)
                        try:
                            await page.wait_for_selector('section[data-test="JobTile"]', timeout=10000)
                        except:
                            pass
                        html = await page.content()

                    # Parse jobs from this page
                    soup = BeautifulSoup(html, 'html.parser')
                    job_tiles = soup.find_all('section', {'data-test': 'JobTile'})
                    if not job_tiles:
                        job_tiles = soup.find_all('article', class_=lambda x: x and 'job-tile' in x.lower() if x else False)

                    logger.info(f"Found {len(job_tiles)} job tiles on page {page_num}")

                    if not job_tiles:
                        logger.info("No more jobs found, stopping pagination")
                        break

                    # Extract job info from tiles
                    page_jobs = 0
                    for tile in job_tiles:
                        try:
                            job = self._parse_job_tile(tile)
                            if job:
                                jobs.append(job)
                                page_jobs += 1
                        except Exception as e:
                            logger.debug(f"Error parsing job tile: {e}")

                    logger.info(f"Extracted {page_jobs} jobs from page {page_num}")

                    # Check if we have enough jobs
                    if len(jobs) >= num_jobs:
                        logger.info(f"Reached target of {num_jobs} jobs")
                        break

                    # Delay between pages (human-like)
                    if page_num < num_pages:
                        delay = random.uniform(3, 6)
                        logger.info(f"Waiting {delay:.1f}s before next page...")
                        await asyncio.sleep(delay)

        except Exception as e:
            logger.error(f"Scraping error: {e}")

        return jobs

    def _parse_job_tile(self, tile) -> dict:
        """Parse a job tile element into job dict"""
        job = {}

        def clean_text(elem):
            """Extract text with proper spacing (handles highlight spans)"""
            # Use separator to avoid concatenating words
            text = elem.get_text(separator=' ', strip=True)
            # Clean up multiple spaces
            text = re.sub(r'\s+', ' ', text)
            return text.strip()

        # Title - try multiple selectors
        title_elem = tile.find('a', class_=lambda x: x and 'job-tile-title' in str(x).lower() if x else False)
        if not title_elem:
            title_elem = tile.find('h2', class_=lambda x: x and 'title' in str(x).lower() if x else False)
        if not title_elem:
            title_elem = tile.find('a', href=lambda x: x and '/jobs/' in str(x) if x else False)

        if title_elem:
            job['title'] = clean_text(title_elem)
            href = title_elem.get('href', '')
            if href:
                job['link'] = f"https://www.upwork.com{href}" if href.startswith('/') else href
                job['job_id'] = self._extract_job_id(job['link'])

        # If no link found, try to find any job link in the tile
        if not job.get('link'):
            job_link = tile.find('a', href=lambda x: x and '/jobs/' in str(x) if x else False)
            if job_link:
                href = job_link.get('href', '')
                job['link'] = f"https://www.upwork.com{href}" if href.startswith('/') else href
                job['job_id'] = self._extract_job_id(job['link'])
                if not job.get('title'):
                    job['title'] = clean_text(job_link)

        # Description - Upwork uses "UpCLineClamp JobDescription"
        desc_elem = tile.find(attrs={'data-test': 'UpCLineClamp JobDescription'})
        if not desc_elem:
            desc_elem = tile.find(attrs={'data-test': lambda x: x and 'JobDescription' in str(x) if x else False})
        if not desc_elem:
            desc_elem = tile.find('p', class_=lambda x: x and 'description' in str(x).lower() if x else False)
        if not desc_elem:
            # Try finding any long text block
            for p in tile.find_all(['p', 'span', 'div']):
                text = p.get_text(strip=True)
                if len(text) > 80 and 'Posted' not in text and '$' not in text[:20]:
                    desc_elem = p
                    break
        if desc_elem:
            job['description'] = clean_text(desc_elem)[:1000]

        # Budget/Rate
        budget_elem = tile.find(string=re.compile(r'\$[\d,]+'))
        if budget_elem:
            job['payment_rate'] = budget_elem.strip()

        # Experience level
        for level in ['Entry Level', 'Intermediate', 'Expert']:
            if tile.find(string=re.compile(level, re.I)):
                job['experience_level'] = level
                break

        # Skills/Tags
        skill_tags = tile.find_all('a', class_=lambda x: x and 'skill' in str(x).lower() if x else False)
        if not skill_tags:
            skill_tags = tile.find_all('span', class_=lambda x: x and 'skill' in str(x).lower() if x else False)
        if skill_tags:
            job['required_skills'] = ', '.join([s.get_text(strip=True) for s in skill_tags[:10]])

        return job if job.get('title') else None

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
Skills: {job.get('required_skills', 'N/A')}
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
        """Send jobs to Discord webhook (format matching Codeur.com)"""
        webhook_url = self.config.get('discord_webhook_url')
        if not webhook_url or 'YOUR_WEBHOOK' in webhook_url:
            logger.warning("Discord webhook not configured")
            return

        embeds = []
        for job in jobs[:10]:
            ai_score = job.get('ai_score', 0)
            # Color coding by score for quick visual identification
            if ai_score >= 10:
                color = 15844367  # Gold - perfect match
            elif ai_score >= 9:
                color = 3066993   # Green - excellent
            elif ai_score >= 8:
                color = 3447003   # Blue - very good
            else:  # 7
                color = 15105570  # Orange - good

            embed = {
                "title": job.get('title', 'New Job')[:256],
                "url": job.get('link'),
                "color": color,
                "fields": [],
                "timestamp": datetime.now().isoformat()
            }

            if job.get('description'):
                embed["description"] = job['description'][:500]

            # AI Score field
            if ai_score > 0:
                embed["fields"].append({
                    "name": "\U0001F3AF Score AI",
                    "value": f"**{ai_score}/10**",
                    "inline": True
                })

            # Matched skills field
            matched_skills = job.get('matched_skills', [])
            if matched_skills:
                skills_text = ", ".join(matched_skills[:5])
                if len(matched_skills) > 5:
                    skills_text += f" (+{len(matched_skills) - 5})"
                embed["fields"].append({
                    "name": "\U0001F527 Skills",
                    "value": skills_text,
                    "inline": True
                })

            # Budget/Rate field
            if job.get('payment_rate'):
                embed["fields"].append({
                    "name": "\U0001F4B0 Budget",
                    "value": job['payment_rate'],
                    "inline": True
                })

            # Experience level field
            if job.get('experience_level'):
                embed["fields"].append({
                    "name": "\U0001F4BC Niveau",
                    "value": job['experience_level'],
                    "inline": True
                })

            # AI reason as footer
            if job.get('ai_reason'):
                embed["footer"] = {"text": f"\U0001F4A1 {job['ai_reason'][:200]}"}

            embeds.append(embed)

        if not embeds:
            return

        payload = {
            "content": f"**{len(embeds)} nouveau(x) projet(s) sur Upwork**",
            "embeds": embeds
        }

        try:
            response = requests.post(webhook_url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"Sent {len(embeds)} Upwork jobs to Discord")
        except requests.RequestException as e:
            logger.error(f"Error sending to Discord: {e}")

    async def scrape_and_notify(self, search_query: str, num_jobs: int = 20, headless: bool = True, num_pages: int = 2):
        """Main method: scrape Upwork, apply our scoring, notify Discord"""
        logger.info(f"Scraping Upwork for: {search_query}")

        # Scrape jobs
        jobs = await self.scrape_jobs(search_query, num_jobs, headless, num_pages)
        logger.info(f"Scraped {len(jobs)} jobs from Upwork")

        if not jobs:
            return []

        # Filter already seen
        new_jobs = [j for j in jobs if j.get('job_id') not in self.seen_jobs]
        logger.info(f"Found {len(new_jobs)} new jobs (filtered {len(jobs) - len(new_jobs)} seen)")

        if not new_jobs:
            return []

        # Apply our skills matching and scoring
        scoring_config = self.config.get('ai_scoring', {})
        min_weight = scoring_config.get('min_weight', 5)
        min_score = scoring_config.get('upwork_min_score', 8)

        scored_jobs = []
        for job in new_jobs:
            # Build text for matching
            text = f"{job.get('title', '')} {job.get('description', '')} {job.get('required_skills', '')}"

            # Match skills
            matched_skills = self._match_skills(text)
            total_weight = self._calculate_total_weight(matched_skills)

            job['matched_skills'] = [s['name'] for s in matched_skills]
            job['total_weight'] = total_weight

            logger.debug(f"Job '{job.get('title', '')[:40]}' - Weight: {total_weight}, Skills: {job['matched_skills']}")

            # Skip if weight too low
            if total_weight < min_weight:
                logger.debug(f"  Skipping - weight {total_weight} < {min_weight}")
                continue

            # Score with AI using dynamic profile
            dynamic_profile = self._assemble_profile(matched_skills)
            job = self.score_job_with_ai(job, dynamic_profile)

            if job.get('ai_score', 0) >= min_score:
                scored_jobs.append(job)
                logger.info(f"  [OK] {job.get('title', '')[:50]}... - Score: {job.get('ai_score')}/10")

            # Mark as seen
            if job.get('job_id'):
                self.seen_jobs.add(job['job_id'])

        self._save_seen_jobs()

        # Send to Discord
        if scored_jobs:
            self.send_discord_notification(scored_jobs)

        logger.info(f"Upwork scrape complete: {len(scored_jobs)} jobs passed scoring")
        return scored_jobs

    def run(self, search_query: str, num_jobs: int = 20, headless: bool = True, num_pages: int = 2):
        """Sync wrapper for async scrape"""
        return asyncio.run(self.scrape_and_notify(search_query, num_jobs, headless, num_pages))


def main():
    parser = argparse.ArgumentParser(description='Upwork Adapter for Freelance Notify')
    parser.add_argument('--config', default='config.json', help='Config file path')
    parser.add_argument('--query', default='VBA automation', help='Search query')
    parser.add_argument('--num-jobs', type=int, default=20, help='Number of jobs to scrape')
    parser.add_argument('--pages', type=int, default=2, help='Number of pages to scrape (default: 2)')
    parser.add_argument('--dry-run', action='store_true', help='Scrape but do not notify or score')
    parser.add_argument('--visible', action='store_true', help='Show browser window (for debugging)')
    args = parser.parse_args()

    adapter = UpworkAdapter(config_path=args.config)

    print(f"\n[*] Camoufox (stealth Firefox)")
    print(f"[*] Search query: {args.query}")
    print(f"[*] Max jobs: {args.num_jobs}")
    print(f"[*] Pages: {args.pages}")
    print(f"[*] Headless: {not args.visible}")
    print()

    if args.dry_run:
        async def dry_run():
            jobs = await adapter.scrape_jobs(args.query, args.num_jobs, headless=not args.visible, num_pages=args.pages)
            print(f"\n{'='*60}")
            print(f"  Scraped {len(jobs)} jobs from Upwork (dry-run)")
            print(f"{'='*60}\n")

            for i, job in enumerate(jobs[:20], 1):
                # Match skills for display
                text = f"{job.get('title', '')} {job.get('description', '')} {job.get('required_skills', '')}"
                matched = adapter._match_skills(text)
                weight = adapter._calculate_total_weight(matched)
                skills_str = ', '.join([m['name'] for m in matched]) or 'None'

                # Sanitize for Windows console encoding
                title = job.get('title', 'N/A')[:60].encode('ascii', 'replace').decode('ascii')
                print(f"{i}. {title}")
                print(f"   Rate: {job.get('payment_rate', 'N/A')} | Level: {job.get('experience_level', 'N/A')}")
                print(f"   Skills: {skills_str} (weight: {weight})")
                print(f"   Link: {job.get('link', 'N/A')}")
                print()

        asyncio.run(dry_run())
    else:
        adapter.run(args.query, args.num_jobs, headless=not args.visible, num_pages=args.pages)


if __name__ == "__main__":
    main()
