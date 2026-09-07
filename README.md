# AWS Cloud Security Lab

Laboratorio práctico desarrollado con **AWS CDK (TypeScript)** y Python para experimentar con conceptos fundamentales de seguridad en Amazon Web Services: control de acceso con IAM, reglas de Security Groups, URLs prefirmadas en Amazon S3 y auditoría de eventos en AWS CloudTrail.

Diseñado para talleres educativos, estudiantes y comunidades técnicas que buscan comprender cómo funcionan las políticas de seguridad en la práctica.

---

## Requisitos Previos

- AWS CLI instalado y configurado (`aws configure`).
- Node.js (v18+) y npm.
- Python 3.9+.
- AWS CDK v2 (`npm install -g aws-cdk`).

---

## Inicio Rápido

1. Clonar el repositorio e ingresar a la carpeta:
   ```bash
   git clone https://github.com/Siegfried-FS/aws-cloud-security-lab.git
   cd aws-cloud-security-lab
   ```

2. Instalar dependencias del proyecto CDK:
   ```bash
   cd cdk && npm install && cd ..
   ```

3. Iniciar el asistente en terminal:
   ```bash
   ./cloudsec
   ```
   *(O directamente con Python: `python3 scripts/cloudsec_wizard.py`)*

---

## Acciones del Laboratorio

El script `./cloudsec` detecta las credenciales configuradas en tu entorno y permite ejecutar las siguientes pruebas:

- **Despliegue de infraestructura:** Crea una VPC básica, una instancia EC2 con un servidor web de prueba, un bucket S3 privado y roles de IAM correspondientes.
- **Reglas de red (Security Groups):** Habilita o restringe el tráfico en el puerto 80 para observar el comportamiento de filtrado en capa 4.
- **Principio de menor privilegio (IAM):** Modifica los permisos de la instancia para observar respuestas `403 Access Denied` al intentar escribir en S3 sin autorización.
- **Descargas seguras (AWS STS):** Genera URLs prefirmadas temporales para acceder a objetos manteniendo el bucket privado.
- **Auditoría (AWS CloudTrail):** Consulta las llamadas a la API registradas durante las pruebas.
- **Limpieza de recursos:** Destruye los recursos creados con CDK para evitar costos posteriores.

---

## Estructura del Repositorio

```text
aws-cloud-security-lab/
├── cloudsec                    # Script de inicio para el asistente CLI
├── cdk/                        # Código de infraestructura (AWS CDK TypeScript)
│   ├── bin/app.ts              # Punto de entrada de la aplicación CDK
│   ├── lib/cloud-security-stack.ts # Definición de recursos (VPC, EC2, S3, IAM)
│   └── assets/server.py        # Servidor web en Python para las pruebas
│
└── scripts/                    # Scripts de soporte
    ├── cloudsec_wizard.py      # Menú de opciones en consola
    ├── deploy.sh               # Despliegue directo
    ├── destroy.sh              # Destrucción directa
    └── ver_auditoria_cloudtrail.sh # Consulta de eventos en CloudTrail
```

---

## Limpieza Manual

Para destruir la infraestructura sin usar el menú interactivo:

```bash
./scripts/destroy.sh
```

---

## Licencia

Código publicado bajo licencia MIT. Puede utilizarse y adaptarse libremente con fines educativos y comunitarios.
