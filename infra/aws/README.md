# 서울 EC2 + GitHub Actions 배포

대상: AWS `410618141864`, 서울 `ap-northeast-2`, GitHub `yeonsung-cloud-mlops/subway`의 `main`.

## 생성된 환경

2026-09-21 `subway-production` 스택 생성 완료. [리소스 식별자](deployment.json)에 EC2, 영속 디스크, 보안 그룹, 백업 버킷을 기록했습니다. Docker Compose 설치와 데이터 볼륨 마운트, IMDSv2 강제 설정을 확인했고 IAM 정책 시뮬레이터에서 배포 역할의 `iam:CreateUser`, `ec2:RunInstances`, `ssm:UpdateDocument`가 거부됨을 확인했습니다.

- 서비스 주소: http://43.203.18.42
- API 문서: http://43.203.18.42/docs
- [배포 실행/결과](https://github.com/yeonsung-cloud-mlops/subway/actions/workflows/deploy.yml)
- 등록 완료 Secrets: `AWS_ROLE_ARN`, `AWS_INSTANCE_ID`. 활성화 변수: `AWS_DEPLOY_ENABLED=true`.
- 앱의 현재 배포 성공 여부와 SHA는 Actions 실행 결과 및 서버의 `/srv/subway/deployed-commit`에서 확인합니다.

### 최초 배포 검증

[Actions 실행 35579690939](https://github.com/yeonsung-cloud-mlops/subway/actions/runs/35579690939)에서 `ec663c455cba30cafdd2510d0a7e090d29c66f20` 배포 성공. 백엔드 61개·브라우저 14개 테스트 통과, OIDC 역할 인증·ECR 게시·SSM 배포를 실제 검증했습니다. 공인 IP를 통한 화면/API 문서/역/원본 조회/전체 경로 예측/잘못된 입력 처리도 통과했습니다.

원본 파일 24개와 승하차 원문 597,970행을 적재했습니다. EC2에서 세 컨테이너 healthy, SQLite 약 707MiB, 사용 가능 RAM 약 426MiB를 확인했습니다(초기 검증 시점의 순간 측정값). 최초 배포에는 기존 DB가 없어 배포 전 백업은 생성되지 않았으며, 다음 배포부터 백업·복구 경로가 적용됩니다.

## 리소스와 비용

- 전용 VPC / 퍼블릭 서브넷 / 인터넷 게이트웨이. NAT Gateway, ALB, RDS 없음.
- Amazon Linux 2023 ARM64, t4g.micro(1GiB RAM), CPU 크레딧 standard(추가 크레딧 과금 없음), 1GiB swap.
- 암호화 gp3 루트 12GiB + SQLite 전용 8GiB. SQLite 디스크는 CloudFormation 삭제 시에도 보존.
- Elastic IP 1개. 외부 인바운드는 HTTP 80만 허용. SSH 키/22 포트 없음. 관리·배포는 SSM.
- private ECR 2개. Git SHA 이미지 태그 변경 불가. 이미지 보존으로 롤백 가능.
- 비공개 암호화 S3 버킷에 배포 전 DB 백업. 14일 후 만료, 로컬 백업은 최근 2개. 일별 정기 백업은 아직 없음.
- 기본 운영비는 소규모 트래픽 기준 월 약 US$15 안팎 예상. EC2/EBS/IPv4는 중지·보존 상태에 따라 계속 과금될 수 있음. 데이터 전송·세금·이미지/백업 누적 저장은 별도. 무료 티어를 가정하지 않음.

## 인증과 최소 권한

장기 IAM 사용자/Access Key 대신 GitHub OIDC와 EC2 instance profile을 사용합니다. [GitHub 공식 OIDC 안내](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws).

GitHub 역할 `subway-github-deploy`:

- `aud=sts.amazonaws.com` 및 이 저장소의 불변 owner/repository ID가 포함된 `main` subject와 정확히 일치해야 함.
- ECR 두 저장소에만 이미지 push/pull 허용.
- 이 EC2 한 대에 `subway-deploy` SSM document만 실행 가능. 인자는 40자리 커밋 SHA만 허용.
- IAM, EC2 생성/변경, SSM document 변경, 임의 shell 명령 전송, S3 접근 권한 없음.
- 인증 토큰 및 명령 결과 조회처럼 리소스 ARN 제한을 지원하지 않는 API에만 `Resource: *` 사용.

EC2 역할:

- SSM Agent 연결 및 상태 보고.
- 해당 ECR 두 저장소에서 pull만 허용.
- 백업 버킷의 `backups/*`에 PutObject만 허용.
- IMDSv2 강제, hop limit 1로 애플리케이션 컨테이너의 instance profile 접근 제한.

GitHub Actions Secrets:

| 이름 | 값 |
|---|---|
| `AWS_ROLE_ARN` | CloudFormation `RoleArn` 출력 |
| `AWS_INSTANCE_ID` | CloudFormation `InstanceId` 출력 |

위 두 값 자체는 비밀번호가 아니지만 사용자 요청에 따라 Secrets로 관리합니다. AWS Access Key, SSH private key, 루트 계정 자격증명은 저장하지 않습니다. `AWS_DEPLOY_ENABLED=true`는 Actions repository variable이며 리소스 준비 후 활성화합니다.

## 재현과 초기 프로비저닝

`render_template.py`가 설치할 스크립트·Compose·Nginx 설정을 `stack.json` 안에 포함합니다. 실제 변경 후 반드시 재생성하고 diff를 검토합니다. 초기 IAM/네트워크 생성 권한은 관리자에게만 필요하며 배포 역할에는 주지 않습니다.

```sh
python3 infra/aws/render_template.py
python3 infra/aws/test_infra.py
cfn-lint infra/aws/stack.json
aws cloudformation validate-template --template-body file://infra/aws/stack.json --region ap-northeast-2
aws cloudformation create-stack --stack-name subway-production \
  --template-body file://infra/aws/stack.json --capabilities CAPABILITY_NAMED_IAM \
  --region ap-northeast-2 --tags Key=Project,Value=subway
aws cloudformation wait stack-create-complete --stack-name subway-production --region ap-northeast-2
aws cloudformation describe-stacks --stack-name subway-production --region ap-northeast-2 --query 'Stacks[0].Outputs'
```

처음 확인한 계정에는 GitHub OIDC provider가 없었습니다. 다른 계정에 기존 provider가 있으면 이 템플릿의 provider 생성/참조를 먼저 조정해야 합니다. 본 템플릿은 이 저장소/계정용이며 임의 다른 저장소 subject를 자동 허용하지 않습니다.

## 배포 흐름

`.github/workflows/deploy.yml`:

1. push/PR/수동 실행 시 ARM runner에서 정책 계약 검사, 백엔드 테스트, 프로덕션 Compose 빌드·통합 검사, Playwright 실행.
2. `main`에서만 OIDC 인증, 동일 ARM 아키텍처로 이미지를 ECR에 게시. 검증된 동일 SHA 태그가 있으면 재사용.
3. SSM document에 SHA를 전달. 서버는 ECR에서 이미지를 받고, 기존 DB를 일관된 SQLite backup API로 스냅샷하여 S3에 보관.
4. 최초 배포 시 공식 원본을 해시 검증 후 적재. 이후에는 영속 DB를 재사용.
5. 새 이미지로 교체 후 healthcheck 및 실제 여정/원본 API 검증. 실패 시 이전 이미지와 직전 DB 스냅샷 복원 시도. 배포는 짧은 중단이 발생하는 단일 인스턴스 방식.

테스트는 AWS 권한 없이 실행하고, fork PR에는 배포 권한이 제공되지 않습니다. Actions는 검증한 commit SHA로 고정합니다. 실행 중 배포를 자동 취소하지 않으며 서버에서도 `flock`으로 중복 배포를 막습니다.

배포 스크립트/Compose/Nginx는 CloudFormation이 서버 초기화 때 설치합니다. 애플리케이션 변경은 Actions로 배포하지만 인프라 파일 변경은 관리자 검토 후 스택 업데이트와 서버 파일 반영이 별도로 필요합니다. 기존 EC2의 user-data 수정만으로 초기화 스크립트가 다시 실행되는 것으로 가정하지 마세요.

## 확인·복구

- AWS SSM Run Command의 실행 결과와 `/var/log/cloud-init-output.log`에서 초기화 상태 확인.
- 설치 완료 표시: `/opt/subway/bootstrap-ready`; 현재 배포 SHA: `/srv/subway/deployed-commit`.
- 서비스 상태: `docker compose --env-file /opt/subway/current.env -f /opt/subway/compose.yaml ps`.
- 수동 롤백: 권한 있는 관리자가 같은 SSM document에 이전 Git SHA 지정. 현재 DB 호환성을 확인하고 필요 시 S3 백업을 별도 복구.
- 실패한 스택을 무조건 삭제/재생성하지 말 것. Retain된 데이터 볼륨·버킷·ECR 리소스가 남음.
- 중지·삭제 전 DB 백업 및 잔존 EBS/EIP/S3/ECR 과금을 점검할 것.

현재 서비스에는 로그인/민감한 사용자 입력이 없고 도메인이 없어 IP HTTP로 공개합니다. 향후 인증이나 개인정보를 다루기 전 도메인과 TLS를 구성하세요.
