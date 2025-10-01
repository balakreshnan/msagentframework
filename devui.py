from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from agent_framework.devui import serve
import os

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_weather(location: str) -> str:
    """Get weather for a location."""
    return f"Weather in {location}: 72°F and sunny"

# Create your agent
agent = ChatAgent(
    name="WeatherAgent",
    chat_client=OpenAIChatClient(api_key=os.getenv("AZURE_OPENAI_KEY"),
                                 base_url=os.getenv("AZURE_OPENAI_ENDPOINT"),
                                 model_id=os.getenv("AZURE_OPENAI_DEPLOYMENT")),
    tools=[get_weather]
)


# Launch debug UI - that's it!
serve(entities=[agent], auto_open=True)
# → Opens browser to http://localhost:8080