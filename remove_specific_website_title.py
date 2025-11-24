#!/usr/bin/env python3
"""
Script to remove specific content by title from a specific website in the master JSON file.
Creates a backup before modifying the original file.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
import shutil
import re

def load_json(file_path):
    """Load JSON file"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: File not found: {file_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in {file_path}: {e}")
        sys.exit(1)

def save_json(data, file_path):
    """Save JSON file"""
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def create_backup(file_path):
    """Create backup of the original file"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = file_path.parent / f"{file_path.stem}_backup_{timestamp}.json"
    shutil.copy2(file_path, backup_path)
    return backup_path

def title_matches(item_title, title_pattern, match_mode='exact'):
    """
    Check if item title matches the pattern
    
    Args:
        item_title: Title from the item
        title_pattern: Pattern to match
        match_mode: 'exact', 'contains', or 'regex'
    
    Returns:
        True if matches, False otherwise
    """
    if not item_title:
        return False
    
    if match_mode == 'exact':
        return item_title.lower() == title_pattern.lower()
    elif match_mode == 'contains':
        return title_pattern.lower() in item_title.lower()
    elif match_mode == 'regex':
        try:
            return bool(re.search(title_pattern, item_title, re.IGNORECASE))
        except re.error:
            print(f"⚠️  Invalid regex pattern: {title_pattern}")
            return False
    
    return False

def remove_content_by_title(data, website, title_pattern, match_mode='exact'):
    """
    Remove content with specific title from a specific website
    
    Args:
        data: Master JSON data
        website: Website domain to filter
        title_pattern: Title pattern to match
        match_mode: 'exact', 'contains', or 'regex'
    
    Returns:
        Modified data and statistics
    """
    
    stats = {
        'announcements_removed': 0,
        'full_content_removed': 0,
        'removed_items': [],
        'scrapers_affected': [],
        'scrapers_remaining': 0,
        'announcements_remaining': 0,
        'full_content_remaining': 0
    }
    
    scrapers_to_remove = []
    
    for scraper_name, scraper_data in data['results_by_scraper'].items():
        scraper_affected = False
        
        # Filter announcements
        original_announcements = scraper_data.get('announcements', [])
        filtered_announcements = []
        
        for item in original_announcements:
            # Check if item is from target website and matches title
            if (item.get('source_website', '') == website and 
                title_matches(item.get('title', ''), title_pattern, match_mode)):
                stats['announcements_removed'] += 1
                stats['removed_items'].append({
                    'scraper': scraper_name,
                    'type': 'announcement',
                    'title': item.get('title', 'N/A'),
                    'url': item.get('url', 'N/A')
                })
                scraper_affected = True
            else:
                filtered_announcements.append(item)
        
        # Filter full content
        original_content = scraper_data.get('full_content', [])
        filtered_content = []
        
        for item in original_content:
            # Check if item is from target website and matches title
            if (item.get('source_website', '') == website and 
                title_matches(item.get('title', ''), title_pattern, match_mode)):
                stats['full_content_removed'] += 1
                stats['removed_items'].append({
                    'scraper': scraper_name,
                    'type': 'full_content',
                    'title': item.get('title', 'N/A'),
                    'url': item.get('url', 'N/A')
                })
                scraper_affected = True
            else:
                filtered_content.append(item)
        
        # Update scraper data
        scraper_data['announcements'] = filtered_announcements
        scraper_data['full_content'] = filtered_content
        
        # Update statistics
        if 'statistics' in scraper_data:
            scraper_data['statistics']['total_announcements'] = len(filtered_announcements)
            scraper_data['statistics']['total_full_content'] = len(filtered_content)
        
        # Mark scraper for tracking
        if scraper_affected:
            stats['scrapers_affected'].append(scraper_name)
        
        # Mark scraper for removal if empty
        if len(filtered_announcements) == 0 and len(filtered_content) == 0:
            scrapers_to_remove.append(scraper_name)
    
    # Remove empty scrapers
    for scraper_name in scrapers_to_remove:
        del data['results_by_scraper'][scraper_name]
        print(f"  ✓ Removed empty scraper: {scraper_name}")
    
    # Update summary statistics
    total_announcements = 0
    total_full_content = 0
    
    for scraper_data in data['results_by_scraper'].values():
        total_announcements += len(scraper_data.get('announcements', []))
        total_full_content += len(scraper_data.get('full_content', []))
    
    stats['scrapers_remaining'] = len(data['results_by_scraper'])
    stats['announcements_remaining'] = total_announcements
    stats['full_content_remaining'] = total_full_content
    
    # Update master summary
    data['summary'] = {
        'total_announcements': total_announcements,
        'total_full_content': total_full_content,
        'total_errors': data['summary'].get('total_errors', 0),
        'scrapers_count': len(data['results_by_scraper']),
        'last_updated': datetime.now().isoformat()
    }
    
    # Update scraping history
    if 'scraping_history' in data:
        data['scraping_history']['last_updated'] = datetime.now().isoformat()
    
    return data, stats

def list_titles_by_website(data, website=None):
    """List all titles from a specific website or all websites"""
    titles_by_website = {}
    
    for scraper_name, scraper_data in data['results_by_scraper'].items():
        # Process announcements
        for item in scraper_data.get('announcements', []):
            site = item.get('source_website', 'Unknown')
            if website and site != website:
                continue
            
            if site not in titles_by_website:
                titles_by_website[site] = []
            
            titles_by_website[site].append({
                'title': item.get('title', 'N/A'),
                'type': 'announcement',
                'scraper': scraper_name
            })
        
        # Process full content
        for item in scraper_data.get('full_content', []):
            site = item.get('source_website', 'Unknown')
            if website and site != website:
                continue
            
            if site not in titles_by_website:
                titles_by_website[site] = []
            
            titles_by_website[site].append({
                'title': item.get('title', 'N/A'),
                'type': 'full_content',
                'scraper': scraper_name
            })
    
    return titles_by_website

def print_report(stats, title_pattern, match_mode):
    """Print removal report"""
    print("\n" + "="*60)
    print("REMOVAL REPORT")
    print("="*60)
    
    print(f"\n🎯 Title Pattern: '{title_pattern}' (mode: {match_mode})")
    
    if stats['scrapers_affected']:
        print(f"\n✓ Scrapers Affected: {', '.join(stats['scrapers_affected'])}")
    
    print(f"\n📊 Items Removed:")
    print(f"  • Announcements: {stats['announcements_removed']}")
    print(f"  • Full Content: {stats['full_content_removed']}")
    
    if stats['removed_items'] and len(stats['removed_items']) <= 20:
        print(f"\n📝 Removed Items:")
        for item in stats['removed_items']:
            print(f"  • [{item['type']}] {item['title']}")
            print(f"    Scraper: {item['scraper']}")
    elif len(stats['removed_items']) > 20:
        print(f"\n📝 Showing first 20 of {len(stats['removed_items'])} removed items:")
        for item in stats['removed_items'][:20]:
            print(f"  • [{item['type']}] {item['title']}")
    
    print(f"\n📊 Remaining in File:")
    print(f"  • Scrapers: {stats['scrapers_remaining']}")
    print(f"  • Announcements: {stats['announcements_remaining']}")
    print(f"  • Full Content: {stats['full_content_remaining']}")
    
    print("\n" + "="*60)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Remove content by title from specific websites in the master JSON file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all titles from a specific website
  python remove_by_title.py --list-titles --website abc.com

  # Remove exact title match
  python remove_by_title.py --website abc.com --title "News" --mode exact

  # Remove titles containing text
  python remove_by_title.py --website abc.com --title "breaking" --mode contains

  # Remove titles matching regex pattern
  python remove_by_title.py --website abc.com --title "^News.*2024$" --mode regex

  # Dry run (don't save changes)
  python remove_by_title.py --website abc.com --title "News" --dry-run

  # Specify custom master file
  python remove_by_title.py --file custom_data.json --website abc.com --title "News"
        """
    )
    
    parser.add_argument('--file', '-f', 
                       default='master_scraped_data.json',
                       help='Path to master JSON file (default: scraped_data/master_scraped_data.json)')
    
    parser.add_argument('--website', '-w',
                       help='Website domain to target (e.g., abc.com)')
    
    parser.add_argument('--title', '-t',
                       help='Title pattern to remove')
    
    parser.add_argument('--mode', '-m',
                       choices=['exact', 'contains', 'regex'],
                       default='exact',
                       help='Match mode: exact (default), contains, or regex')
    
    parser.add_argument('--list-titles', '-l', action='store_true',
                       help='List all titles from specified website')
    
    parser.add_argument('--dry-run', '-d', action='store_true',
                       help='Show what would be removed without saving changes')
    
    parser.add_argument('--no-backup', action='store_true',
                       help='Skip creating backup (not recommended)')
    
    args = parser.parse_args()
    
    # Convert to Path object
    master_file = Path(args.file)
    
    if not master_file.exists():
        print(f"❌ Error: File not found: {master_file}")
        sys.exit(1)
    
    print(f"📂 Loading: {master_file}")
    data = load_json(master_file)
    
    # List titles mode
    if args.list_titles:
        if not args.website:
            print("❌ Error: --website required when using --list-titles")
            sys.exit(1)
        
        print("\n" + "="*60)
        print(f"TITLES FROM: {args.website}")
        print("="*60)
        
        titles_by_website = list_titles_by_website(data, args.website)
        
        if args.website in titles_by_website:
            titles = titles_by_website[args.website]
            print(f"\nFound {len(titles)} items:")
            for item in titles:
                print(f"\n  📄 {item['title']}")
                print(f"     Type: {item['type']}")
                print(f"     Scraper: {item['scraper']}")
        else:
            print(f"\n⚠️  No content found from website: {args.website}")
        
        print("\n" + "="*60)
        sys.exit(0)
    
    # Removal mode
    if not args.website or not args.title:
        print("❌ Error: Both --website and --title are required (or use --list-titles)")
        parser.print_help()
        sys.exit(1)
    
    print(f"\n🎯 Target Website: {args.website}")
    print(f"🎯 Title Pattern: '{args.title}' (mode: {args.mode})")
    
    # Create backup unless --no-backup
    if not args.no_backup and not args.dry_run:
        backup_path = create_backup(master_file)
        print(f"💾 Backup created: {backup_path}")
    
    # Remove content
    print(f"\n🔍 Scanning and removing content...")
    modified_data, stats = remove_content_by_title(data, args.website, args.title, args.mode)
    
    # Print report
    print_report(stats, args.title, args.mode)
    
    # Save changes
    if args.dry_run:
        print("\n⚠️  DRY RUN: No changes were saved")
        print("   Remove --dry-run flag to save changes")
    else:
        if stats['announcements_removed'] > 0 or stats['full_content_removed'] > 0:
            save_json(modified_data, master_file)
            print(f"\n✅ Changes saved to: {master_file}")
        else:
            print(f"\n⚠️  No content was removed (no matching titles found)")

if __name__ == "__main__":
    main()


# python remove_specific_website_title.py --website alzheimersresearchuk.org --title "News"