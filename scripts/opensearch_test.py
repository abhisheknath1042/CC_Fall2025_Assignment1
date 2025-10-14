import requests
import json
from requests.auth import HTTPBasicAuth

# ================================
# Configuration
# ================================
# Replace these with your OpenSearch domain details
ES_ENDPOINT = "https://search-restaurants-domain-wcljgs6k6zzwyy7hadpuientvu.us-east-1.es.amazonaws.com"
ES_INDEX = "restaurants"

# Master user credentials (from your domain setup)
ES_USERNAME = "abhisheknath"
ES_PASSWORD = "Random@#42"

# ================================
# Query Setup
# ================================
# Example query: find 5 restaurants matching cuisine = Japanese
query = {
    "query": {
        "match": {
            "cuisine": "japanese"
        }
    },
    "size": 5
}

# ================================
# Execution
# ================================
def main():
    url = f"{ES_ENDPOINT.rstrip('/')}/{ES_INDEX}/_search"
    headers = {"Content-Type": "application/json"}

    print(f"Querying {url} ...")

    try:
        response = requests.get(
            url,
            auth=HTTPBasicAuth(ES_USERNAME, ES_PASSWORD),
            headers=headers,
            json=query,
            timeout=10
        )
        print(f"Status Code: {response.status_code}")
        try:
            print(json.dumps(response.json(), indent=2))
        except json.JSONDecodeError:
            print("Raw Response:", response.text)
    except requests.exceptions.RequestException as e:
        print("Error connecting to OpenSearch:", str(e))

# ================================
# Entry Point
# ================================
if __name__ == "__main__":
    main()
