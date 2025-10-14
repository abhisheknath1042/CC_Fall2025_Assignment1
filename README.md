# Dining Concierge — Serverless Chatbot (CS-GY 9223 Fall 2025)

## 🧩 Overview
Dining Concierge is a **serverless chatbot** that suggests restaurants using AWS services.  
Users interact with a Lex v2 chatbot via a web frontend hosted on S3.  
Requests flow through API Gateway and multiple Lambda functions that store data in DynamoDB, query OpenSearch, and send restaurant suggestions by email through SES.

## 🏗️ Architecture
**Frontend (S3)** → **API Gateway** → **Lambda (LF0)** → **Lex v2 Bot + LF1 Code Hook** → **SQS Queue (Q1)** → **Lambda (LF2)** → **DynamoDB + OpenSearch + SES**  
All services communicate via event-driven, fully managed AWS components.

## ⚙️ AWS Resources
| Component | Purpose |
|------------|----------|
| **S3** | Hosts static frontend (public website) |
| **API Gateway** | REST API layer importing `swagger.yaml` |
| **Lambda LF0** | Receives API calls, forwards text to Lex |
| **Lex v2 Bot** | Conversational interface (Greeting, ThankYou, DiningSuggestions) |
| **Lambda LF1** | Lex code hook; validates slots, sends SQS messages |
| **SQS (Q1)** | Queues user dining requests |
| **Lambda LF2** | Processes SQS messages, queries OpenSearch & DynamoDB, sends emails |
| **DynamoDB (yelp-restaurants)** | Stores detailed restaurant data |
| **OpenSearch** | Indexes restaurants by cuisine |
| **SES** | Sends suggestion emails |
| **EventBridge** | Triggers LF2 every minute |
| **IAM Roles** | Provide Lambda + service permissions |

## 🪜 High-Level Steps
1. **Frontend Setup**  
   - Clone starter repo → `npm install && npm run build`  
   - Create S3 bucket → disable public-block → upload build → enable static website hosting.  

2. **IAM & Roles**  
   - Create `LambdaWorkerRole` with `AWSLambdaBasicExecutionRole`, `AmazonSQSFullAccess`, `AmazonDynamoDBFullAccess`, `AmazonOpenSearchServiceFullAccess`, `AmazonSESFullAccess`.  

3. **Lex Bot Creation**  
   - Create Lex v2 bot `DiningConciergeBot` with intents: *Greeting*, *ThankYou*, *DiningSuggestions*.  
   - Add slots: `Location`, `Cuisine`, `DiningDate`, `DiningTime`, `NumberOfPeople`, `Email`.  
   - Configure Lambda code hook = **LF1**. Deploy alias `Prod`.  

4. **Lambda Functions**  
   - **LF0** → Handles API Gateway requests, calls Lex (`boto3.lexv2-runtime`).  
   - **LF1** → Lex hook; validates slots and pushes message to **SQS (Q1)**.  
   - **LF2** → Reads SQS, fetches restaurants from **OpenSearch** & **DynamoDB**, sends email via **SES**.  

5. **API Gateway**  
   - Import `swagger/swagger.yaml`, integrate POST endpoint with **LF0**, enable CORS, deploy stage `prod`.  

6. **Backend Data**  
   - Create DynamoDB table `yelp-restaurants` (PK=`BusinessID`).  
   - Create OpenSearch domain, index `restaurants`.  
   - Run `scripts/scrape_yelp.py` to fetch 1000+ Manhattan restaurants (using Yelp API) and populate both.  

7. **SQS & EventBridge**  
   - Create queue `dining-requests-queue` (+ optional DLQ).  
   - Schedule LF2 every minute using EventBridge rule `rate(1 minute)`.  

8. **SES Setup**  
   - Verify sender email (and recipient if SES sandbox).  
   - Add env var `SES_SENDER` to LF2.  

9. **Testing Flow**  
   - Visit S3 website → type messages (“I need restaurant suggestions”).  
   - LF0 → Lex → LF1 → SQS → LF2 → SES email with suggestions.  

## 🧰 Tools
Developed with **VSCode**, **PowerShell**, and **AWS CLI** on Windows.  
All Lambda functions are written in **Python 3.10** and deployed via zip or console.

## 🚑 Troubleshooting
- **CORS 403** → Enable in API Gateway + include header in Lambda responses.  
- **Lex errors** → Check CloudWatch logs & ensure correct bot IDs.  
- **SES rejects** → Verify sender/recipient or move account out of sandbox.  
- **SQS unprocessed** → Review LF2 logs; unhandled messages move to DLQ.  
- **OpenSearch 403** → Update domain access policy for Lambda role.  

## 🧾 Deliverables
- Working chatbot (frontend + backend)  
- Screenshots: Lex dialog, SQS/DLQ, DynamoDB, SES email  
- Source code: `lf0_lambda.py`, `lf1_lex_hook.py`, `lf2_worker.py`, `scrape_yelp.py`, and this README  

---

**Author:** Abhishek Nath  
**Environment:** AWS Cloud (Serverless Stack)  
**Languages:** Python, JavaScript  
**Goal:** Demonstrate a complete event-driven serverless application on AWS.