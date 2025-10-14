import boto3, json, requests
from requests_aws4auth import AWS4Auth

region = "us-east-1"
service = "es"
endpoint = "https://search-restaurants-domain-wcljgs6k6zzwyy7hadpuientvu.us-east-1.es.amazonaws.com"

session = boto3.Session()
credentials = session.get_credentials()
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key, region, service, session_token=credentials.token)

q = {"query": {"match": {"Cuisine": "Indian"}}, "size": 3}
r = requests.get(endpoint + "/restaurants/_search", auth=awsauth, json=q)
print("Status:", r.status_code)
print(json.dumps(r.json(), indent=2))
