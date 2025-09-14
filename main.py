from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
import json
import uuid
import http.client
import ssl
from datetime import datetime, timedelta, timezone
import asyncio
import logging
from pathlib import Path
import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Citizen Voice AI", description="Government Accountability System with Watson Integration")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# IBM Watson Configuration
@dataclass
class WatsonConfig:
    region_code: str = os.getenv("WATSON_REGION_CODE", "us-south")
    jwt_token: str = os.getenv("WATSON_JWT_TOKEN", "")
    instance_id: str = os.getenv("WATSON_INSTANCE_ID", "")
    base_url: str = "dl.watsonx.ai"

    def is_configured(self) -> bool:
        return bool(self.jwt_token and self.instance_id and self.region_code)

watson_config = WatsonConfig()

# Pydantic models
class ComplaintInput(BaseModel):
    citizenName: str
    phone: str
    location: str
    complaintText: str
    isPublic: bool = False

class ChatMessage(BaseModel):
    message: str
    user_id: Optional[str] = None

class ComplaintResponse(BaseModel):
    complaint_id: str
    status: str
    category: str
    urgency: str
    department: str
    deadlines: Dict[str, str]
    agent_processing: Dict[str, Any]

class AgentStatus(BaseModel):
    name: str
    status: str
    message: str
    timestamp: str

class ChatResponse(BaseModel):
    message: str
    complaint_id: Optional[str] = None
    agent_updates: List[Dict] = []
    processing_complete: bool = False

class ComplaintResponseInput(BaseModel):
    status: str
    message: str
    estimated_completion: Optional[str] = None
    department: str
    officer_name: str

# In-memory storage (replace with database in production)
complaints_db: Dict[str, Dict] = {}
agent_statuses: Dict[str, Dict] = {}
active_connections: Dict[str, WebSocket] = {}

# Watson Integration Class
class WatsonIntegration:
    def __init__(self, config: WatsonConfig):
        self.config = config

    async def get_skills(self) -> Dict:
        """Get available Watson skills"""
        if not self.config.is_configured():
            logger.warning("Watson not configured, using mock response")
            return {"skills": [], "mock": True}

        try:
            conn = http.client.HTTPSConnection(f"{self.config.region_code}.{self.config.base_url}")

            headers = {
                'Authorization': f"Bearer {self.config.jwt_token}",
                'accept': "application/json"
            }

            conn.request("GET", f"/instances/{self.config.instance_id}/v1/orchestrate/digital-employees/allskills", headers=headers)

            res = conn.getresponse()
            data = res.read()

            if res.status == 200:
                return json.loads(data.decode("utf-8"))
            else:
                logger.error(f"Watson API error: {res.status}")
                return {"error": f"Watson API error: {res.status}", "mock": True}

        except Exception as e:
            logger.error(f"Watson connection error: {str(e)}")
            return {"error": str(e), "mock": True}

    async def analyze_text(self, text: str) -> Dict:
        """Analyze text using Watson (or fallback to local processing)"""
        if not self.config.is_configured():
            return self._local_text_analysis(text)

        # Implement Watson text analysis here
        # For now, falling back to local analysis
        return self._local_text_analysis(text)

    def _local_text_analysis(self, text: str) -> Dict:
        """Local text analysis fallback"""
        text_lower = text.lower()

        # Category detection
        categories = {
            "electricity": ["electricity", "power", "light", "transformer", "outage", "blackout"],
            "water": ["water", "tap", "supply", "pipeline", "pressure", "leak"],
            "road": ["road", "pothole", "traffic", "signal", "street", "highway"],
            "sanitation": ["garbage", "waste", "clean", "drain", "toilet", "sewage"],
            "health": ["health", "hospital", "doctor", "medicine", "ambulance"],
            "general": []
        }

        category = "general"
        for cat, keywords in categories.items():
            if any(keyword in text_lower for keyword in keywords):
                category = cat
                break

        # Urgency detection
        urgent_keywords = ["emergency", "urgent", "critical", "immediate", "dangerous"]
        high_keywords = ["days", "week", "problem", "issue", "not working", "broken"]
        low_keywords = ["sometime", "when possible", "eventually", "convenience"]

        if any(keyword in text_lower for keyword in urgent_keywords):
            urgency = "CRITICAL"
        elif any(keyword in text_lower for keyword in high_keywords):
            urgency = "HIGH"
        elif any(keyword in text_lower for keyword in low_keywords):
            urgency = "LOW"
        else:
            urgency = "MEDIUM"
        
        # Language detection
        hindi_chars = any('\u0900' <= char <= '\u097F' for char in text)
        language = "Hindi" if hindi_chars else "English"
        
        return {
            "category": category.title(),
            "urgency": urgency,
            "language": language,
            "confidence": 0.85,
            "keywords_found": [kw for cat, keywords in categories.items() 
                              if cat == category for kw in keywords 
                              if kw in text_lower][:5]
        }

watson = WatsonIntegration(watson_config)

