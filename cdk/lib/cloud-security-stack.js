"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.CloudSecurityStack = void 0;
const cdk = require("aws-cdk-lib");
const ec2 = require("aws-cdk-lib/aws-ec2");
const iam = require("aws-cdk-lib/aws-iam");
const s3 = require("aws-cdk-lib/aws-s3");
const s3assets = require("aws-cdk-lib/aws-s3-assets");
const s3deploy = require("aws-cdk-lib/aws-s3-deployment");
const path = require("path");
class CloudSecurityStack extends cdk.Stack {
    constructor(scope, id, props) {
        super(scope, id, props);
        const labName = this.node.tryGetContext('labName') || props?.labName || 'AWS Cloud Security Lab';
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
        // Desplegar automáticamente la Guía de Referencia de Seguridad en el bucket privado
        new s3deploy.BucketDeployment(this, 'DeploySecurityReferenceDoc', {
            sources: [s3deploy.Source.asset(path.join(__dirname, '../assets/sample-docs'))],
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
            webSg.addIngressRule(ec2.Peer.anyIpv4(), ec2.Port.tcp(80), 'Permitir trafico HTTP publico para la demo interactiva');
        }
        // -----------------------------------------------------------------------------------------------------------------
        // 4. ASSET DE APLICACIÓN & INSTANCIA EC2 CON USERDATA LIGERO (SIN LÍMITE DE 25KB)
        // -----------------------------------------------------------------------------------------------------------------
        const serverAppAsset = new s3assets.Asset(this, 'ServerAppAsset', {
            path: path.join(__dirname, '../assets/server.py'),
        });
        serverAppAsset.grantRead(ec2Role);
        const userData = ec2.UserData.forLinux();
        userData.addCommands('command -v python3 >/dev/null 2>&1 && command -v aws >/dev/null 2>&1 || dnf install -y python3 awscli', 'mkdir -p /opt/cloudsec-app/uploads /opt/cloudsec-app/docs', 'cd /opt/cloudsec-app', 'for i in {1..20}; do', `  aws s3 cp s3://${serverAppAsset.s3BucketName}/${serverAppAsset.s3ObjectKey} /opt/cloudsec-app/server.py --region ${this.region} && break`, '  echo "Esperando credenciales S3 e intentando de nuevo ($i/20)..."', '  sleep 3', 'done', `aws s3 cp s3://${photoGalleryBucket.bucketName}/docs/ /opt/cloudsec-app/docs/ --recursive --region ${this.region} || true`, 'chmod 755 /opt/cloudsec-app/server.py', 'cat << EOF_SERVICE > /etc/systemd/system/cloudsec-app.service', '[Unit]', 'Description=Cloud Security Photo Wall Live Demo', 'After=network.target', '', '[Service]', 'Type=simple', 'User=root', 'WorkingDirectory=/opt/cloudsec-app', `Environment="BUCKET_NAME=${photoGalleryBucket.bucketName}"`, `Environment="COMMUNITY_NAME=${labName}"`, `Environment="EVENT_NAME=Detección y Mitigación de 4 Puntos Ciegos"`, `Environment="REPO_URL=https://github.com/Siegfried-FS/aws-cloud-security-lab"`, `Environment="DOCS_URL=https://docs.aws.amazon.com/security/"`, `Environment="DEMO_DOC_NAME=aws_cloud_security_reference_guide.pdf"`, `Environment="AWS_REGION=${this.region}"`, 'ExecStart=/usr/bin/python3 /opt/cloudsec-app/server.py', 'Restart=always', 'RestartSec=3', '', '[Install]', 'WantedBy=multi-user.target', 'EOF_SERVICE', 'systemctl daemon-reload', 'systemctl enable cloudsec-app', 'systemctl start cloudsec-app');
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
exports.CloudSecurityStack = CloudSecurityStack;
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoiY2xvdWQtc2VjdXJpdHktc3RhY2suanMiLCJzb3VyY2VSb290IjoiIiwic291cmNlcyI6WyJjbG91ZC1zZWN1cml0eS1zdGFjay50cyJdLCJuYW1lcyI6W10sIm1hcHBpbmdzIjoiOzs7QUFBQSxtQ0FBbUM7QUFDbkMsMkNBQTJDO0FBQzNDLDJDQUEyQztBQUMzQyx5Q0FBeUM7QUFDekMsc0RBQXNEO0FBQ3RELDBEQUEwRDtBQUUxRCw2QkFBNkI7QUFNN0IsTUFBYSxrQkFBbUIsU0FBUSxHQUFHLENBQUMsS0FBSztJQUMvQyxZQUFZLEtBQWdCLEVBQUUsRUFBVSxFQUFFLEtBQStCO1FBQ3ZFLEtBQUssQ0FBQyxLQUFLLEVBQUUsRUFBRSxFQUFFLEtBQUssQ0FBQyxDQUFDO1FBRXhCLE1BQU0sT0FBTyxHQUFHLElBQUksQ0FBQyxJQUFJLENBQUMsYUFBYSxDQUFDLFNBQVMsQ0FBQyxJQUFJLEtBQUssRUFBRSxPQUFPLElBQUksd0JBQXdCLENBQUM7UUFDakcsTUFBTSxVQUFVLEdBQUcsSUFBSSxDQUFDLElBQUksQ0FBQyxhQUFhLENBQUMsWUFBWSxDQUFDLEtBQUssS0FBSyxJQUFJLElBQUksQ0FBQyxJQUFJLENBQUMsYUFBYSxDQUFDLFlBQVksQ0FBQyxLQUFLLE9BQU8sQ0FBQztRQUN4SCxNQUFNLFlBQVksR0FBRyxJQUFJLENBQUMsSUFBSSxDQUFDLGFBQWEsQ0FBQyxjQUFjLENBQUMsS0FBSyxLQUFLLElBQUksSUFBSSxDQUFDLElBQUksQ0FBQyxhQUFhLENBQUMsY0FBYyxDQUFDLEtBQUssT0FBTyxDQUFDO1FBRTlILG9IQUFvSDtRQUNwSCxrR0FBa0c7UUFDbEcsb0hBQW9IO1FBQ3BILE1BQU0sa0JBQWtCLEdBQUcsSUFBSSxFQUFFLENBQUMsTUFBTSxDQUFDLElBQUksRUFBRSxvQkFBb0IsRUFBRTtZQUNuRSxpQkFBaUIsRUFBRSxFQUFFLENBQUMsaUJBQWlCLENBQUMsU0FBUztZQUNqRCxVQUFVLEVBQUUsRUFBRSxDQUFDLGdCQUFnQixDQUFDLFVBQVU7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RztZQUNILFlBQVksRUFBRSxHQUFHLENBQUMsWUFBWSxDQUFDLEVBQUUsQ0FBQyxHQUFHLENBQUMsYUFBYSxDQUFDLEVBQUUsRUFBRSxHQUFHLENBQUMsWUFBWSxDQUFDLEtBQUssQ0FBQztZQUMvRSxZQUFZLEVBQUUsR0FBRyxDQUFDLFlBQVksQ0FBQyxxQkFBcUIsRUFBRTtZQUN0RCxJQUFJLEVBQUUsT0FBTztZQUNiLGFBQWEsRUFBRSxLQUFLO1lBQ3BCLFVBQVUsRUFBRSxFQUFFLFVBQVUsRUFBRSxHQUFHLENBQUMsVUFBVSxDQUFDLE1BQU0sRUFBRTtZQUNqRCxRQUFRO1NBQ1QsQ0FBQyxDQUFDO1FBRUgsSUFBSSxHQUFHLENBQUMsU0FBUyxDQUFDLElBQUksRUFBRSxhQUFhLEVBQUU7WUFDckMsS0FBSyxFQUFFLFFBQVEsQ0FBQyxnQkFBZ0I7WUFDaEMsV0FBVyxFQUFFLDBDQUEwQztTQUN4RCxDQUFDLENBQUM7UUFFSCxJQUFJLEdBQUcsQ0FBQyxTQUFTLENBQUMsSUFBSSxFQUFFLFlBQVksRUFBRTtZQUNwQyxLQUFLLEVBQUUsVUFBVSxRQUFRLENBQUMsZ0JBQWdCLEVBQUU7WUFDNUMsV0FBVyxFQUFFLDZEQUE2RDtTQUMzRSxDQUFDLENBQUM7UUFFSCxJQUFJLEdBQUcsQ0FBQyxTQUFTLENBQUMsSUFBSSxFQUFFLHdCQUF3QixFQUFFO1lBQ2hELEtBQUssRUFBRSxrQkFBa0IsQ0FBQyxVQUFVO1lBQ3BDLFdBQVcsRUFBRSxvREFBb0Q7U0FDbEUsQ0FBQyxDQUFDO0lBQ0wsQ0FBQztDQUNGO0FBbEtELGdEQWtLQyIsInNvdXJjZXNDb250ZW50IjpbImltcG9ydCAqIGFzIGNkayBmcm9tICdhd3MtY2RrLWxpYic7XG5pbXBvcnQgKiBhcyBlYzIgZnJvbSAnYXdzLWNkay1saWIvYXdzLWVjMic7XG5pbXBvcnQgKiBhcyBpYW0gZnJvbSAnYXdzLWNkay1saWIvYXdzLWlhbSc7XG5pbXBvcnQgKiBhcyBzMyBmcm9tICdhd3MtY2RrLWxpYi9hd3MtczMnO1xuaW1wb3J0ICogYXMgczNhc3NldHMgZnJvbSAnYXdzLWNkay1saWIvYXdzLXMzLWFzc2V0cyc7XG5pbXBvcnQgKiBhcyBzM2RlcGxveSBmcm9tICdhd3MtY2RrLWxpYi9hd3MtczMtZGVwbG95bWVudCc7XG5pbXBvcnQgeyBDb25zdHJ1Y3QgfSBmcm9tICdjb25zdHJ1Y3RzJztcbmltcG9ydCAqIGFzIHBhdGggZnJvbSAncGF0aCc7XG5cbmV4cG9ydCBpbnRlcmZhY2UgQ2xvdWRTZWN1cml0eVN0YWNrUHJvcHMgZXh0ZW5kcyBjZGsuU3RhY2tQcm9wcyB7XG4gIGxhYk5hbWU/OiBzdHJpbmc7XG59XG5cbmV4cG9ydCBjbGFzcyBDbG91ZFNlY3VyaXR5U3RhY2sgZXh0ZW5kcyBjZGsuU3RhY2sge1xuICBjb25zdHJ1Y3RvcihzY29wZTogQ29uc3RydWN0LCBpZDogc3RyaW5nLCBwcm9wcz86IENsb3VkU2VjdXJpdHlTdGFja1Byb3BzKSB7XG4gICAgc3VwZXIoc2NvcGUsIGlkLCBwcm9wcyk7XG5cbiAgICBjb25zdCBsYWJOYW1lID0gdGhpcy5ub2RlLnRyeUdldENvbnRleHQoJ2xhYk5hbWUnKSB8fCBwcm9wcz8ubGFiTmFtZSB8fCAnQVdTIENsb3VkIFNlY3VyaXR5IExhYic7XG4gICAgY29uc3QgZW5hYmxlSHR0cCA9IHRoaXMubm9kZS50cnlHZXRDb250ZXh0KCdlbmFibGVIdHRwJykgIT09IGZhbHNlICYmIHRoaXMubm9kZS50cnlHZXRDb250ZXh0KCdlbmFibGVIdHRwJykgIT09ICdmYWxzZSc7XG4gICAgY29uc3QgZW5hYmxlVXBsb2FkID0gdGhpcy5ub2RlLnRyeUdldENvbnRleHQoJ2VuYWJsZVVwbG9hZCcpICE9PSBmYWxzZSAmJiB0aGlzLm5vZGUudHJ5R2V0Q29udGV4dCgnZW5hYmxlVXBsb2FkJykgIT09ICdmYWxzZSc7XG5cbiAgICAvLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLVxuICAgIC8vIDEuIEJVQ0tFVCBTMyBQQVJBIEVMIE1VUkFMIERFIEZPVE9TIERFIExBIFNFU0nDk04gKENPTiBBVVRPLUVYUElSQUNJw5NOIEVOIDIgRMONQVMgUEFSQSAkMCBDT1NUT1MpXG4gICAgLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS1cbiAgICBjb25zdCBwaG90b0dhbGxlcnlCdWNrZXQgPSBuZXcgczMuQnVja2V0KHRoaXMsICdQaG90b0dhbGxlcnlCdWNrZXQnLCB7XG4gICAgICBibG9ja1B1YmxpY0FjY2VzczogczMuQmxvY2tQdWJsaWNBY2Nlc3MuQkxPQ0tfQUxMLFxuICAgICAgZW5jcnlwdGlvbjogczMuQnVja2V0RW5jcnlwdGlvbi5TM19NQU5BR0VELFxuICAgICAgZW5mb3JjZVNTTDogdHJ1ZSxcbiAgICAgIHJlbW92YWxQb2xpY3k6IGNkay5SZW1vdmFsUG9saWN5LkRFU1RST1ksXG4gICAgICBhdXRvRGVsZXRlT2JqZWN0czogdHJ1ZSxcbiAgICAgIGxpZmVjeWNsZVJ1bGVzOiBbXG4gICAgICAgIHtcbiAgICAgICAgICBpZDogJ0F1dG9EZWxldGVQaG90b3NBZnRlcjJEYXlzJyxcbiAgICAgICAgICBleHBpcmF0aW9uOiBjZGsuRHVyYXRpb24uZGF5cygyKSxcbiAgICAgICAgICBlbmFibGVkOiB0cnVlLFxuICAgICAgICB9LFxuICAgICAgXSxcbiAgICB9KTtcblxuICAgIC8vIERlc3BsZWdhciBhdXRvbcOhdGljYW1lbnRlIGxhIEd1w61hIGRlIFJlZmVyZW5jaWEgZGUgU2VndXJpZGFkIGVuIGVsIGJ1Y2tldCBwcml2YWRvXG4gICAgbmV3IHMzZGVwbG95LkJ1Y2tldERlcGxveW1lbnQodGhpcywgJ0RlcGxveVNlY3VyaXR5UmVmZXJlbmNlRG9jJywge1xuICAgICAgc291cmNlczogW3MzZGVwbG95LlNvdXJjZS5hc3NldChwYXRoLmpvaW4oX19kaXJuYW1lLCAnLi4vYXNzZXRzL3NhbXBsZS1kb2NzJykpXSxcbiAgICAgIGRlc3RpbmF0aW9uQnVja2V0OiBwaG90b0dhbGxlcnlCdWNrZXQsXG4gICAgICBkZXN0aW5hdGlvbktleVByZWZpeDogJ2RvY3MnLFxuICAgICAgcmV0YWluT25EZWxldGU6IGZhbHNlLFxuICAgIH0pO1xuXG4gICAgLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS1cbiAgICAvLyAyLiBJQU0gUk9MRSAmIFBPTMONVElDQSBDT04gTUVOT1IgUFJJVklMRUdJTyAoVE9HR0xFIFMzOlBVVE9CSkVDVClcbiAgICAvLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLVxuICAgIGNvbnN0IGVjMlJvbGUgPSBuZXcgaWFtLlJvbGUodGhpcywgJ0VDMlBob3RvV2FsbFJvbGUnLCB7XG4gICAgICBhc3N1bWVkQnk6IG5ldyBpYW0uU2VydmljZVByaW5jaXBhbCgnZWMyLmFtYXpvbmF3cy5jb20nKSxcbiAgICAgIGRlc2NyaXB0aW9uOiAnSUFNIFJvbGUgY29uIG1lbm9yIHByaXZpbGVnaW8gcGFyYSBlbCBtdXJhbCBkZSBmb3RvcycsXG4gICAgfSk7XG5cbiAgICBpZiAoZW5hYmxlVXBsb2FkKSB7XG4gICAgICBjb25zdCBzM1VwbG9hZFBvbGljeSA9IG5ldyBpYW0uUG9saWN5KHRoaXMsICdTM1VwbG9hZFBvbGljeScsIHtcbiAgICAgICAgcG9saWN5TmFtZTogJ1Bob3RvV2FsbC1TMy1MZWFzdFByaXZpbGVnZScsXG4gICAgICAgIHN0YXRlbWVudHM6IFtcbiAgICAgICAgICBuZXcgaWFtLlBvbGljeVN0YXRlbWVudCh7XG4gICAgICAgICAgICBzaWQ6ICdBbGxvd1Bob3RvR2FsbGVyeU9wZXJhdGlvbnMnLFxuICAgICAgICAgICAgZWZmZWN0OiBpYW0uRWZmZWN0LkFMTE9XLFxuICAgICAgICAgICAgYWN0aW9uczogWydzMzpQdXRPYmplY3QnLCAnczM6R2V0T2JqZWN0JywgJ3MzOkxpc3RCdWNrZXQnXSxcbiAgICAgICAgICAgIHJlc291cmNlczogW1xuICAgICAgICAgICAgICBwaG90b0dhbGxlcnlCdWNrZXQuYnVja2V0QXJuLFxuICAgICAgICAgICAgICBwaG90b0dhbGxlcnlCdWNrZXQuYXJuRm9yT2JqZWN0cygnKicpLFxuICAgICAgICAgICAgXSxcbiAgICAgICAgICB9KSxcbiAgICAgICAgXSxcbiAgICAgIH0pO1xuICAgICAgZWMyUm9sZS5hdHRhY2hJbmxpbmVQb2xpY3koczNVcGxvYWRQb2xpY3kpO1xuICAgIH1cblxuICAgIC8vIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tXG4gICAgLy8gMy4gUkVEICYgU0VDVVJJVFkgR1JPVVAgKFRPR0dMRSBTVEFURUZVTCBGSVJFV0FMTClcbiAgICAvLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLVxuICAgIGNvbnN0IHZwYyA9IG5ldyBlYzIuVnBjKHRoaXMsICdTZWN1cml0eVZwYycsIHtcbiAgICAgIG1heEF6czogMixcbiAgICAgIG5hdEdhdGV3YXlzOiAwLFxuICAgICAgc3VibmV0Q29uZmlndXJhdGlvbjogW1xuICAgICAgICB7XG4gICAgICAgICAgbmFtZTogJ1B1YmxpYycsXG4gICAgICAgICAgc3VibmV0VHlwZTogZWMyLlN1Ym5ldFR5cGUuUFVCTElDLFxuICAgICAgICAgIGNpZHJNYXNrOiAyNCxcbiAgICAgICAgfSxcbiAgICAgIF0sXG4gICAgfSk7XG5cbiAgICBjb25zdCB3ZWJTZyA9IG5ldyBlYzIuU2VjdXJpdHlHcm91cCh0aGlzLCAnV2ViU2VjdXJpdHlHcm91cCcsIHtcbiAgICAgIHZwYyxcbiAgICAgIGRlc2NyaXB0aW9uOiAnU2VjdXJpdHkgR3JvdXAgcGFyYSBlbCBtdXJhbCBkZSBmb3RvcyBlbiB2aXZvJyxcbiAgICAgIGFsbG93QWxsT3V0Ym91bmQ6IHRydWUsXG4gICAgfSk7XG5cbiAgICBpZiAoZW5hYmxlSHR0cCkge1xuICAgICAgd2ViU2cuYWRkSW5ncmVzc1J1bGUoXG4gICAgICAgIGVjMi5QZWVyLmFueUlwdjQoKSxcbiAgICAgICAgZWMyLlBvcnQudGNwKDgwKSxcbiAgICAgICAgJ1Blcm1pdGlyIHRyYWZpY28gSFRUUCBwdWJsaWNvIHBhcmEgbGEgZGVtbyBpbnRlcmFjdGl2YSdcbiAgICAgICk7XG4gICAgfVxuXG4gICAgLy8gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS1cbiAgICAvLyA0LiBBU1NFVCBERSBBUExJQ0FDScOTTiAmIElOU1RBTkNJQSBFQzIgQ09OIFVTRVJEQVRBIExJR0VSTyAoU0lOIEzDjU1JVEUgREUgMjVLQilcbiAgICAvLyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLVxuICAgIGNvbnN0IHNlcnZlckFwcEFzc2V0ID0gbmV3IHMzYXNzZXRzLkFzc2V0KHRoaXMsICdTZXJ2ZXJBcHBBc3NldCcsIHtcbiAgICAgIHBhdGg6IHBhdGguam9pbihfX2Rpcm5hbWUsICcuLi9hc3NldHMvc2VydmVyLnB5JyksXG4gICAgfSk7XG4gICAgc2VydmVyQXBwQXNzZXQuZ3JhbnRSZWFkKGVjMlJvbGUpO1xuXG4gICAgY29uc3QgdXNlckRhdGEgPSBlYzIuVXNlckRhdGEuZm9yTGludXgoKTtcbiAgICB1c2VyRGF0YS5hZGRDb21tYW5kcyhcbiAgICAgICdjb21tYW5kIC12IHB5dGhvbjMgPi9kZXYvbnVsbCAyPiYxICYmIGNvbW1hbmQgLXYgYXdzID4vZGV2L251bGwgMj4mMSB8fCBkbmYgaW5zdGFsbCAteSBweXRob24zIGF3c2NsaScsXG4gICAgICAnbWtkaXIgLXAgL29wdC9jbG91ZHNlYy1hcHAvdXBsb2FkcyAvb3B0L2Nsb3Vkc2VjLWFwcC9kb2NzJyxcbiAgICAgICdjZCAvb3B0L2Nsb3Vkc2VjLWFwcCcsXG4gICAgICAnZm9yIGkgaW4gezEuLjIwfTsgZG8nLFxuICAgICAgYCAgYXdzIHMzIGNwIHMzOi8vJHtzZXJ2ZXJBcHBBc3NldC5zM0J1Y2tldE5hbWV9LyR7c2VydmVyQXBwQXNzZXQuczNPYmplY3RLZXl9IC9vcHQvY2xvdWRzZWMtYXBwL3NlcnZlci5weSAtLXJlZ2lvbiAke3RoaXMucmVnaW9ufSAmJiBicmVha2AsXG4gICAgICAnICBlY2hvIFwiRXNwZXJhbmRvIGNyZWRlbmNpYWxlcyBTMyBlIGludGVudGFuZG8gZGUgbnVldm8gKCRpLzIwKS4uLlwiJyxcbiAgICAgICcgIHNsZWVwIDMnLFxuICAgICAgJ2RvbmUnLFxuICAgICAgYGF3cyBzMyBjcCBzMzovLyR7cGhvdG9HYWxsZXJ5QnVja2V0LmJ1Y2tldE5hbWV9L2RvY3MvIC9vcHQvY2xvdWRzZWMtYXBwL2RvY3MvIC0tcmVjdXJzaXZlIC0tcmVnaW9uICR7dGhpcy5yZWdpb259IHx8IHRydWVgLFxuICAgICAgJ2NobW9kIDc1NSAvb3B0L2Nsb3Vkc2VjLWFwcC9zZXJ2ZXIucHknLFxuICAgICAgJ2NhdCA8PCBFT0ZfU0VSVklDRSA+IC9ldGMvc3lzdGVtZC9zeXN0ZW0vY2xvdWRzZWMtYXBwLnNlcnZpY2UnLFxuICAgICAgJ1tVbml0XScsXG4gICAgICAnRGVzY3JpcHRpb249Q2xvdWQgU2VjdXJpdHkgUGhvdG8gV2FsbCBMaXZlIERlbW8nLFxuICAgICAgJ0FmdGVyPW5ldHdvcmsudGFyZ2V0JyxcbiAgICAgICcnLFxuICAgICAgJ1tTZXJ2aWNlXScsXG4gICAgICAnVHlwZT1zaW1wbGUnLFxuICAgICAgJ1VzZXI9cm9vdCcsXG4gICAgICAnV29ya2luZ0RpcmVjdG9yeT0vb3B0L2Nsb3Vkc2VjLWFwcCcsXG4gICAgICBgRW52aXJvbm1lbnQ9XCJCVUNLRVRfTkFNRT0ke3Bob3RvR2FsbGVyeUJ1Y2tldC5idWNrZXROYW1lfVwiYCxcbiAgICAgIGBFbnZpcm9ubWVudD1cIkNPTU1VTklUWV9OQU1FPSR7bGFiTmFtZX1cImAsXG4gICAgICBgRW52aXJvbm1lbnQ9XCJFVkVOVF9OQU1FPURldGVjY2nDs24geSBNaXRpZ2FjacOzbiBkZSA0IFB1bnRvcyBDaWVnb3NcImAsXG4gICAgICBgRW52aXJvbm1lbnQ9XCJSRVBPX1VSTD1odHRwczovL2dpdGh1Yi5jb20vU2llZ2ZyaWVkLUZTL2F3cy1jbG91ZC1zZWN1cml0eS1sYWJcImAsXG4gICAgICBgRW52aXJvbm1lbnQ9XCJET0NTX1VSTD1odHRwczovL2RvY3MuYXdzLmFtYXpvbi5jb20vc2VjdXJpdHkvXCJgLFxuICAgICAgYEVudmlyb25tZW50PVwiREVNT19ET0NfTkFNRT1hd3NfY2xvdWRfc2VjdXJpdHlfcmVmZXJlbmNlX2d1aWRlLnBkZlwiYCxcbiAgICAgIGBFbnZpcm9ubWVudD1cIkFXU19SRUdJT049JHt0aGlzLnJlZ2lvbn1cImAsXG4gICAgICAnRXhlY1N0YXJ0PS91c3IvYmluL3B5dGhvbjMgL29wdC9jbG91ZHNlYy1hcHAvc2VydmVyLnB5JyxcbiAgICAgICdSZXN0YXJ0PWFsd2F5cycsXG4gICAgICAnUmVzdGFydFNlYz0zJyxcbiAgICAgICcnLFxuICAgICAgJ1tJbnN0YWxsXScsXG4gICAgICAnV2FudGVkQnk9bXVsdGktdXNlci50YXJnZXQnLFxuICAgICAgJ0VPRl9TRVJWSUNFJyxcbiAgICAgICdzeXN0ZW1jdGwgZGFlbW9uLXJlbG9hZCcsXG4gICAgICAnc3lzdGVtY3RsIGVuYWJsZSBjbG91ZHNlYy1hcHAnLFxuICAgICAgJ3N5c3RlbWN0bCBzdGFydCBjbG91ZHNlYy1hcHAnXG4gICAgKTtcblxuICAgIGNvbnN0IGluc3RhbmNlID0gbmV3IGVjMi5JbnN0YW5jZSh0aGlzLCAnU2VjdXJpdHlEZW1vSW5zdGFuY2UnLCB7XG4gICAgICB2cGMsXG4gICAgICBpbnN0YW5jZVR5cGU6IGVjMi5JbnN0YW5jZVR5cGUub2YoZWMyLkluc3RhbmNlQ2xhc3MuVDIsIGVjMi5JbnN0YW5jZVNpemUuTUlDUk8pLFxuICAgICAgbWFjaGluZUltYWdlOiBlYzIuTWFjaGluZUltYWdlLmxhdGVzdEFtYXpvbkxpbnV4MjAyMygpLFxuICAgICAgcm9sZTogZWMyUm9sZSxcbiAgICAgIHNlY3VyaXR5R3JvdXA6IHdlYlNnLFxuICAgICAgdnBjU3VibmV0czogeyBzdWJuZXRUeXBlOiBlYzIuU3VibmV0VHlwZS5QVUJMSUMgfSxcbiAgICAgIHVzZXJEYXRhLFxuICAgIH0pO1xuXG4gICAgbmV3IGNkay5DZm5PdXRwdXQodGhpcywgJ0VjMlB1YmxpY0lwJywge1xuICAgICAgdmFsdWU6IGluc3RhbmNlLmluc3RhbmNlUHVibGljSXAsXG4gICAgICBkZXNjcmlwdGlvbjogJ0RpcmVjY2lvbiBJUCBwdWJsaWNhIGRlIGxhIGluc3RhbmNpYSBFQzInLFxuICAgIH0pO1xuXG4gICAgbmV3IGNkay5DZm5PdXRwdXQodGhpcywgJ1dlYkRlbW9VcmwnLCB7XG4gICAgICB2YWx1ZTogYGh0dHA6Ly8ke2luc3RhbmNlLmluc3RhbmNlUHVibGljSXB9YCxcbiAgICAgIGRlc2NyaXB0aW9uOiAnVVJMIHB1YmxpY2EgcGFyYSBhYnJpciBlbiBuYXZlZ2Fkb3IgeSBzaW5jcm9uaXphciBjb24gZWwgUVInLFxuICAgIH0pO1xuXG4gICAgbmV3IGNkay5DZm5PdXRwdXQodGhpcywgJ1Bob3RvR2FsbGVyeUJ1Y2tldE5hbWUnLCB7XG4gICAgICB2YWx1ZTogcGhvdG9HYWxsZXJ5QnVja2V0LmJ1Y2tldE5hbWUsXG4gICAgICBkZXNjcmlwdGlvbjogJ05vbWJyZSBkZWwgYnVja2V0IEFtYXpvbiBTMyBwYXJhIGVsIG11cmFsIGRlIGZvdG9zJyxcbiAgICB9KTtcbiAgfVxufVxuIl19