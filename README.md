# Web Scraper Orchestrator

A universal web scraping system that manages multiple website scrapers with deduplication and standardized output.

## Features

- **Modular Design**: Easy to add new scrapers for different websites
- **URL Deduplication**: Prevents re-scraping the same content  
- **Single Master File**: Maintains all data in one JSON file
- **Standardized Output**: Consistent format across all scrapers
- **Error Handling**: Robust error management and reporting

## Currently Supported Sites

- **FDA**: Press announcements and safety alerts
- Add more scrapers easily!

## Quick Start

1. **Install Dependencies**
```bash
   pip install requests beautifulsoup4

## Run fda scrappers
python base_scraper.py --start-date yyyy-mm-dd --end-date yyyy-mm-dd --scraper fda_scraper

## Run All Scrappers
python base_scraper.py --start-date yyyy-mm-dd --end-date yyyy-mm-dd
