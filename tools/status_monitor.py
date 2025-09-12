# tools/status_monitor.py

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from datetime import datetime, timedelta
import json
import os

KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), "../knowledge")
STATUS_LOG_PATH = os.path.join(KNOWLEDGE_PATH, "status_monitoring_log.json")
COMPLAINTS_STATUS_PATH = os.path.join(KNOWLEDGE_PATH, "complaints_status.json")

# Status definitions with color codes
STATUS_DEFINITIONS = {
    "RED": {
        "name": "Received & Processing", 
        "description": "Complaint received, AI agents are processing and categorizing",
        "auto_actions": ["categorize", "route"],
        "max_duration_hours": 1,
        "next_statuses": ["ORANGE"]
    },
    "ORANGE": {
        "name": "Routed to Department",
        "description": "Complaint routed to appropriate department with deadline",
        "auto_actions": ["send_notification", "start_timer"],
        "max_duration_hours": 48,  # Default, varies by urgency
        "next_statuses": ["BLUE", "RED"]  # Can go back to RED if routing fails
    },
    "BLUE": {
        "name": "Acknowledged by Department", 
        "description": "Department has acknowledged receipt and assigned officer",
        "auto_actions": ["notify_citizen", "schedule_follow_up"],
        "max_duration_hours": 72,
        "next_statuses": ["GREEN", "ORANGE"]  # Can escalate back
    },
    "GREEN": {
        "name": "Work in Progress",
        "description": "Department is actively working on resolution",
        "auto_actions": ["progress_tracking", "regular_updates"],
        "max_duration_hours": 168,  # 1 week default
        "next_statuses": ["BLACK", "BLUE"]  # Can regress if issues
    },
    "BLACK": {
        "name": "Resolved & Verified",
        "description": "Problem resolved and citizen satisfaction confirmed",
        "auto_actions": ["satisfaction_survey", "close_complaint"],
        "max_duration_hours": None,  # Final status
        "next_statuses": []  # Terminal status
    }
}

def load_complaints_status():
    """Load current complaints status data"""
    try:
        if os.path.exists(COMPLAINTS_STATUS_PATH):
            with open(COMPLAINTS_STATUS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"active_complaints": {}, "status_transitions": []}
    except Exception as e:
        return {"active_complaints": {}, "status_transitions": []}

