import os
import requests
from dotenv import load_dotenv
import xml.etree.ElementTree as ET
from datetime import datetime
import time
from collections import defaultdict

# Load environment variables from .env file
load_dotenv()

# Get API credentials from environment variables
API_KEY = os.getenv("NAMECHEAP_API_KEY")
API_USER = os.getenv("NAMECHEAP_USERNAME")
CLIENT_IP = os.getenv("CLIENT_IP")

def get_domains():
    """
    Fetch the list of domains from Namecheap API based on the provided Go code structure
    """
    url = "https://api.namecheap.com/xml.response"
    
    # Parameters based on Go code structure
    params = {
        "ApiUser": API_USER,
        "ApiKey": API_KEY,
        "UserName": API_USER,
        "Command": "namecheap.domains.getList",
        "ClientIp": CLIENT_IP,
        "ListType": "ALL",  # Allowed values: ALL, EXPIRING, EXPIRED
        "Page": "1",
        "PageSize": "100",  # Maximum allowed value
        "SortBy": "EXPIREDATE"  # Sort by expiration date
    }
    
    print("Making API request with parameters:")
    for key, value in params.items():
        if key == "ApiKey":
            print(f"{key}: {'*' * 8}")  # Mask the API key
        else:
            print(f"{key}: {value}")
    
    response = requests.get(url, params=params)
    
    print(f"\nAPI Response Status Code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        print(response.text)
        return []
    
    # Save the response for debugging
    with open("api_response.xml", "w") as f:
        f.write(response.text)
    print("Response saved to api_response.xml for debugging")
    
    # Parse XML response with namespace awareness
    root = ET.fromstring(response.text)
    
    # Register the namespace
    ns = {"nc": "http://api.namecheap.com/xml.response"}
    
    # Check if the command was successful
    status = root.attrib.get("Status")
    if status != "OK":
        errors = root.findall(".//nc:Errors/nc:Error", ns)
        if errors:
            for error in errors:
                number = error.attrib.get("Number", "Unknown")
                print(f"API Error {number}: {error.text}")
        return []
    
    domains = []
    # Extract domain information based on the Go struct using namespace
    domain_elements = root.findall(".//nc:CommandResponse/nc:DomainGetListResult/nc:Domain", ns)
    
    print(f"Found {len(domain_elements)} domains in response")
    
    for domain in domain_elements:
        domain_info = {
            "ID": domain.attrib.get("ID"),
            "name": domain.attrib.get("Name"),
            "user": domain.attrib.get("User"),
            "created": domain.attrib.get("Created"),
            "expires": domain.attrib.get("Expires"),
            "is_expired": domain.attrib.get("IsExpired") == "true",
            "is_locked": domain.attrib.get("IsLocked") == "true",
            "auto_renew": domain.attrib.get("AutoRenew") == "true",
            "whois_guard": domain.attrib.get("WhoisGuard"),
            "is_premium": domain.attrib.get("IsPremium") == "true",
            "is_our_dns": domain.attrib.get("IsOurDNS") == "true",
        }
        domains.append(domain_info)
    
    # Check paging information
    paging = root.find(".//nc:CommandResponse/nc:Paging", ns)
    if paging is not None:
        total_items = paging.findtext("nc:TotalItems", "Unknown", ns)
        current_page = paging.findtext("nc:CurrentPage", "Unknown", ns)
        page_size = paging.findtext("nc:PageSize", "Unknown", ns)
        print(f"Paging: Total Items: {total_items}, Current Page: {current_page}, Page Size: {page_size}")
    
    return domains

def parse_date(date_str):
    """Parse date from Namecheap API format"""
    try:
        # Check if the date string is provided
        if not date_str:
            return None
        
        # Handle multiple possible date formats
        for fmt in ["%m/%d/%Y", "%m/%d/%y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        # If none of the formats match
        print(f"Warning: Unable to parse date: {date_str}")
        return None
    except Exception as e:
        print(f"Error parsing date {date_str}: {e}")
        return None

def display_domains(domains):
    """
    Display domains and their renewal dates in the terminal
    """
    if not domains:
        print("No domains found. Please check your API credentials and parameters.")
        return
    
    print(f"\nTotal domains: {len(domains)}")
    print(f"\n{'Domain Name':<30} {'Expiry Date':<20} {'Created Date':<20} {'Auto Renew':<12} {'Is Locked':<10} {'WHOIS Guard':<15}")
    print("-" * 120)
    
    # Sort domains by expiry date
    sorted_domains = []
    for domain in domains:
        # Add parsed expiry date for sorting
        domain["expiry_date_obj"] = parse_date(domain["expires"])
        if domain["expiry_date_obj"]:
            sorted_domains.append(domain)
        else:
            # Still include domains with unparseable dates, but at the end
            sorted_domains.append(domain)
    
    # Sort only the ones with valid dates
    valid_dates = [d for d in sorted_domains if d["expiry_date_obj"] is not None]
    invalid_dates = [d for d in sorted_domains if d["expiry_date_obj"] is None]
    
    sorted_domains = sorted(valid_dates, key=lambda x: x["expiry_date_obj"]) + invalid_dates
    
    today = datetime.now()
    
    for domain in sorted_domains:
        expiry_date = domain["expires"] if domain["expires"] else "N/A"
        created_date = domain["created"] if domain["created"] else "N/A"
        
        # Calculate days until expiry
        days_left = ""
        if domain["expiry_date_obj"]:
            delta = domain["expiry_date_obj"] - today
            days_left = f"({delta.days} days left)"
            
            # Highlight domains expiring soon
            if 0 < delta.days <= 30:
                expiry_date = f"{expiry_date} {days_left} - RENEW SOON!"
            elif delta.days <= 0:
                expiry_date = f"{expiry_date} - EXPIRED!"
            else:
                expiry_date = f"{expiry_date} {days_left}"
        
        print(f"{domain['name']:<30} {expiry_date:<20} {created_date:<20} "
              f"{'Yes' if domain['auto_renew'] else 'No':<12} "
              f"{'Yes' if domain['is_locked'] else 'No':<10} "
              f"{domain['whois_guard']:<15}")
    
    # Show upcoming renewals
    print("\n--- Upcoming Renewals (next 90 days) ---")
    upcoming = [d for d in sorted_domains 
                if d["expiry_date_obj"] is not None 
                and 0 < (d["expiry_date_obj"] - today).days <= 90]
    
    if upcoming:
        print(f"\n{'Domain Name':<30} {'Expiry Date':<20} {'Days Left':<10} {'Auto Renew'}")
        print("-" * 75)
        
        for domain in upcoming:
            days_left = (domain["expiry_date_obj"] - today).days
            print(f"{domain['name']:<30} {domain['expires']:<20} {days_left:<10} {'Yes' if domain['auto_renew'] else 'No'}")
    else:
        print("No domains expiring in the next 90 days.")
    
    # Domain statistics
    print("\n--- Domain Statistics ---")
    total = len(domains)
    auto_renew = sum(1 for d in domains if d["auto_renew"])
    locked = sum(1 for d in domains if d["is_locked"])
    whois_guard_enabled = sum(1 for d in domains if d["whois_guard"] == "ENABLED")
    
    print(f"Total domains: {total}")
    print(f"Auto-renew enabled: {auto_renew} ({auto_renew/total*100:.1f}% of all domains)")
    print(f"Locked domains: {locked} ({locked/total*100:.1f}% of all domains)")
    print(f"WHOIS guard enabled: {whois_guard_enabled} ({whois_guard_enabled/total*100:.1f}% of all domains)")
    
    # Calendar year view
    print("\n--- Domain Renewal Calendar ---")
    
    # Group domains by month and year of expiry
    domains_by_month = defaultdict(list)
    
    # Map of month names to their numeric values for sorting
    month_map = {
        "January": 1, "February": 2, "March": 3, "April": 4, 
        "May": 5, "June": 6, "July": 7, "August": 8, 
        "September": 9, "October": 10, "November": 11, "December": 12
    }
    
    for domain in sorted_domains:
        if domain["expiry_date_obj"]:
            month_year = domain["expiry_date_obj"].strftime("%B %Y")  # e.g., "November 2025"
            domains_by_month[month_year].append(domain)
    
    # Sort the months chronologically
    def month_year_key(month_year_str):
        # Split the string into month and year
        parts = month_year_str.split()
        if len(parts) != 2:
            return (9999, 13)  # Invalid format, place at the end
        
        month_name, year_str = parts
        
        try:
            # Convert year to integer
            year = int(year_str)
            # Get month number from the map
            month_num = month_map.get(month_name, 13)  # Default to 13 (beyond December) if not found
            return (year, month_num)
        except (ValueError, KeyError):
            return (9999, 13)  # Invalid format, place at the end
    
    # Print domains by month in chronological order
    for month_year in sorted(domains_by_month.keys(), key=month_year_key):
        print(f"\n{month_year}:")
        for domain in domains_by_month[month_year]:
            print(f"  - {domain['name']} (Expires: {domain['expires']})")

if __name__ == "__main__":
    if not API_KEY or not API_USER or not CLIENT_IP:
        print("Error: Environment variables not set.")
        print("Please create a .env file with NAMECHEAP_API_KEY, NAMECHEAP_USERNAME, and CLIENT_IP")
        exit(1)
    
    print(f"Namecheap Domain Checker")
    print(f"=" * 30)
    print(f"Username: {API_USER}")
    print(f"Client IP: {CLIENT_IP}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"=" * 30)
    print("Fetching domains from Namecheap...")
    
    start_time = time.time()
    domains = get_domains()
    end_time = time.time()
    
    print(f"Time taken: {end_time - start_time:.2f} seconds")
    
    display_domains(domains)