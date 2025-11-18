#!/usr/bin/env python3
"""
OvoGoaal Stream Extractor
Extracts streaming data including event links, categories, and m3u8 URLs
"""

import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs
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
    
    def extract_events_from_html(self, html):
        """Extract events from the specific HTML structure"""
        soup = BeautifulSoup(html, 'html.parser')
        events = []
        
        # Find all stream-row divs
        stream_rows = soup.find_all('div', class_='stream-row')
        
        print(f"Found {len(stream_rows)} stream rows")
        
        for row in stream_rows:
            try:
                # Extract category
                category = row.get('data-category', 'unknown')
                
                # Extract time
                time_elem = row.find('div', class_='stream-time')
                match_time = time_elem.get_text(strip=True) if time_elem else 'Unknown'
                
                # Extract match info
                info_elem = row.find('div', class_='stream-info')
                match_info = info_elem.get_text(strip=True) if info_elem else 'Unknown Match'
                
                # Extract logo
                logo_img = info_elem.find('img', class_='team-logo') if info_elem else None
                logo_url = logo_img.get('src') if logo_img else None
                if logo_url:
                    logo_url = urljoin(self.base_url, logo_url)
                
                # Extract watch button and URL
                watch_btn = row.find('button', class_='watch-btn')
                stream_url = None
                
                if watch_btn:
                    onclick = watch_btn.get('onclick', '')
                    # Extract URL from onclick="window.location.href='...'"
                    url_match = re.search(r"window\.location\.href=['\"]([^'\"]+)['\"]", onclick)
                    if url_match:
                        stream_url = url_match.group(1)
                        if not stream_url.startswith('http'):
                            stream_url = urljoin(self.base_url, stream_url)
                
                event = {
                    'category': category,
                    'time': match_time,
                    'match': match_info,
                    'logo': logo_url,
                    'stream_page_url': stream_url,
                    'type': 'live_event'
                }
                
                events.append(event)
                
            except Exception as e:
                print(f"Error parsing event: {e}")
                continue
        
        return events
    
    def extract_stream_page_data(self, url):
        """Extract iframe and m3u8 data from a stream page"""
        print(f"Fetching stream page: {url}")
        html = self.fetch_page(url)
        
        if not html:
            return None
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # Extract iframes
        iframes = []
        for iframe in soup.find_all('iframe'):
            src = iframe.get('src') or iframe.get('data-src')
            if src:
                full_src = urljoin(url, src)
                iframes.append({
                    'src': full_src,
                    'attributes': dict(iframe.attrs)
                })
        
        # Extract m3u8 URLs
        m3u8_urls = self.extract_m3u8_from_page(html, url)
        
        # Extract any embedded player URLs
        player_urls = []
        
        # Look for common player patterns
        patterns = [
            r'player\.php\?id=([^&\'"]+)',
            r'embed\.php\?id=([^&\'"]+)',
            r'stream\.php\?id=([^&\'"]+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, html)
            for match in matches:
                player_urls.append(urljoin(url, f"player.php?id={match}"))
        
        return {
            'url': url,
            'iframes': iframes,
            'm3u8_urls': m3u8_urls,
            'player_urls': player_urls
        }
    
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
            r'hlsUrl["\']?\s*:\s*["\']([^"\']*)["\']',
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
            'nested_iframes': [
                {
                    'src': urljoin(iframe_url, iframe.get('src') or iframe.get('data-src')),
                    'attributes': dict(iframe.attrs)
                }
                for iframe in BeautifulSoup(html, 'html.parser').find_all('iframe')
                if iframe.get('src') or iframe.get('data-src')
            ]
        }
    
    def get_m3u8_headers(self, m3u8_url, referer=None):
        """Generate appropriate headers for m3u8 playback"""
        parsed = urlparse(m3u8_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Origin': origin,
            'Referer': referer or self.base_url,
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'cross-site',
        }
    
    def extract_all(self, max_stream_pages=5):
        """Main extraction method"""
        print(f"[{datetime.now().isoformat()}] Starting extraction from {self.base_url}")
        
        # Fetch main page
        html = self.fetch_page(self.base_url)
        if not html:
            print("Failed to fetch main page")
            return None
        
        print("Extracting events from main page...")
        events = self.extract_events_from_html(html)
        print(f"Found {len(events)} events")
        
        # Extract stream page data for each event
        stream_pages_data = []
        for i, event in enumerate(events[:max_stream_pages]):
            if event.get('stream_page_url'):
                print(f"\nProcessing stream page {i+1}/{min(len(events), max_stream_pages)}: {event['match']}")
                try:
                    stream_data = self.extract_stream_page_data(event['stream_page_url'])
                    if stream_data:
                        stream_data['event_info'] = {
                            'match': event['match'],
                            'category': event['category'],
                            'time': event['time']
                        }
                        stream_pages_data.append(stream_data)
                    time.sleep(2)  # Rate limiting
                except Exception as e:
                    print(f"Error processing stream page: {e}")
        
        # Process iframes from stream pages
        print("\nProcessing iframes from stream pages...")
        iframe_data = []
        iframe_count = 0
        for stream_page in stream_pages_data:
            for iframe in stream_page.get('iframes', [])[:2]:  # Limit to 2 iframes per page
                if iframe_count >= 10:  # Overall limit
                    break
                print(f"Processing iframe {iframe_count + 1}: {iframe['src'][:80]}...")
                try:
                    data = self.extract_iframe_content(iframe['src'])
                    if data:
                        iframe_data.append(data)
                    iframe_count += 1
                    time.sleep(1)
                except Exception as e:
                    print(f"Error processing iframe: {e}")
        
        # Compile all m3u8 URLs
        all_m3u8 = set()
        for stream_page in stream_pages_data:
            all_m3u8.update(stream_page.get('m3u8_urls', []))
        for iframe in iframe_data:
            all_m3u8.update(iframe.get('m3u8_urls', []))
        
        # Create playback info
        playback_info = []
        for m3u8_url in all_m3u8:
            playback_info.append({
                'url': m3u8_url,
                'headers': self.get_m3u8_headers(m3u8_url),
                'referer': self.base_url
            })
        
        # Compile results
        results = {
            'timestamp': datetime.now().isoformat(),
            'source_url': self.base_url,
            'events': events,
            'stream_pages': stream_pages_data,
            'iframe_data': iframe_data,
            'playback_info': playback_info,
            'statistics': {
                'total_events': len(events),
                'stream_pages_analyzed': len(stream_pages_data),
                'iframes_found': sum(len(sp.get('iframes', [])) for sp in stream_pages_data),
                'iframes_analyzed': len(iframe_data),
                'm3u8_urls_found': len(playback_info)
            }
        }
        
        return results
    
    def save_results(self, results, filename='stream_data.json'):
        """Save results to JSON file"""
        if results:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\n{'='*60}")
            print(f"Results saved to {filename}")
            print(f"{'='*60}")
            print(f"Total events found: {results['statistics']['total_events']}")
            print(f"Stream pages analyzed: {results['statistics']['stream_pages_analyzed']}")
            print(f"Iframes found: {results['statistics']['iframes_found']}")
            print(f"Iframes analyzed: {results['statistics']['iframes_analyzed']}")
            print(f"M3U8 URLs found: {results['statistics']['m3u8_urls_found']}")
            print(f"{'='*60}")
        else:
            print("No results to save")

def main():
    extractor = OvoStreamExtractor()
    
    # Extract with limit on stream pages to analyze (to avoid long runtime)
    results = extractor.extract_all(max_stream_pages=5)
    
    if results:
        extractor.save_results(results)
        
        # Print sample event
        if results['events']:
            print("\nSample Event:")
            sample_event = results['events'][0]
            print(json.dumps(sample_event, indent=2))
        
        # Print sample m3u8 info if available
        if results['playback_info']:
            print("\nSample M3U8 Playback Info:")
            sample = results['playback_info'][0]
            print(f"URL: {sample['url']}")
            print(f"Referer: {sample['referer']}")
            print("Headers:", json.dumps(sample['headers'], indent=2))
        
        return 0
    else:
        print("Extraction failed")
        return 1

if __name__ == "__main__":
    exit(main())
