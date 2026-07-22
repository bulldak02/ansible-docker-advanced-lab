# Ansible + Docker 고급 실습

RHEL 9.7 Docker Host에 Ansible Role을 이용하여 Nginx, Flask, MariaDB 기반의 3-Tier 서비스를 배포합니다. 단순 설치 예제가 아니라 Blue-Green 릴리스, 컨테이너 health check, 비밀정보 분리, 최소 권한, 리소스 제한, 영속 볼륨, 백업·복원, 통합 검증 및 안전한 삭제를 실습합니다.

## 1. 아키텍처

```text
사용자 :8080
    |
    v
+--------------------+
| Nginx Web           |  외부 포트 8080만 공개
| lab_web             |
+---------+----------+
          |
          | Docker 전용 Bridge Network
          v
+--------------------+       +--------------------+
| Flask Blue         |       | Flask Green        |
| lab_app_blue:8000  |       | lab_app_green:8000 |
+---------+----------+       +----------+---------+
          \                             /
           \                           /
            v                         v
             +-----------------------+
             | MariaDB               |
             | lab_db:3306           |
             | Named Volume 영속화   |
             +-----------------------+
```

Nginx upstream이 Blue 또는 Green 중 하나만 가리키며, `switch.yml`은 전환 대상이 healthy인지 먼저 확인한 뒤 트래픽을 전환합니다.

## 2. 주요 학습 요소

- Role과 include_tasks를 이용한 기능 분리
- `community.docker`의 image, network, volume, container, exec, info 모듈
- Docker BuildKit/buildx 기반 이미지 빌드
- Blue-Green 배포와 즉시 롤백
- Health check 기반 의존성 대기
- App/DB 포트 비공개 및 Nginx 포트만 공개
- non-root App, read-only filesystem, capability drop, no-new-privileges
- CPU, 메모리, PID 제한 및 로그 회전
- MariaDB named volume과 논리 백업·복원
- URI와 SQL을 결합한 End-to-End 검증
- `--check`, `--diff`, 재실행을 통한 멱등성 관찰

## 3. 전제 조건

- Ansible Control Node: RHEL 9.7, ansible-core 2.14.x
- Managed Docker Host: RHEL 9.7
- Control Node에서 Managed Host로 SSH 키 접속 및 sudo 가능
- Managed Host가 Docker 저장소와 컨테이너 이미지 저장소에 접근 가능

현재 예제는 ansible-core 2.14.x와 호환되도록 `community.docker 3.13.1`을 고정합니다. 최신 `community.docker 5.x`는 더 높은 ansible-core 버전을 요구하므로, Control Node를 업그레이드하기 전에는 버전 고정을 유지하십시오.

## 4. 시작하기

### 4.1 Inventory 수정

```ini
[docker_hosts]
docker01 ansible_host=192.168.201.11 ansible_user=nova ansible_ssh_private_key_file=~/.ssh/id_ed25519
```

### 4.2 Collection 설치

```bash
ansible-galaxy collection install -r requirements.yml
ansible-galaxy collection list | grep -E 'community.docker|ansible.posix'
```

### 4.3 비밀번호 공급 방법 A: 환경 변수

```bash
export LAB_DB_ROOT_PASSWORD='Strong-Root-Password-2026!'
export LAB_DB_APP_PASSWORD='Strong-App-Password-2026!'
```

### 4.4 비밀번호 공급 방법 B: Ansible Vault

```bash
cp group_vars/docker_hosts/vault.yml.example \
   group_vars/docker_hosts/vault.yml

vi group_vars/docker_hosts/vault.yml
ansible-vault encrypt group_vars/docker_hosts/vault.yml
```

Vault 사용 시 실행 명령에 `--ask-vault-pass` 또는 vault password file 옵션을 추가합니다.

## 5. 배포

```bash
ansible docker_hosts -m ansible.builtin.ping
ansible-playbook site.yml --syntax-check
ansible-playbook site.yml --ask-vault-pass -K
```

