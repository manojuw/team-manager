import os
import sys
import time

os.chdir("/home/runner/workspace")

time.sleep(0.5)

os.execvp("bash", ["bash", "start.sh"])
