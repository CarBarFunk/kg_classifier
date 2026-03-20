import functions_framework
from google.cloud import bigquery
import vertexai
from vertexai.generative_models import GenerativeModel
import os
import re


TOPICS = [
    "Nur ein Artikel",
    "Livestreams",
    "Sonstiges - Zu teuer",
    "Sonstiges - Zu selten",
    "Sonstiges - Inhalte",
    "UX",
    "Umzug",
    "Anderes",
]


@functions_framework.http
def classify_topics(request):
    try:
        project_id = os.environ.get("GCP_PROJECT_ID")
        location = os.environ.get("GCP_LOCATION")
        bq_output_table = os.environ.get("BQ_OUTPUT_TABLE")

        if not project_id:
            return {"error": "Missing GCP_PROJECT_ID environment variable"}, 400

        vertexai.init(project=project_id, location=location)
        bq_client = bigquery.Client(project=project_id)

        # Get data from BQ
        query = """
            SELECT
                invoked_date as date,
                FORMAT_DATE('%Y-%m', invoked_date) AS month,
                standort,
                portal,
                page_element_placeholder AS reason
            FROM `analytics.fact_piano_kuendigungsgruende`
            WHERE date_trunc(invoked_date, month) = date_trunc(date_sub(current_date(), interval 1 month), month)
                AND page_element_placeholder IS NOT NULL
        """
        texts_metadata = [
            {
                "date": str(r.date),
                "month": r.month,
                "standort": r.standort,
                "portal": r.portal,
                "reason": r.reason
            }
            for r in bq_client.query(query).result()
            if r.reason
        ]

        if not texts_metadata:
            return {"message": "No data found"}, 200

        model = GenerativeModel("gemini-2.5-flash")
        topics_list_str = "\n".join(f"- {t}" for t in TOPICS)

        # Map each row to a topic with Gemini (batched)
        batch_size = 50
        rows_to_insert = []

        for batch_start in range(0, len(texts_metadata), batch_size):
            batch = texts_metadata[batch_start: batch_start + batch_size]
            numbered = "\n".join(
                f"Zeile {i + 1}: {item['reason']}"
                for i, item in enumerate(batch)
            )
            mapping_prompt = (
                f"""Ordne jeden der folgenden Kündigungsgründe genau einer der vorgegebenen Themenkategorien zu.
                Nur ein Artikel wenn der Nutzer nur ein Artikel lesen wollte.
                Livestreams wenn es mit Livestreams zu tun hat.
                Sonstiges - Zu teuer wenn es mit dem Preis zu tun hat.
                Sonstiges - Zu selten wenn der Nutzer den Abo zu selten genutzt hatte.
                Sonstiges - Inhalte wenn der Nutzer unzufriden mit der Qualität der Inhalte/Artikel ist.
                UX wenn es mit der User Experience zu tun hat, z.B. Probleme beim Login oder bei der Steuerung der Webseite oder Verwaltung des Abovertrags.
                Umzug wenn der Nutzer in eine andere Stadt/Region umzieht und der Abo dann nicht mehr relevant ist.
                Anderes für alle Fälle, die nicht in den gelisteten Topics abgedeckt sind.
                 \n\n"""
                f"Themenkategorien:\n{topics_list_str}\n\n"
                f"Kündigungsgründe:\n{numbered}\n\n"
                "Antworte mit genau einer Zeile pro Eintrag im Format:\n"
                "Zeile N: Kategoriename\n"
                "Verwende ausschließlich Kategorien aus der obigen Liste, ohne Anführungszeichen oder Formatierung."
            )
            batch_lines = model.generate_content(mapping_prompt).text.strip().split("\n")
            print(f"DEBUG - Batch {batch_start}: {batch_lines}")

            for i, item in enumerate(batch):
                raw = batch_lines[i].strip() if i < len(batch_lines) else "Anderes"
                # Extract everything after "Zeile N: "
                topic_raw = re.sub(r"^Zeile\s+\d+:\s*", "", raw).strip()
                # Fall back to "Anderes" if the result is not in the known list
                topic = topic_raw if topic_raw in TOPICS else "Anderes"

                rows_to_insert.append({
                    "date": item["date"],
                    "month": item["month"],
                    "standort": item["standort"],
                    "portal": item["portal"],
                    "reason": item["reason"],
                    "topic": topic,
                })

        # Append to BigQuery
        errors = bq_client.insert_rows_json(
            bq_output_table,
            rows_to_insert,
            retry=bigquery.DEFAULT_RETRY,
        )
        if errors:
            print("ERROR - BigQuery insert errors:", errors)
            return {"error": f"Failed to write to BigQuery: {errors}"}, 500

        print(f"SUCCESS - Inserted {len(rows_to_insert)} rows into {bq_output_table}")
        return {"message": "Done", "rows_inserted": len(rows_to_insert)}, 200

    except Exception as e:
        print("ERROR:", str(e))
        return {"error": str(e)}, 500
