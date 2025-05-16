import requests
import json
import time
import threading
from flask import Flask, render_template, request, jsonify
from queue import Queue
import os

# LinkedIn API credentials
ACCESS_TOKEN = os.environ.get("LINKEDIN_OAUTH_TOKEN")  # Set in Render environment variables
USER_ID = "mirharoonofficial"  # Your LinkedIn profile ID
API_BASE_URL = "https://api.linkedin.com/v2"

# Message queue for web UI
message_queue = Queue()

# Flask app setup
app = Flask(__name__)

# Load response templates
def load_response_templates():
    try:
        with open("response_templates.json", "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {
            "application": {
                "keywords": ["application", "apply", "job", "role"],
                "response": "Dear [Sender], Thank you for your application. We have received your submission and will review it carefully. You will hear from us soon regarding next steps. Best regards, Mir Haroon"
            },
            "interview": {
                "keywords": ["interview", "meeting", "schedule"],
                "response": "Dear [Sender], Thank you for your interest. I’d like to schedule an interview to discuss your qualifications further. Please share your availability for the coming week. Best regards, Mir Haroon"
            },
            "connection": {
                "keywords": ["connect", "network", "connection"],
                "response": "Dear [Sender], Thank you for reaching out. I’m pleased to connect and explore potential professional opportunities. Looking forward to staying in touch. Best regards, Mir Haroon"
            },
            "thank_you": {
                "keywords": ["thank", "thanks", "gratitude"],
                "response": "Dear [Sender], Thank you for your kind message. I appreciate your support and look forward to future collaboration. Best regards, Mir Haroon"
            },
            "general": {
                "keywords": [],
                "response": "Dear [Sender], Thank you for your message. I’ll review it and respond soon. Best regards, Mir Haroon"
            }
        }

# Save response templates
def save_response_templates(templates):
    with open("response_templates.json", "w") as file:
        json.dump(templates, file, indent=4)

# Fetch LinkedIn messages
def get_inbox_messages():
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    try:
        response = requests.get(
            f"{API_BASE_URL}/messages?q=inbox&createdBefore={int(time.time() * 1000)}",
            headers=headers
        )
        response.raise_for_status()
        return response.json().get("elements", [])
    except requests.exceptions.RequestException as e:
        print(f"Error fetching messages: {e}")
        return []

# Send LinkedIn message
def send_message(recipient_id, message_text):
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    payload = {
        "message": {
            "recipients": [f"urn:li:person:{recipient_id}"],
            "body": message_text,
            "subject": "Re: Your Message"
        }
    }
    try:
        response = requests.post(
            f"{API_BASE_URL}/messages",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        print(f"Message sent to {recipient_id}: {message_text}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error sending message: {e}")
        return False

# Process incoming message
def process_message(message, templates):
    message_text = message.get("body", "").lower()
    sender_id = message.get("sender", {}).get("urn", "").replace("urn:li:person:", "")
    sender_name = message.get("sender", {}).get("name", sender_id) or sender_id
    message_id = message.get("id")

    if not sender_id or not message_id:
        return None

    for category, template in templates.items():
        if category == "general" or any(keyword in message_text for keyword in template["keywords"]):
            response = template["response"].replace("[Sender]", sender_name)
            return {
                "message_id": message_id,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "message_text": message.get("body", ""),
                "proposed_response": response
            }
    response = templates["general"]["response"].replace("[Sender]", sender_name)
    return {
        "message_id": message_id,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "message_text": message.get("body", ""),
        "proposed_response": response
    }

# Poll messages and queue for review
def poll_messages():
    templates = load_response_templates()
    processed_message_ids = set()
    while True:
        messages = get_inbox_messages()
        for message in messages:
            message_id = message.get("id")
            if message_id in processed_message_ids:
                continue
            processed_message_ids.add(message_id)
            message_data = process_message(message, templates)
            if message_data:
                message_queue.put(message_data)
                print(f"Queued message from {message_data['sender_name']}: {message_data['message_text']}")
        time.sleep(60)  # Check every minute

# Flask routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/messages', methods=['GET'])
def get_messages():
    messages = []
    while not message_queue.empty():
        messages.append(message_queue.get())
    return jsonify(messages)

@app.route('/respond', methods=['POST'])
def respond():
    data = request.json
    action = data.get('action')
    message_id = data.get('message_id')
    sender_id = data.get('sender_id')
    response_text = data.get('response_text')

    if action == 'approve' or action == 'edit':
        if send_message(sender_id, response_text):
            return jsonify({"status": "success", "message_id": message_id})
        return jsonify({"status": "error", "message": "Failed to send message"})
    return jsonify({"status": "skipped", "message_id": message_id})

# Start message polling in a separate thread
def start_polling():
    polling_thread = threading.Thread(target=poll_messages, daemon=True)
    polling_thread.start()

if __name__ == "__main__":
    start_polling()
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 5000)))
