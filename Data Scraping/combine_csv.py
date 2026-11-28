# Nepali News Dataset Combiner
# This Script Combines Multiple CSV Files Into A Single Clean Dataset
# The Output File Has Columns id, content, And summary

# Import Required Libraries
import pandas as pd
import hashlib
import re
import os
import glob

class DatasetCombiner:
    def __init__(self):
        # Store All Extracted Articles Here Before Deduplication
        self.all_data = []
        # Set Of Content Hashes To Prevent Duplicate Entries
        self.seen_hashes = set()

    def find_csv_files(self, search_patterns):
        """
        Search For CSV Files In Several Common Locations
        It Checks The Current Folder, A CSV Files Subfolder,
        The Parent Directory, And A Parent CSV Files Folder
        """
        found_files = []

        # Check Current Directory
        for pattern in search_patterns:
            matches = glob.glob(pattern)
            found_files.extend(matches)

        # Check CSV Files Subfolder
        for pattern in search_patterns:
            matches = glob.glob(f"CSV Files/{pattern}")
            found_files.extend(matches)

        # Check Parent Directory
        for pattern in search_patterns:
            matches = glob.glob(f"../{pattern}")
            found_files.extend(matches)
            matches = glob.glob(f"../CSV Files/{pattern}")
            found_files.extend(matches)

        # Remove Duplicate File Paths While Preserving Order
        seen = set()
        unique_files = []
        for file in found_files:
            if file not in seen:
                seen.add(file)
                unique_files.append(file)

        return unique_files

    def load_and_combine_csvs(self, file_paths):
        """
        Load All Found CSV Files And Extract The Content And Summary Columns
        It Supports Multiple Column Naming Conventions (content/input, summary/output)
        """
        print("Combining Nepali News Datasets")

        for file_path in file_paths:
            if not os.path.exists(file_path):
                print(f"File Not Found: {file_path}")
                continue

            print(f"Loading: {file_path}")

            try:
                df = pd.read_csv(file_path, encoding='utf-8-sig')

                # Identify The Content Column
                content_col = None
                for col in ['content', 'Full_Content', 'Content', 'article_content', 'content_preview', 'input']:
                    if col in df.columns:
                        content_col = col
                        break

                # Identify The Summary Column
                summary_col = None
                for col in ['summary', 'Summary', 'article_summary', 'Summary_Text', 'output']:
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

                        # Use Existing Summary Or Generate One
                        if summary_col and pd.notna(row[summary_col]):
                            summary = str(row[summary_col])
                        else:
                            summary = self._generate_summary(content)

                        content = self._clean_text(content)
                        summary = self._clean_text(summary)

                        # Only Keep Articles That Are Long Enough And Contain Nepali Text
                        if len(content) >= 200 and len(summary) >= 20 and self._has_nepali(content):
                            self.all_data.append({'content': content, 'summary': summary})
                            extracted += 1
                    except:
                        continue

                print(f"Extracted {extracted} Articles From {file_path}")

            except Exception as e:
                print(f"Error Reading {file_path}: {str(e)[:100]}")

        print(f"Total Before Deduplication: {len(self.all_data)}")
        self._remove_duplicates()
        print(f"Unique Articles After Deduplication: {len(self.all_data)}")

        return self.all_data

    def _generate_summary(self, content):
        """
        Generate A Summary From The First Meaningful Sentence
        This Is Used When No Summary Column Is Present In The CSV
        """
        sentences = re.split(r'[।\.]', content)
        for sent in sentences[:3]:
            sent = sent.strip()
            if 30 < len(sent) < 400:
                return sent
        return content[:200] if len(content) > 200 else content

    def _clean_text(self, text):
        """
        Clean Text By Removing URLs, Emails, And Extra Spaces
        Keeps Nepali Script, Basic Latin Letters, Digits, And Common Punctuation
        """
        if not isinstance(text, str):
            return ""

        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'http\S+|www\S+|https\S+', '', text)
        text = re.sub(r'\S+@\S+', '', text)
        text = re.sub(r'[^\u0900-\u097F\s\.\,\!\?।॥a-zA-Z0-9]', '', text)
        text = ' '.join(text.split())

        return text.strip()

    def _has_nepali(self, text):
        """
        Check That At Least 20 Percent Of The Non-Space Characters Are Nepali
        This Filters Out Articles That Are Mostly In English
        """
        text_clean = text.replace(' ', '')
        if not text_clean:
            return False

        nepali_chars = len(re.findall(r'[\u0900-\u097F]', text))
        return (nepali_chars / len(text_clean)) >= 0.2

    def _remove_duplicates(self):
        """
        Remove Duplicate Articles Based On A Hash Of The First 500 Characters
        This Prevents The Same Article From Appearing Multiple Times
        """
        unique_data = []
        for item in self.all_data:
            content_hash = hashlib.md5(item['content'][:500].encode('utf-8')).hexdigest()
            if content_hash not in self.seen_hashes:
                self.seen_hashes.add(content_hash)
                unique_data.append(item)
        self.all_data = unique_data

    def save_final_dataset(self, output_file="Nepali_Text_Summarizer_Dataset.csv"):
        """
        Save The Combined And Cleaned Dataset To A CSV File
        The Output File Includes An id Column, content, And summary
        """
        if not self.all_data:
            print("No Data To Save")
            return False

        df = pd.DataFrame(self.all_data)
        df.insert(0, 'id', range(1, len(df) + 1))
        df.to_csv(output_file, index=False, encoding='utf-8-sig')

        print(f"Dataset Saved: {output_file} ({len(df)} Articles)")
        return True


# Main Execution
if __name__ == "__main__":
    combiner = DatasetCombiner()

    # Look For CSV Files In Common Locations
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