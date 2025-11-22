import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
from typing import List, Dict
import time

class OvogoaalScraper:
    def __init__(self):
        self.base_url = "https://ovogoaal.com"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def fetch_page(self, url: str) -> str:
        """Fetch a page with error handling"""
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return ""

    def extract_match_links(self, html: str) -> List[Dict]:
        """Extract all match links from the homepage"""
        soup = BeautifulSoup(html, 'html.parser')
        matches = []
        
        # Look for match links - multiple possible patterns
        patterns = [
            r'/match-updates/',
            r'/live/',
            r'/stream/',
            r'/match/',
            r'/game/'
        ]
        
        links = []
        for pattern in patterns:
            found = soup.find_all('a', href=re.compile(pattern))
            links.extend(found)
        
        # Also try finding links in common container classes
        containers = soup.find_all(['div', 'article', 'section'], class_=re.compile(r'match|game|stream|event', re.I))
        for container in containers:
            container_links = container.find_all('a', href=True)
            links.extend(container_links)
        
        seen_urls = set()
        for link in links:
            href = link.get('href', '')
            if not href:
                continue
            
            # Make absolute URL
            if href.startswith('/'):
                full_url = self.base_url + href
            elif href.startswith('http'):
                full_url = href
            else:
                full_url = self.base_url + '/' + href
            
            # Avoid duplicates
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            
            # Extract match title
            title = link.get_text(strip=True)
            if not title:
                # Try to extract from URL
                title = href.split('/')[-1].replace('-', ' ').title()
            
            # Try to find time/date info nearby
            time_info = ""
            parent = link.parent
            if parent:
                time_elem = parent.find(['time', 'span'], class_=re.compile(r'time|date', re.I))
                if time_elem:
                    time_info = time_elem.get_text(strip=True)
            
            matches.append({
                'title': title,
                'url': full_url,
                'time': time_info
            })
        
        return matches

    def extract_iframes(self, html: str) -> List[str]:
        """Extract all iframe sources from a match page"""
        soup = BeautifulSoup(html, 'html.parser')
        iframes = []
        
        # Find all iframes
        iframe_tags = soup.find_all('iframe')
        
        for iframe in iframe_tags:
            src = iframe.get('src', '') or iframe.get('data-src', '')
            if src:
                # Make absolute URL if needed
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = self.base_url + src
                
                iframes.append(src)
        
        return iframes

    def scrape_match_details(self, match_url: str) -> Dict:
        """Scrape iframe details from a specific match page"""
        print(f"Scraping: {match_url}")
        
        html = self.fetch_page(match_url)
        if not html:
            return None
        
        iframes = self.extract_iframes(html)
        
        return {
            'iframes': iframes,
            'iframe_count': len(iframes)
        }

    def scrape_all(self) -> Dict:
        """Main scraping function"""
        print("Fetching homepage...")
        homepage_html = self.fetch_page(self.base_url)
        
        if not homepage_html:
            print("Failed to fetch homepage")
            return {}
        
        print("Extracting match links...")
        matches = self.extract_match_links(homepage_html)
        print(f"Found {len(matches)} matches")
        
        results = []
        for i, match in enumerate(matches, 1):
            print(f"\n[{i}/{len(matches)}] Processing: {match['title']}")
            
            details = self.scrape_match_details(match['url'])
            
            if details:
                results.append({
                    'title': match['title'],
                    'url': match['url'],
                    'time': match['time'],
                    'iframes': details['iframes'],
                    'iframe_count': details['iframe_count']
                })
            
            # Be polite - delay between requests
            if i < len(matches):
                time.sleep(2)
        
        return {
            'last_updated': datetime.utcnow().isoformat() + 'Z',
            'total_matches': len(results),
            'matches': results
        }

    def save_to_json(self, data: Dict, filename: str = 'ovogoaal_events.json'):
        """Save scraped data to JSON file"""
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Data saved to {filename}")
        print(f"Total matches: {data.get('total_matches', 0)}")
        total_iframes = sum(m.get('iframe_count', 0) for m in data.get('matches', []))
        print(f"Total iframes: {total_iframes}")

def main():
    scraper = OvogoaalScraper()
    
    print("🔍 Starting Ovogoaal.com scraper...\n")
    
    # Debug: Save homepage HTML
    print("Fetching homepage for debugging...")
    homepage_html = scraper.fetch_page(scraper.base_url)
    if homepage_html:
        with open('debug_homepage.html', 'w', encoding='utf-8') as f:
            f.write(homepage_html)
        print(f"Debug: Saved homepage HTML ({len(homepage_html)} chars)")
    
    data = scraper.scrape_all()
    
    if data and data.get('total_matches', 0) > 0:
        scraper.save_to_json(data)
        print("\n✨ Scraping completed successfully!")
    else:
        print("\n⚠️ No matches found - website structure may have changed")
        print("Check debug_homepage.html to see the actual page content")
        # Still save empty data
        scraper.save_to_json(data if data else {'last_updated': datetime.utcnow().isoformat() + 'Z', 'total_matches': 0, 'matches': []})

if __name__ == "__main__":
    main()
