import os
import urllib.request
import json
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# File path for tracking state, stored in the same directory as the script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, "state.json")

def load_state():
    """Load stock status state from state.json."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading state.json: {e}")
    # Default state if file is missing or corrupt
    return {"last_status": False, "notified": False}

def save_state(state):
    """Save stock status state to state.json."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
        print(f"Saved state: {state}")
    except Exception as e:
        print(f"Error saving state.json: {e}")

def check_stock_status():
    """Fetch SMUD Energy Store page and determine if NEMA 14-50 variant is available."""
    url = "https://smudenergystore.com/EV-Chargers/P-NEOSMRTSP.html"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5'
    }
    
    print(f"Fetching product page: {url}...")
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8')
    except Exception as e:
        print(f"Network error while fetching SMUD store: {e}")
        # Return None so we don't change states on transient network/DNS issues
        return None

    # Parse using regex matching for the JSON data object injected on the page
    product_match = re.search(r'window\.seMarketplace\.product\s*=\s*(\{.*?\});', html, re.DOTALL)
    if product_match:
        try:
            product_data = json.loads(product_match.group(1))
            available = product_data.get('available')
            if available is not None:
                print(f"Parse success: available={available}")
                return available
        except Exception as e:
            print(f"Parsing window.seMarketplace.product failed: {e}")

    # Fallback to simple HTML string search
    if "https://schema.org/InStock" in html or '"InStock"' in html:
        print("Fallback parse: Found InStock in HTML")
        return True
    elif "https://schema.org/OutOfStock" in html or '"OutOfStock"' in html:
        print("Fallback parse: Found OutOfStock in HTML")
        return False

    print("Warning: Could not parse stock status from HTML page structure.")
    return None

def send_email_notification():
    """Send an email notification using SMTP settings from environment variables."""
    # Retrieve configuration from environment variables (GitHub secrets)
    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_port_str = os.environ.get("SMTP_PORT", "587")
    smtp_user = os.environ.get("SMTP_USERNAME")
    smtp_pass = os.environ.get("SMTP_PASSWORD")
    receiver_email = os.environ.get("RECEIVER_EMAIL")
    sender_email = os.environ.get("SENDER_EMAIL") or smtp_user

    # Validate that we have the minimum requirements to send email
    missing = [k for k, v in {
        "SMTP_SERVER": smtp_server,
        "SMTP_USERNAME": smtp_user,
        "SMTP_PASSWORD": smtp_pass,
        "RECEIVER_EMAIL": receiver_email
    }.items() if not v]

    if missing:
        print(f"SKIPPING EMAIL: Missing environment variables: {', '.join(missing)}")
        return False

    try:
        smtp_port = int(smtp_port_str)
    except ValueError:
        print(f"Invalid SMTP_PORT: '{smtp_port_str}'. Defaulting to 587.")
        smtp_port = 587

    print(f"Sending email notification to {receiver_email} via {smtp_server}:{smtp_port}...")

    # Create message
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = "🚨 IN STOCK: NeoCharge Smart Splitter 14-50 at SMUD!"

    body = (
        "Good news!\n\n"
        "The NeoCharge Smart Splitter (NEMA 14-50 variant) is back in stock at the SMUD Energy Store.\n\n"
        "Product Link: https://smudenergystore.com/EV-Chargers/P-NEOSMRTSP.html\n\n"
        "This is an automated notification from your GitHub Action stock checker."
    )
    msg.attach(MIMEText(body, 'plain'))

    try:
        # Establish connection. If port is 465, use SMTP_SSL. Otherwise use standard SMTP and STARTTLS.
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10)
        else:
            server = smtplib.SMTP(smtp_server, smtp_port, timeout=10)
            server.ehlo()
            server.starttls()
            server.ehlo()
            
        server.login(smtp_user, smtp_pass)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.close()
        print("Email sent successfully!")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

def main():
    state = load_state()
    print(f"Current State: last_status={state.get('last_status')}, notified={state.get('notified')}")

    current_stock = check_stock_status()
    if current_stock is None:
        print("Stock check failed or was inconclusive. Exiting without state change.")
        return

    print(f"Stock status detected: {current_stock}")

    state_changed = False

    if current_stock:
        # It's in stock. If we haven't notified the user yet, notify them now.
        if not state.get('notified'):
            print("Product is IN STOCK and we have not notified the user yet. Sending email...")
            email_sent = send_email_notification()
            if email_sent:
                state['notified'] = True
                state['last_status'] = True
                state_changed = True
            else:
                print("Failed to send notification email. Will retry on next execution.")
        else:
            print("Product is in stock, but user was already notified. No action taken.")
    else:
        # It's out of stock. If our state still says "notified", reset it so they can be notified next time it restocks.
        if state.get('notified') or state.get('last_status'):
            print("Product is OUT OF STOCK. Resetting notification flag for next restock.")
            state['notified'] = False
            state['last_status'] = False
            state_changed = True
        else:
            print("Product is out of stock. User not notified (as expected). No action taken.")

    if state_changed:
        save_state(state)
        # We output a flag for GitHub Actions to know that it needs to commit changes
        with open(os.path.join(SCRIPT_DIR, "state_changed.txt"), "w") as f:
            f.write("true")
    else:
        print("No state changes to write.")

if __name__ == "__main__":
    main()
