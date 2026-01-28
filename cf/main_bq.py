import functions_framework
from google.cloud import bigquery
import vertexai
from vertexai.generative_models import GenerativeModel
import requests
import json
import os


def extract_topic_names(classification_result):
    """
    Extract topic names from the classification result.
    Assumes topics follow the pattern "**Topic Name**".
    """
    topic_names = []
    if "**Themenkategorien:**" in classification_result:
        # Split the classification result into lines
        lines = classification_result.split("\n")
        for line in lines:
            # Look for bold topic names using "**"
            start = line.find("**")
            end = line.find("**", start + 2)
            if start != -1 and end != -1:
                topic_name = line[start + 2:end].strip()  # Extract the content inside the `**`
                topic_names.append(topic_name)
    return topic_names


@functions_framework.http
def classify_topics(request):
    """
    Cloud Function to classify topics using Gemini, save results in BigQuery,
    and send results to Power Automate. Ensures both global and individual mappings are included.
    """
    try:
        # Initialize clients
        project_id = os.environ.get('GCP_PROJECT_ID')
        location = os.environ.get('GCP_LOCATION')
        power_automate_url = os.environ.get('POWER_AUTOMATE_WEBHOOK_URL')
        bigquery_table = "dev_cba_analytics.dev_cba_kg_topic_classifier_output"

        # Validate environment variables
        if not project_id or not power_automate_url:
            return {'error': 'Missing required environment variables'}, 400

        # Initialize Vertex AI
        vertexai.init(project=project_id, location=location)

        # Query BigQuery to fetch input data
        bq_client = bigquery.Client(project=project_id)
        query = """
            SELECT
                page_element_placeholder AS cleaned_text,
                invoked_date,
                portal
            FROM `reports.rep_piano_kuendigungsgruende`
            WHERE invoked_date >= "2025-11-01"
                AND page_element_placeholder IS NOT NULL
        """
        query_job = bq_client.query(query)
        results = query_job.result()

        # Collect and validate input data
        texts_metadata = [
            {"cleaned_text": row.cleaned_text, "invoked_date": row.invoked_date, "portal": row.portal}
            for row in results if row.cleaned_text
        ]
        if not texts_metadata:
            return {'message': 'No data found'}, 200

        # **Step 1:** Global prompt to identify all topics across all rows
        combined_text = "\n".join([item["cleaned_text"] for item in texts_metadata])
        global_prompt = f"""Analysiere die folgenden {len(texts_metadata)} Kündigungsgründe und klassifiziere sie in Hauptthemen.
WICHTIG: Antworte direkt mit der Analyse ohne Einleitung wie "Hier ist", "Absolut", etc.
Kündigungsgründe:
{combined_text}
Erstelle eine Zusammenfassung mit:
1. Die Top Themenkategorien (max. 5-10 Kategorien), fett geschrieben im Format "**Kategorie**".
2. Eine kurze Beschreibung jeder Kategorie.
3. Anzahl der Einträge pro Kategorie.
Format: Beginne direkt mit "**Themenkategorien:**"."""
        model = GenerativeModel("gemini-2.5-flash-lite")
        global_response = model.generate_content(global_prompt)
        global_topics_result = global_response.text

        # Debugging: Log raw global response
        print("DEBUG - RAW GLOBAL TOPICS RESULT:", global_topics_result)

        # Extract global topics
        global_topics = extract_topic_names(global_topics_result)
        print("DEBUG - Extracted Global Topics:", global_topics)

        if not global_topics:
            # In case global topics were not extracted, log and return an error
            print("ERROR - No global topics found in Gemini response:", global_topics_result)
            return {'error': 'Failed to extract global topics from Gemini response'}, 500

        # **Step 2:** Individual row mapping using global topics
        rows_to_insert = []
        summary_texts = []

        for item in texts_metadata:
            individual_text = item["cleaned_text"]

            # Create a prompt to map the individual text to a global topic
            mapping_prompt = f"""Analysiere den folgenden Kündigungsgrund und ordne ihn einer der globalen Themenkategorien zu:
Kündigungsgrund:
{individual_text}
Globale Themenkategorien:
{', '.join(global_topics)}
Ermittle die passendste Themenkategorie aus der Liste oben. Format: Gib nur die Themenkategorie als Antwort, z.B., "**Kosten / Preis-Leistungs-Verhältnis**".
"""
            # Call Gemini for individual mapping
            response = model.generate_content(mapping_prompt)
            classification_result = response.text.strip()

            # Debugging: Log individual mapping result
            print(f"DEBUG - Individual Classification for '{individual_text}': {classification_result}")

            # Verify mapping result and prepare BigQuery row
            rows_to_insert.append({
                "original_text": individual_text,
                "classification_result": classification_result if classification_result else None,
                "date": str(item["invoked_date"]),
                "portal": item["portal"]
            })
            summary_texts.append(f"{individual_text}: {classification_result}")

        # **Step 3:** Insert rows into BigQuery
        errors = bq_client.insert_rows_json(
            bigquery_table,
            rows_to_insert,
            retry=bigquery.DEFAULT_RETRY
        )
        if errors:
            print("ERROR - BigQuery Insert Errors:", errors)
            return {'error': f'Failed to write to BigQuery. Errors: {errors}'}, 500

        # Prepare summary message for Power Automate
        safe_global_topics = global_topics_result.replace("\n", "\\n").replace('"', '\\"').replace("\t", " ")  # Clean global topics
        safe_summary = "\n".join(summary_texts).replace("\n", "\\n").replace('"', '\\"').replace("\t", " ")  # Clean individual summary
        message_payload = {
            "title": "Kündigungsgründe Topic Classification Summary",
            "total_entries": str(len(texts_metadata)),
            "classification": safe_global_topics  # Direct inclusion in the `classification` field
        }

        # Debugging: Log Payload for Power Automate
        print("DEBUG - Payload for Teams:", message_payload)

        # Send to Power Automate
        response = requests.post(
            power_automate_url,
            headers={'Content-Type': 'application/json'},
            data=json.dumps(message_payload)
        )
        if response.status_code in [200, 202]:
            return {'message': 'Classification sent to Teams successfully', 'analyzed_count': len(summary_texts)}, 200
        else:
            print("ERROR - Failed to send to Teams. Response:", response.text)
            return {'error': f'Failed to send to Teams. Status: {response.status_code}, Response: {response.text}'}, 500

    except Exception as e:
        print("ERROR - Exception occurred:", str(e))
        return {'error': str(e)}, 500
