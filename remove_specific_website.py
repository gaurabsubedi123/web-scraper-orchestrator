#!/usr/bin/env python3
"""
Script to remove all content from a specific website in the master JSON file.
Creates a backup before modifying the original file.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
import shutil

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

def remove_website_content(data, website_to_remove, remove_mode='website'):
    """
    Remove content from a specific website or scraper
    
    Args:
        data: Master JSON data
        website_to_remove: Website domain or scraper name to remove
        remove_mode: 'website' or 'scraper'
            - 'website': Removes all items where source_website matches
            - 'scraper': Removes entire scraper from results_by_scraper
    
    Returns:
        Modified data and statistics
    """
    
    stats = {
        'scrapers_removed': [],
        'announcements_removed': 0,
        'full_content_removed': 0,
        'scrapers_remaining': 0,
        'announcements_remaining': 0,
        'full_content_remaining': 0
    }
    
    if remove_mode == 'scraper':
        # Remove entire scraper by name
        if website_to_remove in data['results_by_scraper']:
            scraper_data = data['results_by_scraper'][website_to_remove]
            stats['announcements_removed'] = len(scraper_data.get('announcements', []))
            stats['full_content_removed'] = len(scraper_data.get('full_content', []))
            stats['scrapers_removed'].append(website_to_remove)
            
            del data['results_by_scraper'][website_to_remove]
            print(f"✓ Removed scraper: {website_to_remove}")
        else:
            print(f"⚠ Scraper '{website_to_remove}' not found")
            return data, stats
    
    else:  # remove_mode == 'website'
        # Remove items by source_website across all scrapers
        scrapers_to_remove = []
        
        for scraper_name, scraper_data in data['results_by_scraper'].items():
            # Filter announcements
            original_announcements = scraper_data.get('announcements', [])
            filtered_announcements = [
                item for item in original_announcements 
                if item.get('source_website', '') != website_to_remove
            ]
            removed_announcements = len(original_announcements) - len(filtered_announcements)
            stats['announcements_removed'] += removed_announcements
            
            # Filter full content
            original_content = scraper_data.get('full_content', [])
            filtered_content = [
                item for item in original_content 
                if item.get('source_website', '') != website_to_remove
            ]
            removed_content = len(original_content) - len(filtered_content)
            stats['full_content_removed'] += removed_content
            
            # Update scraper data
            scraper_data['announcements'] = filtered_announcements
            scraper_data['full_content'] = filtered_content
            
            # Update statistics
            if 'statistics' in scraper_data:
                scraper_data['statistics']['total_announcements'] = len(filtered_announcements)
                scraper_data['statistics']['total_full_content'] = len(filtered_content)
            
            # Mark scraper for removal if empty
            if len(filtered_announcements) == 0 and len(filtered_content) == 0:
                scrapers_to_remove.append(scraper_name)
                stats['scrapers_removed'].append(scraper_name)
            
            if removed_announcements > 0 or removed_content > 0:
                print(f"  {scraper_name}: Removed {removed_announcements} announcements, {removed_content} full content items")
        
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

def list_websites(data):
    """List all websites in the master file"""
    websites = {}
    
    for scraper_name, scraper_data in data['results_by_scraper'].items():
        website = scraper_data.get('scraper_info', {}).get('website', 'Unknown')
        announcement_count = len(scraper_data.get('announcements', []))
        content_count = len(scraper_data.get('full_content', []))
        
        if website not in websites:
            websites[website] = {
                'scrapers': [],
                'total_announcements': 0,
                'total_content': 0
            }
        
        websites[website]['scrapers'].append(scraper_name)
        websites[website]['total_announcements'] += announcement_count
        websites[website]['total_content'] += content_count
    
    return websites

def list_scrapers(data):
    """List all scrapers in the master file"""
    scrapers = {}
    
    for scraper_name, scraper_data in data['results_by_scraper'].items():
        scrapers[scraper_name] = {
            'website': scraper_data.get('scraper_info', {}).get('website', 'Unknown'),
            'announcements': len(scraper_data.get('announcements', [])),
            'full_content': len(scraper_data.get('full_content', []))
        }
    
    return scrapers

def print_report(stats):
    """Print removal report"""
    print("\n" + "="*60)
    print("REMOVAL REPORT")
    print("="*60)
    
    if stats['scrapers_removed']:
        print(f"\n✓ Scrapers Removed: {', '.join(stats['scrapers_removed'])}")
    
    print(f"\n📊 Items Removed:")
    print(f"  • Announcements: {stats['announcements_removed']}")
    print(f"  • Full Content: {stats['full_content_removed']}")
    
    print(f"\n📊 Remaining in File:")
    print(f"  • Scrapers: {stats['scrapers_remaining']}")
    print(f"  • Announcements: {stats['announcements_remaining']}")
    print(f"  • Full Content: {stats['full_content_remaining']}")
    
    print("\n" + "="*60)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Remove content from specific websites in the master JSON file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all websites and scrapers
  python remove_website.py --list

  # Remove by website domain
  python remove_website.py --website alzheimersresearchuk.org

  # Remove by scraper name
  python remove_website.py --scraper alz_research_uk_scraper

  # Specify custom master file
  python remove_website.py --website example.org --file custom_data.json

  # Dry run (don't save changes)
  python remove_website.py --website alzheimersresearchuk.org --dry-run
        """
    )
    
    parser.add_argument('--file', '-f', 
                       default='scraped_data/master_scraped_data.json',
                       help='Path to master JSON file (default: scraped_data/master_scraped_data.json)')
    
    parser.add_argument('--website', '-w',
                       help='Website domain to remove (e.g., alzheimersresearchuk.org)')
    
    parser.add_argument('--scraper', '-s',
                       help='Scraper name to remove (e.g., alz_research_uk_scraper)')
    
    parser.add_argument('--list', '-l', action='store_true',
                       help='List all websites and scrapers in the file')
    
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
    
    # List mode
    if args.list:
        print("\n" + "="*60)
        print("AVAILABLE WEBSITES")
        print("="*60)
        
        websites = list_websites(data)
        for website, info in websites.items():
            print(f"\n🌐 {website}")
            print(f"   Announcements: {info['total_announcements']}")
            print(f"   Full Content: {info['total_content']}")
            print(f"   Scrapers: {', '.join(info['scrapers'])}")
        
        print("\n" + "="*60)
        print("AVAILABLE SCRAPERS")
        print("="*60)
        
        scrapers = list_scrapers(data)
        for scraper_name, info in scrapers.items():
            print(f"\n🔧 {scraper_name}")
            print(f"   Website: {info['website']}")
            print(f"   Announcements: {info['announcements']}")
            print(f"   Full Content: {info['full_content']}")
        
        print("\n" + "="*60)
        sys.exit(0)
    
    # Removal mode
    if not args.website and not args.scraper:
        print("❌ Error: Must specify --website or --scraper (or use --list)")
        parser.print_help()
        sys.exit(1)
    
    if args.website and args.scraper:
        print("❌ Error: Cannot specify both --website and --scraper")
        sys.exit(1)
    
    # Determine removal mode
    if args.website:
        target = args.website
        mode = 'website'
        print(f"\n🎯 Target: Remove all content from website '{target}'")
    else:
        target = args.scraper
        mode = 'scraper'
        print(f"\n🎯 Target: Remove scraper '{target}'")
    
    # Create backup unless --no-backup
    if not args.no_backup and not args.dry_run:
        backup_path = create_backup(master_file)
        print(f"💾 Backup created: {backup_path}")
    
    # Remove content
    print(f"\n🔍 Scanning and removing content...")
    modified_data, stats = remove_website_content(data, target, mode)
    
    # Print report
    print_report(stats)
    
    # Save changes
    if args.dry_run:
        print("\n⚠️  DRY RUN: No changes were saved")
        print("   Remove --dry-run flag to save changes")
    else:
        if stats['announcements_removed'] > 0 or stats['full_content_removed'] > 0 or stats['scrapers_removed']:
            save_json(modified_data, master_file)
            print(f"\n✅ Changes saved to: {master_file}")
        else:
            print(f"\n⚠️  No content was removed (target not found)")

if __name__ == "__main__":
    main()