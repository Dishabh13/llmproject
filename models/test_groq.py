
import sys
import os

# Fix the Python path to allow imports from the root directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from groq import Groq
from security_helper import get_api_key

# Get the API key using our secure method
api_key = get_api_key("groq")

if not api_key:
    print("Could not retrieve Groq API key. Please save it in the config panel.")
    exit()

client = Groq(api_key=api_key)

print("Fetching available Groq models...")
models = client.models.list()

print("Available Models:")
for m in models.data:
    if m.active:
      print(m.id)
