import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3assets from 'aws-cdk-lib/aws-s3-assets';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import { Construct } from 'constructs';
import * as path from 'path';

export interface CloudSecurityStackProps extends cdk.StackProps {
  communityName?: string;
  speakerMeetupUrl?: string;
}

export class CloudSecurityStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: CloudSecurityStackProps) {
    super(scope, id, props);

    const communityName = this.node.tryGetContext('communityName') || props?.communityName || 'AWS Cloud Security Lab';
    const speakerMeetupUrl = this.node.tryGetContext('speakerMeetupUrl') || props?.speakerMeetupUrl || 'https://www.meetup.com/aws-user-group-playa-vicente/';
    const unamMeetupUrl = this.node.tryGetContext('unamMeetupUrl') || 'https://www.meetup.com/aws-sbg-at-unam/';
    const mixtleDriveUrl = this.node.tryGetContext('mixtleDriveUrl') || 'https://drive.google.com/drive/folders/1Do2TAG4_kNnOXpiiKBc4qSzilOxZQ_N6?usp=drive_link';
    const enableHttp = this.node.tryGetContext('enableHttp') !== false && this.node.tryGetContext('enableHttp') !== 'false';
    const enableUpload = this.node.tryGetContext('enableUpload') !== false && this.node.tryGetContext('enableUpload') !== 'false';

    // -----------------------------------------------------------------------------------------------------------------
    // 1. BUCKET S3 PARA EL MURAL DE FOTOS DE LA SESIÓN (CON AUTO-EXPIRACIÓN EN 2 DÍAS PARA $0 COSTOS)
    // -----------------------------------------------------------------------------------------------------------------
    const photoGalleryBucket = new s3.Bucket(this, 'PhotoGalleryBucket', {
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      lifecycleRules: [
        {
          id: 'AutoDeletePhotosAfter2Days',
          expiration: cdk.Duration.days(2),
          enabled: true,
        },
      ],
    });

    // Desplegar automáticamente la Guía Oficial de Certificaciones AWS en el bucket privado
    new s3deploy.BucketDeployment(this, 'DeployCertificationDoc', {
      sources: [s3deploy.Source.asset(path.join(__dirname, '../assets/docs'))],
      destinationBucket: photoGalleryBucket,
      destinationKeyPrefix: 'docs',
      retainOnDelete: false,
    });

    // -----------------------------------------------------------------------------------------------------------------
    // 2. IAM ROLE & POLÍTICA CON MENOR PRIVILEGIO (TOGGLE S3:PUTOBJECT)
    // -----------------------------------------------------------------------------------------------------------------
    const ec2Role = new iam.Role(this, 'EC2PhotoWallRole', {
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      description: 'IAM Role con menor privilegio para el mural de fotos',
    });

    if (enableUpload) {
      const s3UploadPolicy = new iam.Policy(this, 'S3UploadPolicy', {
        policyName: 'PhotoWall-S3-LeastPrivilege',
        statements: [
          new iam.PolicyStatement({
            sid: 'AllowPhotoGalleryOperations',
            effect: iam.Effect.ALLOW,
            actions: ['s3:PutObject', 's3:GetObject', 's3:ListBucket'],
            resources: [
              photoGalleryBucket.bucketArn,
              photoGalleryBucket.arnForObjects('*'),
            ],
          }),
        ],
      });
      ec2Role.attachInlinePolicy(s3UploadPolicy);
    }

    // -----------------------------------------------------------------------------------------------------------------
    // 3. RED & SECURITY GROUP (TOGGLE STATEFUL FIREWALL)
    // -----------------------------------------------------------------------------------------------------------------
    const vpc = new ec2.Vpc(this, 'SecurityVpc', {
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [
        {
          name: 'Public',
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 24,
        },
      ],
    });

    const webSg = new ec2.SecurityGroup(this, 'WebSecurityGroup', {
      vpc,
      description: 'Security Group para el mural de fotos en vivo',
      allowAllOutbound: true,
    });

