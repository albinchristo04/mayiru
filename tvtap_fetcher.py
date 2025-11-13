#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TVTap Channel Fetcher - Standalone version for GitHub Actions
Fetches Italian TV channels from TVTap and outputs as JSON
"""

import requests
import json
import sys
from base64 import b64decode, b64encode
from binascii import a2b_hex
from datetime import datetime

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

def get_static_channels():
    """Return static list of Italian channels as fallback"""
    return [
        {"id": "813", "name": "Baby TV", "country": "IT"},
        {"id": "812", "name": "Boomerang", "country": "IT"},
        {"id": "438", "name": "Canale 5", "country": "IT"},
        {"id": "439", "name": "Cartoon Network", "country": "IT"},
        {"id": "810", "name": "Classica", "country": "IT"},
        {"id": "700", "name": "Discovery", "country": "IT"},
        {"id": "731", "name": "Discovery Real Time", "country": "IT"},
        {"id": "737", "name": "Discovery Science", "country": "IT"},
        {"id": "713", "name": "Discovery Travel & Living", "country": "IT"},
        {"id": "830", "name": "Dazn 1", "country": "IT"},
        {"id": "819", "name": "Dazn 10", "country": "IT"},
        {"id": "820", "name": "Dazn 11", "country": "IT"},
        {"id": "768", "name": "Dazn 2", "country": "IT"},
        {"id": "769", "name": "Dazn 3", "country": "IT"},
        {"id": "770", "name": "Dazn 4", "country": "IT"},
        {"id": "771", "name": "Dazn 5", "country": "IT"},
        {"id": "815", "name": "Dazn 6", "country": "IT"},
        {"id": "816", "name": "Dazn 7", "country": "IT"},
        {"id": "817", "name": "Dazn 8", "country": "IT"},
        {"id": "818", "name": "Dazn 9", "country": "IT"},
        {"id": "811", "name": "Dea Kids", "country": "IT"},
        {"id": "711", "name": "Euro Sport", "country": "IT"},
        {"id": "712", "name": "Euro Sport 2", "country": "IT"},
        {"id": "442", "name": "History", "country": "IT"},
        {"id": "739", "name": "Inter Tv", "country": "IT"},
        {"id": "443", "name": "Italia 1", "country": "IT"},
        {"id": "466", "name": "La 7", "country": "IT"},
        {"id": "794", "name": "Lazio Style", "country": "IT"},
        {"id": "718", "name": "Mediaset 2", "country": "IT"},
        {"id": "749", "name": "Mediaset Extra", "country": "IT"},
        {"id": "797", "name": "MediaSet Focus", "country": "IT"},
        {"id": "729", "name": "Milan tv", "country": "IT"},
        {"id": "801", "name": "Nove", "country": "IT"},
        {"id": "791", "name": "Nicklodean", "country": "IT"},
        {"id": "426", "name": "Rai 1", "country": "IT"},
        {"id": "427", "name": "Rai 2", "country": "IT"},
        {"id": "428", "name": "Rai 3", "country": "IT"},
        {"id": "429", "name": "Rai 4", "country": "IT"},
        {"id": "430", "name": "Rai 5", "country": "IT"},
        {"id": "800", "name": "Rai Movie", "country": "IT"},
        {"id": "698", "name": "Rai news 24", "country": "IT"},
        {"id": "784", "name": "Rai Premium", "country": "IT"},
        {"id": "465", "name": "Rete 4", "country": "IT"},
        {"id": "792", "name": "TG Com 24", "country": "IT"},
        {"id": "809", "name": "TV 2000", "country": "IT"},
        {"id": "798", "name": "TV8", "country": "IT"},
        {"id": "776", "name": "Comedy Central", "country": "IT"},
        {"id": "710", "name": "Sky Atlantic", "country": "IT"},
        {"id": "582", "name": "Sky Calcio 1", "country": "IT"},
        {"id": "583", "name": "Sky Calcio 2", "country": "IT"},
        {"id": "706", "name": "Sky Calcio 3", "country": "IT"},
        {"id": "707", "name": "Sky Calcio 4", "country": "IT"},
        {"id": "708", "name": "Sky Calcio 5", "country": "IT"},
        {"id": "709", "name": "Sky Calcio 6", "country": "IT"},
        {"id": "876", "name": "Sky Calcio 7", "country": "IT"},
        {"id": "877", "name": "Sky Calcio 8", "country": "IT"},
        {"id": "878", "name": "Sky Calcio 9", "country": "IT"},
        {"id": "590", "name": "Sky Cinema Action", "country": "IT"},
        {"id": "589", "name": "Sky Cinema Collection", "country": "IT"},
        {"id": "586", "name": "Sky Cinema Comedy", "country": "IT"},
        {"id": "587", "name": "Sky Cinema Due", "country": "IT"},
        {"id": "588", "name": "Sky Cinema Family", "country": "IT"},
        {"id": "591", "name": "Sky Cinema Romance", "country": "IT"},
        {"id": "584", "name": "Sky Cinema UNO", "country": "IT"},
        {"id": "629", "name": "Sky Sport 24", "country": "IT"},
        {"id": "579", "name": "Sky Sport Arena", "country": "IT"},
        {"id": "705", "name": "Sky Sport Calcio", "country": "IT"},
        {"id": "581", "name": "Sky Sport F1", "country": "IT"},
        {"id": "580", "name": "Sky Sport Football", "country": "IT"},
        {"id": "668", "name": "Sky Sport Motogp", "country": "IT"},
        {"id": "704", "name": "Sky Sport NBA", "country": "IT"},
        {"id": "578", "name": "Sky Sport Uno", "country": "IT"},
        {"id": "592", "name": "Sky TG24", "country": "IT"},
        {"id": "593", "name": "Sky Uno", "country": "IT"}
    ]

def fetch_channels_from_api():
    """Fetch Italian channels from TVTap API"""
    user_agent = 'USER-AGENT-tvtap-APP-V2'
    
    headers = {
        'User-Agent': user_agent,
        'app-token': '37a6259cc0c1dae299a7866489dff0bd',
        'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        'Host': 'taptube.net',
    }
    
    try:
        payload_data = payload()
        log("Sending request to TVTap API...")
        
        r = requests.post(
            'https://rocktalk.net/tv/index.php?case=get_all_channels',
            headers=headers,
            data={"payload": payload_data, "username": "603803577"},
            timeout=15
        )
        
        log(f"Response status: {r.status_code}")
        
        if r.status_code != 200:
            log(f"HTTP error: {r.status_code}, using static list")
            return get_static_channels(), "static"
        
        response_json = r.json()
        
        # Check for errors in response
        if isinstance(response_json, dict) and "msg" in response_json:
            msg = response_json["msg"]
            
            if isinstance(msg, str) and ("error" in msg.lower() or "occured" in msg.lower()):
                log(f"API error: {msg}, using static list")
                return get_static_channels(), "static"
            
            if isinstance(msg, dict) and "channels" in msg:
                channels = msg["channels"]
                log(f"Found {len(channels)} total channels from API")
                
                # Filter Italian channels
                italian_channels = []
                for channel in channels:
                    if isinstance(channel, dict) and channel.get("country") == "IT":
                        italian_channels.append({
                            "id": channel.get("pk_id"),
                            "name": channel.get("channel_name"),
                            "country": channel.get("country"),
                            "thumbnail": channel.get("img")
                        })
                
                log(f"Filtered {len(italian_channels)} Italian channels")
                
                if italian_channels:
                    return italian_channels, "api"
                else:
                    log("No Italian channels found in API response, using static list")
                    return get_static_channels(), "static"
        
        log("Unexpected API response structure, using static list")
        return get_static_channels(), "static"
        
    except Exception as e:
        log(f"Error fetching from API: {e}, using static list")
        return get_static_channels(), "static"

def main():
    """Main function to fetch channels and output JSON"""
    log("Starting TVTap channel fetch...")
    
    channels, source = fetch_channels_from_api()
    
    # Sort channels by name
    channels_sorted = sorted(channels, key=lambda x: x.get("name", ""))
    
    # Create output JSON
    output = {
        "metadata": {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "source": source,
            "total_channels": len(channels_sorted),
            "country": "IT"
        },
        "channels": channels_sorted
    }
    
    # Output to stdout
    print(json.dumps(output, ensure_ascii=False, indent=2))
    
    log(f"Successfully fetched {len(channels_sorted)} channels from {source}")
    log("Done!")

if __name__ == "__main__":
    main()
