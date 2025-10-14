import os, json, re, time, logging, boto3
from datetime import datetime

# ---------- Logging ----------
logger = logging.getLogger()
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

# ---------- AWS ----------
sqs = boto3.client("sqs")
QUEUE_URL = os.getenv("QUEUE_URL")

# ---------- Constants ----------
VALID_CUISINES = {"chinese", "indian", "italian", "japanese", "thai", "mexican"}
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


# ---------- Slot Helpers ----------
def get_slot(slots, name):
    val = (slots.get(name) or {}).get("value") or {}
    v = val.get("interpretedValue") or val.get("originalValue")
    return v.replace("T", "") if isinstance(v, str) else v


def elicit_slot(session_state, slots, slot_to_elicit, text):
    ss = dict(session_state or {})
    intent = dict(ss.get("intent") or {})
    intent["slots"] = slots
    intent["state"] = "InProgress"
    ss["intent"] = intent
    ss["dialogAction"] = {"type": "ElicitSlot", "slotToElicit": slot_to_elicit}
    return {"sessionState": ss, "messages": [{"contentType": "PlainText", "content": text}]}


def delegate(session_state, slots):
    ss = dict(session_state or {})
    intent = dict(ss.get("intent") or {})
    intent["slots"] = slots
    intent["state"] = "InProgress"
    ss["intent"] = intent
    ss["dialogAction"] = {"type": "Delegate"}
    return {"sessionState": ss}


def close(session_state, text, state="Fulfilled"):
    ss = dict(session_state or {})
    intent = dict(ss.get("intent") or {})
    intent["state"] = state
    ss["intent"] = intent
    ss["dialogAction"] = {"type": "Close"}
    return {
        "sessionState": ss,
        "messages": [{"contentType": "PlainText", "content": text}],
    }


# ---------- Validation ----------
def validate(location, cuisine, num_people, dining_time, email):
    if location and location.lower() != "manhattan":
        return False, "Location", "Currently, we only support restaurant suggestions in Manhattan."

    if cuisine and cuisine.lower() not in VALID_CUISINES:
        return False, "Cuisine", f"We do not support {cuisine} cuisine yet. How about trying Italian instead?"

    if num_people:
        try:
            n = int(num_people)
            if not (1 <= n < 30):
                raise ValueError
        except ValueError:
            return False, "NumberOfPeople", "Please provide a number of people between 1 and 30."

    if dining_time and not re.fullmatch(r"^([0-1]?\d|2[0-3]):[0-5]\d$", dining_time):
        return False, "DiningTime", "Please provide a valid time in HH:MM format (e.g., 19:30)."

    if email and not EMAIL_RE.fullmatch(email):
        return False, "email", "Please provide a valid email address."

    return True, None, None


# ---------- Intent Handlers ----------
def handle_greeting(event):
    return close(event.get("sessionState"), "Hello! How can I assist you today?", "Fulfilled")


def handle_thanks(event):
    return close(event.get("sessionState"), "You're welcome!", "Fulfilled")


def handle_dining(event):
    ss = event.get("sessionState", {})
    intent = ss.get("intent", {})
    slots = dict(intent.get("slots") or {})
    source = event.get("invocationSource")

    # Extract slot values
    location = get_slot(slots, "Location")
    cuisine = get_slot(slots, "Cuisine")
    num_people = get_slot(slots, "NumberOfPeople")
    dining_time = get_slot(slots, "DiningTime")
    email = get_slot(slots, "email")

    # ---- DIALOG CODE HOOK ----
    if source == "DialogCodeHook":
        valid, violated, msg = validate(location, cuisine, num_people, dining_time, email)
        if not valid:
            if violated not in slots:
                slots[violated] = {"value": {"interpretedValue": ""}}
            return elicit_slot(ss, slots, violated, msg)
        for s, prompt in [
            ("Cuisine", "What cuisine would you like?"),
            ("Location", "Where do you want to eat?"),
            ("DiningTime", "At what time? (HH:MM, 24h format)"),
            ("NumberOfPeople", "How many people are dining?"),
            ("email", "What email should I send your suggestions to?"),
        ]:
            if not get_slot(slots, s):
                return elicit_slot(ss, slots, s, prompt)
        return delegate(ss, slots)

    # ---- FULFILLMENT CODE HOOK ----
    payload = {
        "Location": location or "",
        "Cuisine": (cuisine or "").lower(),
        "NumberOfPeople": str(num_people or ""),
        "DiningTime": dining_time or "",
        "email": email or "",
        "sessionId": event.get("sessionId"),
    }

    logger.info("[LF1] Enqueue payload: %s", json.dumps(payload))

    if QUEUE_URL:
        try:
            sqs.send_message(
                QueueUrl=QUEUE_URL,
                MessageBody=json.dumps(payload),
                MessageAttributes={
                    "intent": {"DataType": "String", "StringValue": "DiningSuggestionsIntent"},
                    "Cuisine": {"DataType": "String", "StringValue": payload["Cuisine"]},
                },
            )
        except Exception as e:
            logger.error("SQS send failed: %s", e)
    else:
        logger.warning("[LF1] QUEUE_URL not set — skipping SQS send.")

    confirm_msg = (
        f"Got it! I'll send you {payload['Cuisine'].title()} restaurant suggestions "
        f"in {payload['Location']} for {payload['NumberOfPeople']} people at {payload['DiningTime']}. "
        f"Expect an email soon!"
    )
    return close(ss, confirm_msg, "Fulfilled")


# ---------- Main Entry ----------
def lambda_handler(event, _context):
    os.environ["TZ"] = "America/New_York"
    try:
        time.tzset()
    except Exception:
        pass

    intent = ((event.get("sessionState") or {}).get("intent") or {}).get("name")
    logger.info("[LF1] intent=%s source=%s", intent, event.get("invocationSource"))

    if intent == "GreetingIntent":
        return handle_greeting(event)
    if intent == "ThankYouIntent":
        return handle_thanks(event)
    if intent == "DiningSuggestionsIntent":
        return handle_dining(event)

    return close(event.get("sessionState"), "Sorry, I didn’t catch that.", "Fulfilled")