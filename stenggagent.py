# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64
from pathlib import Path

from agent_framework import ChatMessage, DataContent, Role, TextContent, UriContent
from agent_framework.azure import AzureOpenAIResponsesClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

"""
Azure OpenAI Responses Client with Image Analysis Example

This sample demonstrates using Azure OpenAI Responses for image analysis and vision tasks,
showing multi-modal messages combining text and image content.
"""


async def main():
    print("=== Azure Responses Agent with Image Analysis ===")

    # 1. Create an Azure Responses agent with vision capabilities
    agent = AzureOpenAIResponsesClient(credential=AzureCliCredential()).create_agent(
        name="VisionAgent",
        instructions="You are a helpful agent that can analyze images.",
    )

    image_path = "img/csifactoryengdraw1.jpg"
    
    
    image_path = Path("img/csifactoryengdraw1.jpg")
    
    with image_path.open("rb") as f:
        encoded_bytes = base64.b64encode(f.read())
    
    base64_string = encoded_bytes.decode("utf-8")
    # print(base64_string)
    # image_uri = f"data:image/jpg;base64,{base64_string}"
    data_uri = f"data:image/jpeg;base64,{base64_string}"

    # 2. Create a simple message with both text and image content
    # user_message = ChatMessage(
    #     role="user",
    #     contents=[
    #         TextContent(text="What do you see in this image?"),
    #         UriContent(
    #             uri="https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wisconsin-madison-the-nature-boardwalk.jpg/2560px-Gfp-wisconsin-madison-the-nature-boardwalk.jpg",
    #             media_type="image/jpeg",
    #         ),
    #     ],
    # )
    user_message = ChatMessage(
        role=Role.USER,
        contents=[TextContent(text="What's in this image?"), 
                  DataContent(
                    uri=data_uri, media_type="image/jpeg"
                    )
                ],
    )

    # 3. Get the agent's response
    print("User: What do you see in this image? [Image provided]")
    result = await agent.run(user_message)
    print(f"Agent: {result.text}")
    print()
    


if __name__ == "__main__":
    asyncio.run(main())