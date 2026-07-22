SHELL := /bin/bash

.PHONY: collections ping syntax deploy verify green blue backup destroy destroy-all

collections:
	ansible-galaxy collection install -r requirements.yml

ping:
	ansible docker_hosts -m ansible.builtin.ping

syntax:
	ansible-playbook site.yml --syntax-check

# 실행 전 LAB_DB_ROOT_PASSWORD, LAB_DB_APP_PASSWORD 환경 변수 필요
deploy:
	ansible-playbook site.yml

verify:
	ansible-playbook verify.yml

green:
	ansible-playbook switch.yml -e target_color=green

blue:
	ansible-playbook switch.yml -e target_color=blue

backup:
	ansible-playbook backup.yml

destroy:
	ansible-playbook destroy.yml -e confirm_destroy=true

destroy-all:
	ansible-playbook destroy.yml -e confirm_destroy=true -e delete_data=true -e remove_images_on_destroy=true
