import requests

SHOPIFY_API_KEY = "bf520678d939baaf977cf4fbc5a00ba1"
SHOPIFY_PASSWORD = "8b63bb8951839d6d91b3038b82a80c1f"
SHOPIFY_STORE = "nerdused.myshopify.com"

def get_order_from_shopify(order_id):
    url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_PASSWORD}@{SHOPIFY_STORE}/admin/api/2023-10/orders/{order_id}.json"
    response = requests.get(url)
    if response.status_code != 200:
        print("Failed to fetch order:", response.text)
        return None
    return response.json().get("order", {})

def deliver_digital_product(order):
    # Replace with your real digital delivery logic (e.g., send email, license key, etc.)
    print(f"Delivering digital product for order {order['id']} to {order['email']}")
    # Example: Send download link or license via email
    # send_license_email(order["email"], ...)

def check_and_deliver(order_id):
    order = get_order_from_shopify(order_id)
    if not order:
        print("Order not found.")
        return

    tags = order.get("tags", "").lower()
    if "fraud-high" in tags or "fraud-medium" in tags:
        print(f"Order {order_id} flagged as risky ({tags}). Delivery is delayed for manual review.")
        # Optionally: send internal notification, add to queue, etc.
        return
    else:
        deliver_digital_product(order)

# ==== Example usage ====
if __name__ == "__main__":
    order_id = 1234567890123  # Replace with a real Shopify Order ID
    check_and_deliver(order_id)
