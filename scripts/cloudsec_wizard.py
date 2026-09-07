#!/usr/bin/env python3
"""
Cloud Security Lab — Live Session Photo Wall Wizard
Framework interactivo de fundamentos de seguridad en AWS con AWS CDK
y demostrar en vivo Security Groups e IAM Least Privilege (s3:PutObject).
"""

import os
import sys
import json
import subprocess
import shutil
import time

# PALETA SYNTHWAVE / CYBERPUNK RETRO GAMER (256-COLOR + ANSI)
PINK = "\033[38;5;198m"
PURPLE = "\033[38;5;141m"
CYAN = "\033[38;5;51m"
GREEN = "\033[38;5;82m"
YELLOW = "\033[38;5;226m"
ORANGE = "\033[38;5;208m"
RED = "\033[38;5;196m"
WHITE = "\033[97m"
BOLD = "\033[1m"
DIM = "\033[2m"
BLINK = "\033[5m"
RESET = "\033[0m"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CDK_DIR = os.path.join(BASE_DIR, "cdk")
CONFIG_PATH = os.path.join(BASE_DIR, "presentacion", "demo-config.json")


def banner():
    print(f"\n{PINK}{BOLD}  ██████╗██╗      ██████╗ ██╗   ██╗██████╗ ███████╗███████╗ ██████╗ {RESET}")
    print(f"{PINK}{BOLD} ██╔════╝██║     ██╔═══██╗██║   ██║██╔══██╗██╔════╝██╔════╝██╔════╝ {RESET}")
    print(f"{PURPLE}{BOLD} ██║     ██║     ██║   ██║██║   ██║██║  ██║███████╗█████╗  ██║      {RESET}")
    print(f"{PURPLE}{BOLD} ██║     ██║     ██║   ██║██║   ██║██║  ██║╚════██║██╔══╝  ██║      {RESET}")
    print(f"{CYAN}{BOLD} ╚██████╗███████╗╚██████╔╝╚██████╔╝██████╔╝███████║███████╗╚██████╗ {RESET}")
    print(f"{CYAN}{BOLD}  ╚═════╝╚══════╝ ╚═════╝  ╚═════╝ ╚═════╝ ╚══════╝╚══════╝ ╚═════╝ {RESET}")
    print(f"     {YELLOW}{BOLD}:: A R C A D E   E D I T I O N   //   C L O U D   S E C U R I T Y ::{RESET}")
    print(f"     {GREEN}{BOLD}[ AWS CLOUD SECURITY LAB ]{RESET}  ·  {CYAN}SOFTWARE LIBRE & REPLICABLE{RESET}\n")


def check_prerequisites():
    tools = ["node", "npm", "aws"]
    missing = [t for t in tools if not shutil.which(t)]
    if missing:
        print(f"{RED}{BOLD}[FAIL] SYSTEM FAILURE: Faltan herramientas necesarias: {", ".join(missing)}{RESET}")
        sys.exit(1)


def get_aws_profiles():
    try:
        res = subprocess.run(["aws", "configure", "list-profiles"], capture_output=True, text=True, check=True)
        profiles = [p.strip() for p in res.stdout.splitlines() if p.strip()]
        return profiles if profiles else ["default"]
    except Exception:
        return ["default"]


def strip_ansi(text):
    import re
    return re.sub(r"\033\[[0-9;]*m", "", text)


def arcade_box_line(content, width=82, border_color=None, reset=RESET, indent=2):
    if border_color is None:
        border_color = f"{PURPLE}{BOLD}"
    vis_len = len(strip_ansi(content))
    padding = max(0, width - vis_len - indent)
    return f"{border_color}║{reset}{" " * indent}{content}{" " * padding}{border_color}║{reset}"


