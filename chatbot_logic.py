import os, re
import json
import time
import random
import html
from typing import List, Dict, Optional
from functools import lru_cache

import streamlit as st
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Optional: SerpAPI for reliable search results
try:
    from serpapi import GoogleSearch
    _HAS_SERPAPI = True
except Exception:
    _HAS_SERPAPI = False

load_dotenv()

# ---------- Config ----------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-preview-05-20")
MAX_SOURCES = 3

# Define supported languages and UI translations
LANGUAGES = {
    "English": "en",
    "Bengali": "bn",
    "Hindi": "hi"
}

TRANSLATIONS = {
    "en": {
        "page_title": "ArogyaBOT",
        "disclaimer": "Your sourced health assistant — not a substitute for medical advice.",
        "ask_placeholder": "Ask about a disease, symptom, or treatment",
        "search_button": "Ask",
        "finding_sources": "Finding trustworthy sources...",
        "generating_answer": "Generating answer...",
        "error_message": "Sorry — something went wrong. Please try again.",
        "api_key_configured": "✅ Gemini API key is configured",
        "api_key_missing": "❌ Gemini API key is missing. Please set GEMINI_API_KEY in your environment.",
        "question_prefix": "Q:",
        "answer_prefix": "A:",
        "sources_title": "Sources (verified links)",
        "show_sources": "Show sources (verified links)",
        "no_sources_found": "No sources found, but I'll try to help based on general medical knowledge."
    },
    "bn": {
        "page_title": "আরোগ্যবট",
        "disclaimer": "আপনার উৎস-ভিত্তিক স্বাস্থ্য সহকারী — চিকিৎসা পরামর্শের বিকল্প নয়।",
        "ask_placeholder": "কোনো রোগ, লক্ষণ, বা চিকিৎসা সম্পর্কে জিজ্ঞাসা করুন",
        "search_button": "জিজ্ঞাসা করুন",
        "finding_sources": "নির্ভরযোগ্য উৎস খুঁজছে...",
        "generating_answer": "উত্তর তৈরি করছে...",
        "error_message": "দুঃখিত — কিছু ভুল হয়েছে। অনুগ্রহ করে আবার চেষ্টা করুন।",
        "api_key_configured": "✅ জেমিনি এপিআই কী কনফিগার করা হয়েছে",
        "api_key_missing": "❌ জেমিনি এপিআই কী অনুপস্থিত। অনুগ্রহ করে আপনার পরিবেশে GEMINI_API_KEY সেট করুন।",
        "question_prefix": "প্র:",
        "answer_prefix": "উ:",
        "sources_title": "উৎস (সত্যায়িত লিঙ্ক)",
        "show_sources": "উৎস দেখান (সত্যায়িত লিঙ্ক)",
        "no_sources_found": "কোনো উৎস পাওয়া যায়নি, তবে আমি সাধারণ চিকিৎসা জ্ঞানের উপর ভিত্তি করে সাহায্য করার চেষ্টা করব।"
    },
    "hi": {
        "page_title": "आरोग्यबॉट",
        "disclaimer": "आपका स्रोत-आधारित स्वास्थ्य सहायक — चिकित्सा सलाह का विकल्प नहीं।",
        "ask_placeholder": "किसी बीमारी, लक्षण या उपचार के बारे में पूछें",
        "search_button": "पूछें",
        "finding_sources": "विश्वसनीय स्रोत ढूँढ रहा है...",
        "generating_answer": "उत्तर उत्पन्न कर रहा है...",
        "error_message": "क्षमा करें — कुछ गलत हो गया। कृपया पुनः प्रयास करें।",
        "api_key_configured": "✅ जेमिनी एपीआई कुंजी कॉन्फ़िगर की गई है",
        "api_key_missing": "❌ जेमिनी एपीआई कुंजी गायब है। कृपया अपने पर्यावरण में GEMINI_API_KEY सेट करें।",
        "question_prefix": "प्र:",
        "answer_prefix": "उ:",
        "sources_title": "स्रोत (सत्यापित लिंक)",
        "show_sources": "स्रोत दिखाएँ (सत्यापित लिंक)",
        "no_sources_found": "कोई स्रोत नहीं मिला, लेकिन मैं सामान्य चिकित्सा ज्ञान के आधार पर मदद करने की कोशिश करूंगा।"
    }
}

