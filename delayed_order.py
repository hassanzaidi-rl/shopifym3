import requests
import time

# Shopify API credentials (set as environment variables in production)
SHOPIFY_API_KEY = "bf520678d939baaf977cf4fbc5a00ba1"
SHOPIFY_PASSWORD = "8b63bb8951839d6d91b3038b82a80c1f"
SHOPIFY_STORE = "nerdused.myshopify.com"

# Optional: Keep track of already processed orders (in memory)
delivered_orders = set()

def get_recent_orders():
    url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_PASSWORD}@{SHOPIFY_STORE}/admin/api/2023-10/orders.json?status=paid&limit=50"
    response = requests.get(url)
    if response.status_code != 200:
        print("Failed to fetch orders:", response.text)
        return []
    return response.json().get("orders", [])

def get_order_from_shopify(order_id):
    url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_PASSWORD}@{SHOPIFY_STORE}/admin/api/2023-10/orders/{order_id}.json"
    response = requests.get(url)
    if response.status_code != 200:
        print("Failed to fetch order:", response.text)
        return None
    return response.json().get("order", {})

def deliver_digital_product(order):
    # Replace with your real digital delivery logic
    print(f"Delivering digital product for order {order['id']} to {order['email']}")
    # e.g. send_license_email(order["email"], ...)

def check_and_deliver(order_id):
    order = get_order_from_shopify(order_id)
    if not order:
        print("Order not found.")
        return

    tags = order.get("tags", "").lower()
    if "fraud-high" in tags or "fraud-medium" in tags:
        print(f"Order {order_id} flagged as risky ({tags}). Delivery is delayed for manual review.")
        return
    elif order["id"] in delivered_orders:
        print(f"Order {order_id} already delivered. Skipping.")
        return
    else:
        deliver_digital_product(order)
        delivered_orders.add(order["id"])

if __name__ == "__main__":
    while True:
        print("Checking for new orders...")
        orders = get_recent_orders()
        for order in orders:
            check_and_deliver(order["id"])
        print("Waiting for 5 minutes before next check...")
        time.sleep(300)  # 5 minutes (300 seconds)