# Shared Memory System
class SharedMemory:
    def __init__(self):
        self.complaints = {}
        self.messages = []
        self.agent_states = {}
        self.analytics_data = {}
        self.websocket_connections: Dict[str, WebSocket] = {}
        self.dashboard_connections: List[WebSocket] = []
    
    def save_complaint(self, complaint_id: str, complaint_data: Dict):
        self.complaints[complaint_id] = complaint_data
        logger.info(f"Saved complaint {complaint_id}")
    
    def get_complaint(self, complaint_id: str) -> Dict:
        return self.complaints.get(complaint_id, {})
    
    def add_message(self, sender_agent: str, receiver_agent: str,
                   message_type: str, content: Dict):
        message = {
            "id": str(uuid.uuid4()),
            "sender": sender_agent,
            "receiver": receiver_agent,
            "type": message_type,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "read": False
        }
        self.messages.append(message)
        logger.info(f"Message from {sender_agent} to {receiver_agent}: {message_type}")
    
    async def broadcast_message(self, message: Dict, user_id: Optional[str] = None):
        """Broadcast a message to a specific user or all users."""
        if user_id and user_id in self.websocket_connections:
            try:
                await self.websocket_connections[user_id].send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending message to {user_id}: {e}")
                self.websocket_connections.pop(user_id, None)
        elif not user_id:
            # Broadcast to all
            for connection in list(self.websocket_connections.values()):
                try:
                    await connection.send_text(json.dumps(message))
                except Exception:
                    # Remove disconnected client
                    for uid, ws in list(self.websocket_connections.items()):
                        if ws == connection:
                            self.websocket_connections.pop(uid, None)
                            break

    async def broadcast_to_dashboards(self, message: Dict):
        """Broadcast a message to all connected dashboard clients."""
        for connection in self.dashboard_connections[:]:  # Iterate over a copy
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending to dashboard: {e}")
                self.dashboard_connections.remove(connection)

    async def broadcast_agent_update(self, complaint_id: str, agent_name: str, status: str, message: str = ""):
        """Broadcast agent status updates to all connected WebSocket clients"""
        update = {
            "type": "agent_update",
            "complaint_id": complaint_id,
            "agent": agent_name,
            "status": status,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Send to all active WebSocket connections
        await self.broadcast_message(update)

shared_memory = SharedMemory()

# Enhanced AI Agent Classes
class BaseAgent:
    def __init__(self, name: str, description: str, icon: str = "🤖"):
        self.name = name
        self.description = description
        self.icon = icon
        self.status = "ready"
        self.last_activity = datetime.now(timezone.utc)
    
    async def update_status(self, status: str, message: str = "", complaint_id: str = ""):
        self.status = status
        self.last_activity = datetime.now(timezone.utc)
        agent_statuses[self.name] = {
            "status": status,
            "message": message,
            "timestamp": self.last_activity.isoformat()
        }
        
        # Broadcast update to WebSocket clients
        await shared_memory.broadcast_agent_update(complaint_id, self.name, status, message)

class ChatAgent(BaseAgent):
    def __init__(self):
        super().__init__("Chat_Agent", "Processes and categorizes citizen complaints", "💬")
    
    async def process_complaint(self, complaint_data: Dict, complaint_id: str) -> Dict:
        await self.update_status("processing", "Step 1: Parsing citizen complaint text...", complaint_id)
        await asyncio.sleep(0.5)

        await self.update_status("processing", "Step 2: Identifying keywords and entities...", complaint_id)
        await asyncio.sleep(0.5)

        await self.update_status("processing", "Step 3: Determining complaint category and urgency...", complaint_id)
        await asyncio.sleep(0.5)
        
        # Use Watson for analysis
        analysis = await watson.analyze_text(complaint_data["complaintText"])
        
        # complaint_id is now passed in

        reasoning = f"The complaint was classified as '{analysis.get('category', 'General')}' because it contained keywords like '{', '.join(analysis.get('keywords_found', []))}'. The urgency was set to '{analysis.get('urgency', 'MEDIUM')}' based on the language used."
        
        processed_complaint = {
            "id": complaint_id,
            "user_id": complaint_data.get("user_id"),
            "text": complaint_data["complaintText"],
            "citizen_name": complaint_data["citizenName"],
            "phone": complaint_data["phone"],
            "location": complaint_data["location"],
            "is_public": complaint_data["isPublic"],
            "language": analysis.get("language", "English"),
            "category": analysis.get("category", "General"),
            "urgency": analysis.get("urgency", "MEDIUM"),
            "confidence": analysis.get("confidence", 0.0),
            "keywords": analysis.get("keywords_found", []),
            "status": "RED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "watson_analysis": analysis,
            "processing_history": [
                {
                    "agent": "Chat_Agent",
                    "action": "complaint_processed",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            ]
        }
        
        shared_memory.save_complaint(complaint_id, processed_complaint)
        
        # Send message to Router Agent
        shared_memory.add_message(
            "Chat_Agent", "Router_Agent", "new_complaint",
            {"complaint_id": complaint_id}
        )
        
        await self.update_status("completed", f"Complaint classified as {analysis.get('category', 'General')} with {analysis.get('urgency', 'MEDIUM')} urgency", complaint_id)
        
        return {
            "complaint_id": complaint_id,
            "category": analysis.get("category", "General"),
            "urgency": analysis.get("urgency", "MEDIUM"),
            "language": analysis.get("language", "English"),
            "confidence": analysis.get("confidence", 0.0),
            "reasoning": reasoning
        }

class RouterAgent(BaseAgent):
    def __init__(self):
        super().__init__("Router_Agent", "Routes complaints to appropriate departments", "🎯")
        self.department_mapping = {
            "Electricity": "Delhi Electricity Regulatory Commission (DERC)",
            "Water": "Delhi Jal Board (DJB)",
            "Road": "Public Works Department (PWD)",
            "Sanitation": "Municipal Corporation of Delhi (MCD)",
            "Health": "Department of Health & Family Welfare",
            "General": "District Collector Office"
        }
    
    async def route_complaint(self, complaint_id: str) -> Dict:
        await self.update_status("processing", "Step 1: Analyzing complaint category and location...", complaint_id)
        await asyncio.sleep(0.5)
        await self.update_status("processing", "Step 2: Matching with government department directory...", complaint_id)
        await asyncio.sleep(0.5)
        
        complaint = shared_memory.get_complaint(complaint_id)
        if not complaint:
            raise ValueError(f"Complaint {complaint_id} not found")
        
        # Route to department
        department = self.department_mapping.get(complaint["category"], 
                                               self.department_mapping["General"])
        
        # Calculate deadlines based on urgency
        deadlines = self.calculate_deadlines(complaint["urgency"])
        
        # Update complaint
        complaint["status"] = "ORANGE"
        complaint["assigned_department"] = department
        complaint["deadlines"] = deadlines
        complaint["processing_history"].append({
            "agent": "Router_Agent",
            "action": "routed_to_department",
            "department": department,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        shared_memory.save_complaint(complaint_id, complaint)
        
        # Send to Tracker Agent
        shared_memory.add_message(
            "Router_Agent", "Tracker_Agent", "routed_complaint",
            {"complaint_id": complaint_id}
        )
        
        await self.update_status("completed", f"Routed to: {department}", complaint_id)
        
        return {
            "department": department,
            "deadlines": deadlines
        }
    
    def calculate_deadlines(self, urgency: str) -> Dict[str, str]:
        now = datetime.now(timezone.utc)
        deadlines_hours = {
            "CRITICAL": {"ack": 4, "resolve": 24},
            "HIGH": {"ack": 24, "resolve": 120},
            "MEDIUM": {"ack": 48, "resolve": 240},
            "LOW": {"ack": 168, "resolve": 720}
        }
        
        hours = deadlines_hours.get(urgency, deadlines_hours["MEDIUM"])
        
        return {
            "acknowledgment": (now + timedelta(hours=hours["ack"])).isoformat(),
            "resolution": (now + timedelta(hours=hours["resolve"])).isoformat()
        }

class TrackerAgent(BaseAgent):
    def __init__(self):
        super().__init__("Tracker_Agent", "Monitors complaint progress", "👁️")
    
    async def setup_tracking(self, complaint_id: str) -> Dict:
        await self.update_status("processing", "Step 1: Calculating estimated resolution deadlines...", complaint_id)
        await asyncio.sleep(0.4)
        await self.update_status("processing", "Step 2: Initializing tracking monitor...", complaint_id)
        await asyncio.sleep(0.4)
        
        complaint = shared_memory.get_complaint(complaint_id)
        if not complaint:
            raise ValueError(f"Complaint {complaint_id} not found")
        
        # Set up tracking
        complaint["tracking"] = {
            "monitoring_active": True,
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "check_frequency": "hourly",
            "notifications_enabled": True
        }
        complaint["processing_history"].append({
            "agent": "Tracker_Agent",
            "action": "tracking_activated",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        shared_memory.save_complaint(complaint_id, complaint)
        
        # Notify other agents
        for agent in ["Follow_Agent", "Analytics_Agent", "Escalate_Agent"]:
            shared_memory.add_message(
                "Tracker_Agent", agent, "tracked_complaint",
                {"complaint_id": complaint_id}
            )
        
        await self.update_status("completed", "Tracking and deadlines established.", complaint_id)
        
        return {"tracking_active": True}

    async def process_government_response(self, complaint_id: str, response_data: Dict):
        await self.update_status("processing", "Step 1: Analyzing government response...", complaint_id)
        await asyncio.sleep(0.5)

        complaint = shared_memory.get_complaint(complaint_id)
        new_status = response_data.get("status", complaint["status"])
        complaint["status"] = new_status
        shared_memory.save_complaint(complaint_id, complaint)

        await self.update_status("completed", f"Government response processed. Status updated to {new_status}.", complaint_id)

        # Notify FollowAgent to adjust reminders
        await agents["follow"].handle_response_update(complaint_id, new_status)

        # Notify user about the update
        user_id = complaint.get("user_id")
        if user_id:
            await shared_memory.broadcast_message({
                "type": "government_response",
                "complaint_id": complaint_id,
                "status": new_status,
                "message": f"An official response has been recorded: '{response_data['message']}'",
                "department": response_data['department'],
                "officer_name": response_data['officer_name']
            }, user_id)

class FollowAgent(BaseAgent):
    def __init__(self):
        super().__init__("Follow_Agent", "Sends automated reminders", "🔔")
    
    async def schedule_reminders(self, complaint_id: str) -> Dict:
        await self.update_status("processing", "Step 1: Defining reminder schedule based on urgency...", complaint_id)
        await asyncio.sleep(0.3)
        await self.update_status("processing", "Step 2: Scheduling follow-up tasks...", complaint_id)
        await asyncio.sleep(0.4)
        
        complaint = shared_memory.get_complaint(complaint_id)
        if not complaint:
            raise ValueError(f"Complaint {complaint_id} not found")
        
        now = datetime.now(timezone.utc)
        urgency_multiplier = {
            "CRITICAL": 0.25,
            "HIGH": 0.5,
            "MEDIUM": 1.0,
            "LOW": 2.0
        }.get(complaint["urgency"], 1.0)
        
        complaint["reminders"] = {
            "first_reminder": (now + timedelta(hours=int(12 * urgency_multiplier))).isoformat(),
            "urgent_reminder": (now + timedelta(hours=int(24 * urgency_multiplier))).isoformat(),
            "escalation_reminder": (now + timedelta(hours=int(48 * urgency_multiplier))).isoformat(),
            "reminder_frequency": f"Every {int(24 * urgency_multiplier)} hours"
        }
        complaint["processing_history"].append({
            "agent": "Follow_Agent",
            "action": "reminders_scheduled",
            "timestamp": now.astimezone(timezone.utc).isoformat()
        })
        
        shared_memory.save_complaint(complaint_id, complaint)
        
        await self.update_status("completed", f"Automated follow-ups scheduled every {int(24 * urgency_multiplier)} hours", complaint_id)
        
        return {"reminders_scheduled": True, "frequency": f"{int(24 * urgency_multiplier)} hours"}

    async def handle_response_update(self, complaint_id: str, new_status: str):
        await self.update_status("processing", "Adjusting reminders based on new status...", complaint_id)
        complaint = shared_memory.get_complaint(complaint_id)
        if new_status in ["RESOLVED", "CLOSED"]:
            # Cancel future reminders if resolved
            complaint["reminders"] = {}
            shared_memory.save_complaint(complaint_id, complaint)
            await self.update_status("completed", "Reminders cancelled as complaint is resolved.", complaint_id)
        else:
            await self.update_status("completed", "Reminder schedule checked.", complaint_id)

class AnalyticsAgent(BaseAgent):
    def __init__(self):
        super().__init__("Analytics_Agent", "Generates insights and analytics", "📊")
    
    async def analyze_complaint(self, complaint_id: str) -> Dict:
        await self.update_status("processing", "Step 1: Comparing complaint with historical data...", complaint_id)
        await asyncio.sleep(0.6)
        await self.update_status("processing", "Step 2: Generating predictive insights...", complaint_id)
        await asyncio.sleep(0.6)
        
        complaint = shared_memory.get_complaint(complaint_id)
        if not complaint:
            raise ValueError(f"Complaint {complaint_id} not found")
        
        # Advanced analytics
        all_complaints = list(shared_memory.complaints.values())
        
        # Similar complaints analysis
        similar_complaints = [c for c in all_complaints 
                            if c.get("category") == complaint["category"]]
        
        # Location analysis
        location_area = complaint["location"].split(",")[0].strip()
        location_complaints = [c for c in all_complaints 
                             if location_area.lower() in c.get("location", "").lower()]
        
        # Trend analysis
        recent_complaints = [c for c in all_complaints
                           if (datetime.now(timezone.utc) -
                               datetime.fromisoformat(c["timestamp"])).days <= 7]
        
        analytics = {
            "similar_complaints": len(similar_complaints),
            "location_complaints": len(location_complaints),
            "recent_trend": len(recent_complaints),
            "category_rank": self._get_category_rank(complaint["category"]),
            "urgency_distribution": self._get_urgency_stats(),
            "average_resolution_time": f"{self._estimate_resolution_time(complaint)} days",
            "department_rating": f"{7.5 + (len(similar_complaints) * 0.1):.1f}/10",
            "success_probability": f"{max(60, 90 - (len(similar_complaints) * 2))}%",
            "insights": [
                f"This is a {complaint['urgency'].lower()} priority {complaint['category'].lower()} complaint",
                f"Your area has {len(location_complaints)} similar complaints",
                f"Average resolution time for this category is {self._estimate_resolution_time(complaint)} days",
                f"Success rate for similar complaints is {max(60, 90 - (len(similar_complaints) * 2))}%"
            ],
            "recommendations": [
                "Follow up within 24 hours if no acknowledgment",
                "Consider filing an RTI if delayed beyond deadline",
                "Join community groups for similar issues"
            ]
        }
        
        complaint["analytics"] = analytics
        complaint["processing_history"].append({
            "agent": "Analytics_Agent",
            "action": "analytics_generated",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        shared_memory.save_complaint(complaint_id, complaint)
        
        await self.update_status("completed", f"Generated {len(analytics['insights'])} insights.", complaint_id)
        
        return analytics
    
    def _get_category_rank(self, category: str) -> int:
        all_complaints = list(shared_memory.complaints.values())
        category_counts = {}
        for c in all_complaints:
            cat = c.get("category", "General")
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
        for i, (cat, _) in enumerate(sorted_categories):
            if cat == category:
                return i + 1
        return len(sorted_categories)
    
    def _get_urgency_stats(self) -> Dict:
        all_complaints = list(shared_memory.complaints.values())
        urgency_counts = {}
        for c in all_complaints:
            urgency = c.get("urgency", "MEDIUM")
            urgency_counts[urgency] = urgency_counts.get(urgency, 0) + 1
        return urgency_counts
    
    def _estimate_resolution_time(self, complaint: Dict) -> int:
        urgency_days = {
            "CRITICAL": 2,
            "HIGH": 5,
            "MEDIUM": 10,
            "LOW": 21
        }
        return urgency_days.get(complaint["urgency"], 10)

class EscalateAgent(BaseAgent):
    def __init__(self):
        super().__init__("Escalate_Agent", "Handles complaint escalation", "⚡")
    
    async def check_escalation(self, complaint_id: str) -> Dict:
        await self.update_status("processing", "Step 1: Checking for critical keywords and urgency...", complaint_id)
        await asyncio.sleep(0.4)
        await self.update_status("processing", "Step 2: Determining escalation path...", complaint_id)
        await asyncio.sleep(0.4)
        
        complaint = shared_memory.get_complaint(complaint_id)
        if not complaint:
            raise ValueError(f"Complaint {complaint_id} not found")
        
        # Advanced escalation logic
        needs_escalation = self._should_escalate(complaint)
        escalation_reason = self._get_escalation_reason(complaint)
        escalation_level = self._get_escalation_level(complaint)
        
        complaint["escalation"] = {
            "immediate": needs_escalation,
            "reason": escalation_reason,
            "level": escalation_level,
            "escalated_at": datetime.now(timezone.utc).isoformat() if needs_escalation else None,
            "escalation_path": self._get_escalation_path(complaint)
        }
        complaint["processing_history"].append({
            "agent": "Escalate_Agent",
            "action": "escalation_check",
            "escalated": needs_escalation,
            "level": escalation_level,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        shared_memory.save_complaint(complaint_id, complaint)
        
        status_msg = f"{escalation_level} escalation triggered!" if needs_escalation else "No escalation needed"
        await self.update_status("completed", status_msg, complaint_id)
        # Already updated above
        
        return {
            "escalated": needs_escalation,
            "reason": escalation_reason,
            "level": escalation_level,
            "path": complaint["escalation"]["escalation_path"]
        }
    
    def _should_escalate(self, complaint: Dict) -> bool:
        return (complaint["urgency"] == "CRITICAL" or 
                "emergency" in complaint["text"].lower() or
                "dangerous" in complaint["text"].lower())
    
    def _get_escalation_reason(self, complaint: Dict) -> str:
        if complaint["urgency"] == "CRITICAL":
            return "Critical urgency detected"
        elif "emergency" in complaint["text"].lower():
            return "Emergency situation identified"
        elif "dangerous" in complaint["text"].lower():
            return "Safety concern identified"
        else:
            return "Normal processing"
    
    def _get_escalation_level(self, complaint: Dict) -> str:
        if "emergency" in complaint["text"].lower():
            return "IMMEDIATE"
        elif complaint["urgency"] == "CRITICAL":
            return "HIGH"
        else:
            return "STANDARD"
    
    def _get_escalation_path(self, complaint: Dict) -> List[str]:
        if complaint["urgency"] == "CRITICAL":
            return ["Department Head", "District Magistrate", "State Authority"]
        else:
            return ["Department Officer", "Department Head"]

# Initialize agents
agents = {
    "chat": ChatAgent(),
    "router": RouterAgent(),
    "tracker": TrackerAgent(),
    "follow": FollowAgent(),
    "analytics": AnalyticsAgent(),
    "escalate": EscalateAgent()
}

# WebSocket endpoint for real-time updates
@app.websocket("/ws/dashboard")
async def websocket_dashboard_endpoint(websocket: WebSocket):
    await websocket.accept()
    shared_memory.dashboard_connections.append(websocket)
    try:
        while True:
            await websocket.receive_text()  # Keep connection alive
    except WebSocketDisconnect:
        logger.info("Dashboard client disconnected")
        shared_memory.dashboard_connections.remove(websocket)

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    shared_memory.websocket_connections[user_id] = websocket
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        shared_memory.websocket_connections.pop(user_id, None)

# API Endpoints
@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the government dashboard interface"""
    try:
        with open("dashboard.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        return HTMLResponse(content="""<!DOCTYPE html>
        <html>
        <head><title>Dashboard Not Found</title></head>
        <body style="text-align: center; padding: 50px;">
            <h1>Dashboard file not found</h1>
            <p>Please ensure dashboard.html is in the same directory as main.py</p>
        </body>
        </html>""")

@app.get("/", response_class=HTMLResponse)
async def serve_citizen_chat_interface():
    """Serve the citizen chat interface"""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Chat interface file (index.html) not found</h1>")

@app.get("/api")
async def root():
    return {
        "message": "🏛️ Citizen Voice AI Backend with Watson Integration",
        "status": "healthy",
        "agents": len(agents),
        "watson_configured": watson_config.is_configured(),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/health")
async def health_check():
    watson_status = "configured" if watson_config.is_configured() else "mock_mode"
    return {
        "status": "healthy", 
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agents_initialized": len(agents),
        "watson_status": watson_status,
        "cors_enabled": True,
        "websocket_connections": len(shared_memory.websocket_connections)
    }

async def process_complaint_flow(complaint_data: Dict, complaint_id: str):
    """The full pipeline for processing a complaint with all agents."""
    try:
        # Process through all agents rapidly
        await agents["chat"].process_complaint(complaint_data, complaint_id)
        await agents["router"].route_complaint(complaint_id)
        await agents["tracker"].setup_tracking(complaint_id)
        
        # Process remaining agents in parallel for speed
        await asyncio.gather(
            agents["follow"].schedule_reminders(complaint_id),
            agents["analytics"].analyze_complaint(complaint_id),
            agents["escalate"].check_escalation(complaint_id)
        )
        logger.info(f"Completed processing for complaint {complaint_id}")
    except Exception as e:
        logger.error(f"Error in complaint processing flow for {complaint_id}: {e}", exc_info=True)

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(message: ChatMessage, background_tasks: BackgroundTasks):
    """Enhanced chat endpoint that processes messages as complaints"""
    try:
        logger.info(f"Chat message received: {message.message[:100]}...")
        
        # Parse message as complaint (simplified - would use NLP in production)
        complaint_data = {
            "citizenName": "Chat User",  # Would be collected/authenticated
            "user_id": message.user_id,
            "phone": "+91-0000000000",   # Placeholder
            "location": "Delhi, India",   # Could be detected or asked
            "complaintText": message.message,
            "isPublic": False
        }
        
        complaint_id = str(uuid.uuid4())[:8].upper()
        complaint_data["id"] = complaint_id

        # Start the agent processing in the background
        background_tasks.add_task(process_complaint_flow, complaint_data, complaint_id)

        response_message = f"✅ Complaint received! Your Complaint ID is **{complaint_id}**. Our AI agents are now processing it. You will see their real-time activity below."
        
        return ChatResponse(
            message=response_message,
            complaint_id=complaint_id,
            processing_complete=False # It's happening in the background
        )
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {str(e)}", exc_info=True)
        return ChatResponse(
            message=f"I encountered an error processing your request: {str(e)}",
            processing_complete=True
        )

@app.post("/api/complaint", response_model=ComplaintResponse)
async def submit_complaint(complaint: ComplaintInput, background_tasks: BackgroundTasks):
    """Original complaint submission endpoint"""
    try:
        logger.info(f"Complaint received from {complaint.citizenName}")
        
        complaint_id = str(uuid.uuid4())[:8].upper()
        complaint_data = complaint.dict()
        complaint_data["id"] = complaint_id

        # Start the agent processing in the background
        background_tasks.add_task(process_complaint_flow, complaint_data, complaint_id)

        # Return an immediate acknowledgment
        return ComplaintResponse(
            complaint_id=complaint_id,
            status="SUBMITTED",
            category="PENDING",
            urgency="PENDING",
            department="PENDING",
            deadlines={},
            agent_processing={}
        )
        
    except Exception as e:
        logger.error(f"Error processing complaint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")

@app.post("/api/complaint/{complaint_id}/respond-legacy")
async def respond_to_complaint_legacy(complaint_id: str, response: ComplaintResponseInput):
    """Legacy endpoint (kept to avoid route collision). Use /api/complaint/{id}/respond instead."""
    try:
        complaint = shared_memory.get_complaint(complaint_id)
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")

        # Update complaint status
        complaint['status'] = response.status
        complaint['gov_response'] = response.dict()
        shared_memory.save_complaint(complaint_id, complaint)

        # Notify dashboards of the update
        await shared_memory.broadcast_to_dashboards({
            "type": "complaint_updated",
            "complaint": complaint
        })

        # In legacy endpoint, do not spawn background tasks (use modern endpoint instead)

        # Send real-time update to the citizen
        user_id = complaint.get("user_id")
        if user_id:
            message = {
                "type": "government_response",
                "complaint_id": complaint_id,
                "status": response.status,
                "message": response.message,
                "department": response.department,
                "officer_name": response.officer_name,
                "estimated_completion": response.estimated_completion
            }
            await shared_memory.broadcast_message(message, user_id)

        return {"status": "success", "message": "Response sent to citizen."}

    except Exception as e:
        logger.error(f"Error responding to complaint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/api/watson/skills")
async def get_watson_skills():
    """Get Watson skills (if configured)"""
    skills = await watson.get_skills()
    return skills

@app.get("/api/complaint/{complaint_id}")
async def get_complaint(complaint_id: str):
    """Get complaint details"""
    complaint = shared_memory.get_complaint(complaint_id)
    if not complaint:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint

@app.get("/api/agents/status")
async def get_agent_statuses():
    """Get status of all agents"""
    return agent_statuses

@app.get("/api/complaints")
async def list_complaints():
    """List all complaints"""
    return list(shared_memory.complaints.values())

@app.post("/api/complaint/{complaint_id}/respond")
async def respond_to_complaint(complaint_id: str, response: ComplaintResponseInput):
    """Update complaint with government response"""
    try:
        logger.info(f"Response received for complaint {complaint_id}")

        # Get complaint
        complaint = shared_memory.get_complaint(complaint_id)
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")

        # Update complaint with response
        complaint["status"] = response.status
        complaint["response"] = {
            "message": response.message,
            "department": response.department,
            "officer_name": response.officer_name,
            "estimated_completion": response.estimated_completion,
            "responded_at": datetime.now(timezone.utc).isoformat(),
            "response_timestamp": datetime.now(timezone.utc).isoformat()
        }
        complaint["processing_history"].append({
            "agent": "Government_Officer",
            "action": "response_provided",
            "status": response.status,
            "department": response.department,
            "officer": response.officer_name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        # Save updated complaint
        shared_memory.save_complaint(complaint_id, complaint)

        # Notify dashboards of the update
        await shared_memory.broadcast_to_dashboards({
            "type": "complaint_updated",
            "complaint": complaint
        })

        # Let TrackerAgent handle follow-up logic immediately
        await agents["tracker"].process_government_response(complaint_id, response.dict())

        return {
            "complaint_id": complaint_id,
            "status": "updated",
            "message": "Complaint response recorded successfully",
            "response_details": complaint["response"]
        }

    except Exception as e:
        logger.error(f"Error updating complaint response: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error updating complaint: {str(e)}")

@app.get("/api/analytics")
async def get_analytics():
    """Get system analytics"""
    total_complaints = len(shared_memory.complaints)
    by_category = {}
    by_urgency = {}
    by_status = {}

    for complaint in shared_memory.complaints.values():
        category = complaint.get("category", "Unknown")
        urgency = complaint.get("urgency", "Unknown")
        status = complaint.get("status", "Unknown")

        by_category[category] = by_category.get(category, 0) + 1
        by_urgency[urgency] = by_urgency.get(urgency, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1

    return {
        "total_complaints": total_complaints,
        "by_category": by_category,
        "by_urgency": by_urgency,
        "by_status": by_status,
        "agent_statuses": agent_statuses,
        "watson_integration": watson_config.is_configured(),
        "active_websockets": len(shared_memory.websocket_connections)
    }

# Serve the chat interface
@app.get("/chat", response_class=HTMLResponse)
async def serve_chat_interface():
    """Serve the ChatGPT-style interface"""
    # Read the HTML file content
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        # Fallback HTML if file not found
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Citizen Voice AI - Chat Interface</title>
        </head>
        <body style="text-align: center; padding: 50px; font-family: Arial, sans-serif;">
            <h1>🏛️ Citizen Voice AI - Chat Interface</h1>
            <p>Chat interface file (index.html) not found.</p>
            <p>Please make sure the HTML file is in the same directory as main.py</p>
            <div style="margin-top: 30px;">
                <h3>Available API Endpoints:</h3>
                <ul style="list-style: none; display: inline-block; text-align: left;">
                    <li>POST /api/chat - Chat interface endpoint</li>
                    <li>POST /api/complaint - Submit complaint</li>
                    <li>GET /api/complaints - List complaints</li>
                    <li>GET /api/agents/status - Agent statuses</li>
                    <li>GET /api/analytics - System analytics</li>
                    <li>GET /api/watson/skills - Watson skills</li>
                    <li>WS /ws - WebSocket for real-time updates</li>
                </ul>
            </div>
        </body>
        </html>
        """)

@app.get("/", response_class=HTMLResponse) 
async def serve_main_interface():
    """Redirect to chat interface"""
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Citizen Voice AI</title>
        <meta http-equiv="refresh" content="0; url=/chat">
    </head>
    <body>
        <div style="text-align: center; padding: 50px;">
            <h1>🏛️ Citizen Voice AI</h1>
            <p>Redirecting to chat interface...</p>
            <p><a href="/chat">Click here if not redirected automatically</a></p>
        </div>
    </body>
    </html>
    """)

# Background task for periodic agent health checks
async def periodic_health_check():
    """Periodic health check for agents"""
    while True:
        try:
            await asyncio.sleep(30)  # Check every 30 seconds
            
            current_time = datetime.now(timezone.utc)
            for agent_name, agent in agents.items():
                # Check if agent has been inactive for too long
                time_since_activity = current_time - agent.last_activity
                if time_since_activity.total_seconds() > 300:  # 5 minutes
                    await agent.update_status("idle", "Agent idle - ready for new tasks")
                
            logger.info("Periodic health check completed")
            
        except Exception as e:
            logger.error(f"Error in periodic health check: {str(e)}")

# Background task for processing reminders
async def process_reminders():
    """Background task to process scheduled reminders"""
    while True:
        try:
            await asyncio.sleep(60)  # Check every minute
            
            current_time = datetime.now(timezone.utc)
            
            for complaint in shared_memory.complaints.values():
                reminders = complaint.get("reminders", {})
                if not reminders:
                    continue
                    
                # Check if any reminders are due
                for reminder_type, reminder_time_str in reminders.items():
                    if reminder_type.endswith("_reminder"):
                        try:
                            reminder_time = datetime.fromisoformat(reminder_time_str.replace("Z", "+00:00"))
                            if current_time >= reminder_time and not complaint.get(f"{reminder_type}_sent", False):
                                # Send reminder (in production, this would send actual notifications)
                                logger.info(f"Reminder due for complaint {complaint['id']}: {reminder_type}")
                                
                                # Mark reminder as sent
                                complaint[f"{reminder_type}_sent"] = True
                                shared_memory.save_complaint(complaint["id"], complaint)
                                
                                # Broadcast reminder notification
                                await shared_memory.broadcast_agent_update(
                                    "Follow_Agent", 
                                    "reminder_sent", 
                                    f"Sent {reminder_type} for complaint {complaint['id']}"
                                )
                                
                        except (ValueError, KeyError) as e:
                            logger.error(f"Error processing reminder: {str(e)}")
                            
        except Exception as e:
            logger.error(f"Error in reminder processing: {str(e)}")

# Startup event to initialize background tasks
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code
    asyncio.create_task(periodic_health_check())
    asyncio.create_task(process_reminders())
    
    logger.info("🏛️ Citizen Voice AI Backend Started")
    logger.info(f"📊 Agents initialized: {len(agents)}")
    logger.info(f"🤖 Watson integration: {'Configured' if watson_config.is_configured() else 'Mock mode'}")
    logger.info("🚀 Background tasks started")
    
    yield
    # Shutdown code
    logger.info("🛑 Shutting down Citizen Voice AI Backend")
    
    # Close all WebSocket connections
    for websocket in shared_memory.websocket_connections.values():
        try:
            await websocket.close()
        except:
            pass
    
    logger.info("✅ Shutdown complete")

app.router.lifespan_context = lifespan

# Remove deprecated on_event handlers
# @app.on_event("startup")
# async def startup_event():
#     ...

# @app.on_event("shutdown")
# async def shutdown_event():
#     ...
# """Initialize background tasks"""
# asyncio.create_task(periodic_health_check())
# asyncio.create_task(process_reminders())
# 
# logger.info("🏛️ Citizen Voice AI Backend Started")
# logger.info(f"📊 Agents initialized: {len(agents)}")
# logger.info(f"🤖 Watson integration: {'Configured' if watson_config.is_configured() else 'Mock mode'}")
# logger.info("🚀 Background tasks started")

# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 Shutting down Citizen Voice AI Backend")
    
    # Close all WebSocket connections
    for websocket in shared_memory.websocket_connections.values():
        try:
            await websocket.close()
        except:
            pass
    
    logger.info("✅ Shutdown complete")

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("🏛️  CITIZEN VOICE AI - GOVERNMENT ACCOUNTABILITY SYSTEM")
    print("=" * 60)
    print("🚀 Starting Enhanced Python Backend Server...")
    print("📊 Multi-Agent System with 6 AI Agents")
    print("🤖 IBM Watson Integration Ready")
    print("💬 ChatGPT-style Interface Available")
    print("🔄 Real-time WebSocket Updates")
    print("=" * 60)
    print("🔗 Chat Interface: http://localhost:8000/chat")
    print("🔗 API Docs: http://localhost:8000/docs")
    print("🔗 Health Check: http://localhost:8000/api/health")
    print("🔗 WebSocket: ws://localhost:8000/ws")
    print("=" * 60)
    
    # Environment variables info
    if watson_config.is_configured():
        print("✅ Watson Integration: CONFIGURED")
    else:
        print("⚠️  Watson Integration: MOCK MODE")
        print("   Set WATSON_JWT_TOKEN, WATSON_INSTANCE_ID, WATSON_REGION_CODE")
    
    print("=" * 60)
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )