#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
import time
import urllib.parse
from collections import deque
from urllib.robotparser import RobotFileParser

# Check for required libraries and give helpful error messages
try:
    import requests
except ImportError:
    print("Error: The 'requests' library is required. Please install it using:")
    print("python3 -m pip install requests")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Error: The 'beautifulsoup4' library is required. Please install it using:")
    print("python3 -m pip install beautifulsoup4")
    sys.exit(1)

# Check for optional lxml library (improves XML parsing)
try:
    import lxml
    has_lxml = True
except ImportError:
    has_lxml = False
    print("Note: The 'lxml' library is not installed. Sitemap parsing may be limited.")
    print("To install lxml: python3 -m pip install lxml")
    print("Continuing without lxml...")

# Check for optional selenium library (for JavaScript rendering)
selenium_available = False
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, WebDriverException
    selenium_available = True
except ImportError:
    pass  # We'll handle this gracefully if the user selects js_mode='selenium'

class WebsiteCrawler:
    def __init__(self, root_url, output_dir="output", respect_robots=True, max_depth=10, 
                 max_pages=1000, delay=1, ignore_query_params=True, check_sitemap=True, 
                 output_format="json", js_mode="headers", verbose=False, page_load_wait=3,
                 browser_timeout=30):
        # Store all configuration parameters first
        self.output_dir = output_dir
        self.respect_robots = respect_robots
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.delay = delay
        self.ignore_query_params = ignore_query_params
        self.check_sitemap = check_sitemap
        self.output_format = output_format
        self.js_mode = js_mode
        self.verbose = verbose
        self.page_load_wait = page_load_wait  # Seconds to wait for page to load in browser
        self.browser_timeout = browser_timeout  # Seconds to wait for browser operations
        
        # Browser-like headers for requests - DEFINE THIS BEFORE setup_browser
        self.user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
        
        # Set up browser options if needed
        self.browser = None
        if js_mode == "selenium":
            if not selenium_available:
                print("Error: Selenium is required for js_mode='selenium'. Install with:")
                print("python3 -m pip install selenium webdriver-manager")
                sys.exit(1)
            self._setup_browser()
        
        # Now normalize the URL (which uses self.ignore_query_params)
        self.root_url = self._normalize_url(root_url)
        self.root_domain = urllib.parse.urlparse(self.root_url).netloc
        
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
        
        # Check for sitemap (after the URL and robot parser are set up)
        if self.check_sitemap:
            self._check_sitemap()
    
    def __del__(self):
        """Clean up resources when the object is destroyed."""
        if hasattr(self, 'browser') and self.browser:
            try:
                self.browser.quit()
            except:
                pass
    
    def _setup_browser(self):
        """Set up a headless browser for JavaScript rendering."""
        if not selenium_available:
            return
            
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            chrome_options = Options()
            chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument(f"user-agent={self.user_agent}")
            
            # Create the Chrome WebDriver
            print("Setting up headless browser for JavaScript rendering...")
            service = Service(ChromeDriverManager().install())
            self.browser = webdriver.Chrome(service=service, options=chrome_options)
            self.browser.set_page_load_timeout(self.browser_timeout)
            print("Browser setup complete.")
        except Exception as e:
            print(f"Error setting up browser: {e}")
            print("Falling back to regular requests.")
            self.js_mode = "headers"
    
    def _is_binary_content(self, content):
        """Check if content appears to be binary rather than text."""
        # Check for common binary file signatures
        if isinstance(content, bytes):
            # Check for common binary file signatures (PDF, images, etc.)
            if (content.startswith(b'%PDF-') or content.startswith(b'\x89PNG\r\n') or 
                content.startswith(b'GIF8') or content.startswith(b'\xFF\xD8\xFF')):
                return True
                
            # Check if there's a high proportion of null bytes or binary data
            sample = content[:4000]  # Check a reasonable sample
            binary_chars = sum(1 for b in sample if b < 9 or (b > 13 and b < 32) or b > 126)
            return binary_chars > len(sample) * 0.1  # More than 10% binary is suspicious
        return False
    
    def _detect_encoding(self, response):
        """Detect and set the appropriate character encoding for HTTP response."""
        # First try content-type header
        content_type = response.headers.get('content-type', '').lower()
        charset = None
        
        if 'charset=' in content_type:
            charset_match = re.search(r'charset=([^\s;]+)', content_type)
            if charset_match:
                charset = charset_match.group(1)
                if self.verbose:
                    print(f"  Found charset in HTTP header: {charset}")
        
        # If no charset in header, try apparent encoding
        if not charset:
            charset = response.apparent_encoding
            if charset:
                if self.verbose:
                    print(f"  Using detected encoding: {charset}")
            else:
                # Default to UTF-8 as a last resort
                charset = 'utf-8'
                if self.verbose:
                    print(f"  No encoding detected, defaulting to UTF-8")
        
        # Set the response encoding
        response.encoding = charset
        return charset
    
    def _save_debug_content(self, url, raw_content, decoded_content):
        """Save raw and decoded content for debugging encoding issues."""
        debug_dir = os.path.join(self.output_dir, "debug_encoding")
        os.makedirs(debug_dir, exist_ok=True)
        
        # Create a filename based on the URL
        page_filename = urllib.parse.urlparse(url).path
        if not page_filename or page_filename == '/':
            page_filename = 'index'
        else:
            page_filename = page_filename.strip('/').replace('/', '_')
        
        # Save the raw binary content
        raw_filename = os.path.join(debug_dir, f"{self.root_domain}_{page_filename}_raw.bin")
        with open(raw_filename, 'wb') as f:
            f.write(raw_content)
        
        # Save the decoded text content
        decoded_filename = os.path.join(debug_dir, f"{self.root_domain}_{page_filename}_decoded.txt")
        with open(decoded_filename, 'w', encoding='utf-8', errors='replace') as f:
            f.write(decoded_content)
        
        if self.verbose:
            print(f"  Saved debug content to {debug_dir}")
            
    def _fetch_with_browser(self, url):
        """Fetch a URL using the headless browser with JavaScript rendering."""
        if not self.browser:
            return None
            
        try:
            if self.verbose:
                print(f"  Fetching with browser: {url}")
                
            self.browser.get(url)
            
            # Wait for page to load
            time.sleep(self.page_load_wait)
            
            # Get the page source after JavaScript execution
            html = self.browser.page_source
            
            if not html:
                return None
                
            # Check if the page source appears to be properly encoded text
            if isinstance(html, bytes) and self._is_binary_content(html):
                print(f"  Error: Browser returned binary content")
                return None
                
            if self.verbose:
                print(f"  Page fetched successfully with browser, HTML size: {len(html)} bytes")
                
            return html
        except Exception as e:
            print(f"Error fetching with browser: {e}")
            return None
            
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
            print(f"Checking for sitemap at {sitemap_url}")
            response = requests.get(sitemap_url, headers={"User-Agent": self.user_agent}, timeout=10)
            
            if response.status_code == 200:
                print(f"Found sitemap at {sitemap_url}")
                
                # Try to parse sitemap - use lxml if available, otherwise use html.parser
                if 'has_lxml' in globals() and has_lxml:
                    soup = BeautifulSoup(response.text, 'xml')
                else:
                    soup = BeautifulSoup(response.text, 'html.parser')
                
                # Try different methods of finding URLs in the sitemap
                urls = soup.find_all('loc')
                
                # If no URLs found with 'loc' tag, try looking for URLs in the text
                if not urls:
                    # Simple regex to find URLs in the sitemap
                    url_pattern = re.compile(r'https?://[^\s<>"\']+')
                    found_urls = url_pattern.findall(response.text)
                    
                    # Convert found URLs to a format similar to soup.find_all
                    class UrlObject:
                        def __init__(self, url):
                            self.text = url
                    
                    urls = [UrlObject(url) for url in found_urls]
                
                if not urls:
                    print("No URLs found in sitemap.")
                    return
                
                print(f"Found {len(urls)} URLs in sitemap")
                for url in urls:
                    url_text = url.text
                    if self._is_internal_url(url_text) and url_text not in self.visited_urls:
                        normalized_url = self._normalize_url(url_text)
                        self.queued_urls.append((normalized_url, 0))  # Add as depth 0
                        print(f"Added from sitemap: {normalized_url}")
            else:
                print(f"No sitemap found at {sitemap_url} (status code: {response.status_code})")
                
                # Try sitemap_index.xml as fallback
                sitemap_index_url = urllib.parse.urljoin(self.root_url, "/sitemap_index.xml")
                print(f"Checking for sitemap index at {sitemap_index_url}")
                try:
                    response = requests.get(sitemap_index_url, headers={"User-Agent": self.user_agent}, timeout=10)
                    if response.status_code == 200:
                        print(f"Found sitemap index at {sitemap_index_url}")
                        # Processing sitemap index is more complex and would require additional code
                        print("Sitemap index found but not processed. Consider adding the main sitemap URL directly.")
                except Exception:
                    pass
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
    
    def _extract_links(self, soup, page_url, current_depth, page_count=0):
        """Extract internal links from a BeautifulSoup object."""
        links = []
        found_urls = set()
        
        if current_depth >= self.max_depth:
            if self.verbose:
                print(f"  Reached max depth {self.max_depth}, not extracting more links")
            return links
        
        # Debug - save HTML for inspection if verbose
        if self.verbose:
            debug_dir = os.path.join(self.output_dir, "debug")
            os.makedirs(debug_dir, exist_ok=True)
            page_filename = urllib.parse.urlparse(page_url).path
            if not page_filename or page_filename == '/':
                page_filename = 'index'
            else:
                page_filename = page_filename.strip('/').replace('/', '_')
            
            filename = os.path.join(debug_dir, f"{self.root_domain}_{page_filename}.html")
            with open(filename, 'w', encoding='utf-8', errors='replace') as f:
                f.write(str(soup))
            print(f"  Saved HTML to {filename} for debugging")
        
        # Standard link extraction - find all <a> tags with href attributes
        anchors = soup.find_all('a', href=True)
        if self.verbose:
            print(f"  Found {len(anchors)} anchor tags with href attributes")
        
        for anchor in anchors:
            href = anchor['href']
            
            # Skip empty, javascript, and anchor links
            if not href or href.startswith('javascript:') or href.startswith('#'):
                continue
            
            # Resolve relative URLs
            absolute_url = urllib.parse.urljoin(page_url, href)
            normalized_url = self._normalize_url(absolute_url)
            found_urls.add(normalized_url)
            
            # Add to links if internal and not already visited or queued
            if (self._is_internal_url(normalized_url) and 
                normalized_url not in self.visited_urls and 
                normalized_url not in [u for u, _ in self.queued_urls]):
                links.append((normalized_url, current_depth + 1))
                if self.verbose:
                    print(f"  Found link: {normalized_url}")
        
        # Wix-specific extraction - look for links in data-testid="linkElement" attributes
        link_elements = soup.find_all(attrs={"data-testid": "linkElement"})
        if self.verbose:
            print(f"  Found {len(link_elements)} elements with data-testid=linkElement")
            
        for link_element in link_elements:
            href = None
            # Check if this element has an href attribute
            if link_element.has_attr('href'):
                href = link_element['href']
            else:
                # Look for nested <a> tags
                nested_a = link_element.find('a', href=True)
                if nested_a:
                    href = nested_a['href']
            
            if not href or href.startswith('javascript:') or href.startswith('#'):
                continue
                
            absolute_url = urllib.parse.urljoin(page_url, href)
            normalized_url = self._normalize_url(absolute_url)
            
            if normalized_url in found_urls:
                continue
                
            found_urls.add(normalized_url)
            
            if (self._is_internal_url(normalized_url) and 
                normalized_url not in self.visited_urls and 
                normalized_url not in [u for u, _ in self.queued_urls]):
                links.append((normalized_url, current_depth + 1))
                if self.verbose:
                    print(f"  Found Wix link: {normalized_url}")
        
        # Look for common URL patterns in the HTML text
        if len(links) < 5:  # If we found few links, try to find more
            # Find anything that looks like a URL to the same domain
            domain_pattern = re.escape(self.root_domain)
            url_pattern = re.compile(f'https?://(www\\.)?{domain_pattern}/[a-zA-Z0-9_-]+/?')
            text_urls = url_pattern.findall(str(soup))
            
            if self.verbose:
                print(f"  Found {len(text_urls)} URLs in HTML text matching domain pattern")
            
            for url in text_urls:
                normalized_url = self._normalize_url(url)
                
                if normalized_url in found_urls:
                    continue
                    
                found_urls.add(normalized_url)
                
                if (self._is_internal_url(normalized_url) and 
                    normalized_url not in self.visited_urls and 
                    normalized_url not in [u for u, _ in self.queued_urls]):
                    links.append((normalized_url, current_depth + 1))
                    if self.verbose:
                        print(f"  Found URL pattern: {normalized_url}")
        
        # Additional Wix-specific URL guessing
        if len(links) < 5:
            # Common Wix pages to try
            common_paths = ["about-us", "contact", "services", "blog", "gallery", "faq", 
                           "team", "products", "portfolio", "testimonials", "pricing"]
            
            if self.verbose:
                print(f"  Few links found, trying common Wix paths")
                
            for path in common_paths:
                guess_url = urllib.parse.urljoin(self.root_url, path)
                normalized_url = self._normalize_url(guess_url)
                
                if normalized_url in found_urls:
                    continue
                    
                found_urls.add(normalized_url)
                
                if (self._is_internal_url(normalized_url) and 
                    normalized_url not in self.visited_urls and 
                    normalized_url not in [u for u, _ in self.queued_urls]):
                    links.append((normalized_url, current_depth + 1))
                    if self.verbose:
                        print(f"  Adding common Wix path: {normalized_url}")
        
        if self.verbose:
            print(f"  Total links found: {len(links)}")
            
        return links
    
    def _validate_text(self, text):
        """Ensure text is valid Unicode and clean it."""
        if text is None:
            return ""
        
        # Convert to string if somehow not already
        if not isinstance(text, str):
            try:
                text = str(text)
            except Exception:
                return "[Undecodable content]"
        
        # Remove or replace problematic characters
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
        
        # Apply normal text cleanup
        return self._clean_text(text)
    
    def _clean_text(self, text):
        """Clean up text by applying cleanup patterns."""
        if not text:
            return ""
            
        # Handle potential non-string input
        if not isinstance(text, str):
            try:
                text = str(text)
            except Exception:
                return ""
                
        # Apply regular cleanup patterns
        cleaned = text
        for pattern, repl in self.cleanup_patterns:
            try:
                cleaned = pattern.sub(repl, cleaned)
            except Exception:
                # If regex fails, just return the original
                pass
        
        # Additional sanity checks
        # Remove control characters
        cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', cleaned)
        
        # Replace very long strings of the same character (likely garbage)
        cleaned = re.sub(r'(.)\1{30,}', r'\1\1\1...', cleaned)
        
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
            "title": self._validate_text(soup.title.text if soup.title else "No Title"),
            "page_type": page_type,
            "meta_description": "",
            "elements": []
        }
        
        # Extract meta description
        meta_desc = soup.find('meta', attrs={"name": "description"})
        if meta_desc:
            content["meta_description"] = self._validate_text(meta_desc.get('content', ''))
        
        # Find main content area - Wix specific selectors
        main_content = None
        
        # Try Wix-specific selectors first
        wix_content_selectors = [
            "[data-testid='richTextElement']",  # Wix rich text elements
            ".wixui-rich-text",                 # Wix UI rich text
            "[data-mesh-id]",                   # Wix mesh containers
            ".font_0, .font_1, .font_2, .font_3, .font_4, .font_5, .font_6, .font_7, .font_8, .font_9, .font_10"  # Wix font classes
        ]
        
        # Try to find Wix-specific content first
        wix_elements = []
        for selector in wix_content_selectors:
            elements = soup.select(selector)
            if elements:
                wix_elements.extend(elements)
                if self.verbose:
                    print(f"  Found {len(elements)} elements with selector: {selector}")
        
        # If we found Wix elements, extract content from them
        if wix_elements:
            for element in wix_elements:
                # Try to determine element type based on class or other attributes
                element_type = "paragraph"  # default
                
                # Check for heading classes or tags
                if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                    element_type = element.name
                elif element.has_attr('class'):
                    classes = ' '.join(element.get('class', []))
                    if 'font_0' in classes or 'font_1' in classes or 'font_2' in classes:
                        element_type = 'h1'
                    elif 'font_3' in classes or 'font_4' in classes:
                        element_type = 'h2'
                    elif 'font_5' in classes or 'font_6' in classes:
                        element_type = 'h3'
                
                # Clean the text
                cleaned_text = self._validate_text(element.text)
                if cleaned_text:
                    content["elements"].append({
                        "type": element_type,
                        "text": cleaned_text
                    })
            
            # If we found content from Wix elements, return it
            if content["elements"]:
                return content
        
        # If no Wix-specific content was found or extracted, try the generic approach
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
                cleaned_text = self._validate_text(heading.text)
                if cleaned_text:
                    content["elements"].append({
                        "type": heading_tag,
                        "text": cleaned_text
                    })
        
        # Process paragraphs
        for para in main_content.find_all('p'):
            # Skip empty paragraphs
            cleaned_text = self._validate_text(para.text)
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
                cleaned_text = self._validate_text(li.text)
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
            cleaned_text = self._validate_text(quote.text)
            if cleaned_text:
                content["elements"].append({
                    "type": "blockquote",
                    "text": cleaned_text
                })
        
        # If we didn't find any elements, try a more aggressive approach for Wix sites
        if not content["elements"]:
            if self.verbose:
                print("  No content found with standard selectors, trying more aggressive extraction")
            
            # Extract all text that looks like content (paragraphs and headings based on text characteristics)
            text_elements = []
            
            # Get all elements with text
            for element in main_content.find_all(text=True):
                if element.parent.name not in ['script', 'style', 'meta', 'link']:
                    text = self._validate_text(element)
                    if text and len(text) > 20:  # Only consider substantial text
                        # Try to determine if it's a heading or paragraph
                        parent = element.parent
                        if parent.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                            element_type = parent.name
                        elif parent.has_attr('class') and any('font_' in cls for cls in parent.get('class', [])):
                            element_type = 'h2'  # Assume it's a heading from Wix
                        else:
                            element_type = 'paragraph'
                        
                        text_elements.append({
                            "type": element_type,
                            "text": text
                        })
            
            # Add unique elements to content
            seen_texts = set()
            for element in text_elements:
                if element["text"] not in seen_texts:
                    content["elements"].append(element)
                    seen_texts.add(element["text"])
        
        if self.verbose:
            print(f"  Extracted {len(content['elements'])} content elements")
        
        return content
    
    def crawl(self):
        """Crawl the website and extract content."""
        page_count = 0
        
        # Print initialization info
        print(f"Starting crawl of {self.root_url}")
        print(f"JavaScript mode: {self.js_mode}")
        print(f"Output format: {self.output_format}")
        print(f"Max pages: {self.max_pages}, Max depth: {self.max_depth}")
        
        while self.queued_urls and page_count < self.max_pages:
            url, depth = self.queued_urls.popleft()
            
            # Skip if already visited or cannot fetch
            if url in self.visited_urls or not self._can_fetch(url):
                continue
            
            self.visited_urls.add(url)
            
            # Fetch URL content
            try:
                print(f"Crawling: {url} (depth: {depth})")
                html_content = None
                raw_content = None
                final_url = url
                
                # Decide how to fetch the page based on the js_mode
                if self.js_mode == "selenium":
                    html_content = self._fetch_with_browser(url)
                    if html_content:
                        final_url = self.browser.current_url
                        if final_url != url:
                            final_url = self._normalize_url(final_url)
                            print(f"  Browser redirected to: {final_url}")
                    else:
                        print(f"  Browser fetch failed, falling back to request")
                
                # If we don't have content yet, use regular requests
                if not html_content:
                    if self.verbose:
                        print(f"  Fetching with requests: {url}")
                    
                    response = requests.get(url, headers=self.headers, timeout=15)
                    raw_content = response.content  # Store raw binary content
                    
                    # Handle redirects
                    if response.history:
                        final_url = self._normalize_url(response.url)
                        print(f"  Redirected to: {final_url}")
                    
                    # Check content type
                    content_type = response.headers.get('content-type', '').lower()
                    if 'text/html' not in content_type:
                        print(f"  Skipping non-HTML content type: {content_type}")
                        continue
                    
                    # Check for binary content
                    if self._is_binary_content(raw_content):
                        print(f"  Skipping binary content detected as HTML")
                        if self.verbose:
                            print(f"  Content appears to be binary but was served as HTML")
                            self._save_debug_content(url, raw_content, "BINARY CONTENT")
                        continue
                    
                    # Detect and set encoding
                    self._detect_encoding(response)
                    
                    if self.verbose:
                        print(f"  Using encoding: {response.encoding}")
                    
                    # Get the decoded content
                    html_content = response.text
                    
                    # Save debug info if verbose
                    if self.verbose:
                        self._save_debug_content(url, raw_content, html_content)
                
                # If final URL is different, handle it
                if final_url != url:
                    if final_url not in self.visited_urls:
                        self.queued_urls.append((final_url, depth))
                    continue
                
                # Parse HTML content
                if self.verbose:
                    print(f"  Parsing HTML content: {len(html_content)} bytes")
                
                try:
                    # First try with default parser
                    soup = BeautifulSoup(html_content, 'html.parser')
                except Exception as e:
                    print(f"  Error parsing HTML with html.parser: {e}")
                    
                    # Try alternative parsers if available
                    try:
                        if 'has_lxml' in globals() and has_lxml:
                            soup = BeautifulSoup(html_content, 'lxml')
                        else:
                            # Try with explicitly declared encoding
                            soup = BeautifulSoup(html_content, 'html.parser', from_encoding='utf-8')
                    except Exception as e2:
                        print(f"  Failed to parse HTML with alternative parsers: {e2}")
                        continue
                
                # Extract and store text content
                page_content = self._extract_text_content(soup, url)
                
                # Only store if we extracted content
                if page_content["elements"]:
                    self.page_content[url] = page_content
                    print(f"  Extracted {len(page_content['elements'])} elements")
                else:
                    print(f"  No content extracted")
                
                # Extract links
                new_links = self._extract_links(soup, url, depth, page_count)
                
                # Before adding new links, print them if verbose
                if new_links and self.verbose:
                    print("  New links to be added to queue:")
                    for new_url, new_depth in new_links:
                        print(f"    {new_url} (depth: {new_depth})")
                
                self.queued_urls.extend(new_links)
                
                # If we didn't find any links and this is the root page, try common Wix paths
                if not new_links and url == self.root_url:
                    print("  WARNING: No links found on the homepage, trying common Wix paths...")
                    for path in ["about", "about-us", "contact", "services", "products", "blog"]:
                        guess_url = urllib.parse.urljoin(self.root_url, path)
                        normalized_url = self._normalize_url(guess_url)
                        
                        if (normalized_url not in self.visited_urls and 
                            normalized_url not in [u for u, _ in self.queued_urls]):
                            self.queued_urls.append((normalized_url, 1))
                            print(f"  Added common path: {normalized_url}")
                
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
        try:
            with open(output_file, 'w', encoding='utf-8', errors='replace') as f:
                json.dump(list(self.page_content.values()), f, indent=2, ensure_ascii=False)
            print(f"Content saved as JSON to {output_file}")
        except Exception as e:
            print(f"Error saving JSON output: {e}")
            # Try a more forgiving approach
            try:
                with open(output_file, 'w', encoding='utf-8', errors='replace') as f:
                    # Convert any problematic elements to strings
                    safe_data = []
                    for page in self.page_content.values():
                        safe_page = {
                            "url": page["url"],
                            "title": self._validate_text(page["title"]),
                            "page_type": page["page_type"],
                            "meta_description": self._validate_text(page["meta_description"]),
                            "elements": []
                        }
                        
                        for element in page["elements"]:
                            safe_element = element.copy()
                            if "text" in safe_element:
                                safe_element["text"] = self._validate_text(safe_element["text"])
                            if "items" in safe_element:
                                safe_element["items"] = [self._validate_text(item) for item in safe_element["items"]]
                            safe_page["elements"].append(safe_element)
                        
                        safe_data.append(safe_page)
                        
                    json.dump(safe_data, f, indent=2, ensure_ascii=False)
                print(f"Content saved as sanitized JSON to {output_file}")
            except Exception as e2:
                print(f"Critical error saving JSON: {e2}")
    
    def _save_as_text(self):
        """Save the crawled results as text."""
        output_file = os.path.join(self.output_dir, f"{self.root_domain}_content.txt")
        try:
            with open(output_file, 'w', encoding='utf-8', errors='replace') as f:
                # First, write an index of pages at the top
                f.write(f"# {self.root_domain} Website Content\n\n")
                f.write("## Table of Contents\n\n")
                
                # Group pages by type
                pages_by_type = {}
                for url, content in self.page_content.items():
                    page_type = content["page_type"]
                    if page_type not in pages_by_type:
                        pages_by_type[page_type] = []
                    pages_by_type[page_type].append((url, content))
                
                # Write the table of contents
                for page_type, pages in sorted(pages_by_type.items()):
                    f.write(f"* {page_type.replace('_', ' ').title()}\n")
                    for url, content in sorted(pages, key=lambda x: x[1]['title']):
                        f.write(f"  - {self._validate_text(content['title'])}\n")
                
                f.write("\n" + "="*80 + "\n\n")
                
                # Now write each page's content in a more human-readable format
                for url, content in self.page_content.items():
                    # Write page header
                    f.write(f"# {self._validate_text(content['title'])}\n\n")
                    
                    # URL and metadata in a more subtle format
                    f.write(f"URL: {url}\n")
                    f.write(f"Type: {content['page_type'].replace('_', ' ').title()}\n")
                    if content['meta_description']:
                        f.write(f"Description: {self._validate_text(content['meta_description'])}\n")
                    f.write("\n")
                    
                    # Process elements to group related content
                    current_heading = None
                    current_heading_level = 0
                    
                    for element in content['elements']:
                        if element['type'] in self.included_tags['headings']:
                            # Get the heading level (h1, h2, etc.)
                            level = int(element['type'][1])
                            # Format heading with the right number of #
                            prefix = "#" * (level + 1)  # +1 because we used # for page title
                            f.write(f"{prefix} {self._validate_text(element['text'])}\n\n")
                            current_heading = element['text']
                            current_heading_level = level
                        elif element['type'] == 'paragraph':
                            f.write(f"{self._validate_text(element['text'])}\n\n")
                        elif element['type'] == 'list':
                            for idx, item in enumerate(element['items']):
                                if element['list_type'] == 'unordered':
                                    f.write(f"* {self._validate_text(item)}\n")
                                else:
                                    f.write(f"{idx+1}. {self._validate_text(item)}\n")
                            f.write("\n")
                        elif element['type'] == 'blockquote':
                            # Format blockquotes with indentation
                            lines = self._validate_text(element['text']).split('\n')
                            for line in lines:
                                f.write(f"> {line}\n")
                            f.write("\n")
                    
                    f.write("\n" + "="*80 + "\n\n")
            
            print(f"Content saved as text to {output_file}")
        except Exception as e:
            print(f"Error saving text content: {e}")
    
    def _save_as_markdown(self):
        """Save the crawled results as markdown files."""
        try:
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
                    
                    with open(output_file, 'w', encoding='utf-8', errors='replace') as f:
                        f.write(f"# {self._validate_text(content['title'])}\n\n")
                        
                        if content['meta_description']:
                            f.write(f"_{self._validate_text(content['meta_description'])}_\n\n")
                        
                        f.write(f"URL: {url}\n\n")
                        
                        for element in content['elements']:
                            if element['type'] in self.included_tags['headings']:
                                level = int(element['type'][1])  # Get the heading level (h1, h2, etc.)
                                # Adjust level to be under the title
                                level = min(level + 1, 6)
                                f.write(f"{'#' * level} {self._validate_text(element['text'])}\n\n")
                            elif element['type'] == 'paragraph':
                                f.write(f"{self._validate_text(element['text'])}\n\n")
                            elif element['type'] == 'list':
                                for item in element['items']:
                                    if element['list_type'] == 'unordered':
                                        f.write(f"* {self._validate_text(item)}\n")
                                    else:
                                        f.write(f"1. {self._validate_text(item)}\n")
                                f.write("\n")
                            elif element['type'] == 'blockquote':
                                f.write(f"> {self._validate_text(element['text'])}\n\n")
            
            # Create an index file
            index_file = os.path.join(self.output_dir, "index.md")
            with open(index_file, 'w', encoding='utf-8', errors='replace') as f:
                f.write(f"# {self.root_domain} Content\n\n")
                
                f.write("## Contents\n\n")
                # Write a section for each page type
                for page_type, pages in sorted(pages_by_type.items()):
                    f.write(f"### {page_type.replace('_', ' ').title()}\n\n")
                    for url, content in sorted(pages, key=lambda x: x[1]['title']):
                        path = f"{page_type}/{urllib.parse.urlparse(url).path.strip('/').replace('/', '_')}.md"
                        if path.endswith("/.md"):
                            path = f"{page_type}/index.md"
                        f.write(f"* [{self._validate_text(content['title'])}]({path})\n")
                    f.write("\n")
            
            print(f"Content saved as markdown files to {self.output_dir}")
        except Exception as e:
            print(f"Error saving markdown content: {e}")
    
    def _save_as_readable(self):
        """Save the crawled results as a clean, human-readable document."""
        output_file = os.path.join(self.output_dir, f"{self.root_domain}_content_readable.txt")
        try:
            with open(output_file, 'w', encoding='utf-8', errors='replace') as f:
                # First, create a header with minimal metadata
                f.write(f"{self.root_domain} Website Content\n")
                f.write("="*len(f"{self.root_domain} Website Content") + "\n\n")
                f.write(f"Generated on {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                # Group pages by type for better organization
                pages_by_type = {}
                for url, content in self.page_content.items():
                    page_type = content["page_type"]
                    if page_type not in pages_by_type:
                        pages_by_type[page_type] = []
                    pages_by_type[page_type].append((url, content))
                    
                # Process each page type
                for page_type, pages in sorted(pages_by_type.items()):
                    section_title = page_type.replace('_', ' ').title()
                    f.write(f"\n\n{section_title}\n")
                    f.write("-"*len(section_title) + "\n\n")
                    
                    # Process each page
                    for url, content in sorted(pages, key=lambda x: x[1]['title']):
                        # Write title with encoding validation
                        title = self._validate_text(content['title'])
                        f.write(f"{title}\n")
                        f.write("."*len(title) + "\n\n")
                        
                        # Add the description if available
                        if content['meta_description']:
                            f.write(f"{self._validate_text(content['meta_description'])}\n\n")
                        
                        # Process elements in a more natural flow
                        current_section = None
                        
                        for element in content['elements']:
                            if element['type'] in self.included_tags['headings']:
                                heading_text = self._validate_text(element['text'])
                                level = int(element['type'][1])
                                
                                if level <= 2:  # Major heading
                                    f.write(f"\n{heading_text}\n")
                                    f.write("-"*len(heading_text) + "\n")
                                else:  # Minor heading
                                    f.write(f"\n{heading_text}\n")
                                    
                                current_section = heading_text
                            
                            elif element['type'] == 'paragraph':
                                para_text = self._validate_text(element['text'])
                                f.write(f"{para_text}\n\n")
                            
                            elif element['type'] == 'list':
                                f.write("\n")
                                for idx, item in enumerate(element['items']):
                                    item_text = self._validate_text(item)
                                    if element['list_type'] == 'unordered':
                                        f.write(f"• {item_text}\n")  # Using a bullet character
                                    else:
                                        f.write(f"{idx+1}. {item_text}\n")
                                f.write("\n")
                            
                            elif element['type'] == 'blockquote':
                                quote_text = self._validate_text(element['text'])
                                f.write("\n    ")  # Indent with 4 spaces
                                # Replace newlines with newline + 4 spaces
                                quote_text = quote_text.replace("\n", "\n    ")
                                f.write(f"{quote_text}\n\n")
                        
                        f.write("\n" + "-"*80 + "\n\n")
            
            print(f"Human-readable content saved to {output_file}")
        except Exception as e:
            print(f"Error saving readable content: {e}")
            # Try with a more forgiving approach
            try:
                with open(output_file, 'w', encoding='utf-8', errors='replace') as f:
                    f.write(f"{self.root_domain} Website Content\n")
                    f.write("="*len(f"{self.root_domain} Website Content") + "\n\n")
                    f.write(f"Generated on {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                    f.write("An error occurred while formatting the content.\n")
                    f.write("Basic content dump follows:\n\n")
                    
                    for url, content in self.page_content.items():
                        f.write(f"\nURL: {url}\n")
                        f.write(f"Title: {self._validate_text(content['title'])}\n")
                        f.write("-"*80 + "\n")
                        
                        for element in content['elements']:
                            if 'text' in element:
                                f.write(self._validate_text(element['text']) + "\n\n")
                            elif 'items' in element:
                                for item in element['items']:
                                    f.write(self._validate_text(item) + "\n")
                
                print(f"Simplified content saved to {output_file} due to formatting error")
            except Exception as e2:
                print(f"Critical error saving content: {e2}")
                    
    def _save_results(self):
        """Save the crawled results to the specified output format."""
        if self.output_format == "json":
            self._save_as_json()
        elif self.output_format == "txt":
            self._save_as_text()
        elif self.output_format == "markdown":
            self._save_as_markdown()
        elif self.output_format == "readable":
            self._save_as_readable()

def main():
    # Default settings
    default_output_format = "readable"  # Changed the default to readable
    default_max_pages = 1000
    default_max_depth = 10
    default_delay = 1
    default_js_mode = "headers"
    default_page_load_wait = 3
    
    parser = argparse.ArgumentParser(
        description="Website Copy Scraper - Extract text content from websites for reuse",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter  # Show default values in help
    )
    
    # Required arguments
    parser.add_argument("url", help="The root URL of the website to crawl (e.g., example.com)")
    
    # Output options
    output_group = parser.add_argument_group('Output Options')
    output_group.add_argument("--output", "-o", default="output", 
                               help="Output directory for extracted content")
    output_group.add_argument("--format", "-f", choices=["json", "txt", "markdown", "readable"], 
                               default=default_output_format, 
                               help="Format to save the content in")
    
    # Crawling options
    crawl_group = parser.add_argument_group('Crawling Options')
    crawl_group.add_argument("--max-pages", "-m", type=int, default=default_max_pages, 
                              help="Maximum number of pages to crawl")
    crawl_group.add_argument("--max-depth", "-d", type=int, default=default_max_depth, 
                              help="Maximum link depth from the root URL")
    crawl_group.add_argument("--delay", "-w", type=float, default=default_delay, 
                              help="Delay between requests in seconds (be gentle to servers)")
    
    # JavaScript handling
    js_group = parser.add_argument_group('JavaScript Options')
    js_group.add_argument("--js-mode", choices=["none", "headers", "selenium"], default=default_js_mode,
                          help="How to handle JavaScript-heavy sites: none=basic requests, "
                               "headers=browser-like headers, selenium=full browser rendering")
    js_group.add_argument("--page-load-wait", type=int, default=default_page_load_wait,
                          help="Seconds to wait for page to load when using selenium mode")
    
    # Debugging
    debug_group = parser.add_argument_group('Debugging Options')
    debug_group.add_argument("--verbose", "-v", action="store_true",
                            help="Enable verbose output for debugging")
    
    # Behavior flags
    behavior_group = parser.add_argument_group('Behavior Flags')
    behavior_group.add_argument("--ignore-robots", action="store_true", 
                                 help="Ignore robots.txt restrictions")
    behavior_group.add_argument("--respect-params", action="store_true", 
                                 help="Treat URLs with different query parameters as different pages")
    behavior_group.add_argument("--skip-sitemap", action="store_true", 
                                 help="Skip checking sitemap.xml")
    
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
        output_format=args.format,
        js_mode=args.js_mode,
        verbose=args.verbose,
        page_load_wait=args.page_load_wait
    )
    
    try:
        crawler.crawl()
        if crawler.browser:
            crawler.browser.quit()
            print("Browser closed successfully.")
    except KeyboardInterrupt:
        print("\nCrawling interrupted by user.")
        if crawler and crawler.browser:
            crawler.browser.quit()
            print("Browser closed successfully.")
    except Exception as e:
        print(f"Error during crawling: {e}")
        if crawler and crawler.browser:
            crawler.browser.quit()
            print("Browser closed successfully.")

if __name__ == "__main__":
    main()