def select_aws_profile():
    profiles = get_aws_profiles()
    current_profile = os.environ.get("AWS_PROFILE", "default")
    if current_profile not in profiles and profiles:
        current_profile = profiles[0]

    print(f"{PINK}{BOLD}┌── [ SELECT OPERATIVE // AWS PROFILE ] ───────────────────────────────────┐{RESET}")
    for idx, prof in enumerate(profiles, 1):
        is_current = f" {GREEN}◄ [HERO SELECTED]{RESET}" if prof == current_profile else ""
        print(f"{PINK}│{RESET}  {CYAN}{BOLD}[{idx}]{RESET} {WHITE}{prof:<20}{RESET}{is_current:<43}{PINK}│{RESET}")
    print(f"{PINK}│{RESET}  {CYAN}{BOLD}[0]{RESET} {YELLOW}CUSTOM STS / VARIABLE DE ENTORNO (AWS_ACCESS_KEY_ID){RESET}{" ":<12}{PINK}│{RESET}")
    print(f"{PINK}└──{YELLOW}[ CREDITS: 99 ]{PINK}────────────────────────────────────────────────────────┘{RESET}")

    choice = input(f"\n{YELLOW}{BOLD}>> Elige tu slot {DIM}[Enter para \x27{current_profile}\x27]{RESET}{YELLOW}{BOLD}: {RESET}").strip()

    selected_profile = current_profile
    if choice == "0":
        selected_profile = None
    elif choice.isdigit() and 1 <= int(choice) <= len(profiles):
        selected_profile = profiles[int(choice) - 1]

    if selected_profile:
        os.environ["AWS_PROFILE"] = selected_profile
        print(f"\n{GREEN}[+] Operative activo: {BOLD}{selected_profile}{RESET}")
    else:
        print(f"\n{GREEN}[+] Usando variables de entorno activas (STS).{RESET}")

    cmd = ["aws", "sts", "get-caller-identity", "--output", "json"]
    if selected_profile:
        cmd.extend(["--profile", selected_profile])

    try:
        sts_res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        identity = json.loads(sts_res.stdout)
        account_id = identity.get("Account", "Desconocida")
        arn = identity.get("Arn", "Desconocido")
        
        masked_account = f"{account_id[:4]}-****-{account_id[-4:]}" if len(account_id) == 12 else "****"
        masked_arn = arn.replace(account_id, masked_account)

        region_cmd = ["aws", "configure", "get", "region"]
        if selected_profile:
            region_cmd.extend(["--profile", selected_profile])
        region_res = subprocess.run(region_cmd, capture_output=True, text=True)
        region = region_res.stdout.strip() or os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        os.environ["AWS_DEFAULT_REGION"] = region
        os.environ["CDK_DEFAULT_REGION"] = region
        os.environ["CDK_DEFAULT_ACCOUNT"] = account_id

        print(f"\n{CYAN}{BOLD}╔══════════════════════════════════════════════════════════════════════════════════╗{RESET}")
        print(f"{CYAN}{BOLD}║                    [ OPERATIVE TELEMETRY HUD // PLAYER 1 ]                       ║{RESET}")
        print(f"{CYAN}{BOLD}╠══════════════════════════════════════════════════════════════════════════════════╣{RESET}")
        print(arcade_box_line(f"TARGET REALM : {YELLOW}{BOLD}{masked_account:<24}{RESET} REGION  : {CYAN}{BOLD}{region:<24}{RESET}", border_color=f"{CYAN}{BOLD}"))
        print(arcade_box_line(f"OPERATIVE    : {DIM}{masked_arn[-24:]:<24}{RESET} ENGINE  : {GREEN}{BOLD}{'AWS CDK v2 (LTS)':<24}{RESET}", border_color=f"{CYAN}{BOLD}"))
        print(arcade_box_line(f"MISSION      : {PINK}{BOLD}{'CLOUD SECURITY LAB':<24}{RESET} MODE    : {WHITE}{BOLD}{'LIVE DEMO & AUDIT':<24}{RESET}", border_color=f"{CYAN}{BOLD}"))
        print(arcade_box_line(f"SYSTEM POWER : {GREEN}[██████████] 100%{RESET}{" ":<8} STATUS  : {YELLOW}{BOLD}{'READY TO PLAY':<24}{RESET}", border_color=f"{CYAN}{BOLD}"))
        print(f"{CYAN}{BOLD}╚══════════════════════════════════════════════════════════════════════════════════╝{RESET}")

        confirm = input(f"\n{YELLOW}{BOLD}[?] ¿Iniciar mision en este Realm? [S/n]: {RESET}").strip().lower()
        if confirm in ["n", "no"]:
            print(f"{RED}Partida abortada por el jugador.{RESET}")
            sys.exit(0)

        return selected_profile, account_id, region

    except subprocess.CalledProcessError as e:
        print(f"\n{RED}[FAIL] Error de conexion con AWS:{RESET} {e.stderr.strip()}")
        sys.exit(1)


def run_aws_cmd(args, profile=None):
    cmd = ["aws"] + args
    if profile:
        cmd.extend(["--profile", profile])
    return subprocess.run(cmd, capture_output=True, text=True)


