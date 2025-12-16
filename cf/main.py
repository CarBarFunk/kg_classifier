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
            WHERE invoked_date >= "2025-01-01"
                and page_element_placeholder IS NOT NULL
        """

        query_job = bq_client.query(query)
        results = query_job.result()

        # Collect texts
        texts = [row.cleaned_text for row in results if row.cleaned_text]

        if not texts:
            return {'message': 'No data found'}, 200

        # Prepare prompt for Gemini - send all texts
        combined_text = "\n".join(texts)  # Send all entries
        prompt = f"""Analysiere die folgenden {len(texts)} Kündigungsgründe und klassifiziere sie in Hauptthemen.

WICHTIG: Antworte direkt mit der Analyse ohne Einleitung wie "Absolut", "Hier ist", "Gerne" etc.

Kündigungsgründe:
{combined_text}

Erstelle eine Zusammenfassung mit:
1. Die Top 5-10 Themenkategorien
2. Eine kurze Beschreibung jeder Kategorie
3. Anzahl der Instanzen pro Kategorie
4. Prozentualer Anteil (als Anteil: Prozentzahl in Bold)

Format: Beginne direkt mit "**Themenkategorien:**" oder einer Überschrift.
Für jede Kategorie gib an: Kategoriename, Anzahl der Einträge, Prozentsatz
"""

        # Call Gemini
        model = GenerativeModel("gemini-2.5-flash-lite")
        response = model.generate_content(prompt)
        classification_result = response.text

        # Prepare message for Power Automate (which will post to Teams)
        # Escape special characters that might break JSON/adaptive card
        safe_classification = classification_result.replace('\n', '\\n').replace('"', '\\"').replace('\t', ' ')

        message_payload = {
            "title": "Kündigungsgründe Topic Classification",
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
