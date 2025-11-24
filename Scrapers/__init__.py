"""
Web Scrapers Package
Contains all website-specific scraper modules
"""

# This file makes the scrapers directory a Python package
# It can be empty, but we'll add some useful imports

from pathlib import Path

# Package metadata
__version__ = "1.0.0"
__author__ = "Gaurab Subedi"
__description__ = "Collection of web scrapers for press releases and announcements"

# Make the scrapers directory discoverable
SCRAPERS_DIR = Path(__file__).parent