
"""
FDA Press Announcements Scraper - Refactored for Base Scraper System
Implements BaseScraperInterface for integration with the universal scraper orchestrator
"""

import requests
from bs4 import BeautifulSoup
import time
import re
from datetime import datetime
from urllib.parse import urljoin
import uuid
from typing import Dict, List, Any, Optional

from abc import ABC, abstractmethod
class BaseScraperInterface(ABC):
        @abstractmethod
        def get_scraper_info(self) -> Dict[str, str]:
            pass
        
        @abstractmethod
        def scrape_announcements(self, start_date: str, end_date: str, **kwargs) -> List[Dict[str, Any]]:
            pass
        
        @abstractmethod
        def scrape_full_content(self, announcement_urls: List[str], **kwargs) -> List[Dict[str, Any]]:
            pass
        
        @abstractmethod
        def validate_date_format(self, date_str: str) -> bool:
            pass

class FDAScraper(BaseScraperInterface):
    """FDA Press Announcements Scraper implementing BaseScraperInterface"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.base_url = "https://www.fda.gov"
        self.delay = 1.0  # Default delay between requests
        
    def get_scraper_info(self) -> Dict[str, str]:
        """Return scraper metadata"""
        return {
            'name': 'FDA Press Announcements Scraper',
            'version': '2.0',
            'website': 'fda.gov',
            'description': 'Scrapes FDA press announcements and full content',
            'supported_date_format': 'YYYY-MM-DD',
            'categories': 'Drug Safety, Food Safety, Medical Device, Tobacco Products, General'
        }
    
    def validate_date_format(self, date_str: str) -> bool:
        """Validate if date format is supported"""
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False
    
    def _get_page(self, url: str, page: int = 0) -> Optional[BeautifulSoup]:
        """Get a page from the FDA website"""
        try:
            if page > 0:
                url = f"{url}?page={page}"
            
            print(f"Fetching: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            time.sleep(self.delay)
            return BeautifulSoup(response.content, 'html.parser')
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def _parse_date(self, date_text: str) -> Optional[datetime]:
        """Parse date from text"""
        if not date_text:
            return None
            
        # Clean the text
        date_text = re.sub(r'\s+', ' ', date_text.strip())
        
        # Try common formats
        formats = [
            '%B %d, %Y',    # September 17, 2025
            '%b %d, %Y',    # Sep 17, 2025
            '%m/%d/%Y',     # 09/17/2025
            '%Y-%m-%d'      # 2025-09-17
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_text, fmt)
            except:
                continue
        
        return None
    
    def _clean_title(self, title_text: str) -> str:
        """Clean title by removing date prefix"""
        if not title_text:
            return ""
        
        # Remove date prefix like "September 12, 2025- " or "September 12, 2025 - "
        clean_title = re.sub(r'^[A-Za-z]+ \d{1,2}, \d{4}\s*-\s*', '', title_text)
        return clean_title.strip()
    
    def _extract_date_from_title(self, title_text: str) -> Optional[datetime]:
        """Extract date from title if it has date prefix"""
        if not title_text:
            return None
            
        # Look for date at the beginning like "September 12, 2025- "
        date_match = re.match(r'^([A-Za-z]+ \d{1,2}, \d{4})', title_text)
        if date_match:
            return self._parse_date(date_match.group(1))
        
        return None
    
    def _categorize_announcement(self, title: str) -> str:
        """Categorize announcement based on title"""
        title_lower = title.lower()
        
        if any(word in title_lower for word in ['drug', 'medication', 'pharmaceutical']):
            return "Drug Safety"
        elif any(word in title_lower for word in ['food', 'recall', 'contamination']):
            return "Food Safety"
        elif any(word in title_lower for word in ['medical device', 'device']):
            return "Medical Device"
        elif any(word in title_lower for word in ['tobacco', 'cigarette', 'vaping']):
            return "Tobacco Products"
        elif 'roundup' in title_lower:
            return "Roundup"
        
        return "General"
    
    def _scrape_page(self, page_num: int = 0) -> List[Dict[str, Any]]:
        """Scrape one page of press announcements"""
        url = "https://www.fda.gov/news-events/fda-newsroom/press-announcements"
        soup = self._get_page(url, page_num)
        
        if not soup:
            return []
        
        announcements = []
        processed_urls = set()
        
        # Find all links that go to press announcements
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link.get('href', '')
            
            # Check if this is a press announcement link
            if '/press-announcements/' in href and not href.endswith('/press-announcements'):
                if 'fda-newsroom' in href:
                    continue
                
                # Build full URL
                if href.startswith('/'):
                    full_url = self.base_url + href
                else:
                    full_url = href
                
                if full_url in processed_urls:
                    continue
                processed_urls.add(full_url)
                
                # Get title
                raw_title = link.get_text(strip=True)
                if not raw_title or len(raw_title) < 10:
                    continue
                
                # Extract date from title and clean title
                date_from_title = self._extract_date_from_title(raw_title)
                clean_title = self._clean_title(raw_title)
                
                # Try to find additional date info in surrounding elements
                date_found = date_from_title
                if not date_found:
                    parent = link.find_parent()
                    if parent:
                        parent_text = parent.get_text()
                        date_match = re.search(r'([A-Za-z]+ \d{1,2}, \d{4})', parent_text)
                        if date_match:
                            date_found = self._parse_date(date_match.group(1))
                
                # Create standardized announcement
                announcement = {
                    'id': str(uuid.uuid4()),
                    'title': clean_title,
                    'url': full_url,
                    'date': date_found.strftime('%Y-%m-%d') if date_found else '',
                    'category': self._categorize_announcement(clean_title),
                    'excerpt': clean_title if len(clean_title) <= 200 else clean_title[:200] + "...",
                    'raw_title': raw_title,
                    'source': 'FDA Press Announcements'
                }
                
                announcements.append(announcement)
        
        print(f"Found {len(announcements)} announcements on page {page_num + 1}")
        return announcements
    
    def scrape_announcements(self, start_date: str, end_date: str, **kwargs) -> List[Dict[str, Any]]:
        """Scrape announcements within a date range"""
        max_pages = kwargs.get('max_pages', 10)
        
        # Validate and parse dates
        if not self.validate_date_format(start_date) or not self.validate_date_format(end_date):
            raise ValueError("Invalid date format. Use YYYY-MM-DD")
        
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        print(f"Scraping FDA announcements from {start_date} to {end_date}")
        
        all_announcements = []
        
        for page in range(max_pages):
            page_announcements = self._scrape_page(page)
            
            if not page_announcements:
                print(f"No announcements found on page {page + 1}, stopping")
                break
            
            # Filter by date
            filtered = []
            has_older_than_start = False
            
            for ann in page_announcements:
                if ann['date']:
                    ann_date = datetime.strptime(ann['date'], '%Y-%m-%d')
                    
                    if start_dt <= ann_date <= end_dt:
                        filtered.append(ann)
                        print(f"INCLUDED: {ann['title'][:50]}... ({ann['date']})")
                    elif ann_date < start_dt:
                        has_older_than_start = True
                        print(f"TOO OLD: {ann['title'][:50]}... ({ann['date']})")
                    else:
                        print(f"TOO NEW: {ann['title'][:50]}... ({ann['date']})")
                else:
                    print(f"NO DATE: {ann['title'][:50]}... (skipping)")
            all_announcements.extend(filtered)
            print(f"Page {page + 1}: {len(filtered)} announcements in date range\n")
            
            # If we found announcements older than our start date, we can stop
            if has_older_than_start and page > 0:
                print("Found announcements older than start date, stopping search")
                break
        
        return all_announcements
    
    def _extract_full_content(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Extract comprehensive content from an FDA announcement page"""
        content_data = {
            'id': str(uuid.uuid4()),
            'url': url,
            'title': '',
            'date_published': '',
            'full_content': '',
            'word_count': 0,
            'images': [],
            'links': [],
            'contact_info': '',
            'tags': [],
            'comments': [],
            'metadata': {},
            'raw_html': str(soup)[:5000]  # First 5k chars of HTML for debugging
        }
        
        try:
            # Extract title
            title_selectors = ['h1', '.page-title', '.node-title', '[class*="title"]']
            for selector in title_selectors:
                title_elem = soup.select_one(selector)
                if title_elem:
                    content_data['title'] = title_elem.get_text(strip=True)
                    break
            
            # Extract publication date
            date_selectors = ['time', '.date', '.published', '[class*="date"]']
            for selector in date_selectors:
                date_elem = soup.select_one(selector)
                if date_elem:
                    date_text = date_elem.get('datetime') or date_elem.get_text(strip=True)
                    content_data['date_published'] = date_text
                    break
            
            # Extract main content
            content_selectors = [
                '.field--name-body',
                '.content',
                '.node-content', 
                '.press-release-content',
                '.main-content',
                'main',
                '[role="main"]'
            ]
            
            main_content = ""
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    # Remove unwanted elements
                    for unwanted in content_elem.select('nav, aside, .sidebar, .menu, .navigation'):
                        unwanted.decompose()
                    
                    # Get clean text content
                    paragraphs = content_elem.find_all(['p', 'div', 'li'])
                    content_parts = []
                    
                    for para in paragraphs:
                        text = para.get_text(strip=True)
                        if text and len(text) > 20:
                            content_parts.append(text)
                    
                    main_content = '\n\n'.join(content_parts)
                    if main_content:
                        break
            
            # Fallback to all paragraphs
            if not main_content:
                all_paragraphs = soup.find_all('p')
                content_parts = []
                for para in all_paragraphs:
                    text = para.get_text(strip=True)
                    if text and len(text) > 20:
                        content_parts.append(text)
                main_content = '\n\n'.join(content_parts)
            
            content_data['full_content'] = main_content
            content_data['word_count'] = len(main_content.split())
            
            # Extract images
            images = []
            for img in soup.find_all('img'):
                img_data = {
                    'src': img.get('src', ''),
                    'alt': img.get('alt', ''),
                    'title': img.get('title', '')
                }
                if img_data['src']:
                    if img_data['src'].startswith('/'):
                        img_data['src'] = self.base_url + img_data['src']
                    images.append(img_data)
            content_data['images'] = images
            
            # Extract all links
            links = []
            for link in soup.find_all('a', href=True):
                link_data = {
                    'url': link.get('href'),
                    'text': link.get_text(strip=True),
                    'title': link.get('title', '')
                }
                if link_data['url'].startswith('/'):
                    link_data['url'] = self.base_url + link_data['url']
                links.append(link_data)
            content_data['links'] = links
            
            # Extract contact information
            contact_patterns = [
                r'Media Inquiries:?\s*([^,\n]+)',
                r'Contact:?\s*([^,\n]+)', 
                r'For more information:?\s*([^,\n]+)',
                r'(\d{3}-\d{3}-\d{4})',  # Phone numbers
                r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'  # Email addresses
            ]
            
            full_text = soup.get_text()
            contacts = []
            for pattern in contact_patterns:
                matches = re.findall(pattern, full_text, re.IGNORECASE)
                contacts.extend(matches)
            
            content_data['contact_info'] = ', '.join(set(contacts)) if contacts else ''
            
            # Extract tags/categories
            tag_selectors = ['.tags a', '.categories a', '.field--name-field-tags a']
            tags = []
            for selector in tag_selectors:
                tag_elems = soup.select(selector)
                for tag in tag_elems:
                    tag_text = tag.get_text(strip=True)
                    if tag_text:
                        tags.append(tag_text)
            content_data['tags'] = list(set(tags))
            
            # Extract comments (if any comment system exists)
            comment_selectors = ['.comments', '.comment', '#disqus_thread']
            comments = []
            for selector in comment_selectors:
                comment_section = soup.select_one(selector)
                if comment_section:
                    comment_texts = comment_section.find_all(text=True)
                    comment_content = ' '.join([t.strip() for t in comment_texts if t.strip()])
                    if comment_content:
                        comments.append({
                            'content': comment_content,
                            'source': 'page_comments'
                        })
            content_data['comments'] = comments
            
            # Extract metadata
            meta_tags = soup.find_all('meta')
            metadata = {}
            for meta in meta_tags:
                name = meta.get('name') or meta.get('property')
                content = meta.get('content')
                if name and content:
                    metadata[name] = content
            
            # Additional structured data
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                try:
                    import json
                    structured_data = json.loads(script.string)
                    metadata['structured_data'] = structured_data
                    break
                except:
                    pass
            
            content_data['metadata'] = metadata
            
        except Exception as e:
            print(f"Error extracting content from {url}: {e}")
        
        return content_data
    
    def scrape_full_content(self, announcement_urls: List[str], **kwargs) -> List[Dict[str, Any]]:
        """Scrape full content from announcement URLs"""
        delay = kwargs.get('delay', self.delay)
        self.delay = delay
        
        full_content = []
        failed_urls = []
        
        print(f"Scraping full content from {len(announcement_urls)} URLs...")
        
        for i, url in enumerate(announcement_urls, 1):
            if not url:
                continue
                
            print(f"Processing {i}/{len(announcement_urls)}: {url}")
            
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                time.sleep(delay)
                
                soup = BeautifulSoup(response.content, 'html.parser')
                content = self._extract_full_content(soup, url)
                
                if content['full_content']:
                    full_content.append(content)
                    print(f"Success! Extracted {content['word_count']} words")
                else:
                    failed_urls.append(url)
                    print(f"No content extracted")
                    
            except Exception as e:
                failed_urls.append(url)
                print(f"Error: {e}")
        
        print(f"Successfully scraped: {len(full_content)}/{len(announcement_urls)}")
        if failed_urls:
            print(f"Failed URLs: {len(failed_urls)}")
        
        return full_content


