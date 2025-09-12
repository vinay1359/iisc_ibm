# tools/text_classifier.py

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
import json
import os
import re
from datetime import datetime

# Load complaint categories
KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), "../knowledge")
CATEGORIES_PATH = os.path.join(KNOWLEDGE_PATH, "complaint-categories.json")
CLASSIFICATION_LOG_PATH = os.path.join(KNOWLEDGE_PATH, "classification_log.json")

def load_categories():
    """Load complaint categories from knowledge base"""
    try:
        with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        # Fallback categories if file not found
        return {
            "categories": {
                "electricity": {
                    "keywords": ["electricity", "power", "light", "bijli", "current", "voltage", "transformer", "meter"],
                    "subcategories": ["power_outage", "voltage_fluctuation", "transformer_fault", "billing_dispute"],
                    "typical_resolution_days": 3,
                    "priority_multiplier": 1.2
                },
                "water": {
                    "keywords": ["water", "pani", "supply", "tap", "pipeline", "leak", "quality", "pressure"],
                    "subcategories": ["supply_shortage", "quality_issue", "pipeline_leak", "billing_dispute"],
                    "typical_resolution_days": 2,
                    "priority_multiplier": 1.5
                },
                "road": {
                    "keywords": ["road", "street", "pothole", "sadak", "signal", "footpath", "construction"],
                    "subcategories": ["pothole", "traffic_signal", "street_damage", "footpath"],
                    "typical_resolution_days": 7,
                    "priority_multiplier": 0.8
                },
                "sanitation": {
                    "keywords": ["garbage", "waste", "cleaning", "safai", "drain", "toilet", "sweeping"],
                    "subcategories": ["garbage_collection", "drain_cleaning", "public_toilet", "waste_management"],
                    "typical_resolution_days": 3,
                    "priority_multiplier": 1.0
                },
                "health": {
                    "keywords": ["hospital", "doctor", "medicine", "health", "ambulance", "treatment", "clinic"],
                    "subcategories": ["hospital_service", "ambulance", "medicine_shortage", "doctor_availability"],
                    "typical_resolution_days": 1,
                    "priority_multiplier": 2.0
                }
            }
        }

def log_classification(text, category, confidence, keywords_found):
    """Log classification results for learning"""
    try:
        os.makedirs(KNOWLEDGE_PATH, exist_ok=True)
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "text_sample": text[:200] + "..." if len(text) > 200 else text,
            "classified_category": category,
            "confidence": confidence,
            "keywords_found": keywords_found
        }
        
        logs = []
        if os.path.exists(CLASSIFICATION_LOG_PATH):
            with open(CLASSIFICATION_LOG_PATH, "r", encoding="utf-8") as f:
                logs = json.load(f)
        
        logs.append(log_entry)
        
        # Keep only last 1000 classifications
        if len(logs) > 1000:
            logs = logs[-1000:]
        
        with open(CLASSIFICATION_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error logging classification: {e}")

@tool(
    name="text_classifier",
    description="Classifies complaint text into appropriate government service categories",
    permission=ToolPermission.READ_ONLY
)
def classify_complaint(text: str, location: str = "", context: dict = {}) -> dict:
    """
    Classify complaint text into service categories.
    
    Args:
        text (str): Complaint text to classify
        location (str): Location context for classification
        context (dict): Additional context information
        
    Returns:
        dict: Classification results with category, confidence, and metadata
    """
    if not text or not text.strip():
        return {
            "category": "general",
            "subcategory": "unclassified",
            "confidence": 0.0,
            "keywords_found": [],
            "department": "District Collector Office",
            "estimated_resolution_days": 7,
            "priority_multiplier": 1.0
        }
    
    # Load categories
    categories_data = load_categories()
    categories = categories_data.get("categories", {})
    
    # Normalize text for analysis
    text_lower = text.lower().strip()
    words = re.findall(r'\b\w+\b', text_lower)
    
    # Score each category
    category_scores = {}
    all_keywords_found = {}
    
    for category, category_info in categories.items():
        keywords = category_info.get("keywords", [])
        keywords_found = []
        
        # Count keyword matches
        score = 0
        for keyword in keywords:
            if keyword.lower() in text_lower:
                keywords_found.append(keyword)
                # Weight longer keywords more heavily
                weight = len(keyword) / 5.0  # Normalize weight
                score += weight
        
        # Bonus for multiple keyword matches
        if len(keywords_found) > 1:
            score *= 1.2
        
        # Context-based adjustments
        if location:
            location_lower = location.lower()
            if category == "water" and any(term in location_lower for term in ["colony", "residential"]):
                score *= 1.1
            elif category == "road" and any(term in location_lower for term in ["highway", "main", "road"]):
                score *= 1.1
        
        if score > 0:
            category_scores[category] = score
            all_keywords_found[category] = keywords_found
    
    # Determine best category
    if not category_scores:
        best_category = "general"
        confidence = 0.3
        keywords_found = []
        category_info = {
            "subcategories": ["administrative"],
            "typical_resolution_days": 7,
            "priority_multiplier": 1.0
        }
    else:
        best_category = max(category_scores.items(), key=lambda x: x[1])[0]
        max_score = category_scores[best_category]
        
        # Calculate confidence (0-1 scale)
        total_score = sum(category_scores.values())
        confidence = min(max_score / max(total_score, 1.0), 1.0)
        
        keywords_found = all_keywords_found.get(best_category, [])
        category_info = categories.get(best_category, {})
    
    # Determine subcategory
    subcategories = category_info.get("subcategories", ["general"])
    subcategory = subcategories[0]  # Default to first subcategory
    
    # Try to match subcategory based on text
    for sub in subcategories:
        sub_keywords = sub.replace("_", " ").split()
        if any(keyword in text_lower for keyword in sub_keywords):
            subcategory = sub
            break
    
    # Map category to department
    department_mapping = {
        "electricity": "Delhi Electricity Regulatory Commission (DERC)",
        "water": "Delhi Jal Board (DJB)",
        "road": "Public Works Department (PWD)", 
        "sanitation": "Municipal Corporation of Delhi (MCD)",
        "health": "Department of Health & Family Welfare (DHFW)",
        "general": "District Collector Office"
    }
    
    result = {
        "category": best_category,
        "subcategory": subcategory,
        "confidence": round(confidence, 2),
        "keywords_found": keywords_found,
        "department": department_mapping.get(best_category, "District Collector Office"),
        "estimated_resolution_days": category_info.get("typical_resolution_days", 7),
        "priority_multiplier": category_info.get("priority_multiplier", 1.0),
        "alternative_categories": {k: round(v, 2) for k, v in category_scores.items() if k != best_category and v > 0.1},
        "total_categories_considered": len(categories)
    }
    
    # Log classification
    log_classification(text, best_category, confidence, keywords_found)
    
    return result