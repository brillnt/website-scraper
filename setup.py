from setuptools import setup, find_packages

setup(
    name="website-scraper",
    version="0.1.0",
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