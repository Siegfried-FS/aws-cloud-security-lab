#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { CloudSecurityStack } from '../lib/cloud-security-stack';

const app = new cdk.App();

new CloudSecurityStack(app, 'CloudSecurityMasterclassStack', {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT,
    region: process.env.CDK_DEFAULT_REGION || 'us-east-1',
  },
  description: 'AWS CDK Stack para AWS Cloud Security Lab (IAM, Security Groups, S3 y CloudTrail)',
});

app.synth();