def save_complaints_status(data):
    """Save complaints status data"""
    try:
        os.makedirs(KNOWLEDGE_PATH, exist_ok=True)
        with open(COMPLAINTS_STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving complaints status: {e}")

def log_status_change(complaint_id, old_status, new_status, reason):
    """Log status changes for monitoring"""
    try:
        os.makedirs(KNOWLEDGE_PATH, exist_ok=True)
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "complaint_id": complaint_id,
            "status_change": f"{old_status} -> {new_status}",
            "reason": reason,
            "duration_in_previous_status": None  # Calculate if needed
        }
        
        logs = []
        if os.path.exists(STATUS_LOG_PATH):
            with open(STATUS_LOG_PATH, "r", encoding="utf-8") as f:
                logs = json.load(f)
        
        logs.append(log_entry)
        
        if len(logs) > 5000:  # Keep larger log for status monitoring
            logs = logs[-5000:]
        
        with open(STATUS_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error logging status change: {e}")

@tool(
    name="status_monitor",
    description="Monitors complaint status progression and identifies overdue or stuck complaints",
    permission=ToolPermission.READ_WRITE  # Needs write to update status
)
def monitor_status(complaint_id: str = "", status_filter: str = "", check_overdue: bool = True) -> dict:
    """
    Monitor complaint status and identify issues.
    
    Args:
        complaint_id (str): Specific complaint to monitor (optional)
        status_filter (str): Filter by status color (optional)
        check_overdue (bool): Whether to check for overdue complaints
        
    Returns:
        dict: Status monitoring results with alerts and recommendations
    """
    current_time = datetime.now()
    complaints_data = load_complaints_status()
    active_complaints = complaints_data.get("active_complaints", {})
    
    monitoring_results = {
        "timestamp": current_time.isoformat(),
        "total_active_complaints": len(active_complaints),
        "status_distribution": {},
        "overdue_complaints": [],
        "at_risk_complaints": [],
        "alerts": [],
        "recommendations": []
    }
    
    # Status distribution
    for status in STATUS_DEFINITIONS.keys():
        monitoring_results["status_distribution"][status] = 0
    
    # Monitor each complaint
    for cid, complaint_data in active_complaints.items():
        # Skip if filtering by complaint_id
        if complaint_id and cid != complaint_id:
            continue
            
        current_status = complaint_data.get("current_status", "RED")
        
        # Skip if filtering by status
        if status_filter and current_status != status_filter:
            continue
            
        # Update status distribution
        if current_status in monitoring_results["status_distribution"]:
            monitoring_results["status_distribution"][current_status] += 1
        
        # Calculate time in current status
        status_start_time = datetime.fromisoformat(complaint_data.get("status_start_time", current_time.isoformat()))
        time_in_status = (current_time - status_start_time).total_seconds() / 3600  # hours
        
        # Check if overdue
        if check_overdue and current_status != "BLACK":
            status_def = STATUS_DEFINITIONS.get(current_status, {})
            max_duration = status_def.get("max_duration_hours")
            
            # Adjust max duration based on urgency
            urgency = complaint_data.get("urgency", "MEDIUM")
            urgency_multipliers = {"CRITICAL": 0.5, "HIGH": 0.75, "MEDIUM": 1.0, "LOW": 1.5}
            
            if max_duration:
                adjusted_max = max_duration * urgency_multipliers.get(urgency, 1.0)
                
                if time_in_status > adjusted_max:
                    # Overdue complaint
                    overdue_info = {
                        "complaint_id": cid,
                        "current_status": current_status,
                        "hours_overdue": round(time_in_status - adjusted_max, 1),
                        "urgency": urgency,
                        "category": complaint_data.get("category", "unknown"),
                        "department": complaint_data.get("assigned_department", "unknown"),
                        "last_update": complaint_data.get("last_update", "no_update")
                    }
                    monitoring_results["overdue_complaints"].append(overdue_info)
                    
                    # Generate alert
                    alert = {
                        "type": "OVERDUE_COMPLAINT",
                        "severity": "HIGH" if urgency in ["CRITICAL", "HIGH"] else "MEDIUM",
                        "message": f"Complaint {cid} is {overdue_info['hours_overdue']} hours overdue in {current_status} status",
                        "action_required": "immediate_escalation" if urgency == "CRITICAL" else "follow_up_required"
                    }
                    monitoring_results["alerts"].append(alert)
                
                elif time_in_status > adjusted_max * 0.8:
                    # At risk complaint (80% of deadline passed)
                    at_risk_info = {
                        "complaint_id": cid,
                        "current_status": current_status,
                        "hours_remaining": round(adjusted_max - time_in_status, 1),
                        "urgency": urgency,
                        "category": complaint_data.get("category", "unknown"),
                        "risk_level": "HIGH" if time_in_status > adjusted_max * 0.9 else "MEDIUM"
                    }
                    monitoring_results["at_risk_complaints"].append(at_risk_info)
        
        # Check for stuck complaints (no status change in expected timeframes)
        last_status_change = datetime.fromisoformat(complaint_data.get("last_status_change", current_time.isoformat()))
        hours_since_change = (current_time - last_status_change).total_seconds() / 3600
        
        if current_status in ["ORANGE", "BLUE"] and hours_since_change > 72:  # 3 days without progress
            alert = {
                "type": "STUCK_COMPLAINT",
                "severity": "MEDIUM",
                "message": f"Complaint {cid} stuck in {current_status} status for {round(hours_since_change, 1)} hours",
                "action_required": "department_follow_up"
            }
            monitoring_results["alerts"].append(alert)
    
    # Generate recommendations
    if monitoring_results["overdue_complaints"]:
        monitoring_results["recommendations"].append({
            "type": "ESCALATION_NEEDED",
            "priority": "HIGH",
            "action": f"Escalate {len(monitoring_results['overdue_complaints'])} overdue complaints immediately",
            "details": "Use Escalate_Agent to trigger automated escalation process"
        })
    
    if monitoring_results["at_risk_complaints"]:
        monitoring_results["recommendations"].append({
            "type": "PREVENTIVE_ACTION",
            "priority": "MEDIUM", 
            "action": f"Send reminders for {len(monitoring_results['at_risk_complaints'])} at-risk complaints",
            "details": "Use Follow_Agent to send proactive reminders"
        })
    
    # Department performance analysis
    dept_performance = {}
    for complaint_data in active_complaints.values():
        dept = complaint_data.get("assigned_department", "unknown")
        status = complaint_data.get("current_status", "RED")
        
        if dept not in dept_performance:
            dept_performance[dept] = {"total": 0, "overdue": 0, "resolved": 0}
        
        dept_performance[dept]["total"] += 1
        if status == "BLACK":
            dept_performance[dept]["resolved"] += 1
        
        # Count overdue for this department
        for overdue in monitoring_results["overdue_complaints"]:
            if overdue.get("department") == dept:
                dept_performance[dept]["overdue"] += 1
    
    # Identify underperforming departments
    underperforming_depts = []
    for dept, perf in dept_performance.items():
        if perf["total"] > 0:
            overdue_rate = perf["overdue"] / perf["total"]
            if overdue_rate > 0.3:  # More than 30% overdue
                underperforming_depts.append({
                    "department": dept,
                    "overdue_rate": round(overdue_rate * 100, 1),
                    "total_complaints": perf["total"],
                    "overdue_count": perf["overdue"]
                })
    
    if underperforming_depts:
        monitoring_results["recommendations"].append({
            "type": "DEPARTMENT_PERFORMANCE",
            "priority": "HIGH",
            "action": "Review underperforming departments",
            "details": f"Departments with >30% overdue rate: {[d['department'] for d in underperforming_depts]}"
        })
    
    monitoring_results["department_performance"] = dept_performance
    monitoring_results["underperforming_departments"] = underperforming_depts
    
    # System health metrics
    total_complaints = len(active_complaints)
    if total_complaints > 0:
        overdue_percentage = len(monitoring_results["overdue_complaints"]) / total_complaints * 100
        resolved_count = monitoring_results["status_distribution"].get("BLACK", 0)
        resolution_rate = resolved_count / total_complaints * 100 if total_complaints > 0 else 0
        
        monitoring_results["system_health"] = {
            "overall_overdue_rate": round(overdue_percentage, 1),
            "resolution_rate": round(resolution_rate, 1),
            "active_complaint_load": total_complaints,
            "health_status": "GOOD" if overdue_percentage < 10 else "POOR" if overdue_percentage > 25 else "FAIR"
        }
    
    # Save updated monitoring data
    complaints_data["last_monitoring"] = monitoring_results
    save_complaints_status(complaints_data)
    
    return monitoring_results

@tool(
    name="update_complaint_status",
    description="Updates the status of a specific complaint with validation and logging",
    permission=ToolPermission.READ_WRITE
)
def update_complaint_status(complaint_id: str, new_status: str, reason: str = "", metadata: dict = {}) -> dict:
    """
    Update complaint status with proper validation and logging.
    
    Args:
        complaint_id (str): Unique complaint identifier
        new_status (str): New status (RED, ORANGE, BLUE, GREEN, BLACK)
        reason (str): Reason for status change
        metadata (dict): Additional metadata for the status change
        
    Returns:
        dict: Status update confirmation with validation results
    """
    current_time = datetime.now()
    
    # Validate new status
    if new_status not in STATUS_DEFINITIONS:
        return {
            "success": False,
            "error": f"Invalid status: {new_status}. Valid statuses: {list(STATUS_DEFINITIONS.keys())}",
            "complaint_id": complaint_id
        }
    
    # Load current data
    complaints_data = load_complaints_status()
    active_complaints = complaints_data.get("active_complaints", {})
    
    # Get current complaint data
    if complaint_id not in active_complaints:
        # Create new complaint entry
        active_complaints[complaint_id] = {
            "complaint_id": complaint_id,
            "created_time": current_time.isoformat(),
            "current_status": "RED",
            "status_history": [],
            "last_update": current_time.isoformat()
        }
    
    complaint_data = active_complaints[complaint_id]
    old_status = complaint_data.get("current_status", "RED")
    
    # Validate status transition
    status_def = STATUS_DEFINITIONS[old_status]
    valid_next_statuses = status_def.get("next_statuses", [])
    
    if new_status != old_status and valid_next_statuses and new_status not in valid_next_statuses:
        return {
            "success": False,
            "error": f"Invalid status transition from {old_status} to {new_status}. Valid transitions: {valid_next_statuses}",
            "complaint_id": complaint_id,
            "current_status": old_status
        }
    
    # Calculate time in previous status
    status_start_time = datetime.fromisoformat(complaint_data.get("status_start_time", current_time.isoformat()))
    time_in_previous = (current_time - status_start_time).total_seconds() / 3600
    
    # Update complaint data
    complaint_data.update({
        "current_status": new_status,
        "status_start_time": current_time.isoformat(),
        "last_update": current_time.isoformat(),
        "last_status_change": current_time.isoformat()
    })
    
    # Add to status history
    if "status_history" not in complaint_data:
        complaint_data["status_history"] = []
    
    complaint_data["status_history"].append({
        "from_status": old_status,
        "to_status": new_status,
        "timestamp": current_time.isoformat(),
        "duration_hours": round(time_in_previous, 2),
        "reason": reason,
        "metadata": metadata
    })
    
    # Update metadata if provided
    if metadata:
        complaint_data.update(metadata)
    
    # Save updated data
    complaints_data["active_complaints"] = active_complaints
    save_complaints_status(complaints_data)
    
    # Log status change
    log_status_change(complaint_id, old_status, new_status, reason)
    
    # Prepare result
    result = {
        "success": True,
        "complaint_id": complaint_id,
        "status_change": {
            "from": old_status,
            "to": new_status,
            "timestamp": current_time.isoformat(),
            "duration_in_previous": round(time_in_previous, 2)
        },
        "new_status_info": STATUS_DEFINITIONS[new_status],
        "auto_actions_triggered": STATUS_DEFINITIONS[new_status].get("auto_actions", []),
        "next_expected_statuses": STATUS_DEFINITIONS[new_status].get("next_statuses", [])
    }
    
    return result