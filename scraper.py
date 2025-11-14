#!/usr/bin/env python3
"""
Fast M3U8 URL Extractor - Optimized Version
Improvements:
- Aggressive timeouts to prevent hanging
- Progress checkpoints
- Early termination on persistent failures
- Better error handling
"""

import requests
import json
import re
from datetime import datetime
import sys
import time
from urllib.parse import urljoin, urlparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import threading
import signal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

class TimeoutException(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutException("Operation timed out")

class FastM3U8Extractor:
    def __init__(self, max_workers=10, timeout=10, max_channels=1500):
        self.max_workers = max_workers
        self.timeout = timeout
        self.max_channels = max_channels
        self.lock = threading.Lock()
        self.processed_count = 0
        self.failed_count = 0
        self.last_progress_time = time.time()
        
        # Create session with aggressive timeouts
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
            'Cache-Control': 'no-cache'
        })
        
        # Set adapter with minimal retries
        adapter = requests.adapters.HTTPAdapter(
            max_retries=requests.adapters.Retry(
                total=1,
                backoff_factor=0.3,
                status_forcelist=[500, 502, 503, 504]
            ),
            pool_connections=max_workers,
            pool_maxsize=max_workers * 2
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def fetch_m3u_content(self, url):
        """Fetch M3U content from URL"""
        try:
            logging.info(f"Fetching M3U playlist from: {url}")
            response = self.session.get(url, timeout=15)
            response.raise_for_status()
            logging.info(f"✅ Successfully fetched M3U playlist")
            return response.text
        except Exception as e:
            logging.error(f"❌ Error fetching M3U: {e}")
            return None

    def parse_m3u_for_webpages(self, content):
        """Parse M3U content and extract webpage URLs and channel info"""
        channels = []
        lines = content.strip().split('\n')
        
        logging.info(f"Parsing {len(lines)} lines...")
        
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
        """Extract M3U8 URL from webpage with aggressive timeouts"""
        try:
            # Method 1: Check for direct redirects (fastest)
            m3u8_url = self.check_redirects(webpage_url)
            if m3u8_url:
                return m3u8_url
            
            # Method 2: Parse webpage content with timeout
            response = self.session.get(webpage_url, timeout=self.timeout, allow_redirects=True)
            if response.status_code != 200:
                return None
            
            # Limit content size to prevent memory issues
            content = response.text[:500000]  # First 500KB only
            
            # Method 3: Look for M3U8 URLs in content
            m3u8_url = self.find_m3u8_in_content(content, webpage_url)
            if m3u8_url:
                return m3u8_url
            
            return None
            
        except requests.Timeout:
            logging.debug(f"⏱️ Timeout: {channel_name}")
            return None
        except Exception as e:
            logging.debug(f"❌ Error {channel_name}: {str(e)[:50]}")
            return None

    def check_redirects(self, url):
        """Check if URL redirects directly to an M3U8 - with timeout"""
        try:
            response = self.session.head(url, timeout=5, allow_redirects=False)
            
            redirect_count = 0
            current_url = url
            
            while redirect_count < 5:  # Max 5 redirects
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
                    response = self.session.head(current_url, timeout=5, allow_redirects=False)
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
        # Simplified patterns for speed
        patterns = [
            r'["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'source[:\s]*["\']([^"\']*\.m3u8[^"\']*)["\']',
            r'src[=:\s]*["\']([^"\']*\.m3u8[^"\']*)["\']',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches[:5]:  # Check first 5 matches only
                url = match.strip()
                
                # Skip invalid URLs
                if any(skip in url.lower() for skip in ['javascript:', 'data:', '${', 'undefined', 'null']):
                    continue
                
                # Convert to absolute URL
                if url.startswith('//'):
                    url = 'https:' + url
                elif url.startswith('/'):
                    parsed = urlparse(base_url)
                    url = f"{parsed.scheme}://{parsed.netloc}{url}"
                elif not url.startswith('http'):
                    url = urljoin(base_url, url)
                
                return url  # Return first potentially valid URL
        
        return None

    def process_single_channel(self, channel):
        """Process a single channel with timeout"""
        webpage_url = channel.get('webpage_url')
        channel_name = channel.get('name', 'Unknown')
        
        if not webpage_url:
            return None
        
        try:
            m3u8_url = self.extract_m3u8_from_webpage(webpage_url, channel_name)
            
            if m3u8_url:
                channel['url'] = m3u8_url
                with self.lock:
                    self.processed_count += 1
                return channel
            else:
                with self.lock:
                    self.failed_count += 1
                return None
        except Exception as e:
            with self.lock:
                self.failed_count += 1
            return None

    def process_channels_parallel(self, channels):
        """Process channels in parallel with progress monitoring"""
        successful_channels = []
        total = len(channels)
        
        logging.info(f"🚀 Processing {total} channels with {self.max_workers} workers...")
        logging.info(f"⚙️ Timeout per channel: {self.timeout}s")
        
        start_time = time.time()
        last_log_time = start_time
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_channel = {
                executor.submit(self.process_single_channel, channel): channel 
                for channel in channels
            }
            
            # Process completed tasks with overall timeout
            completed = 0
            for future in as_completed(future_to_channel, timeout=1800):  # 30 min max
                try:
                    result = future.result(timeout=self.timeout + 5)
                    if result:
                        successful_channels.append(result)
                    
                    completed += 1
                    
                    # Log progress every 10 seconds
                    current_time = time.time()
                    if current_time - last_log_time >= 10:
                        elapsed = current_time - start_time
                        rate = completed / elapsed if elapsed > 0 else 0
                        eta = (total - completed) / rate if rate > 0 else 0
                        
                        logging.info(
                            f"📊 Progress: {completed}/{total} "
                            f"({completed/total*100:.1f}%) | "
                            f"✅ {self.processed_count} | "
                            f"❌ {self.failed_count} | "
                            f"⏱️ {elapsed:.0f}s | "
                            f"ETA: {eta:.0f}s"
                        )
                        last_log_time = current_time
                    
                except TimeoutError:
                    logging.warning(f"⏱️ Future timed out")
                    completed += 1
                except Exception as e:
                    logging.debug(f"Error in future: {e}")
                    completed += 1
        
        return successful_channels

    def save_to_json(self, channels, filename='updatedv3.json'):
        """Save channels to JSON file"""
        data = {
            'last_updated': datetime.utcnow().isoformat() + 'Z',
            'total_channels': len(channels),
            'extraction_method': 'fast_parallel_extractor_v3',
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
    logging.info("=" * 60)
    logging.info("🚀 Fast M3U8 Extractor (Limited to 1500 channels)")
    logging.info("=" * 60)
    
    # Initialize extractor with optimized settings
    extractor = FastM3U8Extractor(
        max_workers=10,  # More workers for speed
        timeout=10,      # Aggressive timeout
        max_channels=1500
    )
    
    # M3U URL
    m3u_url = "https://raw.githubusercontent.com/abusaeeidx/IPTV-Scraper-Zilla/refs/heads/main/hilaytv.m3u"
    
    try:
        # Step 1: Fetch and parse M3U
        logging.info("📥 Step 1/3: Fetching M3U playlist...")
        m3u_content = extractor.fetch_m3u_content(m3u_url)
        
        if not m3u_content:
            logging.error("Failed to fetch M3U content")
            sys.exit(1)
        
        # Step 2: Parse channels
        logging.info("📋 Step 2/3: Parsing channel list...")
        channels = extractor.parse_m3u_for_webpages(m3u_content)
        
        if not channels:
            logging.error("No channels found in M3U")
            sys.exit(1)
        
        # Step 3: Extract M3U8 URLs
        logging.info("⚡ Step 3/3: Extracting M3U8 URLs (parallel processing)...")
        start_time = time.time()
        
        successful_channels = extractor.process_channels_parallel(channels)
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Step 4: Save results
        logging.info("=" * 60)
        if successful_channels:
            extractor.save_to_json(successful_channels)
            
            # Print summary
            success_rate = (len(successful_channels) / len(channels)) * 100
            logging.info("🎉 EXTRACTION COMPLETE!")
            logging.info(f"📊 SUMMARY:")
            logging.info(f"   ⏱️  Processing time: {processing_time:.1f}s ({processing_time/60:.1f}m)")
            logging.info(f"   📺 Channels processed: {len(channels)}")
            logging.info(f"   ✅ Successful: {len(successful_channels)}")
            logging.info(f"   ❌ Failed: {len(channels) - len(successful_channels)}")
            logging.info(f"   📈 Success rate: {success_rate:.1f}%")
            logging.info(f"   ⚡ Speed: {len(channels)/processing_time:.1f} channels/sec")
            
            # Show some examples
            if len(successful_channels) >= 3:
                logging.info("🔗 Sample extracted URLs:")
                for i, channel in enumerate(successful_channels[:3]):
                    logging.info(f"   {i+1}. {channel['name'][:40]} -> {channel['url'][:60]}...")
        else:
            logging.error("❌ No M3U8 URLs were successfully extracted")
            # Still save empty file
            extractor.save_to_json([])
            sys.exit(1)
        
        logging.info("=" * 60)
        
    except KeyboardInterrupt:
        logging.info("\n⚠️ Process interrupted by user")
        sys.exit(1)
    except Exception as e:
        logging.error(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
