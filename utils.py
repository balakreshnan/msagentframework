import asyncio
import os
import json
from datetime import datetime
from random import randint
from typing import Annotated, Dict, List, Any
import requests
from pydantic import Field
from datetime import datetime, timedelta
import yfinance as yf

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_weather(
    location: Annotated[str, Field(description="The location to get the weather for.")],
) -> str:
    """Get the weather for a given location."""
    try:
        # Step 1: Convert location -> lat/lon using Open-Meteo Geocoding
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={location}&count=1"
        geo_response = requests.get(geo_url)

        if geo_response.status_code != 200:
            return f"Failed to get coordinates. Status code: {geo_response.status_code}"

        geo_data = geo_response.json()
        if "results" not in geo_data or len(geo_data["results"]) == 0:
            return f"Could not find location: {location}"

        lat = geo_data["results"][0]["latitude"]
        lon = geo_data["results"][0]["longitude"]

        # Step 2: Get weather for that lat/lon
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            current_weather = data.get("current_weather", {})
            temperature = current_weather.get("temperature")
            windspeed = current_weather.get("windspeed")
            return f"Weather in {location}: {temperature}°C, Wind speed: {windspeed} km/h"
        else:
            return f"Failed to get weather data. Status code: {response.status_code}"

    except Exception as e:
        import traceback
        return f"Error fetching weather data: {str(e)}\n{traceback.format_exc()}"
    
def get_ticker(company_name):
    """
    Searches for the stock ticker symbol based on the company name using Yahoo Finance search API.
    """
    url = f"https://query1.finance.yahoo.com/v1/finance/search?q={company_name}&quotesCount=1&newsCount=0"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return None
    data = json.loads(response.text)
    if data.get('quotes'):
        return data['quotes'][0]['symbol']
    return None

def fetch_stock_data(company_name) -> str:
    """
    Fetches and prints stock data for the past 7 days based on company name.
    """
    ticker = get_ticker(company_name)
    if not ticker:
        print(f"Could not find ticker for company: {company_name}")
        return
    
    # Fetch data for the past 7 days
    data = yf.download(ticker, period='7d')
    
    if data.empty:
        print(f"No data found for ticker: {ticker}")
    else:
        print(f"Stock data for {company_name} ({ticker}) over the past 7 days:")
        print(data)

    return data.to_string()
