import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime
from typing import List, Dict, Optional
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

    def fetch_page(self, url: str, referer: str = None) -> str:
        """Fetch a page with error handling"""
        try:
            headers = self.headers.copy()
            if referer:
                headers['Referer'] = referer
            response = self.session.get(url, timeout=30, headers=headers)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"    Error fetching {url}: {e}")
            return ""

    def extract_match_links(self, html: str) -> List[Dict]:
        """Extract all match links from the homepage"""
        soup = BeautifulSoup(html, 'html.parser')
        matches = []
        
        buttons = soup.find_all('button', class_='watch-btn')
        
        for button in buttons:
            onclick = button.get('onclick', '')
            url_match = re.search(r"window\.location\.href='([^']+)'", onclick)
            if not url_match:
                continue
            
            match_url = url_match.group(1)
            stream_row = button.find_parent('div', class_='stream-row')
            if not stream_row:
                continue
            
            time_elem = stream_row.find('div', class_='stream-time')
            time_str = time_elem.get_text(strip=True) if time_elem else ""
            
            info_elem = stream_row.find('div', class_='stream-info')
            title = info_elem.get_text(strip=True) if info_elem else "Unknown Match"
            category = stream_row.get('data-category', 'unknown')
            
            matches.append({
                'title': title,
                'url': match_url,
                'time': time_str,
                'category': category
            })
        
        return matches

    def extract_iframes_from_html(self, html: str, base_url: str = None) -> List[str]:
        """Extract all iframe sources from HTML content"""
        soup = BeautifulSoup(html, 'html.parser')
        iframes = []
        
        # Find all iframes
        iframe_tags = soup.find_all('iframe')
        for iframe in iframe_tags:
            src = iframe.get('src', '') or iframe.get('data-src', '')
            if src:
                src = self._normalize_url(src, base_url)
                if src and src not in iframes:
                    iframes.append(src)
        
        # Look for iframes in script tags
        scripts = soup.find_all('script')
        for script in scripts:
            content = script.string
            if content:
                # Pattern 1: src="url" or iframe="url"
                urls = re.findall(r'(?:src|iframe)["\s:=]+["\']?(https?://[^\s"\'<>]+)', content)
                for url in urls:
                    if url not in iframes:
                        iframes.append(url)
                
                # Pattern 2: Look for .php URLs specifically
                php_urls = re.findall(r'(https?://[^\s"\'<>]+\.php[^\s"\'<>]*)', content)
                for url in php_urls:
                    if url not in iframes:
                        iframes.append(url)
        
        return iframes

    def _normalize_url(self, url: str, base_url: str = None) -> str:
        """Normalize URL to absolute form"""
        if not url or url.startswith('javascript:') or url.startswith('about:'):
            return ""
        if url.startswith('//'):
            return 'https:' + url
        elif url.startswith('/') and base_url:
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}{url}"
        elif not url.startswith('http'):
            if base_url:
                from urllib.parse import urljoin
                return urljoin(base_url, url)
            return ""
        return url

    def extract_nested_iframes(self, iframe_url: str, depth: int = 0, max_depth: int = 2) -> Dict:
        """
        Recursively extract nested iframes from an iframe URL
        Returns a dict with the URL and any nested iframes found
        """
        result = {
            'url': iframe_url,
            'nested_iframes': [],
            'stream_urls': []
        }
        
        if depth >= max_depth:
            return result
        
        # Skip YouTube and other known non-stream URLs
        skip_domains = ['youtube.com', 'google.com', 'facebook.com', 'twitter.com']
        if any(domain in iframe_url for domain in skip_domains):
            return result
        
        print(f"    {'  ' * depth}↳ Fetching: {iframe_url}")
        html = self.fetch_page(iframe_url, referer=self.base_url)
        
        if not html:
            return result
        
        # Extract iframes from this page
        nested_urls = self.extract_iframes_from_html(html, iframe_url)
        
        # Also look for direct stream URLs (.php, .m3u8, etc.)
        stream_patterns = [
            r'(https?://[^\s"\'<>]+\.php[^\s"\'<>]*)',
            r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)',
            r'source["\s:=]+["\']?(https?://[^\s"\'<>]+)',
            r'file["\s:=]+["\']?(https?://[^\s"\'<>]+)',
            r'hls["\s:=]+["\']?(https?://[^\s"\'<>]+)',
        ]
        
        for pattern in stream_patterns:
            matches = re.findall(pattern, html, re.IGNORECASE)
            for url in matches:
                url = url.strip('"\'')
                if url and url not in result['stream_urls'] and url != iframe_url:
                    result['stream_urls'].append(url)
        
        # Process nested iframes
        for nested_url in nested_urls:
            if nested_url == iframe_url:
                continue
            
            # Check if it's likely a stream URL
            if any(ext in nested_url.lower() for ext in ['.php', '.m3u8', 'stream', 'player']):
                if nested_url not in result['stream_urls']:
                    result['stream_urls'].append(nested_url)
            
            # Recursively fetch nested iframes
            time.sleep(0.5)  # Small delay
            nested_result = self.extract_nested_iframes(nested_url, depth + 1, max_depth)
            result['nested_iframes'].append(nested_result)
            
            # Collect stream URLs from nested results
            result['stream_urls'].extend(nested_result.get('stream_urls', []))
        
        # Deduplicate stream URLs
        result['stream_urls'] = list(set(result['stream_urls']))
        
        return result

    def scrape_match_details(self, match_url: str) -> Dict:
        """Scrape iframe details from a specific match page"""
        print(f"  Scraping: {match_url}")
        
        html = self.fetch_page(match_url)
        if not html:
            return None
        
        # Get first-level iframes
        first_level_iframes = self.extract_iframes_from_html(html, match_url)
        
        all_stream_urls = []
        iframe_details = []
        
        for iframe_url in first_level_iframes:
            # Skip YouTube live chat
            if 'youtube.com/live_chat' in iframe_url:
                iframe_details.append({
                    'url': iframe_url,
                    'type': 'youtube_chat',
                    'nested_iframes': [],
                    'stream_urls': []
                })
                continue
            
            # Extract nested iframes
            time.sleep(1)  # Delay between requests
            nested = self.extract_nested_iframes(iframe_url)
            
            iframe_details.append(nested)
            all_stream_urls.extend(nested.get('stream_urls', []))
        
        # Deduplicate
        all_stream_urls = list(set(all_stream_urls))
        
        return {
            'first_level_iframes': first_level_iframes,
            'iframe_details': iframe_details,
            'stream_urls': all_stream_urls,
            'stream_count': len(all_stream_urls)
        }

    def scrape_all(self) -> Dict:
        """Main scraping function"""
        print("Fetching homepage...")
        homepage_html = self.fetch_page(self.base_url)
        
        if not homepage_html:
            print("Failed to fetch homepage")
            return {}
        
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
            print(f"\n[{i}/{len(matches)}] {match['title']} ({match['time']})")
            print("-" * 50)
            
            details = self.scrape_match_details(match['url'])
            
            if details:
                results.append({
                    'title': match['title'],
                    'url': match['url'],
                    'time': match['time'],
                    'category': match['category'],
                    'first_level_iframes': details['first_level_iframes'],
                    'stream_urls': details['stream_urls'],
                    'stream_count': details['stream_count'],
                    'iframe_details': details['iframe_details']
                })
                print(f"  ✅ Found {details['stream_count']} stream URL(s)")
                for url in details['stream_urls']:
                    print(f"     → {url}")
            else:
                print(f"  ❌ Failed to scrape")
            
            # Delay between matches
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
        
        print(f"\n{'=' * 60}")
        print(f"✅ Data saved to {filename}")
        print(f"\n📊 Statistics:")
        print(f"   Total matches: {data.get('total_matches', 0)}")
        
        total_streams = sum(m.get('stream_count', 0) for m in data.get('matches', []))
        print(f"   Total stream URLs: {total_streams}")
        
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
    
    print("🔍 Starting Ovogoaal.com scraper (with nested iframe extraction)...\n")
    print("=" * 60)
    
    data = scraper.scrape_all()
    
    if data and data.get('total_matches', 0) > 0:
        scraper.save_to_json(data)
        print("\n" + "=" * 60)
        print("✨ Scraping completed successfully!")
    else:
        print("\n⚠️ No matches found")
        scraper.save_to_json(data if data else {
            'last_updated': datetime.utcnow().isoformat() + 'Z',
            'total_matches': 0,
            'matches': []
        })


if __name__ == "__main__":
    main()
