"""Generate reviewable CloudFormation JSON with the exact checked-in runtime files."""
import base64
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def ref(name): return {'Ref': name}
def sub(value): return {'Fn::Sub': value}
def attr(name, value): return {'Fn::GetAtt': [name, value]}
def statement(actions, resources, **extra):
    return {'Effect': 'Allow', 'Action': actions, 'Resource': resources, **extra}
def policy(statements): return {'Version': '2012-10-17', 'Statement': statements}
def assume(service):
    return policy([{'Effect':'Allow','Principal':{'Service':service},'Action':'sts:AssumeRole'}])
def encoded(name): return base64.b64encode((HERE/name).read_bytes()).decode()

def template():
    r = {}
    def add(name, kind, props, **extra):
        r[name]={'Type':kind,'Properties':props,**extra}
    tags=[{'Key':'Project','Value':'subway'}]
    az={'Fn::Select':[0, {'Fn::GetAZs':''}]}
    add('Vpc','AWS::EC2::VPC',{'CidrBlock':'10.81.0.0/24','EnableDnsSupport':True,'EnableDnsHostnames':True,'Tags':tags})
    add('Gateway','AWS::EC2::InternetGateway',{'Tags':tags})
    add('GatewayAttachment','AWS::EC2::VPCGatewayAttachment',{'VpcId':ref('Vpc'),'InternetGatewayId':ref('Gateway')})
    add('Subnet','AWS::EC2::Subnet',{'VpcId':ref('Vpc'),'CidrBlock':'10.81.0.0/26','AvailabilityZone':az,'Tags':tags})
    add('RouteTable','AWS::EC2::RouteTable',{'VpcId':ref('Vpc'),'Tags':tags})
    add('Route','AWS::EC2::Route',{'RouteTableId':ref('RouteTable'),'DestinationCidrBlock':'0.0.0.0/0','GatewayId':ref('Gateway')},DependsOn='GatewayAttachment')
    add('SubnetRoute','AWS::EC2::SubnetRouteTableAssociation',{'SubnetId':ref('Subnet'),'RouteTableId':ref('RouteTable')})
    add('SecurityGroup','AWS::EC2::SecurityGroup',{
        'GroupDescription':'Subway public HTTP only; administration uses SSM, no SSH', 'VpcId':ref('Vpc'),
        'SecurityGroupIngress':[{'IpProtocol':'tcp','FromPort':80,'ToPort':80,'CidrIp':'0.0.0.0/0'}],
        'SecurityGroupEgress':[{'IpProtocol':'tcp','FromPort':443,'ToPort':443,'CidrIp':'0.0.0.0/0'},{'IpProtocol':'tcp','FromPort':80,'ToPort':80,'CidrIp':'0.0.0.0/0'}], 'Tags':tags})
    for name, repo in [('BackendRepository','backend'),('FrontendRepository','frontend')]:
        add(name,'AWS::ECR::Repository',{'RepositoryName':f'subway/{repo}','ImageTagMutability':'IMMUTABLE','EncryptionConfiguration':{'EncryptionType':'AES256'},'ImageScanningConfiguration':{'ScanOnPush':True},'Tags':tags},DeletionPolicy='Retain',UpdateReplacePolicy='Retain')
    repos=[attr('BackendRepository','Arn'),attr('FrontendRepository','Arn')]
    add('BackupBucket','AWS::S3::Bucket',{'BucketEncryption':{'ServerSideEncryptionConfiguration':[{'ServerSideEncryptionByDefault':{'SSEAlgorithm':'AES256'}}]},'PublicAccessBlockConfiguration':{'BlockPublicAcls':True,'BlockPublicPolicy':True,'IgnorePublicAcls':True,'RestrictPublicBuckets':True},'OwnershipControls':{'Rules':[{'ObjectOwnership':'BucketOwnerEnforced'}]},'LifecycleConfiguration':{'Rules':[{'Id':'ExpireBackups','Status':'Enabled','Prefix':'backups/','ExpirationInDays':14}]},'Tags':tags},DeletionPolicy='Retain',UpdateReplacePolicy='Retain')
    add('BackupBucketPolicy','AWS::S3::BucketPolicy',{'Bucket':ref('BackupBucket'),'PolicyDocument':policy([{'Effect':'Deny','Principal':'*','Action':'s3:*','Resource':[attr('BackupBucket','Arn'),sub('${BackupBucket.Arn}/*')],'Condition':{'Bool':{'aws:SecureTransport':'false'}}}])})
    add('DataVolume','AWS::EC2::Volume',{'AvailabilityZone':az,'Size':8,'VolumeType':'gp3','Encrypted':True,'Tags':tags},DeletionPolicy='Retain',UpdateReplacePolicy='Retain')
    add('InstanceRole','AWS::IAM::Role',{'AssumeRolePolicyDocument':assume('ec2.amazonaws.com'),'Policies':[{'PolicyName':'SubwayRuntime','PolicyDocument':policy([
        statement(['ssm:UpdateInstanceInformation'], '*'),
        statement(['ssmmessages:CreateControlChannel','ssmmessages:CreateDataChannel','ssmmessages:OpenControlChannel','ssmmessages:OpenDataChannel'],'*'),
        statement(['ecr:GetAuthorizationToken'],'*'),
        statement(['ecr:BatchGetImage','ecr:GetDownloadUrlForLayer','ecr:BatchCheckLayerAvailability'],repos),
        statement(['s3:PutObject'],sub('${BackupBucket.Arn}/backups/*')),
    ])}],'Tags':tags})
    add('InstanceProfile','AWS::IAM::InstanceProfile',{'Roles':[ref('InstanceRole')]})
    userdata='''#!/bin/bash
set -euxo pipefail
export AWS_DEFAULT_REGION=${AWS::Region}
dnf install -y docker python3 util-linux
systemctl enable --now docker amazon-ssm-agent
mkdir -p /usr/local/lib/docker/cli-plugins /opt/subway /srv/subway
curl -fL --retry 5 https://github.com/docker/compose/releases/download/v5.5.1/docker-compose-linux-aarch64 -o /usr/local/lib/docker/cli-plugins/docker-compose
curl -fL --retry 5 https://github.com/docker/compose/releases/download/v5.5.1/docker-compose-linux-aarch64.sha256 -o /tmp/compose.sha256
(cd /usr/local/lib/docker/cli-plugins; sed 's/docker-compose-linux-aarch64/docker-compose/' /tmp/compose.sha256 | sha256sum -c -)
chmod 755 /usr/local/lib/docker/cli-plugins/docker-compose
if [ ! -f /swapfile ]; then
  fallocate -l 1G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
swapon -a
VOLUME_SERIAL=$(echo '${DataVolume}' | tr -d '-')
DEVICE=''
for attempt in $(seq 1 120); do
  DEVICE=$(lsblk -dn -o PATH,SERIAL | awk -v serial="$VOLUME_SERIAL" '$2==serial {print $1}')
  if [ -b "$DEVICE" ]; then break; fi
  sleep 5
done
test -b "$DEVICE"
if ! blkid "$DEVICE"; then mkfs.ext4 "$DEVICE"; fi
UUID=$(blkid -s UUID -o value "$DEVICE")
echo "UUID=$UUID /srv/subway ext4 defaults,nofail 0 2" >> /etc/fstab
mount /srv/subway
mkdir -p /srv/subway/data /srv/subway/backups
chown 10001:10001 /srv/subway/data
chmod 750 /srv/subway/data /srv/subway/backups
cat > /etc/subway.conf <<'ENV'
AWS_ACCOUNT_ID=${AWS::AccountId}
AWS_REGION=${AWS::Region}
BACKUP_BUCKET=${BackupBucket}
ENV
'''
    for name, dest, mode in [('deploy.sh','/usr/local/bin/subway-deploy','755'),('compose.yaml','/opt/subway/compose.yaml','644'),('nginx.conf','/opt/subway/nginx.conf','644')]:
        userdata+=f"printf '%s' '{encoded(name)}' | base64 -d > {dest}\nchmod {mode} {dest}\n"
    userdata+='touch /opt/subway/bootstrap-ready\n'
    add('Instance','AWS::EC2::Instance',{'ImageId':ref('Ami'),'InstanceType':'t4g.micro','IamInstanceProfile':ref('InstanceProfile'),'MetadataOptions':{'HttpTokens':'required','HttpEndpoint':'enabled','HttpPutResponseHopLimit':1},'CreditSpecification':{'CPUCredits':'standard'},'BlockDeviceMappings':[{'DeviceName':'/dev/xvda','Ebs':{'VolumeSize':12,'VolumeType':'gp3','Encrypted':True,'DeleteOnTermination':True}}],'NetworkInterfaces':[{'DeviceIndex':'0','AssociatePublicIpAddress':True,'SubnetId':ref('Subnet'),'GroupSet':[ref('SecurityGroup')]}],'UserData':{'Fn::Base64':sub(userdata)},'Tags':tags+[{'Key':'Name','Value':'subway-production'}]},DependsOn=['Route','SubnetRoute'])
    add('DataAttachment','AWS::EC2::VolumeAttachment',{'Device':'/dev/sdf','InstanceId':ref('Instance'),'VolumeId':ref('DataVolume')})
    add('PublicIp','AWS::EC2::EIP',{'Domain':'vpc','Tags':tags},DependsOn='GatewayAttachment')
    add('PublicIpAssociation','AWS::EC2::EIPAssociation',{'InstanceId':ref('Instance'),'AllocationId':attr('PublicIp','AllocationId')})
    add('GithubProvider','AWS::IAM::OIDCProvider',{'Url':'https://token.actions.githubusercontent.com','ClientIdList':['sts.amazonaws.com'],'Tags':tags})
    add('DeployDocument','AWS::SSM::Document',{'DocumentType':'Command','Name':'subway-deploy','Content':{'schemaVersion':'2.2','description':'Deploy immutable Subway images; shell command text cannot be supplied by callers.','parameters':{'CommitSha':{'type':'String','allowedPattern':'^[0-9a-f]{40}$','description':'Git commit SHA / immutable ECR image tag'}},'mainSteps':[{'action':'aws:runShellScript','name':'Deploy','inputs':{'timeoutSeconds':'1800','runCommand':['/usr/local/bin/subway-deploy {{ CommitSha }}']}}]},'Tags':tags})
    add('GithubRole','AWS::IAM::Role',{'RoleName':'subway-github-deploy','MaxSessionDuration':3600,'AssumeRolePolicyDocument':policy([{'Effect':'Allow','Principal':{'Federated':ref('GithubProvider')},'Action':'sts:AssumeRoleWithWebIdentity','Condition':{'StringEquals':{'token.actions.githubusercontent.com:aud':'sts.amazonaws.com','token.actions.githubusercontent.com:sub':'repo:yeonsung-cloud-mlops@323049364/subway@1379279774:ref:refs/heads/main'}}}]),'Policies':[{'PolicyName':'SubwayImagePublishAndDeploy','PolicyDocument':policy([
        statement(['ecr:GetAuthorizationToken'],'*'),
        statement(['ecr:BatchCheckLayerAvailability','ecr:CompleteLayerUpload','ecr:InitiateLayerUpload','ecr:PutImage','ecr:UploadLayerPart','ecr:BatchGetImage','ecr:GetDownloadUrlForLayer','ecr:DescribeImages'],repos),
        statement(['ssm:SendCommand'],[sub('arn:${AWS::Partition}:ssm:${AWS::Region}:${AWS::AccountId}:document/${DeployDocument}'),sub('arn:${AWS::Partition}:ec2:${AWS::Region}:${AWS::AccountId}:instance/${Instance}')]),
        statement(['ssm:GetCommandInvocation'],'*',Condition={'StringEquals':{'aws:RequestedRegion':ref('AWS::Region')}}),
    ])}],'Tags':tags})
    return {'AWSTemplateFormatVersion':'2010-09-09','Description':'Subway Seoul: ARM EC2, persistent SQLite, private ECR, GitHub main-only OIDC, fixed SSM deployment.','Parameters':{'Ami':{'Type':'AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>','Default':'/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64'}},'Resources':r,'Outputs':{'RoleArn':{'Value':attr('GithubRole','Arn')},'InstanceId':{'Value':ref('Instance')},'PublicIp':{'Value':ref('PublicIp')},'ServiceUrl':{'Value':sub('http://${PublicIp}')},'BackupBucket':{'Value':ref('BackupBucket')},'DataVolumeId':{'Value':ref('DataVolume')},'DeployDocument':{'Value':ref('DeployDocument')}}}

if __name__=='__main__':
    (HERE/'stack.json').write_text(json.dumps(template(),indent=2)+'\n')
