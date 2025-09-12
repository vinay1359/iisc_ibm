# tools/deadline_calculator.py

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from datetime import datetime, timedelta
import json
import os

KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), "../knowledge")
DEADLINE_LOG_PATH = os.path.join(KNOWLEDGE_PATH, "deadline_calculations.json")

# Business hours and holidays configuration
BUSINESS_HOURS = {
    "start_hour": 9,
    "end_hour": 18,
    "working_days": [0, 1, 2, 3, 4, 5],  # Monday to Saturday (0=Monday)
    "holidays": [
        "2025-01-26",  # Republic Day
        "2025-08-15",  # Independence Day
        "2025-10-02",  # Gandhi Jayanti
        "2025-12-25"   # Christmas
    ]
}

def is_working_day(date):
    """Check if a given date is a working day"""
    if date.weekday() not in BUSINESS_HOURS["working_days"]:
        return False
    if date.strftime("%Y-%m-%d") in BUSINESS_HOURS["holidays"]:
        return False
    return True

def add_business_hours(start_time, hours_to_add):
    """Add business hours to a datetime, skipping weekends and holidays"""
    current_time = start_time
    remaining_hours = hours_to_add
    
    while remaining_hours > 0:
        # Skip to next working day if current day is not working
        while not is_working_day(current_time):
            current_time += timedelta(days=1)
            current_time = current_time.replace(hour=BUSINESS_HOURS["start_hour"], minute=0, second=0)
        
        # Calculate hours available in current working day
        if current_time.hour < BUSINESS_HOURS["start_hour"]:
            current_time = current_time.replace(hour=BUSINESS_HOURS["start_hour"], minute=0, second=0)
        
        hours_left_today = max(0, BUSINESS_HOURS["end_hour"] - current_time.hour)
        
        if remaining_hours <= hours_left_today:
            # Can finish today
            current_time += timedelta(hours=remaining_hours)
            remaining_hours = 0
        else:
            # Move to next working day
            remaining_hours -= hours_left_today
            current_time += timedelta(days=1)
            current_time = current_time.replace(hour=BUSINESS_HOURS["start_hour"], minute=0, second=0)
    
    return current_time

