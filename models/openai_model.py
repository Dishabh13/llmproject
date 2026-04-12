from openai import OpenAI

def run_openai(prompt, text, api_key, model_name):
    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ]
    )

    return response.choices[0].message.content