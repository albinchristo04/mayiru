#!/usr/bin/env python3
"""
Fast M3U8 URL Extractor
This script efficiently extracts M3U8 URLs by:
1. Following redirects to find actual stream URLs
2. Parsing webpage content quickly
3. Using multiple detection methods
4. Handling timeouts and errors gracefully
5. Limited to processing first 1500 channels
"""

import requests
import json
import re
from datetime import datetime
import sys
import time
from urllib.parse import urljoin, urlparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

class FastM3U8Extractor:
    def __init__(self, max_workers=5, timeout=15, max_channels=1500):
        self.max_workers = max_workers
        self.timeout = timeout
        self.max_channels = max_channels
        self.lock = threading.Lock()
        self.processed_count = 0
        
        # Create session with optimized settings
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache'
        })
        
        # Set adapter with retry strategy
        adapter = requests.adapters.HTTPAdapter(
            max_retries=requests.adapters.Retry(
                total=2,
                backoff_factor=0.5,
                status_forcelist=[500, 502, 503, 504]
            )
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def fetch_m3u_content(self, url):
        """Fetch M3U content from URL"""
        try:
            logging.info(f"Fetching M3U playlist from: {url}")
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logging.error(f"Error fetching M3U: {e}")
            return None

    def parse_m3u_for_webpages(self, content):
        """Parse M3U content and extract webpage URLs and channel info"""
        channels = []
        lines = content.strip().split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if line.startswith('#EXTINF:'):
                try:
                    channel_info = self.extract_channel_info(line)
                    
                    if i + 1 < len(lines):
                        webpage_url = lines[i + 1].strip()
                        
                        if webpage_url and not webpage_url.startswith('#'):
                            channel_info['webpage_url'] = webpage_url
                            channels.append(channel_info)
                        
                        i += 2
                    else:
                        i += 1
                except Exception as e:
                    logging.warning(f"Error parsing line {i}: {e}")
                    i += 1
            else:
                i += 1
        
        logging.info(f"Found {len(channels)} channels in M3U")
        
        # Limit to max_channels
        if len(channels) > self.max_channels:
            logging.info(f"⚠️ Limiting processing to first {self.max_channels} channels")
            channels = channels[:self.max_channels]
        
        return channels

    def extract_channel_info(self, extinf_line):
        """Extract channel information from EXTINF line"""
        channel_info = {'duration': '-1'}
        
        # Extract duration and title
        extinf_match = re.match(r'#EXTINF:([^,]*),(.+)', extinf_line)
        if extinf_match:
            channel_info['duration'] = extinf_match.group(1).strip()
        
        # Extract attributes
        patterns = {
            'tvg_id': r'tvg-id="([^"]*)"',
            'tvg_name': r'tvg-name="([^"]*)"', 
            'tvg_logo': r'tvg-logo="([^"]*)"',
            'group_title': r'group-title="([^"]*)"'
        }
        
        for attr, pattern in patterns.items():
            match = re.search(pattern, extinf_line)
            if match:
                channel_info[attr] = match.group(1)
        
        # Extract channel name
        name_parts = extinf_line.split(',')
        if len(name_parts) > 1:
            name = name_parts[-1].strip()
            name = re.sub(r'tvg-[^=]*="[^"]*"\s*', '', name).strip()
            channel_info['name'] = name if name else channel_info.get('tvg_name', 'Unknown Channel')
        else:
            channel_info['name'] = channel_info.get('tvg_name', 'Unknown Channel')
        
        return channel_info

    def extract_m3u8_from_webpage(self, webpage_url, channel_name):
        """Extract M3U8 URL from webpage with multiple methods"""
        try:
            logging.info(f"Processing: {channel_name} -> {webpage_url}")
            
            # Method 1: Check for direct redirects to M3U8
            m3u8_url = self.check_redirects(webpage_url)
            if m3u8_url:
                logging.info(f"✅ Found via redirect: {channel_name} -> {m3u8_url}")
                return m3u8_url
            
            # Method 2: Parse webpage content
            response = self.session.get(webpage_url, timeout=self.timeout, allow_redirects=True)
            if response.status_code != 200:
                logging.warning(f"HTTP {response.status_code} for {webpage_url}")
                return None
            
            content = response.text
            
            # Method 3: Look for M3U8 URLs in content
            m3u8_url = self.find_m3u8_in_content(content, webpage_url)
            if m3u8_url:
                logging.info(f"✅ Found in content: {channel_name} -> {m3u8_url}")
                return m3u8_url
            
            # Method 4: Check for iframe sources
            m3u8_url = self.check_iframes(content, webpage_url)
            if m3u8_url:
                logging.info(f"✅ Found in iframe: {channel_name} -> {m3u8_url}")
                return m3u8_url
            
            logging.warning(f"❌ No M3U8 found for: {channel_name}")
            return None
            
        except requests.Timeout:
            logging.warning(f"⏱️ Timeout for: {channel_name}")
            return None
        except Exception as e:
            logging.warning(f"❌ Error for {channel_name}: {e}")
            return None

    def check_redirects(self, url):
        """Check if URL redirects directly to an M3U8"""
        try:
            # Follow redirects but stop at first M3U8
            response = self.session.head(url, timeout=self.timeout, allow_redirects=False)
            
            redirect_count = 0
            current_url = url
            
            while redirect_count < 10:  # Max 10 redirects
                if response.status_code in [301, 302, 303, 307, 308]:
                    location = response.headers.get('Location', '')
                    if not location:
                        break
                    
                    # Make absolute URL
                    if location.startswith('//'):
                        location = 'https:' + location
                    elif location.startswith('/'):
                        parsed = urlparse(current_url)
                        location = f"{parsed.scheme}://{parsed.netloc}{location}"
                    elif not location.startswith('http'):
                        location = urljoin(current_url, location)
                    
                    # Check if this is an M3U8 URL
                    if '.m3u8' in location.lower():
                        return location
                    
                    current_url = location
                    response = self.session.head(current_url, timeout=self.timeout, allow_redirects=False)
                    redirect_count += 1
                else:
                    break
            
            # Check final URL
            if '.m3u8' in current_url.lower():
                return current_url
                
        except:
            pass
        
        return None

    def find_m3u8_in_content(self, content, base_url):
        """Find M3U8 URLs in webpage content"""
        # Multiple patterns to find M3U8 URLs
        patterns = [
            r'["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'source["\s]*:["\s]*["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'src["\s]*=["\s]*["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'file["\s]*:["\s]*["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'url["\s]*:["\s]*["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'hls[^"\']*["\s]*:["\s]*["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'playlist["\s]*:["\s]*["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'stream["\s]*:["\s]*["\']([^"\']*\.m3u8[^"\']*)["\']'
        ]
        
        found_urls = []
        
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE | re.DOTALL)
            for match in matches:
                url = match.strip()
                
                # Skip invalid URLs
                if any(skip in url.lower() for skip in ['javascript:', 'data:', '${', '{', 'undefined', 'null']):
                    continue
                
                # Convert to absolute URL
                if url.startswith('//'):
                    url = 'https:' + url
                elif url.startswith('/'):
                    parsed = urlparse(base_url)
                    url = f"{parsed.scheme}://{parsed.netloc}{url}"
                elif not url.startswith('http'):
                    url = urljoin(base_url, url)
                
                found_urls.append(url)
        
        # Return first valid URL
        for url in found_urls:
            if self.is_valid_m3u8(url):
                return url
        
        # If no valid URLs, return first one
        return found_urls[0] if found_urls else None

    def check_iframes(self, content, base_url):
        """Check iframe sources for M3U8 URLs"""
        iframe_pattern = r'<iframe[^>]+src=["\']([^"\']+)["\'][^>]*>'
        iframes = re.findall(iframe_pattern, content, re.IGNORECASE)
        
        for iframe_src in iframes[:3]:  # Check first 3 iframes only
            try:
                # Make absolute URL
                if iframe_src.startswith('//'):
                    iframe_src = 'https:' + iframe_src
                elif iframe_src.startswith('/'):
                    parsed = urlparse(base_url)
                    iframe_src = f"{parsed.scheme}://{parsed.netloc}{iframe_src}"
                elif not iframe_src.startswith('http'):
                    iframe_src = urljoin(base_url, iframe_src)
                
                # Quick check of iframe content
                iframe_response = self.session.get(iframe_src, timeout=10)
                if iframe_response.status_code == 200:
                    m3u8_url = self.find_m3u8_in_content(iframe_response.text, iframe_src)
                    if m3u8_url:
                        return m3u8_url
            except:
                continue
        
        return None

    def is_valid_m3u8(self, url):
        """Quick validation of M3U8 URL"""
        try:
            response = self.session.head(url, timeout=5)
            return response.status_code == 200
        except:
            return False

    def process_single_channel(self, channel):
        """Process a single channel"""
        webpage_url = channel.get('webpage_url')
        channel_name = channel.get('name', 'Unknown')
        
        if not webpage_url:
            return None
        
        m3u8_url = self.extract_m3u8_from_webpage(webpage_url, channel_name)
        
        if m3u8_url:
            channel['url'] = m3u8_url
            with self.lock:
                self.processed_count += 1
            return channel
        
        return None

    def process_channels_parallel(self, channels):
        """Process channels in parallel for speed"""
        successful_channels = []
        total = len(channels)
        
        logging.info(f"Processing {total} channels with {self.max_workers} workers...")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_channel = {
                executor.submit(self.process_single_channel, channel): channel 
                for channel in channels
            }
            
            # Process completed tasks
            for future in as_completed(future_to_channel):
                try:
                    result = future.result()
                    if result:
                        successful_channels.append(result)
                        with self.lock:
                            logging.info(f"Progress: {self.processed_count}/{total} - ✅ {result['name']}")
                except Exception as e:
                    channel = future_to_channel[future]
                    logging.error(f"Error processing {channel.get('name', 'Unknown')}: {e}")
        
        return successful_channels

    def save_to_json(self, channels, filename='updatedv3.json'):
        """Save channels to JSON file"""
        data = {
            'last_updated': datetime.utcnow().isoformat() + 'Z',
            'total_channels': len(channels),
            'extraction_method': 'fast_parallel_extractor',
            'max_channels_limit': self.max_channels,
            'channels': channels
        }
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logging.info(f"💾 Saved {len(channels)} channels to {filename}")
            return True
        except Exception as e:
            logging.error(f"Error saving JSON: {e}")
            return False

def main():
    logging.info("🚀 Starting Fast M3U8 Extractor (Limited to 1500 channels)...")
    
    # Initialize extractor with 1500 channel limit
    extractor = FastM3U8Extractor(max_workers=8, timeout=15, max_channels=1500)
    
    # M3U URL
    m3u_url = "https://raw.githubusercontent.com/abusaeeidx/IPTV-Scraper-Zilla/refs/heads/main/hilaytv.m3u"
    
    # Step 1: Fetch and parse M3U
    logging.info("📥 Fetching M3U playlist...")
    m3u_content = extractor.fetch_m3u_content(m3u_url)
    
    if not m3u_content:
        logging.error("Failed to fetch M3U content")
        sys.exit(1)
    
    # Step 2: Parse channels
    logging.info("📋 Parsing channel list...")
    channels = extractor.parse_m3u_for_webpages(m3u_content)
    
    if not channels:
        logging.error("No channels found in M3U")
        sys.exit(1)
    
    # Step 3: Extract M3U8 URLs (parallel processing)
    logging.info("⚡ Extracting M3U8 URLs (parallel processing)...")
    start_time = time.time()
    
    successful_channels = extractor.process_channels_parallel(channels)
    
    end_time = time.time()
    processing_time = end_time - start_time
    
    # Step 4: Save results
    if successful_channels:
        extractor.save_to_json(successful_channels)
        
        # Print summary
        success_rate = (len(successful_channels) / len(channels)) * 100
        logging.info("🎉 EXTRACTION COMPLETE!")
        logging.info(f"📊 SUMMARY:")
        logging.info(f"   ⏱️  Processing time: {processing_time:.1f} seconds")
        logging.info(f"   📺 Total channels processed: {len(channels)}")
        logging.info(f"   ✅ Successful: {len(successful_channels)}")
        logging.info(f"   ❌ Failed: {len(channels) - len(successful_channels)}")
        logging.info(f"   📈 Success rate: {success_rate:.1f}%")
        
        # Show some examples
        if successful_channels:
            logging.info("🔗 Sample extracted URLs:")
            for i, channel in enumerate(successful_channels[:3]):
                logging.info(f"   {i+1}. {channel['name']} -> {channel['url']}")
    else:
        logging.error("❌ No M3U8 URLs were successfully extracted")
        sys.exit(1)

if __name__ == "__main__":
    main()
