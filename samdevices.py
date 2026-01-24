
import asyncio
import aiohttp
import pysmartthings
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TOKEN = os.getenv("SAMSUNG_PAT")

async def main():
    async with aiohttp.ClientSession() as session:
        api = pysmartthings.SmartThings(session=session, _token=TOKEN)

        devices = await api.get_devices()
        for d in devices:
            print(f"\nDevice: {d.label}  id={d.device_id}")
            # Components and capabilities (your "menu")
            for comp_id, comp in d.components.items():
                caps = sorted([c for c in comp.capabilities])
                print(f"  Component: {comp_id}")
                print(f"    Capabilities: {', '.join(caps)}")

asyncio.run(main())
