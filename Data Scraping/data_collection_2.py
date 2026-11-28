import csv
import hashlib
import json
import random
import re
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


class OptimizedNepaliNewsScraper:
    """Multi-portal scraper for building Nepali news summarization datasets in JSONL and CSV."""

    def __init__(self):
        """Initialize browser headers, news portals, deduplication sets, and output paths."""
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ne,en-US;q=0.7,en;q=0.3",
        }

        self.news_sources = {
            "onlinekhabar": {
                "base": "https://www.onlinekhabar.com",
                "article_pattern": "/content/",
                "pages": [
                    "https://www.onlinekhabar.com",
                    "https://www.onlinekhabar.com/content/news",
                    "https://www.onlinekhabar.com/content/news/politics",
                    "https://www.onlinekhabar.com/content/news/economy",
                    "https://www.onlinekhabar.com/content/news/sports",
                    "https://www.onlinekhabar.com/content/news/technology",
                    "https://www.onlinekhabar.com/content/news/entertainment",
                ],
                "max_pages": 25,
            },
            "kantipur": {
                "base": "https://ekantipur.com",
                "article_pattern": "/news/",
                "pages": [
                    "https://ekantipur.com/news",
                    "https://ekantipur.com/news/politics",
                    "https://ekantipur.com/news/business",
                    "https://ekantipur.com/news/sports",
                    "https://ekantipur.com/news/world",
                    "https://ekantipur.com/news/entertainment",
                    "https://ekantipur.com/opinion",
                ],
                "max_pages": 25,
            },
            "ratopati": {
                "base": "https://www.ratopati.com",
                "article_pattern": "/story/",
                "pages": [
                    "https://www.ratopati.com",
                    "https://www.ratopati.com/category/news",
                    "https://www.ratopati.com/category/politics",
                    "https://www.ratopati.com/category/economy",
                    "https://www.ratopati.com/category/sports",
                    "https://www.ratopati.com/category/entertainment",
                ],
                "max_pages": 15,
            },
            "setopati": {
                "base": "https://www.setopati.com",
                "article_pattern": "/article/",
                "pages": [
                    "https://www.setopati.com",
                    "https://www.setopati.com/politics",
                    "https://www.setopati.com/social",
                    "https://www.setopati.com/business",
                    "https://www.setopati.com/sports",
                    "https://www.setopati.com/entertainment",
                ],
                "max_pages": 20,
                "use_sitemap": True,
                "sitemap_url": "https://www.setopati.com/sitemap.xml",
            },
            "nayapatrika": {
                "base": "https://www.nayapatrikadaily.com",
                "article_pattern": "/news-details/",
                "pages": [
                    "https://www.nayapatrikadaily.com",
                    "https://www.nayapatrikadaily.com/category/national",
                    "https://www.nayapatrikadaily.com/category/economy",
                    "https://www.nayapatrikadaily.com/category/sports",
                ],
                "max_pages": 20,
            },
            "annapurnapost": {
                "base": "https://annapurnapost.com",
                "article_pattern": "/news/",
                "pages": [
                    "https://annapurnapost.com",
                    "https://annapurnapost.com/category/national",
                    "https://annapurnapost.com/category/economy",
                    "https://annapurnapost.com/category/sports",
                ],
                "max_pages": 20,
            },
            "khabarhub": {
                "base": "https://khabarhub.com",
                "article_pattern": "/",
                "pages": [
                    "https://khabarhub.com",
                    "https://khabarhub.com/category/national",
                    "https://khabarhub.com/category/politics",
                    "https://khabarhub.com/category/economy",
                    "https://khabarhub.com/category/sports",
                ],
                "max_pages": 20,
            },
        }

        self.seen_urls = set()
        self.seen_hashes = set()
        self.seen_titles = set()
        self.articles = []

        # Timestamp output files so repeated runs do not overwrite existing datasets.
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_jsonl = f"nepali_news_dataset_{self.timestamp}.jsonl"
        self.output_csv = f"nepali_news_dataset_{self.timestamp}.csv"

    def clean_text(self, text):
        """Collapse whitespace and strip characters outside Devanagari, ASCII, and basic punctuation."""
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[^\u0900-\u097F\s\.\,\-\'\'\"\"\!\?\|\।॥a-zA-Z0-9]", "", text)
        return text.strip()

    def is_nepali_content(self, text):
        """Return True if at least 20% of non-whitespace characters are Devanagari."""
        if not text:
            return False
        nepali_chars = len(re.findall(r"[\u0900-\u097F]", text))
        total_chars = len(text.replace(" ", ""))
        if total_chars == 0:
            return False
        return (nepali_chars / total_chars) >= 0.2

    def is_valid_article(self, content, title):
        """Filter out short, non-Nepali, boilerplate-heavy, or sentence-poor articles."""
        if not content or not title:
            return False
        if len(content) < 350 or len(title) < 10:
            return False
        if not self.is_nepali_content(content):
            return False
        if content.count("।") < 2:
            return False

        spam_keywords = [
            "login",
            "register",
            "subscribe",
            "advertisement",
            "cookie policy",
            "privacy policy",
            "terms of use",
            "click here",
            "download",
            "newsletter",
            "follow us",
            "share this",
            "comment",
            "facebook",
            "twitter",
        ]
        content_lower = content.lower()
        for keyword in spam_keywords:
            if keyword in content_lower:
                return False

        sentences = [s.strip() for s in content.split("।") if len(s.strip()) > 20]
        if len(sentences) < 3:
            return False
        return True

    def generate_summary(self, title, content):
        """Build a bounded target summary from the headline and an informative lead sentence."""
        title = self.clean_text(title)

        sentences = []
        for sep in ["।", "\\."]:
            parts = re.split(sep, content)
            for part in parts:
                part = part.strip()
                if len(part) > 25 and not any(x in part.lower() for x in ["http", "www", "@"]):
                    sentences.append(part)

        first_sentence = ""
        for sent in sentences[:5]:
            sent = self.clean_text(sent)
            if 30 < len(sent) < 300:
                if title.lower() not in sent.lower() or len(sent) > len(title) * 1.5:
                    first_sentence = sent
                    break

        if first_sentence:
            if title.lower() in first_sentence.lower():
                summary = first_sentence
            else:
                summary = f"{title}। {first_sentence}"
        else:
            summary = title

        if len(summary) > 500:
            summary = summary[:497] + "..."
        return summary

    def extract_title(self, soup):
        """Extract the article headline via CSS selectors, Open Graph metadata, or page title."""
        title_selectors = [
            "h1",
            "h1.article-title",
            "h1.post-title",
            "h1.entry-title",
            ".title",
            ".news-title",
            ".article-headline",
            ".headline",
        ]
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = self.clean_text(title_elem.get_text())
                if len(title) > 5:
                    return title

        meta_title = soup.find("meta", property="og:title")
        if meta_title:
            title = self.clean_text(meta_title.get("content", ""))
            if len(title) > 5:
                return title

        if soup.title:
            title = self.clean_text(soup.title.string)
            title = re.sub(r"\s*[|\-–]\s*(Online Khabar|Kantipur|Ratopati|Setopati|News).*$", "", title)
            if len(title) > 5:
                return title
        return ""

    def extract_content(self, soup):
        """Extract main article paragraphs from known containers with a main/body fallback."""
        content_selectors = [
            "div.article-body",
            "div.news-body",
            "div.post-content",
            "div.entry-content",
            "div.content",
            "article",
            ".detail-body",
            ".description",
            ".main-content",
            'div[class*="content"]',
            'div[class*="article"]',
        ]
        content_parts = []

        for selector in content_selectors:
            content_div = soup.select_one(selector)
            if content_div:
                paragraphs = content_div.find_all("p")
                for p in paragraphs:
                    text = self.clean_text(p.get_text())
                    if len(text) > 40 and not any(
                        x in text.lower()
                        for x in ["advertisement", "subscribe", "click here", "read more", "also read"]
                    ):
                        content_parts.append(text)
                if len(content_parts) >= 3:
                    break

        if len(content_parts) < 3:
            main_content = soup.find("main") or soup.find("div", {"role": "main"}) or soup.find("body")
            if main_content:
                paragraphs = main_content.find_all("p")
                for p in paragraphs:
                    text = self.clean_text(p.get_text())
                    if 40 < len(text) < 1000:
                        content_parts.append(text)

        return " ".join(content_parts)

    def get_links_from_sitemap(self, source_name, source_config):
        """Extract matching article URLs from a source XML sitemap when enabled."""
        links = []
        if source_config.get("use_sitemap"):
            try:
                response = requests.get(source_config["sitemap_url"], headers=self.headers, timeout=15)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, "xml")
                    for loc in soup.find_all("loc"):
                        url = loc.text
                        if source_config["base"] in url and source_config["article_pattern"] in url:
                            if url not in self.seen_urls:
                                self.seen_urls.add(url)
                                links.append(url)
            except Exception:
                # Ignore transient sitemap failures and fall back to category crawling.
                pass
        return links

    def get_all_links(self):
        """Collect deduplicated candidate article URLs across sitemaps and paginated category pages."""
        all_links = []
        print("Collecting article links from all sources...")

        for source_name, source_config in self.news_sources.items():
            source_links = []

            if source_config.get("use_sitemap"):
                source_links.extend(self.get_links_from_sitemap(source_name, source_config))

            for page_url in source_config["pages"]:
                for page_num in range(1, source_config["max_pages"] + 1):
                    if page_num == 1:
                        paginated_url = page_url
                    else:
                        sep = "&" if "?" in page_url else "?"
                        paginated_url = f"{page_url}{sep}page={page_num}"

                    try:
                        response = requests.get(paginated_url, headers=self.headers, timeout=15)
                        response.encoding = "utf-8"
                        if response.status_code != 200:
                            if page_num > 1:
                                break
                            continue

                        soup = BeautifulSoup(response.text, "html.parser")
                        found = 0

                        for a in soup.find_all("a", href=True):
                            href = a["href"]
                            if href.startswith("/"):
                                href = urljoin(source_config["base"], href)
                            if source_config["base"].replace("https://", "").replace("http://", "") in href:
                                patterns = [
                                    source_config["article_pattern"],
                                    "/news/",
                                    "/story/",
                                    "/article/",
                                    "/post/",
                                ]
                                if any(pattern in href for pattern in patterns):
                                    exclude = [
                                        "category",
                                        "tag",
                                        "author",
                                        "search",
                                        "page?",
                                        "wp-content",
                                        ".jpg",
                                        ".png",
                                        ".pdf",
                                        "#",
                                        "/page/",
                                    ]
                                    if not any(ex in href.lower() for ex in exclude):
                                        if href not in self.seen_urls:
                                            self.seen_urls.add(href)
                                            source_links.append(href)
                                            found += 1

                        if found == 0 and page_num > 2:
                            break
                        time.sleep(random.uniform(0.3, 0.5))

                    except Exception:
                        continue

            print(f"  {source_name}: {len(source_links)} links")
            all_links.extend([(link, source_name) for link in source_links])
            time.sleep(1)

        print(f"Total unique links collected: {len(all_links)}")
        return all_links

    def scrape_article(self, url, source_name):
        """Fetch, validate, deduplicate, and format a single article with metadata and summary."""
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.encoding = "utf-8"
            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, "html.parser")
            title = self.extract_title(soup)
            content = self.extract_content(soup)

            if not self.is_valid_article(content, title):
                return None

            # Filter substring-level title collisions to reduce near-duplicate stories.
            title_normalized = re.sub(r"[^\u0900-\u097Fa-zA-Z0-9]", "", title.lower())
            for existing_title in self.seen_titles:
                if title_normalized in existing_title or existing_title in title_normalized:
                    return None
            self.seen_titles.add(title_normalized)

            content_hash = hashlib.md5(f"{title}{content}".encode("utf-8")).hexdigest()
            if content_hash in self.seen_hashes:
                return None
            self.seen_hashes.add(content_hash)

            summary = self.generate_summary(title, content)

            return {
                "id": len(self.articles),
                "title": title,
                "content": content,
                "summary": summary,
                "url": url,
                "source": source_name,
                "word_count": len(content.split()),
                "nepali_ratio": (
                    len(re.findall(r"[\u0900-\u097F]", content)) / len(content.replace(" ", ""))
                    if content
                    else 0
                ),
                "collected_at": datetime.now().isoformat(),
            }
        except Exception:
            return None

    def save_article(self, article):
        """Append a validated article record to both the JSONL and CSV output files."""
        with open(self.output_jsonl, "a", encoding="utf-8") as f:
            f.write(json.dumps(article, ensure_ascii=False) + "\n")

        with open(self.output_csv, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    article["id"],
                    article["title"],
                    article["summary"],
                    article["content"][:300] + "..." if len(article["content"]) > 300 else article["content"],
                    article["url"],
                    article["source"],
                    article["word_count"],
                    f"{article['nepali_ratio']*100:.1f}%",
                    article["collected_at"],
                ]
            )

    def save_checkpoint(self, count):
        """Write a progress checkpoint file after each batch of collected articles."""
        checkpoint_file = f"checkpoint_{self.timestamp}_{count}.json"
        with open(checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "count": count,
                    "articles_saved": count,
                    "timestamp": datetime.now().isoformat(),
                    "sources_completed": list(self.news_sources.keys()),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def build_dataset(self, target_articles=1500):
        """Run link discovery, article scraping, incremental saving, and checkpoints up to target."""
        print("=" * 60)
        print("Nepali News Dataset Builder")
        print(f"Target: {target_articles} articles")
        print("=" * 60)

        with open(self.output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "id",
                    "title",
                    "summary",
                    "content_preview",
                    "url",
                    "source",
                    "word_count",
                    "nepali_ratio",
                    "collected_at",
                ]
            )

        all_links = self.get_all_links()
        random.shuffle(all_links)

        articles_collected = 0
        source_stats = {}

        for url, source_name in all_links:
            if articles_collected >= target_articles:
                break

            article = self.scrape_article(url, source_name)
            if article:
                self.save_article(article)
                self.articles.append(article)
                articles_collected += 1
                source_stats[source_name] = source_stats.get(source_name, 0) + 1
                print(f"  [{articles_collected}/{target_articles}] {source_name}: {article['title'][:50]}...")

            time.sleep(random.uniform(0.5, 0.8))

            if articles_collected % 100 == 0 and articles_collected > 0:
                self.save_checkpoint(articles_collected)

        print("\n" + "=" * 60)
        print(f"Dataset completed. Total articles: {articles_collected}")
        print("Articles per source:")
        for source, count in sorted(source_stats.items(), key=lambda x: x[1], reverse=True):
            print(f"  {source}: {count}")
        print(f"Output files: {self.output_jsonl}, {self.output_csv}")
        print("=" * 60)

        return self.articles


if __name__ == "__main__":
    scraper = OptimizedNepaliNewsScraper()
    dataset = scraper.build_dataset(target_articles=1500)
    print("Done")