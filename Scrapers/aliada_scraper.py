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


class AliadaScraper(BaseScraperInterface):
    """Aliada Therapeutics Press Releases Scraper"""

    def __init__(self):
        self.base_url = "https://investors.alnylam.com/press-releases"
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
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.117 Safari/537.36")

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
            'name': 'Aliada Therapeutics Scraper',
            'version': '1.0',
            'website': 'investors.alnylam.com',
            'description': 'Scrapes Aliada Therapeutics press releases',
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
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@id, 'onetrust-accept-btn-handler')]"))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", cookie_button)
            time.sleep(1)
            cookie_button.click()
            print("Accepted cookies")
            time.sleep(1)
            return True
        except:
            return False

    def _get_all_links(self, driver) -> List[str]:
        """Get all article links using pagination"""
        links = []

        try:
            driver.get(self.base_url)
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(3)

            # Handle cookies
            self._handle_cookies(driver)

            page_count = 0
            max_pages = 50

            while page_count < max_pages:
                try:
                    # Get container with articles
                    try:
                        container = driver.find_element(By.CSS_SELECTOR, "div.financial-info-table")
                    except:
                        container = driver

                    # Find all links in container
                    link_elements = container.find_elements(By.TAG_NAME, "a")
                    base_domain = urlparse(self.base_url).netloc

                    for element in link_elements:
                        href = element.get_attribute("href")
                        if href and href.startswith("http") and not href.lower().endswith(".pdf"):
                            # Filter for internal links
                            link_domain = urlparse(href).netloc
                            if link_domain == base_domain:
                                links.append(href)

                    # Try to find and click next button
                    try:
                        next_button = WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.XPATH, "//a[contains(@rel, 'next')]"))
                        )
                        driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", next_button)
                        time.sleep(3)
                        page_count += 1
                        print(f"Navigated to page {page_count + 1}")
                    except TimeoutException:
                        print("No more pages found")
                        break

                except Exception as e:
                    print(f"Error during pagination: {e}")
                    break

            links = list(set(links))  # Remove duplicates
            print(f"Found {len(links)} unique article links")

        except Exception as e:
            print(f"Error getting links: {e}")

        return links

    def scrape_announcements(self, start_date: str, end_date: str, **kwargs) -> List[Dict[str, Any]]:
        """Scrape announcements within a date range"""
        if not self.validate_date_format(start_date) or not self.validate_date_format(end_date):
            raise ValueError("Invalid date format. Use YYYY-MM-DD")

        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')

        print(f"Scraping Aliada Therapeutics press releases from {start_date} to {end_date}")

        driver = self._setup_driver()
        if not driver:
            return []

        try:
            links = self._get_all_links(driver)
            announcements = []

            for link in links:
                try:
                    driver.get(link)
                    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
                    time.sleep(self.delay)

                    soup = BeautifulSoup(driver.page_source, 'html.parser')

                    # Extract title
                    title = ""
                    title_elem = soup.find("h2", class_=["press-d-title", "mt-0"])
                    if title_elem:
                        title = title_elem.text.strip()

                    # Extract date
                    date_str = ""
                    date_elem = soup.find("p", class_="event-date")
                    if date_elem:
                        date_str = date_elem.text.strip()

                    # Parse and filter by date
                    parsed_date = self._parse_date(date_str)
                    if parsed_date:
                        if not (start_dt <= parsed_date <= end_dt):
                            continue
                        date_str = parsed_date.strftime('%Y-%m-%d')

                    # Extract excerpt
                    excerpt = title[:200] if title else ""

                    announcement = {
                        'id': str(uuid.uuid4()),
                        'title': title,
                        'url': link,
                        'date': date_str,
                        'category': 'Press Release',
                        'excerpt': excerpt,
                        'source': 'Aliada Therapeutics'
                    }

                    announcements.append(announcement)
                    print(f"Added: {title[:60]}... ({date_str})")

                except Exception as e:
                    print(f"Error processing {link}: {e}")
                    continue

            print(f"Found {len(announcements)} announcements in date range")
            return announcements

        finally:
            self._close_driver()

    def scrape_full_content(self, announcement_urls: List[str], **kwargs) -> List[Dict[str, Any]]:
        """Scrape full content from announcement URLs"""
        print(f"Scraping full content from {len(announcement_urls)} URLs...")

        driver = self._setup_driver()
        if not driver:
            return []

        try:
            full_content = []

            for i, url in enumerate(announcement_urls, 1):
                print(f"Processing {i}/{len(announcement_urls)}: {url}")

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
                        'metadata': {}
                    }

                    # Extract title
                    title_elem = soup.find("h2", class_=["press-d-title", "mt-0"])
                    if title_elem:
                        content_data['title'] = title_elem.text.strip()

                    # Extract date
                    date_elem = soup.find("p", class_="event-date")
                    if date_elem:
                        content_data['date_published'] = date_elem.text.strip()

                    # Extract body content
                    body_text = []
                    body_containers = soup.select("div.col-sm-9")
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
                    print(f"Success! Extracted {content_data['word_count']} words")

                except Exception as e:
                    print(f"Error: {e}")
                    continue

            print(f"Successfully scraped: {len(full_content)}/{len(announcement_urls)}")
            return full_content

        finally:
            self._close_driver()


if __name__ == "__main__":
    # Standalone testing
    scraper = AliadaScraper()
    info = scraper.get_scraper_info()
    print(f"Running {info['name']} v{info['version']}")
