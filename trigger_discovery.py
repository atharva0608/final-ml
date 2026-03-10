import sys
import os
sys.path.insert(0, os.path.abspath('.'))
from backend.workers.tasks.discovery import run_discovery

print("Triggering discovery...")
result = run_discovery()
print("Result:", result)
