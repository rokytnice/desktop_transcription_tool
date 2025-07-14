#!/bin/bash
sudo apt update
sudo apt install ffmpeg
sudo apt install xdotool

python3 -m venv .venv
source .venv/bin/activate


curl -O https://repo.anaconda.com/archive/Anaconda3-2024.10-1-Linux-x86_64.sh ~/scripts/
chmod +x ~/scripts/Anaconda3-2024.10-1-Linux-x86_64.sh
bash ~/scripts/Anaconda3-2024.10-1-Linux-x86_64.sh
source ~/.bashrc
# Replace <PATH_TO_CONDA> with the path to your conda install
source ~/scripts/bin/activate
conda init --all

conda config --set auto_activate_base True


pip install --upgrade pip
pip install -r requirements.txt
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118


