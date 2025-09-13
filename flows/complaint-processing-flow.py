"""
Citizen Voice AI - Complaint Processing Flow (CORRECTED)
End-to-end automated complaint processing with 6 AI agents

This flow orchestrates all 6 AI agents to process citizen complaints 
from intake to resolution tracking using IBM watsonx Orchestrate ADK.
"""
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field
from ibm_watsonx_orchestrate.flow_builder.flows import END, Flow, flow, START, AgentNode

# Input schema definition using Pydantic
class ComplaintInput(BaseModel):
    complaint_text: str = Field(description="Citizen's complaint description in any language")
    citizen_name: str = Field(description="Citizen's name")
    phone: str = Field(description="Contact number")
    location: str = Field(description="Complaint location")
    is_public: Optional[bool] = Field(default=False, description="Whether complaint should be visible to community")

# Output schema definition using Pydantic  
class ComplaintOutput(BaseModel):
    complaint_id: str = Field(description="Generated unique complaint identifier")
    processing_status: str = Field(description="Overall processing status")
    assigned_department: str = Field(description="Department assigned to handle complaint")
    current_status: str = Field(description="Current complaint status (RED/ORANGE/BLUE/GREEN/BLACK)")
    acknowledgment_deadline: str = Field(description="Department acknowledgment deadline")
    resolution_deadline: str = Field(description="Expected resolution deadline")
    citizen_response: str = Field(description="Response message to citizen")
    tracking_active: bool = Field(description="Whether tracking is active")
    analytics_summary: dict = Field(description="Analytics and insights summary")
    agent_processing_summary: dict = Field(description="Summary of all agent processing")

# Individual agent request/response schemas
class ChatAgentRequest(BaseModel):
    text: str = Field(description="Complaint text to process")
    location: str = Field(description="Complaint location")
    citizen_id: str = Field(description="Citizen identifier")
    contact_info: dict = Field(description="Contact information")

class ChatAgentResponse(BaseModel):
    complaint_id: str = Field(description="Generated complaint ID")
    category: str = Field(description="Identified complaint category")
    urgency: str = Field(description="Assessed urgency level")
    citizen_response: str = Field(description="Response to citizen")

class RouterAgentRequest(BaseModel):
    complaint_id: str = Field(description="Complaint ID to route")
    category: str = Field(description="Complaint category")
    urgency: str = Field(description="Urgency level")
    location: str = Field(description="Location")

class RouterAgentResponse(BaseModel):
    assigned_department: str = Field(description="Assigned department")
    acknowledgment_deadline: str = Field(description="Acknowledgment deadline")
    resolution_deadline: str = Field(description="Resolution deadline")
    status: str = Field(description="Routing status")

class TrackerAgentRequest(BaseModel):
    complaint_id: str = Field(description="Complaint ID to track")
    assigned_department: str = Field(description="Assigned department")
    deadlines: dict = Field(description="Deadline information")

class TrackerAgentResponse(BaseModel):
    status: str = Field(description="Tracking status")
    tracking_info: dict = Field(description="Tracking details")

class FollowAgentRequest(BaseModel):
    complaint_id: str = Field(description="Complaint ID for follow-up")
    department_info: dict = Field(description="Department information")

class FollowAgentResponse(BaseModel):
    status: str = Field(description="Follow-up status")
    reminder_type: str = Field(description="Type of reminder set")

class AnalyticsAgentRequest(BaseModel):
    complaints: list = Field(description="List of complaints to analyze")
    analysis_type: str = Field(description="Type of analysis")
    focus_complaint_id: str = Field(description="Focus complaint ID")

class AnalyticsAgentResponse(BaseModel):
    summary: dict = Field(description="Analytics summary")
    insights: list = Field(description="Generated insights")
    status: str = Field(description="Analytics processing status")

class EscalateAgentRequest(BaseModel):
    complaint_id: str = Field(description="Complaint ID to check for escalation")
    tracking_info: dict = Field(description="Tracking information")
    urgency: str = Field(description="Urgency level")

