from security_helper import get_api_key, load_config
from models.openai_model import run_openai
from models.gemini_model import run_gemini
from models.anthropic_model import run_claude
from models.groq_model import call_groq

def run_model(prompt, text):
    config = load_config()
    model_name = config["selected_model"]

    if "gpt" in model_name:
        api_key = get_api_key("openai")
        return run_openai(prompt, text, api_key, model_name)

    elif "gemini" in model_name:
        api_key = get_api_key("google")
        return run_gemini(prompt, text, api_key, model_name)

    elif "claude" in model_name:
        api_key = get_api_key("anthropic")
        return run_claude(prompt, text, api_key, model_name)

    elif "groq" in model_name:
        return call_groq(prompt)

    else:
        raise ValueError("Unsupported model")