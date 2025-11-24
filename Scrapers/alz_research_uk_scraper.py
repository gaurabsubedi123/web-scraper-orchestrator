from bs4 import BeautifulSoup
import time
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
import uuid
from typing import Dict, List, Any, Optional

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

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


class AlzResearchUKScraper(BaseScraperInterface):
    """Alzheimer's Research UK News Scraper - Improved Version"""

    def __init__(self):
        self.base_url = "https://www.alzheimersresearchuk.org/about-us/latest/news/"
        self.driver = None
        self.delay = 2.0

    def _setup_driver(self):
        """Initialize Selenium driver"""
        if self.driver:
            return self.driver

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1200")
        options.add_argument("--log-level=3")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        try:
            self.driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            return self.driver
        except Exception as e:
            print(f"Failed to initialize Chrome driver: {e}")
            return None

    def _close_driver(self):
        """Close Selenium driver"""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def get_scraper_info(self) -> Dict[str, str]:
        """Return scraper metadata"""
        return {
            'name': "Alzheimer's Research UK Scraper",
            'version': '2.0',
            'website': 'alzheimersresearchuk.org',
            'description': "Scrapes Alzheimer's Research UK news with improved article detection",
            'supported_date_format': 'YYYY-MM-DD'
        }

    def validate_date_format(self, date_str: str) -> bool:
        """Validate if date format is supported"""
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False

    def _parse_date(self, date_text: str) -> Optional[datetime]:
        """Parse date from text"""
        if not date_text:
            return None

        date_text = re.sub(r'\s+', ' ', date_text.strip())

        formats = [
            '%B %d, %Y',
            '%b %d, %Y',
            '%m/%d/%Y',
            '%Y-%m-%d',
            '%B %d %Y',
            '%b. %d, %Y',
            '%d %B %Y',
            '%A %d %B %Y',
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_text, fmt)
            except:
                continue

        return None

    def _handle_cookies(self, driver):
        """Handle cookie consent popup"""
        try:
            cookie_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@id, 'CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll')]"))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", cookie_button)
            time.sleep(1)
            cookie_button.click()
            print("✓ Accepted cookies")
            time.sleep(1)
            return True
        except:
            print("ℹ No cookie banner found")
            return False

    def _get_article_cards(self, driver) -> List[Dict[str, Any]]:
        """Extract article information from currently loaded cards"""
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        articles = []
        
        # Try multiple possible selectors for article cards
        selectors = [
            'article.pp-grid-item',
            'div.pp-grid-item',
            'div.pp-post',
            'div[class*="post-item"]',
            'div[class*="news-item"]',
        ]
        
        article_cards = []
        for selector in selectors:
            article_cards = soup.select(selector)
            if article_cards:
                print(f"✓ Found article cards using selector: {selector}")
                break
        
        if not article_cards:
            print("⚠ Warning: No article cards found with standard selectors")
            print("⚠ Falling back to link extraction...")
            return []
        
        for card in article_cards:
            try:
                # Extract link
                link_elem = card.find('a', href=True)
                if not link_elem:
                    continue
                
                url = link_elem.get('href')
                if not url.startswith('http'):
                    url = urljoin(self.base_url, url)
                
                # Skip PDFs
                if url.lower().endswith('.pdf'):
                    continue
                
                # Extract title
                title = ""
                title_elem = card.find(['h2', 'h3', 'h4'])
                if title_elem:
                    title = title_elem.get_text(strip=True)
                
                # Extract date (might be in various elements)
                date_text = ""
                date_elem = card.find(['time', 'span', 'p'], class_=re.compile(r'date|time|published', re.I))
                if date_elem:
                    date_text = date_elem.get_text(strip=True)
                
                articles.append({
                    'url': url,
                    'title': title,
                    'date_text': date_text
                })
                
            except Exception as e:
                print(f"⚠ Error parsing card: {e}")
                continue
        
        return articles

    def _get_all_article_links(self, driver, start_dt: datetime, end_dt: datetime) -> List[str]:
        """Get all article links by loading more content progressively"""
        all_urls = set()
        seen_urls = set()
        consecutive_no_new = 0
        max_no_new = 3  # Stop after 3 consecutive clicks with no new articles
        
        try:
            driver.get(self.base_url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(3)

            # Handle cookies
            self._handle_cookies(driver)
            
            click_count = 0
            articles_in_range = 0
            articles_before_range = 0

            while True:
                # Get currently visible article cards
                articles = self._get_article_cards(driver)
                
                if not articles:
                    # Fallback: extract all links if card detection fails
                    print("⚠ Using fallback link extraction method")
                    links = driver.find_elements(By.TAG_NAME, "a")
                    for link in links:
                        href = link.get_attribute("href")
                        if href and '/news/' in href and href not in seen_urls:
                            all_urls.add(href)
                            seen_urls.add(href)
                
                new_articles_count = 0
                
                for article in articles:
                    url = article['url']
                    
                    if url in seen_urls:
                        continue
                    
                    seen_urls.add(url)
                    new_articles_count += 1
                    
                    # Try to parse date if available
                    if article['date_text']:
                        parsed_date = self._parse_date(article['date_text'])
                        if parsed_date:
                            if start_dt <= parsed_date <= end_dt:
                                all_urls.add(url)
                                articles_in_range += 1
                            elif parsed_date < start_dt:
                                articles_before_range += 1
                                # If we've seen many articles before our date range, we can stop
                                if articles_before_range > 20:
                                    print(f"✓ Found {articles_before_range} articles before date range, stopping")
                                    return list(all_urls)
                            continue
                    
                    # If no date available on card, add it for later filtering
                    all_urls.add(url)
                
                print(f"Click {click_count}: Found {new_articles_count} new articles (Total unique: {len(all_urls)}, In range: {articles_in_range})")
                
                if new_articles_count == 0:
                    consecutive_no_new += 1
                    if consecutive_no_new >= max_no_new:
                        print(f"✓ No new articles after {max_no_new} clicks, stopping")
                        break
                else:
                    consecutive_no_new = 0

                # Try to find and click load more button
                try:
                    # Try multiple selectors for load more button
                    load_more_selectors = [
                        "//span[contains(@class, 'pp-grid-loader-text') and contains(text(), 'Load More')]",
                        "//button[contains(text(), 'Load More')]",
                        "//a[contains(text(), 'Load More')]",
                        "//*[contains(@class, 'load-more')]"
                    ]
                    
                    load_more_button = None
                    for selector in load_more_selectors:
                        try:
                            load_more_button = WebDriverWait(driver, 3).until(
                                EC.presence_of_element_located((By.XPATH, selector))
                            )
                            if load_more_button:
                                break
                        except:
                            continue
                    
                    if not load_more_button:
                        print("✓ No more 'Load More' button found")
                        break
                    
                    # Scroll to button and click
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", load_more_button)
                    time.sleep(1)
                    
                    # Try click, then JavaScript click if needed
                    try:
                        load_more_button.click()
                    except:
                        driver.execute_script("arguments[0].click();", load_more_button)
                    
                    time.sleep(3)  # Wait for content to load
                    click_count += 1
                    
                    # Safety limit
                    if click_count >= 100:
                        print("⚠ Reached maximum click limit (100)")
                        break
                    
                except TimeoutException:
                    print("✓ No more 'Load More' button found")
                    break
                except Exception as e:
                    print(f"⚠ Error clicking 'Load More': {e}")
                    break

            print(f"\n{'='*60}")
            print(f"✓ Collected {len(all_urls)} unique article URLs")
            print(f"✓ Articles confirmed in date range: {articles_in_range}")
            print(f"{'='*60}\n")

        except Exception as e:
            print(f"❌ Error getting links: {e}")

        return list(all_urls)

    def scrape_announcements(self, start_date: str, end_date: str, **kwargs) -> List[Dict[str, Any]]:
        """Scrape announcements within a date range"""
        if not self.validate_date_format(start_date) or not self.validate_date_format(end_date):
            raise ValueError("Invalid date format. Use YYYY-MM-DD")

        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')

        print(f"\n{'='*60}")
        print(f"Scraping Alzheimer's Research UK News")
        print(f"Date range: {start_date} to {end_date}")
        print(f"{'='*60}\n")

        driver = self._setup_driver()
        if not driver:
            return []

        try:
            # Get all article links
            links = self._get_all_article_links(driver, start_dt, end_dt)
            
            if not links:
                print("⚠ No article links found")
                return []
            
            announcements = []
            skipped_count = 0

            for idx, link in enumerate(links, 1):
                print(f"\n[{idx}/{len(links)}] Processing: {link}")
                
                try:
                    driver.get(link)
                    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                    time.sleep(self.delay)

                    soup = BeautifulSoup(driver.page_source, 'html.parser')

                    # Extract title
                    title = ""
                    title_elem = soup.select_one("h1.fl-heading")
                    if not title_elem:
                        title_elem = soup.find('h1')
                    if title_elem:
                        title = title_elem.text.strip()

                    # Extract author and date
                    author = ""
                    date_str = ""
                    date_elements = soup.select("div.fl-rich-text")
                    for date_element in date_elements:
                        p_tag = date_element.find("p")
                        if p_tag:
                            text = p_tag.text.strip()
                            if "|" in text or "by " in text.lower():
                                if "|" in text:
                                    parts = text.split("|", 1)
                                    author_part = parts[0].strip()
                                    date_part = parts[1].strip()

                                    if author_part.lower().startswith("by "):
                                        author = author_part[3:].strip()
                                    else:
                                        author = author_part

                                    date_str = date_part
                                else:
                                    date_str = text.strip()
                                break

                    # Parse and filter by date
                    parsed_date = self._parse_date(date_str)
                    if parsed_date:
                        if not (start_dt <= parsed_date <= end_dt):
                            print(f"  ⊘ Skipped: Date {parsed_date.strftime('%Y-%m-%d')} outside range")
                            skipped_count += 1
                            continue
                        date_str = parsed_date.strftime('%Y-%m-%d')
                    else:
                        print(f"  ⚠ Warning: Could not parse date '{date_str}'")

                    # Extract excerpt
                    excerpt = title[:200] if title else ""

                    announcement = {
                        'id': str(uuid.uuid4()),
                        'title': title,
                        'url': link,
                        'date': date_str,
                        'category': 'Research News',
                        'excerpt': excerpt,
                        'author': author,
                        'source': "Alzheimer's Research UK"
                    }

                    announcements.append(announcement)
                    print(f"  ✓ Added: {title[:50]}... ({date_str})")

                except Exception as e:
                    print(f"  ❌ Error: {e}")
                    continue

            print(f"\n{'='*60}")
            print(f"✓ Successfully scraped {len(announcements)} announcements")
            print(f"⊘ Skipped {skipped_count} articles outside date range")
            print(f"{'='*60}\n")
            
            return announcements

        finally:
            self._close_driver()

    def scrape_full_content(self, announcement_urls: List[str], **kwargs) -> List[Dict[str, Any]]:
        """Scrape full content from announcement URLs"""
        print(f"\n{'='*60}")
        print(f"Scraping full content from {len(announcement_urls)} URLs")
        print(f"{'='*60}\n")

        driver = self._setup_driver()
        if not driver:
            return []

        try:
            full_content = []

            for i, url in enumerate(announcement_urls, 1):
                print(f"\n[{i}/{len(announcement_urls)}] {url}")

                try:
                    driver.get(url)
                    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                    time.sleep(self.delay)

                    soup = BeautifulSoup(driver.page_source, 'html.parser')

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
                        'author': ''
                    }

                    # Extract title
                    title_elem = soup.select_one("h1.fl-heading")
                    if not title_elem:
                        title_elem = soup.find('h1')
                    if title_elem:
                        content_data['title'] = title_elem.text.strip()

                    # Extract author and date
                    date_elements = soup.select("div.fl-rich-text")
                    for date_element in date_elements:
                        p_tag = date_element.find("p")
                        if p_tag:
                            text = p_tag.text.strip()
                            if "|" in text or "by " in text.lower():
                                if "|" in text:
                                    parts = text.split("|", 1)
                                    author_part = parts[0].strip()
                                    date_part = parts[1].strip()

                                    if author_part.lower().startswith("by "):
                                        content_data['author'] = author_part[3:].strip()
                                    else:
                                        content_data['author'] = author_part

                                    content_data['date_published'] = date_part
                                else:
                                    content_data['date_published'] = text.strip()
                                break

                    # Extract body content
                    body_text = []
                    body_containers = soup.select("div.fl-module-content.fl-node-content")
                    if body_containers:
                        for block in body_containers:
                            paragraphs = block.find_all("p")
                            for p in paragraphs:
                                txt = p.get_text(strip=True)
                                if txt:
                                    body_text.append(txt)

                    content_data['full_content'] = "\n\n".join(body_text)
                    content_data['word_count'] = len(content_data['full_content'].split())

                    # Extract images
                    images = []
                    for img in soup.find_all('img'):
                        img_src = img.get('src', '')
                        if img_src:
                            images.append({
                                'src': urljoin(url, img_src),
                                'alt': img.get('alt', ''),
                                'title': img.get('title', '')
                            })
                    content_data['images'] = images

                    # Extract links
                    links = []
                    for link in soup.find_all('a', href=True):
                        links.append({
                            'url': urljoin(url, link.get('href')),
                            'text': link.get_text(strip=True),
                            'title': link.get('title', '')
                        })
                    content_data['links'] = links

                    full_content.append(content_data)
                    print(f"  ✓ Success! {content_data['word_count']} words extracted")

                except Exception as e:
                    print(f"  ❌ Error: {e}")
                    continue

            print(f"\n{'='*60}")
            print(f"✓ Successfully scraped: {len(full_content)}/{len(announcement_urls)}")
            print(f"{'='*60}\n")
            
            return full_content

        finally:
            self._close_driver()


if __name__ == "__main__":
    scraper = AlzResearchUKScraper()
    info = scraper.get_scraper_info()
    print(f"Running {info['name']} v{info['version']}")
    
    # Test with a date range
    announcements = scraper.scrape_announcements('2024-01-01', '2024-12-31')
    print(f"\nTotal announcements found: {len(announcements)}")