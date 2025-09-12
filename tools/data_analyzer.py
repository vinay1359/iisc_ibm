# tools/data_analyzer.py

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
import os
import json

# Paths to knowledge files
KNOWLEDGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../knowledge"))
CATEGORY_PATH = os.path.join(KNOWLEDGE_DIR, "complaint-categories.json")
HISTORICAL_PATH = os.path.join(KNOWLEDGE_DIR, "complaints.json")
ACTIVE_PATH = os.path.join(KNOWLEDGE_DIR, "active_complaints.json")
LOG_FILES = [
    "classification_log.json",
    "urgency_analysis_log.json",
    "routing_log.json",
    "status_monitoring_log.json",
    "sent_reminders_log.json",
    "deadline_calculations.json"
]

def load_data():
    """Load all available data sources"""
    data_sources = {}

    # Load categories
    try:
        with open(CATEGORY_PATH, "r", encoding="utf-8") as f:
            data_sources["categories"] = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data_sources["categories"] = {"categories": {}}

    # Load historical complaints
    try:
        with open(HISTORICAL_PATH, "r", encoding="utf-8") as f:
            data_sources["historical"] = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data_sources["historical"] = []

    # Load active complaints
    try:
        with open(ACTIVE_PATH, "r", encoding="utf-8") as f:
            active_data = json.load(f)
            data_sources["active"] = list(active_data.get("complaints", {}).values())
    except (FileNotFoundError, json.JSONDecodeError):
        data_sources["active"] = []

    # Load logs
    for log_file in LOG_FILES:
        path = os.path.join(KNOWLEDGE_DIR, log_file)
        key = log_file.replace(".json", "")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data_sources[key] = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data_sources[key] = []

    return data_sources

@tool(
    name="data_analyzer",
    description="Analyzes complaint data for patterns, trends, and insights",
    permission=ToolPermission.READ_ONLY
)
def analyze_data(analysis_type: str = "summary", filters: dict = {}) -> dict:
    """
    Analyze complaint data based on provided parameters.
    """
    data = load_data()

    # Example: simple statistics
    categories = data.get("categories", {}).get("categories", {})
    stats = {cat: len(info.get("subcategories", [])) for cat, info in categories.items()}
    total_complaints = sum(stats.values())

    return {
        "summary_statistics": {
            "total_complaints": total_complaints,
            "active_complaints": len(data.get("active", [])),
            "historical_complaints": len(data.get("historical", []))
        },
        "category_breakdown": stats,
        "logs_available": list(data.keys())
    }
