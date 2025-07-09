from flask import Flask, request, jsonify
import joblib
import pandas as pd
import requests
import smtplib
from email.mime.text import MIMEText
import datetime

app = Flask(__name__)

# ==== Shopify Admin API Credentials (replace these!) ====
SHOPIFY_API_KEY = "bf520678d939baaf977cf4fbc5a00ba1"
SHOPIFY_PASSWORD = "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"
SHOPIFY_STORE = "nerdused.myshopify.com"  # e.g. "mybrand.myshopify.com"

# ==== Load the trained model and metadata ====
model_bundle = joblib.load('fraud_advanced_model.pkl')
model = model_bundle['model']
label_encoder = model_bundle['label_encoder']
features = model_bundle['features']

EXPLANATION_LABELS = {
    "repeat_orders_7d": "Repeat Orders in Last 7 Days",
    "refund_history": "High Refund Rate",
    "risky_payment_method": "Unusual/Risky Payment Method",
    "chargeback_history": "Chargeback History",
    "order_value_jump": "Order Value Higher Than Usual",
    "none": "No Specific Risk Reason"
}

@app.route('/shopify_webhook', methods=['POST'])
def shopify_webhook():
    order_data = request.get_json()
    
    # If customer info exists, calculate account age
    customer = order_data.get("customer", {})
    account_created_at = customer.get("created_at")
    if account_created_at:
        try:
            account_created_date = datetime.datetime.strptime(account_created_at, "%Y-%m-%dT%H:%M:%S%z")
            account_age_days = (datetime.datetime.now(datetime.timezone.utc) - account_created_date).days
        except Exception:
            account_age_days = 365  # Fallback to 1 year
    else:
        account_age_days = 365

    # Count payment methods
    payment_methods = order_data.get("payment_gateway_names", [])
    num_payment_methods = len(payment_methods)

    # Check if payment method is risky (e.g., contains "crypto" or "bitcoin")
    payment_method_is_risky = 1 if any("crypto" in pm.lower() or "bitcoin" in pm.lower() for pm in payment_methods) else 0

    # Check unique shipping address (default 1 if present)
    unique_shipping_address = 1 if order_data.get("shipping_address") else 0

    # --- Feature extraction from order_data ---
    features_dict = {
    "total": float(order_data.get("total_price", 0)),
    "order_value_mean": float(order_data.get("total_price", 0)),
    "order_value_std": 0.01,               # Small nonzero value
    "order_value_prev": float(order_data.get("total_price", 0)),
    "order_value_jump": 0.01,              # Small nonzero value
    "days_since_last_order": 30,           # Assume safe, 30 days
    "orders_last_7d": 1,
    "orders_last_30d": 2,
    "refund_rate": 0.0,
    "cancel_rate": 0.0,
    "chargeback_rate": 0.0,
    "unique_shipping_address": unique_shipping_address,
    "account_age_days": account_age_days,
    "payment_method_is_risky": payment_method_is_risky,
    "num_payment_methods": num_payment_methods if num_payment_methods > 0 else 1,
    "order_id": order_data.get("id"),
    "email": order_data.get("email")
    }

    # --- Run prediction ---
    input_df = pd.DataFrame([features_dict])[features]
    prediction = model.predict(input_df)[0]
    risk_label = label_encoder.inverse_transform([prediction])[0]

    # --- Explanation logic ---
    explanation = []
    if input_df['orders_last_7d'].iloc[0] > 2:
        explanation.append('repeat_orders_7d')
    if input_df['refund_rate'].iloc[0] > 0.2:
        explanation.append('refund_history')
    if input_df['payment_method_is_risky'].iloc[0] == 1:
        explanation.append('risky_payment_method')
    if input_df['chargeback_rate'].iloc[0] > 0.05:
        explanation.append('chargeback_history')
    if input_df['order_value_jump'].iloc[0] > input_df['order_value_std'].iloc[0]:
        explanation.append('order_value_jump')
    if not explanation:
        explanation.append('none')
    explanation_str = ', '.join([EXPLANATION_LABELS.get(code, code) for code in explanation])

    # --- Tag and annotate the order in Shopify ---
    order_id = features_dict["order_id"]
    shopify_status_code, shopify_response = None, None
    if order_id:
        shopify_status_code, shopify_response = tag_order_in_shopify(order_id, risk_label, explanation_str)

    # --- Send confirmation email for medium/high risk ---
    customer_email = features_dict["email"]
    email_sent = None
    if risk_label.lower() in ["medium", "high"] and customer_email:
        email_sent = send_confirmation_email(customer_email, order_id, risk_label, explanation_str)

    # --- Optional: Delayed delivery flag ---
    delayed_delivery = (risk_label.lower() in ["medium", "high"])

    return jsonify({
        "fraud_risk": risk_label,
        "explanation": explanation_str,
        "shopify_status_code": shopify_status_code,
        "shopify_response": shopify_response,
        "email_sent": email_sent,
        "delayed_delivery": delayed_delivery
    }), 200

