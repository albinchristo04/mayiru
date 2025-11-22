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
        
        # Find all buttons with onclick that contains match URLs
        buttons = soup.find_all('button', class_='watch-btn')
        
        for button in buttons:
            onclick = button.get('onclick', '')
            
            # Extract URL from onclick="window.location.href='URL'"
            url_match = re.search(r"window\.location\.href='([^']+)'", onclick)
            if not url_match:
                continue
            
            match_url = url_match.group(1)
            
            # Get the parent stream-row to extract time and match info
            stream_row = button.find_parent('div', class_='stream-row')
            if not stream_row:
                continue
            
            # Extract time
            time_elem = stream_row.find('div', class_='stream-time')
            time_str = time_elem.get_text(strip=True) if time_elem else ""
            
            # Extract match title
            info_elem = stream_row.find('div', class_='stream-info')
            if info_elem:
                # Get text without the img tag
                title = info_elem.get_text(strip=True)
            else:
                title = "Unknown Match"
            
            # Extract category
            category = stream_row.get('data-category', 'unknown')
            
            matches.append({
                'title': title,
                'url': match_url,
                'time': time_str,
                'category': category
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
                elif src.startswith('/') and not src.startswith('//'):
                    src = self.base_url + src
                
                iframes.append(src)
        
        # Also look for iframes in script tags (sometimes dynamically loaded)
        scripts = soup.find_all('script')
        for script in scripts:
            script_content = script.string
            if script_content:
                # Look for iframe sources in JavaScript
                iframe_urls = re.findall(r'(?:src|iframe)["\s:=]+(["\'])(https?://[^"\']+)\1', script_content)
                for _, url in iframe_urls:
                    if url not in iframes:
                        iframes.append(url)
        
        return iframes

    def scrape_match_details(self, match_url: str) -> Dict:
        """Scrape iframe details from a specific match page"""
        print(f"  Scraping: {match_url}")
        
        html = self.fetch_page(match_url)
        if not html:
            return None
        
        iframes = self.extract_iframes(html)
        
        # Debug: Save first match page HTML
        if not hasattr(self, '_saved_match_page'):
            with open('debug_match_page.html', 'w', encoding='utf-8') as f:
                f.write(html)
            self._saved_match_page = True
            print(f"  Debug: Saved match page HTML")
        
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
        
        # Save homepage for debugging
        with open('debug_homepage.html', 'w', encoding='utf-8') as f:
            f.write(homepage_html)
        print(f"Debug: Saved homepage ({len(homepage_html)} chars)")
        
        print("\nExtracting match links...")
        matches = self.extract_match_links(homepage_html)
        print(f"✅ Found {len(matches)} matches\n")
        
        if len(matches) == 0:
            print("⚠️ No matches found - check debug_homepage.html")
            return {
                'last_updated': datetime.utcnow().isoformat() + 'Z',
                'total_matches': 0,
                'matches': []
            }
        
        results = []
        for i, match in enumerate(matches, 1):
            print(f"[{i}/{len(matches)}] {match['title']} ({match['time']})")
            
            details = self.scrape_match_details(match['url'])
            
            if details:
                results.append({
                    'title': match['title'],
                    'url': match['url'],
                    'time': match['time'],
                    'category': match['category'],
                    'iframes': details['iframes'],
                    'iframe_count': details['iframe_count']
                })
                print(f"  ✅ Found {details['iframe_count']} iframe(s)")
            else:
                print(f"  ❌ Failed to scrape")
            
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
        print(f"📊 Statistics:")
        print(f"   Total matches: {data.get('total_matches', 0)}")
        total_iframes = sum(m.get('iframe_count', 0) for m in data.get('matches', []))
        print(f"   Total iframes: {total_iframes}")
        
        # Show category breakdown
        if data.get('matches'):
            categories = {}
            for match in data['matches']:
                cat = match.get('category', 'unknown')
                categories[cat] = categories.get(cat, 0) + 1
            
            print(f"\n📋 Matches by category:")
            for cat, count in sorted(categories.items()):
                print(f"   {cat}: {count}")

def main():
    scraper = OvogoaalScraper()
    
    print("🔍 Starting Ovogoaal.com scraper...\n")
    print("=" * 60)
    
    data = scraper.scrape_all()
    
    if data and data.get('total_matches', 0) > 0:
        scraper.save_to_json(data)
        print("\n" + "=" * 60)
        print("✨ Scraping completed successfully!")
    else:
        print("\n⚠️ No matches found")
        # Still save empty data
        scraper.save_to_json(data if data else {
            'last_updated': datetime.utcnow().isoformat() + 'Z',
            'total_matches': 0,
            'matches': []
        })

if __name__ == "__main__":
    main()