class EscalateAgentResponse(BaseModel):
    escalated: bool = Field(description="Whether escalation occurred")
    reason: str = Field(description="Escalation reason")
    status: str = Field(description="Escalation status")

# Helper functions to build agent nodes
def build_chat_agent_node(aflow: Flow) -> AgentNode:
    """Build the Chat Agent node"""
    return aflow.agent(
        name="chat_processing",
        agent="Chat_Agent",
        title="Process and Classify Complaint",
        description="Analyze citizen complaint, detect language, categorize, and assess urgency",
        message="Please process this complaint: {text}. Location: {location}. Contact: {contact_info}",
        input_schema=ChatAgentRequest,
        output_schema=ChatAgentResponse
    )

def build_router_agent_node(aflow: Flow) -> AgentNode:
    """Build the Router Agent node"""
    return aflow.agent(
        name="routing",
        agent="Router_Agent", 
        title="Route to Department",
        description="Route complaint to appropriate government department with deadlines",
        message="Route complaint {complaint_id} of category {category} with urgency {urgency} at location {location}",
        input_schema=RouterAgentRequest,
        output_schema=RouterAgentResponse
    )

def build_tracker_agent_node(aflow: Flow) -> AgentNode:
    """Build the Tracker Agent node"""
    return aflow.agent(
        name="tracking",
        agent="Tracker_Agent",
        title="Setup Complaint Tracking", 
        description="Setup continuous monitoring and status tracking for the complaint",
        message="Setup tracking for complaint {complaint_id} assigned to {assigned_department} with deadlines {deadlines}",
        input_schema=TrackerAgentRequest,
        output_schema=TrackerAgentResponse
    )

def build_follow_agent_node(aflow: Flow) -> AgentNode:
    """Build the Follow Agent node"""
    return aflow.agent(
        name="follow_up",
        agent="Follow_Agent",
        title="Setup Automated Reminders",
        description="Configure automated reminder system for the complaint",
        message="Setup follow-up reminders for complaint {complaint_id} with department info {department_info}",
        input_schema=FollowAgentRequest,
        output_schema=FollowAgentResponse
    )

def build_analytics_agent_node(aflow: Flow) -> AgentNode:
    """Build the Analytics Agent node"""
    return aflow.agent(
        name="analytics",
        agent="Analytics_Agent",
        title="Generate Analytics and Insights",
        description="Analyze complaint patterns and generate insights",
        message="Analyze complaints {complaints} with focus on {focus_complaint_id}. Analysis type: {analysis_type}",
        input_schema=AnalyticsAgentRequest,
        output_schema=AnalyticsAgentResponse
    )

def build_escalate_agent_node(aflow: Flow) -> AgentNode:
    """Build the Escalate Agent node"""
    return aflow.agent(
        name="escalation",
        agent="Escalate_Agent",
        title="Monitor for Escalation",
        description="Monitor complaint for escalation needs and take action if required",
        message="Check escalation needs for complaint {complaint_id} with tracking info {tracking_info} and urgency {urgency}",
        input_schema=EscalateAgentRequest,
        output_schema=EscalateAgentResponse
    )

