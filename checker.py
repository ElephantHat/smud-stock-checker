import os
import urllib.request
import json
import re

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

def send_slack_notification(message):
    """Send a notification message to Slack via Incoming Webhook."""
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("SKIPPING SLACK: Missing SLACK_WEBHOOK_URL environment variable.")
        return False

    headers = {
        "Content-Type": "application/json"
    }
    payload = {
        "text": message
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(webhook_url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as response:
            res_body = response.read().decode("utf-8")
            print(f"Slack response: {res_body}")
            return res_body == "ok"
    except Exception as e:
        print(f"Failed to send Slack notification: {e}")
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
            print("Product is IN STOCK. Sending Slack notification...")
            msg = (
                "🚨 *IN STOCK:* NeoCharge Smart Splitter 14-50 at SMUD!\n"
                "Product Link: https://smudenergystore.com/EV-Chargers/P-NEOSMRTSP.html"
            )
            slack_sent = send_slack_notification(msg)
            if slack_sent:
                state['notified'] = True
                state['last_status'] = True
                state_changed = True
            else:
                print("Failed to send Slack notification. Will retry on next execution.")
        else:
            print("Product is in stock, but user was already notified. No action taken.")
    else:
        # It's out of stock. If our state still says "notified", reset it and notify.
        if state.get('notified') or state.get('last_status'):
            print("Product is OUT OF STOCK. Sending Slack notification and resetting state...")
            msg = "ℹ️ *OUT OF STOCK:* NeoCharge Smart Splitter 14-50 is now out of stock at SMUD."
            slack_sent = send_slack_notification(msg)
            if slack_sent:
                state['notified'] = False
                state['last_status'] = False
                state_changed = True
            else:
                print("Failed to send Slack notification. Will retry on next execution.")
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
