import os
import sys
import asyncio
from flask import Flask, request, redirect, url_for, session, jsonify, render_template, flash
from functools import wraps
import requests as http
from middlewares.middleware import AuthMiddleware
from utils.errors import ErrorHelper
from flask_wtf import CSRFProtect
from flask_cors import CORS
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv

from browser_use import Agent, Browser, BrowserConfig
from browser_use.browser.context import (
    BrowserContext,
    BrowserContextConfig,
    BrowserContextWindowSize,
)
from browser_use.agent.service import Agent

API_URL = "http://31.57.224.118:8011/api/v1"

# Load environment variables
load_dotenv()
if not os.getenv('GOOGLE_API_KEY'):
    raise ValueError('GOOGLE_API_KEY is not set. Please add it to your environment variables.')

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY') or 'your_secret_key'
csrf = CSRFProtect(app)
CORS(app, resources={r"/*": {"origins": "*"}}, methods=["GET", "POST", "PUT", "DELETE"])

# Middleware untuk memastikan user sudah login
auth = AuthMiddleware()

# Registrasi handler error
# errorHelper = ErrorHelper()
# @app.errorhandler(404)
# def not_found_error(error):
#     return errorHelper.not_found_error(error=error)

# @app.errorhandler(500)
# def internal_error(error):
#     return errorHelper.internal_error(error=error)

# @app.errorhandler(405)
# def method_not_allowed(error):
#     return errorHelper.method_not_allowed(error=error)

# @app.errorhandler(400)
# def bad_request(error):
#     return errorHelper.bad_request(error=error)

async def run_agents(data):
    # Initialize chat model with gemini 2.0 flash
    model = ChatGoogleGenerativeAI(model=data.get('model'))

    browser_context = BrowserContextConfig(
        no_viewport=False,
        browser_window_size=BrowserContextWindowSize(
            width=int(data.get('browser_width', 1920)),
            height=int(data.get('browser_height', 1080))
        )
    )

    browser = Browser(config=BrowserConfig(
        headless=data.get('headless_mode', False),
        disable_security=data.get('disable_security', True),
        # cdp_url=data.get('cdp_url') or None,
        # chrome_instance_path=data.get('chrome_instance_path'),
        # chrome_instance_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        # extra_chromium_args=[
        #     '--user-data-dir=/Users/mochammadhairullah/Library/Application Support/Google/Chrome',  # Ganti dengan path ke user data yang benar
        #     '--profile-directory=Profile 1', # Tentukan profil yang benar
        #     f'--window-size={data.get("browser_width")},{data.get("browser_height")}',
        # ]
    ))

    context = BrowserContext(browser=browser, config=browser_context)

    # Run agents
    agent = Agent(
        task=data.get('task'),
        llm=model,
        use_vision=data.get('use_vision', True),
        browser_context=context,
        max_actions_per_step=data.get('max_actions_per_step'),
        max_input_tokens=data.get('max_input_tokens'),
    )

    await agent.run(max_steps=int(data.get('max_steps', 10)))
    return "Task completed"

@app.route('/login', methods=['GET', 'POST'])
@auth.unauthorized
def login():
    if request.method == 'POST':
        data = request.form
        email = data.get('email')
        password = data.get('password')

        headers = {"Content-Type": "application/json"}
        payload = json.dumps({"email": email, "password": password})

        # Authenticate user with the API
        response = http.post(f"{API_URL}/auth/login", headers=headers, data=payload)
        print(response.json())
        if response.status_code == 200:
            user = response.json()
            session['user'] = user
            return redirect(url_for('index'))
        else:
            # get detail or message from the response
            flash(response.json().get('message') or response.json().get('detail'), 'red')
            return redirect(url_for('login'))
    return render_template('auth/login.html')

@app.route('/register', methods=['GET', 'POST'])
@auth.unauthorized
def register():
    if request.method == 'POST':
        data = request.form
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')
        confirm_password = data.get('confirm_password')

        if password != confirm_password:
            flash("Passwords doesn't match", 'red')
            return redirect(url_for('register'))

        headers = {"Content-Type": "application/json"}
        payload = json.dumps({"name": name, "email": email, "password": password})

        # Register user with the API
        response = http.post(f"{API_URL}/auth/register", headers=headers, data=payload)
        if response.status_code == 201:
            user = response.json()
            # to login the user after registration
            flash("Registration successful. Please login", 'green')
            return redirect(url_for('login'))
        else:
            # get detail or message from the response
            flash(response.json().get('message') or response.json().get('detail'), 'red')
            return redirect(url_for('register'))
    return render_template('auth/register.html')

@app.route('/')
@auth.authorized
def index():
    return render_template('pages/index.html')

@app.route('/logout', methods=['POST'])
@auth.authorized
def logout():
    if 'user' in session:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {
                session['user']['data']['access_token'] if 'user' in session else ''
            }"
        }

        response = http.post(f"{API_URL}/auth/logout", headers=headers)
        print(response.json())
        if response.status_code == 200:
            session.pop('user', None)
            flash("You have been logged out", 'green')
            return redirect(url_for('login'))
        else:
            flash("Failed to logout", 'red')
            return redirect(url_for('index'))

@app.route('/run_task', methods=['POST'])
@auth.authorized
def run_task():
    data = request.get_json()

    if not data:
        return jsonify({"message": "Invalid request"})

    # Run agents asynchronously
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(run_agents(data))

    return jsonify({"message": result})

# stop Agent
@app.route('/stop_agent', methods=['POST'])
@auth.authorized
def stop_agent():
    data = request.get_json()

    if not data:
        return jsonify({"message": "Invalid request"})

    # Stop agents
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    result = loop.run_until_complete(stop_agents(data))

    return jsonify({"message": result})

if __name__ == "__main__":
    app.run(debug=True)
