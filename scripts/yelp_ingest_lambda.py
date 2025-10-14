"""
Yelp Ingestion Lambda
Fetches restaurant data from Yelp API and stores into:
 - DynamoDB (full details)
 - OpenSearch (partial index)
"""

import os
import json
import time
import logging
import requests
import boto3
from urllib.parse import urlencode
from datetime import datetime
from requests_aws4auth import AWS4Auth
from requests.auth import HTTPBasicAuth
from decimal import Decimal

# ======================
# Logging setup
# ======================
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ======================
# Environment Variables
# ======================
YELP_API_KEY = os.environ.get("YELP_API_KEY")
DYNAMO_TABLE = os.environ.get("DYNAMO_TABLE", "yelp-restaurants")
OPENSEARCH_ENDPOINT = os.environ.get("OPENSEARCH_ENDPOINT")  # e.g. https://search-xyz.us-east-1.es.amazonaws.com
REGION = os.environ.get("AWS_REGION", "us-east-1")
CUISINES = os.environ.get("CUISINES", "Japanese,Italian,Chinese,Mexican,Indian").split(",")
NEIGHBORHOODS = os.environ.get("NEIGHBORHOODS", "Manhattan").split(",")

# Optional FGAC credentials
OS_USERNAME = os.environ.get("OS_USERNAME")
OS_PASSWORD = os.environ.get("OS_PASSWORD")

if not YELP_API_KEY:
    raise Exception("❌ Missing required env var: YELP_API_KEY")

# ======================
# AWS Clients
# ======================
dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(DYNAMO_TABLE)

session = boto3.Session()
credentials = session.get_credentials().get_frozen_credentials()

# Choose auth method for OpenSearch
if OS_USERNAME and OS_PASSWORD:
    # FGAC enabled domain using master username/password
    opensearch_auth = HTTPBasicAuth(OS_USERNAME, OS_PASSWORD)
    logger.info("Using HTTP Basic Auth for OpenSearch (FGAC mode)")
else:
    # Standard SigV4 for IAM-based domain policy
    opensearch_auth = AWS4Auth(
        credentials.access_key,
        credentials.secret_key,
        REGION,
        "es",
        session_token=credentials.token,
    )
    logger.info("Using AWS SigV4 Auth for OpenSearch")

HEADERS = {"Authorization": f"Bearer {YELP_API_KEY}"}
YELP_SEARCH_URL = "https://api.yelp.com/v3/businesses/search"
YELP_LIMIT = 50  # Max per request

# ======================
# Helper Functions
# ======================
def safe_decimal(value):
    """Convert float to Decimal for DynamoDB compatibility."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return value

def fetch_businesses_for_term(term, location="Manhattan, NY", total_needed=200):
    """Fetches up to `total_needed` businesses for a given search term."""
    businesses = {}
    offset = 0
    logger.info(f"Fetching Yelp businesses for '{term}' in {location}")
    while len(businesses) < total_needed:
        params = {"term": term, "location": location, "limit": YELP_LIMIT, "offset": offset}
        url = f"{YELP_SEARCH_URL}?{urlencode(params)}"
        r = requests.get(url, headers=HEADERS)
        if r.status_code == 429:
            logger.warning("⚠️ Yelp rate-limited. Sleeping 5s...")
            time.sleep(5)
            continue
        if r.status_code != 200:
            logger.error(f"❌ Yelp API error {r.status_code}: {r.text}")
            break

        data = r.json()
        items = data.get("businesses", [])
        if not items:
            break
        for b in items:
            businesses[b["id"]] = b
        offset += YELP_LIMIT
        if offset >= 1000:  # Yelp hard limit
            break
        time.sleep(0.3)
    return list(businesses.values())

def save_to_dynamo(b):
    """Store one business into DynamoDB."""
    coords = b.get("coordinates", {})
    item = {
        "business_id": b.get("id"),
        "Name": b.get("name"),
        "Address": " ".join(b.get("location", {}).get("display_address", [])),
        "Coordinates": {
            "latitude": safe_decimal(coords.get("latitude")),
            "longitude": safe_decimal(coords.get("longitude")),
        },
        "NumReviews": int(b.get("review_count", 0)),
        "Rating": safe_decimal(b.get("rating", 0.0)),
        "ZipCode": b.get("location", {}).get("zip_code", ""),
        "Categories": [c.get("title") for c in b.get("categories", [])],
        "Phone": b.get("phone", ""),
        "insertedAtTimestamp": datetime.utcnow().isoformat(),
    }
    try:
        table.put_item(Item=item)
        return True
    except Exception as e:
        logger.exception(f"❌ DynamoDB put_item failed for {b.get('id')}: {e}")
        return False

def index_to_opensearch(b):
    """Indexes a restaurant to OpenSearch."""
    if not OPENSEARCH_ENDPOINT:
        logger.warning("⚠️ OPENSEARCH_ENDPOINT not set; skipping indexing.")
        return False

    cuisine_list = [c.get("title") for c in b.get("categories", [])]
    doc = {
        "business_id": b.get("id"),
        "name": b.get("name"),
        "address": " ".join(b.get("location", {}).get("display_address", [])),
        "cuisine": cuisine_list,
        "zip_code": b.get("location", {}).get("zip_code", ""),
    }

    url = f"{OPENSEARCH_ENDPOINT.rstrip('/')}/restaurants/_doc/{b.get('id')}"
    headers = {"Content-Type": "application/json"}

    try:
        r = requests.put(url, auth=opensearch_auth, json=doc, headers=headers, timeout=30)
        if r.status_code not in (200, 201):
            logger.error(f"❌ OpenSearch index error {r.status_code}: {r.text}")
            return False
        logger.info(f"✅ Indexed to OpenSearch: {b.get('name')} ({b.get('id')})")
        return True
    except Exception as e:
        logger.exception(f"❌ Failed to index {b.get('id')} to OpenSearch: {e}")
        return False

# ======================
# Main Lambda Handler
# ======================
def handler(event, context):
    """Main Lambda entry point."""
    logger.info("🚀 Starting Yelp ingest Lambda")
    logger.info(f"Event: {json.dumps(event)}")

    total_added = 0
    total_indexed = 0

    try:
        for cuisine in CUISINES:
            cuisine = cuisine.strip()
            term = f"{cuisine} restaurant"
            for neighborhood in NEIGHBORHOODS:
                loc = neighborhood.strip()
                businesses = fetch_businesses_for_term(term, location=loc, total_needed=200)
                logger.info(f"Fetched {len(businesses)} businesses for {cuisine} in {loc}")

                for b in businesses:
                    if save_to_dynamo(b):
                        total_added += 1
                    if index_to_opensearch(b):
                        total_indexed += 1

        logger.info(f"✅ Ingest complete: {total_added} saved, {total_indexed} indexed.")
        return {"status": "ok", "added": total_added, "indexed": total_indexed}

    except Exception as e:
        logger.exception(f"💥 Unexpected error during ingestion: {e}")
        return {"status": "error", "error": str(e)}
