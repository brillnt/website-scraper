# Website Scraper

A simple tool to scrape website content. It focuses on extracting headings and body text, explicitly ignore navigation elements and footer elements.

The only exception is that the tool finds all nav elements, extracts any links to other pages *on the same domain*, and scrapes those pages as well.

Note: The initial version of this script extracted every link on the page and that cause a lot of pain and errors lol. So this should act as a quick start for gathering copy from websites you work on.

## Installation

```bash
pip install website-scraper
```

## Usage

```bash
website-scraper https://example.com
```

This will create a directory with the domain name and save all scraped content to text files within that directory.
