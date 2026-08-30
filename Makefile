.PHONY: check-prereqs bootstrap-init bootstrap-apply dev-init dev-plan build-push verify demo-ui destroy deploy

check-prereqs:
	bash scripts/check_prereqs.sh

bootstrap-init:
	cd infra/bootstrap && terraform init

bootstrap-apply:
	cd infra/bootstrap && terraform apply

# infra/environments/dev/backend.tf uses partial backend config
# (see backend.hcl.example) -- scripts/bootstrap.sh generates the real
# backend.hcl for you from infra/bootstrap's own output.
dev-init:
	cd infra/environments/dev && terraform init -backend-config=backend.hcl

dev-plan:
	cd infra/environments/dev && terraform plan

build-push:
	bash scripts/build-and-push.sh $(VERSION)

verify:
	bash scripts/verify.sh

demo-ui:
	bash scripts/start-demo.sh

destroy:
	bash scripts/destroy.sh

deploy:
	bash scripts/deploy.sh $(VERSION)
