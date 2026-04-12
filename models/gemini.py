import google.generativeai as genai

genai.configure(api_key="YOUR_API_KEY")
MODEL_NAME = "models/gemini-2.5-flash"   
def clean_json(text):
    # Remove markdown formatting
    if "```" in text:
        text = text.replace("```json", "").replace("```", "")
    return text.strip()

def call_gemini(prompt):
    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content(prompt)
    return clean_json(response.text)