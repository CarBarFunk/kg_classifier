
# run servers

run_api:
	@uvicorn api.fast:app --reload --port 8000

run_interactive:
	@uvicorn api.interactive:app --reload --port 8080

run_ressort:
	@uvicorn api.ressort:app --reload --port 8010

run_inter_2:
	@uvicorn api.interactive:app --reload --port 8020

run_button:
	@uvicorn api.button:app --reload --port 8090

run_article:
	@uvicorn api.article:app --reload --port 8060


run_all:
	@uvicorn api.all_cf_fast:app --reload --port 8040


# call APIs

teams_test:
	@curl -X POST "http://127.0.0.1:8000/teams/"

teams:
	@curl -X POST "http://127.0.0.1:8000/send_message/"

ask_teams:
	@curl -X POST "http://127.0.0.1:8080/ask_portal/"

select_portal:
	@curl -X POST "http://127.0.0.1:8020/select_portal/"

teams_button:
	@curl -X POST "http://127.0.0.1:8090/send_message_button/"

teams_article:
	@curl -X POST "http://127.0.0.1:8060/send_message_article/"

teams_ressort:
	@curl -X POST "http://127.0.0.1:8010/send_message/"

teams_all:
	@curl -X POST "http://127.0.0.1:8040/send_all_messages/"




# get token
get_token:
	@gcloud auth print-identity-token


# trigger CF
trigger_cf:
	@curl -X POST -H "Authorization: Bearer $(shell gcloud auth print-identity-token)" https://kg-topic-classifier-823771140216.europe-west1.run.app
