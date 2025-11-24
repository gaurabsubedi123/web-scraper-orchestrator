import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Set
import re
import argparse

class KeywordSearcher:
    """Search and filter master JSON data by keywords"""

    def __init__(self, master_file: str = "scraped_data/master_scraped_data.json"):
        self.master_file = Path(master_file)
        self.master_data = None
        self.search_results = {
            'search_info': {
                'searched_at': datetime.now().isoformat(),
                'keywords': [],
                'search_mode': 'any',
                'case_sensitive': False,
                'fields_searched': []
            },
            'scraping_history': {},
            'summary': {},
            'results_by_scraper': {}
        }
        # Track duplicates
        self.skipped_duplicates = 0

    def load_master_data(self) -> bool:
        """Load the master JSON file"""
        if not self.master_file.exists():
            print(f"Error: Master file not found: {self.master_file}")
            return False
        try:
            with open(self.master_file, 'r', encoding='utf-8') as f:
                self.master_data = json.load(f)
            print(f"Loaded master data from: {self.master_file}")
            return True
        except Exception as e:
            print(f"Error loading master file: {e}")
            return False

    def _text_contains_keyword(self, text: str, keyword: str, case_sensitive: bool = False) -> bool:
        """Check if text contains keyword"""
        if not text:
            return False
        if not case_sensitive:
            return keyword.lower() in text.lower()
        return keyword in text

    def _text_contains_keywords(
        self,
        text: str,
        keywords: List[str],
        mode: str = 'any',
        case_sensitive: bool = False
    ) -> tuple[bool, List[str]]:
        """
        Check if text contains keywords
        Returns: (matches: bool, matched_keywords: List[str])
        """
        matched = []
        for keyword in keywords:
            if self._text_contains_keyword(text, keyword, case_sensitive):
                matched.append(keyword)

        if mode == 'all':
            return len(matched) == len(keywords), matched
        else:  # mode == 'any'
            return len(matched) > 0, matched

    def _search_in_item(
        self,
        item: Dict[str, Any],
        keywords: List[str],
        fields: List[str],
        mode: str = 'any',
        case_sensitive: bool = False
    ) -> tuple[bool, Dict[str, List[str]]]:
        """
        Search for keywords in specific fields of an item
        Returns: (found: bool, matches_by_field: Dict[field, List[keywords]])
        """
        matches_by_field = {}
        all_matched_keywords = set()

        for field in fields:
            field_value = item.get(field, '')

            # Handle nested fields (e.g., 'raw_data.description')
            if '.' in field:
                parts = field.split('.')
                field_value = item
                for part in parts:
                    if isinstance(field_value, dict):
                        field_value = field_value.get(part, '')
                    else:
                        field_value = ''
                        break

            # Convert to string if needed
            if not isinstance(field_value, str):
                field_value = str(field_value)

            contains, matched_keywords = self._text_contains_keywords(
                field_value, keywords, 'any', case_sensitive
            )

            if contains:
                matches_by_field[field] = matched_keywords
                all_matched_keywords.update(matched_keywords)

        # Determine if item matches based on mode
        if mode == 'all':
            found = len(all_matched_keywords) == len(keywords)
        else:  # mode == 'any'
            found = len(all_matched_keywords) > 0

        return found, matches_by_field

    def search_announcements(
        self,
        keywords: List[str],
        fields: List[str] = None,
        mode: str = 'any',
        case_sensitive: bool = False
    ) -> Dict[str, Any]:
        """
        Search announcements for keywords WITH DEDUPLICATION

        Args:
            keywords: List of keywords to search for
            fields: Fields to search in (default: ['title', 'excerpt', 'category'])
            mode: 'any' (match any keyword) or 'all' (match all keywords)
            case_sensitive: Whether search is case-sensitive
        """
        if not self.master_data:
            print("Master data not loaded!")
            return {}

        if fields is None:
            fields = ['title', 'excerpt', 'category', 'url']

        # Update search info
        self.search_results['search_info'].update({
            'searched_at': datetime.now().isoformat(),
            'keywords': keywords,
            'search_mode': mode,
            'case_sensitive': case_sensitive,
            'fields_searched': fields
        })

        # Copy scraping history
        self.search_results['scraping_history'] = self.master_data.get('scraping_history', {})

        total_matches = 0
        self.skipped_duplicates = 0
        
        # Track seen URLs to avoid duplicates
        seen_urls = set()

        # Search through each scraper's data
        for scraper_name, scraper_data in self.master_data.get('results_by_scraper', {}).items():
            matched_announcements = []
            matched_full_content = []

            # Search announcements with deduplication
            for announcement in scraper_data.get('announcements', []):
                url = announcement.get('url', '')
                
                # Skip if we've seen this URL before (deduplication)
                if url and url in seen_urls:
                    self.skipped_duplicates += 1
                    continue
                
                found, matches_by_field = self._search_in_item(
                    announcement, keywords, fields, mode, case_sensitive
                )
                if found:
                    # Add match metadata
                    announcement_copy = announcement.copy()
                    announcement_copy['_search_matches'] = matches_by_field
                    matched_announcements.append(announcement_copy)
                    
                    # Mark URL as seen
                    if url:
                        seen_urls.add(url)

            # Search full content with deduplication (using same or extended fields)
            content_fields = fields + ['full_content']
            for content in scraper_data.get('full_content', []):
                url = content.get('url', '')
                
                # Skip if we've seen this URL before (deduplication)
                if url and url in seen_urls:
                    self.skipped_duplicates += 1
                    continue
                
                found, matches_by_field = self._search_in_item(
                    content, keywords, content_fields, mode, case_sensitive
                )
                if found:
                    content_copy = content.copy()
                    content_copy['_search_matches'] = matches_by_field
                    matched_full_content.append(content_copy)
                    
                    # Mark URL as seen
                    if url:
                        seen_urls.add(url)

            # Only include scrapers that have matches
            if matched_announcements or matched_full_content:
                self.search_results['results_by_scraper'][scraper_name] = {
                    'scraper_info': scraper_data.get('scraper_info', {}),
                    'announcements': matched_announcements,
                    'full_content': matched_full_content,
                    'statistics': {
                        'matched_announcements': len(matched_announcements),
                        'matched_full_content': len(matched_full_content),
                        'total_matches': len(matched_announcements) + len(matched_full_content)
                    }
                }
                total_matches += len(matched_announcements) + len(matched_full_content)

        # Update summary with deduplication stats
        self.search_results['summary'] = {
            'total_scrapers_with_matches': len(self.search_results['results_by_scraper']),
            'total_matched_announcements': sum(
                data['statistics']['matched_announcements']
                for data in self.search_results['results_by_scraper'].values()
            ),
            'total_matched_full_content': sum(
                data['statistics']['matched_full_content']
                for data in self.search_results['results_by_scraper'].values()
            ),
            'total_matches': total_matches,
            'skipped_duplicates': self.skipped_duplicates,
            'unique_urls_found': len(seen_urls),
            'generated_at': datetime.now().isoformat()
        }

        return self.search_results

    def save_keyword_master(self, output_file: str = "scraped_data/keywords_master.json") -> str:
        """
        Save filtered results to a new master file

        This now does THREE things:
        1. Saves the main master file (as before)
        2. Saves an archived copy with a timestamp in an 'archive' subfolder
        3. Saves separate per-scraper keyword JSONs in a 'per_scraper' subfolder
        """
        output_path = Path(output_file)
        output_path.parent.mkdir(exist_ok=True)

        # 1) MAIN MASTER FILE (same as before)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.search_results, f, indent=2, ensure_ascii=False)
        print(f"Keyword master file saved: {output_path}")
        print(f"Total matches: {self.search_results['summary']['total_matches']}")
        print(f"Skipped duplicates: {self.search_results['summary']['skipped_duplicates']}")

        # 2) ARCHIVE MASTER FILE (timestamped)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir = output_path.parent / "archive"
        archive_dir.mkdir(exist_ok=True)
        archive_path = archive_dir / f"{output_path.stem}_{timestamp}{output_path.suffix}"

        with open(archive_path, 'w', encoding='utf-8') as f:
            json.dump(self.search_results, f, indent=2, ensure_ascii=False)
        print(f"Archive keyword master file saved: {archive_path}")

        # 3) PER-SCRAPER KEYWORD JSONS
        per_scraper_dir = output_path.parent / "per_scraper"
        per_scraper_dir.mkdir(exist_ok=True)

        for scraper_name, scraper_data in self.search_results.get('results_by_scraper', {}).items():
            # Make filename safe-ish
            safe_name = re.sub(r'[^a-zA-Z0-9_-]+', '_', scraper_name)
            scraper_path = per_scraper_dir / f"{output_path.stem}_{safe_name}{output_path.suffix}"

            # Build a per-scraper structure that keeps your formatting
            scraper_summary = scraper_data.get('statistics', {}).copy()
            scraper_summary['scraper_name'] = scraper_name
            scraper_summary['generated_at'] = datetime.now().isoformat()

            scraper_result = {
                'search_info': self.search_results.get('search_info', {}),
                'scraping_history': self.search_results.get('scraping_history', {}),
                'summary': scraper_summary,
                'results_by_scraper': {
                    scraper_name: scraper_data
                }
            }

            with open(scraper_path, 'w', encoding='utf-8') as f:
                json.dump(scraper_result, f, indent=2, ensure_ascii=False)

            print(f"Per-scraper keyword file saved: {scraper_path}")

        return str(output_path)

    def generate_keyword_feed(
        self,
        output_file: str = "feeds/keywords_latest_feed.json",
        max_items: int = 100,
        sort_by: str = 'date'
    ) -> str:
        """
        Generate a lightweight feed from keyword search results

        Args:
            output_file: Path to save the feed
            max_items: Maximum number of items in feed
            sort_by: Sort by 'date' or 'relevance' (number of keyword matches)
        """
        output_path = Path(output_file)
        output_path.parent.mkdir(exist_ok=True)

        all_items = []

        # Collect all matched items (announcements only)
        for scraper_name, scraper_data in self.search_results.get('results_by_scraper', {}).items():
            # Process announcements only
            for announcement in scraper_data.get('announcements', []):
                # Extract category properly - it might be in raw_data or top level
                category = announcement.get('category', '')
                if not category and 'raw_data' in announcement:
                    category = announcement['raw_data'].get('category', '')

                # Extract excerpt properly
                excerpt = announcement.get('excerpt', '')
                if not excerpt and 'raw_data' in announcement:
                    excerpt = announcement['raw_data'].get('excerpt', '')
                    if not excerpt:
                        excerpt = announcement['raw_data'].get('description', '')

                # Truncate excerpt
                if excerpt and len(excerpt) > 200:
                    excerpt = excerpt[:200] + '...'

                all_matched = set()
                for field_keywords in announcement.get('_search_matches', {}).values():
                    all_matched.update(field_keywords)

                item = {
                    'id': announcement.get('id', ''),
                    'title': announcement.get('title', ''),
                    'url': announcement.get('url', ''),
                    'date': announcement.get('date', ''),
                    'category': category if category else 'General',
                    'excerpt': excerpt,
                    'source_website': announcement.get('source_website', ''),
                    'scraper': scraper_name,
                    'scraped_at': announcement.get('scraped_at', ''),
                    'matched_keywords': announcement.get('_search_matches', {}),
                    'relevance_score': len(all_matched)
                }
                all_items.append(item)

        # Sort items
        if sort_by == 'relevance':
            all_items.sort(
                key=lambda x: (x.get('relevance_score', 0), x.get('date', '')),
                reverse=True
            )
        else:  # sort by date
            all_items.sort(
                key=lambda x: x.get('date', '') or x.get('scraped_at', ''),
                reverse=True
            )

        # Limit items (if max_items is set to a reasonable number)
        if max_items and max_items < len(all_items):
            feed_items = all_items[:max_items]
        else:
            feed_items = all_items

        # Create feed
        feed = {
            'feed_type': 'keyword_search',
            'search_info': self.search_results.get('search_info', {}),
            'generated_at': datetime.now().isoformat(),
            'total_items': len(feed_items),
            'max_items': max_items,
            'sort_by': sort_by,
            'items': feed_items
        }

        # Save feed
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(feed, f, indent=2, ensure_ascii=False)

        print(f"Keyword feed saved: {output_path}")
        print(f"Feed contains {len(feed_items)} items (sorted by {sort_by})")
        return str(output_path)

    def generate_report(self) -> str:
        """Generate a text report of search results"""
        report_lines = [
            "KEYWORD SEARCH REPORT",
            f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Master file: {self.master_file}",
            ""
        ]

        # Search parameters
        search_info = self.search_results.get('search_info', {})
        keywords = search_info.get('keywords', [])
        report_lines.extend([
            "SEARCH PARAMETERS",
            f"Total keywords: {len(keywords)}",
            f"Keywords: {', '.join(keywords[:10])}{'...' if len(keywords) > 10 else ''}",
            f"Search mode: {search_info.get('search_mode', 'any')}",
            f"Case sensitive: {search_info.get('case_sensitive', False)}",
            f"Fields searched: {', '.join(search_info.get('fields_searched', []))}",
            ""
        ])

        # Summary
        summary = self.search_results.get('summary', {})
        report_lines.extend([
            "SEARCH RESULTS SUMMARY",
            f"Scrapers with matches: {summary.get('total_scrapers_with_matches', 0)}",
            f"Matched announcements: {summary.get('total_matched_announcements', 0)}",
            f"Matched full content: {summary.get('total_matched_full_content', 0)}",
            f"Total matches: {summary.get('total_matches', 0)}",
            f"Skipped duplicates: {summary.get('skipped_duplicates', 0)}",
            f"Unique URLs found: {summary.get('unique_urls_found', 0)}",
            ""
        ])

        # Per-scraper breakdown
        if self.search_results.get('results_by_scraper'):
            report_lines.append("MATCHES BY SCRAPER")
            for scraper_name, scraper_data in self.search_results['results_by_scraper'].items():
                stats = scraper_data.get('statistics', {})
                report_lines.extend([
                    f"\n{scraper_name}:",
                    f"  Announcements: {stats.get('matched_announcements', 0)}",
                    f"  Full content: {stats.get('matched_full_content', 0)}",
                    f"  Total: {stats.get('total_matches', 0)}"
                ])

                # Show sample matches
                announcements = scraper_data.get('announcements', [])[:3]
                if announcements:
                    report_lines.append("  Sample matches:")
                    for ann in announcements:
                        title = ann.get('title', 'No title')[:60]
                        matches = ann.get('_search_matches', {})
                        report_lines.append(f"    - {title}...")
                        for field, keywords in matches.items():
                            report_lines.append(f"      [{field}]: {', '.join(keywords)}")

        return "\n".join(report_lines)


