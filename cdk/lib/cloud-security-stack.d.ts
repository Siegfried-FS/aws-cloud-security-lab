import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
export interface CloudSecurityStackProps extends cdk.StackProps {
    labName?: string;
}
export declare class CloudSecurityStack extends cdk.Stack {
    constructor(scope: Construct, id: string, props?: CloudSecurityStackProps);
}
