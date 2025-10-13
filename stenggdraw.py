# Copyright (c) Microsoft. All rights reserved.

import asyncio
import base64
from pathlib import Path

from agent_framework import ChatMessage, DataContent, Role, TextContent
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential


def create_sample_image() -> str:
    """Create a simple 1x1 pixel PNG image for testing."""
    # This is a tiny red pixel in PNG format
    png_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
    return f"data:image/png;base64,{png_data}"

async def test_image() -> None:
    """Test image analysis with Azure OpenAI."""
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option. Requires AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME
    # environment variables to be set.
    # Alternatively, you can pass deployment_name explicitly:
    # client = AzureOpenAIChatClient(credential=AzureCliCredential(), deployment_name="your-deployment-name")
    client = AzureOpenAIChatClient(credential=AzureCliCredential())

    image_uri = create_sample_image()
    image_path = "img/csifactoryengdraw1.jpg"
    
    
    image_path = Path("img/csifactoryengdraw1.jpg")
    
    with image_path.open("rb") as f:
        encoded_bytes = base64.b64encode(f.read())
    
    base64_string = encoded_bytes.decode("utf-8")
    # print(base64_string)
    # image_uri = f"data:image/jpg;base64,{base64_string}"
    data_uri = f"data:image/jpeg;base64,{base64_string}"

    message = ChatMessage(
        role=Role.USER,
        contents=[TextContent(text="What's in this image?"), DataContent(uri=data_uri, media_type="image/jpeg")],
    )

    response = await client.get_response(message)
    print(f"Image Response: {response}")
    # print('Client response JSON:', client.to_json())


async def main() -> None:
    print("=== Testing Azure OpenAI Multimodal ===")
    print("Testing image analysis (supported by Chat Completions API)")
    await test_image()

if __name__ == "__main__":
    asyncio.run(main())