import re
import pandas as pd
from datetime import datetime

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
                
        # Attempt to parse date flexibly
        try:
            # We'll keep date as string for now and let the DB handle it if needed,
            # or try a basic parse. 
            timestamp = date_str  # Simplified for MVP
        except Exception:
            timestamp = date_str
            
        messages.append({
            "timestamp": timestamp,
            "sender": sender.strip(),
            "message": message.strip()
        })
        
    return messages
