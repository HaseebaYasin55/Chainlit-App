"""
app.py
======
A minimal, beginner-friendly Chainlit chatbot.

This app demonstrates the two core Chainlit decorators:

    @cl.on_chat_start  -> runs once, when a new chat session begins
    @cl.on_message      -> runs every time the user sends a message

Text conversation is powered by the Gemini free API.
Image generation is powered by FLUX.1-schnell via Hugging Face's free
Inference Providers API.

The routing logic is simple:
    - If the user's message looks like an image request
      ("generate an image of...", "draw...", "create a picture of...")
      -> call FLUX.1-schnell and display the image.
    - Otherwise
      -> send the message to Gemini and stream back a text answer.
"""

import os
import re
import tempfile

import chainlit as cl
from dotenv import load_dotenv
from google import genai
from huggingface_hub import InferenceClient

# ---------------------------------------------------------------------------
# 1. Configuration
# ---------------------------------------------------------------------------
# Load environment variables from a local .env file (see .env.example).
# We point load_dotenv() at the .env file next to THIS script explicitly,
# rather than relying on it to guess the current working directory --
# on some setups (e.g. Chainlit's --port / --watch reloader on Windows)
# the process's working directory isn't what you'd expect, which is a
# common reason HF_TOKEN / GEMINI_API_KEY appear "missing" even though
# the .env file exists.
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=ENV_PATH)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError(
        f"GEMINI_API_KEY is missing. Expected to find it in: {ENV_PATH}\n"
        "Copy .env.example to .env (same folder as app.py) and add your key."
    )

# Create the Gemini client once, at import time.
genai_client = genai.Client(api_key=GEMINI_API_KEY)

# "gemini-3.5-flash" is Google's current fast, free-tier-friendly model.
# Swap the model name here if you'd like to try a different Gemini model
# (run `for m in genai_client.models.list(): print(m.name)` to see options).
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

HF_TOKEN = os.getenv("HF_TOKEN")

if not HF_TOKEN:
    raise RuntimeError(
        f"HF_TOKEN is missing. Expected to find it in: {ENV_PATH}\n"
        "Copy .env.example to .env (same folder as app.py) and add your free "
        "Hugging Face token from https://huggingface.co/settings/tokens"
    )

# FLUX.1-schnell is Black Forest Labs' free, open-weight image model,
# served through Hugging Face's free Inference Providers API.
hf_client = InferenceClient(api_key=HF_TOKEN)
FLUX_MODEL_NAME = "black-forest-labs/FLUX.1-schnell"

# ---------------------------------------------------------------------------
# 1b. Chat history (sidebar "Previous Chats")
# ---------------------------------------------------------------------------
# Chainlit can list past conversations in the sidebar -- each one titled
# with a short heading taken from its first message -- but only if a "data
# layer" is registered to store them somewhere. We use a local SQLite file
# so nothing extra needs to be installed or hosted to get this working.
#
# If this fails to initialize for any reason (e.g. missing sqlalchemy /
# aiosqlite packages), the app falls back to running without history
# instead of crashing.
try:
    from chainlit.data.sql_alchemy import SQLAlchemyDataLayer

    CHAT_HISTORY_DB_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "chainlit.db"
    )

    @cl.data_layer
    def get_data_layer():
        return SQLAlchemyDataLayer(
            conninfo=f"sqlite+aiosqlite:///{CHAT_HISTORY_DB_PATH}"
        )

except Exception as data_layer_error:  # noqa: BLE001
    print(f"[chat history] persistence disabled: {data_layer_error}")


# A small set of trigger phrases used to detect an "image request".
# This keeps the routing logic simple and transparent (no extra ML/NLP).
IMAGE_TRIGGERS = [
    r"\bgenerate\s+(an?\s+)?image\b",
    r"\bcreate\s+(an?\s+)?image\b",
    r"\bmake\s+(an?\s+)?image\b",
    r"\bdraw\b",
    r"\bpicture\s+of\b",
    r"\bimage\s+of\b",
    r"\bpaint\b",
]


def is_image_request(text: str) -> bool:
    """Return True if the user's message looks like an image generation request."""
    text_lower = text.lower()
    return any(re.search(pattern, text_lower) for pattern in IMAGE_TRIGGERS)


def extract_image_prompt(text: str) -> str:
    """
    Strip common trigger phrases from the message so only the descriptive
    part is sent to FLUX.1 as the image prompt.

    Example:
        "Generate an image of a futuristic city" -> "a futuristic city"
    """
    cleaned = text
    for pattern in IMAGE_TRIGGERS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    # Remove leftover connector words like "of" at the start.
    cleaned = re.sub(r"^\s*(of|for|showing)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" .!?")
    return cleaned if cleaned else text.strip()


# ---------------------------------------------------------------------------
# 2. @cl.on_chat_start
# ---------------------------------------------------------------------------
# Chainlit calls any function decorated with @cl.on_chat_start exactly once,
# right when a user opens a new chat session. It's the natural place to
# send a welcome message or set up per-session state (via cl.user_session).
@cl.on_chat_start
async def start_chat():
    """Runs once per new chat session."""
    chat_session = genai_client.chats.create(model=GEMINI_MODEL_NAME)
    cl.user_session.set("gemini_chat", chat_session)

    # Minimal imagineAI landing/welcome screen.
    robot_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "public",
        "robot.png"
    )
    
    robot = cl.Image(
        path=robot_path,
        name="imagineAI",
        display="inline"
    )

    await cl.Message(
        content=(
            "## imagineAI\n\n"
            "Welcome to imagineAI! Describe your vision and I'll create an image.\n\n"
            "Try typing: \"A futuristic city skyline at sunset with flying vehicles in cyberpunk style\""
        ),
        elements=[robot],
    ).send()

