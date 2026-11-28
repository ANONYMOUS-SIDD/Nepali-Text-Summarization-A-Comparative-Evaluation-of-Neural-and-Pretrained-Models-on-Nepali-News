# Training a Nepali Text Summarizer – OnlineKhabar Data Collection Script

# First, I'm importing all the required libraries.
# Requests is used to fetch web pages, BeautifulSoup helps parse HTML,
# time adds delays so we don't overload the server,
# hashlib creates unique fingerprints to detect duplicate content,
# json and csv handle the output file formats,
# re is for cleaning text with regular expressions.

import requests
from bs4 import BeautifulSoup
import time
import hashlib
import json
import csv
import re

# These headers make the scraper look like a normal web browser.
headers = {
    "User-Agent": "Mozilla/5.0"
}

# The base URL for OnlineKhabar, one of the most popular Nepali news portals.
BASE_URL = "https://www.onlinekhabar.com"

# I am defining the names of the output files that will store the scraped data.
# JSONL is good for machine learning pipelines, CSV is easier to inspect manually.
OUTPUT_JSONL = "onlinekhabar_dataset.jsonl"
OUTPUT_CSV = "onlinekhabar_dataset.csv"


def clean_text(text):
    """
    This function removes extra whitespace and trims the text.
    It helps keep the content clean and consistent.
    """
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_hash(text):
    """
    This function creates an MD5 hash of the given text.
    I use it to detect duplicate articles by comparing fingerprints.
    """
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def is_nepali(text):
    """
    This function checks whether the text contains any Nepali characters.
    It returns True if at least one Devanagari script character is found.
    """
    return any("\u0900" <= c <= "\u097F" for c in text)


def is_valid_article(content):
    """
    This function applies quality filters to ensure only meaningful articles are kept.
    It checks the length, looks for spam or boilerplate words,
    and verifies that there are enough Nepali sentence endings.
    """
    if not content:
        return False

    # A valid article must have at least 600 characters of body text.
    if len(content) < 600:
        return False

    # These words often appear in non-article pages or advertisements.
    bad_words = [
        "login",
        "register",
        "subscribe",
        "advertisement",
        "cookie",
        "javascript",
        "click here",
        "download"
    ]
    content_low = content.lower()
    if any(word in content_low for word in bad_words):
        return False

    # A proper Nepali news article usually has at least three full stops (।).
    if content.count("।") < 3:
        return False

    return True


def get_first_sentence(content):
    """
    This function extracts the first meaningful sentence from the article content.
    It splits by the Nepali full stop and returns the first sentence that is long enough.
    """
    sentences = [
        s.strip()
        for s in content.split("।")
        if len(s.strip()) > 20
    ]
    return sentences[0] if sentences else ""


def init_csv():
    """
    This function creates the CSV file with the header row if it doesn't exist yet.
    I use this so that the file is ready to receive data from the start.
    """
    try:
        with open(OUTPUT_CSV, "x", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "id",
                "input",
                "output",
                "url",
                "source"
            ])
    except FileExistsError:
        pass


def save_jsonl(data):
    """
    This function appends a single data record to the JSONL file.
    Each line is a complete JSON object, which is a common format for training data.
    """
    with open(OUTPUT_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def save_csv(data):
    """
    This function appends a single data record to the CSV file.
    It writes the same fields in the order defined in the header.
    """
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            data["id"],
            data["input"],
            data["output"],
            data["url"],
            data["source"]
        ])


def get_links():
    """
    This function collects article URLs from OnlineKhabar's category pages.
    It loops through multiple categories and paginates up to page 80 for each.
    All unique article links are returned as a list.
    """
    # These category paths cover the main sections of the website.
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
        "content/news/health"
    ]

    links = set()

    print("Collecting article links...")

    for category in categories:
        for page in range(1, 80):
            # The homepage and category pages follow a simple URL pattern.
            if category == "":
                url = BASE_URL + f"/page/{page}"
            else:
                url = BASE_URL + "/" + category + f"/page/{page}"

            print("Fetching:", url)

            try:
                r = requests.get(url, headers=headers, timeout=10)
                r.encoding = "utf-8"
                soup = BeautifulSoup(r.text, "html.parser")

                # Every anchor tag is checked; only article links are kept.
                for a in soup.find_all("a", href=True):
                    link = a["href"]
                    if link.startswith("/"):
                        link = BASE_URL + link

                    if (
                        "onlinekhabar.com" in link
                        and "/202" in link              # News articles typically have a year in the URL
                        and "wp-content" not in link    # Exclude media files
                        and not link.endswith((".jpg", ".png", ".pdf"))
                    ):
                        links.add(link)

                time.sleep(0.5)

            except:
                continue

    print("\nTotal links found:", len(links))
    return list(links)


def scrape_article(url):
    """
    This function downloads and parses a single article page.
    It extracts the title and the main content, validates the quality,
    and returns a dictionary with the article data, or None if invalid.
    """
    try:
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")

        # The title is usually inside the first <h1> tag.
        title_tag = soup.find("h1")
        title = clean_text(title_tag.text) if title_tag else ""

        # The content is built by joining all paragraphs that are longer than 40 characters.
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
            "hash": get_hash(title + content)
        }

    except:
        return None


def generate_summary(title, content):
    """
    This function creates a short summary by combining the article title
    and the first meaningful sentence from the content.
    If the title already appears in that sentence, only the sentence is used.
    """
    first_sentence = get_first_sentence(content)

    if first_sentence:
        if title.strip() in first_sentence:
            return first_sentence
        return f"{title}। {first_sentence}"

    return title


def build_dataset(max_samples=5000):
    """
    This is the main function that orchestrates the entire collection process.
    It collects links, scrapes each article, validates it,
    generates a summary, and saves the result to JSONL and CSV files.
    The process stops after the desired number of articles is reached.
    """
    links = get_links()
    seen = set()
    count = 0

    # Initialize the CSV file with a header row.
    init_csv()

    print("\nStarting dataset generation...")

    for url in links:
        print("Scraping:", url)

        article = scrape_article(url)

        if article:
            # Skip articles that we have already saved (exact duplicate check).
            if article["hash"] in seen:
                continue
            seen.add(article["hash"])

            data = {
                "id": count,
                "input": article["content"],
                "output": generate_summary(
                    article["title"],
                    article["content"]
                ),
                "url": article["url"],
                "source": "onlinekhabar"
            }

            save_jsonl(data)
            save_csv(data)

            count += 1
            print("Saved:", count)

        if count >= max_samples:
            break

        time.sleep(1)

    print("Dataset created successfully")

    print("JSONL file:", OUTPUT_JSONL)
    print("CSV file  :", OUTPUT_CSV)
    print("Total data:", count)


# When this script is run directly, I start building a dataset of up to 5000 articles.
if __name__ == "__main__":
    build_dataset(max_samples=5000)