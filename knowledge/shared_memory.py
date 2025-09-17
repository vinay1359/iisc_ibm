# knowledge/shared_memory.py

import json
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

KNOWLEDGE_PATH = os.path.dirname(__file__)
ACTIVE_COMPLAINTS_PATH = os.path.join(KNOWLEDGE_PATH, "active_complaints.json")
AGENT_MESSAGES_PATH = os.path.join(KNOWLEDGE_PATH, "agent_messages.json")
SYSTEM_STATE_PATH = os.path.join(KNOWLEDGE_PATH, "system_state.json")

class SharedMemorySystem:
    def __init__(self):
        self._lock = threading.Lock()
        self._ensure_files_exist()
    
    def _ensure_files_exist(self):
        """Ensure all required JSON files exist with proper structure"""
        default_files = {
            ACTIVE_COMPLAINTS_PATH: {"complaints": {}, "last_updated": ""},
            AGENT_MESSAGES_PATH: {"messages": [], "last_message_id": 0},
            SYSTEM_STATE_PATH: {"agents": {}, "system_status": "running", "last_activity": ""}
        }
        
        os.makedirs(KNOWLEDGE_PATH, exist_ok=True)
        
        for file_path, default_content in default_files.items():
            if not os.path.exists(file_path):
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(default_content, f, ensure_ascii=False, indent=2)
    
    def _load_state(self) -> Dict:
        """Load current system state"""
        try:
            with open(ACTIVE_COMPLAINTS_PATH, "r", encoding="utf-8") as f:
                complaints_data = json.load(f)
            
            with open(AGENT_MESSAGES_PATH, "r", encoding="utf-8") as f:
                messages_data = json.load(f)
            
            with open(SYSTEM_STATE_PATH, "r", encoding="utf-8") as f:
                system_data = json.load(f)
            
            return {
                "complaints": complaints_data.get("complaints", {}),
                "messages": messages_data.get("messages", []),
                "last_message_id": messages_data.get("last_message_id", 0),
                "agents": system_data.get("agents", {}),
                "system_status": system_data.get("system_status", "running")
            }
        except Exception as e:
            print(f"Error loading state: {e}")
            return {
                "complaints": {},
                "messages": [],
                "last_message_id": 0,
                "agents": {},
                "system_status": "error"
            }
    
    def _save_state(self, state: Dict):
        """Save system state to files"""
        try:
            # Save complaints
            complaints_data = {
                "complaints": state.get("complaints", {}),
                "last_updated": datetime.now().isoformat()
            }
            with open(ACTIVE_COMPLAINTS_PATH, "w", encoding="utf-8") as f:
                json.dump(complaints_data, f, ensure_ascii=False, indent=2)
            
            # Save messages
            messages_data = {
                "messages": state.get("messages", []),
                "last_message_id": state.get("last_message_id", 0)
            }
            with open(AGENT_MESSAGES_PATH, "w", encoding="utf-8") as f:
                json.dump(messages_data, f, ensure_ascii=False, indent=2)
            
            # Save system state
            system_data = {
                "agents": state.get("agents", {}),
                "system_status": state.get("system_status", "running"),
                "last_activity": datetime.now().isoformat()
            }
            with open(SYSTEM_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump(system_data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            print(f"Error saving state: {e}")
    
    def save_complaint(self, complaint_id: str, complaint_data: Dict):
        """Save or update a complaint"""
        with self._lock:
            state = self._load_state()
            state["complaints"][complaint_id] = complaint_data
            complaint_data["last_modified"] = datetime.now().isoformat()
            self._save_state(state)
    
    def get_complaint(self, complaint_id: str) -> Optional[Dict]:
        """Get a specific complaint by ID"""
        with self._lock:
            state = self._load_state()
            return state["complaints"].get(complaint_id)
    
    def get_all_complaints(self) -> Dict[str, Dict]:
        """Get all complaints"""
        with self._lock:
            state = self._load_state()
            return state.get("complaints", {})
    
    def add_chat_message(self, complaint_id: str, message: str, user_type: str, timestamp: str):
        """Add a chat message to a complaint"""
        with self._lock:
            state = self._load_state()
            
            if complaint_id in state["complaints"]:
                complaint = state["complaints"][complaint_id]
                if "chat_messages" not in complaint:
                    complaint["chat_messages"] = []
                
                chat_message = {
                    "message": message,
                    "user_type": user_type,
                    "timestamp": timestamp
                }
                
                complaint["chat_messages"].append(chat_message)
                self._save_state(state)
                return True
            
            return False
    
    def add_message(self, sender_agent: str, receiver_agent: str, message_type: str, content: Dict):
        """Add a message between agents"""
        with self._lock:
            state = self._load_state()
            
            message_id = state["last_message_id"] + 1
            message = {
                "id": message_id,
                "sender_agent": sender_agent,
                "receiver_agent": receiver_agent,
                "type": message_type,
                "content": content,
                "timestamp": datetime.now().isoformat(),
                "read": False,
                "processed": False
            }
            
            state["messages"].append(message)
            state["last_message_id"] = message_id
            
            # Keep only last 1000 messages to prevent file bloat
            if len(state["messages"]) > 1000:
                state["messages"] = state["messages"][-1000:]
            
            self._save_state(state)
            return message_id
    
    def get_messages_for_agent(self, agent_name: str) -> List[Dict]:
        """Get unread messages for a specific agent"""
        with self._lock:
            state = self._load_state()
            agent_messages = [
                msg for msg in state["messages"] 
                if msg["receiver_agent"] == agent_name and not msg["read"]
            ]
            return agent_messages
    
    def mark_message_read(self, message_id: int):
        """Mark a message as read"""
        with self._lock:
            state = self._load_state()
            for msg in state["messages"]:
                if msg["id"] == message_id:
                    msg["read"] = True
                    msg["read_at"] = datetime.now().isoformat()
                    break
            self._save_state(state)
    
    def mark_message_processed(self, message_id: int):
        """Mark a message as processed"""
        with self._lock:
            state = self._load_state()
            for msg in state["messages"]:
                if msg["id"] == message_id:
                    msg["processed"] = True
                    msg["processed_at"] = datetime.now().isoformat()
                    break
            self._save_state(state)
    
    def update_agent_status(self, agent_name: str, status: str, metadata: Dict = {}):
        """Update agent status and activity"""
        with self._lock:
            state = self._load_state()
            if "agents" not in state:
                state["agents"] = {}
            
            state["agents"][agent_name] = {
                "status": status,
                "last_activity": datetime.now().isoformat(),
                "metadata": metadata
            }
            self._save_state(state)
    
    def get_agent_status(self, agent_name: str) -> Optional[Dict]:
        """Get status of a specific agent"""
        with self._lock:
            state = self._load_state()
            return state.get("agents", {}).get(agent_name)
    
    def get_system_health(self) -> Dict:
        """Get overall system health and statistics"""
        with self._lock:
            state = self._load_state()
            
            # Count complaints by status
            status_counts = {}
            for complaint in state["complaints"].values():
                status = complaint.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1
            
            # Count unprocessed messages
            unprocessed_messages = len([msg for msg in state["messages"] if not msg["processed"]])
            
            # Count active agents
            active_agents = len([
                agent for agent, info in state.get("agents", {}).items()
                if info.get("status") == "active"
            ])
            
            return {
                "system_status": state.get("system_status", "unknown"),
                "total_complaints": len(state["complaints"]),
                "complaints_by_status": status_counts,
                "unprocessed_messages": unprocessed_messages,
                "total_messages": len(state["messages"]),
                "active_agents": active_agents,
                "last_activity": state.get("agents", {}).get("last_activity", "never")
            }
    
    def cleanup_old_data(self, days_to_keep: int = 30):
        """Clean up old processed messages and resolved complaints"""
        with self._lock:
            state = self._load_state()
            current_time = datetime.now()
            cutoff_time = current_time - timedelta(days=days_to_keep)
            
            # Clean old processed messages
            cleaned_messages = []
            for msg in state["messages"]:
                try:
                    msg_time = datetime.fromisoformat(msg["timestamp"])
                    if msg_time > cutoff_time or not msg.get("processed", False):
                        cleaned_messages.append(msg)
                except ValueError:
                    # Keep messages with invalid timestamps for manual review
                    cleaned_messages.append(msg)
            
            state["messages"] = cleaned_messages
            
            # Optionally move resolved complaints to archive
            archived_complaints = {}
            active_complaints = {}
            
            for complaint_id, complaint in state["complaints"].items():
                try:
                    last_modified = datetime.fromisoformat(complaint.get("last_modified", complaint.get("timestamp", "")))
                    if complaint.get("status") == "BLACK" and last_modified < cutoff_time:
                        archived_complaints[complaint_id] = complaint
                    else:
                        active_complaints[complaint_id] = complaint
                except ValueError:
                    # Keep complaints with invalid timestamps
                    active_complaints[complaint_id] = complaint
            
            state["complaints"] = active_complaints
            
            # Save archived complaints if any
            if archived_complaints:
                archive_path = os.path.join(KNOWLEDGE_PATH, "archived_complaints.json")
                try:
                    if os.path.exists(archive_path):
                        with open(archive_path, "r", encoding="utf-8") as f:
                            existing_archive = json.load(f)
                    else:
                        existing_archive = {"archived_complaints": {}}
                    
                    existing_archive["archived_complaints"].update(archived_complaints)
                    existing_archive["last_updated"] = {"timestamp": current_time.isoformat()}
                    
                    with open(archive_path, "w", encoding="utf-8") as f:
                        json.dump(existing_archive, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    print(f"Error archiving complaints: {e}")
            
            self._save_state(state)
            
            return {
                "messages_cleaned": len(state["messages"]) - len(cleaned_messages),
                "complaints_archived": len(archived_complaints),
                "cleanup_completed_at": current_time.isoformat()
            }

# Global instance
_shared_memory = SharedMemorySystem()

# Convenience functions for agent use
def save_complaint(complaint_id: str, complaint_data: Dict):
    return _shared_memory.save_complaint(complaint_id, complaint_data)

def get_complaint(complaint_id: str) -> Optional[Dict]:
    return _shared_memory.get_complaint(complaint_id)

def get_all_complaints() -> Dict[str, Dict]:
    return _shared_memory.get_all_complaints()

def add_message(sender_agent: str, receiver_agent: str, message_type: str, content: Dict) -> int:
    return _shared_memory.add_message(sender_agent, receiver_agent, message_type, content)

def get_messages_for_agent(agent_name: str) -> List[Dict]:
    return _shared_memory.get_messages_for_agent(agent_name)

def mark_message_read(message_id: int):
    return _shared_memory.mark_message_read(message_id)

def mark_message_processed(message_id: int):
    return _shared_memory.mark_message_processed(message_id)

def update_agent_status(agent_name: str, status: str, metadata: Dict = {}):
    return _shared_memory.update_agent_status(agent_name, status, metadata)

def get_system_health() -> Dict:
    return _shared_memory.get_system_health()

def add_chat_message(complaint_id: str, message: str, user_type: str, timestamp: str) -> bool:
    return _shared_memory.add_chat_message(complaint_id, message, user_type, timestamp)