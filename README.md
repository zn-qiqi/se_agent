# se_agent

A minimal coding agent that can read and write files, list directories, and run
commands in its workspace through an OpenAI-compatible model API.

## Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

$env:OPENAI_API_KEY = "your-api-key"
$env:OPENAI_MODEL = "your-model-name"
# Optional for an OpenAI-compatible gateway:
$env:OPENAI_BASE_URL = "https://your-gateway.example/v1"

python main.py
```

Enter `exit` or `quit` to stop. Credentials are read only from environment
variables or the Git-ignored local `config.py`; do not commit them to the
repository.
