# Training a Nepali Text Summarizer – Data Collection Script

# First, I'm importing all the required libraries.
# Requests is used to fetch web pages, BeautifulSoup helps parse HTML,
# time and random introduce delays so we don't overload the servers,
# hashlib creates unique fingerprints to detect duplicate content,
# json and csv handle the output file formats,
# re is for cleaning text with regular expressions,
# urllib.parse helps resolve relative URLs,
# and datetime is used to timestamp our dataset.

import requests
from bs4 import BeautifulSoup
import time
import hashlib
import json
import csv
import re
from urllib.parse import urljoin, urlparse
from datetime import datetime
import random


class OptimizedNepaliNewsScraper:
    """
    This class scrapes Nepali news articles from multiple online portals.
    It collects the full article content and automatically generates a short
    summary from the title and the most informative first sentence.
    The output is saved as both JSONL and CSV files for easy use in training.
    """

    def __init__(self):
        # These headers make the scraper look like a normal web browser.
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ne,en-US;q=0.7,en;q=0.3",
        }

        # Each news source is defined with its base URL, the pattern that
        # identifies an article link, a list of category pages to crawl,
        # and how many pages deep we should go.
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
                "max_pages": 25
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
                "max_pages": 25
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
                "max_pages": 15
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
                "sitemap_url": "https://www.setopati.com/sitemap.xml"
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
                "max_pages": 20
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
                "max_pages": 20
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
                "max_pages": 20
            }
        }

        # I am using these sets to keep track of everything I have already seen.
        # This prevents downloading the same article twice and avoids duplicates.
        self.seen_urls = set()          # Every URL that has been visited or queued
        self.seen_hashes = set()        # Content fingerprints for exact duplicates
        self.seen_titles = set()        # Normalised titles for near duplicate detection
        self.articles = []              # The final list of collected articles

        # Every time the scraper runs, it creates a fresh set of output files
        # with the current timestamp in their names.
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_jsonl = f"nepali_news_dataset_{self.timestamp}.jsonl"
        self.output_csv   = f"nepali_news_dataset_{self.timestamp}.csv"

    def clean_text(self, text):
        """
        This method removes extra whitespace and unwanted characters from the text.
        It keeps Nepali Unicode characters, basic Latin letters, digits,
        and common punctuation marks so the content stays readable.
        """
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[^\u0900-\u097F\s\.\,\-\'\'\"\"\!\?\|\।॥a-zA-Z0-9]', '', text)
        return text.strip()

    def is_nepali_content(self, text):
        """
        This method checks whether the text contains enough Nepali characters.
        At least 20% of the non-space characters must be from the Devanagari script.
        This filters out articles that are mostly in English or other languages.
        """
        if not text:
            return False
        nepali_chars = len(re.findall(r'[\u0900-\u097F]', text))
        total_chars = len(text.replace(' ', ''))
        if total_chars == 0:
            return False
        return (nepali_chars / total_chars) >= 0.2

    def is_valid_article(self, content, title):
        """
        This method applies several quality checks to ensure we only keep
        meaningful, long-form news articles. It checks the length,
        the amount of Nepali text, the presence of spam keywords,
        and whether the article has enough proper sentences.
        """
        if not content or not title:
            return False
        if len(content) < 350 or len(title) < 10:
            return False
        if not self.is_nepali_content(content):
            return False
        if content.count('।') < 2:
            return False

        # These spam keywords are common on low-quality or non-article pages.
        spam_keywords = [
            'login', 'register', 'subscribe', 'advertisement',
            'cookie policy', 'privacy policy', 'terms of use',
            'click here', 'download', 'newsletter', 'follow us',
            'share this', 'comment', 'facebook', 'twitter'
        ]
        content_lower = content.lower()
        for keyword in spam_keywords:
            if keyword in content_lower:
                return False

        # The article must have at least three meaningful sentences.
        sentences = [s.strip() for s in content.split('।') if len(s.strip()) > 20]
        if len(sentences) < 3:
            return False
        return True

    def generate_summary(self, title, content):
        """
        This method creates a short summary by combining the article title
        and the first informative sentence that does not simply repeat the title.
        The summary will be used as the target text for the summarization model.
        """
        title = self.clean_text(title)

        # I split the content into sentences using both Nepali and English full stops.
        sentences = []
        for sep in ['।', '\.']:
            parts = re.split(sep, content)
            for part in parts:
                part = part.strip()
                if len(part) > 25 and not any(x in part.lower() for x in ['http', 'www', '@']):
                    sentences.append(part)

        # I look at the first five sentences and pick the one that seems most informative.
        first_sentence = ""
        for sent in sentences[:5]:
            sent = self.clean_text(sent)
            if len(sent) > 30 and len(sent) < 300:
                if title.lower() not in sent.lower() or len(sent) > len(title) * 1.5:
                    first_sentence = sent
                    break

        # Now I combine the title and the chosen sentence to form the summary.
        if first_sentence:
            if title.lower() in first_sentence.lower():
                summary = first_sentence
            else:
                summary = f"{title}। {first_sentence}"
        else:
            summary = title

        # I limit the summary length so it stays concise.
        if len(summary) > 500:
            summary = summary[:497] + "..."
        return summary

    def extract_title(self, soup):
        """
        This method tries several different ways to extract the article title.
        It starts with common HTML selectors, then checks meta tags,
        and finally falls back to the page title tag.
        """
        title_selectors = [
            'h1', 'h1.article-title', 'h1.post-title',
            'h1.entry-title', '.title', '.news-title',
            '.article-headline', '.headline'
        ]
        for selector in title_selectors:
            title_elem = soup.select_one(selector)
            if title_elem:
                title = self.clean_text(title_elem.get_text())
                if len(title) > 5:
                    return title

        # Sometimes the title is stored in the Open Graph meta tag.
        meta_title = soup.find('meta', property='og:title')
        if meta_title:
            title = self.clean_text(meta_title.get('content', ''))
            if len(title) > 5:
                return title

        # As a last resort, I use the browser title bar and remove the site name.
        if soup.title:
            title = self.clean_text(soup.title.string)
            title = re.sub(r'\s*[|\-–]\s*(Online Khabar|Kantipur|Ratopati|Setopati|News).*$', '', title)
            if len(title) > 5:
                return title
        return ""

    def extract_content(self, soup):
        """
        This method extracts the main article body from the HTML.
        It tries several content‑specific selectors first, and if none work,
        it falls back to collecting all reasonably sized paragraphs.
        """
        content_selectors = [
            'div.article-body', 'div.news-body', 'div.post-content',
            'div.entry-content', 'div.content', 'article',
            '.detail-body', '.description', '.main-content',
            'div[class*="content"]', 'div[class*="article"]'
        ]
        content_parts = []

        for selector in content_selectors:
            content_div = soup.select_one(selector)
            if content_div:
                paragraphs = content_div.find_all('p')
                for p in paragraphs:
                    text = self.clean_text(p.get_text())
                    if len(text) > 40 and not any(x in text.lower() for x in
                        ['advertisement', 'subscribe', 'click here', 'read more', 'also read']):
                        content_parts.append(text)
                if len(content_parts) >= 3:
                    break

        # If we still don't have enough content, I gather paragraphs from the whole page.
        if len(content_parts) < 3:
            main_content = soup.find('main') or soup.find('div', {'role': 'main'}) or soup.find('body')
            if main_content:
                paragraphs = main_content.find_all('p')
                for p in paragraphs:
                    text = self.clean_text(p.get_text())
                    if 40 < len(text) < 1000:
                        content_parts.append(text)

        return ' '.join(content_parts)

    def get_links_from_sitemap(self, source_name, source_config):
        """
        If a news source provides a sitemap, this method fetches it
        and extracts all the article URLs it contains.
        Using a sitemap is faster than crawling category pages.
        """
        links = []
        if source_config.get('use_sitemap'):
            try:
                response = requests.get(source_config['sitemap_url'], headers=self.headers, timeout=15)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'xml')
                    for loc in soup.find_all('loc'):
                        url = loc.text
                        if source_config['base'] in url and source_config['article_pattern'] in url:
                            if url not in self.seen_urls:
                                self.seen_urls.add(url)
                                links.append(url)
            except Exception:
                pass  # Sitemap errors are non‑critical; we just skip them
        return links

    def get_all_links(self):
        """
        This is the main link collection method. It loops over every source
        and every category page, collects all article links it can find,
        and returns a deduplicated list.
        """
        all_links = []
        print("Collecting article links from all sources...")

        for source_name, source_config in self.news_sources.items():
            source_links = []

            # I try the sitemap first if the source has one.
            if source_config.get('use_sitemap'):
                source_links.extend(self.get_links_from_sitemap(source_name, source_config))

            # Then I crawl the category pages page by page.
            for page_url in source_config['pages']:
                for page_num in range(1, source_config['max_pages'] + 1):
                    if page_num == 1:
                        paginated_url = page_url
                    else:
                        if '?' in page_url:
                            paginated_url = f"{page_url}&page={page_num}"
                        else:
                            paginated_url = f"{page_url}?page={page_num}"

                    try:
                        response = requests.get(paginated_url, headers=self.headers, timeout=15)
                        response.encoding = 'utf-8'
                        if response.status_code != 200:
                            if page_num > 1:
                                break
                            continue

                        soup = BeautifulSoup(response.text, 'html.parser')
                        found = 0

                        # I look at every link on the page and keep only the article ones.
                        for a in soup.find_all('a', href=True):
                            href = a['href']
                            if href.startswith('/'):
                                href = urljoin(source_config['base'], href)
                            if source_config['base'].replace('https://', '').replace('http://', '') in href:
                                patterns = [source_config['article_pattern'], '/news/', '/story/', '/article/', '/post/']
                                if any(pattern in href for pattern in patterns):
                                    exclude = ['category', 'tag', 'author', 'search', 'page?',
                                              'wp-content', '.jpg', '.png', '.pdf', '#', '/page/']
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
        """
        This method downloads and parses a single article.
        It extracts the title and content, validates the quality,
        checks for duplicates, and generates a summary.
        If the article is good, it returns a dictionary of its data.
        """
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.encoding = 'utf-8'
            if response.status_code != 200:
                return None

            soup = BeautifulSoup(response.text, 'html.parser')
            title = self.extract_title(soup)
            content = self.extract_content(soup)

            if not self.is_valid_article(content, title):
                return None

            # I normalize the title to catch articles that are almost identical.
            title_normalized = re.sub(r'[^\u0900-\u097Fa-zA-Z0-9]', '', title.lower())
            for existing_title in self.seen_titles:
                if title_normalized in existing_title or existing_title in title_normalized:
                    return None
            self.seen_titles.add(title_normalized)

            # I create an exact fingerprint using the title and content together.
            content_hash = hashlib.md5(f"{title}{content}".encode('utf-8')).hexdigest()
            if content_hash in self.seen_hashes:
                return None
            self.seen_hashes.add(content_hash)

            # Now I generate a short summary for the article.
            summary = self.generate_summary(title, content)

            return {
                'id': len(self.articles),
                'title': title,
                'content': content,
                'summary': summary,
                'url': url,
                'source': source_name,
                'word_count': len(content.split()),
                'nepali_ratio': len(re.findall(r'[\u0900-\u097F]', content)) / len(content.replace(' ', '')) if content else 0,
                'collected_at': datetime.now().isoformat()
            }
        except Exception:
            return None

    def save_article(self, article):
        """
        This method appends a validated article to both the JSONL and CSV output files.
        JSONL is convenient for model training, while CSV is easy to inspect manually.
        """
        with open(self.output_jsonl, 'a', encoding='utf-8') as f:
            f.write(json.dumps(article, ensure_ascii=False) + '\n')

        with open(self.output_csv, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                article['id'],
                article['title'],
                article['summary'],
                article['content'][:300] + "..." if len(article['content']) > 300 else article['content'],
                article['url'],
                article['source'],
                article['word_count'],
                f"{article['nepali_ratio']*100:.1f}%",
                article['collected_at']
            ])

    def save_checkpoint(self, count):
        """
        Every 100 articles, I save a small checkpoint file so that I can
        resume later if something interrupts the scraping.
        """
        checkpoint_file = f"checkpoint_{self.timestamp}_{count}.json"
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump({
                'count': count,
                'articles_saved': count,
                'timestamp': datetime.now().isoformat(),
                'sources_completed': list(self.news_sources.keys())
            }, f, ensure_ascii=False, indent=2)

    def build_dataset(self, target_articles=1500):
        """
        This is the main method that orchestrates the entire process.
        It first collects all article links, then scrapes each one until
        the desired number of valid articles is reached.
        """
        print("=" * 60)
        print("Nepali News Dataset Builder")
        print(f"Target: {target_articles} articles")
        print("=" * 60)

        # I write the CSV header so the file is ready to receive data.
        with open(self.output_csv, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'title', 'summary', 'content_preview', 'url',
                             'source', 'word_count', 'nepali_ratio', 'collected_at'])

        # Phase 1 – gather all candidate links from every source.
        all_links = self.get_all_links()
        random.shuffle(all_links)

        # Phase 2 – visit each link and scrape articles until the target is hit.
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

            # I save a checkpoint every 100 articles in case of interruption.
            if articles_collected % 100 == 0 and articles_collected > 0:
                self.save_checkpoint(articles_collected)

        # Final summary of what was collected.
        print("\n" + "=" * 60)
        print(f"Dataset completed. Total articles: {articles_collected}")
        print("Articles per source:")
        for source, count in sorted(source_stats.items(), key=lambda x: x[1], reverse=True):
            print(f"  {source}: {count}")
        print(f"Output files: {self.output_jsonl}, {self.output_csv}")
        print("=" * 60)

        return self.articles


# When this script is run directly, I create a scraper instance
# and start building a dataset of 1500 high-quality articles.
if __name__ == "__main__":
    scraper = OptimizedNepaliNewsScraper()
    dataset = scraper.build_dataset(target_articles=1500)
    print("Done")