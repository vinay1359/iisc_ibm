# knowledge/shared_memory.py
# This acts as a shared memory system for agent communication

import json
import os
from datetime import datetime
from typing import Dict, Any, List

KNOWLEDGE_PATH = os.path.dirname(__file__)

class SharedMemory:
    """Shared memory system for inter-agent communication via knowledge folder"""
    
    def __init__(self):
        self.memory_file = os.path.join(KNOWLEDGE_PATH, "agent_shared_memory.json")
        self.message_queue_file = os.path.join(KNOWLEDGE_PATH, "agent_message_queue.json")
        self.active_complaints_file = os.path.join(KNOWLEDGE_PATH, "active_complaints.json")
        self.ensure_files_exist()
    
    def ensure_files_exist(self):
        """Ensure all memory files exist with proper structure"""
        files_structure = {
            self.memory_file: {
                "last_updated": datetime.now().isoformat(),
                "agent_status": {
                    "Chat_Agent": {"status": "idle", "last_activity": "", "processed_count": 0},
                    "Router_Agent": {"status": "idle", "last_activity": "", "routed_count": 0},
                    "Tracker_Agent": {"status": "monitoring", "last_activity": "", "tracked_count": 0},
                    "Follow_Agent": {"status": "idle", "last_activity": "", "reminders_sent": 0},
                    "Escalate_Agent": {"status": "idle", "last_activity": "", "escalations_count": 0},
                    "Analytics_Agent": {"status": "idle", "last_activity": "", "reports_generated": 0}
                },
                "global_counters": {
                    "total_complaints": 0,
                    "complaints_today": 0,
                    "resolved_complaints": 0,
                    "overdue_complaints": 0
                },
                "system_alerts": []
            },
            self.message_queue_file: {
                "message_id_counter": 0,
                "messages": [],
                "processed_messages": []
            },
            self.active_complaints_file: {
                "complaints": {},
                "complaint_id_counter": 1000,  # Start from 1000
                "last_updated": datetime.now().isoformat()
            }
        }
        
        for file_path, default_data in files_structure.items():
            if not os.path.exists(file_path):
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(default_data, f, ensure_ascii=False, indent=2)

# Create tools that use shared memory for agent communication

# tools/shared_memory_tool.py
from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
import json
import os
from datetime import datetime

KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), "../knowledge")
MEMORY_FILE = os.path.join(KNOWLEDGE_PATH, "agent_shared_memory.json")
MESSAGE_QUEUE_FILE = os.path.join(KNOWLEDGE_PATH, "agent_message_queue.json")
ACTIVE_COMPLAINTS_FILE = os.path.join(KNOWLEDGE_PATH, "active_complaints.json")

def ensure_memory_files():
    """Ensure memory files exist"""
    os.makedirs(KNOWLEDGE_PATH, exist_ok=True)
    
    if not os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "last_updated": datetime.now().isoformat(),
                "agent_status": {},
                "global_counters": {"total_complaints": 0},
                "system_alerts": []
            }, f, ensure_ascii=False, indent=2)

