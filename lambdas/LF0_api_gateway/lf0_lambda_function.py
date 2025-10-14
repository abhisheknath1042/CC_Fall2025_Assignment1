import json
import boto3
import logging
import os
import uuid

# ------------------------------------------------------------
# Logger setup
# ------------------------------------------------------------
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ------------------------------------------------------------
# Initialize Lex V2 Runtime client
# ------------------------------------------------------------
lex_client = boto3.client("lexv2-runtime")

# Lex V2 Bot Configuration (from Lambda environment variables)
BOT_ID = os.getenv("BOT_ID")
BOT_ALIAS_ID = os.getenv("BOT_ALIAS_ID")
LOCALE_ID = "en_US"  # default locale


def lambda_handler(event, context):
    """
    LF0 Lambda: API Gateway entrypoint for the Dining Concierge chatbot.

    Steps:
      1. Extract user's message from request body (supports multiple formats)
      2. Generate or reuse session ID
      3. Forward text to Lex V2 via recognize_text()
      4. Return Lex's reply to frontend with proper CORS headers
    """

    logger.info(f"Received event: {json.dumps(event)}")

    try:
        # ------------------------------------------------------------
        # 1️⃣  Parse user message from event (robustly handles both formats)
        # ------------------------------------------------------------
        body = {}
        if isinstance(event, dict):
            # Case A: API Gateway proxy integration (body as JSON string)
            if "body" in event:
                try:
                    if event["body"]:
                        body = json.loads(event["body"])
                except json.JSONDecodeError:
                    logger.warning("Request body is not valid JSON; using empty dict")
                    body = {}
            # Case B: direct invoke (no 'body' key, text at top level)
            elif "text" in event:
                body = event

        user_message = ""

        # Try to extract message from the full swagger-style structure
        if "messages" in body:
            try:
                user_message = (
                    body.get("messages", [{}])[0]
                    .get("unstructured", {})
                    .get("text", "")
                )
            except Exception:
                user_message = ""
        # Fallback: flat structure { "text": "hello" }
        elif "text" in body:
            user_message = body.get("text", "")

        # ------------------------------------------------------------
        # 2️⃣  Validate message presence
        # ------------------------------------------------------------
        if not user_message:
            logger.warning("No user message found in request body.")
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                    "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
                },
                "body": json.dumps(
                    {
                        "messages": [
                            {
                                "type": "unstructured",
                                "unstructured": {
                                    "text": "Error: No message provided",
                                },
                            }
                        ]
                    }
                ),
            }

        logger.info(f"Parsed user message: {user_message}")

        # ------------------------------------------------------------
        # 3️⃣  Determine or generate session ID
        # ------------------------------------------------------------
        session_id = body.get("sessionId")
        if not session_id:
            session_id = str(uuid.uuid4())
            logger.info(f"Generated new session ID: {session_id}")
        else:
            logger.info(f"Using provided session ID: {session_id}")

        # ------------------------------------------------------------
        # 4️⃣  Validate Lex environment config
        # ------------------------------------------------------------
        if not BOT_ID or not BOT_ALIAS_ID:
            logger.error("BOT_ID or BOT_ALIAS_ID not configured.")
            return {
                "statusCode": 500,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                    "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
                },
                "body": json.dumps(
                    {
                        "messages": [
                            {
                                "type": "unstructured",
                                "unstructured": {
                                    "text": "Bot configuration error. Please contact the administrator.",
                                },
                            }
                        ]
                    }
                ),
            }

        # ------------------------------------------------------------
        # 5️⃣  Send text to Lex V2
        # ------------------------------------------------------------
        lex_response = lex_client.recognize_text(
            botId=BOT_ID,
            botAliasId=BOT_ALIAS_ID,
            localeId=LOCALE_ID,
            sessionId=session_id,
            text=user_message,
        )

        logger.info(f"Lex raw response: {json.dumps(lex_response, default=str)}")

        # ------------------------------------------------------------
        # 6️⃣  Extract Lex response message
        # ------------------------------------------------------------
        bot_message = "I'm sorry, I didn't understand that. Can you please rephrase?"
        if "messages" in lex_response and len(lex_response["messages"]) > 0:
            bot_message = lex_response["messages"][0].get("content", bot_message)

        timestamp = (
            lex_response.get("messages", [{}])[0].get("timestamp", "")
            if lex_response.get("messages")
            else ""
        )

        # ------------------------------------------------------------
        # 7️⃣  Format API response for frontend
        # ------------------------------------------------------------
        response_body = {
            "messages": [
                {
                    "type": "unstructured",
                    "unstructured": {
                        "id": "1",
                        "text": bot_message,
                        "timestamp": timestamp,
                    },
                }
            ]
        }

        response = {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
            },
            "body": json.dumps(response_body),
        }

        return response

    # ------------------------------------------------------------
    # 🔴 Global error handler
    # ------------------------------------------------------------
    except Exception as e:
        logger.error(f"Unhandled exception: {str(e)}", exc_info=True)

        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
                "Access-Control-Allow-Methods": "OPTIONS,POST,GET",
            },
            "body": json.dumps(
                {
                    "messages": [
                        {
                            "type": "unstructured",
                            "unstructured": {
                                "text": f"Error processing your request: {str(e)}",
                            },
                        }
                    ]
                }
            ),
        }