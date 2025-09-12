import json
import os
import threading
from datetime import datetime

KNOWLEDGE_PATH = os.path.dirname(__file__)
STATE_FILE = os.path.join(KNOWLEDGE_PATH, "shared_state.json")
LOCK = threading.Lock()

def _load_state():
    if not os.path.exists(STATE_FILE):
        return {"complaints": {}, "messages": []}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"complaints": {}, "messages": []}

def _save_state(state):
    with LOCK:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

def get_complaint(complaint_id):
    state = _load_state()
    return state["complaints"].get(complaint_id)

def save_complaint(complaint_id, complaint_data):
    state = _load_state()
    state["complaints"][complaint_id] = complaint_data
    _save_state(state)

def delete_complaint(complaint_id):
    state = _load_state()
    if complaint_id in state["complaints"]:
        del state["complaints"][complaint_id]
        _save_state(state)

def add_message(sender_agent, receiver_agent, message_type, content, metadata=None):
    state = _load_state()
    message = {
        "id": len(state["messages"]) + 1,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "sender": sender_agent,
        "receiver": receiver_agent,
        "type": message_type,
        "content": content,
        "metadata": metadata or {},
        "read": False
    }
    state["messages"].append(message)
    _save_state(state)
    return message

def get_messages_for_agent(agent_name, unread_only=True):
    state = _load_state()
    messages = [m for m in state["messages"] if m["receiver"] == agent_name]
    if unread_only:
        messages = [m for m in messages if not m.get("read", False)]
    return messages

def mark_message_read(message_id):
    state = _load_state()
    for m in state["messages"]:
        if m["id"] == message_id:
            m["read"] = True
            _save_state(state)
            return True
    return False

def clear_messages_for_agent(agent_name):
    state = _load_state()
    state["messages"] = [m for m in state["messages"] if m["receiver"] != agent_name]
    _save_state(state)
