import requests
from bs4 import BeautifulSoup

def scrape_website_copy(url):
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        soup = BeautifulSoup(response.content, 'html.parser')
        text_content = soup.get_text(separator='\n', strip=True)
        return text_content
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