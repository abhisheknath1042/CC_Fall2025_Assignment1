# Dining Concierge — CS-GY 9223 HW1

## Overview
This project implements a Dining Concierge chatbot using serverless AWS services:
- Frontend hosted on S3 (static website).
- API Gateway + Lambda (LF0) to forward chat messages to Amazon Lex v2.
- Amazon Lex v2 bot with intents (GreetingIntent, ThankYouIntent, DiningSuggestionsIntent) and Lambda code hook (LF1).
- SQS queue (Q1) to hold suggestion requests.
- DynamoDB table `yelp-restaurants` to store Yelp restaurant data.
- OpenSearch index `restaurants` for cuisine search.
- Worker Lambda (LF2) reads SQS, queries OpenSearch & DynamoDB, and sends emails via SES.

## Setup (high level)
1. Clone frontend starter repo and build: `npm install && npm run build`
2. Create S3 bucket and enable static website hosting, upload build output.
3. Create required IAM roles (see IAM section).
4. Create DynamoDB table `yelp-restaurants`.
5. Create OpenSearch domain and index `restaurants`.
6. Create SQS queue `dining-requests-queue` (and optional DLQ).
7. Set up Lex v2 bot with intents and Lambda code hook (LF1).
8. Deploy Lambda functions LF0, LF1, LF2 with required env vars and roles.
9. Create API Gateway API from provided swagger, integrate LF0, enable CORS, and deploy.
10. Configure SES sender email and verify.
11. Run Yelp scraping script to populate DynamoDB and OpenSearch (requires `YELP_API_KEY`).
12. Create EventBridge scheduled rule to trigger LF2 every minute.

## Files
- `lf0_lambda.py` — API gateway handler & Lex integration
- `lf1_lex_hook.py` — Lex code hook that validates slots and pushes SQS messages
- `lf2_worker.py` — SQS worker that queries OpenSearch/DynamoDB and sends emails via SES
- `scripts/scrape_yelp.py` — Yelp scraping & ingestion script

## Environment variables (Lambda)
LF0:
- `LEX_BOT_ID`
- `LEX_BOT_ALIAS_ID`
- `LEX_BOT_LOCALE` (optional)

LF1:
- `SQS_URL`

LF2:
- `SQS_URL`
- `OPENSEARCH_ENDPOINT`
- `DYNAMO_TABLE` (yelp-restaurants)
- `SES_SENDER`

## Troubleshooting
Read the project's `Troubleshooting` section in the project wiki. (See detailed instructions in the assignment doc.)

## Notes
- AWS resource names must be unique per account and region.
- SES may be in sandbox—verify recipients or request production access for sending to arbitrary addresses.