def check_cdk_bootstrap(profile, region, account_id):
    expected_bucket = f"cdk-hnb659fds-assets-{account_id}-{region}"
    print(f"\n{CYAN}[*] Verificando estado de AWS CDK y almacenamiento de assets...{RESET}")

    # 1. Comprobar stack CloudFormation CDKToolkit
    cfn_res = run_aws_cmd(["cloudformation", "describe-stacks", "--stack-name", "CDKToolkit", "--region", region], profile)
    cfn_exists = (cfn_res.returncode == 0)

    # 2. Comprobar bucket fisico de CDK en S3
    bkt_res = run_aws_cmd(["s3api", "head-bucket", "--bucket", expected_bucket], profile)
    bucket_exists = (bkt_res.returncode == 0)

    if cfn_exists and bucket_exists:
        print(f"{GREEN}[OK] Entorno CDK listo (Stack CDKToolkit y bucket {expected_bucket} verificados).{RESET}")
        return

    if not cfn_exists:
        print(f"{YELLOW}[!] La cuenta requiere inicializacion de AWS CDK (Bootstrap) en {region}.{RESET}")
        run_boot = input(f"[?] ¿Ejecutar \x27cdk bootstrap\x27 ahora? {BOLD}[S/n]{RESET}: ").strip().lower()
        if run_boot not in ["n", "no"]:
            boot_cmd = ["npx", "cdk", "bootstrap", f"aws://{account_id}/{region}"]
            if profile: boot_cmd.extend(["--profile", profile])
            subprocess.run(boot_cmd, cwd=CDK_DIR, check=True)
            print(f"{GREEN}[OK] CDK Bootstrap completado con exito.{RESET}")
        else:
            sys.exit(1)
        return

    # Si el stack CDKToolkit existe pero el bucket S3 fue eliminado o falta
    if cfn_exists and not bucket_exists:
        print(f"{YELLOW}[WARN] Detectado drift de CDK: stack CDKToolkit existe pero falta bucket \x27{expected_bucket}\x27.{RESET}")
        print(f"{CYAN}[*] Auto-reparando bucket de CDK con politicas seguras (SSE AES256 + Block Public Access)...{RESET}")
        create_args = ["s3api", "create-bucket", "--bucket", expected_bucket]
        if region != "us-east-1":
            create_args.extend(["--create-bucket-configuration", f"LocationConstraint={region}"])
        c_res = run_aws_cmd(create_args, profile)
        if c_res.returncode == 0:
            pab = "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
            run_aws_cmd(["s3api", "put-public-access-block", "--bucket", expected_bucket, "--public-access-block-configuration", pab], profile)
            sse = '{"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]}'
            run_aws_cmd(["s3api", "put-bucket-encryption", "--bucket", expected_bucket, "--server-side-encryption-configuration", sse], profile)
            print(f"{GREEN}[OK] Bucket de CDK restaurado y protegido. Despliegues asegurados.{RESET}")
        else:
            print(f"{RED}[FAIL] No se pudo auto-recrear el bucket: {c_res.stderr.strip()}{RESET}")
            print(f"{YELLOW}[*] Reintentando CDK bootstrap con bandera --force...{RESET}")
            boot_cmd = ["npx", "cdk", "bootstrap", "--force", f"aws://{account_id}/{region}"]
            if profile: boot_cmd.extend(["--profile", profile])
            subprocess.run(boot_cmd, cwd=CDK_DIR, check=True)


def print_ascii_qr(url):
    print(f"\n{BOLD}[ QR MATRIX ] Escanea para conectar al nodo en vivo:{RESET}")
    try:
        res = subprocess.run(["curl", "-s", f"qrenco.de/{url}"], capture_output=True, text=True, timeout=3)
        if res.returncode == 0 and res.stdout:
            print(res.stdout)
            return
    except Exception:
        pass
    print(f"{CYAN}>> Abre en tu navegador movil: {BOLD}{url}{RESET}")