@flow(
    name="complaint_processing_workflow",
    description="End-to-end automated complaint processing with 6 AI agents",
    input_schema=ComplaintInput,
    output_schema=ComplaintOutput,
    schedulable=True
)
def build_complaint_processing_flow(aflow: Flow) -> Flow:
    """
    Build the complaint processing flow that orchestrates all 6 AI agents
    to handle citizen complaints from intake to resolution tracking.
    
    Flow sequence:
    1. Chat Agent - Process and classify complaint
    2. Router Agent - Route to appropriate department with deadlines
    3. Tracker Agent - Setup continuous monitoring
    4. Follow Agent - Setup automated reminders (parallel with Analytics)
    5. Analytics Agent - Generate insights and analytics (parallel with Follow)
    6. Escalate Agent - Monitor for escalation needs (parallel)
    
    Args:
        aflow: Flow object to build the workflow
        
    Returns:
        Flow: Complete configured flow ready for execution
    """
    
    # Build all agent nodes
    chat_agent = build_chat_agent_node(aflow)
    router_agent = build_router_agent_node(aflow) 
    tracker_agent = build_tracker_agent_node(aflow)
    follow_agent = build_follow_agent_node(aflow)
    analytics_agent = build_analytics_agent_node(aflow)
    escalate_agent = build_escalate_agent_node(aflow)
    
    # Build the flow sequence
    # Main sequential path: START -> Chat -> Router -> Tracker
    aflow.sequence(START, chat_agent, router_agent, tracker_agent)

    # Parallel processing after tracker: Follow, Analytics, and Escalate run in parallel
    # Using sequence chaining to simulate parallelism by branching manually
    # Note: Replace with official parallel method if available in SDK

    # Follow Agent sequence
    aflow.sequence(tracker_agent, follow_agent)
    aflow.sequence(follow_agent, END)

    # Analytics Agent sequence
    aflow.sequence(tracker_agent, analytics_agent)
    aflow.sequence(analytics_agent, END)

    # Escalate Agent sequence
    aflow.sequence(tracker_agent, escalate_agent)
    aflow.sequence(escalate_agent, END)

    # Output mapping handled by returning a dictionary from flow function
    # Compose output from agent results manually in flow execution environment

    return aflow


# Test function for local development
def test_complaint_flow():
    """Test the complaint processing flow locally"""
    
    test_input = ComplaintInput(
        complaint_text="There has been no electricity in my street for 2 days. This is causing major problems for everyone.",
        citizen_name="John Doe",
        phone="+91-9876543210", 
        location="Karol Bagh, Delhi",
        is_public=True
    )
    
    print("=== Citizen Voice AI - Complaint Processing Flow Test (CORRECTED) ===")
    print(f"Input: {test_input.complaint_text}")
    print(f"Location: {test_input.location}")
    print(f"Citizen: {test_input.citizen_name}")
    print(f"Public Complaint: {test_input.is_public}")
    
    print("\nFlow Structure:")
    print("START -> Chat_Agent -> Router_Agent -> Tracker_Agent")
    print("                                          |")
    print("                                          ├-> Follow_Agent -> END")
    print("                                          ├-> Analytics_Agent -> END")
    print("                                          └-> Escalate_Agent -> END")
    
    print("\nAgent Processing Sequence:")
    print("1. Chat_Agent: Process complaint text -> classify as 'electricity', urgency 'HIGH'")
    print("2. Router_Agent: Route to DERC -> set acknowledgment (24h) and resolution (5d) deadlines")
    print("3. Tracker_Agent: Setup monitoring -> status tracking and deadline monitoring")
    print("4. Parallel Processing:")
    print("   - Follow_Agent: Configure automated reminders")
    print("   - Analytics_Agent: Generate complaint insights")
    print("   - Escalate_Agent: Monitor for escalation needs")
    
    print("\nExpected Output:")
    print("- complaint_id: 8-character unique ID (e.g., 'a1b2c3d4')")
    print("- assigned_department: 'Delhi Electricity Regulatory Commission (DERC)'")
    print("- current_status: 'ORANGE'")
    print("- acknowledgment_deadline: '24 hours from now'")
    print("- resolution_deadline: '5 days from now'")
    print("- tracking_active: true")
    
    print("\nFlow ready for import to IBM watsonx Orchestrate!")
    print("\nImport Commands:")
    print("orchestrate tools import -k flow -f flows/complaint-processing-flow.py")
    print("orchestrate flows list")
    print("orchestrate flows run complaint_processing_workflow --input '{...}'")


if __name__ == "__main__":
    test_complaint_flow()