import asyncio
import base64
import os
from pathlib import Path

from agent_framework import ChatMessage, DataContent, Role, TextContent
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import AzureCliCredential
import streamlit as st
from PIL import Image
from io import BytesIO

async def test_image(img_base64: str, query: str) -> str:
    returntxt = ""
    """Test image analysis with Azure OpenAI."""
    # For authentication, run `az login` command in terminal or replace AzureCliCredential with preferred
    # authentication option. Requires AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_DEPLOYMENT_NAME
    # environment variables to be set.
    # Alternatively, you can pass deployment_name explicitly:
    # client = AzureOpenAIChatClient(credential=AzureCliCredential(), deployment_name="your-deployment-name")
    client = AzureOpenAIChatClient(credential=AzureCliCredential()
                                   , deployment_name=os.getenv("AZURE_OPENAI_RESPONSES_DEPLOYMENT_NAME")
                                   , endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
                                   , api_key=os.getenv("AZURE_OPENAI_KEY")
                                   )

    # image_uri = create_sample_image()
    image_path = "img/pneumonia_gallery1.jpeg"
    
    
    # image_path = Path("img/pnemonia_gallery1.jpg")
    
    with open(image_path, "rb") as f:
        encoded_bytes = base64.b64encode(f.read())
    
    base64_string = encoded_bytes.decode("utf-8")
    # print(base64_string)
    # image_uri = f"data:image/jpg;base64,{base64_string}"
    #data_uri = f"data:image/jpeg;base64,{base64_string}"
    data_uri = f"data:image/jpeg;base64,{img_base64}"

    message = ChatMessage(
        role=Role.USER,
        contents=[TextContent(text=query), DataContent(uri=data_uri, media_type="image/jpeg")],
    )

    response = await client.get_response(message)
    print(f"Image Response: {response}")
    # print('Client response JSON:', client.to_json())
    returntxt += f"Image Response: {response}\n"
    return returntxt


async def main() -> None:
    # Configure Streamlit page with Material Design 3 theme
    st.set_page_config(
        page_title="Radiology Report Generator",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    # print("=== Testing Azure OpenAI Multimodal ===")
    # print("Testing image analysis (supported by Chat Completions API)")
    # await test_image()
    st.title("Radiology Report Generator")

    prompt = st.chat_input("Enter your prompt for the radiology report:")
    if prompt:
        with st.spinner("Generating radiology report..."):
            with st.container(height=500):
                response_text = await test_image()
                st.markdown(response_text)
    

# if __name__ == "__main__":
#     asyncio.run(main())



async def run_app():
    # Configure page
    st.set_page_config(
        page_title="Radiology Image Analysis",
        page_icon="🏥",
        layout="wide"
    )

    st.title("🏥 Radiology Image Analysis")

    # Create columns with medium gap
    col1, col2 = st.columns(2, gap="medium")

    # Left column - Image upload and display
    with col1:
        st.subheader("📤 Upload Image")
        
        uploaded_file = st.file_uploader(
            "Choose a radiology image",
            type=["png", "jpg", "jpeg", "dcm", "tiff"],
            help="Upload X-ray, CT, MRI, or other medical images"
        )
        
        if uploaded_file is not None:
            # Display uploaded image in a container
            with st.container(border=True, height=400):
                st.markdown("### Uploaded Image")
                
                # Read and display the image
                if uploaded_file.type.startswith('image/'):
                    image = Image.open(uploaded_file)
                    st.image(image, use_container_width=True, caption=uploaded_file.name)
                    
                    # Show image details
                    st.caption(f"**Filename:** {uploaded_file.name}")
                    st.caption(f"**Size:** {uploaded_file.size / 1024:.2f} KB")
                    st.caption(f"**Dimensions:** {image.size[0]} x {image.size[1]} pixels")
                    
                    # Convert image to base64 for API calls (if needed)
                    buffered = BytesIO()
                    image.save(buffered, format="PNG")
                    img_base64 = base64.b64encode(buffered.getvalue()).decode()
                    
                    # Store in session state for later use
                    if 'uploaded_image' not in st.session_state:
                        st.session_state.uploaded_image = {}
                    
                    st.session_state.uploaded_image = {
                        'name': uploaded_file.name,
                        'image': image,
                        'base64': img_base64,
                        'size': uploaded_file.size
                    }
                else:
                    st.warning("⚠️ DICOM files require special processing. Please upload PNG/JPG for now.")
        else:
            with st.container(border=True):
                st.info("👆 Upload an image to begin analysis")

    # Right column - Analysis and Results
    with col2:
        st.subheader("🔍 Analysis & Results")

        # Input for analysis query
        analysis_query = st.text_area(
            "What would you like to know about this image?",
            placeholder="E.g., 'Identify any abnormalities', 'Analyze lung fields', 'Check for fractures'",
            height=100
        )
        
        with st.container(border=True, height=500):
            if uploaded_file is not None and 'uploaded_image' in st.session_state:
                # Analysis section
                st.markdown("### AI Analysis")
                
                
                
                # Analysis button
                if st.button("🚀 Run Analysis", type="primary", use_container_width=True):
                    with st.spinner("Analyzing image...", show_time=True):
                        # Your agent analysis code here
                        # Example placeholder:
                        if img_base64:
                            test_result = await test_image(img_base64, analysis_query)
                            # Display results
                            st.markdown("#### Findings:")
                            st.write("Analysis results will appear here...")
                            st.write(test_result)
                        st.success("✅ Analysis complete!")
                        
                        
                        
                        # You can call your agent here with the image
                        # result = await multi_agent_interaction(
                        #     query=analysis_query,
                        #     image_base64=st.session_state.uploaded_image['base64']
                        # )
                
                # Previous analyses (if any)
                if 'analysis_history' in st.session_state and st.session_state.analysis_history:
                    st.markdown("---")
                    st.markdown("#### Previous Analyses")
                    for i, analysis in enumerate(st.session_state.analysis_history[-3:]):
                        with st.expander(f"Analysis {i+1}: {analysis['query'][:50]}..."):
                            st.write(analysis['result'])
            else:
                st.info("Upload an image to start analysis")
                
                # Show example/instructions
                st.markdown("""
                **How to use:**
                1. Upload a radiology image on the left
                2. Enter your analysis question
                3. Click 'Run Analysis' to get AI-powered insights
                
                **Supported formats:**
                - X-rays (PNG, JPG, JPEG)
                - CT scans
                - MRI images
                - TIFF medical images
                """)

    # Footer
    st.markdown("---")
    st.caption("🏥 Radiology AI Assistant | Powered by Azure AI")

if __name__ == "__main__":
    # run_app()
    asyncio.run(run_app())