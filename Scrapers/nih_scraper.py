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

class NIHScraper(BaseScraperInterface):
    """NIH (National Institutes of Health) News Releases Scraper implementing BaseScraperInterface"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.base_url = "https://www.nih.gov"
        self.news_url = "https://www.nih.gov/news-events/news-releases"
        self.delay = 1.0  # Default delay between requests
        
    def get_scraper_info(self) -> Dict[str, str]:
        """Return scraper metadata"""
        return {
            'name': 'NIH News Releases Scraper',
            'version': '1.1',
            'website': 'nih.gov',
            'description': 'Scrapes NIH news releases and full content',
            'supported_date_format': 'YYYY-MM-DD',
            'categories': 'Research, Health, Medical Breakthroughs, Clinical Trials, Policy'
        }
    
    def validate_date_format(self, date_str: str) -> bool:
        """Validate if date format is supported"""
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False
    
    def _get_page(self, url: str, params: Dict = None) -> Optional[BeautifulSoup]:
        """Get a page from the NIH website"""
        try:
            print(f"Fetching: {url}")
            if params:
                print(f"Parameters: {params}")
            
            response = self.session.get(url, params=params, timeout=30)
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
            '%B %d, %Y',      # September 17, 2025
            '%b %d, %Y',      # Sep 17, 2025
            '%m/%d/%Y',       # 09/17/2025
            '%Y-%m-%d',       # 2025-09-17
            '%B %d %Y',       # September 17 2025
            '%b. %d, %Y',     # Sep. 17, 2025
            '%d %B %Y',       # 17 September 2025
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_text, fmt)
            except:
                continue
        
        return None
    
    def _categorize_release(self, title: str, content: str = '') -> str:
        """Categorize news release based on title and content"""
        text = (title + ' ' + content).lower()
        
        if any(word in text for word in ['clinical trial', 'study', 'research', 'finding']):
            return "Research"
        elif any(word in text for word in ['cancer', 'tumor', 'oncology']):
            return "Cancer Research"
        elif any(word in text for word in ['brain', 'neurological', 'alzheimer', 'parkinson']):
            return "Neuroscience"
        elif any(word in text for word in ['heart', 'cardiovascular', 'cardiac']):
            return "Cardiovascular"
        elif any(word in text for word in ['vaccine', 'immunization', 'antibody']):
            return "Vaccines & Immunology"
        elif any(word in text for word in ['diabetes', 'insulin', 'glucose']):
            return "Diabetes"
        elif any(word in text for word in ['gene', 'genetic', 'dna', 'genome']):
            return "Genomics"
        elif any(word in text for word in ['drug', 'treatment', 'therapy', 'medication']):
            return "Treatment & Therapeutics"
        elif any(word in text for word in ['policy', 'funding', 'budget', 'director']):
            return "Policy & Administration"
        elif any(word in text for word in ['aging', 'elderly', 'senior']):
            return "Aging Research"
        
        return "General Health"
    
    def _scrape_page(self, page_num: int = 0) -> List[Dict[str, Any]]:
        """Scrape one page of NIH news releases"""
        params = {'page': page_num} if page_num > 0 else None
        soup = self._get_page(self.news_url, params)
        
        if not soup:
            return []
        
        releases = []
        processed_urls = set()
        
        # Debug: Save HTML to see structure
        if page_num == 0:
            with open('nih_debug.html', 'w', encoding='utf-8') as f:
                f.write(str(soup.prettify()))
            print("DEBUG: Saved page HTML to nih_debug.html")
        
        # Try to find all links that point to news releases
        # NIH uses specific URL patterns for news releases
        all_links = soup.find_all('a', href=True)
        
        print(f"DEBUG: Found {len(all_links)} total links on page")
        
        for link in all_links:
            href = link.get('href', '')
            
            # Check if this is a news release link
            # NIH news releases typically have these patterns:
            # /news-events/news-releases/[title-slug]
            if not href or '/news-releases' not in href:
                continue
            
            # Skip the main news-releases page itself
            if href.endswith('/news-releases') or href.endswith('/news-releases/'):
                continue
            
            # Build full URL
            if href.startswith('/'):
                full_url = self.base_url + href
            elif not href.startswith('http'):
                full_url = urljoin(self.base_url, href)
            else:
                full_url = href
            
            # Skip if already processed
            if full_url in processed_urls:
                continue
            processed_urls.add(full_url)
            
            # Get title from link text
            title = link.get_text(strip=True)
            
            # If title is too short, try to find it in parent elements
            if not title or len(title) < 10:
                parent = link.find_parent(['h2', 'h3', 'h4', 'div', 'li'])
                if parent:
                    # Try to get heading text
                    heading = parent.find(['h2', 'h3', 'h4'])
                    if heading:
                        title = heading.get_text(strip=True)
                    else:
                        title = parent.get_text(strip=True)
            
            if not title or len(title) < 10:
                continue
            
            # Try to find date near the link
            date_found = None
            parent = link.find_parent(['div', 'li', 'article'])
            
            if parent:
                # Look for time element
                time_elem = parent.find('time')
                if time_elem:
                    date_text = time_elem.get('datetime') or time_elem.get_text(strip=True)
                    date_found = self._parse_date(date_text)
                
                # Look for date in text
                if not date_found:
                    parent_text = parent.get_text()
                    date_pattern = r'([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4})'
                    date_match = re.search(date_pattern, parent_text)
                    if date_match:
                        date_found = self._parse_date(date_match.group(1))
            
            # If still no date, try to extract from title (sometimes dates are in titles)
            if not date_found:
                date_in_title = re.search(r'([A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4})', title)
                if date_in_title:
                    date_found = self._parse_date(date_in_title.group(1))
                    # Remove date from title
                    title = re.sub(r'[A-Z][a-z]+\.?\s+\d{1,2},?\s+\d{4}\s*[-–—]?\s*', '', title).strip()
            
            # Get excerpt from parent
            excerpt = title
            if parent:
                paragraphs = parent.find_all('p', limit=2)
                if paragraphs:
                    excerpt_parts = []
                    for p in paragraphs:
                        p_text = p.get_text(strip=True)
                        if p_text and p_text != title:
                            excerpt_parts.append(p_text)
                    if excerpt_parts:
                        excerpt = ' '.join(excerpt_parts)
            
            if len(excerpt) > 200:
                excerpt = excerpt[:200] + "..."
            
            # Get NIH institute if visible
            institute = ''
            if parent:
                institute_elem = parent.find(text=re.compile(r'NCI|NHLBI|NIDA|NIAAA|NIAID|NIAMS|NIBIB|NICHD|NIDCD|NIDCR|NIDDK|NEI|NIEHS|NIGMS|NIMH|NIMHD|NINDS|NINR|NLM|NCCIH', re.I))
                if institute_elem:
                    institute = institute_elem.strip()
            
            # Create standardized release
            release = {
                'id': str(uuid.uuid4()),
                'title': title,
                'url': full_url,
                'date': date_found.strftime('%Y-%m-%d') if date_found else '',
                'category': self._categorize_release(title, excerpt),
                'excerpt': excerpt,
                'institute': institute,
                'source': 'NIH News Releases'
            }
            
            releases.append(release)
        
        print(f"Found {len(releases)} releases on page {page_num + 1}")
        return releases
    
    def scrape_announcements(self, start_date: str, end_date: str, **kwargs) -> List[Dict[str, Any]]:
        """Scrape announcements within a date range"""
        max_pages = kwargs.get('max_pages', 20)
        
        # Validate and parse dates
        if not self.validate_date_format(start_date) or not self.validate_date_format(end_date):
            raise ValueError("Invalid date format. Use YYYY-MM-DD")
        
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        print(f"Scraping NIH news releases from {start_date} to {end_date}")
        
        all_releases = []
        
        for page in range(max_pages):
            page_releases = self._scrape_page(page)
            
            if not page_releases:
                print(f"No releases found on page {page + 1}, stopping")
                break
            
            # Filter by date
            filtered = []
            has_older_than_start = False
            
            for release in page_releases:
                if release['date']:
                    release_date = datetime.strptime(release['date'], '%Y-%m-%d')
                    
                    if start_dt <= release_date <= end_dt:
                        filtered.append(release)
                        print(f"INCLUDED: {release['title'][:60]}... ({release['date']})")
                    elif release_date < start_dt:
                        has_older_than_start = True
                        print(f"TOO OLD: {release['title'][:60]}... ({release['date']})")
                    else:
                        print(f"TOO NEW: {release['title'][:60]}... ({release['date']})")
                else:
                    # Include releases without dates by default
                    filtered.append(release)
                    print(f"NO DATE: {release['title'][:60]}... (included)")
            
            all_releases.extend(filtered)
            print(f"Page {page + 1}: {len(filtered)} releases in date range\n")
            
            # If we found releases older than our start date, we can stop
            if has_older_than_start and page > 2:
                print("Found releases older than start date, stopping search")
                break
        
        return all_releases
    
    def _extract_full_content(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Extract comprehensive content from an NIH news release page"""
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
            'metadata': {},
            'institute': '',
            'related_links': [],
        }
        
        try:
            # Extract title
            title_elem = (
                soup.find('h1') or
                soup.find('h1', class_=re.compile(r'title', re.I))
            )
            if title_elem:
                content_data['title'] = title_elem.get_text(strip=True)
            
            # Extract publication date
            date_elem = (
                soup.find('time') or
                soup.find('span', class_=re.compile(r'date', re.I)) or
                soup.find('div', class_=re.compile(r'date', re.I)) or
                soup.find('p', class_=re.compile(r'date', re.I))
            )
            if date_elem:
                date_text = date_elem.get('datetime') or date_elem.get_text(strip=True)
                parsed_date = self._parse_date(date_text)
                content_data['date_published'] = parsed_date.strftime('%Y-%m-%d') if parsed_date else date_text
            
            # Extract NIH institute/center
            institute_patterns = [
                r'Contact:\s*([^,\n]+National\s+Institute[^,\n]+)',
                r'(National\s+Institute\s+(?:of|on)\s+[^,\n]+)',
                r'(NCI|NHLBI|NIDA|NIAAA|NIAID|NIAMS|NIBIB|NICHD|NIDCD|NIDCR|NIDDK|NEI|NIEHS|NIGMS|NIMH|NIMHD|NINDS|NINR|NLM|NCCIH)',
            ]
            
            full_text = soup.get_text()
            for pattern in institute_patterns:
                match = re.search(pattern, full_text, re.IGNORECASE)
                if match:
                    content_data['institute'] = match.group(1).strip()
                    break
            
            # Extract main content
            content_selectors = [
                '.content-body',
                '.news-release-body',
                '.field--name-body',
                '.node-content',
                'article',
                '.main-content',
                'main',
                '[role="main"]'
            ]
            
            main_content = ""
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    # Remove unwanted elements
                    for unwanted in content_elem.select('nav, aside, .sidebar, .menu, .navigation, script, style, .social-share'):
                        unwanted.decompose()
                    
                    # Get clean text content
                    paragraphs = content_elem.find_all(['p', 'div', 'li', 'h2', 'h3', 'h4'])
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
            
            # Extract related links
            related_section = soup.find(['div', 'section'], class_=re.compile(r'related', re.I))
            if related_section:
                related_links = []
                for link in related_section.find_all('a', href=True):
                    related_links.append({
                        'url': urljoin(self.base_url, link.get('href')),
                        'text': link.get_text(strip=True)
                    })
                content_data['related_links'] = related_links
            
            # Extract contact information
            contact_patterns = [
                r'Contact:\s*([^\n]+)',
                r'Media Contact:\s*([^\n]+)',
                r'For more information:?\s*([^\n]+)',
                r'(\d{3}-\d{3}-\d{4})',  # Phone numbers
                r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'  # Email addresses
            ]
            
            contacts = []
            for pattern in contact_patterns:
                matches = re.findall(pattern, full_text, re.IGNORECASE)
                contacts.extend(matches)
            
            content_data['contact_info'] = ', '.join(set([c.strip() for c in contacts if c.strip()])) if contacts else ''
            
            # Extract tags/keywords
            tag_selectors = ['.tags a', '.keywords a', '.field--name-field-tags a']
            tags = []
            for selector in tag_selectors:
                tag_elems = soup.select(selector)
                for tag in tag_elems:
                    tag_text = tag.get_text(strip=True)
                    if tag_text:
                        tags.append(tag_text)
            content_data['tags'] = list(set(tags))
            
            # Extract metadata
            meta_tags = soup.find_all('meta')
            metadata = {}
            for meta in meta_tags:
                name = meta.get('name') or meta.get('property')
                content = meta.get('content')
                if name and content:
                    metadata[name] = content
            
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


