#!/usr/bin/env python3
"""
M3U8 Scraper Script
Extracts M3U8 playlist data and converts it to JSON format
"""

import requests
import json
import re
from datetime import datetime
import sys
import os

def parse_m3u8(content):
    """Parse M3U8 content and extract channel information"""
    channels = []
    lines = content.strip().split('\n')
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Look for #EXTINF lines (channel info)
        if line.startswith('#EXTINF:'):
            try:
                # Extract duration and attributes
                extinf_match = re.match(r'#EXTINF:([^,]*),(.+)', line)
                if extinf_match:
                    duration = extinf_match.group(1).strip()
                    title_info = extinf_match.group(2).strip()
                    
                    # Extract attributes from the EXTINF line
                    attributes = {}
                    
                    # Extract tvg-id
                    tvg_id_match = re.search(r'tvg-id="([^"]*)"', line)
                    if tvg_id_match:
                        attributes['tvg_id'] = tvg_id_match.group(1)
                    
                    # Extract tvg-name
                    tvg_name_match = re.search(r'tvg-name="([^"]*)"', line)
                    if tvg_name_match:
                        attributes['tvg_name'] = tvg_name_match.group(1)
                    
                    # Extract tvg-logo
                    tvg_logo_match = re.search(r'tvg-logo="([^"]*)"', line)
                    if tvg_logo_match:
                        attributes['tvg_logo'] = tvg_logo_match.group(1)
                    
                    # Extract group-title
                    group_title_match = re.search(r'group-title="([^"]*)"', line)
                    if group_title_match:
                        attributes['group_title'] = group_title_match.group(1)
                    
                    # Get the channel name (everything after the last comma)
                    channel_name = re.split(r',', line)[-1].strip()
                    if not channel_name or channel_name.startswith('tvg-'):
                        channel_name = title_info
                    
                    # Get the URL from the next line
                    if i + 1 < len(lines):
                        url = lines[i + 1].strip()
                        
                        # Only add if URL is valid
                        if url and not url.startswith('#'):
                            channel = {
                                'name': channel_name,
                                'url': url,
                                'duration': duration,
                                **attributes
                            }
                            channels.append(channel)
                            
                        i += 2  # Skip the URL line
                    else:
                        i += 1
                else:
                    i += 1
            except Exception as e:
                print(f"Error parsing line {i}: {line}")
                print(f"Error: {e}")
                i += 1
        else:
            i += 1
    
    return channels

def fetch_m3u8(url):
    """Fetch M3U8 content from URL"""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching M3U8: {e}")
        return None

def save_to_json(channels, filename='channels.json'):
    """Save channels data to JSON file"""
    data = {
        'last_updated': datetime.utcnow().isoformat() + 'Z',
        'total_channels': len(channels),
        'channels': channels
    }
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Successfully saved {len(channels)} channels to {filename}")
        return True
    except Exception as e:
        print(f"Error saving JSON: {e}")
        return False

def main():
    # M3U8 URL
    m3u8_url = "https://raw.githubusercontent.com/abusaeeidx/IPTV-Scraper-Zilla/refs/heads/main/hilaytv.m3u"
    
    print("Fetching M3U8 playlist...")
    content = fetch_m3u8(m3u8_url)
    
    if not content:
        print("Failed to fetch M3U8 content")
        sys.exit(1)
    
    print("Parsing M3U8 content...")
    channels = parse_m3u8(content)
    
    if not channels:
        print("No channels found in M3U8")
        sys.exit(1)
    
    print(f"Found {len(channels)} channels")
    
    # Save to JSON
    if save_to_json(channels):
        print("Script completed successfully")
    else:
        print("Failed to save JSON")
        sys.exit(1)

if __name__ == "__main__":
    main()
