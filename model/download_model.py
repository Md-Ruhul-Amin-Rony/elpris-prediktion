import os
import pickle

from huggingface_hub import hf_hub_download

# Hugging Face repository containing the registered model.
REPO_ID = "aim25s-team7/elpris-se3-team-7"

# Optional: set HF_MODEL_REVISION to a commit SHA to download
# an exact model version. If it is not set, the current model is used.
REVISION = os.getenv("HF_MODEL_REVISION")


def main():
    # Download model.pkl from Hugging Face.
    # If REVISION is set, that exact version is downloaded.
    # Otherwise, the current version from the default branch is used.
    model_path = hf_hub_download(
        repo_id=REPO_ID,
        filename="model.pkl",
        revision=REVISION,
    )

    # Load the downloaded model file and verify that it is usable.
    with open(model_path, "rb") as file:
        model_data = pickle.load(file)

    print("Model downloaded and loaded successfully.")
    print(f"Revision: {REVISION or 'current'}")
    print(f"Downloaded to: {model_path}")
    print(f"Loaded object type: {type(model_data)}")


if __name__ == "__main__":
    main()