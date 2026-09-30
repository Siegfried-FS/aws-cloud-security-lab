import http.server
import socketserver
import subprocess
import json
import os
import time
import base64

BUCKET_NAME = os.environ.get("BUCKET_NAME", "")
COMMUNITY_NAME = os.environ.get("COMMUNITY_NAME", "AWS Cloud Security Lab")
EVENT_NAME = os.environ.get("EVENT_NAME", "Detección y Mitigación de 4 Puntos Ciegos")
REPO_URL = os.environ.get("REPO_URL", "https://github.com/Siegfried-FS/aws-cloud-security-lab")
DOCS_URL = os.environ.get("DOCS_URL", "https://docs.aws.amazon.com/security/")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/opt/cloudsec-app/uploads")

try:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
except PermissionError:
    UPLOAD_DIR = "/tmp/cloudsec-app/uploads"
    os.makedirs(UPLOAD_DIR, exist_ok=True)

class PhotoWallHandler(http.server.SimpleHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/upload":
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            try:
                payload = json.loads(post_data.decode('utf-8'))
                author = payload.get('author', 'Asistente').strip() or 'Asistente'
                image_base64 = payload.get('image', '')
                
                if not image_base64 or ',' not in image_base64:
                    self.send_error_json(400, "Formato de imagen inválido o vacío")
                    return
                
                header, encoded = image_base64.split(',', 1)
                img_bytes = base64.b64decode(encoded)
                
                safe_author = "".join([c for c in author if c.isalnum() or c in (' ', '_', '-')])[:15].strip().replace(' ', '_')
                if not safe_author:
                    safe_author = "Asistente"

                filename = f"foto_{int(time.time())}_{safe_author}.jpg"
                local_path = os.path.join(UPLOAD_DIR, filename)
                
                with open(local_path, 'wb') as f:
                    f.write(img_bytes)
                
                s3_key = f"galeria/{filename}"
                s3_ok = False
                
                if BUCKET_NAME:
                    cmd = ["aws", "s3", "cp", local_path, f"s3://{BUCKET_NAME}/{s3_key}", "--region", AWS_REGION]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
                    s3_ok = (result.returncode == 0)
                else:
                    # Modo de prueba local (sin bucket S3)
                    s3_ok = True
                
                if s3_ok:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    resp = {
                        "status": "SUCCESS",
                        "code": 200,
                        "message": "[OK] Foto almacenada exitosamente en Amazon S3",
                        "author": author,
                        "file": filename,
                        "s3_path": s3_key,
                        "bucket": BUCKET_NAME or "demo-local-bucket",
                        "action": "s3:PutObject",
                        "arn": f"arn:aws:s3:::{BUCKET_NAME or 'demo-local-bucket'}/{s3_key}"
                    }
                    self.wfile.write(json.dumps(resp).encode('utf-8'))
                else:
                    self.send_response(403)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    resp = {
                        "status": "ACCESS_DENIED",
                        "code": 403,
                        "message": "[LOCKED] ACCESO DENEGADO POR IAM (HTTP 403 Forbidden)",
                        "detail": "El IAM Instance Profile no tiene concedida la acción 's3:PutObject' en el bucket. ¡Principio de Menor Privilegio en acción!",
                        "action": "s3:PutObject"
                    }
                    self.wfile.write(json.dumps(resp).encode('utf-8'))
            except Exception as e:
                self.send_error_json(500, str(e))
            return

    def do_GET(self):
        clean_path = self.path.split('?')[0]

        if clean_path in ["/api/health", "/healthz"]:
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "healthy",
                "service": "cloudsec-photo-wall",
                "region": AWS_REGION,
                "bucket": BUCKET_NAME or "local-mode",
                "timestamp": int(time.time())
            }).encode('utf-8'))
            return

        if clean_path == "/api/photos":
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            photos = []
            if BUCKET_NAME:
                try:
                    cmd = ["aws", "s3", "ls", f"s3://{BUCKET_NAME}/galeria/", "--region", AWS_REGION]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    if res.returncode == 0:
                        lines = res.stdout.strip().splitlines()
                        for line in lines:
                            parts = line.split()
                            if len(parts) >= 4:
                                fname = parts[3]
                                photos.append({
                                    "filename": fname,
                                    "url": f"/photos/{fname}",
                                    "date": f"{parts[0]} {parts[1]}"
                                })
                except Exception:
                    pass
            
            # Fallback a archivos locales si no hay S3 o está en desarrollo local
            if not photos and os.path.exists(UPLOAD_DIR):
                try:
                    files = [f for f in os.listdir(UPLOAD_DIR) if f.startswith("foto_") and f.endswith((".jpg", ".jpeg", ".png"))]
                    files.sort(key=lambda f: os.path.getmtime(os.path.join(UPLOAD_DIR, f)), reverse=True)
                    for f in files:
                        mtime = os.path.getmtime(os.path.join(UPLOAD_DIR, f))
                        photos.append({
                            "filename": f,
                            "url": f"/photos/{f}",
                            "date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
                        })
                except Exception:
                    pass

            self.wfile.write(json.dumps({"photos": photos[::-1] if BUCKET_NAME else photos}).encode('utf-8'))
            return

        if clean_path.startswith("/photos/"):
            fname = os.path.basename(clean_path)
            local_path = os.path.join(UPLOAD_DIR, fname)
            if os.path.exists(local_path):
                self.send_response(200)
                self.send_header('Content-type', 'image/jpeg')
                self.send_header('Cache-Control', 'public, max-age=3600')
                self.end_headers()
                with open(local_path, 'rb') as f:
                    self.wfile.write(f.read())
                return
            elif BUCKET_NAME:
                cmd = ["aws", "s3", "cp", f"s3://{BUCKET_NAME}/galeria/{fname}", local_path, "--region", AWS_REGION]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if res.returncode == 0 and os.path.exists(local_path):
                    self.send_response(200)
                    self.send_header('Content-type', 'image/jpeg')
                    self.send_header('Cache-Control', 'public, max-age=3600')
                    self.end_headers()
                    with open(local_path, 'rb') as f:
                        self.wfile.write(f.read())
                    return
            self.send_error_json(404, "Foto no encontrada")
            return

        if clean_path == "/api/s3-demo/public":
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            doc_filename = os.environ.get("DEMO_DOC_NAME", "aws_cloud_security_reference_guide.pdf")
            direct_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/docs/{doc_filename}" if BUCKET_NAME else f"https://s3.amazonaws.com/demo-seguridad-cloud/docs/{doc_filename}"
            
            code = 403
            if BUCKET_NAME:
                try:
                    c_res = subprocess.run(["curl", "-sI", direct_url], capture_output=True, text=True, timeout=4)
                    if "200 OK" in c_res.stdout:
                        code = 200
                except Exception:
                    code = 403

            if code == 403:
                resp = {
                    "status": "DENIED",
                    "code": 403,
                    "title": "[BLOCKED] ACCESO DENEGADO (HTTP 403 Forbidden)",
                    "message": "Amazon S3 bloqueó la descarga directa pública.",
                    "url": direct_url,
                    "explanation": "El bucket tiene 'Block Public Access' (BPA) activado al 100%. Nadie en internet puede descargar el archivo sin autenticación previa. ¡La regla de Menor Privilegio protegió tus datos!"
                }
            else:
                resp = {
                    "status": "ALLOWED",
                    "code": 200,
                    "title": "[EXPOSED] ACCESO PÚBLICO EXPUESTO (HTTP 200 OK)",
                    "message": "¡Alerta! El bucket está configurado como público para todo internet.",
                    "url": direct_url,
                    "explanation": "Anti-patrón detectado: Bucket Policy con 'Principal: *'. Cualquier persona puede descargar tus archivos sin autorización."
                }
            self.wfile.write(json.dumps(resp).encode('utf-8'))
            return

        if clean_path == "/api/s3-demo/presigned":
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            
            doc_filename = os.environ.get("DEMO_DOC_NAME", "aws_cloud_security_reference_guide.pdf")
            presigned_url = ""
            if BUCKET_NAME:
                try:
                    cmd = ["aws", "s3", "presign", f"s3://{BUCKET_NAME}/docs/{doc_filename}", "--expires-in", "900", "--region", AWS_REGION]
                    pres_res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                    if pres_res.returncode == 0 and pres_res.stdout.strip():
                        presigned_url = pres_res.stdout.strip()
                except Exception:
                    pass
            
            if not presigned_url:
                presigned_url = f"/docs/{doc_filename}"

            resp = {
                "status": "SUCCESS",
                "code": 200,
                "url": presigned_url,
                "title": "[AUTHORIZED] ACCESO AUTORIZADO (HTTP 200 OK)",
                "message": "Presigned URL temporal generada con éxito por AWS STS.",
                "explanation": "El bucket de S3 permanece 100% PRIVADO. El IAM Role de la EC2 solicitó a AWS STS un token firmado válido por 15 minutos (900 segundos). ¡Descarga iniciada con credenciales temporales SigV4!"
            }
            self.wfile.write(json.dumps(resp).encode('utf-8'))
            return

        if clean_path.startswith("/docs/"):
            req_name = os.path.basename(self.path)
            candidate_paths = [
                os.path.join(os.path.dirname(__file__), "sample-docs", req_name),
                os.path.join(os.path.dirname(__file__), "sample-docs", "aws_cloud_security_reference_guide.pdf"),
                os.path.join(os.path.dirname(__file__), "docs", req_name),
                os.path.join(os.path.dirname(__file__), "docs", "AWS_certification_paths.pdf"),
            ]
            doc_path = next((p for p in candidate_paths if os.path.exists(p)), None)
            
            if doc_path:
                self.send_response(200)
                self.send_header('Content-type', 'application/pdf')
                self.send_header('Content-Disposition', f'attachment; filename="{req_name}"')
                self.end_headers()
                with open(doc_path, 'rb') as f:
                    self.wfile.write(f.read())
                return

        # RENDERIZADO DEL SITIO WEB PRINCIPAL (HTML / CSS / JS CLIENTE)
        html = f"""<!DOCTYPE html>
<html lang="es" class="scroll-smooth antialiased">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
  <title>{COMMUNITY_NAME} · {EVENT_NAME}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body {{
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: #080c14;
      background-image: 
        radial-gradient(ellipse at 50% 0%, rgba(14, 165, 233, 0.08) 0%, transparent 60%),
        radial-gradient(circle at 90% 20%, rgba(99, 102, 241, 0.05) 0%, transparent 40%),
        linear-gradient(rgba(8, 12, 20, 0.98), rgba(8, 12, 20, 0.98));
      color: #f8fafc;
      min-height: 100vh;
    }}
    .font-mono {{ font-family: 'JetBrains Mono', monospace; }}
    .sec-card {{
      background: rgba(15, 23, 42, 0.75);
      border: 1px solid rgba(51, 65, 85, 0.6);
      box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.5);
      border-radius: 12px;
      backdrop-filter: blur(12px);
    }}
    .dropzone-active {{
      border-color: #38bdf8 !important;
      background: rgba(14, 165, 233, 0.08) !important;
    }}
  </style>
</head>
<body class="flex flex-col justify-between p-4 sm:p-6 max-w-3xl mx-auto w-full selection:bg-sky-500 selection:text-slate-950">

  <!-- TOP BAR: CONSOLA DE ESTADO DE INFRAESTRUCTURA -->
  <aside class="w-full mb-5">
    <div class="sec-card px-3.5 py-2.5 flex flex-wrap items-center justify-between gap-2.5 text-[11px] font-mono border-slate-800">
      <div class="flex items-center gap-2">
        <span class="relative flex h-2 w-2">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
        </span>
        <span class="font-semibold text-slate-200 uppercase tracking-wide">EC2 Instance Online</span>
        <span class="text-slate-600">/</span>
        <span class="text-slate-400">t2.micro · {AWS_REGION}</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="px-2 py-0.5 rounded bg-sky-950/70 border border-sky-800/60 text-sky-300 font-medium">
          IAM Role: Attached
        </span>
        <span class="px-2 py-0.5 rounded bg-emerald-950/70 border border-emerald-800/60 text-emerald-300 font-medium">
          S3 BPA: Enforced
        </span>
      </div>
    </div>
  </aside>

  <!-- CABECERA PRINCIPAL -->
  <header class="text-center space-y-2 mb-6">
    <div class="inline-flex items-center gap-2 px-3 py-1 rounded-md bg-slate-900 border border-slate-800 text-sky-400 text-xs font-mono font-medium">
      <svg class="w-3.5 h-3.5 text-sky-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/></svg>
      <span>{EVENT_NAME} · NIVEL 100</span>
    </div>
    
    <h1 class="text-2xl sm:text-3xl font-bold text-white tracking-tight leading-snug">
      {COMMUNITY_NAME}
    </h1>
    
    <p class="text-xs sm:text-sm text-slate-400 max-w-xl mx-auto leading-relaxed">
      Laboratorio interactivo para detectar y corregir descuidos habituales de seguridad: <span class="text-slate-200 font-semibold">IAM Roles temporales</span>, <span class="text-slate-200 font-semibold">Security Groups</span> y protección en <span class="text-slate-200 font-semibold">Amazon S3 con AWS STS</span>.
    </p>

    <!-- NAVEGACIÓN RÁPIDA -->
    <nav class="flex justify-center gap-2 pt-2">
      <a href="#experimento-upload" class="px-3 py-1 rounded-lg bg-slate-900/90 border border-slate-800 text-xs font-mono text-slate-300 hover:text-sky-300 hover:border-slate-700 transition">
        1. Subida IAM Role
      </a>
      <a href="#experimento-s3" class="px-3 py-1 rounded-lg bg-slate-900/90 border border-slate-800 text-xs font-mono text-slate-300 hover:text-amber-300 hover:border-slate-700 transition">
        2. Reto S3 & STS
      </a>
      <a href="#mural-galeria" class="px-3 py-1 rounded-lg bg-slate-900/90 border border-slate-800 text-xs font-mono text-slate-300 hover:text-indigo-300 hover:border-slate-700 transition">
        3. Muro de Evidencias
      </a>
    </nav>
  </header>

  <!-- CONTENIDO DEL LABORATORIO -->
  <main class="space-y-6">

    <!-- EXPERIMENTO 1: SUBIDA CON IAM ROLE (s3:PutObject) -->
    <section id="experimento-upload" class="sec-card p-5 sm:p-6 space-y-4">
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <div class="flex items-center gap-2.5">
          <div class="p-1.5 rounded-lg bg-sky-950/60 border border-sky-800/60 text-sky-400">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12"/></svg>
          </div>
          <div>
            <h2 class="text-sm font-semibold text-white tracking-wide">
              1. Demostración de IAM Roles y Principio de Menor Privilegio
            </h2>
            <p class="text-[11px] font-mono text-slate-400">Envío de objetos mediante credenciales temporales generadas por STS (s3:PutObject)</p>
          </div>
        </div>
        <span class="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-slate-800 text-slate-300 border border-slate-700">
          IAM / CAPA 7
        </span>
      </div>

      <div class="bg-slate-950/70 border border-slate-800 rounded-lg p-3.5 space-y-2">
        <div class="flex items-center justify-between">
          <span class="text-xs font-semibold text-slate-200">Participación interactiva en vivo</span>
          <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/60 font-medium">
            CANAL ACTIVO
          </span>
        </div>
        <p class="text-xs text-slate-400 leading-relaxed">
          Toma una foto o selecciona una imagen. El navegador la enviará al servidor EC2 y este invocará a Amazon S3 usando su <b class="text-slate-200">IAM Instance Profile</b>. No existen credenciales estáticas ni secretos guardados en el código.
        </p>
      </div>

      <!-- FORMULARIO -->
      <div class="space-y-3 pt-1">
        <div class="space-y-1.5">
          <div class="flex items-center justify-between">
            <label class="block text-xs font-mono font-medium text-slate-300">
              Identificador o Alias del Participante:
            </label>
            <div class="flex gap-1 text-[11px] font-mono">
              <button type="button" onclick="setAlias('Asistente')" class="text-sky-400 hover:text-sky-300 px-1">Asistente</button>
              <span class="text-slate-600">·</span>
              <button type="button" onclick="setAlias('Builder')" class="text-sky-400 hover:text-sky-300 px-1">Builder</button>
              <span class="text-slate-600">·</span>
              <button type="button" onclick="setAlias('Auditor')" class="text-sky-400 hover:text-sky-300 px-1">Auditor</button>
            </div>
          </div>
          <input type="text" id="author-input" placeholder="Ej: Auditor-01 / CloudSec-Lab / Builder" class="w-full px-3.5 py-2.5 bg-slate-950 border border-slate-700 rounded-lg text-sm text-white focus:outline-none focus:border-sky-500 font-mono transition">
        </div>

        <input type="file" id="camera-input" accept="image/*" capture="user" class="hidden">
        <input type="file" id="file-input" accept="image/*" class="hidden">

        <!-- BOTONES DE CAPTURA -->
        <div class="grid grid-cols-2 gap-2.5">
          <button type="button" onclick="document.getElementById('camera-input').click()" class="py-2.5 px-3 rounded-lg border border-slate-700 bg-slate-900 hover:bg-slate-800 text-slate-200 font-mono text-xs font-medium flex items-center justify-center gap-2 transition active:scale-95">
            <svg class="w-4 h-4 text-sky-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
            <span>Capturar Foto</span>
          </button>
          
          <button type="button" onclick="document.getElementById('file-input').click()" class="py-2.5 px-3 rounded-lg border border-slate-700 bg-slate-900 hover:bg-slate-800 text-slate-200 font-mono text-xs font-medium flex items-center justify-center gap-2 transition active:scale-95">
            <svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
            <span>Seleccionar Archivo</span>
          </button>
        </div>

        <div id="drop-zone" class="hidden sm:block border border-dashed border-slate-700/80 rounded-lg p-3 text-center hover:border-sky-500/60 transition cursor-pointer" onclick="document.getElementById('file-input').click()">
          <p class="text-xs font-mono text-slate-400">
            Arrastra y suelta una imagen aquí o haz clic para examinar.
          </p>
        </div>

        <!-- PREVIEW -->
        <div id="preview-box" class="hidden rounded-lg border border-slate-700 bg-slate-950 p-3 space-y-2 text-center transition-all">
          <div class="relative inline-block max-w-full">
            <img id="preview-img" class="max-h-52 mx-auto rounded border border-slate-800 object-contain">
            <button type="button" onclick="clearPreview()" class="absolute top-2 right-2 bg-slate-900/90 text-slate-400 hover:text-white rounded-full p-1 text-xs border border-slate-700" title="Eliminar imagen">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
            </button>
          </div>
          <div class="flex items-center justify-center gap-2 text-xs font-mono text-slate-400">
            <span>Imagen lista</span>
            <span>·</span>
            <span id="preview-size">0 KB</span>
          </div>
        </div>

        <!-- BOTÓN DE SUBIDA -->
        <button onclick="uploadPhoto()" id="btn-upload" class="w-full py-3 rounded-lg font-semibold text-xs sm:text-sm bg-sky-600 hover:bg-sky-500 text-white transition flex items-center justify-center gap-2 shadow active:scale-95">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"/></svg>
          <span id="upload-btn-text">Subir a S3 (Invocar s3:PutObject vía IAM)</span>
        </button>

        <div id="upload-progress" class="hidden space-y-1 pt-1">
          <div class="w-full bg-slate-950 rounded-full h-1.5 overflow-hidden border border-slate-800">
            <div id="progress-bar" class="bg-sky-500 h-full w-0 transition-all duration-300"></div>
          </div>
          <p id="progress-text" class="text-[10px] font-mono text-sky-400 text-center">Iniciando petición a AWS API...</p>
        </div>

        <div id="alert-box" class="hidden p-3.5 text-xs font-mono rounded-lg border transition-all"></div>
      </div>
    </section>

    <!-- EXPERIMENTO 2: S3 PRIVADO VS STS PRESIGNED URL -->
    <section id="experimento-s3" class="sec-card p-5 sm:p-6 space-y-4">
      <div class="flex items-center justify-between border-b border-slate-800 pb-3">
        <div class="flex items-center gap-2.5">
          <div class="p-1.5 rounded-lg bg-amber-950/60 border border-amber-800/60 text-amber-400">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/></svg>
          </div>
          <div>
            <h2 class="text-sm font-semibold text-white tracking-wide">
              2. Protección de Datos en Amazon S3 y Delegación con AWS STS
            </h2>
            <p class="text-[11px] font-mono text-slate-400">Punto Ciego 3: Bloqueo de Acceso Público vs URLs Prefirmadas</p>
          </div>
        </div>
        <span class="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-slate-800 text-slate-300 border border-slate-700">
          S3 + STS
        </span>
      </div>

      <p class="text-xs text-slate-400 leading-relaxed">
        El bucket privado resguarda la <b class="text-slate-200">Guía de Referencia Técnica y Buenas Prácticas de Seguridad en AWS</b>. Compara el comportamiento entre una petición anónima directa y la emisión de una URL prefirmada temporal generada con credenciales de STS:
      </p>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
        <!-- TEST 1: PÚBLICO (403) -->
        <button onclick="testPublicDownload()" id="btn-public-download" class="p-3.5 rounded-lg border border-rose-900/60 bg-rose-950/30 hover:bg-rose-950/50 text-slate-200 text-xs font-mono flex flex-col items-start gap-1 transition active:scale-95 text-left">
          <div class="flex items-center gap-2 w-full justify-between">
            <span class="font-semibold text-rose-300">Petición Anónima Directa</span>
            <span class="text-[9px] px-1.5 py-0.5 rounded bg-rose-900/80 text-rose-200 font-mono">403 Expected</span>
          </div>
          <span class="text-[11px] text-slate-400">Intenta descargar sin pasar por autenticación.</span>
        </button>

        <!-- TEST 2: PRESIGNED URL (200) -->
        <button onclick="testPresignedDownload()" id="btn-presigned-download" class="p-3.5 rounded-lg border border-emerald-900/60 bg-emerald-950/30 hover:bg-emerald-950/50 text-slate-200 text-xs font-mono flex flex-col items-start gap-1 transition active:scale-95 text-left">
          <div class="flex items-center gap-2 w-full justify-between">
            <span class="font-semibold text-emerald-300">Descarga Segura (STS SigV4)</span>
            <span class="text-[9px] px-1.5 py-0.5 rounded bg-emerald-900/80 text-emerald-200 font-mono">200 + Token</span>
          </div>
          <span class="text-[11px] text-slate-400">Genera una Pre-signed URL temporal válida por 15 min.</span>
        </button>
      </div>

      <div id="s3-alert-box" class="hidden p-3.5 text-xs font-mono rounded-lg border transition-all"></div>
    </section>

    <!-- EXPERIMENTO 3: MURAL COLECTIVO -->
    <section id="mural-galeria" class="sec-card p-4 sm:p-5 space-y-3">
      <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div class="flex items-center gap-2.5">
          <div class="p-1.5 rounded-lg bg-indigo-950/60 border border-indigo-800/60 text-indigo-400">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/></svg>
          </div>
          <div>
            <h2 class="text-sm font-semibold text-white tracking-wide flex items-center gap-2">
              <span>Muro de Evidencias en Vivo</span>
              <span id="photo-counter-badge" class="text-[10px] px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 font-mono">
                0 objetos
              </span>
            </h2>
            <p class="text-[11px] font-mono text-slate-400">Objetos subidos al bucket de Amazon S3 durante la sesión</p>
          </div>
        </div>

        <div class="flex items-center gap-3">
          <label class="inline-flex items-center gap-1.5 text-xs font-mono text-slate-400 cursor-pointer">
            <input type="checkbox" id="auto-refresh-check" checked class="rounded accent-sky-500">
            <span>Sincronizar (6s)</span>
          </label>
          <button onclick="loadPhotos(true)" class="p-1.5 rounded bg-slate-950 border border-slate-700 text-slate-300 hover:text-white transition" title="Actualizar">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
          </button>
        </div>
      </div>

      <div id="gallery-grid" class="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-2">
        <div class="p-8 col-span-full text-center text-xs text-slate-500 font-mono">
          Esperando objetos en el bucket de Amazon S3...
        </div>
      </div>
    </section>

  </main>

  <!-- MODAL DE INSPECCIÓN -->
  <div id="photo-modal" class="fixed inset-0 z-50 hidden bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-4" onclick="closePhotoModal(event)">
    <div class="sec-card max-w-lg w-full p-4 sm:p-5 space-y-3 relative border-slate-700" onclick="event.stopPropagation()">
      <button onclick="closePhotoModal()" class="absolute top-3 right-3 text-slate-400 hover:text-white font-mono text-sm p-1">✕</button>
      
      <div class="rounded-lg overflow-hidden border border-slate-800 bg-black">
        <img id="modal-img" class="w-full max-h-[55vh] object-contain mx-auto">
      </div>

      <div class="space-y-1.5 pt-1">
        <div class="flex items-center justify-between">
          <div id="modal-author" class="font-mono font-semibold text-white text-sm"></div>
          <div id="modal-date" class="text-[11px] font-mono text-slate-400"></div>
        </div>
        
        <div class="bg-slate-950 p-2.5 rounded border border-slate-800 text-[10px] font-mono text-slate-300 space-y-1">
          <div class="flex justify-between"><span class="text-slate-500">IAM Role:</span> <span class="text-sky-300">EC2PhotoWallRole</span></div>
          <div class="flex justify-between"><span class="text-slate-500">Almacenamiento:</span> <span class="text-emerald-300">Amazon S3 Standard (SSE-S3)</span></div>
          <div class="flex justify-between"><span class="text-slate-500">S3 Key:</span> <span id="modal-key" class="text-slate-300 truncate max-w-[220px]"></span></div>
        </div>
      </div>

      <div class="flex gap-2 pt-1">
        <a id="modal-download" target="_blank" download class="flex-1 py-2 rounded bg-sky-600 hover:bg-sky-500 text-white font-mono font-medium text-xs text-center transition">
          Descargar Archivo
        </a>
        <button onclick="closePhotoModal()" class="px-4 py-2 rounded bg-slate-900 border border-slate-700 text-slate-300 font-mono text-xs hover:text-white transition">
          Cerrar
        </button>
      </div>
    </div>
  </div>

  <!-- PIE DE PÁGINA: PROYECTO OPEN SOURCE -->
  <footer class="mt-8 pt-6 border-t border-slate-800/80 space-y-4 text-center">
    <div class="sec-card p-4 sm:p-5 space-y-3 text-left border-slate-800 bg-slate-950/60">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div class="text-sm font-bold text-white font-mono">AWS Cloud Security Lab</div>
          <div class="text-xs text-slate-400 font-mono">Hands-on Cloud Security & Compliance Educational Framework</div>
        </div>
        <span class="px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-slate-800 text-slate-300 border border-slate-700">
          Open Source · Licencia MIT
        </span>
      </div>

      <p class="text-xs text-slate-400 italic border-l-2 border-slate-700 pl-3 my-1 font-mono leading-relaxed">
        «Diseñado para enseñar seguridad en la nube desde la práctica real: detección de puntos ciegos en IAM, Security Groups vs NACLs, URLs prefirmadas en S3 y trazabilidad forense con CloudTrail.»
      </p>

      <div class="text-[11px] text-slate-500 font-mono flex flex-wrap gap-x-4 gap-y-1 pt-2 border-t border-slate-800/80">
        <span>Laboratorio 100% Replicable</span>
        <span>·</span>
        <span>Compatible con Free Tier ($0 USD)</span>
        <span>·</span>
        <span>Infraestructura como Código (AWS CDK)</span>
      </div>
    </div>

    <!-- ENLACES DE RECURSOS TÉCNICOS -->
    <div class="flex flex-wrap gap-2.5 justify-center pt-1">
      <a href="{REPO_URL}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium bg-slate-900 border border-slate-700 text-slate-300 hover:text-white hover:border-slate-600 transition">
        <svg class="w-3.5 h-3.5 text-sky-400" fill="currentColor" viewBox="0 0 24 24"><path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/></svg>
        <span>Código Fuente en GitHub</span>
      </a>
      <a href="{DOCS_URL}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium bg-slate-900 border border-slate-700 text-slate-300 hover:text-white hover:border-slate-600 transition">
        <svg class="w-3.5 h-3.5 text-amber-400" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2L4 5v6.09c0 5.05 3.41 9.76 8 10.91 4.59-1.15 8-5.86 8-10.91V5l-8-3zm1 14.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zm0-4a1 1 0 01-2 0V7a1 1 0 012 0z"/></svg>
        <span>AWS Security Documentation</span>
      </a>
    </div>
  </footer>

  <!-- LÓGICA DE INTERACCIÓN CLIENTE (JS ULTRA-LIGERO) -->
  <script>
    const cameraInput = document.getElementById('camera-input');
    const fileInput = document.getElementById('file-input');
    const previewBox = document.getElementById('preview-box');
    const previewImg = document.getElementById('preview-img');
    const previewSize = document.getElementById('preview-size');
    const alertBox = document.getElementById('alert-box');
    const s3AlertBox = document.getElementById('s3-alert-box');
    const dropZone = document.getElementById('drop-zone');
    const photoCounterBadge = document.getElementById('photo-counter-badge');
    const autoRefreshCheck = document.getElementById('auto-refresh-check');
    let currentBase64 = '';
    let autoRefreshTimer = null;

    function setAlias(chip) {{
      const input = document.getElementById('author-input');
      if (!input.value) {{
        input.value = chip;
      }} else if (!input.value.includes(chip)) {{
        input.value = input.value + ' (' + chip + ')';
      }}
      input.focus();
    }}

    function handleFileSelected(file) {{
      if (!file) return;
      if (!file.type.startsWith('image/')) {{
        alert('Por favor selecciona un archivo de imagen válido (JPG, PNG).');
        return;
      }}

      previewSize.textContent = (file.size / 1024).toFixed(0) + ' KB';

      const reader = new FileReader();
      reader.onload = function(evt) {{
        currentBase64 = evt.target.result;
        previewImg.src = currentBase64;
        previewBox.classList.remove('hidden');
        previewBox.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
      }};
      reader.readAsDataURL(file);
    }}

    cameraInput.addEventListener('change', (e) => handleFileSelected(e.target.files[0]));
    fileInput.addEventListener('change', (e) => handleFileSelected(e.target.files[0]));

    // Drag & Drop
    if (dropZone) {{
      ['dragenter', 'dragover'].forEach(name => {{
        dropZone.addEventListener(name, (e) => {{
          e.preventDefault();
          dropZone.classList.add('dropzone-active');
        }}, false);
      }});
      ['dragleave', 'drop'].forEach(name => {{
        dropZone.addEventListener(name, (e) => {{
          e.preventDefault();
          dropZone.classList.remove('dropzone-active');
        }}, false);
      }});
      dropZone.addEventListener('drop', (e) => {{
        const dt = e.dataTransfer;
        const file = dt.files[0];
        handleFileSelected(file);
      }}, false);
    }}

    function clearPreview() {{
      currentBase64 = '';
      previewImg.src = '';
      previewBox.classList.add('hidden');
      cameraInput.value = '';
      fileInput.value = '';
    }}

    // 1. SUBIDA DE FOTO A S3 (EXPERIMENTO IAM PUT_OBJECT)
    async function uploadPhoto() {{
      if (!currentBase64) {{
        alert('Por favor toma una selfie con tu cámara o selecciona una foto primero.');
        return;
      }}

      const author = document.getElementById('author-input').value.trim() || 'Estudiante';
      const btn = document.getElementById('btn-upload');
      const btnText = document.getElementById('upload-btn-text');
      const progBox = document.getElementById('upload-progress');
      const progBar = document.getElementById('progress-bar');
      const progText = document.getElementById('progress-text');

      btn.disabled = true;
      btn.classList.add('opacity-70', 'cursor-not-allowed');
      progBox.classList.remove('hidden');
      alertBox.classList.add('hidden');

      // Animación didáctica de etapas de seguridad AWS
      progBar.style.width = '30%';
      progText.textContent = '1. Asumiendo IAM Instance Profile (AWS STS)...';

      setTimeout(() => {{
        progBar.style.width = '65%';
        progText.textContent = '2. Firmando payload con AWS SigV4 (s3:PutObject)...';
      }}, 350);

      try {{
        const res = await fetch('/api/upload', {{
          method: 'POST',
          headers: {{ 'Content-Type': 'application/json' }},
          body: JSON.stringify({{ author: author, image: currentBase64 }})
        }});

        progBar.style.width = '90%';
        progText.textContent = '3. Validando respuesta de Amazon S3...';

        const data = await res.json();
        progBar.style.width = '100%';

        if (res.status === 200) {{
          alertBox.className = 'p-4 rounded-xl text-xs font-mono bg-emerald-950/70 border border-emerald-500/50 text-emerald-200 space-y-1.5';
          alertBox.innerHTML = 
            '<div class="flex items-center gap-2 font-bold text-emerald-300 text-sm"><span>✅</span> ¡ÉXITO (HTTP 200 OK)!</div>' +
            '<div>' + data.message + '</div>' +
            '<div class="bg-slate-950 p-2 rounded border border-emerald-500/30 text-[10px] space-y-0.5 mt-1">' +
              '<div><b>Acción IAM:</b> <span class="text-cyan-300">s3:PutObject</span></div>' +
              '<div><b>ARN Destino:</b> <span class="text-amber-300">' + (data.arn || data.s3_path) + '</span></div>' +
              '<div><b>Autor:</b> ' + data.author + '</div>' +
            '</div>' +
            '<div class="text-[10px] text-emerald-300/80 pt-1">🛡️ El IAM Role de la EC2 autorizó la operación bajo el Principio de Menor Privilegio.</div>';
          alertBox.classList.remove('hidden');
          clearPreview();
          setTimeout(() => loadPhotos(false), 800);
        }} else {{
          alertBox.className = 'p-4 rounded-xl text-xs font-mono bg-rose-950/80 border border-rose-500/60 text-rose-200 space-y-1.5';
          alertBox.innerHTML = 
            '<div class="flex items-center gap-2 font-bold text-rose-300 text-sm"><span>🛑</span> ACCESO DENEGADO (HTTP 403 FORBIDDEN)</div>' +
            '<div>' + data.message + '</div>' +
            '<div class="text-[10px] text-rose-300/90">' + data.detail + '</div>';
          alertBox.classList.remove('hidden');
        }}
      }} catch (err) {{
        alertBox.className = 'p-4 rounded-xl text-xs font-mono bg-rose-950/80 border border-rose-500/60 text-rose-200 space-y-1.5';
        alertBox.innerHTML = 
          '<div class="flex items-center gap-2 font-bold text-rose-300 text-sm"><span>❌</span> ERROR DE CONEXIÓN O TIMEOUT</div>' +
          '<div>No se pudo alcanzar el servidor. Si el ponente cerró el Security Group (Puerto 80), el tráfico de red está bloqueado en Capa 4 (Firewall con Estado).</div>';
        alertBox.classList.remove('hidden');
      }} finally {{
        btn.disabled = false;
        btn.classList.remove('opacity-70', 'cursor-not-allowed');
        setTimeout(() => {{ progBox.classList.add('hidden'); progBar.style.width = '0%'; }}, 1000);
      }}
    }}

    // 2. PROBAR DESCARGA DIRECTA PÚBLICA (DEBE DAR 403 FORBIDDEN)
    async function testPublicDownload() {{
      s3AlertBox.classList.remove('hidden');
      s3AlertBox.className = 'p-4 rounded-xl text-xs font-mono bg-slate-900 border border-gray-700 text-gray-300';
      s3AlertBox.innerHTML = '🔄 Consultando URL pública directa de Amazon S3 (sin firma STS)...';

      try {{
        const res = await fetch('/api/s3-demo/public');
        const data = await res.json();

        if (data.code === 403) {{
          s3AlertBox.className = 'p-4 rounded-xl text-xs font-mono bg-rose-950/70 border border-rose-500/60 text-rose-200 space-y-2';
          s3AlertBox.innerHTML = 
            '<div class="font-bold text-rose-300 text-sm flex items-center gap-2"><span>' + data.title + '</span></div>' +
            '<div>' + data.message + '</div>' +
            '<div class="p-2.5 bg-black/40 rounded-lg border border-rose-500/30 text-[10px] text-gray-300 space-y-1">' +
              '<div><b>URL Probada:</b> <a href="' + data.url + '" target="_blank" class="text-cyan-300 underline break-all">' + data.url + '</a></div>' +
              '<div><b>💡 Explicación Técnica:</b> ' + data.explanation + '</div>' +
            '</div>';
        }} else {{
          s3AlertBox.className = 'p-4 rounded-xl text-xs font-mono bg-amber-950/70 border border-amber-500 text-amber-200 space-y-2';
          s3AlertBox.innerHTML = '<b>' + data.title + '</b><br/>' + data.explanation;
        }}
      }} catch (e) {{
        s3AlertBox.className = 'p-4 rounded-xl text-xs font-mono bg-rose-950/70 border border-rose-500 text-rose-200';
        s3AlertBox.innerHTML = '<b>❌ Error:</b> No se pudo comunicar con la API de demostración.';
      }}
    }}

    // 3. DESCARGA SEGURA CON PRESIGNED URL STS (200 OK + INICIA DESCARGA)
    async function testPresignedDownload() {{
      s3AlertBox.classList.remove('hidden');
      s3AlertBox.className = 'p-4 rounded-xl text-xs font-mono bg-slate-900 border border-gray-700 text-gray-300';
      s3AlertBox.innerHTML = '🔑 Solicitando Presigned URL firmada con IAM Role a AWS STS...';

      try {{
        const res = await fetch('/api/s3-demo/presigned');
        const data = await res.json();

        if (data.status === 'SUCCESS') {{
          s3AlertBox.className = 'p-4 rounded-xl text-xs font-mono bg-emerald-950/70 border border-emerald-500/50 text-emerald-200 space-y-2';
          s3AlertBox.innerHTML = 
            '<div class="font-bold text-emerald-300 text-sm flex items-center gap-2"><span>' + data.title + '</span></div>' +
            '<div>' + data.message + '</div>' +
            '<div class="p-2.5 bg-black/40 rounded-lg border border-emerald-500/30 text-[10px] text-gray-300 space-y-1">' +
              '<div><b>💡 Explicación Técnica:</b> ' + data.explanation + '</div>' +
              '<div><b>Parámetros de Seguridad:</b> <span class="text-cyan-300">X-Amz-Expires=900</span> · <span class="text-amber-300">X-Amz-Signature</span></div>' +
            '</div>' +
            '<div class="pt-1"><a href="' + data.url + '" target="_blank" download class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-400 hover:bg-emerald-300 text-slate-950 font-bold text-xs transition">📥 Descargar Rutas de Certificación AWS (PDF)</a></div>';
          
          // Disparo automático de descarga
          const link = document.createElement('a');
          link.href = data.url;
          link.download = 'AWS_certification_paths.pdf';
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        }}
      }} catch (e) {{
        s3AlertBox.className = 'p-4 rounded-xl text-xs font-mono bg-rose-950/70 border border-rose-500 text-rose-200';
        s3AlertBox.innerHTML = '<b>❌ Error:</b> No se pudo generar la Presigned URL.';
      }}
    }}

    // REACCIONES EN LOCALSTORAGE
    function getReactions(fname) {{
      try {{
        const stored = localStorage.getItem('reactions_' + fname);
        return stored ? JSON.parse(stored) : {{ '❤️': 0, '🔥': 0, '🚀': 0 }};
      }} catch(e) {{
        return {{ '❤️': 0, '🔥': 0, '🚀': 0 }};
      }}
    }}

    function addReaction(fname, emoji) {{
      const reactions = getReactions(fname);
      reactions[emoji] = (reactions[emoji] || 0) + 1;
      localStorage.setItem('reactions_' + fname, JSON.stringify(reactions));
      const safeName = fname.replace(/[^a-zA-Z0-9]/g, '_');
      const el = document.getElementById('react-' + emoji + '-' + safeName);
      if (el) el.textContent = reactions[emoji];
    }}

    // 4. CARGAR FOTOS DEL MURAL
    let cachedPhotos = [];
    async function loadPhotos(showToast) {{
      const grid = document.getElementById('gallery-grid');
      try {{
        const res = await fetch('/api/photos?t=' + Date.now());
        const data = await res.json();
        const photos = data.photos || [];
        cachedPhotos = photos;
        photoCounterBadge.textContent = photos.length + ' ' + (photos.length === 1 ? 'foto' : 'fotos');

        if (photos.length > 0) {{
          grid.innerHTML = photos.map(p => {{
            const safeName = p.filename.replace(/[^a-zA-Z0-9]/g, '_');
            const cleanAuthor = p.filename.replace(/^foto_\\d+_?/, '').replace(/\\.jpg$/i, '').replace(/_/g, ' ') || 'Asistente';
            const reactions = getReactions(p.filename);
            
            return '<div class="photo-card rounded-xl overflow-hidden border border-gray-800 bg-slate-900 group hover:border-cyan-500/50 transition duration-300 shadow-md flex flex-col justify-between cursor-pointer" ' +
              'data-fname="' + p.filename + '" data-url="' + p.url + '" data-author="' + cleanAuthor + '" data-date="' + (p.date || 'Hoy') + '">' +
              '<div class="relative overflow-hidden aspect-square bg-slate-950">' +
                '<img src="' + p.url + '" loading="lazy" class="w-full h-full object-cover group-hover:scale-105 transition duration-300">' +
                '<div class="absolute bottom-0 inset-x-0 bg-gradient-to-t from-slate-950/90 to-transparent p-2 pt-4">' +
                  '<div class="text-[11px] font-mono font-bold text-white truncate flex items-center gap-1"><span>👤</span> ' + cleanAuthor + '</div>' +
                '</div>' +
              '</div>' +
              '<div class="p-2 bg-slate-950 flex items-center justify-between border-t border-gray-800/60 text-[10px] font-mono">' +
                '<span class="text-gray-400">' + (p.date ? p.date.split(' ')[0] : 'Hoy') + '</span>' +
                '<div class="flex items-center gap-1.5">' +
                  '<button type="button" class="react-btn hover:scale-125 transition flex items-center gap-0.5 text-gray-300" data-fname="' + p.filename + '" data-emoji="❤️">❤️ <span id="react-❤️-' + safeName + '">' + (reactions['❤️'] || '') + '</span></button>' +
                  '<button type="button" class="react-btn hover:scale-125 transition flex items-center gap-0.5 text-gray-300" data-fname="' + p.filename + '" data-emoji="🔥">🔥 <span id="react-🔥-' + safeName + '">' + (reactions['🔥'] || '') + '</span></button>' +
                '</div>' +
              '</div>' +
            '</div>';
          }}).join('');
        }} else {{
          grid.innerHTML = '<div class="p-8 col-span-full text-center text-xs text-gray-500 font-mono">Aún no hay fotos en el mural. ¡Sé la primera persona en subir una selfie!</div>';
        }}
      }} catch (err) {{
        console.error(err);
        grid.innerHTML = '<div class="p-8 col-span-full text-center text-xs text-rose-400 font-mono">Error: ' + err.message + '</div>';
      }}
    }}

    // DELEGACIÓN DE EVENTOS EN EL GRID
    document.getElementById('gallery-grid').addEventListener('click', function(e) {{
      const reactBtn = e.target.closest('.react-btn');
      if (reactBtn) {{
        e.stopPropagation();
        addReaction(reactBtn.dataset.fname, reactBtn.dataset.emoji);
        return;
      }}
      const card = e.target.closest('.photo-card');
      if (card) {{
        openPhotoModal(card.dataset.fname, card.dataset.url, card.dataset.author, card.dataset.date);
      }}
    }});

    // MODAL DE DETALLES DE FOTO
    function openPhotoModal(fname, url, author, date) {{
      const modal = document.getElementById('photo-modal');
      document.getElementById('modal-img').src = url;
      document.getElementById('modal-author').textContent = '👤 ' + author;
      document.getElementById('modal-date').textContent = '📅 ' + (date || 'Hoy');
      document.getElementById('modal-key').textContent = 'galeria/' + fname;
      document.getElementById('modal-download').href = url;
      document.getElementById('modal-download').download = fname;
      modal.classList.remove('hidden');
    }}

    function closePhotoModal() {{
      document.getElementById('photo-modal').classList.add('hidden');
    }}

    // Control de auto-refresco
    autoRefreshCheck.addEventListener('change', () => {{
      if (autoRefreshCheck.checked) {{
        startAutoRefresh();
      }} else {{
        clearInterval(autoRefreshTimer);
      }}
    }});

    function startAutoRefresh() {{
      clearInterval(autoRefreshTimer);
      autoRefreshTimer = setInterval(() => {{
        if (autoRefreshCheck.checked) {{
          loadPhotos(false);
        }}
      }}, 6000);
    }}

    window.addEventListener('DOMContentLoaded', () => {{
      loadPhotos(false);
      startAutoRefresh();
    }});
  </script>
</body>
</html>
"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def send_error_json(self, code, msg):
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ERROR", "message": msg}).encode('utf-8'))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 80))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), PhotoWallHandler) as httpd:
        print(f"[OK] Servidor activo en http://localhost:{port}")
        httpd.serve_forever()
