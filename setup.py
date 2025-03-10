from setuptools import setup, find_packages
import os
import re

# Read version from _version.py
with open(os.path.join('website_scraper', '_version.py'), 'r') as f:
    version_file = f.read()
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", version_file, re.M)
    if version_match:
        version = version_match.group(1)
    else:
        raise RuntimeError("Unable to find version string in _version.py")

setup(
    name="website-scraper",
    version=version,
    packages=find_packages(),
    scripts=['bin/website-scraper'],
    
    # Dependencies
    install_requires=[
        'requests',
        'beautifulsoup4',
    ],
    
    # Metadata
    author="Dennis Porter Jr",
    author_email="dennis@brillnt.com",
    description="A tool to scrape website content",
    keywords="web, scraper, content, design",
    url="https://github.com/brillnt/website-scraper",
)