브라우저 또는 curl로 확인합니다.

```bash
curl http://192.168.201.11:8080/
curl http://192.168.201.11:8080/health
curl http://192.168.201.11:8080/api/info
```

## 6. Blue-Green 전환

초기 활성 릴리스는 `group_vars/all.yml`의 `active_color: blue`입니다.

```bash
ansible-playbook switch.yml -e target_color=green
curl http://192.168.201.11:8080/api/info
```

장애가 발견되면 즉시 Blue로 롤백합니다.

```bash
ansible-playbook switch.yml -e target_color=blue
```

새 버전을 배포하려면 `app_releases.green.version`과 `message`를 수정한 뒤 `site.yml`을 다시 실행하고 Green으로 전환합니다. 기존 태그와 같은 이미지가 이미 있으면 다시 빌드하지 않으므로, 소스가 바뀌면 버전 태그도 반드시 올리십시오.

## 7. 통합 검증

```bash
ansible-playbook verify.yml --ask-vault-pass
```

검증 항목은 다음과 같습니다.

1. 외부 Web 포트 연결 가능
2. `/health` HTTP 200
3. Nginx가 지정한 Blue/Green App 응답
4. App에서 MariaDB 접속 성공
5. visits 테이블 생성 및 요청 기록
6. DB 컨테이너 내부에서 직접 SQL 실행

## 8. 백업과 복원

```bash
ansible-playbook backup.yml
sudo ls -lh /opt/ansible-docker-lab/backup/
```

복원 예시:

```bash
ansible-playbook restore.yml \
  -e restore_filename=labdb-20260721T103000.sql
```

## 9. 장애 분석 실습

### App 환경 변수 오류

`DB_HOST`를 잘못 변경한 뒤 재배포하고 다음 명령으로 원인을 확인합니다.

```bash
sudo docker ps
sudo docker inspect lab_app_green
sudo docker logs lab_app_green
ansible-playbook verify.yml -vv
```

### DB 중지

```bash
sudo docker stop lab_db
curl -i http://127.0.0.1:8080/health
sudo docker start lab_db
ansible-playbook verify.yml
```

### Green 장애 후 전환 차단 확인

```bash
sudo docker stop lab_app_green
ansible-playbook switch.yml -e target_color=green
```

전환 대상이 healthy가 아니므로 Playbook이 Nginx 설정 변경 전에 실패해야 합니다.

## 10. 멱등성 검증

```bash
ansible-playbook site.yml
ansible-playbook site.yml
# 최초 배포가 완료된 환경에서 변경 예상 확인
ansible-playbook site.yml --check --diff
```

두 번째 실행에서 불필요한 변경이 최소화되는지 확인합니다. `site.yml`은 check mode에서 최종 HTTP·SQL 검증을 건너뜁니다. 외부 이미지 태그의 변경 가능성과 이미지 빌드 정책은 별도로 관리해야 합니다.

## 11. 삭제

컨테이너와 네트워크만 삭제하고 DB 볼륨 및 백업은 보존합니다.

```bash
ansible-playbook destroy.yml -e confirm_destroy=true
```

DB 볼륨, 백업 디렉터리, 애플리케이션 이미지까지 삭제합니다.

```bash
ansible-playbook destroy.yml \
  -e confirm_destroy=true \
  -e delete_data=true \
  -e remove_images_on_destroy=true
```

## 12. 확장 과제

- Docker Registry에 이미지 push 후 digest로 배포
- Ansible Vault 대신 HashiCorp Vault 또는 Azure Key Vault 연동
- Nginx TLS 인증서 및 HSTS 적용
- Docker Swarm의 rolling update와 secret/config 객체 사용
- Prometheus Node Exporter, cAdvisor, Grafana 추가
- GitHub Actions에서 lint, image scan, 배포 승인 단계 구성
- Trivy 결과가 HIGH/CRITICAL이면 배포 중단
- Molecule을 이용한 Role 테스트
