.PHONY: check-prereqs bootstrap-init bootstrap-apply dev-init dev-plan

check-prereqs:
	bash scripts/check_prereqs.sh

bootstrap-init:
	cd infra/bootstrap && terraform init

bootstrap-apply:
	cd infra/bootstrap && terraform apply

dev-init:
	cd infra/environments/dev && terraform init

dev-plan:
	cd infra/environments/dev && terraform plan