@app.route('/')
def home():
    return "✅ Advanced Fraud Detection API is running."

def send_confirmation_email(to_email, order_id, risk_label, explanation):
    smtp_server = "rldev.us"  # e.g. smtp.gmail.com
    smtp_port = 465
    smtp_user = "admin@rldev.us"
    smtp_pass = "RapidLabs+1"
    from_email = smtp_user

    msg = MIMEText(f"""
    Dear Customer,

    Your order ({order_id}) has been flagged as '{risk_label.upper()}' risk for the following reason(s):

    {explanation}

    Please reply to this email to confirm your order is legitimate. 
    If you do not respond, your order may be delayed or canceled.

    Thank you for your cooperation.
    """)
    msg['Subject'] = f"Action Required: Please confirm your order {order_id}"
    msg['From'] = from_email
    msg['To'] = to_email

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, [to_email], msg.as_string())
        print("Confirmation email sent to", to_email)
        return True
    except Exception as e:
        print("Email send failed:", e)
        return False

# ==== Helper: Tag and annotate Shopify order ====
def tag_order_in_shopify(order_id, fraud_label, explanation):
    try:
        # 1. Get current tags
        get_url = f"https://{SHOPIFY_API_KEY}:{SHOPIFY_PASSWORD}@{SHOPIFY_STORE}/admin/api/2023-10/orders/{order_id}.json"
        response = requests.get(get_url)
        if response.status_code != 200:
            return response.status_code, {'error': f'Failed to fetch order: {response.text}'}
        order = response.json().get("order", {})
        existing_tags = order.get("tags", "")
        updated_tags = (existing_tags + f",Fraud-{fraud_label}").strip(",") if existing_tags else f"Fraud-{fraud_label}"

        # 2. Update tags and note attributes
        put_url = f"https://{SHOPIFY_STORE}/admin/api/2023-10/orders/{order_id}.json"
        headers = { "Content-Type": "application/json" }
        data = {
            "order": {
                "id": order_id,
                "tags": updated_tags,
                "note_attributes": [{"name": "fraud_reason", "value": explanation}],
                "note": f"Fraud Explanation: {explanation}"
            }
        }
        put_response = requests.put(put_url, auth=(SHOPIFY_API_KEY, SHOPIFY_PASSWORD), json=data, headers=headers)
        return put_response.status_code, put_response.json()
    except Exception as e:
        return 500, {'error': str(e)}

@app.route('/predict', methods=['POST'])
def predict():
    input_data = request.json
    try:
        input_df = pd.DataFrame([input_data])[features]
        prediction = model.predict(input_df)[0]
        risk_label = label_encoder.inverse_transform([prediction])[0]

        # --- Explanation tags as before ---
        explanation = []
        if input_df['orders_last_7d'].iloc[0] > 2:
            explanation.append('repeat_orders_7d')
        if input_df['refund_rate'].iloc[0] > 0.2:
            explanation.append('refund_history')
        if input_df['payment_method_is_risky'].iloc[0] == 1:
            explanation.append('risky_payment_method')
        if input_df['chargeback_rate'].iloc[0] > 0.05:
            explanation.append('chargeback_history')
        if input_df['order_value_jump'].iloc[0] > input_df['order_value_std'].iloc[0]:
            explanation.append('order_value_jump')
        if not explanation:
            explanation.append('none')
        explanation_str = ', '.join([EXPLANATION_LABELS.get(code, code) for code in explanation])

        # --- Shopify tagging ---
        order_id = input_data.get("order_id")
        shopify_status_code, shopify_response = None, None
        if order_id:
            shopify_status_code, shopify_response = tag_order_in_shopify(order_id, risk_label, explanation_str)

        # --- Email confirmation for medium/high risk ---
        customer_email = input_data.get("email")
        email_sent = None
        if risk_label.lower() in ["medium", "high"] and customer_email:
            email_sent = send_confirmation_email(customer_email, order_id, risk_label, explanation_str)

        # --- Delayed delivery flag ---
        delayed_delivery = (risk_label.lower() in ["medium", "high"])

        # --- Return everything for logging/demo ---
        return jsonify({
            'fraud_risk': risk_label,
            'explanation': explanation_str,
            'shopify_status_code': shopify_status_code,
            'shopify_response': shopify_response,
            'email_sent': email_sent,
            'delayed_delivery': delayed_delivery
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
