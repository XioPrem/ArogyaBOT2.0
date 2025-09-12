import os
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from dotenv import load_dotenv

# Import the logic you refactored from your Streamlit app
from chatbot_logic import (
    search_and_get_sources,
    build_prompt,
    call_llm,
    LANGUAGES,
    TRANSLATIONS
)

load_dotenv()
app = Flask(__name__)

# A simple way to track user language. For production, use a database.
user_language = {}

@app.route("/whatsapp", methods=["POST"])
def whatsapp_reply():
    """Receives incoming WhatsApp messages and sends a reply."""
    
    # Get the message from the user and their phone number
    incoming_msg = request.values.get("Body", "").strip()
    sender_number = request.values.get("From", "")
    
    # --- Language Detection (Simple Example) ---
    # Default to English if user's language is not set
    lang_code = user_language.get(sender_number, "en")
    
    # A simple command to change language
    if incoming_msg.lower() in ["bengali", "hindi", "english"]:
        lang_name = incoming_msg.lower().capitalize()
        user_language[sender_number] = LANGUAGES[lang_name]
        lang_code = LANGUAGES[lang_name]
        t = TRANSLATIONS[lang_code]
        response_msg = f"{t['page_title']} language set to {lang_name}."
    else:
        # --- Main Chatbot Logic ---
        print(f"Finding sources for: '{incoming_msg}' in language '{lang_code}'")
        sources = search_and_get_sources(incoming_msg, lang_code=lang_code)

        print("Building prompt...")
        prompt = build_prompt(incoming_msg, sources, lang_code=lang_code)
        
        system_message = (
            "You are a helpful medical information assistant. Always remind users that your information is for "
            "educational purposes and they should consult healthcare professionals for medical advice."
        )
        
        print("Calling LLM...")
        assistant_text = call_llm(prompt, system_message=system_message)
        
        if assistant_text:
            response_msg = assistant_text
            # Append sources to the message for WhatsApp
            if sources:
                t = TRANSLATIONS[lang_code]
                response_msg += f"\n\n*{t['sources_title']}*"
                for i, source in enumerate(sources, 1):
                    response_msg += f"\n{i}. {source.get('url')}"
        else:
            t = TRANSLATIONS[lang_code]
            response_msg = t["error_message"]

    # Create a Twilio response object and send the message back
    response = MessagingResponse()
    response.message(response_msg)
    
    return str(response)

if __name__ == "__main__":
    # The default port is 5000
    app.run(debug=True)