# app.py
import os
import logging
import threading
import time

from flask import Flask, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client

# Try to load a local .env when running locally (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ---- Config ----
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER")  # e.g. "whatsapp:+1415xxxxxx"
FAST_REPLY = os.getenv("FAST_REPLY", "true").lower() in ("1", "true", "yes")  # set to false to always ack then follow-up
GENERATE_TIMEOUT = float(os.getenv("GENERATE_TIMEOUT", "6.0"))  # seconds allowed for synchronous generation

# ---- Import your chatbot logic ----
# Your chatbot_logic.py must provide a function:
# def generate_reply(text: str, sender: str) -> str: ...
try:
    from chatbot_logic import generate_reply
except Exception as e:
    # if import fails, define a fallback echo function so the app still runs
    def generate_reply(text, sender):
        return f"(fallback) Echo: {text[:800]}"

# ---- App & Logging ----
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)

# Twilio REST client (lazy init)
_twilio_client = None


def twilio_client():
    global _twilio_client
    if _twilio_client is None:
        if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN:
            app.logger.error("Twilio SID/Token missing in environment variables.")
            raise RuntimeError("Twilio credentials missing")
        _twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    return _twilio_client


def send_async_twilio_message(to_whatsapp_number: str, body: str):
    """
    Send a WhatsApp message via Twilio REST API (runs in background thread).
    """
    try:
        client = twilio_client()
        msg = client.messages.create(
            body=body,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=to_whatsapp_number
        )
        app.logger.info("Sent async Twilio message sid=%s to=%s", getattr(msg, "sid", None), to_whatsapp_number)
    except Exception as exc:
        app.logger.exception("Failed to send async Twilio message: %s", exc)


@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "ok", "service": "whatsapp-chatbot", "version": "1.0"}), 200


@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    """
    Twilio will POST form-encoded parameters such as:
      - Body: the message body
      - From: sender in format whatsapp:+<number>
      - To: your Twilio whatsapp number
    This endpoint tries to synchronously generate a reply within GENERATE_TIMEOUT seconds.
    If FAST_REPLY is False or generation takes too long, we immediately ACK and send the reply asynchronously.
    """
    try:
        form = request.values.to_dict()
        app.logger.info("Incoming webhook: %s", form)

        incoming_msg = form.get("Body", "").strip()
        sender = form.get("From", "")  # e.g. whatsapp:+91...
        if not incoming_msg:
            resp = MessagingResponse()
            resp.message("Sorry, I didn't get any text. Please send a message.")
            return str(resp), 200

        # Try to generate reply, but don't block forever
        reply_text = None
        start_t = time.time()

        if FAST_REPLY:
            # attempt "fast" synchronous generation with timeout
            def target():
                nonlocal reply_text
                try:
                    reply_text = generate_reply(incoming_msg, sender)
                except Exception as e:
                    app.logger.exception("generate_reply crashed: %s", e)
                    reply_text = "Sorry, something went wrong while generating the reply."

            thread = threading.Thread(target=target, daemon=True)
            thread.start()
            thread.join(timeout=GENERATE_TIMEOUT)

            if thread.is_alive():
                # generation still running -> fall back to async
                app.logger.info("Synchronous generation timed out after %.2fs. Falling back to async.", GENERATE_TIMEOUT)
                resp = MessagingResponse()
                resp.message("Got your message — I'm thinking and will reply shortly.")
                # start background thread to wait for generate_reply to finish (or call directly)
                def wait_and_send():
                    try:
                        # If generate_reply still running in target thread, we can't access its result.
                        # So call generate_reply again (idempotency not guaranteed). Alternatively,
                        # you could implement your own queue/worker.
                        generated = generate_reply(incoming_msg, sender)
                        send_async_twilio_message(sender, generated)
                    except Exception:
                        app.logger.exception("Background generate/send failed.")
                        try:
                            send_async_twilio_message(sender, "Sorry, I couldn't prepare a reply.")
                        except Exception:
                            app.logger.exception("Failed to send error message.")
                bg = threading.Thread(target=wait_and_send, daemon=True)
                bg.start()
                return str(resp), 200
            else:
                # reply ready synchronously
                duration = time.time() - start_t
                app.logger.info("Generated reply synchronously in %.2fs", duration)
                resp = MessagingResponse()
                resp.message(reply_text)
                return str(resp), 200

        else:
            # FAST_REPLY disabled: immediate ack + background reply
            resp = MessagingResponse()
            resp.message("Received — I'll reply shortly.")
            bg = threading.Thread(target=lambda: send_async_twilio_message(sender, generate_reply(incoming_msg, sender)), daemon=True)
            bg.start()
            return str(resp), 200

    except Exception as exc:
        app.logger.exception("Webhook handling error: %s", exc)
        # Return a safe TwiML so Twilio doesn't retry aggressively
        resp = MessagingResponse()
        resp.message("Server error. Please try again later.")
        return str(resp), 500


# Optional: endpoint to trigger test message from the server (protected or remove in prod)
@app.route("/_send_test", methods=["POST"])
def send_test_message():
    """
    Post JSON: {"to": "whatsapp:+91...", "body": "hello test"}
    Only for quick testing from server (remove or protect in production).
    """
    data = request.get_json(force=True, silent=True) or {}
    to = data.get("to")
    body = data.get("body", "test")
    if not to:
        return jsonify({"error": "missing 'to'"}), 400
    try:
        send_async_twilio_message(to, body)
        return jsonify({"status": "queued"}), 200
    except Exception as e:
        app.logger.exception("test send failed")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # Local dev server (not for production). Render will use gunicorn.
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "false").lower() in ("1", "true"))
