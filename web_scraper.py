import requests
from bs4 import BeautifulSoup

def scrape_website_copy(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract headings and paragraphs
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        paragraphs = soup.find_all('p')
        
        # Format the content
        content = []
        
        # Add headings
        for heading in headings:
            heading_text = heading.get_text(strip=True)
            if heading_text:  # Only add non-empty headings
                content.append(f"{heading.name.upper()}: {heading_text}")
        
        # Add paragraphs
        for para in paragraphs:
            para_text = para.get_text(strip=True)
            if para_text:  # Only add non-empty paragraphs
                content.append(f"PARAGRAPH: {para_text}")
        
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