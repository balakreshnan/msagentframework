from datetime import datetime
import os
from openai import OpenAI, AzureOpenAI
import requests
import time
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

#now lets process the video
def createvideo(query):
    """
    Generate video using Azure OpenAI Sora via direct API calls
    Returns: path to the generated video file
    """
    # 1. Setup
    endpoint = os.getenv("SORA_ENDPOINT")
    api_key = os.getenv("SORA_API_KEY")
    api_version = "preview"
    deployment_name = "sora-2"  # Your Sora deployment name
    
    # 2. Video generation parameters
    prompt = query[:1000]  # Limit prompt length to avoid issues
    
    # 3. Construct the Azure-specific endpoint URL
    # Remove trailing slashes and /openai from endpoint if present
    base_endpoint = endpoint.rstrip('/')
    if base_endpoint.endswith('/openai'):
        base_endpoint = base_endpoint[:-7]
    
    # Format: https://{resource}.cognitiveservices.azure.com/openai/deployments/{deployment}/videos?api-version={version}
    create_url = f"{base_endpoint}/openai/v1/videos?api-version={api_version}"
    
    headers = {
        # "api-key": api_key,
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": deployment_name,  # Required: model/deployment name
        "prompt": prompt,
        "size": "1280x720",
        # "second": 8,
        # Note: duration/seconds might not be supported yet in preview
    }
    
    print(f"Creating video with URL: {create_url}")
    print(f"Payload: {payload}")
    
    # 4. Create video generation request
    response = requests.post(create_url, headers=headers, json=payload)
    
    if response.status_code != 200:
        raise Exception(f"Video creation failed: {response.status_code} - {response.text}")
    
    result = response.json()
    task_id = result.get("id")
    
    if not task_id:
        raise Exception(f"No task ID returned: {result}")
    
    print(f"Task created: {task_id}")
    
    # 5. Poll for completion
    retrieve_url = f"{base_endpoint}/openai/v1/videos/{task_id}?api-version={api_version}"
    
    poll_count = 0
    max_polls = 36  # 6 minutes max (36 * 10 seconds)
    
    while poll_count < max_polls:
        status_response = requests.get(retrieve_url, headers=headers)
        
        print(f"Checking status at: {retrieve_url}, Response code: {status_response.status_code}")
        
        if status_response.status_code != 200:
            raise Exception(f"Status check failed: {status_response.status_code} - {status_response.text}")
        
        status_data = status_response.json()
        status = status_data.get("status")
        
        print(f"Status: {status}")
        
        if status == "completed":
            # Video is ready - we need to download it using the content endpoint
            print(f"Video generation completed! ID: {task_id}")
            break
        elif status in ["failed", "cancelled"]:
            error_msg = status_data.get("error", "Unknown error")
            raise Exception(f"Video generation failed: {error_msg}")
        else:
            time.sleep(10)
            poll_count += 1
    
    if poll_count >= max_polls:
        raise Exception("Video generation timed out after 6 minutes")

    # 5. Download the video content
    # The video content is available at a separate endpoint
    content_url = f"{base_endpoint}/openai/v1/videos/{task_id}/content?api-version={api_version}"
    
    print(f"Downloading video from: {content_url}")
    
    video_response = requests.get(content_url, headers=headers)
    
    if video_response.status_code != 200:
        raise Exception(f"Video download failed: {video_response.status_code} - {video_response.text}")
    
    # 6. Save the video
    # Create videos directory if it doesn't exist
    videos_dir = Path("videos")
    videos_dir.mkdir(exist_ok=True)
    
    # Generate unique filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = videos_dir / f"skit_video_{timestamp}.mp4"

    # Save video content
    with open(output_path, "wb") as f:
        f.write(video_response.content)
    
    print(f"Video saved to: {output_path}")

    return str(output_path)

if __name__ == "__main__":
    query = "A serene beach at sunset with gentle waves and palm trees swaying in the breeze."
    video_path = createvideo(query)
    print(f"Video saved to: {video_path}")