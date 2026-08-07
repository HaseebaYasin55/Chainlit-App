# imagineAI

A minimal, custom-branded Chainlit chatbot that talks like an assistant and paints like an artist — conversational text powered by **Google Gemini**, image generation powered by **FLUX.1-schnell** (via Hugging Face's free Inference Providers API).

## ✨ Features

-  **Conversational chat** — streamed responses from Gemini, with full multi-turn context per session
-  **Text-to-image generation** — just ask ("generate an image of...", "draw...", "a picture of...", "paint...") and it's routed automatically to FLUX.1-schnell
-  **One-click image download** — a download button is injected next to every generated image, alongside the existing copy/feedback actions
-  **Fully custom UI** — a branded welcome screen, warm color palette, and cleaned-up header (no default Chainlit/README/theme-toggle clutter), built on top of Chainlit's Shadcn/Tailwind frontend

## 🧰 Tech Stack

| Layer | Technology |
|---|---|
| App framework | [Chainlit](https://docs.chainlit.io/) (async Python) |
| Text generation | Google Gemini API (`google-genai`) |
| Image generation | FLUX.1-schnell via `huggingface_hub.InferenceClient` |
| Chat history | SQLite + SQLAlchemy (`chainlit.data.sql_alchemy`) |
| UI theming | `config.toml`, `theme.json`, `custom.css`, `custom.js` |

## 📁 Project Structure

```
.
├── app.py               # Core app: chat routing, Gemini streaming, FLUX image generation
├── config.toml          # Chainlit runtime + UI configuration
├── theme.json           # Color palette (CSS custom properties)
├── public/
│   ├── custom.css       # Custom styling — hero/welcome screen, buttons, scroll behavior
│   ├── custom.js 
|   └── robot.png        # Welcome screen mascot                
└── .env                 # Local API keys (not committed — see below)
```

## ✅ Prerequisites

- Python 3.10+
- A free **Gemini API key** → https://aistudio.google.com/apikey
- A free **Hugging Face access token** → https://huggingface.co/settings/tokens

## 🚀 Getting Started

**1. Clone the repository**
```bash
git clone https://github.com/<your-username>/<repo-name>.git
cd <repo-name>
```

**2. Create a virtual environment**
```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
```

**3. Install dependencies**
```bash
pip install -r requirements.txt
```

**4. Configure environment variables**

Create a `.env` file in the project root (same folder as `app.py`):
```env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-3.5-flash   # optional — defaults to gemini-3.5-flash
HF_TOKEN=your_huggingface_token
```

**5. Run the app**
```bash
chainlit run app.py -w
```
Then open **http://localhost:8000** in your browser. The `-w` flag enables auto-reload on file changes.

## 💬 Usage

- Send a normal message → routed to **Gemini**, streamed back token-by-token.
- Send something like *"generate an image of a futuristic city at sunset"* → routed to **FLUX.1-schnell**, and the generated image appears inline with a download button.
- Reopen a past conversation from the sidebar to resume it with full context.

## 🎨 Customization

| File | Purpose |
|---|---|
| `config.toml` | Chainlit UI + feature toggles (theme, file uploads, header links, etc.) |
| `theme.json` | Light-mode color variables used throughout the custom CSS |
| `public/custom.css` | Welcome screen layout, message bubbles, composer, scrollbar |
| `public/custom.js` | Removes default Chainlit branding/README/theme buttons, reorders the welcome hero, and injects the image download button |

## ☁️ Live Link

You can view the deployed app from here [imagineAI](https://chainlit-app-production.up.railway.app/)

---

## Author

**Haseeba Yasin**

If you found this project helpful, feel free to ⭐ the repository.
