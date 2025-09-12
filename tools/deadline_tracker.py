# tools/deadline_tracker.py

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from datetime import datetime, timedelta
import json
import os

KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), "../knowledge")
DEADLINE_TRACKING_PATH = os.path.join(KNOWLEDGE_PATH, "active_deadlines.json")
DEADLINE_ALERTS_PATH = os.path.join(KNOWLEDGE_PATH, "deadline_alerts.json")

def load_active_deadlines():
    """Load active deadline tracking data"""
    try:
        if os.path.exists(DEADLINE_TRACKING_PATH):
            with open(DEADLINE_TRACKING_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"tracked_complaints": {}, "deadline_history": []}
    except Exception as e:
        return {"tracked_complaints": {}, "deadline_history": []}

def save_active_deadlines(data):
    """Save deadline tracking data"""
    try:
        os.makedirs(KNOWLEDGE_PATH, exist_ok=True)
        with open(DEADLINE_TRACKING_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving deadline data: {e}")

def save_deadline_alerts(alerts):
    """Save deadline alerts for other agents"""
    try:
        os.makedirs(KNOWLEDGE_PATH, exist_ok=True)
        with open(DEADLINE_ALERTS_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "generated_at": datetime.now().isoformat(),
                "alerts": alerts
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving deadline alerts: {e}")

@tool(
    name="deadline_tracker",
    description="Tracks acknowledgment and resolution deadlines, generates alerts for approaching/overdue deadlines",
    permission=ToolPermission.READ_WRITE
)
def track_deadlines(complaint_id: str = "", check_all: bool = True) -> dict:
    """
    Track deadlines and generate alerts for approaching or overdue deadlines.
    
    Args:
        complaint_id (str): Specific complaint to track (optional)
        check_all (bool): Whether to check all active deadlines
        
    Returns:
        dict: Deadline tracking results with alerts and actions needed
    """
    current_time = datetime.now()
    deadline_data = load_active_deadlines()
    tracked_complaints = deadline_data.get("tracked_complaints", {})
    
    tracking_results = {
        "tracking_timestamp": current_time.isoformat(),
        "total_tracked": len(tracked_complaints),
        "approaching_deadlines": [],
        "overdue_deadlines": [],
        "alerts": [],
        "actions_required": []
    }
    
    alerts_to_save = []
    
    # Process each tracked complaint
    for cid, complaint_tracking in tracked_complaints.items():
        # Skip if filtering by specific complaint
        if complaint_id and cid != complaint_id:
            continue
            
        # Check acknowledgment deadline
        ack_deadline_str = complaint_tracking.get("acknowledgment_deadline")
        if ack_deadline_str:
            ack_deadline = datetime.fromisoformat(ack_deadline_str)
            time_to_ack_deadline = (ack_deadline - current_time).total_seconds() / 3600  # hours
            
            complaint_info = {
                "complaint_id": cid,
                "urgency": complaint_tracking.get("urgency", "MEDIUM"),
                "category": complaint_tracking.get("category", "general"),
                "department": complaint_tracking.get("assigned_department", "unknown"),
                "current_status": complaint_tracking.get("current_status", "ORANGE")
            }
            
            # Check if acknowledgment is overdue
            if time_to_ack_deadline < 0 and complaint_info["current_status"] in ["RED", "ORANGE"]:
                overdue_hours = abs(time_to_ack_deadline)
                overdue_info = {
                    **complaint_info,
                    "deadline_type": "acknowledgment",
                    "deadline": ack_deadline.isoformat(),
                    "hours_overdue": round(overdue_hours, 1),
                    "severity": "CRITICAL" if overdue_hours > 24 else "HIGH"
                }
                tracking_results["overdue_deadlines"].append(overdue_info)
                
                # Generate alert
                alert = {
                    "type": "OVERDUE_ACKNOWLEDGMENT",
                    "complaint_id": cid,
                    "severity": overdue_info["severity"],
                    "message": f"Acknowledgment overdue by {overdue_info['hours_overdue']} hours",
                    "action": "immediate_escalation" if overdue_hours > 48 else "urgent_follow_up",
                    "department": complaint_info["department"]
                }
                tracking_results["alerts"].append(alert)
                alerts_to_save.append(alert)
                
            # Check if acknowledgment deadline is approaching
            elif 0 < time_to_ack_deadline <= 6 and complaint_info["current_status"] in ["RED", "ORANGE"]:
                approaching_info = {
                    **complaint_info,
                    "deadline_type": "acknowledgment", 
                    "deadline": ack_deadline.isoformat(),
                    "hours_remaining": round(time_to_ack_deadline, 1),
                    "urgency_level": "HIGH" if time_to_ack_deadline <= 2 else "MEDIUM"
                }
                tracking_results["approaching_deadlines"].append(approaching_info)
                
                alert = {
                    "type": "APPROACHING_ACKNOWLEDGMENT_DEADLINE",
                    "complaint_id": cid,
                    "severity": approaching_info["urgency_level"],
                    "message": f"Acknowledgment due in {approaching_info['hours_remaining']} hours",
                    "action": "send_reminder",
                    "department": complaint_info["department"]
                }
                tracking_results["alerts"].append(alert)
        
        # Check resolution deadline
        res_deadline_str = complaint_tracking.get("resolution_deadline")
        if res_deadline_str:
            res_deadline = datetime.fromisoformat(res_deadline_str)
            time_to_res_deadline = (res_deadline - current_time).total_seconds() / 3600  # hours
            
            # Check if resolution is overdue
            if time_to_res_deadline < 0 and complaint_info["current_status"] != "BLACK":
                overdue_hours = abs(time_to_res_deadline)
                overdue_info = {
                    **complaint_info,
                    "deadline_type": "resolution",
                    "deadline": res_deadline.isoformat(),
                    "hours_overdue": round(overdue_hours, 1),
                    "severity": "CRITICAL" if overdue_hours > 72 else "HIGH"
                }
                tracking_results["overdue_deadlines"].append(overdue_info)
                
                alert = {
                    "type": "OVERDUE_RESOLUTION",
                    "complaint_id": cid,
                    "severity": overdue_info["severity"],
                    "message": f"Resolution overdue by {overdue_info['hours_overdue']} hours",
                    "action": "escalation_required",
                    "department": complaint_info["department"]
                }
                tracking_results["alerts"].append(alert)
                alerts_to_save.append(alert)
                
            # Check if resolution deadline is approaching (within 10% of total time)
            elif 0 < time_to_res_deadline <= 24 and complaint_info["current_status"] not in ["BLACK"]:
                approaching_info = {
                    **complaint_info,
                    "deadline_type": "resolution",
                    "deadline": res_deadline.isoformat(), 
                    "hours_remaining": round(time_to_res_deadline, 1),
                    "urgency_level": "HIGH" if time_to_res_deadline <= 8 else "MEDIUM"
                }
                tracking_results["approaching_deadlines"].append(approaching_info)
                
                alert = {
                    "type": "APPROACHING_RESOLUTION_DEADLINE",
                    "complaint_id": cid,
                    "severity": approaching_info["urgency_level"],
                    "message": f"Resolution due in {approaching_info['hours_remaining']} hours",
                    "action": "progress_check_required",
                    "department": complaint_info["department"]
                }
                tracking_results["alerts"].append(alert)
        
        # Check for reminder schedule
        reminder_schedule = complaint_tracking.get("reminder_schedule", [])
        for reminder in reminder_schedule:
            reminder_time = datetime.fromisoformat(reminder["datetime"])
            if current_time >= reminder_time and not reminder.get("sent", False):
                # Time to send reminder
                tracking_results["actions_required"].append({
                    "action_type": "send_reminder",
                    "complaint_id": cid,
                    "reminder_type": reminder["type"],
                    "message": reminder["description"],
                    "recipient": complaint_info["department"],
                    "urgency": complaint_info["urgency"]
                })
                
                # Mark reminder as sent
                reminder["sent"] = True
                reminder["sent_at"] = current_time.isoformat()
    
    # Department-wise summary
    dept_summary = {}
    for deadline in tracking_results["overdue_deadlines"] + tracking_results["approaching_deadlines"]:
        dept = deadline["department"]
        if dept not in dept_summary:
            dept_summary[dept] = {"overdue": 0, "approaching": 0, "total": 0}
        
        dept_summary[dept]["total"] += 1
        if deadline in tracking_results["overdue_deadlines"]:
            dept_summary[dept]["overdue"] += 1
        else:
            dept_summary[dept]["approaching"] += 1
    
    tracking_results["department_summary"] = dept_summary
    
    # Generate action recommendations
    if tracking_results["overdue_deadlines"]:
        critical_overdue = [d for d in tracking_results["overdue_deadlines"] if d["severity"] == "CRITICAL"]
        if critical_overdue:
            tracking_results["actions_required"].append({
                "action_type": "immediate_escalation",
                "priority": "CRITICAL",
                "description": f"Escalate {len(critical_overdue)} critically overdue complaints",
                "complaints": [d["complaint_id"] for d in critical_overdue]
            })
    
    if tracking_results["approaching_deadlines"]:
        urgent_approaching = [d for d in tracking_results["approaching_deadlines"] if d["urgency_level"] == "HIGH"]
        if urgent_approaching:
            tracking_results["actions_required"].append({
                "action_type": "urgent_reminders",
                "priority": "HIGH", 
                "description": f"Send urgent reminders for {len(urgent_approaching)} complaints",
                "complaints": [d["complaint_id"] for d in urgent_approaching]
            })
    
    # Performance metrics
    total_deadlines = len(tracking_results["overdue_deadlines"]) + len(tracking_results["approaching_deadlines"])
    if total_deadlines > 0:
        overdue_rate = len(tracking_results["overdue_deadlines"]) / total_deadlines * 100
        tracking_results["performance_metrics"] = {
            "overdue_percentage": round(overdue_rate, 1),
            "on_time_performance": round(100 - overdue_rate, 1),
            "total_active_deadlines": len(tracked_complaints),
            "departments_at_risk": len([d for d in dept_summary.values() if d["overdue"] > 0])
        }
    
    # Save updated deadline data
    deadline_data["tracked_complaints"] = tracked_complaints
    deadline_data["last_check"] = current_time.isoformat()
    save_active_deadlines(deadline_data)
    
    # Save alerts for other agents to consume
    if alerts_to_save:
        save_deadline_alerts(alerts_to_save)
    
    return tracking_results

@tool(
    name="add_deadline_tracking",
    description="Adds a new complaint to deadline tracking system",
    permission=ToolPermission.READ_WRITE
)
def add_deadline_tracking(complaint_id: str, acknowledgment_deadline: str, resolution_deadline: str, 
                         metadata: dict = {}) -> dict:
    """
    Add a complaint to the deadline tracking system.
    
    Args:
        complaint_id (str): Unique complaint identifier
        acknowledgment_deadline (str): ISO format acknowledgment deadline
        resolution_deadline (str): ISO format resolution deadline
        metadata (dict): Additional complaint metadata
        
    Returns:
        dict: Confirmation of tracking setup
    """
    current_time = datetime.now()
    deadline_data = load_active_deadlines()
    tracked_complaints = deadline_data.get("tracked_complaints", {})
    
    # Add complaint to tracking
    tracked_complaints[complaint_id] = {
        "complaint_id": complaint_id,
        "acknowledgment_deadline": acknowledgment_deadline,
        "resolution_deadline": resolution_deadline,
        "tracking_started": current_time.isoformat(),
        "current_status": metadata.get("current_status", "ORANGE"),
        "urgency": metadata.get("urgency", "MEDIUM"),
        "category": metadata.get("category", "general"),
        "assigned_department": metadata.get("assigned_department", "unknown"),
        "reminder_schedule": metadata.get("reminder_schedule", []),
        "escalation_schedule": metadata.get("escalation_schedule", [])
    }
    
    # Save updated data
    deadline_data["tracked_complaints"] = tracked_complaints
    save_active_deadlines(deadline_data)
    
    return {
        "success": True,
        "complaint_id": complaint_id,
        "tracking_started": current_time.isoformat(),
        "acknowledgment_deadline": acknowledgment_deadline,
        "resolution_deadline": resolution_deadline,
        "total_tracked": len(tracked_complaints)
    }