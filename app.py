import os
import re
import tempfile

import chainlit as cl
from dotenv import load_dotenv
from google import genai
from huggingface_hub import InferenceClient

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=ENV_PATH)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError(
        f"GEMINI_API_KEY is missing. Expected to find it in: {ENV_PATH}\n"
        "Copy .env.example to .env (same folder as app.py) and add your key."
    )

genai_client = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")

HF_TOKEN = os.getenv("HF_TOKEN")

if not HF_TOKEN:
    raise RuntimeError(
        f"HF_TOKEN is missing. Expected to find it in: {ENV_PATH}\n"
        "Copy .env.example to .env (same folder as app.py) and add your free "
        "Hugging Face token from https://huggingface.co/settings/tokens"
    )


hf_client = InferenceClient(api_key=HF_TOKEN)
FLUX_MODEL_NAME = "black-forest-labs/FLUX.1-schnell"


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


@cl.on_message
async def handle_message(message: cl.Message):
    """Runs every time the user sends a message."""
    user_text = message.content

    if is_image_request(user_text):
        await handle_image_request(user_text)
    else:
        await handle_text_request(user_text)

async def handle_image_request(user_text: str):
    """Generate an image with FLUX.1-schnell and display it in the chat."""
    prompt = extract_image_prompt(user_text)
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
    safe_name = re.sub(r"[^a-zA-Z0-9]+", "_", prompt)[:40] or "image"
    image_path = os.path.join(tempfile.gettempdir(), f"{safe_name}.png")
    pil_image.save(image_path)

    image_element = cl.Image(path=image_path, name=prompt, display="inline")

    thinking_msg.content = f"Here's your generated image:"
    thinking_msg.elements = [image_element]
    await thinking_msg.update()

#text conversation with gemini
async def handle_text_request(user_text: str):
    """Send the user's message to Gemini and stream the response back."""
    chat_session = cl.user_session.get("gemini_chat")

    response_msg = cl.Message(content="")
    await response_msg.send()

    try:
        stream = chat_session.send_message_stream(user_text)
        for chunk in stream:
            if chunk.text:
                await response_msg.stream_token(chunk.text)
    except Exception as error: 
        response_msg.content = f"Sorry, something went wrong: {error}"

    await response_msg.update()