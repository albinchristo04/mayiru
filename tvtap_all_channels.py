#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TVTap All Channels Fetcher - Extended version for all countries
Fetches ALL TV channels from TVTap and outputs as JSON
"""

import requests
import json
import sys
from base64 import b64decode, b64encode
from binascii import a2b_hex
from datetime import datetime
import time

def log(message):
    """Print log messages to stderr"""
    print(f"[INFO] {message}", file=sys.stderr)

def payload():
    """Generate encrypted payload for TVTap API requests"""
    try:
        from Crypto.Cipher import PKCS1_v1_5 as Cipher_PKCS1_v1_5
        from Crypto.PublicKey import RSA
        
        _pubkey = RSA.importKey(
            a2b_hex(
                "30819f300d06092a864886f70d010101050003818d003081890281"
                "8100bfa5514aa0550688ffde568fd95ac9130fcdd8825bdecc46f1"
                "8f6c6b440c3685cc52ca03111509e262dba482d80e977a938493ae"
                "aa716818efe41b84e71a0d84cc64ad902e46dbea2ec61071958826"
                "4093e20afc589685c08f2d2ae70310b92c04f9b4c27d79c8b5dbb9"
                "bd8f2003ab6a251d25f40df08b1c1588a4380a1ce8030203010001"
            )
        )
        _msg = a2b_hex(
            "7b224d4435223a22695757786f45684237686167747948392b58563052513d3d5c6e222c22534"
            "84131223a2242577761737941713841327678435c2f5450594a74434a4a544a66593d5c6e227d"
        )
        cipher = Cipher_PKCS1_v1_5.new(_pubkey)
        ret64 = b64encode(cipher.encrypt(_msg))
        return ret64
    except ImportError:
        log("ERROR: pycryptodome not installed. Install with: pip install pycryptodome")
        sys.exit(1)

def get_stream_url(channel_id):
    """
    Get stream URL for a specific channel
    Returns the decrypted M3U8 URL or None if failed
    """
    try:
        from pyDes import des, PAD_PKCS5
    except ImportError:
        log("WARNING: pyDes not available, skipping stream resolution")
        return None
    
    try:
        payload_data = payload()
        
        r = requests.post(
            'https://rocktalk.net/tv/index.php?case=get_channel_link_with_token_latest',
            headers={"app-token": "37a6259cc0c1dae299a7866489dff0bd"},
            data={"payload": payload_data, "channel_id": channel_id, "username": "603803577"},
            timeout=10
        )
        
        if r.status_code != 200:
            return None
        
        response_json = r.json()
        
        if "msg" not in response_json:
            return None
        
        msgRes = response_json["msg"]
        
        if isinstance(msgRes, str):
            return None
        
        if not isinstance(msgRes, dict) or "channel" not in msgRes:
            return None
        
        # Decrypt stream URL
        key = b"98221122"
        jch = msgRes["channel"][0]
        
        for stream_key in jch.keys():
            if "stream" in stream_key or "chrome_cast" in stream_key:
                d = des(key)
                link = d.decrypt(b64decode(jch[stream_key]), padmode=PAD_PKCS5)
                
                if link:
                    link = link.decode("utf-8")
                    if link and link != "dummytext":
                        return link
        
        return None
        
    except Exception as e:
        log(f"Error getting stream for channel {channel_id}: {e}")
        return None

def fetch_all_channels_from_api():
    """Fetch ALL channels from TVTap API"""
    user_agent = 'USER-AGENT-tvtap-APP-V2'
    
    headers = {
        'User-Agent': user_agent,
        'app-token': '37a6259cc0c1dae299a7866489dff0bd',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Host': 'taptube.net',
    }
    
    try:
        payload_data = payload()
        log("Sending request to TVTap API for all channels...")
        
        r = requests.post(
            'https://rocktalk.net/tv/index.php?case=get_all_channels',
            headers=headers,
            data={"payload": payload_data, "username": "603803577"},
            timeout=15
        )
        
        log(f"Response status: {r.status_code}")
        
        if r.status_code != 200:
            log(f"HTTP error: {r.status_code}")
            return [], "error"
        
        response_json = r.json()
        
        # Check for errors in response
        if isinstance(response_json, dict) and "msg" in response_json:
            msg = response_json["msg"]
            
            if isinstance(msg, str) and ("error" in msg.lower() or "occured" in msg.lower()):
                log(f"API error: {msg}")
                return [], "error"
            
            if isinstance(msg, dict) and "channels" in msg:
                channels = msg["channels"]
                log(f"Found {len(channels)} total channels from API")
                
                # Extract all channels
                all_channels = []
                for channel in channels:
                    if isinstance(channel, dict):
                        all_channels.append({
                            "id": channel.get("pk_id"),
                            "name": channel.get("channel_name"),
                            "country": channel.get("country"),
                            "thumbnail": channel.get("img"),
                            "stream_url": None  # Will be populated later if requested
                        })
                
                log(f"Extracted {len(all_channels)} channels")
                return all_channels, "api"
        
        log("Unexpected API response structure")
        return [], "error"
        
    except Exception as e:
        log(f"Error fetching from API: {e}")
        return [], "error"

def group_channels_by_country(channels):
    """Group channels by country code"""
    grouped = {}
    
    for channel in channels:
        country = channel.get("country", "Unknown")
        if country not in grouped:
            grouped[country] = []
        grouped[country].append(channel)
    
    return grouped

def main():
    """Main function to fetch all channels and output JSON"""
    import argparse
    
    parser = argparse.ArgumentParser(description='TVTap All Channels Fetcher')
    parser.add_argument('--resolve-streams', action='store_true', 
                       help='Also fetch stream URLs (slower, requires pyDes)')
    parser.add_argument('--country', type=str, 
                       help='Filter by specific country code (e.g., IT, US, UK)')
    parser.add_argument('--limit', type=int, 
                       help='Limit number of channels to process')
    parser.add_argument('--stream-delay', type=float, default=0.5,
                       help='Delay between stream requests in seconds (default: 0.5)')
    
    args = parser.parse_args()
    
    log("Starting TVTap all channels fetch...")
    
    channels, source = fetch_all_channels_from_api()
    
    if not channels:
        log("No channels retrieved!")
        sys.exit(1)
    
    # Filter by country if specified
    if args.country:
        channels = [ch for ch in channels if ch.get("country") == args.country.upper()]
        log(f"Filtered to {len(channels)} channels for country: {args.country}")
    
    # Limit if specified
    if args.limit:
        channels = channels[:args.limit]
        log(f"Limited to {args.limit} channels")
    
    # Resolve streams if requested
    if args.resolve_streams:
        log("Resolving stream URLs (this may take a while)...")
        
        for i, channel in enumerate(channels, 1):
            channel_id = channel.get("id")
            channel_name = channel.get("name")
            
            log(f"[{i}/{len(channels)}] Resolving: {channel_name} (ID: {channel_id})")
            
            try:
                stream_url = get_stream_url(channel_id)
                channel["stream_url"] = stream_url
                
                if stream_url:
                    log(f"  ✓ Stream found")
                else:
                    log(f"  ✗ No stream")
                    
            except Exception as e:
                log(f"  ✗ Error: {e}")
                channel["stream_url"] = None
            
            # Delay to avoid overwhelming the server
            if i < len(channels):
                time.sleep(args.stream_delay)
    
    # Group channels by country
    grouped_channels = group_channels_by_country(channels)
    
    # Sort channels within each country by name
    for country in grouped_channels:
        grouped_channels[country] = sorted(
            grouped_channels[country], 
            key=lambda x: x.get("name", "")
        )
    
    # Calculate statistics
    total_channels = len(channels)
    channels_with_streams = sum(1 for ch in channels if ch.get("stream_url"))
    countries = sorted(grouped_channels.keys())
    
    # Create output JSON
    output = {
        "metadata": {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "source": source,
            "total_channels": total_channels,
            "countries_count": len(countries),
            "countries": countries,
            "streams_resolved": args.resolve_streams,
            "channels_with_streams": channels_with_streams if args.resolve_streams else None
        },
        "channels_by_country": grouped_channels,
        "channels_flat": channels
    }
    
    # Output to stdout
    print(json.dumps(output, ensure_ascii=False, indent=2))
    
    log(f"Successfully fetched {total_channels} channels from {source}")
    log(f"Countries: {len(countries)}")
    if args.resolve_streams:
        log(f"Channels with streams: {channels_with_streams}/{total_channels}")
    log("Done!")

if __name__ == "__main__":
    main()
