import boto3, requests, json
from requests_aws4auth import AWS4Auth

region = 'us-east-1'
service = 'es'
host = 'search-restaurants-domain-wcljgs6k6zzwyy7hadpuientvu.us-east-1.es.amazonaws.com'
credentials = boto3.Session().get_credentials().get_frozen_credentials()
awsauth = AWS4Auth(credentials.access_key, credentials.secret_key, region, service, session_token=credentials.token)

# Create custom role
role_payload = {
    "cluster": ["cluster_composite_ops"],
    "index": [
        {"names": ["restaurants*"], "privileges": ["read", "write", "create_index"]}
    ]
}
requests.put(f"https://{host}/_plugins/_security/api/roles/lambda_writer_role",
              auth=awsauth, headers={"Content-Type": "application/json"},
              data=json.dumps(role_payload))

# Map IAM role to that custom role
mapping_payload = {"backend_roles": ["arn:aws:iam::238005914314:role/concierge-lambda-role"]}
r = requests.put(f"https://{host}/_plugins/_security/api/rolesmapping/lambda_writer_role",
                 auth=awsauth, headers={"Content-Type": "application/json"},
                 data=json.dumps(mapping_payload))
print(r.status_code, r.text)