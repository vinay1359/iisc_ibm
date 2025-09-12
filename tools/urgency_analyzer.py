# tools/urgency_analyzer.py

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
import json
import os
import re
from datetime import datetime

KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), "../knowledge")
URGENCY_LOG_PATH = os.path.join(KNOWLEDGE_PATH, "urgency_analysis_log.json")

# Urgency keywords and patterns
URGENCY_INDICATORS = {
    "CRITICAL": {
        "keywords": [
            "emergency", "urgent", "critical", "life threatening", "danger", "fire", "accident", 
            "medical", "ambulance", "hospital", "death", "injury", "blood", "heart attack",
            "emergency", "तुरंत", "आपातकाल", "खतरा", "जान", "मृत्यु", "चोट", "एम्बुलेंस"
        ],
        "patterns": [
            r"no water.*days", r"no electricity.*days", r"complete.*breakdown", 
            r"emergency.*help", r"life.*danger", r"immediate.*help"
        ],
        "multiplier": 2.0,
        "max_response_hours": 2
    },
    "HIGH": {
        "keywords": [
            "broken", "not working", "completely", "totally", "failed", "burst", "overflow", 
            "flooding", "blocked", "stopped", "dark", "blackout", "many people", "entire area",
            "बिल्कुल", "टूटा", "बंद", "काम नहीं", "पूरा", "सभी लोग", "पूरे इलाके"
        ],
        "patterns": [
            r"entire.*area", r"whole.*locality", r"many.*people", r"complete.*failure",
            r"totally.*broken", r"not working.*all"
        ],
        "multiplier": 1.5,
        "max_response_hours": 24
    },
    "MEDIUM": {
        "keywords": [
            "problem", "issue", "trouble", "difficulty", "poor", "low", "weak", "irregular",
            "sometimes", "often", "frequently", "समस्या", "परेशानी", "दिक्कत", "कभी कभी"
        ],
        "patterns": [
            r"poor.*quality", r"low.*pressure", r"irregular.*supply", 
            r"sometimes.*works", r"frequent.*problems"
        ],
        "multiplier": 1.0,
        "max_response_hours": 48
    },
    "LOW": {
        "keywords": [
            "request", "please", "kindly", "would like", "can you", "minor", "small", 
            "little", "slight", "निवेदन", "कृपया", "छोटी", "थोड़ी"
        ],
        "patterns": [
            r"can.*please", r"would.*appreciate", r"kindly.*help", 
            r"minor.*issue", r"small.*problem"
        ],
        "multiplier": 0.8,
        "max_response_hours": 72
    }
}

# Category-specific urgency adjustments
CATEGORY_URGENCY_WEIGHTS = {
    "health": 2.0,
    "electricity": 1.3,
    "water": 1.5,
    "sanitation": 1.0,
    "road": 0.8,
    "general": 0.7
}

