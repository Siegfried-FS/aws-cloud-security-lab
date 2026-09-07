import http.server
import socketserver
import subprocess
import json
import os
import time
import base64

BUCKET_NAME = os.environ.get("BUCKET_NAME", "")
COMMUNITY_NAME = os.environ.get("COMMUNITY_NAME", "AWS Cloud Security Lab")
SPEAKER_MEETUP_URL = os.environ.get("SPEAKER_MEETUP_URL", "https://www.meetup.com/aws-user-group-playa-vicente/")
UNAM_MEETUP_URL = os.environ.get("UNAM_MEETUP_URL", "https://www.meetup.com/aws-sbg-at-unam/")
MIXTLE_DRIVE_URL = os.environ.get("MIXTLE_DRIVE_URL", "https://drive.google.com/drive/folders/1Do2TAG4_kNnOXpiiKBc4qSzilOxZQ_N6?usp=drive_link")
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
            
            doc_filename = "Guia_Oportunidades_Becas_AWS_2026.pdf"
            direct_url = f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/docs/{doc_filename}" if BUCKET_NAME else "https://s3.amazonaws.com/demo-seguridad-cloud/docs/Guia_Oportunidades_Becas_AWS_2026.pdf"
            
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
            
            doc_filename = "Guia_Oportunidades_Becas_AWS_2026.pdf"
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

        if clean_path in ["/docs/Guia_Oportunidades_Becas_AWS_2026.pdf", "/docs/AWS_certification_paths.pdf"]:
            req_name = os.path.basename(self.path)
            doc_path = os.path.join(os.path.dirname(__file__), "docs", req_name)
            if not os.path.exists(doc_path):
                doc_path = os.path.join(os.path.dirname(__file__), "docs", "Guia_Oportunidades_Becas_AWS_2026.pdf")
            if not os.path.exists(doc_path):
                doc_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "Guia_Oportunidades_Becas_AWS_2026.pdf")
            if not os.path.exists(doc_path):
                doc_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "AWS_certification_paths.pdf")
            
            if os.path.exists(doc_path):
                self.send_response(200)
                self.send_header('Content-type', 'application/pdf')
                self.send_header('Content-Disposition', f'attachment; filename="{req_name}"')
                self.end_headers()
                with open(doc_path, 'rb') as f:
                    self.wfile.write(f.read())
                return

        # RENDERIZADO DEL SITIO WEB PRINCIPAL (HTML / CSS / JS CLIENTE)
        html = f"""<!DOCTYPE html>
<html lang="es" class="scroll-smooth">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
  <title>Mural de Seguridad AWS · {COMMUNITY_NAME}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --cyan-neon: #00e5ff;
      --amber-neon: #ffb800;
      --emerald-neon: #10b981;
    }}
    body {{
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: #060913;
      background-image: 
        radial-gradient(ellipse at 50% 0%, rgba(0, 229, 255, 0.15) 0%, transparent 60%),
        radial-gradient(circle at 85% 30%, rgba(139, 92, 246, 0.08) 0%, transparent 45%),
        linear-gradient(rgba(6, 9, 19, 0.98), rgba(6, 9, 19, 0.98));
      color: #f1f5f9;
      min-height: 100vh;
    }}
    .font-mono {{ font-family: 'JetBrains Mono', monospace; }}
    .sec-card {{
      background: rgba(13, 19, 36, 0.88);
      border: 1px solid rgba(0, 229, 255, 0.22);
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
      border-radius: 16px;
      backdrop-filter: blur(12px);
    }}
    .dropzone-active {{
      border-color: #00e5ff !important;
      background: rgba(0, 229, 255, 0.08) !important;
    }}
    @keyframes pulse-ring {{
      0% {{ transform: scale(0.95); opacity: 0.8; }}
      50% {{ transform: scale(1.15); opacity: 0.3; }}
      100% {{ transform: scale(0.95); opacity: 0.8; }}
    }}
    .pulse-ring {{
      animation: pulse-ring 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }}
  </style>
</head>
<body class="flex flex-col justify-between p-3 sm:p-6 max-w-3xl mx-auto w-full antialiased selection:bg-cyan-500 selection:text-slate-950">

  <!-- TOP BAR: AWS NODE STATUS (ARCADE HUD) -->
  <aside class="w-full mb-4">
    <div class="sec-card px-3.5 py-2 flex flex-wrap items-center justify-between gap-2 text-[10px] sm:text-xs font-mono border-cyan-500/30">
      <div class="flex items-center gap-2">
        <span class="relative flex h-2.5 w-2.5">
          <span class="pulse-ring absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
        </span>
        <span class="font-bold text-white uppercase tracking-wider">AWS EC2 ONLINE</span>
        <span class="text-gray-500">|</span>
        <span class="text-cyan-300">t2.micro</span>
        <span class="text-gray-500">|</span>
        <span class="text-gray-400">{AWS_REGION}</span>
      </div>
      <div class="flex items-center gap-2">
        <span class="px-2 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 font-semibold">
          IAM ROLE ACTIVE
        </span>
        <span class="px-2 py-0.5 rounded bg-purple-500/10 border border-purple-500/30 text-purple-300 font-semibold">
          S3 BPA: ON
        </span>
      </div>
    </div>
  </aside>

  <!-- CABECERA PRINCIPAL -->
  <header class="text-center space-y-2 mb-6 pt-1">
    <div class="inline-flex items-center gap-2 px-3.5 py-1 rounded-full bg-cyan-500/10 border border-cyan-400/40 text-cyan-300 text-xs font-mono font-bold uppercase tracking-wider">
      <span>🛡️</span> DEMO INTERACTIVA EN VIVO · AWS CLOUD SECURITY
    </div>
    
    <h1 class="text-2xl sm:text-4xl font-extrabold text-white tracking-tight leading-tight">
      {COMMUNITY_NAME}
    </h1>
    
    <p class="text-xs sm:text-sm font-mono text-gray-400 max-w-lg mx-auto">
      Experimenta en tiempo real cómo <b class="text-cyan-300">AWS IAM</b>, los <b class="text-amber-300">Security Groups</b> y <b class="text-emerald-300">Amazon S3</b> protegen las aplicaciones en la nube.
    </p>

    <!-- NAVEGACIÓN RÁPIDA -->
    <nav class="flex justify-center gap-2 pt-2">
      <a href="#experimento-upload" class="px-3 py-1 rounded-lg bg-slate-900 border border-gray-800 text-[11px] font-mono text-gray-300 hover:text-cyan-300 hover:border-cyan-500/50 transition">
        📸 Subir Foto
      </a>
      <a href="#experimento-s3" class="px-3 py-1 rounded-lg bg-slate-900 border border-gray-800 text-[11px] font-mono text-gray-300 hover:text-amber-300 hover:border-amber-500/50 transition">
        📦 Reto S3 STS
      </a>
      <a href="#mural-galeria" class="px-3 py-1 rounded-lg bg-slate-900 border border-gray-800 text-[11px] font-mono text-gray-300 hover:text-purple-300 hover:border-purple-500/50 transition">
        🖼️ Ver Mural
      </a>
    </nav>
  </header>

  <!-- CONTENIDO INTERACTIVO -->
  <main class="space-y-6">

    <!-- EXPERIMENTO 1: SUBIDA DE FOTOS (s3:PutObject) -->
    <section id="experimento-upload" class="sec-card p-5 sm:p-6 space-y-4">
      <div class="flex items-center justify-between border-b border-cyan-500/20 pb-3">
        <div class="flex items-center gap-2">
          <span class="text-lg">📸</span>
          <div>
            <h2 class="text-sm sm:text-base font-mono font-bold text-white uppercase tracking-wider">
              1. Sube tu Foto o Selfie al Mural
            </h2>
            <p class="text-[10px] font-mono text-cyan-400">Demostración en Vivo: AWS IAM Role & s3:PutObject</p>
          </div>
        </div>
        <span class="px-2.5 py-1 rounded text-[10px] font-mono font-bold bg-cyan-500/10 border border-cyan-400/40 text-cyan-300">
          CAPA IAM
        </span>
      </div>

      <!-- INVITACIÓN PARA EVENTO PRESENCIAL -->
      <div class="bg-gradient-to-r from-cyan-950/40 via-slate-900/60 to-purple-950/40 border border-cyan-500/30 rounded-xl p-4 space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span class="text-base">📍</span>
            <span class="text-xs font-bold text-white uppercase tracking-wide">¡Participa desde tu lugar con tu celular!</span>
          </div>
          <span class="text-[9px] font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 font-bold">
            EN VIVO
          </span>
        </div>
        
        <p class="text-xs text-gray-300 leading-relaxed">
          Toma una foto con tu cámara para proyectarla en el auditorio. Tu navegador enviará la imagen a la instancia EC2, y el servidor ejecutará la llamada a Amazon S3 usando su <b>IAM Instance Profile</b> sin ninguna contraseña escrita en código.
        </p>

        <!-- CHIPS DE IDEAS PARA ASISTENTES -->
        <div class="pt-1">
          <span class="text-[10px] font-mono text-cyan-300 font-semibold uppercase tracking-wider block mb-1.5">
            💡 ¿Qué foto puedes subir hoy?
          </span>
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-1.5 text-[11px] font-mono text-gray-200">
            <div class="bg-slate-950/80 px-2.5 py-2 rounded-lg border border-gray-800 flex items-center gap-1.5">
              <span>🤳</span> Selfie personal
            </div>
            <div class="bg-slate-950/80 px-2.5 py-2 rounded-lg border border-gray-800 flex items-center gap-1.5">
              <span>👥</span> Con amigos
            </div>
            <div class="bg-slate-950/80 px-2.5 py-2 rounded-lg border border-gray-800 flex items-center gap-1.5">
              <span>🖥️</span> Pantalla charla
            </div>
            <div class="bg-slate-950/80 px-2.5 py-2 rounded-lg border border-gray-800 flex items-center gap-1.5">
              <span>🎙️</span> El auditorio
            </div>
          </div>
        </div>
      </div>

      <!-- FORMULARIO DE CAPTURA -->
      <div class="space-y-3 pt-1">
        <!-- NOMBRE Y ATRIBUTO -->
        <div class="space-y-1.5">
          <div class="flex items-center justify-between">
            <label class="block text-xs font-mono font-semibold text-gray-300">
              Tu Nombre, Alias o Institución:
            </label>
            <div class="flex gap-1 text-[10px] font-mono">
              <button type="button" onclick="setAlias('Estudiante')" class="text-cyan-400 hover:underline px-1">Estudiante</button>
              <span class="text-gray-600">·</span>
              <button type="button" onclick="setAlias('Builder')" class="text-cyan-400 hover:underline px-1">Builder</button>
              <span class="text-gray-600">·</span>
              <button type="button" onclick="setAlias('Ponente')" class="text-cyan-400 hover:underline px-1">Ponente</button>
            </div>
          </div>
          <input type="text" id="author-input" placeholder="Ej: Roberto / Andrea (Ingeniería) / Asistente" class="w-full px-4 py-3 bg-slate-950 border border-gray-700 rounded-xl text-base sm:text-sm text-white focus:outline-none focus:border-cyan-400 font-mono transition">
        </div>

        <!-- INPUTS OCULTOS DE CÁMARA Y ARCHIVO -->
        <input type="file" id="camera-input" accept="image/*" capture="user" class="hidden">
        <input type="file" id="file-input" accept="image/*" class="hidden">

        <!-- BOTONES DE DISPARO DUAL (CÁMARA / GALERÍA) -->
        <div class="grid grid-cols-2 gap-2.5">
          <button type="button" onclick="document.getElementById('camera-input').click()" class="py-3 px-3 rounded-xl border border-cyan-400/50 bg-cyan-950/40 hover:bg-cyan-900/60 text-cyan-200 font-mono text-xs font-bold flex items-center justify-center gap-2 transition active:scale-95 shadow-md">
            <span class="text-base">📸</span>
            <span>Tomar Selfie Ahora</span>
          </button>
          
          <button type="button" onclick="document.getElementById('file-input').click()" class="py-3 px-3 rounded-xl border border-gray-700 bg-slate-900 hover:bg-slate-800 text-gray-200 font-mono text-xs font-bold flex items-center justify-center gap-2 transition active:scale-95 shadow-md">
            <span class="text-base">🖼️</span>
            <span>Elegir de Galería</span>
          </button>
        </div>

        <!-- DRAG AND DROP ZONE (PARA LAPTOPS / ESCRITORIO) -->
        <div id="drop-zone" class="hidden sm:block border-2 border-dashed border-gray-700/80 rounded-xl p-4 text-center hover:border-cyan-500/60 transition cursor-pointer" onclick="document.getElementById('file-input').click()">
          <p class="text-xs font-mono text-gray-400">
            💻 ¿Estás en laptop? Arrastra y suelta tu foto aquí o haz clic para seleccionarla.
          </p>
        </div>

        <!-- CAJA DE PREVISUALIZACIÓN -->
        <div id="preview-box" class="hidden rounded-xl border border-cyan-400/50 bg-slate-950 p-3 space-y-2 text-center transition-all">
          <div class="relative inline-block max-w-full">
            <img id="preview-img" class="max-h-56 mx-auto rounded-lg border border-cyan-500/40 shadow-xl object-contain">
            <button type="button" onclick="clearPreview()" class="absolute top-2 right-2 bg-slate-900/90 text-rose-400 hover:text-rose-200 rounded-full p-1.5 text-xs border border-rose-500/40" title="Eliminar foto">
              ✕
            </button>
          </div>
          <div class="flex items-center justify-center gap-3 text-[11px] font-mono text-cyan-300">
            <span>✨ Foto lista</span>
            <span class="text-gray-600">•</span>
            <span id="preview-size">0 KB</span>
          </div>
        </div>

        <!-- BOTÓN DE ACCIÓN PRINCIPAL (SUBIR A S3) -->
        <button onclick="uploadPhoto()" id="btn-upload" class="w-full py-3.5 rounded-xl font-bold text-xs sm:text-sm bg-gradient-to-r from-cyan-400 via-teal-400 to-blue-500 hover:from-cyan-300 hover:to-blue-400 text-slate-950 transition flex items-center justify-center gap-2 shadow-lg shadow-cyan-500/20 active:scale-95 uppercase tracking-wide">
          <span id="upload-btn-text">🚀 Subir Foto al Mural (Probar s3:PutObject)</span>
        </button>

        <!-- BARRA DE PROGRESO DE LA PETICIÓN -->
        <div id="upload-progress" class="hidden space-y-1 pt-1">
          <div class="w-full bg-slate-950 rounded-full h-2 overflow-hidden border border-cyan-500/30">
            <div id="progress-bar" class="bg-gradient-to-r from-cyan-400 to-emerald-400 h-full w-0 transition-all duration-300"></div>
          </div>
          <p id="progress-text" class="text-[10px] font-mono text-cyan-400 text-center">Iniciando llamada a AWS API...</p>
        </div>

        <!-- ALERT BOX EXPERIMENTO 1 -->
        <div id="alert-box" class="hidden p-4 text-xs font-mono rounded-xl border transition-all"></div>
      </div>
    </section>


    <!-- EXPERIMENTO 2: DESCARGA S3 PRIVADO VS MENOR PRIVILEGIO -->
    <section id="experimento-s3" class="sec-card p-5 sm:p-6 space-y-4 border-amber-500/30">
      <div class="flex items-center justify-between border-b border-amber-500/20 pb-3">
        <div class="flex items-center gap-2">
          <span class="text-lg">📦</span>
          <div>
            <h2 class="text-sm sm:text-base font-mono font-bold text-white uppercase tracking-wider">
              2. Laboratorio S3: Menor Privilegio & AWS STS
            </h2>
            <p class="text-[10px] font-mono text-amber-300">Catálogo Oficial de Becas y Vouchers de Certificación</p>
          </div>
        </div>
        <span class="px-2.5 py-1 rounded text-[10px] font-mono font-bold bg-amber-500/10 border border-amber-400/40 text-amber-300">
          CAPA S3 + STS
        </span>
      </div>

      <p class="text-xs text-gray-300 leading-relaxed">
        El bucket de Amazon S3 almacena la <b>Guía Oficial de Becas AWS 2026</b>. Comprueba cómo la política de <b>Block Public Access</b> impide que un atacante descargue el archivo anónimamente vs cómo la aplicación genera un pase temporal firmado por AWS STS:
      </p>

      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
        <!-- BOTÓN 1: ACCESO PÚBLICO DIRECTO (FALLA CON 403) -->
        <button onclick="testPublicDownload()" id="btn-public-download" class="p-4 rounded-xl border border-rose-500/50 bg-rose-950/40 hover:bg-rose-900/60 text-rose-200 text-xs font-mono font-bold flex flex-col items-center justify-center gap-1.5 transition text-center active:scale-95 shadow-md">
          <span class="text-xl">🛑</span>
          <span class="text-sm text-white">1. Probar Descarga Directa</span>
          <span class="text-[10px] font-normal text-rose-300/80">URL Pública sin autenticar</span>
          <span class="text-[9px] px-2 py-0.5 rounded bg-rose-900/80 border border-rose-500/40 text-rose-200 mt-1">
            Esperado: 403 Forbidden
          </span>
        </button>

        <!-- BOTÓN 2: DESCARGA CON PRESIGNED URL (200 OK) -->
        <button onclick="testPresignedDownload()" id="btn-presigned-download" class="p-4 rounded-xl border border-emerald-500/50 bg-emerald-950/40 hover:bg-emerald-900/60 text-emerald-200 text-xs font-mono font-bold flex flex-col items-center justify-center gap-1.5 transition text-center active:scale-95 shadow-md">
          <span class="text-xl">⚡</span>
          <span class="text-sm text-white">2. Descarga Segura con STS</span>
          <span class="text-[10px] font-normal text-emerald-300/80">Presigned URL temporal (15 min)</span>
          <span class="text-[9px] px-2 py-0.5 rounded bg-emerald-900/80 border border-emerald-500/40 text-emerald-200 mt-1">
            Esperado: 200 OK + Descarga
          </span>
        </button>
      </div>

      <!-- ALERT BOX EXPERIMENTO 2 -->
      <div id="s3-alert-box" class="hidden p-4 text-xs font-mono rounded-xl border transition-all"></div>
    </section>


    <!-- MURAL COLECTIVO DE FOTOS -->
    <section id="mural-galeria" class="space-y-3">
      <div class="sec-card p-4 sm:p-5">
        <div class="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800 pb-3">
          <div class="flex items-center gap-2">
            <span class="text-lg">🖼️</span>
            <div>
              <h2 class="text-sm sm:text-base font-mono font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <span>Mural Colectivo de la Sesión</span>
                <span id="photo-counter-badge" class="text-[10px] px-2 py-0.5 rounded-full bg-cyan-500/10 border border-cyan-400/40 text-cyan-300">
                  0 fotos
                </span>
              </h2>
              <p class="text-[10px] font-mono text-gray-400">Fotos subidas en vivo por los participantes</p>
            </div>
          </div>

          <div class="flex items-center gap-3">
            <!-- AUTO-REFRESH TOGGLE -->
            <label class="inline-flex items-center gap-1.5 text-[11px] font-mono text-gray-300 cursor-pointer">
              <input type="checkbox" id="auto-refresh-check" checked class="rounded accent-cyan-400">
              <span>Auto-actualizar (6s)</span>
            </label>
            <button onclick="loadPhotos(true)" class="p-2 rounded-lg bg-slate-950 border border-gray-700 text-xs text-cyan-300 hover:border-cyan-400 transition" title="Actualizar ahora">
              🔄
            </button>
          </div>
        </div>

        <!-- REJILLA DE FOTOS -->
        <div id="gallery-grid" class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-3 gap-3 pt-4">
          <div class="p-8 col-span-full text-center text-xs text-gray-500 font-mono">
            ⏳ Cargando fotos del mural en Amazon S3...
          </div>
        </div>
      </div>
    </section>

  </main>


  <!-- MODAL PARA VER FOTO EN ALTA RESOLUCIÓN Y DETALLES IAM -->
  <div id="photo-modal" class="fixed inset-0 z-50 hidden bg-slate-950/90 backdrop-blur-md flex items-center justify-center p-4" onclick="closePhotoModal(event)">
    <div class="sec-card max-w-lg w-full p-4 sm:p-5 space-y-3 relative border-cyan-400/60" onclick="event.stopPropagation()">
      <button onclick="closePhotoModal()" class="absolute top-3 right-3 text-gray-400 hover:text-white font-mono text-lg p-1">✕</button>
      
      <div class="rounded-xl overflow-hidden border border-gray-800 bg-black">
        <img id="modal-img" class="w-full max-h-[60vh] object-contain mx-auto">
      </div>

      <div class="space-y-1.5 pt-1">
        <div class="flex items-center justify-between">
          <div id="modal-author" class="font-mono font-bold text-white text-sm"></div>
          <div id="modal-date" class="text-[10px] font-mono text-gray-400"></div>
        </div>
        
        <div class="bg-slate-950 p-2.5 rounded-lg border border-gray-800 text-[10px] font-mono text-gray-300 space-y-1">
          <div class="flex justify-between"><span class="text-gray-500">IAM Role:</span> <span class="text-cyan-300">SecurityDemoRole-EC2</span></div>
          <div class="flex justify-between"><span class="text-gray-500">Storage:</span> <span class="text-emerald-300">Amazon S3 Standard (SSE-S3)</span></div>
          <div class="flex justify-between"><span class="text-gray-500">S3 Key:</span> <span id="modal-key" class="text-amber-300 truncate max-w-[200px]"></span></div>
        </div>
      </div>

      <div class="flex gap-2 pt-1">
        <a id="modal-download" target="_blank" download class="flex-1 py-2.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-mono font-bold text-xs text-center transition">
          📥 Descargar Foto
        </a>
        <button onclick="closePhotoModal()" class="px-4 py-2.5 rounded-lg bg-slate-900 border border-gray-700 text-gray-300 font-mono text-xs hover:text-white transition">
          Cerrar
        </button>
      </div>
    </div>
  </div>


  <!-- PIE DE PÁGINA: ROBERTO FLORES & COMUNIDADES -->
  <footer class="mt-8 pt-6 border-t border-gray-800/80 space-y-4 text-center">
    <div class="sec-card p-4 sm:p-5 space-y-3 text-left border-cyan-500/20 bg-slate-950/80">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex items-center gap-2.5">
          <span class="text-xl">🎙️</span>
          <div>
            <div class="text-sm font-bold text-white font-mono">Roberto Flores Segundo</div>
            <div class="text-[11px] text-cyan-400 font-mono">Founder & Leader AWS UG Playa Vicente · Becario AWS All Builders Welcome</div>
          </div>
        </div>
        <span class="px-2.5 py-1 rounded text-[10px] font-mono font-bold bg-amber-500/10 border border-amber-500/30 text-amber-300">
          漂泊者 · Vagabundo de la Nube
        </span>
      </div>

      <p class="text-xs text-gray-300 italic border-l-2 border-amber-400/70 pl-3 my-2 font-mono leading-relaxed">
        «En cualquier comunidad o reto de la vida, si alguien me pregunta quién soy, siempre diré lo mismo: solo soy un vagabundo que va pasando por aquí para aprender, compartir y sumar con ustedes.»
      </p>

      <div class="text-[10px] text-gray-400 font-mono flex flex-wrap gap-x-4 gap-y-1 pt-2 border-t border-gray-800/80">
        <span>🤜🤛 Choque de puños & comunidad</span>
        <span>☕ Charlas técnicas abiertas</span>
        <span>🚀 Aprender construyendo (Builders)</span>
      </div>
    </div>

    <!-- ENLACES DE COMUNIDAD Y MATERIALES -->
    <div class="space-y-2 pt-1">
      <div class="text-[10px] font-mono text-gray-400 font-bold uppercase tracking-wider">
        Materiales de la Charla y Enlaces de Comunidad
      </div>
      <div class="flex flex-wrap gap-2.5 justify-center pt-0.5">
        <a href="{MIXTLE_DRIVE_URL}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl font-bold text-xs bg-pink-950/50 border border-pink-400/50 text-pink-300 hover:bg-pink-900/80 transition font-mono shadow-md active:scale-95">
          <span>📁</span> Reto Mixtle (Google Drive)
        </a>
        <a href="{SPEAKER_MEETUP_URL}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl font-bold text-xs bg-amber-950/50 border border-amber-500/40 text-amber-300 hover:bg-amber-900/80 transition font-mono shadow-md active:scale-95">
          <span>🌴</span> AWS UG Playa Vicente
        </a>
        <a href="{UNAM_MEETUP_URL}" target="_blank" rel="noopener noreferrer" class="inline-flex items-center justify-center gap-2 px-3.5 py-2.5 rounded-xl font-bold text-xs bg-cyan-950/60 border border-cyan-400/50 text-cyan-300 hover:bg-cyan-900/80 transition font-mono shadow-md active:scale-95">
          <span>🎓</span> Meetup AWS SBG
        </a>
      </div>
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
            '<div class="pt-1"><a href="' + data.url + '" target="_blank" download class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-400 hover:bg-emerald-300 text-slate-950 font-bold text-xs transition">📥 Descargar Guía de Becas AWS (PDF)</a></div>';
          
          // Disparo automático de descarga
          const link = document.createElement('a');
          link.href = data.url;
          link.download = 'Guia_Oportunidades_Becas_AWS_2026.pdf';
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
