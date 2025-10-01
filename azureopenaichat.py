# Copyright (c) Microsoft. All rights reserved.

import asyncio
from random import randint
from typing import Annotated

from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
from pydantic import Field
import os

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

"""
Azure Chat Client Direct Usage Example

Demonstrates direct AzureChatClient usage for chat interactions with Azure OpenAI models.
Shows function calling capabilities with custom business logic.
"""


def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    conditions = ["sunny", "cloudy", "rainy", "stormy"]
    return f"The weather in {location} is {conditions[randint(0, 3)]} with a high of {randint(10, 30)}°C."


async def main() -> None:
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option.
    client = AzureOpenAIChatClient(# credential=AzureCliCredential(), 
                                   endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
                                   deployment_name=os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME"),
                                   api_key=os.getenv("AZURE_OPENAI_KEY")
    )
    message = "What's the weather in chicago and dallas?"
    stream = False
    print(f"User: {message}")
    if stream:
        print("Assistant: ", end="")
        async for chunk in client.get_streaming_response(message, tools=get_weather):
            if str(chunk):
                print(str(chunk), end="")
        print("")
    else:
        response = await client.get_response(message, tools=get_weather)
        print(f"Assistant: {response}")


if __name__ == "__main__":
    asyncio.run(main())