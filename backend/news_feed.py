"""
NSE Volatility Scanner — News Feed
Fetches latest market news from RSS feeds.
"""

import logging
from datetime import datetime
from typing import List

import feedparser

from backend.config import NEWS_RSS_FEEDS
from backend.signal import NewsItem

logger = logging.getLogger(__name__)

# Cache
_news_cache: List[NewsItem] = []
_news_cache_time: datetime = None


def fetch_news(max_items: int = 30, force_refresh: bool = False) -> List[NewsItem]:
    """Fetch latest news from configured RSS feeds."""
    global _news_cache, _news_cache_time

    # Cache for 2 minutes
    if (
        not force_refresh
        and _news_cache_time
        and (datetime.now() - _news_cache_time).total_seconds() < 120
        and _news_cache
    ):
        return _news_cache[:max_items]

    all_news: List[NewsItem] = []

    for feed_config in NEWS_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_config["url"])
            for entry in feed.entries[:15]:
                title = entry.get("title", "").strip()
                if not title:
                    continue

                # Parse published date
                published = ""
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        published = entry.get("published", "")
                elif hasattr(entry, "published"):
                    published = entry.published

                link = entry.get("link", "")

                news_item = NewsItem(
                    headline=title,
                    source=feed_config["name"],
                    published=published,
                    link=link,
                )
                all_news.append(news_item)

        except Exception as e:
            logger.error(f"Error fetching RSS feed {feed_config['name']}: {e}")

    # Sort by published date (newest first)
    all_news.sort(key=lambda x: x.published, reverse=True)

    # Deduplicate by headline similarity
    seen = set()
    unique_news = []
    for item in all_news:
        key = item.headline[:50].lower()
        if key not in seen:
            seen.add(key)
            unique_news.append(item)

    _news_cache = unique_news
    _news_cache_time = datetime.now()

    logger.info(f"Fetched {len(unique_news)} unique news items from {len(NEWS_RSS_FEEDS)} feeds")
    return unique_news[:max_items]
