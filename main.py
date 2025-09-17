from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any, Set
import json
import uuid
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
import os
from enum import Enum
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Citizen Voice AI", description="Government Accountability System with AI Agents")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# ENUMS AND STATUS SYSTEM
# =============================================================================

class ComplaintStatus(str, Enum):
    RED = "RED"           # Complaint received, under AI processing
    ORANGE = "ORANGE"     # Routed by AI to department with deadline
    BLUE = "BLUE"         # Acknowledged by department
    GREEN = "GREEN"       # In progress, officials working
    BLACK = "BLACK"       # Resolved and verified

class ComplaintType(str, Enum):
    PUBLIC = "PUBLIC"     # Visible to community, can be upvoted
    PRIVATE = "PRIVATE"   # Only citizen and department can see

class UrgencyLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class AgentStatus(str, Enum):
    IDLE = "IDLE"
    PROCESSING = "PROCESSING"
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"

# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class ComplaintInput(BaseModel):
    citizenName: str = Field(..., min_length=2, max_length=100)
    phone: str = Field(..., pattern=r'^\+?[1-9]\d{1,14}$')
    location: str = Field(..., min_length=3, max_length=200)
    complaintText: str = Field(..., min_length=10, max_length=2000)
    complaintType: ComplaintType = ComplaintType.PRIVATE
    area: Optional[str] = None

