from groq import Groq
from security_helper import get_api_key

def call_groq(prompt):
    """
    Calls the Groq API with a hardcoded model and retrieves the API key internally.
    """
    try:
        api_key = get_api_key("groq")
        if not api_key:
            raise ValueError("GROQ_API_KEY not found.")

        client = Groq(api_key=api_key)

        response = client.chat.completions.create(
            # Correct, active model from the definitive list.
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except ImportError:
        raise ImportError(
            "The 'groq' package is not installed. Run: pip install groq"
        )
    except Exception as e:
        print(f"An error occurred in call_groq: {e}")
        return None
