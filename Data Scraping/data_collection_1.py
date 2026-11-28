import csv
import hashlib
import json
import os
import random
import re
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


class ProperNepaliNewsScraper:
    """Scraper for collecting and normalizing Nepali news articles across multiple portals."""

    def __init__(self):
        """Initialize request headers, source configurations, deduplication state, and output directories."""
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }

        self.sources = {
            "onlinekhabar": {
                "base": "https://www.onlinekhabar.com",
                "start_pages": [
                    "https://www.onlinekhabar.com/content/news",
                    "https://www.onlinekhabar.com/content/news/politics",
                    "https://www.onlinekhabar.com/content/news/economy",
                    "https://www.onlinekhabar.com/content/news/sports",
                    "https://www.onlinekhabar.com/content/news/entertainment",
                ],
                "article_pattern": "/content/",
                "max_pages": 40,
                "target": 300,
                "display_name": "Online Khabar",
            },
            "kantipur": {
                "base": "https://ekantipur.com",
                "start_pages": [
                    "https://ekantipur.com/news",
                    "https://ekantipur.com/news/politics",
                    "https://ekantipur.com/news/business",
                    "https://ekantipur.com/news/sports",
                    "https://ekantipur.com/news/world",
                    "https://ekantipur.com/opinion",
                ],
                "article_pattern": "/news/",
                "max_pages": 40,
                "target": 300,
                "display_name": "Kantipur",
            },
            "ratopati": {
                "base": "https://www.ratopati.com",
                "start_pages": [
                    "https://www.ratopati.com/category/news",
                    "https://www.ratopati.com/category/politics",
                    "https://www.ratopati.com/category/economy",
                    "https://www.ratopati.com/category/sports",
                    "https://www.ratopati.com/category/entertainment",
                ],
                "article_pattern": "/story/",
                "max_pages": 35,
                "target": 300,
                "display_name": "Ratopati",
            },
        }

        self.seen_hashes = set()

        # Isolate each run under a timestamped directory to prevent overwriting prior datasets.
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.main_output_dir = f"nepali_news_dataset_{self.timestamp}"
        self.csv_dir = os.path.join(self.main_output_dir, "csv_files")
        self.json_dir = os.path.join(self.main_output_dir, "json_files")

        os.makedirs(self.csv_dir, exist_ok=True)
        os.makedirs(self.json_dir, exist_ok=True)

    def clean_text(self, text):
        """Normalize consecutive whitespace characters and trim leading/trailing spaces."""
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def is_nepali(self, text):
        """Return True if the text contains at least one Devanagari Unicode character."""
        return bool(re.search(r"[\u0900-\u097F]", text))

    def is_valid_article(self, content, title):
        """Validate minimum length, Devanagari script presence, and sentence structure."""
        if not content or not title:
            return False
        if len(content) < 300:
            return False
        if len(title) < 10:
            return False
        if not self.is_nepali(content):
            return False
        # Require at least two purna viram delimiters to filter truncated snippets.
        if content.count("।") < 2:
            return False
        return True

    def extract_title(self, soup):
        """Extract the article headline using fallback selectors from h1 to page title."""
        title_tag = soup.find("h1")
        if title_tag:
            return self.clean_text(title_tag.text)

        meta_title = soup.find("meta", property="og:title")
        if meta_title:
            return self.clean_text(meta_title.get("content", ""))

        if soup.title:
            return self.clean_text(soup.title.text)

        return ""

    def extract_content(self, soup):
        """Join paragraph elements exceeding 40 characters into a single body string."""
        paragraphs = soup.find_all("p")
        content_parts = []

        for p in paragraphs:
            text = self.clean_text(p.text)
            if len(text) > 40:
                content_parts.append(text)

        return " ".join(content_parts)

    def get_links(self, source_name, source_config):
        """Crawl paginated category pages for a source and collect unique article URLs."""
        all_links = []
        seen_urls = set()

        for base_page in source_config["start_pages"]:
            for page_num in range(1, source_config["max_pages"] + 1):
                url = base_page if page_num == 1 else f"{base_page}?page={page_num}"

                try:
                    r = requests.get(url, headers=self.headers, timeout=10)
                    r.encoding = "utf-8"

                    if r.status_code != 200:
                        break

                    soup = BeautifulSoup(r.text, "html.parser")

                    for a in soup.find_all("a", href=True):
                        link = a["href"]

                        if link.startswith("/"):
                            link = source_config["base"] + link

                        if source_config["base"] in link and source_config["article_pattern"] in link:
                            if link not in seen_urls:
                                seen_urls.add(link)
                                all_links.append(link)

                    # Pace pagination requests to reduce load on target servers.
                    time.sleep(0.3)

                except Exception:
                    continue

        return all_links

    def scrape_article(self, url, source_name):
        """Fetch, parse, validate, and deduplicate a single article record."""
        try:
            r = requests.get(url, headers=self.headers, timeout=10)
            r.encoding = "utf-8"

            if r.status_code != 200:
                return None

            soup = BeautifulSoup(r.text, "html.parser")

            title = self.extract_title(soup)
            content = self.extract_content(soup)

            if not self.is_valid_article(content, title):
                return None

            # Deduplicate exact repeats using an MD5 digest of the combined title and body.
            content_hash = hashlib.md5((title + content).encode()).hexdigest()
            if content_hash in self.seen_hashes:
                return None

            self.seen_hashes.add(content_hash)

            sentences = content.split("।")
            summary = sentences[0] if sentences else title

            return {
                "title": title,
                "content": content,
                "summary": summary,
                "url": url,
                "source": source_name,
            }

        except Exception:
            return None

    def scrape_all_sources(self, selected_sources=None):
        """Collect and return validated articles across configured or selected sources."""
        print("Starting Nepali News Scraping...")

        results = {}

        for source_name, source_config in self.sources.items():
            if selected_sources and source_name not in selected_sources:
                continue

            print(f"Scraping {source_config['display_name']}...")

            links = self.get_links(source_name, source_config)
            articles = []

            for url in links[: source_config["target"]]:
                article = self.scrape_article(url, source_name)

                if article:
                    articles.append(article)

                # Add slight jitter between article requests to avoid rate limiting.
                time.sleep(random.uniform(0.5, 0.8))

            results[source_name] = articles

        print("Scraping Completed")
        return results


if __name__ == "__main__":
    scraper = ProperNepaliNewsScraper()

    sources_to_scrape = [
        "onlinekhabar",
        "kantipur",
        "ratopati",
    ]

    results = scraper.scrape_all_sources(selected_sources=sources_to_scrape)

    print("Dataset creation finished")