import requests
import json

response = requests.get('http://localhost:8000/api/v1/clusters')
if response.status_code == 200:
    data = response.json()
    print(json.dumps(data, indent=2))
else:
    print(f"Failed with {response.status_code}: {response.text}")
