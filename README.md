#  Citizen Voice AI - Government Accountability System
# AI Agent That Never Lets Government Ignore You

**Project ID:** `T3:315-Citizen Voice AI MultiAgent Government Accountability System-vinay-vinayb1021`

** Complete AI-Powered Government Complaint Processing System with Dual Deployment Modes**

---

##  **Project Overview**

A comprehensive AI system that automates government complaint processing from citizen submission to resolution tracking. Features 6 intelligent agents working together to ensure transparency, accountability, and efficient resolution of citizen grievances.

### **  6-Agent Workflow:**
```
Citizen Complaint → Chat Agent → Router Agent → Tracker Agent
                                                    ├→ Follow Agent
                                                    ├→ Analytics Agent  
                                                    └→ Escalate Agent
```

### ** Status Progression:**
- 🔴 **RED**: New complaint received
- 🟠 **ORANGE**: Routed to department with deadline
- 🔵 **BLUE**: Acknowledged by department
- 🟢 **GREEN**: Under resolution/progress
- ⚫ **BLACK**: Resolved and closed

---

##  **Dual Deployment Architecture**

### **Mode 1: Standalone FastAPI Demo** 
 **Perfect for:** Development, demos, local testing  
 **Features:** Instant setup, no API keys needed, full web interface  
**Deployment:** Single command - `python main.py`

### **Mode 2: IBM Watsonx Orchestrate Production**
**Perfect for:** Government deployment, enterprise scale  
 **Features:** Professional AI orchestration, cloud scalability  
 **Deployment:** Import ready-made agents, flows, and tools

---

##  **Prerequisites**

- **Python 3.9+**
- **Git** (for cloning repository)
- **Web Browser** (Chrome/Firefox recommended)
- **IBM Watsonx Account** (for Mode 2 only)

---

##  **Installation Steps**

### **1. Clone Repository**
```bash
git clone https://github.com/vinay1359/citizen-voice-ai.git
cd citizen-voice-ai
```

### **2. Create Virtual Environment**
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac/Linux  
python3 -m venv venv
source venv/bin/activate
```

### **3. Install Dependencies**
```bash
pip install -r requirements.txt
```

### **4. Environment Setup (Optional for Mode 1)**
```bash
# Copy environment template
copy ".env sample" .env

# Edit .env file with your credentials (only needed for Mode 2)
```

---

## 🚀 **Build & Deployment**

### **Mode 1: FastAPI Standalone Demo**

**Quick Start (30 seconds):**
```bash
python main.py
```

**Access Points:**
- **Citizen Interface:** http://localhost:8000
- **Government Dashboard:** http://localhost:8000/dashboard.html
- **API Documentation:** http://localhost:8000/docs

**Features Available:**
-  Real-time complaint submission
-  6-agent processing simulation
-  WebSocket live updates
-  Department routing and tracking
-  Status progression visualization
-  Government dashboard for officials

---

### ** Mode 2: IBM Watsonx Orchestrate Production**

**Prerequisites:**
- IBM Watsonx Orchestrate account
- CLI tool installed: `npm install -g @ibm/watsonx-orchestrate-cli`

**Deployment Steps:**

1. **Import Tools:**
```bash
orchestrate tools import -k python -f "tools/language_detector.py"
orchestrate tools import -k python -f "tools/text_classifier.py"
orchestrate tools import -k python -f "tools/urgency_analyzer.py"
orchestrate tools import -k python -f "tools/department_mapper.py"
orchestrate tools import -k python -f "tools/deadline_calculator.py"
orchestrate tools import -k python -f "tools/status_monitor.py"
orchestrate tools import -k python -f "tools/reminder_scheduler.py"
orchestrate tools import -k python -f "tools/data_analyzer.py"
orchestrate tools import -k python -f "tools/deadline_tracker.py"
```

2. **Import Knowledge Base:**
```bash
orchestrate knowledge import -f "knowledge/knowledge_base_config.yaml"
```

3. **Import Agents:**
```bash
orchestrate agents import -f "agents/chat-agent.yaml"
orchestrate agents import -f "agents/router-agent.yaml"
orchestrate agents import -f "agents/tracker-agent.yaml"
orchestrate agents import -f "agents/follow-agent.yaml"
orchestrate agents import -f "agents/analytics-agent.yaml"
orchestrate agents import -f "agents/escalate-agent.yaml"
```

4. **Deploy Agents:**
```bash
orchestrate agents deploy --name "Chat_Agent"
orchestrate agents deploy --name "Router_Agent"
orchestrate agents deploy --name "Tracker_Agent"
orchestrate agents deploy --name "Follow_Agent"
orchestrate agents deploy --name "Analytics_Agent"
orchestrate agents deploy --name "Escalate_Agent"
```

5. **Import Workflow:**
```bash
orchestrate flows import -f "flows/complaint-processing-flow.py"
```

---

## **Demo Instructions**

### **Mode 1 Demo Walkthrough**

1. **Start the Application:**
   ```bash
   python main.py
   ```
   Wait for: ` Server started on http://localhost:8000`

