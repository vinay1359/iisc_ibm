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
def analyze_data(complaints: list = None, analysis_type: str = "summary", filters: dict = None, focus_complaint_id: str = None) -> dict:
    """
    Analyze complaint data based on provided parameters.
    
    Args:
        complaints (list): List of complaint objects to analyze
        analysis_type (str): Type of analysis to perform (summary, trends, performance)
        filters (dict): Filters to apply to the data
        focus_complaint_id (str): Specific complaint ID to focus on
    
    Returns:
        dict: Analysis results with summary, metrics, insights, and recommendations
    """
    # Handle None values
    if complaints is None:
        complaints = []
    if filters is None:
        filters = {}
    
    # Load additional data if complaints list is empty
    if not complaints:
        data = load_data()
        complaints = data.get("active", []) + data.get("historical", [])
    
    # Basic analysis
    if not complaints:
        return {
            "summary": {
                "total_complaints": 0,
                "message": "No complaint data available"
            },
            "metrics": {},
            "insights": ["No data available for analysis"],
            "recommendations": ["Start collecting complaint data"]
        }
    
    # Apply filters if provided
    filtered_complaints = complaints
    if filters:
        if filters.get("category"):
            filtered_complaints = [c for c in filtered_complaints if c.get("category") == filters["category"]]
        if filters.get("status"):
            filtered_complaints = [c for c in filtered_complaints if c.get("status") == filters["status"]]
        if filters.get("urgency"):
            filtered_complaints = [c for c in filtered_complaints if c.get("urgency") == filters["urgency"]]
    
    # Perform analysis
    total_complaints = len(filtered_complaints)
    
    # Category breakdown
    categories = {}
    statuses = {}
    urgencies = {}
    departments = {}
    
    for complaint in filtered_complaints:
        # Count categories
        cat = complaint.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1
        
        # Count statuses
        status = complaint.get("status", "unknown")
        statuses[status] = statuses.get(status, 0) + 1
        
        # Count urgencies
        urgency = complaint.get("urgency", "unknown")
        urgencies[urgency] = urgencies.get(urgency, 0) + 1
        
        # Count departments
        dept = complaint.get("assigned_department", "unassigned")
        departments[dept] = departments.get(dept, 0) + 1
    
    # Calculate metrics
    resolved_count = statuses.get("BLACK", 0) + statuses.get("RESOLVED", 0)
    resolution_rate = (resolved_count / total_complaints * 100) if total_complaints > 0 else 0
    
    critical_count = urgencies.get("CRITICAL", 0)
    high_count = urgencies.get("HIGH", 0)
    priority_rate = ((critical_count + high_count) / total_complaints * 100) if total_complaints > 0 else 0
    
    # Generate insights
    insights = []
    recommendations = []
    
    if total_complaints > 0:
        # Top category insight
        if categories:
            top_category = max(categories, key=categories.get)
            insights.append(f"Most complaints are in '{top_category}' category ({categories[top_category]} complaints)")
        
        # Resolution rate insight
        if resolution_rate < 50:
            insights.append(f"Low resolution rate: {resolution_rate:.1f}%")
            recommendations.append("Improve complaint resolution processes")
        else:
            insights.append(f"Good resolution rate: {resolution_rate:.1f}%")
        
        # Priority complaints insight
        if priority_rate > 30:
            insights.append(f"High priority complaints: {priority_rate:.1f}% are CRITICAL/HIGH")
            recommendations.append("Focus on reducing high-priority complaint backlog")
        
        # Department performance
        if departments:
            busiest_dept = max(departments, key=departments.get)
            insights.append(f"Busiest department: {busiest_dept} ({departments[busiest_dept]} complaints)")
    
    # Focus on specific complaint if provided
    focus_info = {}
    if focus_complaint_id:
        focus_complaint = next((c for c in filtered_complaints if c.get("id") == focus_complaint_id), None)
        if focus_complaint:
            focus_info = {
                "complaint_id": focus_complaint_id,
                "category": focus_complaint.get("category"),
                "status": focus_complaint.get("status"),
                "urgency": focus_complaint.get("urgency"),
                "department": focus_complaint.get("assigned_department")
            }
            insights.append(f"Focus complaint {focus_complaint_id} is in {focus_complaint.get('category')} category")
    
    return {
        "summary": {
            "total_complaints": total_complaints,
            "active_complaints": len([c for c in filtered_complaints if c.get("status") not in ["BLACK", "RESOLVED"]]),
            "resolved_complaints": resolved_count,
            "resolution_rate": round(resolution_rate, 2),
            "priority_complaints": critical_count + high_count,
            "focus_complaint": focus_info if focus_info else None
        },
        "metrics": {
            "categories": categories,
            "statuses": statuses,
            "urgencies": urgencies,
            "departments": departments,
            "resolution_rate": round(resolution_rate, 2),
            "priority_rate": round(priority_rate, 2)
        },
        "insights": insights,
        "recommendations": recommendations,
        "analysis_type": analysis_type,
        "filters_applied": filters
    }