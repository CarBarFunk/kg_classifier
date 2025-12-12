import functions_framework
from google.cloud import bigquery
from google.cloud import aiplatform
import vertexai
from vertexai.generative_models import GenerativeModel
import requests
import json
import os


@functions_framework.http
def classify_topics(request):
    """
    Cloud Function to classify page_element_placeholder topics using Gemini
    and send results to Microsoft Teams via Power Automate
    """
    try:
        # Initialize clients
        project_id = os.environ.get('GCP_PROJECT_ID')
        location = os.environ.get('GCP_LOCATION')
        power_automate_url = os.environ.get('POWER_AUTOMATE_WEBHOOK_URL')

        if not project_id or not power_automate_url:
            return {'error': 'Missing required environment variables'}, 400

        # Initialize Vertex AI
        vertexai.init(project=project_id, location=location)

        # Query BigQuery
        bq_client = bigquery.Client(project=project_id)
        query = """
            SELECT
                page_element_placeholder as cleaned_text
            FROM `reports.rep_piano_kuendigungsgruende`
            WHERE page_element_placeholder IS NOT NULL
            and invoked_date >= "2025-11-01"
        """

        query_job = bq_client.query(query)
        results = query_job.result()

        # Collect texts
        texts = [row.cleaned_text for row in results if row.cleaned_text]

        if not texts:
            return {'message': 'No data found'}, 200

        # Prepare prompt for Gemini
        combined_text = "\n".join(texts[:100])  # Limit to first 100 entries
        prompt = f"""Analyze the following cancellation reasons and classify them into main topics.
Provide a summary with topic categories and their frequency:

{combined_text}

Please provide:
1. Top 5-10 topic categories
2. Brief description of each category
3. Approximate percentage distribution
"""

        # Call Gemini
        model = GenerativeModel("gemini-2.5-pro")
        response = model.generate_content(prompt)
        classification_result = response.text

        # Prepare message for Power Automate (which will post to Teams)
        # Escape special characters that might break JSON/adaptive card
        safe_classification = classification_result.replace('\n', '\\n').replace('"', '\\"').replace('\t', ' ')

        message_payload = {
            "title": "Cancellation Reasons Topic Classification",
            "total_entries": str(len(texts)),
            "classification": safe_classification
        }

        # Send to Power Automate
        response = requests.post(
            power_automate_url,
            headers={'Content-Type': 'application/json'},
            data=json.dumps(message_payload)
        )

        if response.status_code in [200, 202]:
            return {'message': 'Classification sent to Teams successfully', 'analyzed_count': len(texts)}, 200
        else:
            return {'error': f'Failed to send to Teams. Status: {response.status_code}, Response: {response.text}'}, 500

    except Exception as e:
        return {'error': str(e)}, 500




# this is a test
