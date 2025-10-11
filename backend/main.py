import os
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
from dotenv import load_dotenv
from datetime import datetime, timezone

# --- FIX 1: Simplified and moved load_dotenv() to the top ---
# This reliably loads the .env file from the current directory.
load_dotenv()

app = FastAPI()

# --- Configuration ---
# Now, these should load correctly.
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
# --- FIX 2: Corrected the variable name inside getenv() ---
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

# This must match the URI in your Google Cloud Console
REDIRECT_URI = "http://localhost:8000/auth/google/callback" 
# The URL of our React frontend
FRONTEND_URL = "http://localhost:5173" 

# --- Added print statements for you to verify the fix ---
print(f"LOADED GOOGLE_CLIENT_ID: {GOOGLE_CLIENT_ID}")
print(f"LOADED GOOGLE_CLIENT_SECRET: {'*' * 8 if GOOGLE_CLIENT_SECRET else None}") # Hide secret for safety
# --------------------------------------------------------

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for the access token (for demonstration)
user_access_token = None

# --- API Routes ---

@app.get("/")
def read_root():
    return {"message": "Fitness API Backend is running."}

@app.get("/login")
def login_google():
    """
    Redirects the user to Google's OAuth 2.0 consent screen.
    """
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"scope=https://www.googleapis.com/auth/fitness.activity.read&"
        f"include_granted_scopes=true&"
        f"response_type=code&"
        f"redirect_uri={REDIRECT_URI}&"
        f"client_id={GOOGLE_CLIENT_ID}"
    )
    return RedirectResponse(url=auth_url)

@app.get("/auth/google/callback")
async def auth_google_callback(request: Request):
    """
    Handles the callback from Google. Exchanges the authorization code
    for an access token.
    """
    global user_access_token
    code = request.query_params.get('code')
    if not code:
        return RedirectResponse(url=f"{FRONTEND_URL}/login-failed")

    token_url = "https://oauth2.googleapis.com/token"
    token_data = {
        "code": code,
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(token_url, data=token_data)
            response.raise_for_status()
            token_json = response.json()
            user_access_token = token_json.get("access_token")
            return RedirectResponse(url=f"{FRONTEND_URL}/dashboard")
        except httpx.HTTPStatusError as e:
            print(f"Error exchanging code for token: {e.response.text}")
            return RedirectResponse(url=f"{FRONTEND_URL}/login-failed")

@app.get("/get-steps")
async def get_steps():
    """
    Fetches the user's step count from the Google Fit API.
    """
    global user_access_token
    if not user_access_token:
        return {"error": "Not authenticated"}, 401

    api_url = "https://www.googleapis.com/fitness/v1/users/me/dataset:aggregate"
    headers = {"Authorization": f"Bearer {user_access_token}"}
    
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    startTimeMillis = int(today.timestamp() * 1000)
    endTimeMillis = int(datetime.now(timezone.utc).timestamp() * 1000)

    request_body = {
        "aggregateBy": [{
            "dataTypeName": "com.google.step_count.delta",
            "dataSourceId": "derived:com.google.step_count.delta:com.google.android.gms:estimated_steps"
        }],
        "bucketByTime": {"durationMillis": 86400000},
        "startTimeMillis": startTimeMillis,
        "endTimeMillis": endTimeMillis
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(api_url, headers=headers, json=request_body)
            response.raise_for_status()
            data = response.json()
            steps = 0
            if data.get("bucket"):
                bucket = data["bucket"][0]
                if bucket.get("dataset"):
                    dataset = bucket["dataset"][0]
                    if dataset.get("point"):
                        point = dataset["point"][0]
                        if point.get("value"):
                            value = point["value"][0]
                            steps = value.get("intVal", 0)
            return {"steps": steps}
        except httpx.HTTPStatusError as e:
            print(f"Error fetching steps: {e.response.text}")
            return {"error": "Failed to fetch steps from Google Fit."}, 500

