"""
Samsung SmartThings Agent
Example agent using the Samsung SmartThings MCP server
"""
import asyncio
import os
from dotenv import load_dotenv
from agent_framework import ChatAgent, ChatMessage, HostedMCPTool
from agent_framework.azure import AzureAIAgentClient
from azure.identity.aio import AzureCliCredential

# Load environment variables
load_dotenv()


async def main():
    """Main function to demonstrate SmartThings MCP integration"""
    
    # Create the MCP tool that connects to the local MCP server
    # You'll need to start the MCP server separately with:
    # python samsung_smartthings_mcp.py
    smartthings_mcp = HostedMCPTool(
        name="Samsung SmartThings",
        url="stdio://samsung_smartthings_mcp.py",  # Local MCP server
        approval_mode='never_require'
    )
    
    async with (
        AzureCliCredential() as credential,
        AzureAIAgentClient(credential=credential) as chat_client,
    ):
        # Create agent with SmartThings MCP tool
        agent = chat_client.create_agent(
            name="SmartThings Assistant",
            instructions="""You are a Samsung SmartThings home automation assistant.
            
            You can help users:
            - List all their SmartThings devices
            - Get detailed information about specific devices
            - Check device status and capabilities
            - Understand what controls and sensors are available
            
            When asked about devices:
            1. First get all devices to show what's available
            2. If asked about a specific device, use its device_id to get detailed logs
            3. Present information in a clear, user-friendly way
            4. Explain capabilities in plain language
            """,
            tools=[smartthings_mcp],
            model="gpt-4o"
        )
        
        # Create a thread for the conversation
        thread = await chat_client.create_thread()
        
        # Example queries
        queries = [
            "What SmartThings devices do I have?",
            # "Show me detailed information about device [device_id from first query]"
        ]
        
        for query in queries:
            print(f"\n{'='*60}")
            print(f"User: {query}")
            print('='*60)
            
            # Send message
            await chat_client.create_message(
                thread_id=thread.id,
                role="user",
                content=query
            )
            
            # Run the agent
            async with chat_client.run_stream(
                thread_id=thread.id,
                agent_id=agent.id
            ) as stream:
                async for event in stream:
                    # Print assistant messages
                    if hasattr(event, 'data'):
                        data = event.data
                        if hasattr(data, 'delta'):
                            delta = data.delta
                            if hasattr(delta, 'content'):
                                for content in delta.content:
                                    if hasattr(content, 'text') and content.text:
                                        if hasattr(content.text, 'value'):
                                            print(content.text.value, end='', flush=True)
            
            print("\n")


if __name__ == "__main__":
    asyncio.run(main())
