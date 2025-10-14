import os, json, logging, random, boto3, requests
from boto3.dynamodb.conditions import Key
from requests.auth import HTTPBasicAuth
from botocore.exceptions import ClientError

# =========================
# Env / Config
# =========================
AWS_REGION     = os.getenv("AWS_REGION", "us-east-1")
QUEUE_URL      = os.getenv("QUEUE_URL")   # SQS queue URL
ES_ENDPOINT    = os.getenv("ES_ENDPOINT") # https://search-xxx.aos.us-east-1.on.aws
ES_INDEX       = os.getenv("ES_INDEX", "restaurants")
ES_USERNAME    = os.getenv("ES_USERNAME")   # FGAC master user
ES_PASSWORD    = os.getenv("ES_PASSWORD")   # FGAC master password
SES_FROM_EMAIL = os.getenv("SES_FROM_EMAIL", "verified@your.com")
DDB_TABLE      = os.getenv("DYNAMO_TABLE", "yelp-restaurants")

DDB_PK = "business_id"
DDB_SK = "insertedAtTimestamp"

# =========================
# Clients
# =========================
logger = logging.getLogger()
logger.setLevel(logging.INFO)

sqs   = boto3.client("sqs", region_name=AWS_REGION)
ses   = boto3.client("ses", region_name=AWS_REGION)
ddb   = boto3.resource("dynamodb", region_name=AWS_REGION)
table = ddb.Table(DDB_TABLE)

# =========================
# Helpers
# =========================
def norm_cuisine(c: str) -> str:
    return (c or "").strip().capitalize()

def os_search_business_ids(cuisine_tc: str, size: int = 50):
    """
    Query OpenSearch (FGAC) for matching cuisine documents.
    Uses BasicAuth credentials from environment variables.
    """
    if not ES_ENDPOINT:
        logger.error("[LF2] ES_ENDPOINT not set.")
        return [], {}

    url = f"{ES_ENDPOINT.rstrip('/')}/{ES_INDEX}/_search"
    q = {
        "size": size,
        "query": {"term": {"cuisine.keyword": cuisine_tc}},
        "_source": ["business_id", "name", "address"]
    }

    try:
        logger.info("[LF2] Querying OpenSearch: %s", url)
        r = requests.get(
            url,
            auth=HTTPBasicAuth(ES_USERNAME, ES_PASSWORD),
            headers={"Content-Type": "application/json"},
            data=json.dumps(q),
            timeout=8
        )

        logger.info("[LF2] OpenSearch status: %s", r.status_code)
        if r.status_code != 200:
            logger.error("[LF2] Error text: %s", r.text)
        r.raise_for_status()

        hits = (r.json().get("hits") or {}).get("hits") or []
        ids, src_map = [], {}
        for h in hits:
            src = h.get("_source") or {}
            bid = src.get("business_id")
            if bid:
                ids.append(bid)
                src_map[bid] = {
                    "name": src.get("name"),
                    "address": src.get("address")
                }

        logger.info("[LF2] Found %d hits for cuisine '%s'", len(ids), cuisine_tc)
        return list(dict.fromkeys(ids)), src_map

    except requests.exceptions.HTTPError as http_err:
        logger.error("[LF2] OpenSearch HTTPError: %s", http_err, exc_info=True)
        if 'r' in locals():
            logger.error("[LF2] Response text: %s", r.text)
        return [], {}
    except Exception as e:
        logger.error("[LF2] OpenSearch query failed: %s", e, exc_info=True)
        return [], {}

def ddb_fetch_latest(business_id: str):
    """Query DynamoDB by PK and return newest record."""
    try:
        resp = table.query(
            KeyConditionExpression=Key(DDB_PK).eq(business_id),
            ScanIndexForward=False,
            Limit=1
        )
        items = resp.get("Items") or []
        return items[0] if items else None
    except Exception as e:
        logger.error("[LF2] DDB query failed for %s: %s", business_id, e, exc_info=True)
        return None