if "language" not in st.session_state:
    st.session_state.language = "English"

# Get current language code and translations
lang_code = LANGUAGES.get(st.session_state.language, "en")
t = TRANSLATIONS.get(lang_code, TRANSLATIONS["en"])

# ---------- UI ----------
st.set_page_config(page_title=t["page_title"], layout="wide", page_icon="🩺")

# Language selector at the top
st.sidebar.markdown('<p style="font-weight:600; font-size: 1.2rem;">Language</p>', unsafe_allow_html=True)
st.session_state.language = st.sidebar.radio("", list(LANGUAGES.keys()), index=list(LANGUAGES.keys()).index(st.session_state.language))

# App title (user requested name)
st.markdown(f"""
<h1 style="margin:0;padding:0;font-size:36px;">{t["page_title"]}</h1>
<p style="margin:4px 0 18px 0;color:#bfc7ce;">{t["disclaimer"]}</p>
""", unsafe_allow_html=True)

# Custom CSS for clean cards and readable text
st.markdown("""
<style>
.result-card{
  background: #0f1724; /* dark card */
  border-radius: 12px;
  padding: 18px;
  margin-bottom: 12px;
  box-shadow: 0 6px 18px rgba(2,6,23,0.6);
}
.result-title{font-size:18px;font-weight:700;margin-bottom:6px;color:#ffffff}
.result-body{font-size:16px;line-height:1.6;color:#e6eef8}
.source-list{font-size:14px;color:#9fb0d6}
.link{color:#6ec1ff}
.input-area textarea{background:#0b1220;color:#fff}
</style>
""", unsafe_allow_html=True)

# ---------- Networking helpers ----------

def polite_get(url: str, **kwargs) -> requests.Response:
    time.sleep(0.12 + random.random() * 0.18)
    return requests.get(url, headers=kwargs.pop("headers", {"User-Agent": "Mozilla/5.0"}), timeout=kwargs.pop("timeout", 8))

@lru_cache(maxsize=256)
def fetch_page_text_cached(url: str, max_chars: int = 1500) -> str:
    return fetch_page_text(url, max_chars)

def fetch_page_text(url: str, max_chars=1500) -> str:
    try:
        resp = polite_get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        ps = soup.find_all("p")
        text = "\n\n".join(p.get_text().strip() for p in ps[:8])
        return text[:max_chars] + ("..." if len(text) > max_chars else "")
    except Exception as e:
        print(f"Failed to fetch {url}: {e}")
        return ""

def search_and_get_sources(query: str, max_results: int = MAX_SOURCES, lang_code: str = "en") -> List[Dict]:
    serp_key = os.environ.get("SERPAPI_KEY")
    if not _HAS_SERPAPI or not serp_key:
        print("SerpAPI not available - returning empty sources")
        return []

    def run_search(q, engine_params):
        try:
            print(f"Running search with query: {q}")
            search = GoogleSearch(engine_params)
            results = search.get_dict()
            organic_results = results.get("organic_results", [])
            print(f"Found {len(organic_results)} organic results")
            return organic_results
        except Exception as e:
            print(f"Search failed: {e}")
            return []

    # Strategy 1: Search on trusted domains (simplified query)
    trusted_query = f"{query} health medical"
    trusted_params = {
        "q": trusted_query,
        "engine": "google",
        "api_key": serp_key,
        "num": max_results * 2,
        "hl": lang_code if lang_code in ["en", "es"] else "en",
    }
    trusted_results = run_search(trusted_query, trusted_params)
    
    # Filter for trusted domains manually
    trusted_domains = ["who.int", "cdc.gov", "nih.gov", "mayoclinic.org", "webmd.com", "healthline.com", "medlineplus.gov"]
    filtered_results = []
    
    for result in trusted_results:
        url = result.get("link", "")
        if any(domain in url.lower() for domain in trusted_domains):
            filtered_results.append(result)
            if len(filtered_results) >= max_results:
                break
    
    # If no trusted sources found, use general results with health keywords
    results_to_use = filtered_results
    if not filtered_results:
        print("No trusted sources found, using general health results")
        health_keywords = ["health", "medical", "medicine", "symptom", "treatment", "disease"]
        general_results = []
        for result in trusted_results[:max_results]:
            title = result.get("title", "").lower()
            snippet = result.get("snippet", "").lower()
            if any(keyword in title or keyword in snippet for keyword in health_keywords):
                general_results.append(result)
        results_to_use = general_results


    sources = []
    for r in results_to_use[:max_results]:
        url = r.get("link")
        if not url:
            continue
        page_text = fetch_page_text_cached(url)
        if page_text:
            sources.append({
                "url": url, 
                "snippet": page_text,
                "title": r.get("title", "")
            })
    
    print(f"Final sources count: {len(sources)}")
    return sources

