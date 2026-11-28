import glob
import hashlib
import os
import re

import pandas as pd


class DatasetCombiner:
    """Merge, normalize, deduplicate, and export Nepali news CSV datasets into a unified corpus."""

    def __init__(self):
        """Initialize the article buffer and deduplication hash registry."""
        self.all_data = []
        self.seen_hashes = set()

    def find_csv_files(self, search_patterns):
        """Search candidate directories for matching CSV files while preserving discovery order."""
        found_files = []

        for pattern in search_patterns:
            found_files.extend(glob.glob(pattern))
            found_files.extend(glob.glob(f"CSV Files/{pattern}"))
            found_files.extend(glob.glob(f"../{pattern}"))
            found_files.extend(glob.glob(f"../CSV Files/{pattern}"))

        seen = set()
        unique_files = []
        for file in found_files:
            if file not in seen:
                seen.add(file)
                unique_files.append(file)

        return unique_files

    def load_and_combine_csvs(self, file_paths):
        """Load input CSVs, map content and summary columns, filter records, and deduplicate."""
        print("Combining Nepali News Datasets")

        for file_path in file_paths:
            if not os.path.exists(file_path):
                print(f"File Not Found: {file_path}")
                continue

            print(f"Loading: {file_path}")

            try:
                df = pd.read_csv(file_path, encoding="utf-8-sig")

                content_col = None
                for col in ["content", "Full_Content", "Content", "article_content", "content_preview", "input"]:
                    if col in df.columns:
                        content_col = col
                        break

                summary_col = None
                for col in ["summary", "Summary", "article_summary", "Summary_Text", "output"]:
                    if col in df.columns:
                        summary_col = col
                        break

                if content_col is None:
                    print(f"No Content Column Found In: {file_path}")
                    continue

                extracted = 0
                for _, row in df.iterrows():
                    try:
                        content = str(row[content_col]) if pd.notna(row[content_col]) else ""

                        if summary_col and pd.notna(row[summary_col]):
                            summary = str(row[summary_col])
                        else:
                            summary = self._generate_summary(content)

                        content = self._clean_text(content)
                        summary = self._clean_text(summary)

                        if len(content) >= 200 and len(summary) >= 20 and self._has_nepali(content):
                            self.all_data.append({"content": content, "summary": summary})
                            extracted += 1
                    except Exception:
                        # Skip malformed rows so one bad record does not abort the file.
                        continue

                print(f"Extracted {extracted} Articles From {file_path}")

            except Exception as e:
                print(f"Error Reading {file_path}: {str(e)[:100]}")

        print(f"Total Before Deduplication: {len(self.all_data)}")
        self._remove_duplicates()
        print(f"Unique Articles After Deduplication: {len(self.all_data)}")

        return self.all_data

    def _generate_summary(self, content):
        """Extract a bounded lead sentence as a fallback summary when no summary column exists."""
        sentences = re.split(r"[।\.]", content)
        for sent in sentences[:3]:
            sent = sent.strip()
            if 30 < len(sent) < 400:
                return sent
        return content[:200] if len(content) > 200 else content

    def _clean_text(self, text):
        """Strip URLs, emails, and disallowed characters while preserving Devanagari and ASCII."""
        if not isinstance(text, str):
            return ""

        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"http\S+|www\S+|https\S+", "", text)
        text = re.sub(r"\S+@\S+", "", text)
        text = re.sub(r"[^\u0900-\u097F\s\.\,\!\?।॥a-zA-Z0-9]", "", text)
        text = " ".join(text.split())

        return text.strip()

    def _has_nepali(self, text):
        """Return True if at least 20% of non-whitespace characters belong to Devanagari."""
        text_clean = text.replace(" ", "")
        if not text_clean:
            return False

        nepali_chars = len(re.findall(r"[\u0900-\u097F]", text))
        return (nepali_chars / len(text_clean)) >= 0.2

    def _remove_duplicates(self):
        """Deduplicate records using an MD5 hash of the first 500 characters of content."""
        unique_data = []
        for item in self.all_data:
            # Prefix hashing catches near-identical wire or syndicated stories with trailing edits.
            content_hash = hashlib.md5(item["content"][:500].encode("utf-8")).hexdigest()
            if content_hash not in self.seen_hashes:
                self.seen_hashes.add(content_hash)
                unique_data.append(item)
        self.all_data = unique_data

    def save_final_dataset(self, output_file="Nepali_Text_Summarizer_Dataset.csv"):
        """Write the deduplicated dataset with sequential IDs to a UTF-8 BOM CSV file."""
        if not self.all_data:
            print("No Data To Save")
            return False

        df = pd.DataFrame(self.all_data)
        df.insert(0, "id", range(1, len(df) + 1))
        df.to_csv(output_file, index=False, encoding="utf-8-sig")

        print(f"Dataset Saved: {output_file} ({len(df)} Articles)")
        return True


if __name__ == "__main__":
    combiner = DatasetCombiner()

    csv_files = []
    file_names = ["kantipur.csv", "khabarhub.csv", "nepali_news.csv", "onlineKhabar.csv", "ratopati.csv"]
    search_locations = [".", "CSV Files", "..", "../CSV Files"]

    for file_name in file_names:
        for location in search_locations:
            path = os.path.join(location, file_name)
            if os.path.exists(path):
                csv_files.append(path)
                break

    if not csv_files:
        print("No CSV Files Found")
    else:
        combiner.load_and_combine_csvs(csv_files)
        combiner.save_final_dataset("Nepali_Text_Summarizer_Dataset.csv")