def log_urgency_analysis(text, urgency, factors):
    """Log urgency analysis for learning"""
    try:
        os.makedirs(KNOWLEDGE_PATH, exist_ok=True)
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "text_sample": text[:200] + "..." if len(text) > 200 else text,
            "urgency_level": urgency,
            "contributing_factors": factors
        }
        
        logs = []
        if os.path.exists(URGENCY_LOG_PATH):
            with open(URGENCY_LOG_PATH, "r", encoding="utf-8") as f:
                logs = json.load(f)
        
        logs.append(log_entry)
        
        # Keep only last 1000 entries
        if len(logs) > 1000:
            logs = logs[-1000:]
        
        with open(URGENCY_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error logging urgency analysis: {e}")

@tool(
    name="urgency_analyzer", 
    description="Analyzes complaint urgency level for proper prioritization and response timing",
    permission=ToolPermission.READ_ONLY
)
def analyze_urgency(text: str, category: str = "general", location: str = "", context: dict = {}) -> dict:
    """
    Analyze the urgency level of a complaint.
    
    Args:
        text (str): Complaint text to analyze
        category (str): Complaint category
        location (str): Location context
        context (dict): Additional context (time, affected people, etc.)
        
    Returns:
        dict: Urgency analysis with level, factors, and response timelines
    """
    if not text or not text.strip():
        return {
            "urgency_level": "MEDIUM",
            "urgency_score": 1.0,
            "max_response_hours": 48,
            "factors_identified": [],
            "category_weight": 1.0,
            "recommended_sla": "48 hours response, 7 days resolution"
        }
    
    text_lower = text.lower().strip()
    urgency_scores = {}
    factors_identified = []
    
    # Analyze against each urgency level
    for level, indicators in URGENCY_INDICATORS.items():
        score = 0
        level_factors = []
        
        # Check keywords
        for keyword in indicators["keywords"]:
            if keyword.lower() in text_lower:
                score += 1
                level_factors.append(f"keyword: {keyword}")
        
        # Check patterns
        for pattern in indicators["patterns"]:
            if re.search(pattern, text_lower):
                score += 2  # Patterns are weighted higher
                level_factors.append(f"pattern: {pattern}")
        
        # Apply multiplier
        if score > 0:
            score *= indicators["multiplier"]
            urgency_scores[level] = score
            factors_identified.extend(level_factors)
    
    # Determine primary urgency level
    if not urgency_scores:
        urgency_level = "MEDIUM"
        urgency_score = 1.0
        max_response_hours = 48
    else:
        urgency_level = max(urgency_scores.items(), key=lambda x: x[1])[0]
        urgency_score = urgency_scores[urgency_level]
        max_response_hours = URGENCY_INDICATORS[urgency_level]["max_response_hours"]
    
    # Apply category-specific weight
    category_weight = CATEGORY_URGENCY_WEIGHTS.get(category.lower(), 1.0)
    adjusted_score = urgency_score * category_weight
    
    # Context-based adjustments
    context_factors = []
    
    # Time-based urgency
    current_hour = datetime.now().hour
    if current_hour < 6 or current_hour > 22:  # Night time
        if urgency_level == "CRITICAL":
            context_factors.append("night_time_critical")
            max_response_hours = min(max_response_hours, 1)  # Even more urgent at night
    
    # Location-based urgency
    if location:
        location_lower = location.lower()
        if any(term in location_lower for term in ["hospital", "school", "market", "main"]):
            context_factors.append("high_impact_location")
            adjusted_score *= 1.2
    
    # Number of people affected (if mentioned in text)
    people_patterns = [
        r"(\d+)\s*people", r"entire.*area", r"whole.*colony", r"many.*families",
        r"सभी लोग", r"बहुत से लोग", r"पूरे इलाके"
    ]
    for pattern in people_patterns:
        if re.search(pattern, text_lower):
            context_factors.append("multiple_people_affected")
            adjusted_score *= 1.3
            break
    
    # Duration mentioned (problem persisting)
    duration_patterns = [
        r"(\d+)\s*days?", r"weeks?", r"months?", r"long time", r"since.*days",
        r"(\d+)\s*दिन", r"हफ्तों से", r"महीनों से"
    ]
    for pattern in duration_patterns:
        match = re.search(pattern, text_lower)
        if match:
            context_factors.append("long_duration_problem")
            adjusted_score *= 1.4
            break
    
    # Re-evaluate urgency level after adjustments
    if adjusted_score >= 4.0:
        final_urgency = "CRITICAL"
        max_response_hours = 2
        sla_text = "2 hours response, 24 hours resolution"
    elif adjusted_score >= 2.5:
        final_urgency = "HIGH"
        max_response_hours = 24
        sla_text = "24 hours response, 3-5 days resolution"
    elif adjusted_score >= 1.2:
        final_urgency = "MEDIUM"
        max_response_hours = 48
        sla_text = "48 hours response, 5-10 days resolution"
    else:
        final_urgency = "LOW"
        max_response_hours = 72
        sla_text = "72 hours response, 2-4 weeks resolution"
    
    # Prepare result
    result = {
        "urgency_level": final_urgency,
        "urgency_score": round(adjusted_score, 2),
        "max_response_hours": max_response_hours,
        "factors_identified": factors_identified + context_factors,
        "category_weight": category_weight,
        "recommended_sla": sla_text,
        "escalation_triggers": {
            "no_acknowledgment_hours": max_response_hours,
            "no_progress_hours": max_response_hours * 2,
            "overdue_threshold_hours": max_response_hours * 3
        },
        "priority_score": round(adjusted_score, 2)
    }
    
    # Log analysis
    log_urgency_analysis(text, final_urgency, factors_identified + context_factors)
    
    return result