# Standalone usage capability for backward compatibility
def main():
    """Standalone execution for testing/backward compatibility"""
    import argparse
    
    parser = argparse.ArgumentParser(description='FDA Scraper - Standalone Mode')
    parser.add_argument('--start-date', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--max-pages', type=int, default=10, help='Max pages to scrape')
    parser.add_argument('--full-content', action='store_true', help='Also scrape full content')
    parser.add_argument('--output', default='fda_results.json', help='Output file')
    
    args = parser.parse_args()
    
    # Create scraper instance
    scraper = FDAScraper()
    
    # Test scraper info
    info = scraper.get_scraper_info()
    print(f"Running {info['name']} v{info['version']}")
    
    # Scrape announcements
    announcements = scraper.scrape_announcements(
        args.start_date, 
        args.end_date, 
        max_pages=args.max_pages
    )
    
    results = {
        'scraper_info': info,
        'announcements': announcements,
        'full_content': []
    }
    
    # Scrape full content if requested
    if args.full_content and announcements:
        urls = [ann['url'] for ann in announcements if ann.get('url')]
        if urls:
            full_content = scraper.scrape_full_content(urls)
            results['full_content'] = full_content
    
    # Save results
    import json
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"Results saved to {args.output}")
    print(f"Total announcements: {len(announcements)}")
    print(f"Total full content: {len(results['full_content'])}")

if __name__ == "__main__":
    main()