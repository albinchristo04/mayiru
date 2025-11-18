#!/usr/bin/env python3
"""
OvoGoaal Stream Extractor
Extracts streaming data including iframes, m3u8 URLs, and event categories
"""

import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime
from urllib.parse import urljoin, urlparse
import time

class OvoStreamExtractor:
    def __init__(self):
        self.base_url = "https://ovogoaal.com/"
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
        }
        
    def fetch_page(self, url):
        """Fetch page content"""
        try:
            response = self.session.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            return response.text
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None
    
    def extract_iframes(self, html):
        """Extract all iframe sources"""
        soup = BeautifulSoup(html, 'html.parser')
        iframes = []
        
        for iframe in soup.find_all('iframe'):
            src = iframe.get('src') or iframe.get('data-src')
            if src:
                iframes.append({
                    'src': urljoin(self.base_url, src),
                    'attributes': dict(iframe.attrs)
                })
        
        return iframes
    
    def extract_m3u8_from_page(self, html, page_url):
        """Extract m3u8 URLs from page content"""
        m3u8_urls = []
        
        # Pattern 1: Direct m3u8 URLs in HTML
        m3u8_pattern = r'https?://[^\s<>"]+?\.m3u8[^\s<>"]*'
        matches = re.findall(m3u8_pattern, html)
        m3u8_urls.extend(matches)
        
        # Pattern 2: JavaScript variables containing m3u8
        js_patterns = [
            r'["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'source["\']?\s*:\s*["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'file["\']?\s*:\s*["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'src["\']?\s*:\s*["\']([^"\']*\.m3u8[^"\']*)["\']',
        ]
        
        for pattern in js_patterns:
            matches = re.findall(pattern, html)
            m3u8_urls.extend(matches)
        
        # Remove duplicates and resolve relative URLs
        m3u8_urls = list(set(m3u8_urls))
        resolved_urls = []
        
        for url in m3u8_urls:
            if url.startswith('http'):
                resolved_urls.append(url)
            else:
                resolved_urls.append(urljoin(page_url, url))
        
        return resolved_urls
    
    def extract_iframe_content(self, iframe_url):
        """Fetch and extract content from iframe"""
        html = self.fetch_page(iframe_url)
        if not html:
            return None
        
        return {
            'url': iframe_url,
            'm3u8_urls': self.extract_m3u8_from_page(html, iframe_url),
            'nested_iframes': self.extract_iframes(html)
        }
    
    def extract_events(self, html):
        """Extract event categories and details"""
        soup = BeautifulSoup(html, 'html.parser')
        events = []
        
        # Common patterns for sports streaming sites
        selectors = [
            {'class': 'match'},
            {'class': 'event'},
            {'class': 'game'},
            {'class': 'stream'},
            {'class': 'live'},
            {'class': 'fixture'},
        ]
        
        for selector in selectors:
            items = soup.find_all(['div', 'li', 'article'], selector)
            for item in items:
                event = self.parse_event(item)
                if event:
                    events.append(event)
        
        # Also look for links to event pages
        links = soup.find_all('a', href=True)
        for link in links:
            href = link.get('href')
            text = link.get_text(strip=True)
            if href and text:
                full_url = urljoin(self.base_url, href)
                # Filter for likely event pages
                if any(sport in href.lower() for sport in ['football', 'soccer', 'basketball', 'tennis', 'hockey', 'baseball']):
                    events.append({
                        'title': text,
                        'url': full_url,
                        'type': 'link'
                    })
        
        return events
    
    def parse_event(self, element):
        """Parse individual event element"""
        try:
            title = element.get_text(strip=True)
            link = element.find('a')
            url = link.get('href') if link else None
            
            if url:
                url = urljoin(self.base_url, url)
            
            # Try to extract category/sport
            category = None
            for cls in element.get('class', []):
                if any(sport in cls.lower() for sport in ['football', 'soccer', 'basketball', 'tennis', 'hockey']):
                    category = cls
                    break
            
            return {
                'title': title,
                'url': url,
                'category': category,
                'type': 'event'
            }
        except:
            return None
    
    def get_m3u8_headers(self, m3u8_url):
        """Generate appropriate headers for m3u8 playback"""
        parsed = urlparse(m3u8_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Origin': origin,
            'Referer': self.base_url,
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
        }
    
    def extract_all(self):
        """Main extraction method"""
        print(f"[{datetime.now().isoformat()}] Starting extraction from {self.base_url}")
        
        # Fetch main page
        html = self.fetch_page(self.base_url)
        if not html:
            print("Failed to fetch main page")
            return None
        
        print("Extracting events...")
        events = self.extract_events(html)
        print(f"Found {len(events)} events")
        
        print("Extracting iframes...")
        iframes = self.extract_iframes(html)
        print(f"Found {len(iframes)} iframes")
        
        print("Extracting m3u8 URLs from main page...")
        m3u8_urls = self.extract_m3u8_from_page(html, self.base_url)
        print(f"Found {len(m3u8_urls)} m3u8 URLs on main page")
        
        # Process iframes
        iframe_data = []
        for i, iframe in enumerate(iframes[:5]):  # Limit to first 5 iframes
            print(f"Processing iframe {i+1}/{min(len(iframes), 5)}...")
            try:
                data = self.extract_iframe_content(iframe['src'])
                if data:
                    iframe_data.append(data)
                time.sleep(1)  # Rate limiting
            except Exception as e:
                print(f"Error processing iframe: {e}")
        
        # Compile results
        results = {
            'timestamp': datetime.now().isoformat(),
            'source_url': self.base_url,
            'events': events,
            'main_page': {
                'iframes': iframes,
                'm3u8_urls': m3u8_urls
            },
            'iframe_data': iframe_data,
            'playback_info': []
        }
        
        # Add playback information for all m3u8 URLs
        all_m3u8 = set(m3u8_urls)
        for iframe in iframe_data:
            all_m3u8.update(iframe.get('m3u8_urls', []))
        
        for m3u8_url in all_m3u8:
            results['playback_info'].append({
                'url': m3u8_url,
                'headers': self.get_m3u8_headers(m3u8_url),
                'referer': self.base_url
            })
        
        return results
    
    def save_results(self, results, filename='stream_data.json'):
        """Save results to JSON file"""
        if results:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\nResults saved to {filename}")
            print(f"Total m3u8 URLs found: {len(results['playback_info'])}")
            print(f"Total events found: {len(results['events'])}")
        else:
            print("No results to save")

def main():
    extractor = OvoStreamExtractor()
    results = extractor.extract_all()
    
    if results:
        extractor.save_results(results)
        
        # Print summary
        print("\n" + "="*50)
        print("EXTRACTION SUMMARY")
        print("="*50)
        print(f"Events found: {len(results['events'])}")
        print(f"Iframes found: {len(results['main_page']['iframes'])}")
        print(f"M3U8 URLs found: {len(results['playback_info'])}")
        
        if results['playback_info']:
            print("\nSample M3U8 playback info:")
            sample = results['playback_info'][0]
            print(f"URL: {sample['url']}")
            print(f"Referer: {sample['referer']}")
            print("Headers:", json.dumps(sample['headers'], indent=2))
    else:
        print("Extraction failed")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
