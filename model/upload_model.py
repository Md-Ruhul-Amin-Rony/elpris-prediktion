from huggingface_hub import HfApi

# Hugging Face repository where the trained model is stored.
REPO_ID = "aim25s-team7/elpris-se3-team-7"

# Local model file created by train.py.
MODEL_PATH = "model/model.pkl"


def main():
    # Create a Hugging Face API client.
    api = HfApi()

    # Upload model.pkl to the model repository.
    # Hugging Face creates a new commit for this upload.
    commit_info = api.upload_file(
        path_or_fileobj=MODEL_PATH,
        path_in_repo="model.pkl",
        repo_id=REPO_ID,
        repo_type="model",
        commit_message="Upload trained electricity price model",
    )

    # Print the exact version created by the upload.
    print("Model uploaded successfully.")
    print(f"Commit SHA: {commit_info.oid}")
    print(f"Commit URL: {commit_info.commit_url}")


if __name__ == "__main__":
    main()