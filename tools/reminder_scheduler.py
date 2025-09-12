# tools/reminder_scheduler.py

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from datetime import datetime, timedelta
import json
import os

KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), "../knowledge")
REMINDER_QUEUE_PATH = os.path.join(KNOWLEDGE_PATH, "reminder_queue.json")
SENT_REMINDERS_PATH = os.path.join(KNOWLEDGE_PATH, "sent_reminders_log.json")

# Reminder templates
REMINDER_TEMPLATES = {
    "acknowledgment_50_percent": {
        "subject": "Complaint Acknowledgment Required - 50% Deadline Passed",
        "template": "Dear {department_name},\n\nThis is a gentle reminder that complaint #{complaint_id} submitted on {submission_date} requires acknowledgment.\n\nDetails:\n- Category: {category}\n- Urgency: {urgency}\n- Location: {location}\n- Deadline: {deadline}\n\nPlease acknowledge receipt and assign a responsible officer.\n\nRegards,\nCitizen Voice AI System",
        "escalation_level": "gentle"
    },
    "acknowledgment_90_percent": {
        "subject": "URGENT: Complaint Acknowledgment Required - 90% Deadline Passed",
        "template": "Dear {department_head},\n\nURGENT REMINDER: Complaint #{complaint_id} acknowledgment deadline is 90% passed.\n\nComplaint Details:\n- Submitted: {submission_date}\n- Category: {category}\n- Urgency Level: {urgency}\n- Location: {location}\n- Deadline: {deadline}\n- Time Remaining: {time_remaining}\n\nImmediate action required to avoid escalation.\n\nRegards,\nCitizen Voice AI System",
        "escalation_level": "urgent"
    },
    "resolution_25_percent": {
        "subject": "Resolution Progress Check - 25% Timeline Passed",
        "template": "Dear {assigned_officer},\n\nThis is a progress check for complaint #{complaint_id}.\n\n25% of the resolution timeline has passed. Please provide a status update:\n- Current progress\n- Challenges faced (if any)\n- Expected completion date\n- Resources needed\n\nComplaint Details:\n- Category: {category}\n- Urgency: {urgency}\n- Resolution Deadline: {resolution_deadline}\n\nRegards,\nCitizen Voice AI System",
        "escalation_level": "progress_check"
    },
    "resolution_75_percent": {
        "subject": "FINAL WARNING: Resolution Deadline 75% Passed - Complaint #{complaint_id}",
        "template": "Dear {department_head},\n\nFINAL WARNING: 75% of resolution deadline has passed for complaint #{complaint_id}.\n\nImmediate status update and action plan required:\n- Current status of work\n- Obstacles preventing completion\n- Revised completion timeline\n- Escalation requirements\n\nComplaint will be automatically escalated if not resolved by deadline: {resolution_deadline}\n\nRegards,\nCitizen Voice AI System",
        "escalation_level": "final_warning"
    },
    "overdue_acknowledgment": {
        "subject": "OVERDUE: Acknowledgment Required - Complaint #{complaint_id}",
        "template": "Dear {department_head},\n\nComplaint #{complaint_id} acknowledgment is now OVERDUE by {overdue_hours} hours.\n\nThis complaint is being escalated to the next level as per government accountability protocols.\n\nImmediate action required:\n1. Acknowledge complaint receipt\n2. Assign responsible officer\n3. Provide initial assessment\n4. Set resolution timeline\n\nCopy: District Collector, Chief Secretary Office\n\nRegards,\nCitizen Voice AI System",
        "escalation_level": "overdue"
    },
    "overdue_resolution": {
        "subject": "CRITICAL: Resolution Overdue - Escalation Triggered - #{complaint_id}",
        "template": "Dear {department_head},\n\nComplaint #{complaint_id} resolution is critically overdue by {overdue_hours} hours.\n\nAutomatic escalation has been triggered to:\n- District Authority\n- State Secretariat\n- Political Executive (if critical)\n\nImmediate resolution or detailed explanation required within 24 hours.\n\nComplaint Summary:\n- Category: {category}\n- Urgency: {urgency}\n- Original Deadline: {resolution_deadline}\n- Citizen Impact: {impact_description}\n\nRegards,\nCitizen Voice AI System",
        "escalation_level": "critical_overdue"
    }
}

