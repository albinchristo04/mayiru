import requests
import json
import re
from datetime import datetime
from typing import List, Dict

def fetch_sports_data(url: str) -> str:
    """Fetch the sports schedule from the URL"""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching data: {e}")
        return ""

def parse_sports_events(content: str) -> Dict[str, List[Dict]]:
    """Parse the sports events from the text content"""
    events_by_day = {}
    current_day = None
    
    lines = content.split('\n')
    
    for line in lines:
        line = line.strip()
        
        # Skip empty lines and header lines
        if not line or line.startswith('=') or line.startswith('INFO:') or \
           line.startswith('ANY INFO') or line.startswith('24/7') or \
           line.startswith('IMPORTANT:') or line.startswith('*(W)') or \
           'READ!' in line or 'UPDATE' in line or line.startswith('HD') or \
           line.startswith('BR'):
            continue
        
        # Check if this is a day header (SATURDAY, SUNDAY, MONDAY, etc.)
        if line.isupper() and len(line.split()) == 1 and line.isalpha():
            current_day = line
            events_by_day[current_day] = []
            continue
        
        # Parse event lines (format: TIME   EVENT | URL)
        if '|' in line and current_day:
            parts = line.split('|')
            if len(parts) == 2:
                event_info = parts[0].strip()
                url = parts[1].strip()
                
                # Extract time and event name
                match = re.match(r'^(\d{2}:\d{2})\s+(.+)$', event_info)
                if match:
                    time = match.group(1)
                    event_name = match.group(2).strip()
                    
                    # Check if this event already exists for this day
                    existing_event = None
                    for event in events_by_day[current_day]:
                        if event['time'] == time and event['event'] == event_name:
                            existing_event = event
                            break
                    
                    if existing_event:
                        # Add URL to existing event
                        existing_event['streams'].append(url)
                    else:
                        # Create new event
                        events_by_day[current_day].append({
                            'time': time,
                            'event': event_name,
                            'streams': [url]
                        })
    
    return events_by_day

def save_to_json(data: Dict, filename: str = 'sports_events.json'):
    """Save the parsed data to a JSON file"""
    output = {
        'last_updated': datetime.utcnow().isoformat() + 'Z',
        'events': data
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"Data saved to {filename}")
    print(f"Total days: {len(data)}")
    total_events = sum(len(events) for events in data.values())
    print(f"Total events: {total_events}")

def main():
    url = "https://sportsonline.cx/prog.txt"
    
    print("Fetching sports schedule...")
    content = fetch_sports_data(url)
    
    if not content:
        print("Failed to fetch data")
        return
    
    print("Parsing events...")
    events = parse_sports_events(content)
    
    print("Saving to JSON...")
    save_to_json(events)
    
    print("Done!")

if __name__ == "__main__":
    main()