# ---------------------------------------------------------------------------
# 2b. @cl.on_chat_resume
# ---------------------------------------------------------------------------
# Chainlit calls this instead of @cl.on_chat_start when a user reopens a
# saved conversation from the sidebar. The Gemini chat object from
# @cl.on_chat_start lived only in memory, so it's gone -- we rebuild it here
# and replay the saved turns as context, so the conversation can continue
# naturally instead of erroring out or losing context.
@cl.on_chat_resume
async def resume_chat(thread: dict):
    """Runs when a user reopens a past conversation from the sidebar."""
    history = []
    for step in thread.get("steps", []):
        role = "user" if step.get("type") == "user_message" else None
        role = role or ("model" if step.get("type") == "assistant_message" else None)
        text = step.get("output") or step.get("content")
        if role and text:
            history.append({"role": role, "parts": [{"text": text}]})

    try:
        chat_session = genai_client.chats.create(
            model=GEMINI_MODEL_NAME, history=history
        )
    except Exception:  # noqa: BLE001 - fall back to a fresh session
        chat_session = genai_client.chats.create(model=GEMINI_MODEL_NAME)

    cl.user_session.set("gemini_chat", chat_session)


# ---------------------------------------------------------------------------
# 3. @cl.on_message
# ---------------------------------------------------------------------------
# Chainlit calls any function decorated with @cl.on_message every time the
# user sends a new message. Chainlit "routes" the incoming message event to
# this function automatically — that's the whole point of the decorator:
# it registers this function as the handler for the "message" event, so you
# never have to write your own event loop or web server code.
@cl.on_message
async def handle_message(message: cl.Message):
    """Runs every time the user sends a message."""
    user_text = message.content

    if is_image_request(user_text):
        await handle_image_request(user_text)
    else:
        await handle_text_request(user_text)


# ---------------------------------------------------------------------------
# 4. Image generation via FLUX.1-schnell (Hugging Face)
# ---------------------------------------------------------------------------
async def handle_image_request(user_text: str):
    """Generate an image with FLUX.1-schnell and display it in the chat."""
    prompt = extract_image_prompt(user_text)

    # Send a single message and then update it in place once the image is
    # ready, so the user only ever sees one assistant bubble for this
    # request (a "generating..." bubble that turns into the image bubble),
    # instead of a "generating" message followed by a separate result card.
    thinking_msg = cl.Message(content=f"Generating the image ...")
    await thinking_msg.send()

    try:
        # text_to_image returns a PIL.Image object.
        pil_image = await cl.make_async(hf_client.text_to_image)(
            prompt, model=FLUX_MODEL_NAME
        )
    except Exception as error:  # noqa: BLE001 - surface any API error to the user
        thinking_msg.content = f"Sorry, image generation failed: {error}"
        await thinking_msg.update()
        return

    # Save the image locally so Chainlit can display it inline.
    # tempfile.gettempdir() resolves to the right temp folder on any OS
    # (/tmp on Linux/Mac, C:\Users\<you>\AppData\Local\Temp on Windows) --
    # a hardcoded "/tmp/..." path only works on Linux/Mac.
    safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", prompt)[:40] or "image"
    image_path = os.path.join(tempfile.gettempdir(), f"{safe_name}.png")
    pil_image.save(image_path)

    # display="inline" plus referencing the element's name in the message
    # content renders the image directly inside this same chat bubble
    # (right where the reference is) rather than as a separate element
    # card below the text. Clicking the image still lets the user open
    # or save it full-size, so a separate download element isn't needed.
    image_element = cl.Image(path=image_path, name=prompt, display="inline")

    thinking_msg.content = f"Here's your generated image:"
    thinking_msg.elements = [image_element]
    await thinking_msg.update()


# ---------------------------------------------------------------------------
# 5. Text conversation via Gemini
# ---------------------------------------------------------------------------
async def handle_text_request(user_text: str):
    """Send the user's message to Gemini and stream the response back."""
    chat_session = cl.user_session.get("gemini_chat")

    response_msg = cl.Message(content="")
    await response_msg.send()

    try:
        # send_message_stream yields chunks of text as they're generated.
        stream = chat_session.send_message_stream(user_text)
        for chunk in stream:
            if chunk.text:
                await response_msg.stream_token(chunk.text)
    except Exception as error:  # noqa: BLE001 - surface any API error to the user
        response_msg.content = f"Sorry, something went wrong: {error}"

    await response_msg.update()