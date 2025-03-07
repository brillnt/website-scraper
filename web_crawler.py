#!/usr/bin/env python3
import argparse
import json
import os
import re
import time
import urllib.parse
from collections import deque
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

class WebsiteCrawler:
    def __init__(self, root_url, output_dir="output", respect_robots=True, max_depth=10, 
                 max_pages=1000, delay=1, ignore_query_params=True, check_sitemap=True, 
                 output_format="json"):
        self.root_url = self._normalize_url(root_url)
        self.root_domain = urllib.parse.urlparse(self.root_url).netloc
        self.output_dir = output_dir
        self.respect_robots = respect_robots
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.delay = delay
        self.ignore_query_params = ignore_query_params
        self.check_sitemap = check_sitemap
        self.output_format = output_format
        
        # User agent for requests
        self.user_agent = "WebsiteCopyScraper/1.0"
        
        # URL tracking
        self.visited_urls = set()
        self.queued_urls = deque([(self.root_url, 0)])  # URL and its depth from root
        self.page_content = {}
        self.robot_parser = None
        
        # URL exclusion patterns
        self.exclude_url_patterns = [
            r'\.(jpg|jpeg|png|gif|svg|webp|pdf|doc|docx|xls|xlsx|zip|tar|gz|mp3|mp4|avi|mov)$',
            r'(logout|signout|login|signin|cart|checkout|wp-admin|wp-content|feed)',
            r'(#.*$)'  # Exclude URL fragments
        ]
        
        # Text cleanup patterns
        self.text_cleanup_patterns = [
            (r'\s+', ' '),  # Replace multiple whitespace with single space
            (r'^\s+|\s+$', '')  # Remove leading/trailing whitespace
        ]
        
        # Content tags to extract
        self.included_tags = {
            'headings': ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
            'paragraphs': ['p'],
            'lists': ['ul', 'ol'],
            'list_items': ['li'],
            'blockquotes': ['blockquote']
        }
        
        # Common content wrappers
        self.content_wrappers = [
            'main', 'article', 'section', 'div.content', 'div.main', 'div.post', 
            'div#content', 'div#main', 'div.entry', '.post-content', '.entry-content',
            '.article-content', '.content-area'
        ]
        
        # Setup
        if respect_robots:
            self._setup_robot_parser()
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Compile exclusion patterns
        self.exclude_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in self.exclude_url_patterns]
        # Compile text cleanup patterns
        self.cleanup_patterns = [(re.compile(pattern), repl) for pattern, repl in self.text_cleanup_patterns]
        
        # Check for sitemap
        if self.check_sitemap:
            self._check_sitemap()
    
    def _setup_robot_parser(self):
        """Set up the robot parser for robots.txt compliance."""
        self.robot_parser = RobotFileParser()
        robots_url = urllib.parse.urljoin(self.root_url, "/robots.txt")
        self.robot_parser.set_url(robots_url)
        try:
            self.robot_parser.read()
        except Exception as e:
            print(f"Warning: Could not read robots.txt: {e}")
    
    def _check_sitemap(self):
        """Check for sitemap.xml and add found URLs to the queue."""
        sitemap_url = urllib.parse.urljoin(self.root_url, "/sitemap.xml")
        try:
            response = requests.get(sitemap_url, headers={"User-Agent": self.user_agent}, timeout=10)
            if response.status_code == 200:
                print(f"Found sitemap at {sitemap_url}")
                soup = BeautifulSoup(response.text, 'xml')
                urls = soup.find_all('loc')
                
                for url in urls:
                    url_text = url.text
                    if self._is_internal_url(url_text) and url_text not in self.visited_urls:
                        normalized_url = self._normalize_url(url_text)
                        self.queued_urls.append((normalized_url, 0))  # Add as depth 0
                        print(f"Added from sitemap: {normalized_url}")
        except Exception as e:
            print(f"Warning: Could not process sitemap: {e}")
    
    def _normalize_url(self, url):
        """Normalize URL to ensure consistency."""
        parsed = urllib.parse.urlparse(url)
        
        # Ensure the URL has a scheme
        if not parsed.scheme:
            url = f"http://{url}"
            parsed = urllib.parse.urlparse(url)
        
        # Remove trailing slash
        path = parsed.path
        if path.endswith('/') and path != '/':
            path = path[:-1]
        
        # Remove query params if configured to ignore them
        query = parsed.query
        if self.ignore_query_params:
            query = ''
        
        # Reassemble the URL
        normalized = urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            path,
            parsed.params,
            query,
            ''  # Remove fragment
        ))
        
        return normalized
    
    def _is_internal_url(self, url):
        """Check if a URL is internal to the website."""
        parsed = urllib.parse.urlparse(url)
        
        # Check if the domain matches
        if parsed.netloc and parsed.netloc != self.root_domain:
            return False
        
        # Check against excluded patterns
        for pattern in self.exclude_patterns:
            if pattern.search(url):
                return False
        
        return True
    
    def _can_fetch(self, url):
        """Check if a URL can be fetched according to robots.txt."""
        if not self.respect_robots or not self.robot_parser:
            return True
        return self.robot_parser.can_fetch(self.user_agent, url)
    
    def _extract_links(self, soup, page_url, current_depth):
        """Extract internal links from a BeautifulSoup object."""
        links = []
        
        if current_depth >= self.max_depth:
            return links
        
        for anchor in soup.find_all('a', href=True):
            href = anchor['href']
            
            # Skip empty, javascript, and anchor links
            if not href or href.startswith('javascript:') or href.startswith('#'):
                continue
            
            # Resolve relative URLs
            absolute_url = urllib.parse.urljoin(page_url, href)
            normalized_url = self._normalize_url(absolute_url)
            
            # Add to links if internal and not already visited or queued
            if (self._is_internal_url(normalized_url) and 
                normalized_url not in self.visited_urls and 
                normalized_url not in [u for u, _ in self.queued_urls]):
                links.append((normalized_url, current_depth + 1))
        
        return links
    
    def _clean_text(self, text):
        """Clean up text by applying cleanup patterns."""
        if not text:
            return ""
            
        cleaned = text
        for pattern, repl in self.cleanup_patterns:
            cleaned = pattern.sub(repl, cleaned)
        
        return cleaned
    
    def _find_main_content(self, soup):
        """Try to find the main content area of the page."""
        # Look for common content container elements
        for selector in self.content_wrappers:
            if '.' in selector or '#' in selector:
                # CSS selector
                element = soup.select_one(selector)
            else:
                # Tag name
                element = soup.find(selector)
            
            if element:
                return element
        
        # If we can't find a content wrapper, return the body
        return soup.body or soup
    
    def _extract_text_content(self, soup, url):
        """Extract and organize text content from a BeautifulSoup object."""
        # Try to identify page type based on URL and content
        path = urllib.parse.urlparse(url).path
        page_type = "unknown"
        
        if path == "" or path == "/":
            page_type = "homepage"
        elif re.search(r'/(about|about-us)/?$', path, re.IGNORECASE):
            page_type = "about"
        elif re.search(r'/(contact|contact-us)/?$', path, re.IGNORECASE):
            page_type = "contact"
        elif re.search(r'/blog/?$', path, re.IGNORECASE):
            page_type = "blog_index"
        elif re.search(r'/blog/|/news/|/article/|/post/', path, re.IGNORECASE):
            page_type = "blog_post"
        elif re.search(r'/(product|products)/?$', path, re.IGNORECASE):
            page_type = "product_index"
        elif re.search(r'/(product|products)/[^/]+/?$', path, re.IGNORECASE):
            page_type = "product_detail"
        
        content = {
            "url": url,
            "title": self._clean_text(soup.title.text) if soup.title else "No Title",
            "page_type": page_type,
            "meta_description": "",
            "elements": []
        }
        
        # Extract meta description
        meta_desc = soup.find('meta', attrs={"name": "description"})
        if meta_desc:
            content["meta_description"] = self._clean_text(meta_desc.get('content', ''))
        
        # Find main content area
        main_content = self._find_main_content(soup)
        
        # Remove unwanted elements
        for nav in main_content.find_all(['nav', 'header', 'footer']):
            nav.decompose()
        
        for element in main_content.find_all(class_=re.compile('nav|menu|footer|header|sidebar|widget')):
            element.decompose()
        
        # Process headings
        for heading_tag in self.included_tags['headings']:
            for heading in main_content.find_all(heading_tag):
                # Skip empty headings
                cleaned_text = self._clean_text(heading.text)
                if cleaned_text:
                    content["elements"].append({
                        "type": heading_tag,
                        "text": cleaned_text
                    })
        
        # Process paragraphs
        for para in main_content.find_all('p'):
            # Skip empty paragraphs
            cleaned_text = self._clean_text(para.text)
            if cleaned_text:
                content["elements"].append({
                    "type": "paragraph",
                    "text": cleaned_text
                })
        
        # Process lists
        for list_tag in main_content.find_all(['ul', 'ol']):
            # Skip navs and menus that might have survived earlier filtering
            skip_list = False
            for cls in list_tag.get('class', []):
                if 'nav' in cls or 'menu' in cls:
                    skip_list = True
                    break
            if skip_list:
                continue
                
            list_items = []
            for li in list_tag.find_all('li', recursive=False):
                cleaned_text = self._clean_text(li.text)
                if cleaned_text:
                    list_items.append(cleaned_text)
            
            if list_items:  # Only add if the list has items
                content["elements"].append({
                    "type": "list",
                    "list_type": "unordered" if list_tag.name == "ul" else "ordered",
                    "items": list_items
                })
        
        # Process blockquotes
        for quote in main_content.find_all('blockquote'):
            cleaned_text = self._clean_text(quote.text)
            if cleaned_text:
                content["elements"].append({
                    "type": "blockquote",
                    "text": cleaned_text
                })
        
        return content
    
    def crawl(self):
        """Crawl the website and extract content."""
        page_count = 0
        
        while self.queued_urls and page_count < self.max_pages:
            url, depth = self.queued_urls.popleft()
            
            # Skip if already visited or cannot fetch
            if url in self.visited_urls or not self._can_fetch(url):
                continue
            
            self.visited_urls.add(url)
            
            # Fetch URL content
            try:
                print(f"Crawling: {url} (depth: {depth})")
                response = requests.get(url, headers={"User-Agent": self.user_agent}, timeout=10)
                
                # Handle redirects
                if response.history:
                    final_url = self._normalize_url(response.url)
                    print(f"  Redirected to: {final_url}")
                    if final_url != url:
                        # If redirected to a new URL we haven't seen
                        if final_url not in self.visited_urls:
                            self.queued_urls.append((final_url, depth))
                        continue
                
                # Skip non-HTML content
                content_type = response.headers.get('content-type', '').lower()
                if 'text/html' not in content_type:
                    continue
                
                # Parse HTML content
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Extract and store text content
                page_content = self._extract_text_content(soup, url)
                
                # Only store if we extracted content
                if page_content["elements"]:
                    self.page_content[url] = page_content
                    print(f"  Extracted {len(page_content['elements'])} elements")
                else:
                    print(f"  No content extracted")
                
                # Extract links
                new_links = self._extract_links(soup, url, depth)
                self.queued_urls.extend(new_links)
                
                page_count += 1
                
                # Respect crawl delay
                time.sleep(self.delay)
                
            except requests.exceptions.RequestException as e:
                print(f"Request error crawling {url}: {e}")
            except Exception as e:
                print(f"Error crawling {url}: {e}")
        
        print(f"Crawling completed. Visited {len(self.visited_urls)} pages, extracted content from {len(self.page_content)} pages.")
        
        if not self.page_content:
            print("No content was extracted. Try adjusting the crawler settings or check if the website is accessible.")
            return
        
        # Save the results
        self._save_results()
    
    def _save_as_json(self):
        """Save the crawled results as JSON."""
        output_file = os.path.join(self.output_dir, f"{self.root_domain}_content.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(list(self.page_content.values()), f, indent=2, ensure_ascii=False)
        print(f"Content saved as JSON to {output_file}")
    
    def _save_as_text(self):
        """Save the crawled results as text."""
        output_file = os.path.join(self.output_dir, f"{self.root_domain}_content.txt")
        with open(output_file, 'w', encoding='utf-8') as f:
            for url, content in self.page_content.items():
                f.write(f"URL: {url}\n")
                f.write(f"TITLE: {content['title']}\n")
                f.write(f"TYPE: {content['page_type']}\n")
                if content['meta_description']:
                    f.write(f"DESCRIPTION: {content['meta_description']}\n")
                f.write("\n")
                
                for element in content['elements']:
                    if element['type'] in self.included_tags['headings']:
                        f.write(f"{element['type'].upper()}: {element['text']}\n\n")
                    elif element['type'] == 'paragraph':
                        f.write(f"{element['text']}\n\n")
                    elif element['type'] == 'list':
                        f.write(f"{element['list_type'].upper()} LIST:\n")
                        for item in element['items']:
                            f.write(f"  - {item}\n")
                        f.write("\n")
                    elif element['type'] == 'blockquote':
                        f.write(f"BLOCKQUOTE: {element['text']}\n\n")
                
                f.write("="*80 + "\n\n")
        print(f"Content saved as text to {output_file}")
    
    def _save_as_markdown(self):
        """Save the crawled results as markdown files."""
        # Group pages by type
        pages_by_type = {}
        for url, content in self.page_content.items():
            page_type = content["page_type"]
            if page_type not in pages_by_type:
                pages_by_type[page_type] = []
            pages_by_type[page_type].append((url, content))
        
        # Create a folder for each page type
        for page_type, pages in pages_by_type.items():
            type_dir = os.path.join(self.output_dir, page_type)
            os.makedirs(type_dir, exist_ok=True)
            
            # Save each page as a markdown file
            for url, content in pages:
                # Create a filename based on the URL path
                path = urllib.parse.urlparse(url).path
                if not path or path == '/':
                    filename = 'index.md'
                else:
                    # Convert path to filename
                    filename = path.strip('/').replace('/', '_') + '.md'
                
                output_file = os.path.join(type_dir, filename)
                
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(f"# {content['title']}\n\n")
                    
                    if content['meta_description']:
                        f.write(f"_{content['meta_description']}_\n\n")
                    
                    f.write(f"URL: {url}\n\n")
                    
                    for element in content['elements']:
                        if element['type'] in self.included_tags['headings']:
                            level = int(element['type'][1])  # Get the heading level (h1, h2, etc.)
                            # Adjust level to be under the title
                            level = min(level + 1, 6)
                            f.write(f"{'#' * level} {element['text']}\n\n")
                        elif element['type'] == 'paragraph':
                            f.write(f"{element['text']}\n\n")
                        elif element['type'] == 'list':
                            for item in element['items']:
                                if element['list_type'] == 'unordered':
                                    f.write(f"* {item}\n")
                                else:
                                    f.write(f"1. {item}\n")
                            f.write("\n")
                        elif element['type'] == 'blockquote':
                            f.write(f"> {element['text']}\n\n")
        
        # Create an index file
        index_file = os.path.join(self.output_dir, "index.md")
        with open(index_file, 'w', encoding='utf-8') as f:
            f.write(f"# {self.root_domain} Content\n\n")
            
            f.write("## Contents\n\n")
            # Write a section for each page type
            for page_type, pages in sorted(pages_by_type.items()):
                f.write(f"### {page_type.replace('_', ' ').title()}\n\n")
                for url, content in sorted(pages, key=lambda x: x[1]['title']):
                    path = f"{page_type}/{urllib.parse.urlparse(url).path.strip('/').replace('/', '_')}.md"
                    if path.endswith("/.md"):
                        path = f"{page_type}/index.md"
                    f.write(f"* [{content['title']}]({path})\n")
                f.write("\n")
        
        print(f"Content saved as markdown files to {self.output_dir}")
    
    def _save_results(self):
        """Save the crawled results to the specified output format."""
        if self.output_format == "json":
            self._save_as_json()
        elif self.output_format == "txt":
            self._save_as_text()
        elif self.output_format == "markdown":
            self._save_as_markdown()

def main():
    # Default settings
    default_output_format = "json"
    default_max_pages = 1000
    default_max_depth = 10
    default_delay = 1
    
    parser = argparse.ArgumentParser(description="Website copy scraper - Extract text content from websites")
    parser.add_argument("url", help="The root URL of the website to crawl")
    parser.add_argument("--output", "-o", default="output", help="Output directory")
    parser.add_argument("--format", "-f", choices=["json", "txt", "markdown"], default=default_output_format, help="Output format")
    parser.add_argument("--max-pages", "-m", type=int, default=default_max_pages, help="Maximum pages to crawl")
    parser.add_argument("--max-depth", "-d", type=int, default=default_max_depth, help="Maximum crawl depth from root URL")
    parser.add_argument("--delay", "-w", type=float, default=default_delay, help="Delay between requests in seconds")
    parser.add_argument("--ignore-robots", action="store_true", help="Ignore robots.txt")
    parser.add_argument("--respect-params", action="store_true", help="Treat URLs with different query parameters as different pages")
    parser.add_argument("--skip-sitemap", action="store_true", help="Skip checking sitemap.xml")
    
    args = parser.parse_args()
    
    # Create and run the crawler with all parameters from command line
    crawler = WebsiteCrawler(
        root_url=args.url,
        output_dir=args.output,
        respect_robots=not args.ignore_robots,
        max_depth=args.max_depth,
        max_pages=args.max_pages,
        delay=args.delay,
        ignore_query_params=not args.respect_params,
        check_sitemap=not args.skip_sitemap,
        output_format=args.format
    )
    
    crawler.crawl()

if __name__ == "__main__":
    main()