def load_reminder_queue():
    """Load pending reminder queue"""
    try:
        if os.path.exists(REMINDER_QUEUE_PATH):
            with open(REMINDER_QUEUE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"pending_reminders": [], "scheduled_reminders": []}
    except Exception as e:
        return {"pending_reminders": [], "scheduled_reminders": []}

def save_reminder_queue(data):
    """Save reminder queue data"""
    try:
        os.makedirs(KNOWLEDGE_PATH, exist_ok=True)
        with open(REMINDER_QUEUE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving reminder queue: {e}")

def log_sent_reminder(reminder_data, status):
    """Log sent reminders for tracking"""
    try:
        os.makedirs(KNOWLEDGE_PATH, exist_ok=True)
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "complaint_id": reminder_data.get("complaint_id"),
            "reminder_type": reminder_data.get("reminder_type"),
            "recipient": reminder_data.get("recipient_email"),
            "status": status,
            "escalation_level": reminder_data.get("escalation_level")
        }
        
        logs = []
        if os.path.exists(SENT_REMINDERS_PATH):
            with open(SENT_REMINDERS_PATH, "r", encoding="utf-8") as f:
                logs = json.load(f)
        
        logs.append(log_entry)
        
        if len(logs) > 2000:
            logs = logs[-2000:]
        
        with open(SENT_REMINDERS_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error logging sent reminder: {e}")

@tool(
    name="reminder_scheduler",
    description="Schedules and manages automated reminders for departments about pending complaints",
    permission=ToolPermission.READ_WRITE
)
def schedule_reminder(complaint_id: str, reminder_type: str, scheduled_time: str, 
                     complaint_data: dict = {}, department_data: dict = {}) -> dict:
    """
    Schedule a reminder for a specific complaint.
    
    Args:
        complaint_id (str): Unique complaint identifier
        reminder_type (str): Type of reminder (acknowledgment_50_percent, etc.)
        scheduled_time (str): ISO format datetime when reminder should be sent
        complaint_data (dict): Complaint details for template
        department_data (dict): Department contact information
        
    Returns:
        dict: Confirmation of scheduled reminder
    """
    current_time = datetime.now()
    reminder_queue = load_reminder_queue()
    
    # Validate reminder type
    if reminder_type not in REMINDER_TEMPLATES:
        return {
            "success": False,
            "error": f"Invalid reminder type: {reminder_type}. Valid types: {list(REMINDER_TEMPLATES.keys())}",
            "complaint_id": complaint_id
        }
    
    # Get template
    template_data = REMINDER_TEMPLATES[reminder_type]
    
    # Prepare reminder data
    reminder_data = {
        "reminder_id": f"{complaint_id}_{reminder_type}_{int(current_time.timestamp())}",
        "complaint_id": complaint_id,
        "reminder_type": reminder_type,
        "scheduled_time": scheduled_time,
        "created_at": current_time.isoformat(),
        "status": "scheduled",
        "escalation_level": template_data["escalation_level"],
        "subject": template_data["subject"].format(complaint_id=complaint_id),
        "template": template_data["template"],
        "complaint_data": complaint_data,
        "department_data": department_data,
        "recipient_email": department_data.get("email", ""),
        "recipient_phone": department_data.get("phone", ""),
        "cc_emails": [],
        "retry_count": 0,
        "max_retries": 3
    }
    
    # Add CC emails based on escalation level
    if template_data["escalation_level"] in ["urgent", "final_warning", "overdue", "critical_overdue"]:
        reminder_data["cc_emails"].extend([
            "collector@delhi.gov.in",
            complaint_data.get("backup_email", "")
        ])
    
    if template_data["escalation_level"] in ["critical_overdue"]:
        reminder_data["cc_emails"].extend([
            "cs@delhi.gov.in",
            "cmo@delhi.gov.in"
        ])
    
    # Add to appropriate queue
    scheduled_datetime = datetime.fromisoformat(scheduled_time)
    if scheduled_datetime <= current_time:
        # Should be sent immediately
        reminder_queue["pending_reminders"].append(reminder_data)
    else:
        # Schedule for future
        reminder_queue["scheduled_reminders"].append(reminder_data)
    
    # Save updated queue
    save_reminder_queue(reminder_queue)
    
    return {
        "success": True,
        "reminder_id": reminder_data["reminder_id"],
        "complaint_id": complaint_id,
        "reminder_type": reminder_type,
        "scheduled_for": scheduled_time,
        "escalation_level": template_data["escalation_level"],
        "queue_type": "pending" if scheduled_datetime <= current_time else "scheduled"
    }

@tool(
    name="process_pending_reminders",
    description="Processes pending reminders and generates reminder communications",
    permission=ToolPermission.READ_WRITE
)
def process_pending_reminders(max_reminders: int = 50) -> dict:
    """
    Process pending reminders and prepare them for sending.
    
    Args:
        max_reminders (int): Maximum number of reminders to process in one batch
        
    Returns:
        dict: Results of reminder processing with generated communications
    """
    current_time = datetime.now()
    reminder_queue = load_reminder_queue()
    
    # Move scheduled reminders to pending if their time has come
    scheduled_reminders = reminder_queue.get("scheduled_reminders", [])
    pending_reminders = reminder_queue.get("pending_reminders", [])
    
    newly_pending = []
    still_scheduled = []
    
    for reminder in scheduled_reminders:
        scheduled_time = datetime.fromisoformat(reminder["scheduled_time"])
        if scheduled_time <= current_time:
            reminder["status"] = "pending"
            newly_pending.append(reminder)
        else:
            still_scheduled.append(reminder)
    
    # Update queues
    reminder_queue["scheduled_reminders"] = still_scheduled
    reminder_queue["pending_reminders"] = pending_reminders + newly_pending
    
    # Process pending reminders (up to max_reminders)
    to_process = reminder_queue["pending_reminders"][:max_reminders]
    remaining_pending = reminder_queue["pending_reminders"][max_reminders:]
    
    processed_reminders = []
    failed_reminders = []
    
    for reminder in to_process:
        try:
            # Generate personalized reminder content
            complaint_data = reminder.get("complaint_data", {})
            department_data = reminder.get("department_data", {})
            
            # Fill template with actual data
            personalized_content = reminder["template"].format(
                complaint_id=reminder["complaint_id"],
                department_name=department_data.get("name", "Department"),
                department_head=department_data.get("head", "Department Head"),
                assigned_officer=complaint_data.get("assigned_officer", "Assigned Officer"),
                submission_date=complaint_data.get("submission_date", "Unknown"),
                category=complaint_data.get("category", "General"),
                urgency=complaint_data.get("urgency", "MEDIUM"),
                location=complaint_data.get("location", "Not specified"),
                deadline=complaint_data.get("acknowledgment_deadline", "Not set"),
                resolution_deadline=complaint_data.get("resolution_deadline", "Not set"),
                time_remaining=complaint_data.get("time_remaining", "Unknown"),
                overdue_hours=complaint_data.get("overdue_hours", "0"),
                impact_description=complaint_data.get("impact_description", "Citizen inconvenience")
            )
            
            # Prepare communication data
            communication = {
                "reminder_id": reminder["reminder_id"],
                "complaint_id": reminder["complaint_id"],
                "type": "email",  # Primary communication method
                "subject": reminder["subject"],
                "content": personalized_content,
                "primary_recipient": {
                    "email": reminder["recipient_email"],
                    "phone": reminder.get("recipient_phone", ""),
                    "name": department_data.get("head", "Department Official")
                },
                "cc_recipients": [{"email": email} for email in reminder.get("cc_emails", []) if email],
                "escalation_level": reminder["escalation_level"],
                "priority": "HIGH" if reminder["escalation_level"] in ["urgent", "final_warning", "overdue", "critical_overdue"] else "MEDIUM",
                "generated_at": current_time.isoformat(),
                "department": department_data.get("name", "Unknown Department"),
                "follow_up_required": reminder["escalation_level"] in ["urgent", "final_warning", "overdue", "critical_overdue"]
            }
            
            # Add SMS communication for urgent reminders
            if reminder["escalation_level"] in ["urgent", "final_warning", "overdue", "critical_overdue"] and reminder.get("recipient_phone"):
                sms_content = f"URGENT: Complaint #{reminder['complaint_id']} requires immediate attention. {reminder['escalation_level'].upper()} level. Check email for details. -Citizen Voice AI"
                communication["sms"] = {
                    "phone": reminder["recipient_phone"],
                    "content": sms_content[:160]  # SMS length limit
                }
            
            reminder["status"] = "processed"
            reminder["processed_at"] = current_time.isoformat()
            reminder["communication_generated"] = communication
            
            processed_reminders.append(reminder)
            
            # Log successful processing
            log_sent_reminder(reminder, "processed")
            
        except Exception as e:
            # Handle processing failure
            reminder["retry_count"] = reminder.get("retry_count", 0) + 1
            reminder["last_error"] = str(e)
            reminder["last_retry"] = current_time.isoformat()
            
            if reminder["retry_count"] <= reminder.get("max_retries", 3):
                # Retry later
                reminder["status"] = "retry_pending"
                remaining_pending.append(reminder)
            else:
                # Max retries reached
                reminder["status"] = "failed"
                failed_reminders.append(reminder)
                log_sent_reminder(reminder, "failed")
    
    # Update queue with remaining pending reminders
    reminder_queue["pending_reminders"] = remaining_pending
    
    # Archive processed reminders
    if "processed_reminders" not in reminder_queue:
        reminder_queue["processed_reminders"] = []
    reminder_queue["processed_reminders"].extend(processed_reminders)
    
    # Keep only last 1000 processed reminders
    if len(reminder_queue["processed_reminders"]) > 1000:
        reminder_queue["processed_reminders"] = reminder_queue["processed_reminders"][-1000:]
    
    # Save updated queue
    save_reminder_queue(reminder_queue)
    
    # Prepare results
    results = {
        "processing_timestamp": current_time.isoformat(),
        "processed_count": len(processed_reminders),
        "failed_count": len(failed_reminders),
        "remaining_pending": len(reminder_queue["pending_reminders"]),
        "scheduled_count": len(reminder_queue["scheduled_reminders"]),
        "communications_generated": [r["communication_generated"] for r in processed_reminders],
        "escalation_levels_processed": {},
        "departments_notified": set(),
        "next_processing_recommended": (current_time + timedelta(hours=1)).isoformat() if remaining_pending else None
    }
    
    # Statistics
    for reminder in processed_reminders:
        level = reminder["escalation_level"]
        if level not in results["escalation_levels_processed"]:
            results["escalation_levels_processed"][level] = 0
        results["escalation_levels_processed"][level] += 1
        
        dept = reminder.get("department_data", {}).get("name", "Unknown")
        results["departments_notified"].add(dept)
    
    results["departments_notified"] = list(results["departments_notified"])
    
    # Generate summary for other agents
    if processed_reminders:
        summary_for_agents = {
            "reminder_batch_processed": True,
            "timestamp": current_time.isoformat(),
            "high_priority_reminders": len([r for r in processed_reminders if r["escalation_level"] in ["urgent", "final_warning", "overdue", "critical_overdue"]]),
            "complaints_requiring_escalation": [r["complaint_id"] for r in processed_reminders if r["escalation_level"] in ["overdue", "critical_overdue"]],
            "departments_with_overdue": list(set([r.get("department_data", {}).get("name", "Unknown") for r in processed_reminders if r["escalation_level"] in ["overdue", "critical_overdue"]]))
        }
        
        # Save summary for other agents to read
        summary_path = os.path.join(KNOWLEDGE_PATH, "reminder_processing_summary.json")
        try:
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary_for_agents, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving reminder summary: {e}")
    
    return results

@tool(
    name="get_reminder_statistics",
    description="Gets statistics about reminder system performance and effectiveness",
    permission=ToolPermission.READ_ONLY
)
def get_reminder_statistics(days_back: int = 7) -> dict:
    """
    Get reminder system statistics and performance metrics.
    
    Args:
        days_back (int): Number of days to look back for statistics
        
    Returns:
        dict: Reminder system statistics and performance data
    """
    current_time = datetime.now()
    cutoff_time = current_time - timedelta(days=days_back)
    
    # Load sent reminders log
    try:
        if os.path.exists(SENT_REMINDERS_PATH):
            with open(SENT_REMINDERS_PATH, "r", encoding="utf-8") as f:
                sent_logs = json.load(f)
        else:
            sent_logs = []
    except:
        sent_logs = []
    
    # Filter recent reminders
    recent_reminders = [
        log for log in sent_logs 
        if datetime.fromisoformat(log["timestamp"]) >= cutoff_time
    ]
    
    # Load current queue status
    reminder_queue = load_reminder_queue()
    
    # Calculate statistics
    stats = {
        "analysis_period": f"{days_back} days",
        "period_start": cutoff_time.isoformat(),
        "period_end": current_time.isoformat(),
        "total_reminders_sent": len(recent_reminders),
        "current_queue_status": {
            "pending": len(reminder_queue.get("pending_reminders", [])),
            "scheduled": len(reminder_queue.get("scheduled_reminders", [])),
            "processed_archive": len(reminder_queue.get("processed_reminders", []))
        },
        "reminder_types_distribution": {},
        "escalation_levels_distribution": {},
        "departments_contacted": {},
        "success_rate": 0.0,
        "average_processing_time": 0.0,
        "peak_reminder_hours": {}
    }
    
    # Analyze reminder types and escalation levels
    for reminder in recent_reminders:
        # Reminder type distribution
        rtype = reminder.get("reminder_type", "unknown")
        if rtype not in stats["reminder_types_distribution"]:
            stats["reminder_types_distribution"][rtype] = 0
        stats["reminder_types_distribution"][rtype] += 1
        
        # Escalation level distribution
        elevel = reminder.get("escalation_level", "unknown")
        if elevel not in stats["escalation_levels_distribution"]:
            stats["escalation_levels_distribution"][elevel] = 0
        stats["escalation_levels_distribution"][elevel] += 1
        
        # Department contact frequency
        recipient = reminder.get("recipient", "unknown")
        if recipient not in stats["departments_contacted"]:
            stats["departments_contacted"][recipient] = 0
        stats["departments_contacted"][recipient] += 1
        
        # Peak hours analysis
        hour = datetime.fromisoformat(reminder["timestamp"]).hour
        if hour not in stats["peak_reminder_hours"]:
            stats["peak_reminder_hours"][hour] = 0
        stats["peak_reminder_hours"][hour] += 1
    
    # Success rate calculation
    successful = len([r for r in recent_reminders if r.get("status") == "processed"])
    if recent_reminders:
        stats["success_rate"] = round(successful / len(recent_reminders) * 100, 1)
    
    # Performance insights
    stats["performance_insights"] = {
        "most_common_reminder_type": max(stats["reminder_types_distribution"].items(), key=lambda x: x[1])[0] if stats["reminder_types_distribution"] else "none",
        "highest_escalation_level_used": max(stats["escalation_levels_distribution"].items(), key=lambda x: x[1])[0] if stats["escalation_levels_distribution"] else "none",
        "most_contacted_department": max(stats["departments_contacted"].items(), key=lambda x: x[1])[0] if stats["departments_contacted"] else "none",
        "peak_reminder_hour": max(stats["peak_reminder_hours"].items(), key=lambda x: x[1])[0] if stats["peak_reminder_hours"] else 9
    }
    
    return stats