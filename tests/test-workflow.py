#!/usr/bin/env python3

import asyncio
import json
from datetime import datetime
# Define a mock OrchestrateClient for testing purposes
class OrchestrateClient:
    async def execute_flow(self, flow_name, input_data):
        # Mock response for testing
        return {"status": "success", "flow_name": flow_name, "input": input_data}


class WorkflowTester:
    def __init__(self):
        self.client = OrchestrateClient()
    
    async def test_complete_workflow(self):
        """Test the complete complaint processing workflow"""
        print("=" * 60)
        print("TESTING COMPLETE COMPLAINT PROCESSING WORKFLOW")
        print("=" * 60)
        
        # Test Case 1: Standard Electricity Complaint
        print("\nTest Case 1: Electricity Complaint (Hindi)")
        complaint1 = {
            "complaint_text": "हमारी गली में 3 दिन से बिजली नहीं आ रही है। ट्रांसफार्मर खराब लग रहा है।",
            "citizen_name": "राजेश कुमार",
            "phone": "9876543210",
            "location": "करोल बाग, नई दिल्ली", 
            "is_public": True
        }
        
        try:
            result1 = await self.client.execute_flow(
                flow_name="Complaint_Processing_Workflow",
                input_data=complaint1
            )
            print("✓ Workflow executed successfully")
            print(f"Result: {json.dumps(result1, indent=2)}")
        except Exception as e:
            print(f"✗ Workflow failed: {e}")
        
        # Test Case 2: Critical Water Issue
        print("\nTest Case 2: Critical Water Contamination")
        complaint2 = {
            "complaint_text": "Water from tap is dirty and smells bad. Many people in our colony are falling sick. This is urgent.",
            "citizen_name": "Priya Sharma",
            "phone": "8765432109", 
            "location": "Dwarka Sector 12, New Delhi",
            "is_public": True
        }
        
        try:
            result2 = await self.client.execute_flow(
                flow_name="Complaint_Processing_Workflow", 
                input_data=complaint2
            )
            print("✓ Critical workflow executed successfully")
            print(f"Result: {json.dumps(result2, indent=2)}")
        except Exception as e:
            print(f"✗ Critical workflow failed: {e}")
        
        # Test Case 3: Road Safety Emergency
        print("\nTest Case 3: Road Safety Emergency")
        complaint3 = {
            "complaint_text": "Huge pothole on main road near school. 5 accidents in 2 days. Children at risk.",
            "citizen_name": "Amit Singh",
            "phone": "7654321098",
            "location": "Rohini Sector 15, Delhi",
            "is_public": False
        }
        
        try:
            result3 = await self.client.execute_flow(
                flow_name="Complaint_Processing_Workflow",
                input_data=complaint3
            )
            print("✓ Emergency workflow executed successfully")
            print(f"Result: {json.dumps(result3, indent=2)}")
        except Exception as e:
            print(f"✗ Emergency workflow failed: {e}")
    
    async def test_workflow_performance(self):
        """Test workflow performance with multiple complaints"""
        print("\n" + "=" * 60)
        print("TESTING WORKFLOW PERFORMANCE")
        print("=" * 60)
        
        complaints = []
        for i in range(10):
            complaints.append({
                "complaint_text": f"Test complaint #{i+1} for performance testing",
                "citizen_name": f"Test User {i+1}",
                "phone": f"98765432{i:02d}",
                "location": f"Test Location {i+1}, Delhi",
                "is_public": i % 2 == 0
            })
        
        start_time = datetime.now()
        
        for i, complaint in enumerate(complaints):
            try:
                result = await self.client.execute_flow(
                    flow_name="Complaint_Processing_Workflow",
                    input_data=complaint
                )
                print(f"✓ Complaint {i+1}/10 processed")
            except Exception as e:
                print(f"✗ Complaint {i+1}/10 failed: {e}")
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"\nPerformance Results:")
        print(f"Total time: {duration:.2f} seconds")
        print(f"Average per complaint: {duration/10:.2f} seconds")
        print(f"Throughput: {10/duration:.2f} complaints/second")

if __name__ == "__main__":
    tester = WorkflowTester()
    asyncio.run(tester.test_complete_workflow())
    asyncio.run(tester.test_workflow_performance())