JOB PORTAL — setup on your Mac
================================
Needs: macOS with Python 3.11+ (https://www.python.org/downloads/ or `brew install python`).

1. Unzip this folder somewhere, e.g. ~/Documents/MY_PORTAL
2. Open Terminal in that folder and run:   ./desktop/install.sh
   -> a "Job Portal" icon appears on your Desktop.
3. Double-click the icon. The first start takes ~1 minute (it installs its packages),
   then the portal opens at http://localhost:8787. If macOS asks for access to the folder, click Allow.
4. Optional: add YOUR OWN API keys in the .env file (copy .env.example to .env first).
   Without keys, use "copy & paste" mode with your ChatGPT / Claude subscription.

Full guide: README.md