def log_deadline_calculation(urgency, category, acknowledgment_deadline, resolution_deadline):
    """Log deadline calculations for analytics"""
    try:
        os.makedirs(KNOWLEDGE_PATH, exist_ok=True)
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "urgency_level": urgency,
            "category": category,
            "acknowledgment_deadline": acknowledgment_deadline.isoformat(),
            "resolution_deadline": resolution_deadline.isoformat()
        }
        
        logs = []
        if os.path.exists(DEADLINE_LOG_PATH):
            with open(DEADLINE_LOG_PATH, "r", encoding="utf-8") as f:
                logs = json.load(f)
        
        logs.append(log_entry)
        
        if len(logs) > 1000:
            logs = logs[-1000:]
        
        with open(DEADLINE_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error logging deadline calculation: {e}")

@tool(
    name="deadline_calculator",
    description="Calculates acknowledgment and resolution deadlines based on urgency and category",
    permission=ToolPermission.READ_ONLY
)
def calculate_deadlines(urgency: str, category: str, submission_time: str = "", context: dict = {}) -> dict:
    """
    Calculate acknowledgment and resolution deadlines.
    
    Args:
        urgency (str): Urgency level (CRITICAL, HIGH, MEDIUM, LOW)
        category (str): Complaint category
        submission_time (str): ISO format submission time (default: now)
        context (dict): Additional context factors
        
    Returns:
        dict: Calculated deadlines and timeline information
    """
    
    # Parse submission time
    if submission_time:
        try:
            start_time = datetime.fromisoformat(submission_time.replace('Z', '+00:00'))
        except:
            start_time = datetime.now()
    else:
        start_time = datetime.now()
    
    # Base SLA hours by urgency
    urgency_slas = {
        "CRITICAL": {"acknowledgment": 2, "resolution": 24},
        "HIGH": {"acknowledgment": 24, "resolution": 72}, 
        "MEDIUM": {"acknowledgment": 48, "resolution": 168},
        "LOW": {"acknowledgment": 72, "resolution": 336}
    }
    
    # Category-specific adjustments
    category_adjustments = {
        "health": {"ack_multiplier": 0.5, "res_multiplier": 0.5},
        "electricity": {"ack_multiplier": 0.8, "res_multiplier": 0.9},
        "water": {"ack_multiplier": 0.7, "res_multiplier": 0.8},
        "sanitation": {"ack_multiplier": 1.0, "res_multiplier": 1.0},
        "road": {"ack_multiplier": 1.2, "res_multiplier": 1.3},
        "general": {"ack_multiplier": 1.0, "res_multiplier": 1.0}
    }
    
    # Get base SLA
    base_sla = urgency_slas.get(urgency, urgency_slas["MEDIUM"])
    ack_hours = base_sla["acknowledgment"]
    res_hours = base_sla["resolution"]
    
    # Apply category adjustments
    category_adj = category_adjustments.get(category.lower(), {"ack_multiplier": 1.0, "res_multiplier": 1.0})
    ack_hours = max(1, int(ack_hours * category_adj["ack_multiplier"]))
    res_hours = max(4, int(res_hours * category_adj["res_multiplier"]))
    
    # Context-based adjustments
    context_factors = []
    
    # Weekend/holiday submissions get extended deadlines
    if not is_working_day(start_time):
        ack_hours = int(ack_hours * 1.2)
        res_hours = int(res_hours * 1.1)
        context_factors.append("weekend_holiday_submission")
    
    # Night time submissions (after business hours)
    if start_time.hour < BUSINESS_HOURS["start_hour"] or start_time.hour >= BUSINESS_HOURS["end_hour"]:
        if urgency != "CRITICAL":  # Critical complaints are 24/7
            context_factors.append("after_hours_submission")
    
    # Monsoon season adjustments for specific categories
    monsoon_months = [6, 7, 8, 9]  # June to September
    if start_time.month in monsoon_months and category.lower() in ["road", "sanitation", "water"]:
        res_hours = int(res_hours * 1.3)
        context_factors.append("monsoon_season_adjustment")
    
    # Calculate actual deadlines
    if urgency == "CRITICAL":
        # Critical complaints are handled 24/7
        acknowledgment_deadline = start_time + timedelta(hours=ack_hours)
        resolution_deadline = start_time + timedelta(hours=res_hours)
        calculation_method = "24_7_continuous"
    else:
        # Regular complaints follow business hours
        acknowledgment_deadline = add_business_hours(start_time, ack_hours)
        resolution_deadline = add_business_hours(start_time, res_hours)
        calculation_method = "business_hours_only"
    
    # Calculate reminder schedules
    total_ack_duration = (acknowledgment_deadline - start_time).total_seconds() / 3600
    total_res_duration = (resolution_deadline - start_time).total_seconds() / 3600
    
    # Reminder timeline
    reminder_schedule = []
    
    # 50% reminder for acknowledgment
    reminder_50 = start_time + timedelta(hours=total_ack_duration * 0.5)
    reminder_schedule.append({
        "type": "acknowledgment_50_percent",
        "datetime": reminder_50.isoformat(),
        "description": "Gentle reminder - 50% of acknowledgment deadline passed"
    })
    
    # 90% reminder for acknowledgment  
    reminder_90 = start_time + timedelta(hours=total_ack_duration * 0.9)
    reminder_schedule.append({
        "type": "acknowledgment_90_percent", 
        "datetime": reminder_90.isoformat(),
        "description": "Urgent reminder - 90% of acknowledgment deadline passed"
    })
    
    # Resolution progress reminders
    if total_res_duration > 48:  # Only for longer resolution times
        res_25 = start_time + timedelta(hours=total_res_duration * 0.25)
        res_75 = start_time + timedelta(hours=total_res_duration * 0.75)
        
        reminder_schedule.extend([
            {
                "type": "resolution_25_percent",
                "datetime": res_25.isoformat(),
                "description": "Progress check - 25% of resolution deadline passed"
            },
            {
                "type": "resolution_75_percent", 
                "datetime": res_75.isoformat(),
                "description": "Final warning - 75% of resolution deadline passed"
            }
        ])
    
    # Escalation triggers
    escalation_schedule = [
        {
            "level": 1,
            "trigger_datetime": (acknowledgment_deadline + timedelta(hours=24)).isoformat(),
            "condition": "No acknowledgment 24 hours past deadline",
            "action": "Escalate to Department Head"
        },
        {
            "level": 2,
            "trigger_datetime": (acknowledgment_deadline + timedelta(hours=72)).isoformat(), 
            "condition": "No response 72 hours past acknowledgment deadline",
            "action": "Escalate to District Authority"
        },
        {
            "level": 3,
            "trigger_datetime": (resolution_deadline + timedelta(hours=48)).isoformat(),
            "condition": "No resolution 48 hours past deadline", 
            "action": "Escalate to State Secretariat"
        }
    ]
    
    # Prepare result
    result = {
        "deadlines": {
            "acknowledgment_deadline": acknowledgment_deadline.isoformat(),
            "resolution_deadline": resolution_deadline.isoformat(),
            "acknowledgment_hours_from_now": ack_hours,
            "resolution_hours_from_now": res_hours
        },
        "timeline_details": {
            "submission_time": start_time.isoformat(),
            "calculation_method": calculation_method,
            "urgency_level": urgency,
            "category": category,
            "context_factors": context_factors
        },
        "reminder_schedule": reminder_schedule,
        "escalation_schedule": escalation_schedule,
        "sla_compliance": {
            "base_ack_sla": base_sla["acknowledgment"],
            "base_res_sla": base_sla["resolution"],
            "adjusted_ack_sla": ack_hours,
            "adjusted_res_sla": res_hours,
            "category_adjustment_applied": category != "general",
            "urgency_priority": urgency
        },
        "business_rules": {
            "working_hours": f"{BUSINESS_HOURS['start_hour']}:00 - {BUSINESS_HOURS['end_hour']}:00",
            "working_days": "Monday to Saturday",
            "critical_complaints_24_7": urgency == "CRITICAL",
            "holidays_considered": len(BUSINESS_HOURS["holidays"])
        }
    }
    
    # Log calculation
    log_deadline_calculation(urgency, category, acknowledgment_deadline, resolution_deadline)
    
    return result