@tool(
    name="send_message_to_agent",
    description="Sends a message to another agent via shared memory queue",
    permission=ToolPermission.READ_WRITE
)
def send_message_to_agent(sender_agent: str, recipient_agent: str, message_type: str, data: dict, priority: str = "MEDIUM") -> dict:
    """
    Send message to another agent through shared memory queue.
    
    Args:
        sender_agent (str): Name of sending agent
        recipient_agent (str): Name of recipient agent
        message_type (str): Type of message (complaint_processed, routing_request, etc.)
        data (dict): Message payload
        priority (str): Message priority (LOW, MEDIUM, HIGH, CRITICAL)
    """
    ensure_memory_files()
    current_time = datetime.now()
    
    try:
        # Load message queue
        with open(MESSAGE_QUEUE_FILE, 'r', encoding='utf-8') as f:
            queue_data = json.load(f)
        
        # Create message
        message = {
            "message_id": queue_data.get("message_id_counter", 0) + 1,
            "sender": sender_agent,
            "recipient": recipient_agent,
            "message_type": message_type,
            "data": data,
            "priority": priority,
            "timestamp": current_time.isoformat(),
            "status": "pending",
            "retry_count": 0
        }
        
        # Add to queue
        if "messages" not in queue_data:
            queue_data["messages"] = []
        queue_data["messages"].append(message)
        queue_data["message_id_counter"] = message["message_id"]
        
        # Sort by priority (CRITICAL first)
        priority_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        queue_data["messages"].sort(key=lambda x: priority_order.get(x["priority"], 3))
        
        # Save updated queue
        with open(MESSAGE_QUEUE_FILE, 'w', encoding='utf-8') as f:
            json.dump(queue_data, f, ensure_ascii=False, indent=2)
        
        return {
            "success": True,
            "message_id": message["message_id"],
            "queued_at": current_time.isoformat(),
            "queue_position": len(queue_data["messages"])
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@tool(
    name="get_messages_for_agent",
    description="Retrieves pending messages for a specific agent",
    permission=ToolPermission.READ_WRITE
)
def get_messages_for_agent(agent_name: str, mark_as_read: bool = True) -> dict:
    """
    Get pending messages for an agent.
    
    Args:
        agent_name (str): Name of the agent
        mark_as_read (bool): Whether to mark messages as read
    """
    ensure_memory_files()
    
    try:
        with open(MESSAGE_QUEUE_FILE, 'r', encoding='utf-8') as f:
            queue_data = json.load(f)
        
        # Filter messages for this agent
        agent_messages = [
            msg for msg in queue_data.get("messages", [])
            if msg.get("recipient") == agent_name and msg.get("status") == "pending"
        ]
        
        if mark_as_read and agent_messages:
            # Mark as read and move to processed
            remaining_messages = [
                msg for msg in queue_data.get("messages", [])
                if not (msg.get("recipient") == agent_name and msg.get("status") == "pending")
            ]
            
            # Update message status
            for msg in agent_messages:
                msg["status"] = "read"
                msg["read_at"] = datetime.now().isoformat()
            
            # Move to processed
            if "processed_messages" not in queue_data:
                queue_data["processed_messages"] = []
            queue_data["processed_messages"].extend(agent_messages)
            
            # Keep only last 1000 processed messages
            if len(queue_data["processed_messages"]) > 1000:
                queue_data["processed_messages"] = queue_data["processed_messages"][-1000:]
            
            queue_data["messages"] = remaining_messages
            
            # Save updated queue
            with open(MESSAGE_QUEUE_FILE, 'w', encoding='utf-8') as f:
                json.dump(queue_data, f, ensure_ascii=False, indent=2)
        
        return {
            "success": True,
            "message_count": len(agent_messages),
            "messages": agent_messages
        }
        
    except Exception as e:
        return {"success": False, "error": str(e), "messages": []}

@tool(
    name="update_agent_status",
    description="Updates agent status in shared memory",
    permission=ToolPermission.READ_WRITE
)
def update_agent_status(agent_name: str, status: str, activity: str = "", metadata: dict = {}) -> dict:
    """
    Update agent status in shared memory.
    
    Args:
        agent_name (str): Name of the agent
        status (str): Current status (idle, processing, monitoring, etc.)
        activity (str): Current activity description
        metadata (dict): Additional status metadata
    """
    ensure_memory_files()
    current_time = datetime.now()
    
    try:
        with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
            memory_data = json.load(f)
        
        if "agent_status" not in memory_data:
            memory_data["agent_status"] = {}
        
        memory_data["agent_status"][agent_name] = {
            "status": status,
            "last_activity": activity,
            "last_updated": current_time.isoformat(),
            **metadata
        }
        
        memory_data["last_updated"] = current_time.isoformat()
        
        with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(memory_data, f, ensure_ascii=False, indent=2)
        
        return {"success": True, "updated_at": current_time.isoformat()}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@tool(
    name="store_complaint_data",
    description="Stores complaint data in shared memory for other agents to access",
    permission=ToolPermission.READ_WRITE
)
def store_complaint_data(complaint_id: str, complaint_data: dict, update_existing: bool = True) -> dict:
    """
    Store complaint data in shared memory.
    
    Args:
        complaint_id (str): Unique complaint identifier
        complaint_data (dict): Complaint information
        update_existing (bool): Whether to update existing complaint
    """
    ensure_memory_files()
    current_time = datetime.now()
    
    try:
        with open(ACTIVE_COMPLAINTS_FILE, 'r', encoding='utf-8') as f:
            complaints_data = json.load(f)
        
        if "complaints" not in complaints_data:
            complaints_data["complaints"] = {}
        
        # Generate ID if not provided
        if not complaint_id or complaint_id == "auto":
            complaints_data["complaint_id_counter"] = complaints_data.get("complaint_id_counter", 1000) + 1
            complaint_id = f"CMP-{complaints_data['complaint_id_counter']}"
        
        # Store or update complaint
        if complaint_id in complaints_data["complaints"] and not update_existing:
            return {"success": False, "error": "Complaint already exists", "complaint_id": complaint_id}
        
        complaints_data["complaints"][complaint_id] = {
            **complaint_data,
            "complaint_id": complaint_id,
            "last_updated": current_time.isoformat(),
            "created_at": complaints_data["complaints"].get(complaint_id, {}).get("created_at", current_time.isoformat())
        }
        
        complaints_data["last_updated"] = current_time.isoformat()
        
        with open(ACTIVE_COMPLAINTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(complaints_data, f, ensure_ascii=False, indent=2)
        
        return {
            "success": True,
            "complaint_id": complaint_id,
            "stored_at": current_time.isoformat()
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

@tool(
    name="get_complaint_data",
    description="Retrieves complaint data from shared memory",
    permission=ToolPermission.READ_ONLY
)
def get_complaint_data(complaint_id: str = "", status_filter: str = "", limit: int = 50) -> dict:
    """
    Get complaint data from shared memory.
    
    Args:
        complaint_id (str): Specific complaint ID (optional)
        status_filter (str): Filter by status (optional)
        limit (int): Maximum complaints to return
    """
    ensure_memory_files()
    
    try:
        with open(ACTIVE_COMPLAINTS_FILE, 'r', encoding='utf-8') as f:
            complaints_data = json.load(f)
        
        complaints = complaints_data.get("complaints", {})
        
        if complaint_id:
            # Return specific complaint
            if complaint_id in complaints:
                return {
                    "success": True,
                    "complaint": complaints[complaint_id]
                }
            else:
                return {"success": False, "error": "Complaint not found"}
        
        # Filter and return multiple complaints
        filtered_complaints = []
        for cid, data in complaints.items():
            if status_filter and data.get("current_status") != status_filter:
                continue
            filtered_complaints.append(data)
            if len(filtered_complaints) >= limit:
                break
        
        return {
            "success": True,
            "complaint_count": len(filtered_complaints),
            "complaints": filtered_complaints
        }
        
    except Exception as e:
        return {"success": False, "error": str(e), "complaints": []}