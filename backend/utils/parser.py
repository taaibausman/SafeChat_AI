import re
from datetime import datetime, timezone

def parse_whatsapp_chat(file_content: str) -> list[dict]:
    """
    Parses a standard WhatsApp export file (.txt).
    Handles standard formats like:
    [12/5/26, 9:00 PM] Sara: I will destroy you
    or
    12/5/26, 9:00 PM - Sara: I will destroy you
    """
    messages = []
    
    # Common regex patterns for WhatsApp dates
    pattern_bracket = re.compile(r"^\[(.*?)\] (.*?): (.*)$")
    pattern_dash = re.compile(r"^(.*?) - (.*?): (.*)$")
    
    lines = file_content.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        match = pattern_bracket.match(line)
        if match:
            date_str, sender, message = match.groups()
        else:
            match = pattern_dash.match(line)
            if match:
                date_str, sender, message = match.groups()
            else:
                # Might be a multiline message continuing from previous
                if messages:
                    messages[-1]["message"] += "\n" + line
                continue
                
        # Attempt to parse date flexibly and normalize to datetime
        timestamp = None
        for fmt in ["%m/%d/%y, %I:%M %p", "%d/%m/%y, %I:%M %p", "%Y-%m-%d, %H:%M", "%m/%d/%Y, %I:%M %p", "%d/%m/%Y, %I:%M %p"]:
            try:
                timestamp = datetime.strptime(date_str, fmt)
                break
            except Exception:
                continue
        if timestamp is None:
            # If we couldn't parse the timestamp, leave it as None
            timestamp = None
        else:
            # Normalize to UTC if no timezone info present
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            
        messages.append({
            "timestamp": timestamp,
            "sender": sender.strip(),
            "message": message.strip()
        })
        
    return messages
