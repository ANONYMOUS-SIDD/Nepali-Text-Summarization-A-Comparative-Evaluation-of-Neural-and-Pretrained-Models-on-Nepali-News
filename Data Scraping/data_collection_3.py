import csv
import hashlib
import json
import re
import time

import requests
from bs4 import BeautifulSoup

# Use a desktop user-agent string to reduce basic bot filtering on target pages.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

BASE_URL = "https://www.onlinekhabar.com"
OUTPUT_JSONL = "onlinekhabar_dataset.jsonl"
OUTPUT_CSV = "onlinekhabar_dataset.csv"


def clean_text(text):
    """Collapse consecutive whitespace and trim leading and trailing spaces."""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_hash(text):
    """Compute an MD5 hex digest for exact content deduplication."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def is_nepali(text):
    """Return True if the string contains at least one Devanagari character."""
    return any("\u0900" <= c <= "\u097F" for c in text)


def is_valid_article(content):
    """Filter out short, boilerplate-heavy, or sentence-poor article bodies."""
    if not content:
        return False

    if len(content) < 600:
        return False

    bad_words = [
        "login",
        "register",
        "subscribe",
        "advertisement",
        "cookie",
        "javascript",
        "click here",
        "download",
    ]
    content_low = content.lower()
    if any(word in content_low for word in bad_words):
        return False

    # Require at least three Nepali purna viram delimiters to exclude truncated text.
    if content.count("।") < 3:
        return False

    return True


def get_first_sentence(content):
    """Return the first Devanagari sentence exceeding 20 characters, or an empty string."""
    sentences = [
        s.strip()
        for s in content.split("।")
        if len(s.strip()) > 20
    ]
    return sentences[0] if sentences else ""


def init_csv():
    """Create the output CSV file with column headers if it does not already exist."""
    try:
        with open(OUTPUT_CSV, "x", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["id", "input", "output", "url", "source"])
    except FileExistsError:
        pass


def save_jsonl(data):
    """Append a single record as a UTF-8 JSON line for model training."""
    with open(OUTPUT_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def save_csv(data):
    """Append a single record row to the CSV dataset."""
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            data["id"],
            data["input"],
            data["output"],
            data["url"],
            data["source"],
        ])


def get_links():
    """Crawl paginated OnlineKhabar category pages and return deduplicated article URLs."""
    categories = [
        "",
        "content/news",
        "content/news/national",
        "content/news/politics",
        "content/news/business",
        "content/news/sports",
        "content/news/entertainment",
        "content/news/international",
        "content/news/lifestyle",
        "content/news/technology",
        "content/news/health",
    ]

    links = set()

    print("Collecting article links...")

    for category in categories:
        for page in range(1, 80):
            if category == "":
                url = f"{BASE_URL}/page/{page}"
            else:
                url = f"{BASE_URL}/{category}/page/{page}"

            print("Fetching:", url)

            try:
                r = requests.get(url, headers=HEADERS, timeout=10)
                r.encoding = "utf-8"
                soup = BeautifulSoup(r.text, "html.parser")

                for a in soup.find_all("a", href=True):
                    link = a["href"]
                    if link.startswith("/"):
                        link = BASE_URL + link

                    # Filter for dated OnlineKhabar article URLs and exclude static assets.
                    if (
                        "onlinekhabar.com" in link
                        and "/202" in link
                        and "wp-content" not in link
                        and not link.endswith((".jpg", ".png", ".pdf"))
                    ):
                        links.add(link)

                time.sleep(0.5)

            except Exception:
                continue

    print("\nTotal links found:", len(links))
    return list(links)


def scrape_article(url):
    """Fetch, parse, and validate an article page, returning a structured dict or None."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")

        title_tag = soup.find("h1")
        title = clean_text(title_tag.text) if title_tag else ""

        paragraphs = soup.find_all("p")
        content = " ".join(
            clean_text(p.text)
            for p in paragraphs
            if len(p.text.strip()) > 40
        )

        if not is_valid_article(content):
            return None

        if len(title) < 10:
            return None

        if not is_nepali(content):
            return None

        return {
            "title": title,
            "content": content,
            "url": url,
            "hash": get_hash(title + content),
        }

    except Exception:
        return None


def generate_summary(title, content):
    """Construct a target summary from the headline and lead sentence without redundant repetition."""
    first_sentence = get_first_sentence(content)

    if first_sentence:
        if title.strip() in first_sentence:
            return first_sentence
        return f"{title}। {first_sentence}"

    return title


def build_dataset(max_samples=5000):
    """Collect links, scrape and deduplicate articles, and write JSONL and CSV outputs."""
    links = get_links()
    seen = set()
    count = 0

    init_csv()

    print("\nStarting dataset generation...")

    for url in links:
        print("Scraping:", url)

        article = scrape_article(url)

        if article:
            if article["hash"] in seen:
                continue
            seen.add(article["hash"])

            data = {
                "id": count,
                "input": article["content"],
                "output": generate_summary(
                    article["title"],
                    article["content"],
                ),
                "url": article["url"],
                "source": "onlinekhabar",
            }

            save_jsonl(data)
            save_csv(data)

            count += 1
            print("Saved:", count)

        if count >= max_samples:
            break

        # Rate-limit article requests to avoid overloading the origin server.
        time.sleep(1)

    print("Dataset created successfully")
    print("JSONL file:", OUTPUT_JSONL)
    print("CSV file  :", OUTPUT_CSV)
    print("Total data:", count)


if __name__ == "__main__":
    build_dataset(max_samples=5000)