    if (enableHttp) {
      webSg.addIngressRule(
        ec2.Peer.anyIpv4(),
        ec2.Port.tcp(80),
        'Permitir trafico HTTP publico para la demo interactiva'
      );
    }

    // -----------------------------------------------------------------------------------------------------------------
    // 4. ASSET DE APLICACIÓN & INSTANCIA EC2 CON USERDATA LIGERO (SIN LÍMITE DE 25KB)
    // -----------------------------------------------------------------------------------------------------------------
    const serverAppAsset = new s3assets.Asset(this, 'ServerAppAsset', {
      path: path.join(__dirname, '../assets/server.py'),
    });
    serverAppAsset.grantRead(ec2Role);

    const userData = ec2.UserData.forLinux();
    userData.addCommands(
      'command -v python3 >/dev/null 2>&1 && command -v aws >/dev/null 2>&1 || dnf install -y python3 awscli',
      'mkdir -p /opt/cloudsec-app/uploads /opt/cloudsec-app/docs',
      'cd /opt/cloudsec-app',
      'for i in {1..20}; do',
      `  aws s3 cp s3://${serverAppAsset.s3BucketName}/${serverAppAsset.s3ObjectKey} /opt/cloudsec-app/server.py --region ${this.region} && break`,
      '  echo "Esperando credenciales S3 e intentando de nuevo ($i/20)..."',
      '  sleep 3',
      'done',
      `aws s3 cp s3://${photoGalleryBucket.bucketName}/docs/ /opt/cloudsec-app/docs/ --recursive --region ${this.region} || true`,
      'chmod 755 /opt/cloudsec-app/server.py',
      'cat << EOF_SERVICE > /etc/systemd/system/cloudsec-app.service',
      '[Unit]',
      'Description=Cloud Security Photo Wall Live Demo',
      'After=network.target',
      '',
      '[Service]',
      'Type=simple',
      'User=root',
      'WorkingDirectory=/opt/cloudsec-app',
      `Environment="BUCKET_NAME=${photoGalleryBucket.bucketName}"`,
      `Environment="COMMUNITY_NAME=${communityName}"`,
      `Environment="SPEAKER_MEETUP_URL=${speakerMeetupUrl}"`,
      `Environment="UNAM_MEETUP_URL=${unamMeetupUrl}"`,
      `Environment="MIXTLE_DRIVE_URL=${mixtleDriveUrl}"`,
      `Environment="AWS_REGION=${this.region}"`,
      'ExecStart=/usr/bin/python3 /opt/cloudsec-app/server.py',
      'Restart=always',
      'RestartSec=3',
      '',
      '[Install]',
      'WantedBy=multi-user.target',
      'EOF_SERVICE',
      'systemctl daemon-reload',
      'systemctl enable cloudsec-app',
      'systemctl start cloudsec-app'
    );

    const instance = new ec2.Instance(this, 'SecurityDemoInstance', {
      vpc,
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.T2, ec2.InstanceSize.MICRO),
      machineImage: ec2.MachineImage.latestAmazonLinux2023(),
      role: ec2Role,
      securityGroup: webSg,
      vpcSubnets: { subnetType: ec2.SubnetType.PUBLIC },
      userData,
    });

    new cdk.CfnOutput(this, 'Ec2PublicIp', {
      value: instance.instancePublicIp,
      description: 'Direccion IP publica de la instancia EC2',
    });

    new cdk.CfnOutput(this, 'WebDemoUrl', {
      value: `http://${instance.instancePublicIp}`,
      description: 'URL publica para abrir en navegador y sincronizar con el QR',
    });

    new cdk.CfnOutput(this, 'PhotoGalleryBucketName', {
      value: photoGalleryBucket.bucketName,
      description: 'Nombre del bucket Amazon S3 para el mural de fotos',
    });
  }
}
