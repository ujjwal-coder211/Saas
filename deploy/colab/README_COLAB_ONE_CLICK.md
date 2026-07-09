# Colab train — minimum steps (agent cannot use your Google login)

The training notebook is ready. **Google Colab runs on your Google account** — the agent cannot log in or start GPU without you.

## Absolute minimum (3 clicks, ~3 hours GPU time)

1. Open this link (after notebook is pushed to GitHub):

   https://colab.research.google.com/github/ujjwal-coder211/Saas/blob/main/deploy/colab/SARVA_CONDUCTOR_TRAIN.ipynb

2. **Runtime** → **Change runtime type** → **A100** → Save

3. Left **🔑 Secrets** → New secret: name `HF_TOKEN`, value = HuggingFace write token  
   (create at https://huggingface.co/settings/tokens )

4. **Runtime** → **Run all**

Done. Notebook will download dataset, train, save Drive, push `Ujjwal211/aitotech-sarva-v2`.

## If you send a Colab link

Paste your existing Colab notebook URL in chat. The agent still cannot click Run inside your Google session unless Browser tools are enabled and you are already logged in.

## Alternative (no Colab)

Provide in Cursor environment variables:

- `HF_TOKEN`
- `RUNPOD_API_KEY`

Then the agent can train on RunPod without Colab.
