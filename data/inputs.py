import pandas as pd

# Change this value when needed
DEBUG_LIMIT = 5  # set to None for full dataset


def load_inputs():
    df = pd.read_excel("data/dataset.xlsx")

    inputs = []

    for i, row in df.iterrows():
        text = str(row["Text"]) if pd.notna(row["Text"]) else ""

        inputs.append({
            "input_id": f"case_{i+1:03d}",
            "text": text
        })

    # ALWAYS enforce debug limit here
    if DEBUG_LIMIT is not None:
        inputs = inputs[:DEBUG_LIMIT]

    return inputs


# This is what other files will import
inputs = load_inputs()


# Debug check
if __name__ == "__main__":
    print("DEBUG LIMIT:", DEBUG_LIMIT)
    print("Total inputs loaded:", len(inputs))

    for i in range(min(5, len(inputs))):
        print(inputs[i])