def save_demo_config(ip, url, account_id, region):
    data = {
        "demoIp": ip,
        "demoUrl": url,
        "accountId": account_id,
        "region": region,
        "timestamp": subprocess.run(["date", "+%Y-%m-%d %H:%M:%S"], capture_output=True, text=True).stdout.strip()
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def deploy_stack(profile):
    print(f"\n{CYAN}{BOLD}>> [STAGE 1] INITIATING CDK MAINFRAME LAUNCH PROTOCOL...{RESET}")
    cmd = ["npx", "cdk", "deploy", "--outputs-file", "outputs.json", "--require-approval", "never"]
    if profile: cmd.extend(["--profile", profile])

    res = subprocess.run(cmd, cwd=CDK_DIR)
    if res.returncode != 0:
        print(f"{RED}{BOLD}[FAIL] MISSION FAILED: Fallo el despliegue de CDK.{RESET}")
        sys.exit(1)

    outputs_file = os.path.join(CDK_DIR, "outputs.json")
    if os.path.exists(outputs_file):
        try:
            with open(outputs_file, "r", encoding="utf-8") as f:
                outputs = json.load(f)
            
            stack_data = outputs.get("CloudSecurityMasterclassStack", {})
            ip = stack_data.get("Ec2PublicIp", "")
            url = stack_data.get("WebDemoUrl", f"http://{ip}")

            account_id = os.environ.get("CDK_DEFAULT_ACCOUNT", "")
            region = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
            save_demo_config(ip, url, account_id, region)

            print(f"\n{CYAN}[*] [WATCHDOG] Verificando que el servidor web responda HTTP 200 OK ({url})...{RESET}")
            server_ready = False
            for attempt in range(1, 21):
                chk = subprocess.run(["curl", "-sI", "-m", "2", f"{url}/api/health"], capture_output=True, text=True)
                if "200 OK" in chk.stdout:
                    server_ready = True
                    break
                chk_root = subprocess.run(["curl", "-sI", "-m", "2", url], capture_output=True, text=True)
                if "200 OK" in chk_root.stdout or "SimpleHTTP" in chk_root.stdout:
                    server_ready = True
                    break
                print(f"  {DIM}:: Esperando inicializacion de servicios en EC2 ({attempt * 3}s / 60s)...{RESET}")
                time.sleep(3)

            if server_ready:
                print(f"  {GREEN}{BOLD}[OK] [SYSTEM READY] MAINFRAME OPERATIVO Y RESPONDIENDO HTTP 200 OK.{RESET}")
            else:
                print(f"  {YELLOW}[INFO] El servidor continua iniciando en segundo plano. Estara listo en breve.{RESET}")

            print(f"\n{GREEN}{BOLD}══════════════════════════════════════════════════════════════════════════╗{RESET}")
            print(f"{GREEN}{BOLD}       S T A G E   1   C L E A R !   MURAL DESPLEGADO EXITOSAMENTE        ║{RESET}")
            print(f"{GREEN}{BOLD}══════════════════════════════════════════════════════════════════════════╝{RESET}")
            print(f"  :: {WHITE}{BOLD}MISSION URL:{RESET}        {CYAN}{BOLD}{url}{RESET}")
            print(f"  :: {WHITE}{BOLD}SERVER IP:{RESET}          {YELLOW}{BOLD}{ip}{RESET}")
            print(f"  :: {WHITE}{BOLD}PRESENTACION:{RESET}       Abre {PINK}{BOLD}presentacion/index.html{RESET} (¡Sincronizado!)")

            print_ascii_qr(url)

        except Exception as e:
            print(f"{YELLOW}Outputs listos: {e}{RESET}")


def empty_and_delete_bucket(bucket_name, profile):
    print(f"  [-] Purgando y eliminando bucket S3: {BOLD}{bucket_name}{RESET}")
    try:
        ver_res = run_aws_cmd(["s3api", "list-object-versions", "--bucket", bucket_name, "--output", "json"], profile)
        if ver_res.returncode == 0:
            data = json.loads(ver_res.stdout)
            to_delete = []
            for v in data.get("Versions", []):
                to_delete.append({"Key": v["Key"], "VersionId": v["VersionId"]})
            for d in data.get("DeleteMarkers", []):
                to_delete.append({"Key": d["Key"], "VersionId": d["VersionId"]})
            if to_delete:
                for i in range(0, len(to_delete), 1000):
                    batch = {"Objects": to_delete[i:i+1000], "Quiet": True}
                    run_aws_cmd(["s3api", "delete-objects", "--bucket", bucket_name, "--delete", json.dumps(batch)], profile)
    except Exception:
        pass
    run_aws_cmd(["s3", "rb", f"s3://{bucket_name}", "--force"], profile)


def cleanup_manual_lab_resources(profile):
    print(f"\n{CYAN}[*] Limpiando recursos manuales creados para el laboratorio...{RESET}")
    
    # 1. Limpiar usuarios IAM manuales
    res = run_aws_cmd(["iam", "list-users", "--output", "json"], profile)
    if res.returncode == 0:
        try:
            users = json.loads(res.stdout).get("Users", [])
            for u in users:
                uname = u.get("UserName", "")
                if "estudiante" in uname.lower() or "unam" in uname.lower():
                    print(f"  [-] Eliminando usuario IAM manual: {BOLD}{uname}{RESET}")
                    pol_res = run_aws_cmd(["iam", "list-attached-user-policies", "--user-name", uname, "--output", "json"], profile)
                    if pol_res.returncode == 0:
                        for p in json.loads(pol_res.stdout).get("AttachedPolicies", []):
                            run_aws_cmd(["iam", "detach-user-policy", "--user-name", uname, "--policy-arn", p["PolicyArn"]], profile)
                    in_res = run_aws_cmd(["iam", "list-user-policies", "--user-name", uname, "--output", "json"], profile)
                    if in_res.returncode == 0:
                        for pol_name in json.loads(in_res.stdout).get("PolicyNames", []):
                            run_aws_cmd(["iam", "delete-user-policy", "--user-name", uname, "--policy-name", pol_name], profile)
                    grp_res = run_aws_cmd(["iam", "list-groups-for-user", "--user-name", uname, "--output", "json"], profile)
                    if grp_res.returncode == 0:
                        for g in json.loads(grp_res.stdout).get("Groups", []):
                            run_aws_cmd(["iam", "remove-user-from-group", "--user-name", uname, "--group-name", g["GroupName"]], profile)
                    run_aws_cmd(["iam", "delete-login-profile", "--user-name", uname], profile)
                    key_res = run_aws_cmd(["iam", "list-access-keys", "--user-name", uname, "--output", "json"], profile)
                    if key_res.returncode == 0:
                        for k in json.loads(key_res.stdout).get("AccessKeyMetadata", []):
                            run_aws_cmd(["iam", "delete-access-key", "--user-name", uname, "--access-key-id", k["AccessKeyId"]], profile)
                    run_aws_cmd(["iam", "delete-user", "--user-name", uname], profile)
        except Exception as e:
            print(f"  [WARN] Error revisando usuarios: {e}")

    # 2. Limpiar grupos IAM manuales
    res = run_aws_cmd(["iam", "list-groups", "--output", "json"], profile)
    if res.returncode == 0:
        try:
            groups = json.loads(res.stdout).get("Groups", [])
            for g in groups:
                gname = g.get("GroupName", "")
                if "unam" in gname.lower() or "estudiantes" in gname.lower():
                    print(f"  [-] Eliminando grupo IAM manual: {BOLD}{gname}{RESET}")
                    pol_res = run_aws_cmd(["iam", "list-attached-group-policies", "--group-name", gname, "--output", "json"], profile)
                    if pol_res.returncode == 0:
                        for p in json.loads(pol_res.stdout).get("AttachedPolicies", []):
                            run_aws_cmd(["iam", "detach-group-policy", "--group-name", gname, "--policy-arn", p["PolicyArn"]], profile)
                    in_res = run_aws_cmd(["iam", "list-group-policies", "--group-name", gname, "--output", "json"], profile)
                    if in_res.returncode == 0:
                        for pol_name in json.loads(in_res.stdout).get("PolicyNames", []):
                            run_aws_cmd(["iam", "delete-group-policy", "--group-name", gname, "--policy-name", pol_name], profile)
                    run_aws_cmd(["iam", "delete-group", "--group-name", gname], profile)
        except Exception as e:
            print(f"  [WARN] Error revisando grupos: {e}")

    # 3. Limpiar roles e instance profiles manuales
    res = run_aws_cmd(["iam", "list-roles", "--output", "json"], profile)
    if res.returncode == 0:
        try:
            roles = json.loads(res.stdout).get("Roles", [])
            for r in roles:
                rname = r.get("RoleName", "")
                if rname.startswith("Rol-EC2-") or "lectors3" in rname.lower():
                    print(f"  [-] Eliminando rol IAM manual: {BOLD}{rname}{RESET}")
                    ip_res = run_aws_cmd(["iam", "list-instance-profiles-for-role", "--role-name", rname, "--output", "json"], profile)
                    if ip_res.returncode == 0:
                        for ip in json.loads(ip_res.stdout).get("InstanceProfiles", []):
                            ipname = ip.get("InstanceProfileName", "")
                            run_aws_cmd(["iam", "remove-role-from-instance-profile", "--instance-profile-name", ipname, "--role-name", rname], profile)
                            run_aws_cmd(["iam", "delete-instance-profile", "--instance-profile-name", ipname], profile)
                    pol_res = run_aws_cmd(["iam", "list-attached-role-policies", "--role-name", rname, "--output", "json"], profile)
                    if pol_res.returncode == 0:
                        for p in json.loads(pol_res.stdout).get("AttachedPolicies", []):
                            run_aws_cmd(["iam", "detach-role-policy", "--role-name", rname, "--policy-arn", p["PolicyArn"]], profile)
                    in_res = run_aws_cmd(["iam", "list-role-policies", "--role-name", rname, "--output", "json"], profile)
                    if in_res.returncode == 0:
                        for pol_name in json.loads(in_res.stdout).get("PolicyNames", []):
                            run_aws_cmd(["iam", "delete-role-policy", "--role-name", rname, "--policy-name", pol_name], profile)
                    run_aws_cmd(["iam", "delete-role", "--role-name", rname], profile)
        except Exception as e:
            print(f"  [WARN] Error revisando roles: {e}")

    # 4. Limpiar buckets S3 manuales creados para la sesion
    res = run_aws_cmd(["s3api", "list-buckets", "--output", "json"], profile)
    if res.returncode == 0:
        try:
            buckets = json.loads(res.stdout).get("Buckets", [])
            for b in buckets:
                bname = b.get("Name", "")
                lower = bname.lower()
                if "cdk-hnb659fds" in lower or "cdktoolkit" in lower:
                    continue
                if (lower.startswith("seguridad-") or lower.startswith("demo-") or 
                    "unam" in lower or "cloudsec" in lower or "privado" in lower or "publico" in lower):
                    empty_and_delete_bucket(bname, profile)
        except Exception as e:
            print(f"  [WARN] Error revisando buckets: {e}")


def full_destroy(profile):
    print(f"\n{RED}{BOLD}[!] INICIANDO DESTRUCCION Y BARRIDO TOTAL DE RECURSOS...{RESET}")
    cmd = ["npx", "cdk", "destroy", "--force"]
    if profile: cmd.extend(["--profile", profile])
    subprocess.run(cmd, cwd=CDK_DIR)

    cleanup_manual_lab_resources(profile)

    if os.path.exists(CONFIG_PATH):
        os.remove(CONFIG_PATH)
    outputs_path = os.path.join(CDK_DIR, "outputs.json")
    if os.path.exists(outputs_path):
        os.remove(outputs_path)

    print(f"\n{GREEN}{BOLD}════════════════════════════════════════════════════════════════════{RESET}")
    print(f"{GREEN}{BOLD}[OK] CUENTA 100% LIMPIA: CERO RECURSOS HUERFANOS Y $0 COSTO RESIDUAL.{RESET}")
    print(f"{GREEN}{BOLD}════════════════════════════════════════════════════════════════════{RESET}\n")


def interactive_menu(profile, account_id, region):
    state = {
        "sg_active": True,
        "iam_active": True
    }

    while True:
        demo_url = ""
        demo_ip = ""
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r") as f:
                    cfg = json.load(f)
                demo_url = cfg.get("demoUrl", "")
                demo_ip = cfg.get("demoIp", "")
            except Exception:
                pass

        if state["sg_active"]:
            sg_hud = f"{GREEN}[██████████] 100% ONLINE (Port 80 OK){RESET}"
        else:
            sg_hud = f"{RED}{BLINK}[░░░░░░░░░░]   0% BLACKOUT (Port 80 DROP) [!] {RESET}"

        if state["iam_active"]:
            iam_hud = f"{GREEN}[██████████] 100% ALLOWED (s3:PutObject 200){RESET}"
        else:
            iam_hud = f"{YELLOW}{BLINK}[░░░░░░░░░░]   0% REVOKED (HTTP 403 Lock) [-] {RESET}"

        endpoint_str = f"{CYAN}{demo_url}{RESET}" if demo_url else f"{DIM}No desplegado aun (Ejecuta [1]){RESET}"

        print(f"\n{PURPLE}{BOLD}╔══════════════════════════════════════════════════════════════════════════════════╗{RESET}")
        print(f"{PURPLE}{BOLD}║                 :: A W S   S E C O P S   A R C A D E ::                          ║{RESET}")
        print(f"{PURPLE}{BOLD}║              [CREDITS: ∞]  ·  HIGH SCORE: 99990  ·  PLAYER 1: ARMED              ║{RESET}")
        print(f"{PURPLE}{BOLD}╠══════════════════════════════════════════════════════════════════════════════════╣{RESET}")
        print(arcade_box_line(f"REALM     : {YELLOW}{BOLD}{account_id[:12]:<16}{RESET} ZONE : {CYAN}{BOLD}{region:<14}{RESET} ENGINE : {GREEN}CDK v2{RESET}"))
        print(arcade_box_line(f"FIREWALL  : {sg_hud}"))
        print(arcade_box_line(f"IAM POLICY: {iam_hud}"))
        print(arcade_box_line(f"LIVE NODE : {endpoint_str}"))
        print(f"{PURPLE}{BOLD}╠══════════════════════════════════════════════════════════════════════════════════╣{RESET}")
        print(arcade_box_line(f"{PINK}{BOLD}─── [STAGE 1: DESPLIEGUE & ACCESO] ──────────────────────────────────────────────{RESET}"))
        print(arcade_box_line(f" {CYAN}{BOLD}[1]{RESET} {WHITE}{BOLD}DESPLEGAR INFRAESTRUCTURA{RESET}    {DIM}:: Lanzar EC2 + S3 + IAM Role con CDK      {RESET}"))
        print(arcade_box_line(f" {CYAN}{BOLD}[2]{RESET} {WHITE}{BOLD}PROYECTAR CODIGO QR      {RESET}    {DIM}:: Mostrar QR gigante para celulares en vivo{RESET}"))
        print(arcade_box_line(""))
        print(arcade_box_line(f"{PINK}{BOLD}─── [STAGE 2: ATAQUE & DEFENSA EN VIVO // LIVE BATTLE] ───────────────────────────{RESET}"))
        print(arcade_box_line(f" {CYAN}{BOLD}[3]{RESET} {RED}{BOLD}CORTAR TRAFICO WEB (EMP)     {RESET}{DIM}:: Firewall SG Port 80 DROP (Capa 4 Red)   {RESET}"))
        print(arcade_box_line(f" {CYAN}{BOLD}[4]{RESET} {GREEN}{BOLD}RESTAURAR TRAFICO WEB        {RESET}{DIM}:: Firewall SG Port 80 ALLOW (Shield Online){RESET}"))
        print(arcade_box_line(f" {CYAN}{BOLD}[5]{RESET} {YELLOW}{BOLD}BLOQUEAR SUBIDAS S3 (LOCK)   {RESET}{DIM}:: Revocar s3:PutObject (IAM 403 Block)    {RESET}"))
        print(arcade_box_line(f" {CYAN}{BOLD}[6]{RESET} {GREEN}{BOLD}PERMITIR SUBIDAS S3 (ALLOW)  {RESET}{DIM}:: Conceder s3:PutObject (IAM 200 OK)      {RESET}"))
        print(arcade_box_line(""))
        print(arcade_box_line(f"{PINK}{BOLD}─── [STAGE 3: AUDITORIA & TELEMETRIA] ───────────────────────────────────────────{RESET}"))
        print(arcade_box_line(f" {CYAN}{BOLD}[7]{RESET} {CYAN}{BOLD}RADAR CLOUDTRAIL (API)       {RESET}{DIM}:: Ver eventos de corte/firewall en tiempo real{RESET}"))
        print(arcade_box_line(""))
        print(arcade_box_line(f"{PINK}{BOLD}─── [STAGE 4: LIMPIEZA & CIERRE] ──────────────────────────────────────────────────{RESET}"))
        print(arcade_box_line(f" {CYAN}{BOLD}[8]{RESET} {RED}{BOLD}PURGA TOTAL (NUKE CERO $)    {RESET}{DIM}:: Barrido total y $0 costo residual        {RESET}"))
        print(arcade_box_line(f" {CYAN}{BOLD}[0]{RESET} {WHITE}{BOLD}SALIR DEL SISTEMA            {RESET}{DIM}:: Volver al sistema operativo              {RESET}"))
        print(f"{PURPLE}{BOLD}╚══════════════════════════════════════════════════════════════════════════════════╝{RESET}")

        opt = input(f"\n{YELLOW}{BOLD}>> [PLAYER 1] INGRESA COMANDO >> {RESET}").strip()

        if opt == "1":
            deploy_stack(profile)
        elif opt == "2":
            try:
                print("\a", end="", flush=True)
            except Exception:
                pass
            if os.path.exists(CONFIG_PATH):
                with open(CONFIG_PATH, "r") as f:
                    cfg = json.load(f)
                url = cfg.get("demoUrl", "")
                print(f"\n{PINK}{BOLD}[ HOLO-PROJECTOR MATRIX ONLINE ]{RESET}")
                print(f"  :: {WHITE}{BOLD}MISSION URL:{RESET} {CYAN}{BOLD}{url}{RESET}")
                print(f"  :: {DIM}Apunta con la camara de tu celular al codigo QR:{RESET}\n")
                print_ascii_qr(url)
            else:
                print(f"{YELLOW}[WARN] Aun no has desplegado la infraestructura. Elige la opcion [1] primero.{RESET}")
            input(f"\nPresiona {BOLD}[Enter]{RESET} para volver al menu...")
        elif opt == "3":
            try:
                print("\a", end="", flush=True)
            except Exception:
                pass
            print(f"\n{RED}{BOLD}[!] ─── [EMP BLAST TRIGGERED] ──────────────────────────────────────────{RESET}")
            print(f"{RED}[*] Desconectando reglas de Ingress en Security Group...{RESET}")
            cmd = ["npx", "cdk", "deploy", "-c", "enableHttp=false", "--require-approval", "never"]
            if profile: cmd.extend(["--profile", profile])
            subprocess.run(cmd, cwd=CDK_DIR)
            state["sg_active"] = False
            print(f"{RED}{BOLD}[!] FIREWALL ENGAGED: Puerto 80 bloqueado (Capa 4 Red). Audiencia desconectada.{RESET}")
            input(f"\nPresiona {BOLD}[Enter]{RESET} para volver al menu...")
        elif opt == "4":
            try:
                print("\a", end="", flush=True)
            except Exception:
                pass
            print(f"\n{GREEN}{BOLD}[+] ─── [SHIELD OVERDRIVE ENGAGED] ─────────────────────────────────────{RESET}")
            print(f"{GREEN}[*] Reinyectando regla TCP 80: Ingress autorizada desde 0.0.0.0/0...{RESET}")
            cmd = ["npx", "cdk", "deploy", "-c", "enableHttp=true", "--require-approval", "never"]
            if profile: cmd.extend(["--profile", profile])
            subprocess.run(cmd, cwd=CDK_DIR)
            state["sg_active"] = True
            print(f"{GREEN}{BOLD}[OK] SHIELD ONLINE: Trafico web restablecido al 100%. Audiencia conectada.{RESET}")
            input(f"\nPresiona {BOLD}[Enter]{RESET} para volver al menu...")
        elif opt == "5":
            try:
                print("\a", end="", flush=True)
            except Exception:
                pass
            print(f"\n{YELLOW}{BOLD}[-] ─── [CYBER LOCKDOWN INITIATED] ─────────────────────────────────────{RESET}")
            print(f"{YELLOW}[*] Revocando permiso \x27s3:PutObject\x27 del IAM Instance Profile...{RESET}")
            cmd = ["npx", "cdk", "deploy", "-c", "enableUpload=false", "--require-approval", "never"]
            if profile: cmd.extend(["--profile", profile])
            subprocess.run(cmd, cwd=CDK_DIR)
            state["iam_active"] = False
            print(f"{RED}{BOLD}[LOCKED] PERMISO REVOCADO: Subidas denegadas con HTTP 403 Forbidden.{RESET}")
            print(f"{DIM}[INFO] Principio de Menor Privilegio demostrado en vivo a nivel IAM.{RESET}")
            input(f"\nPresiona {BOLD}[Enter]{RESET} para volver al menu...")
        elif opt == "6":
            try:
                print("\a", end="", flush=True)
            except Exception:
                pass
            print(f"\n{GREEN}{BOLD}[+] ─── [SYSTEM OVERRIDE ENGAGED] ──────────────────────────────────────{RESET}")
            print(f"{GREEN}[*] Restableciendo permiso \x27s3:PutObject\x27 en el IAM Role...{RESET}")
            cmd = ["npx", "cdk", "deploy", "-c", "enableUpload=true", "--require-approval", "never"]
            if profile: cmd.extend(["--profile", profile])
            subprocess.run(cmd, cwd=CDK_DIR)
            state["iam_active"] = True
            print(f"{GREEN}{BOLD}[OK] PERMISO AUTORIZADO: Fotos subiendo con HTTP 200 OK hacia Amazon S3.{RESET}")
            input(f"\nPresiona {BOLD}[Enter]{RESET} para volver al menu...")
        elif opt == "7":
            print(f"\n{CYAN}{BOLD}[*] [RADAR RECON] SCANNING CLOUDTRAIL TELEMETRY...{RESET}")
            trail_script = os.path.join(BASE_DIR, "scripts", "ver_auditoria_cloudtrail.sh")
            subprocess.run(["bash", trail_script])
            input(f"\nPresiona {BOLD}[Enter]{RESET} para volver al menu...")
        elif opt == "8":
            confirm = input(f"\n{RED}{BOLD}[!] ¿Confirmar destruccion total de recursos en AWS? [s/N]: {RESET}").strip().lower()
            if confirm in ["s", "si", "y", "yes"]:
                full_destroy(profile)
            input(f"\nPresiona {BOLD}[Enter]{RESET} para volver al menu...")
        elif opt == "0":
            print(f"\n{GREEN}{BOLD}[ SESION FINALIZADA ] ¡Exito en tu taller y practica técnica!{RESET}\n")
            break


def main():
    banner()
    check_prerequisites()
    profile, account_id, region = select_aws_profile()
    check_cdk_bootstrap(profile, region, account_id)
    
    if len(sys.argv) > 1 and sys.argv[1] == "--deploy":
        deploy_stack(profile)
    elif len(sys.argv) > 1 and sys.argv[1] == "--destroy":
        full_destroy(profile)
    else:
        interactive_menu(profile, account_id, region)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}[ABORT] Operacion cancelada por el usuario.{RESET}")
        sys.exit(0)
