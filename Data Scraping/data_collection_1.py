# Nepali News Dataset Scraper
# This script collects news articles from multiple Nepali news websites
# and builds a structured dataset containing title, content, and summary.

# First, I'm importing all the required libraries.
# Requests is used to fetch web pages, BeautifulSoup helps parse HTML,
# time and random introduce delays so we don't overload the servers,
# hashlib creates unique fingerprints to detect duplicate content,
# json and csv handle the output file formats,
# re is for cleaning text with regular expressions,
# urllib.parse helps resolve relative URLs,
# datetime is used to timestamp our dataset,
# and os helps create folders and handle file paths.

import requests
from bs4 import BeautifulSoup
import time
import hashlib
import json
import csv
import re
from urllib.parse import urljoin
from datetime import datetime
import random
import os


# This class handles the complete scraping pipeline
# including link collection, article extraction, cleaning, and saving data.

class ProperNepaliNewsScraper:
    def __init__(self):
        # Setting browser headers to avoid blocking by websites.
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        # Each news source is defined with its base URL, category pages,
        # article URL pattern, how many pages to crawl, the target number
        # of articles, and a human-readable display name.
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
                "display_name": "Online Khabar"
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
                "display_name": "Kantipur"
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
                "display_name": "Ratopati"
            }
        }

        # I am using this set to remember content hashes and avoid duplicate articles.
        self.seen_hashes = set()

        # Every run creates a fresh output folder named with the current timestamp.
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.main_output_dir = f"nepali_news_dataset_{self.timestamp}"

        os.makedirs(self.main_output_dir, exist_ok=True)
        self.csv_dir = os.path.join(self.main_output_dir, "csv_files")
        self.json_dir = os.path.join(self.main_output_dir, "json_files")

        os.makedirs(self.csv_dir, exist_ok=True)
        os.makedirs(self.json_dir, exist_ok=True)

    def clean_text(self, text):
        """
        This method removes extra whitespace and trims the text.
        It helps keep the content clean and consistent.
        """
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def is_nepali(self, text):
        """
        This method checks whether the text contains any Nepali characters.
        It returns True if at least one Devanagari script character is found.
        """
        return bool(re.search(r'[\u0900-\u097F]', text))

    def is_valid_article(self, content, title):
        """
        This method applies quality filters to ensure only meaningful articles are kept.
        It checks the length, the presence of Nepali script,
        and that the article has at least two proper sentence endings.
        """
        if not content or not title:
            return False
        if len(content) < 300:
            return False
        if len(title) < 10:
            return False
        if not self.is_nepali(content):
            return False
        if content.count('।') < 2:
            return False
        return True

    def extract_title(self, soup):
        """
        This method tries several ways to extract the article title.
        It first looks for an <h1> tag, then the Open Graph meta tag,
        and finally the browser title bar text.
        """
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
        """
        This method extracts the main article body from the HTML.
        It collects all paragraphs that are longer than 40 characters.
        """
        paragraphs = soup.find_all("p")
        content_parts = []

        for p in paragraphs:
            text = self.clean_text(p.text)
            if len(text) > 40:
                content_parts.append(text)

        return " ".join(content_parts)

    def get_links(self, source_name, source_config):
        """
        This method collects article URLs from a single news source.
        It crawls the category pages specified in the source configuration,
        follows pagination, and returns all unique article links found.
        """
        all_links = []
        seen_urls = set()

        for base_page in source_config["start_pages"]:
            for page_num in range(1, source_config["max_pages"] + 1):
                # The first page is the base URL; later pages add a page parameter.
                if page_num == 1:
                    url = base_page
                else:
                    url = f"{base_page}?page={page_num}"

                try:
                    r = requests.get(url, headers=self.headers, timeout=10)
                    r.encoding = "utf-8"

                    if r.status_code != 200:
                        break

                    soup = BeautifulSoup(r.text, "html.parser")

                    # Every link on the page is examined; only article links are kept.
                    for a in soup.find_all("a", href=True):
                        link = a["href"]

                        if link.startswith("/"):
                            link = source_config["base"] + link

                        if source_config["base"] in link and source_config["article_pattern"] in link:
                            if link not in seen_urls:
                                seen_urls.add(link)
                                all_links.append(link)

                    time.sleep(0.3)

                except Exception:
                    continue

        return all_links

    def scrape_article(self, url, source_name):
        """
        This method downloads and parses a single article page.
        It extracts the title and content, validates the quality,
        checks for duplicates, and returns a dictionary of the article data.
        If the article is invalid or a duplicate, it returns None.
        """
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

            # I create a hash of the title and content to detect exact duplicates.
            content_hash = hashlib.md5((title + content).encode()).hexdigest()
            if content_hash in self.seen_hashes:
                return None

            self.seen_hashes.add(content_hash)

            # The summary is simply the first sentence of the article.
            sentences = content.split('।')
            summary = sentences[0] if sentences else title

            return {
                "title": title,
                "content": content,
                "summary": summary,
                "url": url,
                "source": source_name
            }

        except Exception:
            return None

    def scrape_all_sources(self, selected_sources=None):
        """
        This is the main method that scrapes all the specified news sources.
        For each source, it collects links, scrapes valid articles,
        and returns a dictionary with the collected articles per source.
        """
        print("Starting Nepali News Scraping...")

        results = {}

        for source_name, source_config in self.sources.items():
            if selected_sources and source_name not in selected_sources:
                continue

            print(f"Scraping {source_config['display_name']}...")

            links = self.get_links(source_name, source_config)
            articles = []

            # I only scrape up to the target number of articles for this source.
            for url in links[:source_config["target"]]:
                article = self.scrape_article(url, source_name)

                if article:
                    articles.append(article)

                time.sleep(random.uniform(0.5, 0.8))

            results[source_name] = articles

        print("Scraping Completed")
        return results


# When this script is run directly, I create an instance of the scraper
# and start collecting articles from OnlineKhabar, Kantipur, and Ratopati.
if __name__ == "__main__":
    scraper = ProperNepaliNewsScraper()

    sources_to_scrape = [
        "onlinekhabar",
        "kantipur",
        "ratopati"
    ]

    results = scraper.scrape_all_sources(selected_sources=sources_to_scrape)

    print("Dataset creation finished")