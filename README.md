# CF for KG Topic Classifier



### models

more expensive and slower but more accurate
gemini-2.5-pro

cheaper and faster
gemini-2.5-flash-lite

### try the code locally
  in the Makefile:

  launch the local servers:
  make run_button or make run_article

  trigger the APIs:
  make teams_button or make teams_article


### launch the CF from your terminal
  get an authentication token:
  ACCESS_TOKEN=$(gcloud auth print-identity-token)

  launch the CF :
  curl -H "Authorization: Bearer $ACCESS_TOKEN" CF-URL (I can provide the URL on request)


  The CF can be completely independent if scheduled either with Cloud Scheduler or with an Eventarc trigger



### to enable cloud function and eventarc APIs from terminal
gcloud services enable eventarc.googleapis.com
gcloud services enable cloudfunctions.googleapis.com


### to add a specific Eventarc trigger to a specific CF
gcloud eventarc triggers create <TRIGGER_NAME> \
    --location=<REGION> \
    --destination-run-service=<CLOUD_FUNCTION_NAME> \
    --destination-run-region=<CLOUD_FUNCTION_REGION> \
    --event-filters=<EVENT_TYPE> \
    --event-filters="serviceName=bigquery.googleapis.com" \
    --event-filters=<EVENT_METHOD> \
    --event-filters="resourceName=projects/PROJECT_ID/datasets/DATASET_NAME/tables/TABLE_NAME" \
    --service-account=<SERVICE_ACCOUNT_EMAIL>




### to call the CF
gcloud functions deploy classify-topics \
       --gen2 \
       --runtime=python314 \
       --region=us-central1 \
       --source=. \
       --entry-point=classify_topics \
       --trigger-http \
       --allow-unauthenticated \
       --set-env-vars GCP_PROJECT_ID=your-project,TEAMS_WEBHOOK_URL=your-webhook
