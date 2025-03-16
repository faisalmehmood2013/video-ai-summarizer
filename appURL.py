from flask import Flask, render_template, request
from phi.agent import Agent
from phi.model.google import Gemini
from phi.tools.duckduckgo import DuckDuckGo
from phi.tools.youtube_tools import YouTubeTools
from google.generativeai import upload_file, get_file
import google.generativeai as genai
import os
import time
import markdown
import json
from pathlib import Path
from dotenv import load_dotenv
from urllib.parse import urlencode
from urllib.request import urlopen
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
import yt_dlp
import requests

# Load environment variables
load_dotenv()

# Configure Google Gemini API
API_KEY = os.getenv("GOOGLE_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)

# Initialize Flask App
app = Flask(__name__)

# Upload Folder Setup
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def get_youtube_video_id(url: str) -> str:
    """Extracts the video ID from a YouTube URL."""
    if "youtube.com" in url:
        return url.split("v=")[-1].split("&")[0]
    elif "youtu.be" in url:
        return url.split("/")[-1].split("?")[0]
    return None


def get_youtube_video_data(url: str) -> dict:
    """Fetches metadata from a YouTube URL using YouTube oEmbed API."""
    if not url:
        return {"error": "No URL provided"}

    try:
        video_id = get_youtube_video_id(url)
        if not video_id:
            return {"error": "Invalid YouTube URL"}

        params = {"format": "json", "url": f"https://www.youtube.com/watch?v={video_id}"}
        request_url = "https://www.youtube.com/oembed?" + urlencode(params)

        with urlopen(request_url) as response:
            video_data = json.loads(response.read().decode())
            return {
                "title": video_data.get("title"),
                "author_name": video_data.get("author_name"),
                "author_url": video_data.get("author_url"),
                "thumbnail_url": video_data.get("thumbnail_url"),
                "video_url": f"https://www.youtube.com/embed/{video_id}"
            }
    except Exception as e:
        return {"error": f"Error getting video data: {e}"}


def get_video_timestamps(url: str) -> str:
    """Generate timestamps for a YouTube video based on captions."""
    if not url:
        return "No URL provided"

    try:
        video_id = get_youtube_video_id(url)
        if not video_id:
            return "Invalid YouTube URL"

        try:
            # Fetch captions using YouTubeTranscriptApi
            captions = YouTubeTranscriptApi.get_transcript(video_id, languages=["en"])
            timestamps = []
            for line in captions:
                start = int(line["start"])
                minutes, seconds = divmod(start, 60)
                timestamps.append(f"{minutes}:{seconds:02d} - {line['text']}")
            return "\n".join(timestamps)

        except (TranscriptsDisabled, NoTranscriptFound, VideoUnavailable):
            # Backup method using yt-dlp
            ydl_opts = {
                'skip_download': True,
                'writeautomaticsub': True,
                'subtitleslangs': ['en'],
                'quiet': True
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=False)
                subtitles = info_dict.get('automatic_captions', {}).get('en') or \
                            info_dict.get('subtitles', {}).get('en')

                if subtitles:
                    sub_url = subtitles[-1]['url']
                    response = requests.get(sub_url)
                    if response.status_code == 200:
                        return response.text  # Returns raw caption text
                    else:
                        return "Could not fetch captions from YouTube."

        return "No captions found for this video."

    except Exception as e:
        return f"Error generating timestamps: {e}"


# Initialize AI Agent
def initialize_agent():
    agent = Agent(
        name="Video AI Summarizer",
        model=Gemini(id="gemini-2.0-flash-exp"),
        tools=[DuckDuckGo(), YouTubeTools()],
        verbose=True,
        markdown=True,
    )
    return agent


multimodal_Agent = initialize_agent()


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        user_query = request.form.get("query", "").strip()
        youtube_link = request.form.get("video_url", "").strip()
        video = request.files.get('video')

        if not user_query:
            return "Please provide a query."

        try:
            if youtube_link:
                video_data = get_youtube_video_data(youtube_link)
                if "error" in video_data:
                    return video_data["error"]

                # Extract timestamps & captions from the YouTube video
                timestamps = get_video_timestamps(youtube_link)

                # AI Analysis Prompt
                analysis_prompt = f"""
                You are an expert video content analyst. Carefully analyze the uploaded video:  
                **Title:** "{video_data['title']}"  
                **Creator:** {video_data['author_name']}  

                ### Task:  
                - Extract key points, themes, and insights.  
                - Identify important topics, conversations, and visual elements.  
                - Analyze the video content and provide a response based on the following user query:  
                **User Query:** {user_query}  
                - Supplement insights with relevant web research where necessary.  

                ### Response Guidelines:  
                1. **Accuracy:** Ensure the response is entirely based on the video’s content.  
                2. **Detail:** Provide structured insights with key takeaways.  
                3. **Clarity:** Keep it clear, user-friendly, and easy to understand.  
                4. **Actionability:** Offer meaningful conclusions or recommendations.  

                ### Additional Requirement:  
                - Summarize the video concisely yet informatively, highlighting its core message, key moments, and relevant observations.  
                """


                
                response = multimodal_Agent.run(analysis_prompt, tools=[YouTubeTools()])
                paragraph = markdown.markdown(response.content)

                return render_template("index.html", youtube_data=video_data, paragraph=paragraph)

            elif video and video.filename:
                # Process uploaded video
                video_path = os.path.join(app.config['UPLOAD_FOLDER'], video.filename)
                video.save(video_path)

                processed_video = upload_file(video_path)
                while processed_video.state.name == "PROCESSING":
                    time.sleep(1)
                    processed_video = get_file(processed_video.name)

                analysis_prompt = f"""
                 You are an expert video content analyst. Carefully analyze the uploaded video, 
                extracting key points, themes, and insights. Identify important topics, conversations, and visual elements. 
                Based on the video content, respond to the following user query and supplementary web research: {user_query}.

                Ensure your response is:

                Accurate and based entirely on the video’s content.
                Detailed with key takeaways and structured insights.
                Clear & user-friendly, making it easy to understand.
                Actionable, providing meaningful conclusions or recommendations.
                Additionally, summarize the video in a concise yet informative way, highlighting its core message, key moments, and any relevant observations.
                """
                
                response = multimodal_Agent.run(analysis_prompt, videos=[processed_video])
                paragraph = markdown.markdown(response.content)

                return render_template("index.html", video_url=video_path, paragraph=paragraph)

        except Exception as e:
            return f"Error processing video: {e}"

    return render_template("index.html", youtube_data=None, video_url=None, paragraph=None)


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')

        # Process or store the form data here (e.g., save to a database or send an email)
        print(f"New Contact Message: {name}, {email}, {message}")

        return render_template('contact.html', success=True)  # Show success message

    return render_template('contact.html', success=False)


if __name__ == '__main__':
    app.run(debug=True)
