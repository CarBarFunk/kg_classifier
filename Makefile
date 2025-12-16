
# run local server

run_api:
	@uvicorn api.fast:app --reload --port 8000


# trigger CF
trigger_cf:
	@curl -X POST -H "Authorization: Bearer $(shell gcloud auth print-identity-token)" https://kg-topic-classifier-823771140216.europe-west1.run.app