class ChatMessage(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    user_id: Optional[str] = None

class ComplaintChatMessage(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)
    user_type: str = Field(..., pattern="^(citizen|government)$")
    complaint_id: str

class ComplaintResponse(BaseModel):
    complaint_id: str
    status: ComplaintStatus
    category: str
    urgency: UrgencyLevel
    department: str
    deadlines: Dict[str, str]
    is_public: bool = False
    upvotes: int = 0
    area: Optional[str] = None
    processing_steps: List[Dict[str, Any]] = []

class ChatResponse(BaseModel):
    message: str
    complaint_id: Optional[str] = None
    current_status: Optional[ComplaintStatus] = None
    processing_steps: List[Dict[str, Any]] = []

class GovernmentResponse(BaseModel):
    status: ComplaintStatus
    message: str = Field(..., min_length=5, max_length=1000)
    estimated_completion: Optional[str] = None
    department: str
    officer_name: str

class UpvoteRequest(BaseModel):
    user_id: str

class PublicComplaint(BaseModel):
    complaint_id: str
    category: str
    location: str
    area: str
    urgency: UrgencyLevel
    status: ComplaintStatus
    upvotes: int
    created_at: datetime
    anonymized_text: str

# =============================================================================
# WATSON INTEGRATION
# =============================================================================

@dataclass
class WatsonConfig:
    region_code: str = os.getenv("WATSON_REGION_CODE", "us-south")
    jwt_token: str = os.getenv("WATSON_JWT_TOKEN", "")
    instance_id: str = os.getenv("WATSON_INSTANCE_ID", "")
    base_url: str = "dl.watsonx.ai"

    def is_configured(self) -> bool:
        return bool(self.jwt_token and self.instance_id and self.region_code)

class WatsonIntegration:
    def __init__(self, config: WatsonConfig):
        self.config = config

    async def analyze_text(self, text: str) -> Dict:
        """Analyze text using Watson (or fallback to local processing)"""
        if not self.config.is_configured():
            return self._local_text_analysis(text)
        
        # TODO: Implement Watson API calls here
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

watson_config = WatsonConfig()
watson = WatsonIntegration(watson_config)

# =============================================================================
# ENHANCED SHARED MEMORY SYSTEM
# =============================================================================

class SharedMemory:
    def __init__(self):
        self.complaints: Dict[str, Dict] = {}
        self.agent_states: Dict[str, Dict] = {}
        self.analytics_data: Dict[str, Any] = {}
        self.websocket_connections: Dict[str, WebSocket] = {}
        self.dashboard_connections: List[WebSocket] = []
        self.public_complaints: Dict[str, Dict] = {}  # Area-based public complaints
        self.upvotes: Dict[str, Set[str]] = {}  # complaint_id -> set of user_ids
        self.agent_message_queue: List[Dict] = []  # Inter-agent communication
        self.processing_history: Dict[str, List[Dict]] = {}  # complaint_id -> history
    
    def save_complaint(self, complaint_id: str, complaint_data: Dict):
        """Save complaint and handle public/private logic"""
        self.complaints[complaint_id] = complaint_data
        
        # If public, add to area-based feed
        if complaint_data.get('complaint_type') == ComplaintType.PUBLIC:
            area = complaint_data.get('area', 'Unknown')
            if area not in self.public_complaints:
                self.public_complaints[area] = {}
            
            self.public_complaints[area][complaint_id] = {
                'category': complaint_data.get('category'),
                'location': complaint_data.get('location'),
                'urgency': complaint_data.get('urgency'),
                'status': complaint_data.get('status'),
                'upvotes': len(self.upvotes.get(complaint_id, set())),
                'created_at': complaint_data.get('timestamp'),
                'anonymized_text': self._anonymize_text(complaint_data.get('text', ''))
            }
        
        logger.info(f"💾 Saved complaint {complaint_id} - Type: {complaint_data.get('complaint_type', 'PRIVATE')}")
    
    def _anonymize_text(self, text: str) -> str:
        """Remove sensitive info for public viewing"""
        import re
        text = re.sub(r'\b[A-Z][a-z]+ [A-Z][a-z]+\b', 'RESIDENT', text)  # Names
        text = re.sub(r'\b\d{10,}\b', 'XXXX-XXXX', text)  # Phone numbers
        text = re.sub(r'\b\d{1,4}[,.]?\s*[A-Za-z]+\s+[A-Za-z]+\b', 'ADDRESS', text)  # Addresses
        return text[:150] + "..." if len(text) > 150 else text
    
    def get_complaint(self, complaint_id: str) -> Dict:
        return self.complaints.get(complaint_id, {})
    
    def update_complaint_status(self, complaint_id: str, status: ComplaintStatus, 
                              agent_name: str = "", message: str = ""):
        """Update complaint status and broadcast changes"""
        if complaint_id in self.complaints:
            self.complaints[complaint_id]['status'] = status.value
            self.complaints[complaint_id]['last_updated'] = datetime.now(timezone.utc).isoformat()
            
            # Add to processing history
            if complaint_id not in self.processing_history:
                self.processing_history[complaint_id] = []
            
            self.processing_history[complaint_id].append({
                'status': status.value,
                'agent': agent_name,
                'message': message,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
            logger.info(f"📊 Status Update: {complaint_id} → {status.value} by {agent_name}")
    
    def upvote_complaint(self, complaint_id: str, user_id: str) -> bool:
        """Add upvote to a public complaint"""
        if complaint_id not in self.complaints:
            return False
        
        complaint = self.complaints[complaint_id]
        if complaint.get('complaint_type') != ComplaintType.PUBLIC:
            return False
        
        if complaint_id not in self.upvotes:
            self.upvotes[complaint_id] = set()
        
        if user_id in self.upvotes[complaint_id]:
            return False  # Already upvoted
        
        self.upvotes[complaint_id].add(user_id)
        
        # Update public complaints data
        area = complaint.get('area', 'Unknown')
        if area in self.public_complaints and complaint_id in self.public_complaints[area]:
            self.public_complaints[area][complaint_id]['upvotes'] = len(self.upvotes[complaint_id])
        
        return True
    
    def get_public_complaints_by_area(self, area: str) -> List[Dict]:
        """Get public complaints for a specific area, sorted by upvotes"""
        area_complaints = self.public_complaints.get(area, {})
        complaints = []
        for complaint_id, data in area_complaints.items():
            complaints.append({
                'complaint_id': complaint_id,
                **data
            })
        return sorted(complaints, key=lambda x: x.get('upvotes', 0), reverse=True)
    
    def send_agent_message(self, sender: str, receiver: str, message_type: str, 
                          content: Dict, priority: str = "normal"):
        """Send message between agents"""
        message = {
            "id": str(uuid.uuid4()),
            "sender": sender,
            "receiver": receiver,
            "type": message_type,
            "content": content,
            "priority": priority,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "processed": False
        }
        self.agent_message_queue.append(message)
        logger.info(f"📨 Agent Message: {sender} → {receiver} [{message_type}]")
    
    def get_agent_messages(self, agent_name: str) -> List[Dict]:
        """Get unprocessed messages for an agent"""
        return [msg for msg in self.agent_message_queue 
                if msg['receiver'] == agent_name and not msg['processed']]
    
    def mark_message_processed(self, message_id: str):
        """Mark message as processed"""
        for msg in self.agent_message_queue:
            if msg['id'] == message_id:
                msg['processed'] = True
                break
    
    async def broadcast_to_users(self, message: Dict, user_id: Optional[str] = None):
        """Broadcast message to user WebSocket connections"""
        if user_id and user_id in self.websocket_connections:
            try:
                await self.websocket_connections[user_id].send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending to user {user_id}: {e}")
                self.websocket_connections.pop(user_id, None)
        elif not user_id:
            # Broadcast to all users
            for uid, connection in list(self.websocket_connections.items()):
                try:
                    await connection.send_text(json.dumps(message))
                except Exception:
                    self.websocket_connections.pop(uid, None)
    
    async def broadcast_to_dashboards(self, message: Dict):
        """Broadcast message to government dashboard connections"""
        for connection in self.dashboard_connections[:]:
            try:
                await connection.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending to dashboard: {e}")
                self.dashboard_connections.remove(connection)
    
    async def broadcast_status_update(self, complaint_id: str, status: ComplaintStatus, 
                                    agent_name: str = "", message: str = ""):
        """Broadcast status update with color coding to all clients"""
        update = {
            "type": "status_update",
            "complaint_id": complaint_id,
            "status": status.value,
            "status_color": self._get_status_color(status),
            "status_message": self._get_status_message(status),
            "agent": agent_name,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        await self.broadcast_to_users(update)
        await self.broadcast_to_dashboards(update)
        logger.info(f"📡 Status Broadcast: {complaint_id} → {status.value}")
    
    def _get_status_color(self, status: ComplaintStatus) -> str:
        color_map = {
            ComplaintStatus.RED: "#dc2626",
            ComplaintStatus.ORANGE: "#ea580c", 
            ComplaintStatus.BLUE: "#2563eb",
            ComplaintStatus.GREEN: "#16a34a",
            ComplaintStatus.BLACK: "#1f2937"
        }
        return color_map.get(status, "#6b7280")
    
    def _get_status_message(self, status: ComplaintStatus) -> str:
        messages = {
            ComplaintStatus.RED: "Complaint received, under AI processing",
            ComplaintStatus.ORANGE: "Routed to department with deadline",
            ComplaintStatus.BLUE: "Acknowledged by department",
            ComplaintStatus.GREEN: "In progress, officials are working",
            ComplaintStatus.BLACK: "Resolved and verified"
        }
        return messages.get(status, "Status unknown")
    
    def add_chat_message(self, complaint_id: str, message: str, user_type: str, timestamp: str) -> bool:
        """Add a chat message to a complaint"""
        if complaint_id in self.complaints:
            complaint = self.complaints[complaint_id]
            if "chat_messages" not in complaint:
                complaint["chat_messages"] = []
            
            chat_message = {
                "message": message,
                "user_type": user_type,
                "timestamp": timestamp
            }
            
            complaint["chat_messages"].append(chat_message)
            return True
        
        return False

# Initialize shared memory
shared_memory = SharedMemory()

# =============================================================================
# AI AGENT SYSTEM WITH REAL COLLABORATION
# =============================================================================

class BaseAgent:
    def __init__(self, name: str, description: str, icon: str = "🤖"):
        self.name = name
        self.description = description
        self.icon = icon
        self.status = AgentStatus.IDLE
        self.last_activity = datetime.now(timezone.utc)
    
    async def update_status(self, status: AgentStatus, message: str = "", complaint_id: str = ""):
        """Update agent status and broadcast to clients"""
        self.status = status
        self.last_activity = datetime.now(timezone.utc)
        
        shared_memory.agent_states[self.name] = {
            "status": status.value,
            "message": message,
            "timestamp": self.last_activity.isoformat(),
            "complaint_id": complaint_id
        }
        
        # Broadcast agent update
        update = {
            "type": "agent_update",
            "agent": self.name,
            "status": status.value,
            "message": message,
            "complaint_id": complaint_id,
            "timestamp": self.last_activity.isoformat()
        }
        
        await shared_memory.broadcast_to_users(update)
        logger.info(f"🤖 {self.name}: {status.value} - {message}")
    
    async def process_messages(self):
        """Process incoming messages from other agents"""
        messages = shared_memory.get_agent_messages(self.name)
        for message in messages:
            await self.handle_message(message)
            shared_memory.mark_message_processed(message['id'])
    
    async def handle_message(self, message: Dict):
        """Override in subclasses to handle specific message types"""
        pass

class ChatAgent(BaseAgent):
    def __init__(self):
        super().__init__("Chat_Agent", "Processes citizen complaints and initiates workflow", "💬")
    
    async def process_complaint(self, complaint_data: Dict, complaint_id: str) -> Dict:
        """Process initial complaint - RED status"""
        await self.update_status(AgentStatus.PROCESSING, "Analyzing citizen complaint...", complaint_id)
        
        # Update complaint status to RED
        shared_memory.update_complaint_status(complaint_id, ComplaintStatus.RED, self.name, 
                                            "Starting AI analysis of complaint")
        await shared_memory.broadcast_status_update(complaint_id, ComplaintStatus.RED, self.name,
                                                  "AI is analyzing your complaint...")
        
        # Simulate processing steps
        await asyncio.sleep(1)
        await self.update_status(AgentStatus.PROCESSING, "Extracting keywords and entities...", complaint_id)
        
        await asyncio.sleep(1) 
        await self.update_status(AgentStatus.PROCESSING, "Determining category and urgency...", complaint_id)
        
        # Analyze with Watson
        analysis = await watson.analyze_text(complaint_data["complaintText"])
        
        # Create processed complaint
        processed_complaint = {
            "id": complaint_id,
            "user_id": complaint_data.get("user_id"),
            "text": complaint_data["complaintText"],
            "citizen_name": complaint_data["citizenName"],
            "phone": complaint_data["phone"],
            "location": complaint_data["location"],
            "area": complaint_data.get("area", "Unknown"),
            "complaint_type": complaint_data.get("complaintType", ComplaintType.PRIVATE),
            "language": analysis.get("language", "English"),
            "category": analysis.get("category", "General"),
            "urgency": analysis.get("urgency", "MEDIUM"),
            "confidence": analysis.get("confidence", 0.0),
            "keywords": analysis.get("keywords_found", []),
            "status": ComplaintStatus.RED.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "watson_analysis": analysis
        }
        
        shared_memory.save_complaint(complaint_id, processed_complaint)
        
        # Send message to Router Agent
        shared_memory.send_agent_message(
            self.name, "Router_Agent", "new_complaint",
            {"complaint_id": complaint_id}, priority="high"
        )
        
        await self.update_status(AgentStatus.COMPLETED, 
                               f"Complaint classified as {analysis.get('category')} - {analysis.get('urgency')} urgency", 
                               complaint_id)
        
        return {
            "complaint_id": complaint_id,
            "category": analysis.get("category", "General"),
            "urgency": analysis.get("urgency", "MEDIUM"),
            "language": analysis.get("language", "English"),
            "confidence": analysis.get("confidence", 0.0)
        }

class RouterAgent(BaseAgent):
    def __init__(self):
        super().__init__("Router_Agent", "Routes complaints to correct departments", "🎯")
        self.department_mapping = {
            "Electricity": "Delhi Electricity Regulatory Commission (DERC)",
            "Water": "Delhi Jal Board (DJB)", 
            "Road": "Public Works Department (PWD)",
            "Sanitation": "Municipal Corporation of Delhi (MCD)",
            "Health": "Department of Health & Family Welfare",
            "General": "District Collector Office"
        }
    
    async def handle_message(self, message: Dict):
        if message['type'] == 'new_complaint':
            await self.route_complaint(message['content']['complaint_id'])
    
    async def route_complaint(self, complaint_id: str) -> Dict:
        """Route complaint to department - ORANGE status"""
        complaint = shared_memory.get_complaint(complaint_id)
        if not complaint:
            return {"error": "Complaint not found"}
        
        await self.update_status(AgentStatus.PROCESSING, "Finding correct department...", complaint_id)
        
        # Update to ORANGE status
        shared_memory.update_complaint_status(complaint_id, ComplaintStatus.ORANGE, self.name,
                                            "Routing to appropriate department")
        await shared_memory.broadcast_status_update(complaint_id, ComplaintStatus.ORANGE, self.name,
                                                  "Finding the right department for your complaint...")
        
        await asyncio.sleep(1)
        
        category = complaint.get('category', 'General')
        department = self.department_mapping.get(category, self.department_mapping['General'])
        urgency = complaint.get('urgency', 'MEDIUM')
        
        # Calculate deadlines based on urgency
        deadlines = self.calculate_deadlines(urgency)
        
        # Update complaint with routing info
        complaint['department'] = department
        complaint['deadlines'] = deadlines
        complaint['routed_at'] = datetime.now(timezone.utc).isoformat()
        shared_memory.save_complaint(complaint_id, complaint)
        
        # Send to Tracker Agent
        shared_memory.send_agent_message(
            self.name, "Tracker_Agent", "setup_tracking",
            {"complaint_id": complaint_id, "department": department, "deadlines": deadlines}
        )
        
        await self.update_status(AgentStatus.COMPLETED, 
                               f"Routed to {department} with {deadlines['acknowledgment']} deadline", 
                               complaint_id)
        
        return {
            "department": department,
            "deadlines": deadlines,
            "urgency": urgency
        }
    
    def calculate_deadlines(self, urgency: str) -> Dict[str, str]:
        """Calculate response and resolution deadlines"""
        now = datetime.now(timezone.utc)
        
        if urgency == "CRITICAL":
            ack_hours = 2
            resolution_days = 1
        elif urgency == "HIGH":
            ack_hours = 6 
            resolution_days = 3
        elif urgency == "MEDIUM":
            ack_hours = 24
            resolution_days = 7
        else:  # LOW
            ack_hours = 48
            resolution_days = 15
        
        acknowledgment = (now + timedelta(hours=ack_hours)).isoformat()
        resolution = (now + timedelta(days=resolution_days)).isoformat()
        
        return {
            "acknowledgment": acknowledgment,
            "resolution": resolution
        }

class TrackerAgent(BaseAgent):
    def __init__(self):
        super().__init__("Tracker_Agent", "Monitors government responses and deadlines", "⏰")
    
    async def handle_message(self, message: Dict):
        if message['type'] == 'setup_tracking':
            await self.setup_tracking(message['content']['complaint_id'])
        elif message['type'] == 'government_response':
            await self.process_government_response(message['content']['complaint_id'], 
                                                 message['content']['response_data'])
    
    async def setup_tracking(self, complaint_id: str) -> Dict:
        """Setup tracking for complaint deadlines"""
        complaint = shared_memory.get_complaint(complaint_id)
        if not complaint:
            return {"error": "Complaint not found"}
        
        await self.update_status(AgentStatus.PROCESSING, "Setting up deadline tracking...", complaint_id)
        
        # Add tracking data
        complaint['tracking'] = {
            'setup_at': datetime.now(timezone.utc).isoformat(),
            'acknowledgment_deadline': complaint.get('deadlines', {}).get('acknowledgment'),
            'resolution_deadline': complaint.get('deadlines', {}).get('resolution'),
            'status_checks': []
        }
        shared_memory.save_complaint(complaint_id, complaint)
        
        # Send to Follow Agent to schedule reminders
        shared_memory.send_agent_message(
            self.name, "Follow_Agent", "schedule_reminders",
            {"complaint_id": complaint_id, "deadlines": complaint.get('deadlines', {})}
        )
        
        await self.update_status(AgentStatus.COMPLETED, "Tracking setup complete", complaint_id)
        
        return {"tracking_setup": True}
    
    async def process_government_response(self, complaint_id: str, response_data: Dict):
        """Process government response - move to BLUE/GREEN/BLACK"""
        complaint = shared_memory.get_complaint(complaint_id)
        if not complaint:
            return
        
        await self.update_status(AgentStatus.PROCESSING, f"Processing government response for {complaint_id}", complaint_id)
        
        new_status = ComplaintStatus(response_data.get('status', ComplaintStatus.BLUE))
        government_message = response_data.get('message', 'Government has responded to your complaint')
        department = response_data.get('department', complaint.get('department', 'Department'))
        officer_name = response_data.get('officer_name', 'Government Official')
        
        # Update complaint with government response
        complaint['government_response'] = {
            'message': government_message,
            'status': new_status.value,
            'department': department,
            'officer_name': officer_name,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'estimated_completion': response_data.get('estimated_completion')
        }
        shared_memory.save_complaint(complaint_id, complaint)
        
        # Update complaint status
        shared_memory.update_complaint_status(complaint_id, new_status, self.name,
                                            f"Government response: {government_message}")
        
        # Broadcast status update to all clients
        await shared_memory.broadcast_status_update(complaint_id, new_status, self.name,
                                                  f"{department} says: {government_message}")
        
        # Send direct message to the citizen who filed the complaint
        citizen_message = {
            "type": "government_response",
            "complaint_id": complaint_id,
            "status": new_status.value,
            "status_color": shared_memory._get_status_color(new_status),
            "message": government_message,
            "department": department,
            "officer_name": officer_name,
            "estimated_completion": response_data.get('estimated_completion'),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Try to send to specific user if available
        user_id = complaint.get('user_id')
        if user_id:
            await shared_memory.broadcast_to_users(citizen_message, user_id)
        else:
            # Broadcast to all users if user_id not available
            await shared_memory.broadcast_to_users(citizen_message)
        
        # Update tracking
        if 'tracking' in complaint:
            complaint['tracking']['status_checks'].append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'status': new_status.value,
                'response': response_data
            })
            shared_memory.save_complaint(complaint_id, complaint)
        
        await self.update_status(AgentStatus.COMPLETED, 
                               f"Government response processed: {new_status.value}", complaint_id)
        
        logger.info(f"🏛️ Government Response Processed: {complaint_id} → {new_status.value}")
        
        # If resolved, send to Analytics for completion analysis
        if new_status == ComplaintStatus.BLACK:
            shared_memory.send_agent_message(
                self.name, "Analytics_Agent", "complaint_resolved",
                {"complaint_id": complaint_id, "resolution_data": response_data}
            )

class FollowAgent(BaseAgent):
    def __init__(self):
        super().__init__("Follow_Agent", "Sends reminders and ensures accountability", "🔔")
    
    async def handle_message(self, message: Dict):
        if message['type'] == 'schedule_reminders':
            await self.schedule_reminders(message['content']['complaint_id'])
    
    async def schedule_reminders(self, complaint_id: str) -> Dict:
        """Schedule automatic reminders to government departments"""
        complaint = shared_memory.get_complaint(complaint_id)
        if not complaint:
            return {"error": "Complaint not found"}
        
        await self.update_status(AgentStatus.PROCESSING, "Scheduling reminders...", complaint_id)
        
        # Add reminder schedule
        reminder_schedule = {
            'created_at': datetime.now(timezone.utc).isoformat(),
            'reminders': []
        }
        
        deadlines = complaint.get('deadlines', {})
        if 'acknowledgment' in deadlines:
            reminder_time = datetime.fromisoformat(deadlines['acknowledgment']) - timedelta(hours=2)
            reminder_schedule['reminders'].append({
                'type': 'acknowledgment_reminder',
                'scheduled_for': reminder_time.isoformat(),
                'sent': False
            })
        
        if 'resolution' in deadlines:
            reminder_time = datetime.fromisoformat(deadlines['resolution']) - timedelta(days=1)
            reminder_schedule['reminders'].append({
                'type': 'resolution_reminder', 
                'scheduled_for': reminder_time.isoformat(),
                'sent': False
            })
        
        complaint['reminders'] = reminder_schedule
        shared_memory.save_complaint(complaint_id, complaint)
        
        # Send to Analytics Agent
        shared_memory.send_agent_message(
            self.name, "Analytics_Agent", "analyze_complaint",
            {"complaint_id": complaint_id}
        )
        
        await self.update_status(AgentStatus.COMPLETED, "Reminders scheduled", complaint_id)
        
        return {"reminders_scheduled": len(reminder_schedule['reminders'])}

class AnalyticsAgent(BaseAgent):
    def __init__(self):
        super().__init__("Analytics_Agent", "Analyzes patterns and generates insights", "📊")
    
    async def handle_message(self, message: Dict):
        if message['type'] == 'analyze_complaint':
            await self.analyze_complaint(message['content']['complaint_id'])
    
    async def analyze_complaint(self, complaint_id: str) -> Dict:
        """Analyze complaint patterns and generate insights"""
        complaint = shared_memory.get_complaint(complaint_id)
        if not complaint:
            return {"error": "Complaint not found"}
        
        await self.update_status(AgentStatus.PROCESSING, "Analyzing complaint patterns...", complaint_id)
        
        # Generate analytics
        analytics = {
            'analyzed_at': datetime.now(timezone.utc).isoformat(),
            'category_frequency': self._get_category_stats(complaint.get('category', 'General')),
            'area_analysis': self._get_area_stats(complaint.get('area', 'Unknown')),
            'urgency_distribution': self._get_urgency_stats(),
            'resolution_predictions': self._predict_resolution_time(complaint)
        }
        
        # Update complaint with analytics
        complaint['analytics'] = analytics
        shared_memory.save_complaint(complaint_id, complaint)
        
        # Update global analytics
        shared_memory.analytics_data[complaint_id] = analytics
        
        # Send to Escalate Agent for escalation check
        shared_memory.send_agent_message(
            self.name, "Escalate_Agent", "check_escalation",
            {"complaint_id": complaint_id}
        )
        
        await self.update_status(AgentStatus.COMPLETED, "Analysis complete", complaint_id)
        
        return analytics
    
    def _get_category_stats(self, category: str) -> Dict:
        """Get statistics for this complaint category"""
        category_complaints = [c for c in shared_memory.complaints.values() 
                             if c.get('category') == category]
        
        return {
            'total_complaints': len(category_complaints),
            'avg_resolution_time': 5.2,  # Mock data
            'success_rate': 0.85
        }
    
    def _get_area_stats(self, area: str) -> Dict:
        """Get statistics for this area"""
        area_complaints = [c for c in shared_memory.complaints.values() 
                          if c.get('area') == area]
        
        return {
            'total_complaints': len(area_complaints),
            'most_common_category': 'Electricity',  # Mock data
            'response_time': 'Average'
        }
    
    def _get_urgency_stats(self) -> Dict:
        """Get overall urgency distribution"""
        return {
            'CRITICAL': 5,
            'HIGH': 15, 
            'MEDIUM': 60,
            'LOW': 20
        }
    
    def _predict_resolution_time(self, complaint: Dict) -> Dict:
        """Predict resolution time based on patterns"""
        urgency = complaint.get('urgency', 'MEDIUM')
        category = complaint.get('category', 'General')
        
        base_days = {'CRITICAL': 1, 'HIGH': 3, 'MEDIUM': 7, 'LOW': 15}
        predicted_days = base_days.get(urgency, 7)
        
        return {
            'estimated_days': predicted_days,
            'confidence': 0.78,
            'factors': ['urgency', 'category', 'historical_data']
        }

class AutoGovernmentAgent(BaseAgent):
    """Simulates automatic government responses for demo purposes"""
    def __init__(self):
        super().__init__("Auto_Government", "Simulates government department responses", "🏛️")
        self.response_templates = {
            "Water": {
                "acknowledgment": "Water complaint received. Technical team will inspect the area within 24 hours.",
                "progress": "Our maintenance crew is working on the water supply issue. Expected resolution in 2-3 days.",
                "resolution": "Water supply issue has been resolved. New pipeline installed and tested."
            },
            "Electricity": {
                "acknowledgment": "Power outage complaint noted. Dispatch team sent to check transformers.",
                "progress": "Electrical fault identified. Repair work in progress. Power should be restored soon.",
                "resolution": "Electrical repairs completed. Power supply fully restored and stabilized."
            },
            "Road": {
                "acknowledgment": "Road maintenance request received. Survey team will assess the damage.",
                "progress": "Pothole repair work started. Road closure may be needed for safety during repairs.",
                "resolution": "Road repairs completed. Surface leveled and traffic flow normalized."
            },
            "Sanitation": {
                "acknowledgment": "Sanitation complaint registered. Cleaning team will be dispatched immediately.",
                "progress": "Garbage collection in progress. Additional cleaning staff deployed to the area.",
                "resolution": "Area cleaned thoroughly. Regular cleaning schedule updated for this location."
            },
            "General": {
                "acknowledgment": "Your complaint has been forwarded to the appropriate department for action.",
                "progress": "Department is reviewing your complaint and working on a resolution.",
                "resolution": "Your complaint has been resolved. Thank you for bringing this to our attention."
            }
        }
    
    async def handle_message(self, message: Dict):
        if message['type'] == 'simulate_response':
            content = message['content']
            complaint_id = content['complaint_id']
            department_category = content['department_category']
            
            # Start simulation in background
            asyncio.create_task(self.simulate_government_workflow(complaint_id, department_category))
    
    async def simulate_government_workflow(self, complaint_id: str, department_category: str):
        """Simulate realistic government response workflow"""
        try:
            complaint = shared_memory.get_complaint(complaint_id)
            if not complaint:
                return
            
            templates = self.response_templates.get(department_category, self.response_templates["General"])
            urgency = complaint.get('urgency', 'MEDIUM')
            
            # Calculate delays based on urgency
            if urgency == 'CRITICAL':
                ack_delay = 2 * 60  # 2 minutes for demo
                progress_delay = 5 * 60  # 5 minutes
                resolution_delay = 10 * 60  # 10 minutes
            elif urgency == 'HIGH':
                ack_delay = 3 * 60  # 3 minutes
                progress_delay = 8 * 60  # 8 minutes 
                resolution_delay = 15 * 60  # 15 minutes
            elif urgency == 'MEDIUM':
                ack_delay = 5 * 60  # 5 minutes
                progress_delay = 10 * 60  # 10 minutes
                resolution_delay = 20 * 60  # 20 minutes
            else:  # LOW
                ack_delay = 8 * 60  # 8 minutes
                progress_delay = 15 * 60  # 15 minutes
                resolution_delay = 30 * 60  # 30 minutes
            
            await self.update_status(AgentStatus.PROCESSING, f"Simulating {department_category} department responses", complaint_id)
            
            # Step 1: Acknowledgment (ORANGE → BLUE)
            await asyncio.sleep(ack_delay)
            await self._send_government_response(complaint_id, {
                "status": "BLUE",
                "message": templates["acknowledgment"],
                "department": complaint.get('department', 'Government Department'),
                "officer_name": f"{department_category} Officer"
            })
            
            # Step 2: Progress Update (BLUE → GREEN)  
            await asyncio.sleep(progress_delay - ack_delay)
            await self._send_government_response(complaint_id, {
                "status": "GREEN", 
                "message": templates["progress"],
                "department": complaint.get('department', 'Government Department'),
                "officer_name": f"{department_category} Officer",
                "estimated_completion": (datetime.now(timezone.utc) + timedelta(minutes=resolution_delay//60)).isoformat()
            })
            
            # Step 3: Resolution (GREEN → BLACK)
            await asyncio.sleep(resolution_delay - progress_delay)
            await self._send_government_response(complaint_id, {
                "status": "BLACK",
                "message": templates["resolution"], 
                "department": complaint.get('department', 'Government Department'),
                "officer_name": f"{department_category} Department Head"
            })
            
            await self.update_status(AgentStatus.COMPLETED, f"Government simulation completed for {complaint_id}", complaint_id)
            
        except Exception as e:
            logger.error(f"Error in government simulation: {e}")
            await self.update_status(AgentStatus.ERROR, f"Simulation error: {str(e)}", complaint_id)
    
    async def _send_government_response(self, complaint_id: str, response_data: Dict):
        """Send government response through Tracker Agent"""
        shared_memory.send_agent_message(
            self.name, "Tracker_Agent", "government_response",
            {"complaint_id": complaint_id, "response_data": response_data},
            priority="high"
        )
        
        logger.info(f"🏛️ Auto-Government Response: {complaint_id} → {response_data['status']}")

class EscalateAgent(BaseAgent):
    def __init__(self):
        super().__init__("Escalate_Agent", "Escalates complaints when departments don't respond", "⚠️")
    
    async def handle_message(self, message: Dict):
        if message['type'] == 'check_escalation':
            await self.check_escalation(message['content']['complaint_id'])
    
    async def check_escalation(self, complaint_id: str) -> Dict:
        """Check if complaint needs escalation"""
        complaint = shared_memory.get_complaint(complaint_id)
        if not complaint:
            return {"error": "Complaint not found"}
        
        await self.update_status(AgentStatus.PROCESSING, "Checking escalation criteria...", complaint_id)
        
        # Check if escalation is needed
        needs_escalation = self._should_escalate(complaint)
        
        escalation_data = {
            'checked_at': datetime.now(timezone.utc).isoformat(),
            'needs_escalation': needs_escalation,
            'escalation_reason': self._get_escalation_reason(complaint) if needs_escalation else None,
            'escalation_level': self._get_escalation_level(complaint) if needs_escalation else None
        }
        
        complaint['escalation'] = escalation_data
        shared_memory.save_complaint(complaint_id, complaint)
        
        if needs_escalation:
            await self.update_status(AgentStatus.COMPLETED, 
                                   f"Escalation recommended: {escalation_data['escalation_reason']}", 
                                   complaint_id)
        else:
            await self.update_status(AgentStatus.COMPLETED, "No escalation needed", complaint_id)
        
        return escalation_data
    
    def _should_escalate(self, complaint: Dict) -> bool:
        """Determine if complaint should be escalated"""
        # Check if deadline passed
        deadlines = complaint.get('deadlines', {})
        if 'acknowledgment' in deadlines:
            ack_deadline = datetime.fromisoformat(deadlines['acknowledgment'])
            if datetime.now(timezone.utc) > ack_deadline and complaint.get('status') in [ComplaintStatus.RED.value, ComplaintStatus.ORANGE.value]:
                return True
        
        # Check urgency
        if complaint.get('urgency') == 'CRITICAL' and complaint.get('status') != ComplaintStatus.BLACK.value:
            complaint_time = datetime.fromisoformat(complaint.get('timestamp', datetime.now(timezone.utc).isoformat()))
            if datetime.now(timezone.utc) - complaint_time > timedelta(hours=6):
                return True
        
        return False
    
    def _get_escalation_reason(self, complaint: Dict) -> str:
        """Get reason for escalation"""
        if complaint.get('urgency') == 'CRITICAL':
            return "Critical complaint not resolved within 6 hours"
        return "Department failed to acknowledge within deadline"
    
    def _get_escalation_level(self, complaint: Dict) -> str:
        """Determine escalation level"""
        if complaint.get('urgency') == 'CRITICAL':
            return "HIGH"
        return "MEDIUM"

# Initialize all agents
agents = {
    "chat": ChatAgent(),
    "router": RouterAgent(), 
    "tracker": TrackerAgent(),
    "follow": FollowAgent(),
    "analytics": AnalyticsAgent(),
    "escalate": EscalateAgent()
}

# =============================================================================
# BACKGROUND AGENT COORDINATOR
# =============================================================================

class AgentCoordinator:
    """Manages agent collaboration and message processing"""
    
    def __init__(self):
        self.running = True
    
    async def start(self):
        """Start the agent coordination loop"""
        logger.info("🤖 Agent Coordinator starting...")
        while self.running:
            # Process messages for all agents
            for agent in agents.values():
                try:
                    await agent.process_messages()
                except Exception as e:
                    logger.error(f"Error processing messages for {agent.name}: {e}")
            
            await asyncio.sleep(1)  # Check every second
    
    def stop(self):
        self.running = False

coordinator = AgentCoordinator()

# =============================================================================
# WEBSOCKET ENDPOINTS
# =============================================================================

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """WebSocket for citizen chat interface"""
    await websocket.accept()
    shared_memory.websocket_connections[user_id] = websocket
    logger.info(f"🔌 User connected: {user_id}")
    
    # Send welcome message
    welcome_msg = {
        "type": "connection_status",
        "status": "connected",
        "message": "Connected to Citizen Voice AI - Real-time updates enabled",
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await websocket.send_text(json.dumps(welcome_msg))
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types from citizen
            if message.get("type") == "complaint_status_request":
                complaint_id = message.get("complaint_id")
                if complaint_id:
                    complaint = shared_memory.get_complaint(complaint_id)
                    if complaint:
                        status_response = {
                            "type": "complaint_status_response",
                            "complaint_id": complaint_id,
                            "status": complaint.get("status"),
                            "processing_history": shared_memory.processing_history.get(complaint_id, []),
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                        await websocket.send_text(json.dumps(status_response))
            
            elif message.get("type") == "area_complaints_request":
                area = message.get("area", "Delhi")
                public_complaints = shared_memory.get_public_complaints_by_area(area)
                area_response = {
                    "type": "area_complaints_response",
                    "area": area,
                    "complaints": public_complaints[:10],  # Limit to 10 most recent
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                await websocket.send_text(json.dumps(area_response))
            
    except WebSocketDisconnect:
        if user_id in shared_memory.websocket_connections:
            del shared_memory.websocket_connections[user_id]
        logger.info(f"🔌 User disconnected: {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")

@app.websocket("/ws/dashboard")
async def websocket_dashboard_endpoint(websocket: WebSocket):
    """WebSocket for government dashboard"""
    await websocket.accept()
    shared_memory.dashboard_connections.append(websocket)
    logger.info("🏛️ Dashboard connected")
    
    # Send initial dashboard data
    welcome_msg = {
        "type": "dashboard_connected",
        "status": "connected",
        "message": "Government Dashboard Connected - Real-time complaint updates enabled",
        "total_complaints": len(shared_memory.complaints),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    await websocket.send_text(json.dumps(welcome_msg))
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle government responses
            if message.get("type") == "government_response":
                complaint_id = message.get("complaint_id")
                response_data = message.get("response_data")
                
                if complaint_id and response_data:
                    # Process government response
                    complaint = shared_memory.get_complaint(complaint_id)
                    if complaint:
                        # Update complaint status based on response
                        new_status = ComplaintStatus(response_data.get("status", ComplaintStatus.BLUE))
                        
                        # Send message to Tracker Agent for processing
                        shared_memory.send_agent_message(
                            "Government_Dashboard", "Tracker_Agent", "government_response",
                            {
                                "complaint_id": complaint_id,
                                "response_data": response_data
                            },
                            priority="high"
                        )
                        
                        # Immediate response confirmation to dashboard
                        dashboard_response = {
                            "type": "response_confirmed",
                            "complaint_id": complaint_id,
                            "status": new_status.value,
                            "message": "Response recorded and citizen notified",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                        await websocket.send_text(json.dumps(dashboard_response))
            
            elif message.get("type") == "get_all_complaints":
                # Send all complaints to dashboard
                complaints = []
                for complaint_id, complaint in shared_memory.complaints.items():
                    complaint_copy = complaint.copy()
                    complaint_copy['processing_history'] = shared_memory.processing_history.get(complaint_id, [])
                    complaint_copy['upvotes'] = len(shared_memory.upvotes.get(complaint_id, set()))
                    complaints.append(complaint_copy)
                
                dashboard_data = {
                    "type": "all_complaints_response",
                    "complaints": complaints,
                    "total": len(complaints),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                await websocket.send_text(json.dumps(dashboard_data))
                
    except WebSocketDisconnect:
        if websocket in shared_memory.dashboard_connections:
            shared_memory.dashboard_connections.remove(websocket)
        logger.info("🏛️ Dashboard disconnected")
    except Exception as e:
        logger.error(f"Dashboard WebSocket error: {e}")

# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def serve_citizen_interface():
    """Serve the citizen chat interface"""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>Citizen Voice AI</h1><p>Frontend files not found. Please check if index.html exists.</p>")

@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the government dashboard"""
    try:
        with open("dashboard.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        return HTMLResponse("<h1>Government Dashboard</h1><p>Frontend files not found. Please check if dashboard.html exists.</p>")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "agents": {name: agent.status.value for name, agent in agents.items()},
        "watson": "configured" if watson_config.is_configured() else "mock_mode",
        "active_complaints": len(shared_memory.complaints),
        "websocket_connections": len(shared_memory.websocket_connections),
        "dashboard_connections": len(shared_memory.dashboard_connections)
    }

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(message: ChatMessage, background_tasks: BackgroundTasks):
    """Main chat endpoint for citizens"""
    try:
        # Generate complaint ID
        complaint_id = f"CMP-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        
        # Parse the message to extract complaint details
        complaint_data = {
            "citizenName": "Anonymous User",  # Will be updated when user provides details
            "phone": "Not provided",
            "location": "Not specified", 
            "complaintText": message.message,
            "complaintType": ComplaintType.PRIVATE,
            "user_id": message.user_id,
            "area": "Unknown"
        }
        
        # Start the agent workflow in background
        background_tasks.add_task(process_complaint_workflow, complaint_data, complaint_id)
        
        return ChatResponse(
            message=f"I understand your complaint. I'm starting the processing with ID: {complaint_id}. Our AI agents will handle this automatically.",
            complaint_id=complaint_id,
            current_status=ComplaintStatus.RED,
            processing_steps=[]
        )
        
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        return ChatResponse(
            message="I'm sorry, there was an error processing your request. Please try again.",
            processing_steps=[]
        )

@app.post("/api/complaint", response_model=ComplaintResponse)
async def submit_complaint(complaint: ComplaintInput, background_tasks: BackgroundTasks):
    """Submit formal complaint"""
    try:
        complaint_id = f"CMP-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
        
        complaint_data = {
            "citizenName": complaint.citizenName,
            "phone": complaint.phone,
            "location": complaint.location,
            "complaintText": complaint.complaintText,
            "complaintType": complaint.complaintType,
            "area": complaint.area or "Unknown"
        }
        
        # Start agent workflow
        background_tasks.add_task(process_complaint_workflow, complaint_data, complaint_id)
        
        return ComplaintResponse(
            complaint_id=complaint_id,
            status=ComplaintStatus.RED,
            category="Processing",
            urgency=UrgencyLevel.MEDIUM,
            department="Determining...",
            deadlines={},
            is_public=complaint.complaintType == ComplaintType.PUBLIC,
            upvotes=0,
            area=complaint.area,
            processing_steps=[]
        )
        
    except Exception as e:
        logger.error(f"Error submitting complaint: {e}")
        raise HTTPException(status_code=500, detail="Error processing complaint")

@app.post("/api/complaint/{complaint_id}/respond")
async def government_respond(complaint_id: str, response: GovernmentResponse):
    """Government department response to complaint"""
    try:
        complaint = shared_memory.get_complaint(complaint_id)
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")
        
        # Send response to Tracker Agent
        shared_memory.send_agent_message(
            "Government", "Tracker_Agent", "government_response",
            {
                "complaint_id": complaint_id,
                "response_data": response.dict()
            },
            priority="high"
        )
        
        return {"message": "Response recorded and complaint status updated"}
        
    except Exception as e:
        logger.error(f"Error processing government response: {e}")
        raise HTTPException(status_code=500, detail="Error processing response")

@app.post("/api/complaint/{complaint_id}/message")
async def add_complaint_message(complaint_id: str, message: ComplaintChatMessage):
    """Add a message to an existing complaint conversation"""
    try:
        # Verify complaint exists
        complaint = shared_memory.get_complaint(complaint_id)
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")
        
        # Store the message in shared memory
        chat_data = {
            "complaint_id": complaint_id,
            "message": message.message,
            "user_type": message.user_type,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Add to complaint's chat history using shared_memory function
        success = shared_memory.add_chat_message(
            complaint_id, 
            message.message, 
            message.user_type, 
            chat_data["timestamp"]
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="Complaint not found")
        
        # Broadcast the message to relevant clients
        websocket_update = {
            "type": "chat_message",
            "complaint_id": complaint_id,
            "message": message.message,
            "user_type": message.user_type,
            "timestamp": chat_data["timestamp"]
        }
        
        # Send to both citizen and government dashboard
        await shared_memory.broadcast_to_users(websocket_update)
        await shared_memory.broadcast_to_dashboards(websocket_update)
        
        return {"message": "Chat message added successfully", "timestamp": chat_data["timestamp"]}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding chat message: {e}")
        raise HTTPException(status_code=500, detail="Error processing message")

@app.post("/api/complaint/{complaint_id}/upvote")
async def upvote_complaint(complaint_id: str, request: UpvoteRequest):
    """Upvote a public complaint"""
    try:
        success = shared_memory.upvote_complaint(complaint_id, request.user_id)
        if success:
            upvotes = len(shared_memory.upvotes.get(complaint_id, set()))
            
            # Broadcast upvote update
            update = {
                "type": "upvote_update",
                "complaint_id": complaint_id,
                "upvotes": upvotes,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            await shared_memory.broadcast_to_users(update)
            
            return {"message": "Upvote added", "total_upvotes": upvotes}
        else:
            raise HTTPException(status_code=400, detail="Cannot upvote this complaint")
            
    except Exception as e:
        logger.error(f"Error upvoting complaint: {e}")
        raise HTTPException(status_code=500, detail="Error processing upvote")

@app.get("/api/public-complaints/{area}")
async def get_public_complaints(area: str):
    """Get public complaints for an area"""
    try:
        complaints = shared_memory.get_public_complaints_by_area(area)
        return {"complaints": complaints, "area": area}
    except Exception as e:
        logger.error(f"Error getting public complaints: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving complaints")

@app.get("/api/complaint/{complaint_id}")
async def get_complaint(complaint_id: str):
    """Get complaint details"""
    try:
        complaint = shared_memory.get_complaint(complaint_id)
        if not complaint:
            raise HTTPException(status_code=404, detail="Complaint not found")
        
        # Add processing history
        complaint['processing_history'] = shared_memory.processing_history.get(complaint_id, [])
        
        return complaint
    except Exception as e:
        logger.error(f"Error getting complaint: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving complaint")

@app.get("/api/complaints")
async def list_complaints():
    """List all complaints (for dashboard)"""
    try:
        complaints = []
        for complaint_id, complaint in shared_memory.complaints.items():
            complaint_copy = complaint.copy()
            complaint_copy['id'] = complaint_id  # Add the complaint ID
            complaint_copy['processing_history'] = shared_memory.processing_history.get(complaint_id, [])
            complaint_copy['upvotes'] = len(shared_memory.upvotes.get(complaint_id, set()))
            complaints.append(complaint_copy)
        
        return {"complaints": complaints, "total": len(complaints)}
    except Exception as e:
        logger.error(f"Error listing complaints: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving complaints")

@app.get("/api/agents/status")
async def get_agent_status():
    """Get status of all agents"""
    return {
        "agents": shared_memory.agent_states,
        "total_agents": len(agents),
        "active_messages": len([msg for msg in shared_memory.agent_message_queue if not msg['processed']])
    }

@app.get("/api/analytics")
async def get_analytics():
    """Get system analytics"""
    try:
        complaints = list(shared_memory.complaints.values())
        
        # Calculate statistics
        status_counts = {}
        category_counts = {}
        urgency_counts = {}
        
        for complaint in complaints:
            status = complaint.get('status', 'Unknown')
            category = complaint.get('category', 'Unknown')
            urgency = complaint.get('urgency', 'Unknown')
            
            status_counts[status] = status_counts.get(status, 0) + 1
            category_counts[category] = category_counts.get(category, 0) + 1
            urgency_counts[urgency] = urgency_counts.get(urgency, 0) + 1
        
        return {
            "total_complaints": len(complaints),
            "status_distribution": status_counts,
            "category_distribution": category_counts,
            "urgency_distribution": urgency_counts,
            "public_complaints": len([c for c in complaints if c.get('complaint_type') == ComplaintType.PUBLIC]),
            "total_upvotes": sum(len(upvotes) for upvotes in shared_memory.upvotes.values())
        }
    except Exception as e:
        logger.error(f"Error getting analytics: {e}")
        raise HTTPException(status_code=500, detail="Error retrieving analytics")

# =============================================================================
# BACKGROUND TASK FUNCTIONS
# =============================================================================

async def process_complaint_workflow(complaint_data: Dict, complaint_id: str):
    """Complete complaint processing workflow through all agents"""
    try:
        logger.info(f"🚀 Starting workflow for complaint {complaint_id}")
        
        # Broadcast new complaint to dashboard immediately
        dashboard_notification = {
            "type": "new_complaint",
            "complaint_id": complaint_id,
            "category": "Processing...",
            "urgency": "MEDIUM",
            "location": complaint_data.get("location", "Not specified"),
            "citizen_name": complaint_data.get("citizenName", "Anonymous"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": f"New complaint received: {complaint_data.get('complaintText', '')[:100]}..."
        }
        await shared_memory.broadcast_to_dashboards(dashboard_notification)
        
        # Step 1: Chat Agent processes the complaint (RED)
        result1 = await agents["chat"].process_complaint(complaint_data, complaint_id)
        await asyncio.sleep(0.5)  # Brief pause between agents
        
        # After processing, broadcast updated complaint info to dashboard
        processed_complaint = shared_memory.get_complaint(complaint_id)
        if processed_complaint:
            updated_notification = {
                "type": "new_complaint",
                "complaint_id": complaint_id,
                "category": processed_complaint.get("category", "General"),
                "urgency": processed_complaint.get("urgency", "MEDIUM"),
                "location": processed_complaint.get("location", "Not specified"),
                "citizen_name": processed_complaint.get("citizen_name", "Anonymous"),
                "status": processed_complaint.get("status", "RED"),
                "timestamp": processed_complaint.get("timestamp"),
                "department": processed_complaint.get("department", "Routing..."),
                "message": f"Complaint processed: {processed_complaint.get('category')} issue with {processed_complaint.get('urgency')} priority"
            }
            await shared_memory.broadcast_to_dashboards(updated_notification)
        
        # The rest of the workflow will be handled by agent message passing
        # Router Agent will receive message and continue the chain
        
        logger.info(f"✅ Workflow initiated for complaint {complaint_id}")
        
    except Exception as e:
        logger.error(f"Error in complaint workflow: {e}")
        
        # Broadcast error to dashboard
        error_notification = {
            "type": "complaint_error",
            "complaint_id": complaint_id,
            "message": f"Error processing complaint {complaint_id}: {str(e)}"
        }
        await shared_memory.broadcast_to_dashboards(error_notification)

# =============================================================================
# APPLICATION LIFECYCLE
# =============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize the system on startup"""
    logger.info("🏛️ Citizen Voice AI Starting Up...")
    logger.info(f"🤖 Agents initialized: {len(agents)}")
    logger.info(f"💾 Watson integration: {'Configured' if watson_config.is_configured() else 'Mock mode'}")
    
    # Start agent coordinator
    asyncio.create_task(coordinator.start())
    logger.info("🔄 Agent coordinator started")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("🛑 Shutting down Citizen Voice AI...")
    coordinator.stop()

# =============================================================================
# MAIN APPLICATION
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 80)
    print("🏛️  CITIZEN VOICE AI - ENHANCED GOVERNMENT ACCOUNTABILITY SYSTEM")
    print("=" * 80)
    print("🚀 Starting Enhanced Multi-Agent System...")
    print("🤖 6 AI Agents Working Together Autonomously")
    print("🎨 Color-Coded Status System: RED → ORANGE → BLUE → GREEN → BLACK")
    print("🔄 Real-time WebSocket Updates")
    print("👥 Public/Private Complaints with Community Features")
    print("📊 Advanced Analytics and Escalation System")
    print("=" * 80)
    print("🔗 Citizen Interface: http://localhost:8000/")
    print("🔗 Government Dashboard: http://localhost:8000/dashboard")
    print("🔗 API Documentation: http://localhost:8000/docs")
    print("🔗 Health Check: http://localhost:8000/api/health")
    print("=" * 80)
    
    if watson_config.is_configured():
        print("🤖 Watson AI: ✅ Configured and Ready")
    else:
        print("🤖 Watson AI: ⚠️  Running in Mock Mode (Set environment variables for Watson)")
    
    print("=" * 80)
    print("🏃 Starting server on http://localhost:8000")
    print("=" * 80)
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )