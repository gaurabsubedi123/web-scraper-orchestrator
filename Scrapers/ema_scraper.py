import requests
from bs4 import BeautifulSoup
import time
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs
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

class EMAScraper(BaseScraperInterface):
    """EMA (European Medicines Agency) News Scraper implementing BaseScraperInterface"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.base_url = "https://www.ema.europa.eu"
        self.news_url = "https://www.ema.europa.eu/en/news"
        self.delay = 1.5  # Default delay between requests
        
    def get_scraper_info(self) -> Dict[str, str]:
        """Return scraper metadata"""
        return {
            'name': 'EMA News Scraper',
            'version': '1.0',
            'website': 'ema.europa.eu',
            'description': 'Scrapes EMA news articles and full content',
            'supported_date_format': 'YYYY-MM-DD',
            'categories': 'Medicines, Vaccines, Safety Alerts, Press Releases, Guidelines'
        }
    
    def validate_date_format(self, date_str: str) -> bool:
        """Validate if date format is supported"""
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False
    
    def _get_page(self, url: str, params: Dict = None) -> Optional[BeautifulSoup]:
        """Get a page from the EMA website"""
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
            '%d %B %Y',      # 17 September 2025
            '%d %b %Y',      # 17 Sep 2025
            '%d/%m/%Y',      # 17/09/2025
            '%Y-%m-%d',      # 2025-09-17
            '%d-%m-%Y',      # 17-09-2025
            '%B %d, %Y',     # September 17, 2025
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_text, fmt)
            except:
                continue
        
        return None
    
    def _categorize_news(self, title: str, article_type: str = '') -> str:
        """Categorize news based on title and type"""
        title_lower = title.lower()
        type_lower = article_type.lower()
        
        # Check article type first
        if 'press release' in type_lower:
            return "Press Release"
        elif 'guideline' in type_lower:
            return "Guideline"
        elif 'safety' in type_lower or 'alert' in type_lower:
            return "Safety Alert"
        
        # Check title content
        if any(word in title_lower for word in ['vaccine', 'immunisation', 'immunization']):
            return "Vaccine"
        elif any(word in title_lower for word in ['safety', 'warning', 'risk', 'side effect']):
            return "Safety Alert"
        elif any(word in title_lower for word in ['approval', 'authorisation', 'authorization', 'recommended']):
            return "Approval/Authorization"
        elif any(word in title_lower for word in ['meeting', 'committee', 'board']):
            return "Committee News"
        elif any(word in title_lower for word in ['guideline', 'guidance', 'recommendation']):
            return "Guideline"
        
        return "General"
    
    def _scrape_page(self, page_num: int = 0) -> List[Dict[str, Any]]:
        """Scrape one page of EMA news"""
        params = {'page': page_num} if page_num > 0 else None
        soup = self._get_page(self.news_url, params)
        
        if not soup:
            return []
        
        articles = []
        processed_urls = set()
        
        # Find all article/news items
        # EMA uses various selectors - try multiple approaches
        article_containers = (
            soup.find_all('article') or
            soup.find_all('div', class_=re.compile(r'(view-content|news|article|item)', re.I)) or
            soup.find_all('div', class_=re.compile(r'(row|list)', re.I))
        )
        
        for container in article_containers:
            try:
                # Find title link
                title_link = (
                    container.find('a', href=re.compile(r'/en/(news|medicines)')) or
                    container.find('h2', class_=re.compile(r'title', re.I))
                )
                
                if not title_link:
                    title_link = container.find('a', href=True)
                
                if not title_link:
                    continue
                
                # Get URL
                if title_link.name == 'a':
                    href = title_link.get('href', '')
                else:
                    link = title_link.find('a', href=True)
                    href = link.get('href', '') if link else ''
                
                if not href:
                    continue
                
                # Build full URL
                if href.startswith('/'):
                    full_url = self.base_url + href
                elif not href.startswith('http'):
                    full_url = urljoin(self.base_url, href)
                else:
                    full_url = href
                
                # Skip if already processed or not a news/medicine article
                if full_url in processed_urls:
                    continue
                if '/en/news' not in full_url and '/en/medicines' not in full_url:
                    continue
                
                processed_urls.add(full_url)
                
                # Get title
                title = title_link.get_text(strip=True)
                if not title or len(title) < 10:
                    continue
                
                # Get date
                date_elem = (
                    container.find('time') or
                    container.find('span', class_=re.compile(r'date', re.I)) or
                    container.find('div', class_=re.compile(r'date', re.I))
                )
                
                date_found = None
                if date_elem:
                    date_text = date_elem.get('datetime') or date_elem.get_text(strip=True)
                    date_found = self._parse_date(date_text)
                
                # Get article type/category
                type_elem = (
                    container.find('span', class_=re.compile(r'(type|category)', re.I)) or
                    container.find('div', class_=re.compile(r'(type|category)', re.I))
                )
                article_type = type_elem.get_text(strip=True) if type_elem else ''
                
                # Get excerpt/summary
                excerpt_elem = (
                    container.find('p') or
                    container.find('div', class_=re.compile(r'(summary|excerpt|description)', re.I))
                )
                excerpt = excerpt_elem.get_text(strip=True) if excerpt_elem else title
                if len(excerpt) > 200:
                    excerpt = excerpt[:200] + "..."
                
                # Create standardized article
                article = {
                    'id': str(uuid.uuid4()),
                    'title': title,
                    'url': full_url,
                    'date': date_found.strftime('%Y-%m-%d') if date_found else '',
                    'category': self._categorize_news(title, article_type),
                    'article_type': article_type,
                    'excerpt': excerpt,
                    'source': 'EMA News'
                }
                
                articles.append(article)
                
            except Exception as e:
                print(f"Error parsing article container: {e}")
                continue
        
        print(f"Found {len(articles)} articles on page {page_num + 1}")
        return articles
    
    def scrape_announcements(self, start_date: str, end_date: str, **kwargs) -> List[Dict[str, Any]]:
        """Scrape announcements within a date range"""
        max_pages = kwargs.get('max_pages', 20)
        
        # Validate and parse dates
        if not self.validate_date_format(start_date) or not self.validate_date_format(end_date):
            raise ValueError("Invalid date format. Use YYYY-MM-DD")
        
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        print(f"Scraping EMA news from {start_date} to {end_date}")
        
        all_articles = []
        
        for page in range(max_pages):
            page_articles = self._scrape_page(page)
            
            if not page_articles:
                print(f"No articles found on page {page + 1}, stopping")
                break
            
            # Filter by date
            filtered = []
            has_older_than_start = False
            
            for article in page_articles:
                if article['date']:
                    article_date = datetime.strptime(article['date'], '%Y-%m-%d')
                    
                    if start_dt <= article_date <= end_dt:
                        filtered.append(article)
                        print(f"INCLUDED: {article['title'][:60]}... ({article['date']})")
                    elif article_date < start_dt:
                        has_older_than_start = True
                        print(f"TOO OLD: {article['title'][:60]}... ({article['date']})")
                    else:
                        print(f"TOO NEW: {article['title'][:60]}... ({article['date']})")
                else:
                    # Include articles without dates by default
                    filtered.append(article)
                    print(f"NO DATE: {article['title'][:60]}... (included)")
            
            all_articles.extend(filtered)
            print(f"Page {page + 1}: {len(filtered)} articles in date range\n")
            
            # If we found articles older than our start date, we can stop
            if has_older_than_start and page > 2:
                print("Found articles older than start date, stopping search")
                break
        
        return all_articles
    
    def _extract_full_content(self, soup: BeautifulSoup, url: str) -> Dict[str, Any]:
        """Extract comprehensive content from an EMA article page"""
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
            'medicine_name': '',
            'active_substance': '',
            'therapeutic_area': '',
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
                soup.find('div', class_=re.compile(r'date', re.I))
            )
            if date_elem:
                date_text = date_elem.get('datetime') or date_elem.get_text(strip=True)
                content_data['date_published'] = date_text
            
            # Extract medicine-specific information
            medicine_elem = soup.find('div', class_=re.compile(r'medicine', re.I))
            if medicine_elem:
                # Medicine name
                name_elem = medicine_elem.find('strong') or medicine_elem.find('h2')
                if name_elem:
                    content_data['medicine_name'] = name_elem.get_text(strip=True)
                
                # Active substance
                substance_pattern = r'Active substance[s]?:?\s*([^\n\r]+)'
                substance_match = re.search(substance_pattern, medicine_elem.get_text(), re.I)
                if substance_match:
                    content_data['active_substance'] = substance_match.group(1).strip()
                
                # Therapeutic area
                area_pattern = r'Therapeutic area[s]?:?\s*([^\n\r]+)'
                area_match = re.search(area_pattern, medicine_elem.get_text(), re.I)
                if area_match:
                    content_data['therapeutic_area'] = area_match.group(1).strip()
            
            # Extract main content
            content_selectors = [
                '.field--name-body',
                '.field--type-text-with-summary',
                '.content',
                '.main-content',
                'main',
                '[role="main"]',
                '.node-content'
            ]
            
            main_content = ""
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    # Remove unwanted elements
                    for unwanted in content_elem.select('nav, aside, .sidebar, .menu, .navigation, script, style'):
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
            
            # Extract contact information
            contact_patterns = [
                r'Contact:?\s*([^,\n]+)',
                r'For more information:?\s*([^,\n]+)',
                r'(\+[\d\s-]+)',  # Phone numbers with country code
                r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})'  # Email addresses
            ]
            
            full_text = soup.get_text()
            contacts = []
            for pattern in contact_patterns:
                matches = re.findall(pattern, full_text, re.IGNORECASE)
                contacts.extend(matches)
            
            content_data['contact_info'] = ', '.join(set(contacts)) if contacts else ''
            
            # Extract tags/keywords
            tag_selectors = ['.tags a', '.keywords a', '.field--name-field-keywords a']
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
    
    parser = argparse.ArgumentParser(description='EMA Scraper - Standalone Mode')
    parser.add_argument('--start-date', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--max-pages', type=int, default=20, help='Max pages to scrape')
    parser.add_argument('--full-content', action='store_true', help='Also scrape full content')
    parser.add_argument('--output', default='ema_results.json', help='Output file')
    
    args = parser.parse_args()
    
    # Create scraper instance
    scraper = EMAScraper()
    
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