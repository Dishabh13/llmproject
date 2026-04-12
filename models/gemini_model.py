def run_gemini(prompt, text, api_key, model_name):
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError(
            "The 'google-generativeai' package is not installed. "
            "Run: pip install google-generativeai"
        )

    genai.configure(api_key=api_key)

    model = genai.GenerativeModel(model_name)
    response = model.generate_content(prompt + "\n" + text)

    return response.text