# Standalone usage capability
def main():
    """Standalone execution for testing"""
    import argparse
    
    parser = argparse.ArgumentParser(description='NIH Scraper - Standalone Mode')
    parser.add_argument('--start-date', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--max-pages', type=int, default=20, help='Max pages to scrape')
    parser.add_argument('--full-content', action='store_true', help='Also scrape full content')
    parser.add_argument('--output', default='nih_results.json', help='Output file')
    
    args = parser.parse_args()
    
    # Create scraper instance
    scraper = NIHScraper()
    
    # Test scraper info
    info = scraper.get_scraper_info()
    print(f"Running {info['name']} v{info['version']}")
    
    # Scrape announcements
    releases = scraper.scrape_announcements(
        args.start_date, 
        args.end_date, 
        max_pages=args.max_pages
    )
    
    results = {
        'scraper_info': info,
        'announcements': releases,
        'full_content': []
    }
    
    # Scrape full content if requested
    if args.full_content and releases:
        urls = [rel['url'] for rel in releases if rel.get('url')]
        if urls:
            full_content = scraper.scrape_full_content(urls)
            results['full_content'] = full_content
    
    # Save results
    import json
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"Results saved to {args.output}")
    print(f"Total releases: {len(releases)}")
    print(f"Total full content: {len(results['full_content'])}")

if __name__ == "__main__":
    main()