def load_keywords_from_file(file_path: str) -> List[str]:
    """Load keywords from a text file (one keyword per line)"""
    keywords = []
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        print(f"Error: Keywords file not found: {file_path}")
        sys.exit(1)
    try:
        with open(file_path_obj, 'r', encoding='utf-8') as f:
            for line in f:
                # Strip whitespace and skip empty lines and comments
                keyword = line.strip()
                if keyword and not keyword.startswith('#'):
                    keywords.append(keyword)
        print(f"Loaded {len(keywords)} keywords from {file_path}")
        return keywords
    except Exception as e:
        print(f"Error loading keywords from file: {e}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Search master JSON for keywords and create filtered dataset (with deduplication)'
    )

    parser.add_argument(
        'keywords', nargs='*',
        help='Keywords to search for (optional if using --keywords-file)'
    )
    parser.add_argument(
        '--keywords-file', '-k',
        help='Load keywords from text file (one per line)'
    )
    parser.add_argument(
        '--master-file', default='scraped_data/master_scraped_data.json',
        help='Path to master JSON file'
    )
    parser.add_argument(
        '--output-master', default='scraped_data/keywords_master.json',
        help='Output path for keyword master file'
    )
    parser.add_argument(
        '--output-feed', default='feeds/keywords_latest_feed.json',
        help='Output path for keyword feed'
    )
    parser.add_argument(
        '--fields', nargs='+',
        default=['title', 'excerpt', 'category', 'url'],
        help='Fields to search in'
    )
    parser.add_argument(
        '--mode', choices=['any', 'all'], default='any',
        help='Match any keyword or all keywords'
    )
    parser.add_argument(
        '--case-sensitive', action='store_true',
        help='Enable case-sensitive search'
    )
    parser.add_argument(
        '--max-feed-items', type=int, default=999999,
        help='Maximum items in feed (default: all items)'
    )
    parser.add_argument(
        '--sort-by', choices=['date', 'relevance'], default='date',
        help='Sort feed by date or relevance'
    )
    parser.add_argument(
        '--report-only', action='store_true',
        help='Only generate report, no output files'
    )
    parser.add_argument(
        '--report-file',
        help='Save report to file'
    )

    args = parser.parse_args()

    # Get keywords from file or command line
    keywords = []
    if args.keywords_file:
        keywords = load_keywords_from_file(args.keywords_file)

    # Add command line keywords if provided
    if args.keywords:
        keywords.extend(args.keywords)

    # Check if we have any keywords
    if not keywords:
        print("Error: Please provide keywords either as arguments or via --keywords-file")
        parser.print_help()
        sys.exit(1)

    # Create searcher
    searcher = KeywordSearcher(args.master_file)

    # Load master data
    if not searcher.load_master_data():
        sys.exit(1)

    print(f"\nSearching for {len(keywords)} keywords")
    if len(keywords) <= 10:
        print(f"Keywords: {', '.join(keywords)}")
    else:
        print(f"Keywords: {', '.join(keywords[:10])}... (and {len(keywords) - 10} more)")
    print(f"Search mode: {args.mode}")
    print(f"Fields: {', '.join(args.fields)}")
    print()

    # Perform search
    results = searcher.search_announcements(
        keywords=keywords,
        fields=args.fields,
        mode=args.mode,
        case_sensitive=args.case_sensitive
    )

    # Generate report
    report = searcher.generate_report()
    print("\n" + report)

    # Save report if requested
    if args.report_file:
        report_path = Path(args.report_file)
        report_path.parent.mkdir(exist_ok=True)
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\nReport saved to: {report_path}")

    # Save outputs unless report-only mode
    if not args.report_only:
        # Save keyword master (+ archive + per-scraper)
        searcher.save_keyword_master(args.output_master)

        # Generate and save feed
        searcher.generate_keyword_feed(
            args.output_feed,
            max_items=args.max_feed_items,
            sort_by=args.sort_by
        )

        print(f"\n✓ Keyword master created: {args.output_master}")
        print(f"✓ Keyword feed created: {args.output_feed}")
    else:
        print("\n(Report-only mode: No files created)")


if __name__ == "__main__":
    main()


    #python keyword_search.py --keywords-file keywords.txt
