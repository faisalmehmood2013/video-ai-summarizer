# 1. Flask: Framework for web applications
# 🔹 render_template: Renders HTML templates.
# 🔹 request: Handles form input and file uploads.
from flask import Flask, render_template, request, redirect  

# 2. Phi Modules (AI Processing)
# 🔹 Agent: The AI agent that processes video and queries.
from phi.agent import Agent

# 🔹 Gemini: Google Gemini 2.0 Flash model.
from phi.model.google import Gemini

# 🔹 DuckDuckGo: Enables web-based search for additional research.
from phi.tools.duckduckgo import DuckDuckGo

# 3. Google Generative AI
# 🔹 upload_file: Uploads video files to Google AI for analysis.
# 🔹 get_file: Retrieves processed files from Google AI.
# 🔹 genai: Configures Google AI API.
from google.generativeai import upload_file, get_file
import google.generativeai as genai

# 4. Other Modules
# Import Markdown in Flask App
import markdown
# 🔹 os: Manages file paths.
import os

# 🔹 time: Pauses execution while waiting for video processing.
import time

# 🔹 Path: Handles file deletion.
from pathlib import Path

# 🔹 dotenv: Loads environment variables from a .env file.
from dotenv import load_dotenv

# 🔹 Load environment variables
load_dotenv()

# 🔹 Configure Google Gemini API
API_KEY = os.getenv("GOOGLE_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)

# 🔹 Initialize Flask App
app = Flask(__name__)
# Creates a folder (static/uploads) to store uploaded videos.
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 🔹 Initialize AI Agent
def initialize_agent():
    agent = Agent(
        name="Video AI Summarizer",
        model=Gemini(id="gemini-2.0-flash-exp"),
        tools=[DuckDuckGo()],
        markdown=True,
    )
    return agent

multimodal_Agent = initialize_agent()

@app.route('/', methods=['GET', 'POST'])

def index():
    if request.method == 'POST':
        # 🔹 Check if file is uploaded
        if 'video' not in request.files:
            return redirect(request.url)

        video = request.files['video']
        user_query = request.form.get("query", "")

        if video.filename == "" or not user_query:
            return "Please upload a video and provide a query."

        # 🔹 Save the uploaded video
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], video.filename)
        video.save(video_path)

        try:
            # 🔹 Upload and process video
            processed_video = upload_file(video_path)
            while processed_video.state.name == "PROCESSING":
                time.sleep(1)
                processed_video = get_file(processed_video.name)

            # 🔹 AI Analysis Prompt
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

            # 🔹 Get AI Response
            response = multimodal_Agent.run(analysis_prompt, videos=[processed_video])
            paragraph = markdown.markdown(response.content)

            return render_template("index.html", video_url=video_path, paragraph=paragraph)

        except Exception as e:
            return f"Error processing video: {e}"
        finally:
            Path(video_path).unlink(missing_ok=True)

    return render_template("index.html", video_url=None, paragraph=None)

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        message = request.form.get('message')

        # You can process/store the form data here (e.g., save to a database or send an email)
        print(f"New Contact Message: {name}, {email}, {message}")

        return render_template('contact.html', success=True)  # Show success message

    return render_template('contact.html', success=False)


if __name__ == '__main__':
    app.run(debug=True)
