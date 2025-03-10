import requests
from bs4 import BeautifulSoup
import os
import re
from urllib.parse import urlparse, urljoin, urldefrag
import time  # For rate limiting

def scrape_page(url):
    try:
        response = requests.get(url)
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
        
        # Extract nav links for further scraping
        nav_links = extract_nav_links(soup, url)
        
        return page_content, nav_links
    except requests.exceptions.RequestException as e:
        print(f"Request error for {url}: {e}")
        return None, set()
    except Exception as e:
        print(f"An error occurred when scraping {url}: {e}")
        return None, set()

def extract_nav_links(soup, base_url):
    # Find all nav elements
    nav_elements = soup.find_all('nav')
    
    links = set()
    
    # Extract links from each nav element
    for nav in nav_elements:
        a_tags = nav.find_all('a', href=True)
        for a in a_tags:
            href = a['href']
            # Convert relative URLs to absolute
            full_url = urljoin(base_url, href)
            # Remove fragments
            full_url, _ = urldefrag(full_url)
            links.add(full_url)
    
    # Filter to only include same-domain links
    same_domain_links = {url for url in links if is_same_domain(base_url, url)}
    
    return same_domain_links

def is_same_domain(base_url, url):
    # Parse both URLs
    base_parsed = urlparse(base_url)
    parsed = urlparse(url)
    
    # Get domains (removing www if present)
    base_domain = base_parsed.netloc
    if base_domain.startswith('www.'):
        base_domain = base_domain[4:]
    
    domain = parsed.netloc
    if domain.startswith('www.'):
        domain = domain[4:]
    
    # Check if domains match
    return domain == base_domain

def get_domain_for_directory(url):
    # Parse the domain from the URL
    parsed_url = urlparse(url)
    domain = parsed_url.netloc
    
    # Remove www subdomain if present
    if domain.startswith('www.'):
        domain = domain[4:]
    
    # Clean the domain (in case it contains characters that aren't valid for directories)
    domain = re.sub(r'[^\w\-\.]', '_', domain)
    
    return domain

def get_filename_from_url(url):
    # Parse the URL
    parsed_url = urlparse(url)
    
    # If it's the homepage, return index.txt
    if parsed_url.path == '/' or parsed_url.path == '':
        return 'index.txt'
    
    # Remove leading and trailing slashes
    path = parsed_url.path.strip('/')
    
    # Replace remaining slashes with hyphens
    path = path.replace('/', '-')
    
    # Add .txt extension
    return f"{path}.txt"

def scrape_website_and_nav_pages(start_url, skip_nav_links=False):
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
    
    # Initialize sets for tracking
    to_scrape = {start_url}
    scraped = set()
    
    # Scrape pages
    while to_scrape:
        # Get a URL to scrape
        current_url = to_scrape.pop()
        
        # Skip if already scraped
        if current_url in scraped:
            continue
        
        print(f"Scraping: {current_url}")
        
        # Scrape the page
        content, nav_links = scrape_page(current_url)
        
        if content:
            # Get the filename
            filename = get_filename_from_url(current_url)
            file_path = os.path.join(output_dir, filename)
            
            # Save to file
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(content)
            
            print(f"Saved content to: {file_path}")
            
            # Add to scraped set
            scraped.add(current_url)
            
            # Add new links to scrape (only if not skipping nav links)
            if not skip_nav_links:
                new_links = nav_links - scraped
                to_scrape.update(new_links)
            
            # Be polite - add a small delay
            time.sleep(1)
    
    return output_dir, len(scraped)

if __name__ == "__main__":
    website_url = input("Enter the URL of the website to scrape: ")
    output_dir, pages_scraped = scrape_website_and_nav_pages(website_url)
    
    print(f"\nScraping complete!")
    print(f"Scraped {pages_scraped} pages to directory: {output_dir}")
