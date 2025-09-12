# tools/department_mapper.py

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
import json
import os
from datetime import datetime

KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), "../knowledge")
DEPARTMENT_CONTACTS_PATH = os.path.join(KNOWLEDGE_PATH, "department-contacts.json")
ROUTING_LOG_PATH = os.path.join(KNOWLEDGE_PATH, "routing_log.json")

def load_department_contacts():
    """Load department contact information"""
    try:
        with open(DEPARTMENT_CONTACTS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        # Fallback department data
        return {
            "departments": {
                "electricity": {
                    "name": "Delhi Electricity Regulatory Commission",
                    "code": "DERC",
                    "email": "complaints@derc.gov.in",
                    "phone": "011-23379920",
                    "emergency": "1912",
                    "head": "Chairperson, DERC",
                    "response_sla": 48,
                    "resolution_sla": 120
                },
                "water": {
                    "name": "Delhi Jal Board",
                    "code": "DJB",
                    "email": "complaints@delhijalboard.nic.in",
                    "phone": "1916",
                    "emergency": "1916",
                    "head": "CEO, Delhi Jal Board",
                    "response_sla": 24,
                    "resolution_sla": 72
                },
                "road": {
                    "name": "Public Works Department",
                    "code": "PWD",
                    "email": "complaints@delhipwd.gov.in", 
                    "phone": "011-23392400",
                    "emergency": "1073",
                    "head": "Chief Engineer, PWD",
                    "response_sla": 72,
                    "resolution_sla": 168
                },
                "sanitation": {
                    "name": "Municipal Corporation of Delhi",
                    "code": "MCD",
                    "email": "complaints@mcdonline.gov.in",
                    "phone": "1800-11-0095",
                    "emergency": "1073", 
                    "head": "Commissioner, MCD",
                    "response_sla": 48,
                    "resolution_sla": 120
                },
                "health": {
                    "name": "Department of Health & Family Welfare",
                    "code": "DHFW",
                    "email": "health@delhi.gov.in",
                    "phone": "011-23392155",
                    "emergency": "102",
                    "head": "Director, Health Services",
                    "response_sla": 12,
                    "resolution_sla": 48
                },
                "general": {
                    "name": "District Collector Office",
                    "code": "DCO",
                    "email": "collector@delhi.gov.in",
                    "phone": "011-23392000",
                    "emergency": "100",
                    "head": "District Collector",
                    "response_sla": 48,
                    "resolution_sla": 168
                }
            }
        }

def log_routing_decision(category, department, justification):
    """Log routing decisions for analytics"""
    try:
        os.makedirs(KNOWLEDGE_PATH, exist_ok=True)
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "category": category,
            "assigned_department": department,
            "routing_justification": justification
        }
        
        logs = []
        if os.path.exists(ROUTING_LOG_PATH):
            with open(ROUTING_LOG_PATH, "r", encoding="utf-8") as f:
                logs = json.load(f)
        
        logs.append(log_entry)
        
        # Keep only last 1000 entries
        if len(logs) > 1000:
            logs = logs[-1000:]
        
        with open(ROUTING_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error logging routing decision: {e}")

@tool(
    name="department_mapper",
    description="Maps complaint categories to appropriate government departments with contact details",
    permission=ToolPermission.READ_ONLY
)
def map_to_department(category: str, subcategory: str = "", urgency: str = "MEDIUM", location: str = "") -> dict:
    """
    Map complaint to appropriate department with full contact details.
    
    Args:
        category (str): Complaint category
        subcategory (str): Specific subcategory
        urgency (str): Urgency level
        location (str): Location for area-specific routing
        
    Returns:
        dict: Department mapping with contact details and SLAs
    """
    departments_data = load_department_contacts()
    departments = departments_data.get("departments", {})
    
    # Primary mapping
    category_lower = category.lower().strip()
    department_key = category_lower if category_lower in departments else "general"
    
    # Special routing logic
    routing_justification = f"Standard mapping for {category} category"
    
    # Handle special cases
    if subcategory:
        sub_lower = subcategory.lower()
        
        # Billing disputes can go to multiple departments
        if "billing" in sub_lower:
            routing_justification += f" with billing subcategory"
        
        # Emergency services routing
        if "emergency" in sub_lower or urgency == "CRITICAL":
            routing_justification += f" - escalated due to {urgency} urgency"
    
    # Location-based routing adjustments
    if location:
        location_lower = location.lower()
        if any(area in location_lower for area in ["hospital", "medical", "clinic"]):
            if category_lower not in ["health"]:
                routing_justification += " - location near medical facility considered"
    
    # Get department info
    dept_info = departments.get(department_key, departments.get("general", {}))
    
    # Adjust SLAs based on urgency
    base_response_sla = dept_info.get("response_sla", 48)
    base_resolution_sla = dept_info.get("resolution_sla", 168)
    
    urgency_multipliers = {
        "CRITICAL": 0.25,
        "HIGH": 0.5,
        "MEDIUM": 1.0,
        "LOW": 1.5
    }
    
    multiplier = urgency_multipliers.get(urgency, 1.0)
    adjusted_response_sla = max(int(base_response_sla * multiplier), 1)
    adjusted_resolution_sla = max(int(base_resolution_sla * multiplier), 4)
    
    # Escalation path
    escalation_contacts = []
    if department_key != "general":
        escalation_contacts.append({
            "level": 1,
            "title": "Department Head", 
            "contact": dept_info.get("head", "Department Head"),
            "trigger_hours": adjusted_response_sla + 24
        })
    
    escalation_contacts.extend([
        {
            "level": 2,
            "title": "District Authority",
            "contact": "District Collector",
            "email": "collector@delhi.gov.in",
            "trigger_hours": adjusted_response_sla + 72
        },
        {
            "level": 3,
            "title": "State Secretariat", 
            "contact": "Chief Secretary",
            "email": "cs@delhi.gov.in",
            "trigger_hours": adjusted_response_sla + 168
        },
        {
            "level": 4,
            "title": "Political Executive",
            "contact": "Chief Minister's Office",
            "email": "cmo@delhi.gov.in", 
            "trigger_hours": adjusted_response_sla + 336
        }
    ])
    
    result = {
        "assigned_department": {
            "name": dept_info.get("name", "District Collector Office"),
            "code": dept_info.get("code", "DCO"),
            "category_key": department_key
        },
        "contact_details": {
            "primary_email": dept_info.get("email", "collector@delhi.gov.in"),
            "primary_phone": dept_info.get("phone", "011-23392000"),
            "emergency_number": dept_info.get("emergency", "100"),
            "department_head": dept_info.get("head", "District Collector"),
            "address": dept_info.get("address", "District Collector Office, Delhi")
        },
        "service_level_agreements": {
            "acknowledgment_deadline_hours": adjusted_response_sla,
            "resolution_deadline_hours": adjusted_resolution_sla,
            "base_response_sla": base_response_sla,
            "base_resolution_sla": base_resolution_sla,
            "urgency_multiplier": multiplier
        },
        "escalation_path": escalation_contacts,
        "routing_metadata": {
            "routing_justification": routing_justification,
            "primary_category": category,
            "subcategory": subcategory,
            "urgency_considered": urgency,
            "location_factor": bool(location),
            "routing_timestamp": datetime.now().isoformat()
        },
        "automated_actions": {
            "initial_reminder_hours": adjusted_response_sla * 0.75,
            "follow_up_reminder_hours": adjusted_response_sla,
            "escalation_trigger_hours": adjusted_response_sla + 24,
            "auto_escalation_enabled": urgency in ["CRITICAL", "HIGH"]
        }
    }
    
    # Log routing decision
    log_routing_decision(category, dept_info.get("name", "Unknown"), routing_justification)
    
    return result