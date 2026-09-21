"""Safety/reproducibility contracts for the live deployment boundary."""
import json
import unittest
from pathlib import Path
from render_template import template

class InfrastructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template=json.loads(Path(__file__).with_name('stack.json').read_text())
        cls.resources=cls.template['Resources']

    def test_generated_template_matches_reviewed_sources(self):
        self.assertEqual(self.template, template())

    def test_oidc_only_exact_repository_main_and_audience(self):
        trust=self.resources['GithubRole']['Properties']['AssumeRolePolicyDocument']['Statement']
        self.assertEqual(len(trust),1)
        condition=trust[0]['Condition']['StringEquals']
        self.assertEqual(condition['token.actions.githubusercontent.com:aud'],'sts.amazonaws.com')
        self.assertEqual(condition['token.actions.githubusercontent.com:sub'],'repo:yeonsung-cloud-mlops@323049364/subway@1379279774:ref:refs/heads/main')
        self.assertNotIn('*', condition['token.actions.githubusercontent.com:sub'])

    def test_no_persistent_credentials_or_ssh(self):
        self.assertFalse(any(r['Type'] in ('AWS::IAM::User','AWS::IAM::AccessKey','AWS::EC2::KeyPair') for r in self.resources.values()))
        ingress=self.resources['SecurityGroup']['Properties']['SecurityGroupIngress']
        self.assertEqual(ingress,[{'IpProtocol':'tcp','FromPort':80,'ToPort':80,'CidrIp':'0.0.0.0/0'}])
        self.assertEqual(self.resources['Instance']['Properties']['MetadataOptions']['HttpTokens'],'required')
        self.assertEqual(self.resources['Instance']['Properties']['MetadataOptions']['HttpPutResponseHopLimit'],1)

    def test_deployer_cannot_provision_or_execute_arbitrary_ssm_commands(self):
        statements=self.resources['GithubRole']['Properties']['Policies'][0]['PolicyDocument']['Statement']
        actions={a for s in statements for a in s['Action']}
        self.assertFalse(any(a.startswith(('iam:','ec2:','cloudformation:','s3:')) or '*' in a for a in actions))
        send=next(s for s in statements if 'ssm:SendCommand' in s['Action'])
        self.assertEqual(len(send['Resource']),2)
        self.assertIn('${Instance}',json.dumps(send))
        self.assertIn('${DeployDocument}',json.dumps(send))
        doc=self.resources['DeployDocument']['Properties']['Content']
        self.assertEqual(doc['parameters']['CommitSha']['allowedPattern'],'^[0-9a-f]{40}$')
        self.assertEqual(doc['mainSteps'][0]['inputs']['runCommand'],['/usr/local/bin/subway-deploy {{ CommitSha }}'])

    def test_sqlite_and_backup_retention(self):
        volume=self.resources['DataVolume']
        self.assertTrue(volume['Properties']['Encrypted'])
        self.assertEqual(volume['DeletionPolicy'],'Retain')
        bucket=self.resources['BackupBucket']
        self.assertTrue(all(bucket['Properties']['PublicAccessBlockConfiguration'].values()))
        self.assertEqual(bucket['DeletionPolicy'],'Retain')
        for name in ('BackendRepository','FrontendRepository'):
            self.assertEqual(self.resources[name]['Properties']['ImageTagMutability'],'IMMUTABLE')

if __name__=='__main__': unittest.main()