# ---------- LLM caller (corrected for Gemini API) ----------

def call_llm(prompt: str, system_message: str = "") -> Optional[str]:
    """
    Call Gemini API using the correct REST format.
    Returns the assistant's text or None on failure.
    """
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY is not set.")
        return None

    # Construct the URL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    
    headers = {
        "x-goog-api-key": GEMINI_API_KEY,
        "Content-Type": "application/json"
    }

    # Build the payload according to Gemini API format
    payload = {
        "contents": [
            {
                "parts": [{"text": prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 2048,
            "candidateCount": 1
        }
    }
    
    if system_message:
        payload["systemInstruction"] = {"parts": [{"text": system_message}]}

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        # Debug logging for API response
        if response.status_code != 200:
            print(f"API Error - Status Code: {response.status_code}")
            print(f"API Error - Response Text: {response.text}")
            return None
            
        data = response.json()
        
        # Parse response using the correct Gemini format
        try:
            candidates = data.get("candidates", [])
            if candidates:
                content = candidates[0].get("content", {})
                parts = content.get("parts", [])
                if parts:
                    text = parts[0].get("text", "")
                    return text.strip() if text else None
        except (KeyError, IndexError, TypeError) as e:
            print(f"Error parsing response: {e}")
            print(f"Response data: {json.dumps(data, indent=2)[:500]}")
            
        return None
        
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"JSON decode failed: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error: {e}")
        return None

# ---------- Prompt builder ----------

def build_prompt(user_question: str, sources: List[Dict], lang_code: str) -> str:
    lang_name = next(key for key, value in LANGUAGES.items() if value == lang_code)
    
    if sources:
        ctx_parts = []
        for i, s in enumerate(sources, start=1):
            if isinstance(s, dict):
                url = s.get("url", "[no-url]")
                snippet = s.get("snippet", "")
                title = s.get("title", "")
            else:
                url = str(s)
                snippet = ""
                title = ""
            part = f"[SOURCE {i}] {title}\nURL: {url}\nEXCERPT:\n{snippet}\n"
            ctx_parts.append(part)

        ctx = "\n\n".join(ctx_parts)
        prompt = (
            f"You are a helpful, cautious medical information assistant. Please provide your answer in {lang_name}. "
            "Use the provided source excerpts to answer the user's question. "
            "Be informative but always remind users to consult healthcare professionals for personalized advice.\n\n"
            f"SOURCES:\n{ctx}\n\n"
            f"USER QUESTION: {user_question}\n\n"
            "Please provide a helpful answer based on the sources (3-6 short paragraphs) and include a note about consulting healthcare professionals."
        )
    else:
        # No sources available - provide general guidance
        prompt = (
            f"You are a helpful, cautious medical information assistant. Please provide your answer in {lang_name}. "
            f"The user is asking: {user_question}\n\n"
            "I don't have access to specific medical sources right now, but I can provide general health information. "
            "Please provide helpful general guidance about this health topic, but emphasize that this is general information only "
            "and the user should consult with healthcare professionals (doctors, WHO, CDC) for personalized medical advice. "
            "Keep the response informative but cautious, and always recommend professional medical consultation."
        )
    
    return prompt

# ---------- Small helpers for clean output ----------

def render_answer_and_sources(answer: str, sources: List[Dict]):
    """Render the answer and sources in a clean format."""
    t = TRANSLATIONS.get(LANGUAGES.get(st.session_state.language), TRANSLATIONS["en"])

    # Answer card
    st.markdown('<div class="result-card">', unsafe_allow_html=True)
    st.markdown(f'<div class="result-title">{t["answer_prefix"]} Answer</div>', unsafe_allow_html=True)

    # Show answer as paragraphs
    paragraphs = [p.strip() for p in answer.split("\n\n") if p.strip()]
    for p in paragraphs:
        # Use markdown for better formatting
        st.markdown(f'<div class="result-body">{html.escape(p)}</div>', unsafe_allow_html=True)

    # Sources in an expander (collapsed by default)
    if sources:
        with st.expander(t["show_sources"]):
            for i, s in enumerate(sources, start=1):
                url = s.get("url") if isinstance(s, dict) else str(s)
                title = s.get("title", "") if isinstance(s, dict) else ""
                if url:
                    display_text = f"{title} - {url}" if title else url
                    st.markdown(f'{i}. [{display_text}]({url})')
    else:
        st.info(t["no_sources_found"])

    st.markdown('</div>', unsafe_allow_html=True)

def strip_trailing_numbered_links(text: str) -> str:
    """Remove trailing numbered link blocks like '1. https://...' until first non-link line."""
    lines = text.strip().splitlines()
    # Walk back while lines look like numbered links
    while lines and re.match(r'^\s*\d+\.\s*https?://', lines[-1]):
        lines.pop()
    return "\n".join(lines).strip()

# ---------- Streamlit UI (clean) ----------
if "history" not in st.session_state:
    st.session_state.history = []

with st.form("query_form"):
    q = st.text_area(t["ask_placeholder"], height=120)
    submitted = st.form_submit_button(t["search_button"])

if submitted and q.strip():
    with st.spinner(t["finding_sources"]):
        # Use session state for caching search results
        if "search_results_cache" not in st.session_state or st.session_state.search_results_cache.get("query") != q or st.session_state.search_results_cache.get("lang") != lang_code:
            st.session_state.search_results_cache = {
                "query": q,
                "lang": lang_code,
                "sources": search_and_get_sources(q, lang_code=lang_code) or []
            }
        sources = st.session_state.search_results_cache["sources"]

    prompt = build_prompt(q, sources, lang_code=lang_code)

    # No harsh system message - let the bot work with or without sources
    system_message = (
        f"You are a helpful medical information assistant. Always remind users that your information is for "
        f"educational purposes and they should consult healthcare professionals for medical advice."
    )

    with st.spinner(t["generating_answer"]):
        assistant_text = call_llm(prompt, system_message=system_message)
        if assistant_text:
            assistant_text = strip_trailing_numbered_links(assistant_text)

    # Handle response
    if not assistant_text:
        user_friendly = t["error_message"]
        st.error(user_friendly)
        answer_to_store = user_friendly
    else:
        answer_to_store = assistant_text

    # Store conversation
    st.session_state.history.append({
        "question": q, 
        "answer": answer_to_store, 
        "sources": sources,
        "language": st.session_state.language
    })

# Display conversation history
for item in reversed(st.session_state.history):
    # Get translations for the language used when the question was asked
    item_lang_code = LANGUAGES.get(item.get("language", "English"), "en")
    item_t = TRANSLATIONS.get(item_lang_code, TRANSLATIONS["en"])
    
    st.markdown(f"**{item_t['question_prefix']}** {html.escape(item['question'])}")
    
    # Use the render function for clean display
    render_answer_and_sources(item['answer'], item['sources'])
    
    st.markdown("---")