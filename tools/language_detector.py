# tools/language_detector.py

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
import re
import json
import os
from datetime import datetime

# Language keywords for basic detection
LANGUAGE_PATTERNS = {
    'hindi': [
        'है', 'में', 'का', 'को', 'से', 'की', 'के', 'और', 'यह', 'वह', 'हम', 'तुम', 'आप',
        'समस्या', 'शिकायत', 'सरकार', 'विभाग', 'काम', 'पानी', 'बिजली', 'सड़क', 'सफाई'
    ],
    'english': [
        'the', 'and', 'is', 'in', 'to', 'of', 'a', 'that', 'it', 'with', 'for', 'as', 'was',
        'complaint', 'problem', 'issue', 'government', 'department', 'service', 'help'
    ],
    'punjabi': ['ਹੈ', 'ਵਿੱਚ', 'ਦਾ', 'ਨੂੰ', 'ਤੋਂ', 'ਅਤੇ', 'ਇਹ', 'ਸਮੱਸਿਆ'],
    'bengali': ['হয়', 'এর', 'একটি', 'থেকে', 'এবং', 'সমস্যা', 'অভিযোগ'],
    'tamil': ['இல்', 'ஒரு', 'மற்றும்', 'இது', 'சிக்கல்', 'புகார்'],
    'telugu': ['లో', 'ఒక', 'మరియు', 'ఇది', 'సమస్య', 'ఫిర్యాదు'],
    'gujarati': ['છે', 'માં', 'એક', 'અને', 'આ', 'સમસ્યા', 'ફરિયાદ'],
    'marathi': ['आहे', 'मध्ये', 'एक', 'आणि', 'हे', 'समस्या', 'तक्रार']
}

# Knowledge path for storing detection results
KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), "../knowledge")
LANGUAGE_LOG_PATH = os.path.join(KNOWLEDGE_PATH, "language_detection_log.json")

def ensure_knowledge_dir():
    """Ensure knowledge directory exists"""
    os.makedirs(KNOWLEDGE_PATH, exist_ok=True)

def log_detection(text, detected_language, confidence):
    """Log language detection for analytics"""
    ensure_knowledge_dir()
    
    log_entry = {
        "timestamp": str(datetime.now()),
        "text_sample": text[:100] + "..." if len(text) > 100 else text,
        "detected_language": detected_language,
        "confidence": confidence
    }
    
    try:
        if os.path.exists(LANGUAGE_LOG_PATH):
            with open(LANGUAGE_LOG_PATH, "r", encoding="utf-8") as f:
                logs = json.load(f)
        else:
            logs = []
        
        logs.append(log_entry)
        
        # Keep only last 1000 entries
        if len(logs) > 1000:
            logs = logs[-1000:]
        
        with open(LANGUAGE_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error logging language detection: {e}")

@tool(
    name="language_detector",
    description="Detects the language of input text for multilingual complaint processing",
    permission=ToolPermission.READ_ONLY
)
def detect_language(text: str) -> dict:
    """
    Detect the primary language of the input text.
    
    Args:
        text (str): Input text to analyze
        
    Returns:
        dict: Language detection results with confidence scores
    """
    if not text or not text.strip():
        return {
            "primary_language": "unknown",
            "confidence": 0.0,
            "all_languages": {},
            "is_multilingual": False
        }
    
    # Clean and normalize text
    text_lower = text.lower().strip()
    words = re.findall(r'\b\w+\b', text_lower)
    
    if not words:
        return {
            "primary_language": "unknown", 
            "confidence": 0.0,
            "all_languages": {},
            "is_multilingual": False
        }
    
    # Score languages based on keyword matches
    language_scores = {}
    total_words = len(words)
    
    for language, keywords in LANGUAGE_PATTERNS.items():
        matches = sum(1 for word in words if word in keywords)
        score = matches / total_words if total_words > 0 else 0
        if score > 0:
            language_scores[language] = score
    
    # Determine primary language
    if not language_scores:
        # Default detection based on character sets
        if any(ord(char) > 2304 and ord(char) < 2432 for char in text):  # Devanagari
            primary_language = "hindi"
            confidence = 0.7
        elif re.search(r'[a-zA-Z]', text):
            primary_language = "english"
            confidence = 0.8
        else:
            primary_language = "unknown"
            confidence = 0.0
    else:
        primary_language = max(language_scores.items(), key=lambda x: x[1])[0]
        confidence = min(language_scores[primary_language] * 2, 1.0)  # Scale confidence
    
    # Check if multilingual
    significant_languages = {lang: score for lang, score in language_scores.items() if score > 0.1}
    is_multilingual = len(significant_languages) > 1
    
    result = {
        "primary_language": primary_language,
        "confidence": round(confidence, 2),
        "all_languages": {k: round(v, 2) for k, v in language_scores.items()},
        "is_multilingual": is_multilingual,
        "word_count": total_words,
        "supported_translation": primary_language in LANGUAGE_PATTERNS
    }
    
    # Log detection for analytics
    try:
        from datetime import datetime
        log_detection(text, primary_language, confidence)
    except Exception:
        pass  # Don't fail if logging fails
    
    return result