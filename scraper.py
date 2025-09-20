#!/usr/bin/env python3
"""
Advanced M3U8 Stream URL Extractor
This script:
1. Fetches M3U playlist from GitHub
2. Extracts webpage URLs from the M3U file
3. Visits each webpage to find embedded M3U8 stream URLs
4. Saves the actual streaming URLs to JSON
"""

import requests
import json
import re
from datetime import datetime
import sys
import time
from urllib.parse import urljoin, urlparse
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

class M3U8StreamExtractor:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
    def fetch_m3u_content(self, url):
        """Fetch M3U content from URL"""
        try:
            logging.info(f"Fetching M3U playlist from: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.exceptions.RequestException as e:
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
                    # Extract channel information from EXTINF line
                    channel_info = self.extract_channel_info(line)
                    
                    # Get the webpage URL from the next line
                    if i + 1 < len(lines):
                        webpage_url = lines[i + 1].strip()
                        
                        if webpage_url and not webpage_url.startswith('#'):
                            channel_info['webpage_url'] = webpage_url
                            channels.append(channel_info)
                            logging.info(f"Found channel: {channel_info.get('name', 'Unknown')} -> {webpage_url}")
                        
                        i += 2
                    else:
                        i += 1
                except Exception as e:
                    logging.warning(f"Error parsing EXTINF line {i}: {e}")
                    i += 1
            else:
                i += 1
        
        logging.info(f"Parsed {len(channels)} channels from M3U")
        return channels
    
    def extract_channel_info(self, extinf_line):
        """Extract channel information from EXTINF line"""
        channel_info = {}
        
        # Extract basic info
        extinf_match = re.match(r'#EXTINF:([^,]*),(.+)', extinf_line)
        if extinf_match:
            channel_info['duration'] = extinf_match.group(1).strip()
            title_part = extinf_match.group(2).strip()
        
        # Extract attributes
        attributes = {
            'tvg_id': r'tvg-id="([^"]*)"',
            'tvg_name': r'tvg-name="([^"]*)"', 
            'tvg_logo': r'tvg-logo="([^"]*)"',
            'group_title': r'group-title="([^"]*)"'
        }
        
        for attr, pattern in attributes.items():
            match = re.search(pattern, extinf_line)
            if match:
                channel_info[attr] = match.group(1)
        
        # Extract channel name (everything after the last comma, or use title part)
        name_parts = extinf_line.split(',')
        if len(name_parts) > 1:
            channel_name = name_parts[-1].strip()
            # Clean up the name (remove attributes that might be mixed in)
            channel_name = re.sub(r'tvg-[^=]*="[^"]*"\s*', '', channel_name).strip()
            if channel_name:
                channel_info['name'] = channel_name
        
        # Fallback name extraction
        if 'name' not in channel_info or not channel_info['name']:
            if 'tvg_name' in channel_info:
                channel_info['name'] = channel_info['tvg_name']
            else:
                channel_info['name'] = 'Unknown Channel'
        
        return channel_info
    
    def extract_m3u8_from_webpage(self, webpage_url, max_retries=3):
        """Extract M3U8 stream URL from webpage"""
        for attempt in range(max_retries):
            try:
                logging.info(f"Extracting M3U8 from webpage (attempt {attempt + 1}): {webpage_url}")
                
                # Add delay between requests to be respectful
                if attempt > 0:
                    time.sleep(2 ** attempt)
                
                response = self.session.get(webpage_url, timeout=30)
                response.raise_for_status()
                
                # Multiple patterns to find M3U8 URLs
                m3u8_patterns = [
                    r'["\']([^"\']*\.m3u8[^"\']*)["\']',
                    r'source["\s]*:["\s]*["\']([^"\']*\.m3u8[^"\']*)["\']',
                    r'src["\s]*=["\s]*["\']([^"\']*\.m3u8[^"\']*)["\']',
                    r'file["\s]*:["\s]*["\']([^"\']*\.m3u8[^"\']*)["\']',
                    r'url["\s]*:["\s]*["\']([^"\']*\.m3u8[^"\']*)["\']',
                    r'stream["\s]*:["\s]*["\']([^"\']*\.m3u8[^"\']*)["\']',
                    r'hlsUrl["\s]*:["\s]*["\']([^"\']*\.m3u8[^"\']*)["\']',
                    r'playlist["\s]*:["\s]*["\']([^"\']*\.m3u8[^"\']*)["\']'
                ]
                
                content = response.text
                found_urls = set()
                
                for pattern in m3u8_patterns:
                    matches = re.findall(pattern, content, re.IGNORECASE)
                    for match in matches:
                        # Clean and validate URL
                        m3u8_url = match.strip()
                        
                        # Skip if it's a variable or placeholder
                        if any(skip in m3u8_url.lower() for skip in ['${', '{', 'undefined', 'null', 'var ', 'let ', 'const ']):
                            continue
                            
                        # Convert relative URLs to absolute
                        if m3u8_url.startswith('//'):
                            m3u8_url = 'https:' + m3u8_url
                        elif m3u8_url.startswith('/'):
                            base_url = f"{urlparse(webpage_url).scheme}://{urlparse(webpage_url).netloc}"
                            m3u8_url = urljoin(base_url, m3u8_url)
                        elif not m3u8_url.startswith('http'):
                            m3u8_url = urljoin(webpage_url, m3u8_url)
                        
                        found_urls.add(m3u8_url)
                
                if found_urls:
                    # Return the first valid M3U8 URL found
                    for url in found_urls:
                        if self.validate_m3u8_url(url):
                            logging.info(f"Found valid M3U8: {url}")
                            return url
                    
                    # If no valid URLs, return the first one anyway
                    first_url = list(found_urls)[0]
                    logging.warning(f"No valid M3U8 found, using first match: {first_url}")
                    return first_url
                
                logging.warning(f"No M3U8 URLs found in webpage: {webpage_url}")
                return None
                
            except requests.exceptions.RequestException as e:
                logging.warning(f"Error fetching webpage {webpage_url} (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    logging.error(f"Failed to fetch webpage after {max_retries} attempts: {webpage_url}")
                    return None
            except Exception as e:
                logging.error(f"Unexpected error extracting M3U8 from {webpage_url}: {e}")
                return None
        
        return None
    
    def validate_m3u8_url(self, url):
        """Validate if M3U8 URL is accessible"""
        try:
            response = self.session.head(url, timeout=10)
            return response.status_code == 200
        except:
            return False
    
    def process_channels(self, channels):
        """Process all channels to extract M3U8 URLs"""
        successful_channels = []
        failed_channels = []
        
        total = len(channels)
        logging.info(f"Starting to process {total} channels...")
        
        for i, channel in enumerate(channels, 1):
            logging.info(f"Processing channel {i}/{total}: {channel.get('name', 'Unknown')}")
            
            webpage_url = channel.get('webpage_url')
            if not webpage_url:
                logging.warning(f"No webpage URL for channel: {channel.get('name')}")
                failed_channels.append(channel)
                continue
            
            # Extract M3U8 URL from webpage
            m3u8_url = self.extract_m3u8_from_webpage(webpage_url)
            
            if m3u8_url:
                # Update channel with actual stream URL
                channel['url'] = m3u8_url
                # Keep the original webpage URL for reference
                channel['webpage_url'] = webpage_url
                successful_channels.append(channel)
                logging.info(f"✅ Success: {channel.get('name')} -> {m3u8_url}")
            else:
                failed_channels.append(channel)
                logging.error(f"❌ Failed: {channel.get('name')} -> {webpage_url}")
            
            # Add delay between requests to be respectful
            time.sleep(1)
        
        logging.info(f"Processing complete: {len(successful_channels)} successful, {len(failed_channels)} failed")
        return successful_channels, failed_channels
    
    def save_to_json(self, channels, filename='channels.json'):
        """Save channels data to JSON file"""
        data = {
            'last_updated': datetime.utcnow().isoformat() + 'Z',
            'total_channels': len(channels),
            'successful_extractions': len(channels),
            'extraction_timestamp': datetime.utcnow().isoformat() + 'Z',
            'channels': channels
        }
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logging.info(f"Successfully saved {len(channels)} channels to {filename}")
            return True
        except Exception as e:
            logging.error(f"Error saving JSON: {e}")
            return False

def main():
    # Initialize extractor
    extractor = M3U8StreamExtractor()
    
    # M3U URL from GitHub
    m3u_url = "https://raw.githubusercontent.com/abusaeeidx/IPTV-Scraper-Zilla/refs/heads/main/hilaytv.m3u"
    
    # Step 1: Fetch M3U content
    logging.info("=== Step 1: Fetching M3U playlist ===")
    m3u_content = extractor.fetch_m3u_content(m3u_url)
    
    if not m3u_content:
        logging.error("Failed to fetch M3U content")
        sys.exit(1)
    
    # Step 2: Parse M3U to get webpage URLs
    logging.info("=== Step 2: Parsing M3U for webpage URLs ===")
    channels = extractor.parse_m3u_for_webpages(m3u_content)
    
    if not channels:
        logging.error("No channels found in M3U")
        sys.exit(1)
    
    # Step 3: Extract M3U8 URLs from webpages
    logging.info("=== Step 3: Extracting M3U8 URLs from webpages ===")
    successful_channels, failed_channels = extractor.process_channels(channels)
    
    if not successful_channels:
        logging.error("No M3U8 URLs were successfully extracted")
        sys.exit(1)
    
    # Step 4: Save results
    logging.info("=== Step 4: Saving results ===")
    if extractor.save_to_json(successful_channels):
        logging.info("✅ Script completed successfully!")
        logging.info(f"📊 Summary:")
        logging.info(f"   - Total channels in M3U: {len(channels)}")
        logging.info(f"   - Successfully extracted: {len(successful_channels)}")
        logging.info(f"   - Failed extractions: {len(failed_channels)}")
        
        if failed_channels:
            logging.warning("⚠️  Failed channels:")
            for channel in failed_channels[:5]:  # Show first 5 failed
                logging.warning(f"   - {channel.get('name', 'Unknown')}: {channel.get('webpage_url', 'No URL')}")
            if len(failed_channels) > 5:
                logging.warning(f"   ... and {len(failed_channels) - 5} more")
    else:
        logging.error("Failed to save JSON file")
        sys.exit(1)

if __name__ == "__main__":
    main()
