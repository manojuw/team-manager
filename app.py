import os

os.chdir("/home/runner/workspace")
os.execvp("bash", ["bash", "start.sh"])
