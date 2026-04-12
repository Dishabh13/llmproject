def run_claude(prompt, text, api_key, model_name):
    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "The 'anthropic' package is not installed. "
            "Run: pip install anthropic"
        )

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model_name,
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt + "\n" + text}]
    )

    return response.content[0].text