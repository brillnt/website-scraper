# Website Scraper

A simple tool to scrape website content. It focuses on extracting headings and body text, explicitly ignoring navigation elements and footer elements.

The only exception is that the tool will find all nav elements, extract any links to other pages *on the same domain*, and scrape those pages as well, automatically.

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

Example output:
```
example.com/
├── index.txt
├── about.txt
├── contact-us.txt
```
