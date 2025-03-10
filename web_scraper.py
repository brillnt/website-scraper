import requests
from bs4 import BeautifulSoup

def scrape_website_copy(url):
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
                    content.append(element_text)
        
        return "\n\n".join(content)
    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return None
    except Exception as e:
        print(f"An error occurred: {e}")
        return None

if __name__ == "__main__":
    website_url = input("Enter the URL of the website to scrape: ")
    scraped_copy = scrape_website_copy(website_url)
    if scraped_copy:
        print("\nScraped copy from the website:\n")
        print(scraped_copy)