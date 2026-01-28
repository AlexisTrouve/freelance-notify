#!/usr/bin/env python3
"""
MCP Server for Upwork Scraper
Allows AI to trigger Upwork scraping jobs.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Import our adapter
from upwork_adapter import UpworkAdapter, find_firefox_profile

server = Server("upwork-scraper")

# Predefined queries
PRESET_QUERIES = {
    "vba": "VBA Excel automation macro",
    "python": "Python scripting automation",
    "api": "API integration REST webhook",
    "discord": "Discord bot",
    "ai": "ChatGPT LLM AI integration",
    "web": "web scraping automation",
}


@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="scrape_upwork",
            description="""Scrape Upwork for freelance jobs matching a query.

IMPORTANT: This launches a visible Firefox browser. The user must solve the Cloudflare captcha manually.
After captcha is solved, jobs are scraped, scored, and sent to Discord.

Preset queries available: vba, python, api, discord, ai, web
Or use a custom query string.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query or preset name (vba, python, api, discord, ai, web)"
                    },
                    "num_jobs": {
                        "type": "integer",
                        "description": "Number of jobs to scrape (default: 20, max: 50)",
                        "default": 20
                    },
                    "dry_run": {
                        "type": "boolean",
                        "description": "If true, scrape but don't send to Discord",
                        "default": False
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="list_upwork_presets",
            description="List available preset queries for Upwork scraping",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="check_upwork_status",
            description="Check if Upwork scraping is possible (Firefox profile exists, cookies available)",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "list_upwork_presets":
        result = "Available Upwork query presets:\n\n"
        for key, query in PRESET_QUERIES.items():
            result += f"- **{key}**: {query}\n"
        result += "\nUse these with scrape_upwork tool."
        return [TextContent(type="text", text=result)]

    elif name == "check_upwork_status":
        profile = find_firefox_profile()
        if not profile:
            return [TextContent(
                type="text",
                text="[ERROR] No Firefox profile found.\n\nTo use Upwork scraper:\n1. Install Firefox\n2. Log in to Upwork\n3. Close Firefox"
            )]

        # Check for cookies
        cookies_db = Path(profile) / 'cookies.sqlite'
        if not cookies_db.exists():
            return [TextContent(
                type="text",
                text=f"[WARNING] Firefox profile found but no cookies.sqlite\nProfile: {profile}"
            )]

        return [TextContent(
            type="text",
            text=f"[OK] Upwork scraper ready\n\nFirefox profile: {profile}\nCookies database: exists\n\nNote: User must solve Cloudflare captcha when browser opens."
        )]

    elif name == "scrape_upwork":
        query = arguments.get("query", "")
        num_jobs = min(arguments.get("num_jobs", 20), 50)
        dry_run = arguments.get("dry_run", False)

        # Resolve preset
        if query.lower() in PRESET_QUERIES:
            actual_query = PRESET_QUERIES[query.lower()]
        else:
            actual_query = query

        # Check Firefox
        profile = find_firefox_profile()
        if not profile:
            return [TextContent(
                type="text",
                text="[ERROR] No Firefox profile found. Cannot scrape Upwork."
            )]

        # Launch scraping
        try:
            adapter = UpworkAdapter(firefox_profile=profile)

            if dry_run:
                # Dry run - just scrape and return results
                jobs = await adapter.scrape_jobs(actual_query, num_jobs, headless=False)

                if not jobs:
                    return [TextContent(
                        type="text",
                        text=f"[DRY RUN] Scraped 0 jobs for query: {actual_query}\n\nPossible reasons:\n- Cloudflare captcha not solved\n- No jobs matching query\n- Not logged in to Upwork"
                    )]

                result = f"[DRY RUN] Scraped {len(jobs)} jobs for: {actual_query}\n\n"
                for i, job in enumerate(jobs[:10], 1):
                    result += f"{i}. {job.get('title', 'N/A')[:60]}\n"
                    result += f"   Rate: {job.get('payment_rate', 'N/A')}\n"
                    result += f"   Link: {job.get('link', 'N/A')}\n\n"

                return [TextContent(type="text", text=result)]
            else:
                # Full run with Discord notification
                scored_jobs = await adapter.scrape_and_notify(actual_query, num_jobs, headless=False)

                if not scored_jobs:
                    return [TextContent(
                        type="text",
                        text=f"No qualifying jobs found for: {actual_query}\n\nJobs must pass weight threshold and AI scoring to be notified."
                    )]

                return [TextContent(
                    type="text",
                    text=f"[OK] Sent {len(scored_jobs)} jobs to Discord for query: {actual_query}"
                )]

        except Exception as e:
            return [TextContent(
                type="text",
                text=f"[ERROR] Scraping failed: {str(e)}"
            )]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
