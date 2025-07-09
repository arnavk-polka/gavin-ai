#!/usr/bin/env python3
"""
Test script to verify multi-turn conversation tracking is working properly.
This script will simulate a multi-turn conversation and check that messages
are grouped correctly in the database.
"""

import asyncio
import aiohttp
import json
import os
import sys

# Add the api directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'api'))

async def test_multiturn_conversation():
    """Test that multi-turn conversations are properly grouped."""
    
    print("🚀 Testing Multi-turn Conversation Tracking...")
    
    base_url = "http://localhost:8000"
    session_id = None
    
    # Test messages for a conversation
    messages = [
        "Hello, can you explain what Polkadot is?",
        "How does it differ from Ethereum?", 
        "What are the main advantages of parachain architecture?",
        "Can you give me a technical example of cross-chain communication?"
    ]
    
    conversation_responses = []
    
    async with aiohttp.ClientSession() as session:
        print(f"📡 Starting conversation with {len(messages)} messages...")
        
        for i, message in enumerate(messages, 1):
            print(f"\n💬 Message {i}: {message[:50]}...")
            
            # Build request payload
            payload = {
                "message": message,
                "history": [
                    {"role": "user" if j % 2 == 0 else "assistant", "content": resp}
                    for j, resp in enumerate(conversation_responses)
                ]
            }
            
            # Include session_id if we have one from previous responses
            if session_id:
                payload["session_id"] = session_id
                print(f"🔗 Using session_id: {session_id}")
            
            try:
                # Send message to chat endpoint
                async with session.post(
                    f"{base_url}/chat/testuser",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                ) as response:
                    
                    if response.status != 200:
                        print(f"❌ Error: HTTP {response.status}")
                        continue
                    
                    full_response = ""
                    captured_session_id = None
                    
                    # Process streaming response
                    async for line in response.content:
                        line_str = line.decode('utf-8').strip()
                        if line_str.startswith('data: '):
                            try:
                                data = json.loads(line_str[6:])
                                
                                # Capture session_id from response
                                if 'session_id' in data and not captured_session_id:
                                    captured_session_id = data['session_id']
                                    if not session_id:
                                        session_id = captured_session_id
                                        print(f"✅ Captured session_id: {session_id}")
                                
                                # Accumulate response content
                                if 'choices' in data and data['choices']:
                                    delta = data['choices'][0].get('delta', {})
                                    if 'content' in delta:
                                        full_response += delta['content']
                                        
                            except json.JSONDecodeError:
                                continue
                    
                    conversation_responses.extend([message, full_response])
                    print(f"✅ Response received: {len(full_response)} characters")
                    
            except Exception as e:
                print(f"❌ Error sending message: {e}")
                return False
        
        print(f"\n🔍 Testing database retrieval...")
        
        # Test that conversations are properly grouped
        try:
            async with session.get(f"{base_url}/api/logs/conversations?limit=5") as response:
                if response.status == 200:
                    data = await response.json()
                    conversations = data.get('conversations', [])
                    
                    # Find our test conversation
                    test_conversation = None
                    for conv in conversations:
                        if conv.get('session_id') == session_id:
                            test_conversation = conv
                            break
                    
                    if test_conversation:
                        print(f"✅ Found conversation in database:")
                        print(f"   Session ID: {test_conversation['session_id']}")
                        print(f"   Total Messages: {test_conversation['total_messages']}")
                        print(f"   Handle: {test_conversation['handle']}")
                        
                        # Verify it's a multi-turn conversation
                        if test_conversation['total_messages'] >= len(messages):
                            print(f"✅ SUCCESS: Multi-turn conversation properly tracked!")
                            print(f"   Expected: {len(messages)} messages")
                            print(f"   Found: {test_conversation['total_messages']} messages")
                            return True
                        else:
                            print(f"❌ FAIL: Expected {len(messages)} messages, found {test_conversation['total_messages']}")
                            return False
                    else:
                        print(f"❌ FAIL: Conversation with session_id {session_id} not found in database")
                        print(f"Available conversations: {[c.get('session_id', 'no-id') for c in conversations]}")
                        return False
                else:
                    print(f"❌ Error retrieving conversations: HTTP {response.status}")
                    return False
                    
        except Exception as e:
            print(f"❌ Error testing database: {e}")
            return False

async def main():
    """Main test function."""
    print("🧪 Multi-turn Conversation Test")
    print("="*50)
    
    success = await test_multiturn_conversation()
    
    print("\n" + "="*50)
    if success:
        print("🎉 ALL TESTS PASSED! Multi-turn conversations are working correctly.")
    else:
        print("💥 TESTS FAILED! Check the implementation.")
    
    return success

if __name__ == "__main__":
    result = asyncio.run(main())
    sys.exit(0 if result else 1) 