2. **Citizen Interface Demo:**
   - Open: http://localhost:8000
   - Submit a complaint: "There has been no electricity in my area for 2 days"
   - **Expected Output:** 
     - Complaint ID generated (e.g., `abc123def`)
     - Status changes: RED → ORANGE
     - Agent activities displayed in real-time
     - Department assignment shown

3. **Government Dashboard Demo:**
   - Open: http://localhost:8000/dashboard.html
   - View complaint in department queue
   - Change status from ORANGE → BLUE → GREEN → BLACK
   - **Expected Output:**
     - Real-time status updates
     - Deadline tracking
     - Department workload display

4. **Agent Workflow Observation:**
   - **Chat Agent:** Processes complaint → categorizes as "electricity"
   - **Router Agent:** Routes to "Delhi Electricity Board" → sets 48hr deadline
   - **Tracker Agent:** Monitors status → sets up tracking
   - **Follow Agent:** Schedules reminders
   - **Analytics Agent:** Generates insights
   - **Escalate Agent:** Monitors for delays

### **Mode 2 Demo Walkthrough**

1. **Access IBM Watsonx Orchestrate Interface**
2. **Start Chat with Chat_Agent:**
   ```json
   {
     "complaint_text": "Water pressure is very low in our building",
     "citizen_name": "John Doe",
     "phone": "+91-9876543210",
     "location": "Mumbai, Maharashtra"
   }
   ```
3. **Expected Agent Flow:**
   - Chat_Agent → processes and returns complaint_id
   - Router_Agent → routes to Mumbai Water Board
   - Tracker_Agent → sets up monitoring
   - Follow/Analytics/Escalate Agents → work in background

---

## **Project Structure**

```
citizen-voice-ai/
├── 📄 main.py                 # FastAPI application (Mode 1)
├── 🌐 index.html             # Citizen interface
├── 🏛️ dashboard.html         # Government dashboard
├── 📋 requirements.txt       # Python dependencies
├── ⚙️ .env                   # Configuration file
├── 🤖 agents/                # IBM Watsonx agent configs (Mode 2)
│   ├── chat-agent.yaml
│   ├── router-agent.yaml
│   ├── tracker-agent.yaml
│   ├── follow-agent.yaml
│   ├── analytics-agent.yaml
│   └── escalate-agent.yaml
├── 🔄 flows/                 # Workflow definitions (Mode 2)
│   ├── complaint-processing-flow.py
│   └── complaint-processing-flow.yaml
├── 🛠️ tools/                 # Processing tools (Mode 2)
│   ├── language_detector.py
│   ├── text_classifier.py
│   ├── urgency_analyzer.py
│   └── [6 more tools]
└── 📚 knowledge/             # Knowledge base (Mode 2)
    ├── complaint-categories.json
    ├── department-contacts.json
    └── [configuration files]
```

---

## **Configuration**

### **Environment Variables (.env)**
```bash
# IBM Watsonx Configuration (Mode 2 only)
WATSON_JWT_TOKEN=your_jwt_token_here
WATSON_INSTANCE_ID=your_instance_id
WATSON_REGION_CODE=us-south
WATSON_MODE=auto
```

---
##  **Key Features**

### **Citizen Experience**
- Multilingual complaint submission (English, Hindi, regional languages)
- Real-time status tracking with visual indicators
- SMS/Email notifications for updates
- Community visibility for public complaints
- Upvoting system for community issues

### **Government Experience**
- Centralized complaint dashboard
- Department-wise workload distribution
- Automated deadline management
- Escalation alerts and workflows
- Performance analytics and insights

### **AI Capabilities**
- Automatic complaint categorization
- Department routing based on complaint type
- Urgency assessment and prioritization
- Deadline calculation with government SLAs
- Pattern recognition for systemic issues
- Automated escalation for delays

---

## **Expected Demo Outputs**

### **Successful Complaint Processing:**
```
✅ Complaint ID: GVT2024001
✅ Category: Electricity
✅ Urgency: HIGH  
✅ Department: Delhi Electricity Regulatory Commission
✅ Acknowledgment Deadline: 24 hours
✅ Resolution Deadline: 5 days
✅ Status: ORANGE → Routed to Department
✅ Tracking: ACTIVE
✅ Reminders: SCHEDULED
```

### **Real-time Updates:**
- Agent status indicators in UI
- WebSocket notifications
- Status progression visualization
- Department workload updates
- Escalation alerts when needed

---

##  **Deployment Options**

### **Local Development**
```bash
python main.py  # Runs on localhost:8000
```

## **Troubleshooting**

### **Common Issues:**

**"Module not found" error:**
```bash
pip install -r requirements.txt
```

**Port 8000 in use:**
```bash
# Change port in main.py or kill existing process
netstat -ano | findstr :8000
```

**WebSocket connection failed:**
- Refresh browser
- Check firewall settings
- Ensure main.py is running

---

## **License**

MIT License - Open for educational and government use

---