def format_email_body(cuisine_tc, num_people, dining_time, recs):
    header = (f"Hello! Here are my {cuisine_tc} restaurant suggestions "
              f"for {num_people} people, for today at {dining_time}:\n")
    lines = []
    if recs:
        for i, r in enumerate(recs, 1):
            lines.append(f"{i}. {r.get('name','Unknown')}, located at {r.get('address','Address unavailable')}")
    else:
        lines.append("Sorry, I couldn't find matching restaurants right now.")
    return header + "\n".join(lines) + "\n\nEnjoy your meal!"

def send_email(to_addr, subject, body):
    if not to_addr:
        logger.warning("[LF2] No recipient email; skipping SES.")
        return
    try:
        ses.send_email(
            Source=SES_FROM_EMAIL,
            Destination={"ToAddresses": [to_addr]},
            Message={"Subject": {"Data": subject}, "Body": {"Text": {"Data": body}}}
        )
        logger.info("[LF2] Email sent to %s", to_addr)
    except ClientError as e:
        logger.error("[LF2] SES send failed: %s", e, exc_info=True)

# =========================
# Core processing
# =========================
def _process_message_dict(msg: dict):
    cuisine_tc  = norm_cuisine(msg.get("Cuisine") or "")
    location    = (msg.get("Location") or "Manhattan").title()
    num_people  = msg.get("NumberOfPeople") or "N/A"
    dining_time = msg.get("DiningTime") or "N/A"
    recipient   = msg.get("email")

    ids, src_map = os_search_business_ids(cuisine_tc)
    if not ids:
        body = format_email_body(cuisine_tc, num_people, dining_time, [])
        send_email(recipient, f"{cuisine_tc} restaurants in {location}", body)
        return

    picks = random.sample(ids, min(3, len(ids)))

    recs = []
    for bid in picks:
        item = ddb_fetch_latest(bid)
        if item:
            recs.append({
                "name": item.get("name", src_map.get(bid, {}).get("name", "Unknown")),
                "address": item.get("address", src_map.get(bid, {}).get("address", "Address unavailable"))
            })
        else:
            fallback = src_map.get(bid, {})
            recs.append({
                "name": fallback.get("name", "Unknown"),
                "address": fallback.get("address", "Address unavailable")
            })

    body = format_email_body(cuisine_tc, num_people, dining_time, recs)
    send_email(recipient, f"{cuisine_tc} restaurants in {location}", body)

def _poll_sqs_once():
    if not QUEUE_URL:
        logger.warning("[LF2] QUEUE_URL not set; skipping manual poll.")
        return
    resp = sqs.receive_message(
        QueueUrl=QUEUE_URL,
        MaxNumberOfMessages=5,
        WaitTimeSeconds=0,
        MessageAttributeNames=["All"]
    )
    for m in resp.get("Messages", []):
        try:
            body = json.loads(m["Body"])
            _process_message_dict(body)
            sqs.delete_message(QueueUrl=QUEUE_URL, ReceiptHandle=m["ReceiptHandle"])
        except Exception as e:
            logger.error("[LF2] Failed to process SQS message: %s", e, exc_info=True)

# =========================
# Lambda entry
# =========================
def lambda_handler(event, _ctx):
    logger.info("[LF2] Event: %s", json.dumps(event))

    # Case 1: SQS trigger
    if isinstance(event, dict) and "Records" in event:
        records = event.get("Records") or []
        if records and records[0].get("eventSource") == "aws:sqs":
            for r in records:
                try:
                    _process_message_dict(json.loads(r["body"]))
                except Exception as e:
                    logger.error("[LF2] Failed SQS-triggered record: %s", e, exc_info=True)
            return {"statusCode": 200, "body": "ok"}

    # Case 2: EventBridge scheduler
    if event.get("detail-type") == "Scheduled Event":
        _poll_sqs_once()
        return {"statusCode": 200, "body": "ok"}

    logger.warning("[LF2] Unknown event source; nothing to do.")
    return {"statusCode": 200, "body": "noop"}