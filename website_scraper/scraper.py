import requests
from bs4 import BeautifulSoup
import os
import re
from urllib.parse import urlparse, urljoin, urldefrag
import time  # For rate limiting

def scrape_page(url):
    try:
        # Define headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # Make the request with browser headers
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract headings and paragraphs in the order they appear
        elements = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p'])
        
        # Format the content
        content = []
        
        # Process elements in order, filtering out nav and footer elements
        for element in elements:
            # Check if element is inside a nav or footer
            nav_parent = element.find_parent('nav')
            footer_parent = element.find_parent('footer')
            
            # Only include elements that are not inside nav or footer
            if not nav_parent and not footer_parent:
                element_text = element.get_text(strip=True)
                if element_text:  # Only add non-empty elements
                    if element.name.startswith('h'):  # It's a heading
                        content.append(f"# {element_text}")
                    else:  # It's a paragraph
                        content.append(element_text)
        
        # Join content with double newlines
        page_content = "\n\n".join(content)
        
        # Extract all links for further scraping
        page_links = extract_page_links(soup, url)
        
        return page_content, page_links
    except requests.exceptions.RequestException as e:
        print(f"Request error for {url}: {e}")
        return None, set()
    except Exception as e:
        print(f"An error occurred when scraping {url}: {e}")
        return None, set()

def normalize_url(url):
    # Parse the URL
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path = parsed.path
    
    # Handle trailing slashes and index pages
    if path == "" or path == "/":
        path = "/"
    elif path.endswith("index.html") or path.endswith("index.htm") or path.endswith("index.php"):
        path = path[:path.rfind("/")+1]
    
    # Reconstruct URL without query string or fragment
    return f"{parsed.scheme}://{netloc}{path}"

def extract_page_links(soup, base_url):
    """Extract all page links from anchor tags in the soup object.
    
    Args:
        soup: BeautifulSoup object
        base_url: Base URL for resolving relative links
        
    Returns:
        set: Set of normalized URLs from the same domain
    """
    # Find all anchor tags
    links = set()
    
    for a in soup.find_all('a', href=True):
        href = a['href']
        # Skip empty or javascript or mailto links
        if not href or href.startswith('javascript:') or href.startswith('mailto:'):
            continue
            
        # Convert relative URLs to absolute and remove fragments
        full_url = urljoin(base_url, href)
        full_url, _ = urldefrag(full_url)
        
        # Normalize URL to handle variations
        normalized_url = normalize_url(full_url)
        
        if is_same_domain(base_url, normalized_url):
            links.add(normalized_url)
    
    return links

def is_same_domain(base_url, url):
    # Parse both URLs
    base_domain = urlparse(base_url).netloc
    domain = urlparse(url).netloc
    
    # Remove www if present
    if base_domain.startswith('www.'):
        base_domain = base_domain[4:]
    if domain.startswith('www.'):
        domain = domain[4:]
    
    return domain == base_domain

def get_domain_for_directory(url):
    # Parse the domain from the URL
    domain = urlparse(url).netloc
    
    # Remove www subdomain if present
    if domain.startswith('www.'):
        domain = domain[4:]
    
    # Clean the domain (in case it contains characters that aren't valid for directories)
    domain = re.sub(r'[^\w\-\.]', '_', domain)
    
    return domain

def get_filename_from_url(url):
    # Normalize the URL first
    url = normalize_url(url)
    parsed = urlparse(url)
    path = parsed.path
    
    # If it's the homepage, return index.txt
    if path == "/":
        return "index.txt"
    
    # Remove leading slash and replace other slashes with hyphens
    path = path.strip("/").replace("/", "-")
    
    # Add .txt extension
    return f"{path}.txt"

def scrape_website_and_nav_pages(start_url, skip_links=False):
    """Scrape a website and optionally follow all links on the pages.
    
    Args:
        start_url: URL to start scraping from
        skip_links: If True, only scrape the start URL without following links
        
    Returns:
        tuple: (output_directory, number_of_pages_scraped)
    """
    # Create the output directory
    domain = get_domain_for_directory(start_url)
    base_dir = f"./{domain}"
    output_dir = base_dir
    
    # Check if directory exists, if so, append incrementing suffix
    suffix = 1
    while os.path.exists(output_dir):
        output_dir = f"{base_dir}-{suffix}"
        suffix += 1
    
    # Create the directory
    os.makedirs(output_dir)
    print(f"Created output directory: {output_dir}")
    
    # Normalize the start URL
    start_url = normalize_url(start_url)
    
    # Initialize tracking sets
    to_scrape = {start_url}
    scraped = set()
    seen_urls = {start_url}  # Track all URLs we've seen
    
    # Scrape pages
    while to_scrape:
        # Get a URL to scrape
        current_url = to_scrape.pop()
        
        # Skip if already scraped
        if current_url in scraped:
            continue
        
        print(f"Scraping: {current_url}")
        
        # Scrape the page
        content, links = scrape_page(current_url)
        
        if content:
            # Get the filename
            filename = get_filename_from_url(current_url)
            file_path = os.path.join(output_dir, filename)
            
            # Save to file
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(content)
            
            print(f"Saved content to: {file_path}")
            
            # Add to scraped set
            scraped.add(current_url)
            
            # Add new links to scrape (only if not skipping links)
            if not skip_links:
                for link in links:
                    # Only add unseen URLs
                    if link not in seen_urls:
                        seen_urls.add(link)
                        to_scrape.add(link)
            
            # Be polite - add a small delay
            time.sleep(1)
    
    return output_dir, len(scraped)

if __name__ == "__main__":
    website_url = input("Enter the URL of the website to scrape: ")
    output_dir, pages_scraped = scrape_website_and_nav_pages(website_url)
    
    print(f"\nScraping complete!")
    print(f"Scraped {pages_scraped} pages to directory: {output_dir}")
