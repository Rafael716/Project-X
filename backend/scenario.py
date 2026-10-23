"""Escenarios (los "niveles" del juego).

Cada escenario es una fábrica que devuelve dicts frescos. `pos` (x, y en 0..1)
es solo para dibujar el mapa en la web. ESCENARIOS es un registro cerrado:
agregar un nivel = escribir una fábrica y registrarla (carga tardía sin reflexión).
"""

import copy


def _nodo(**p):
    base = {
        'servicios': [], 'vulnerabilidades': [], 'archivosSensibles': [], 'valor': 1,
        'estado': 'limpio', 'fase': None, 'compromisoReal': False, 'persistente': False,
        'posturaDefensiva': 0.0, 'score': 0.0, 'senales': {}, 'aisladoHasta': None,
    }
    base.update(p)
    return base


def _vuln(id, nombre, cve, dificultad, tactica, descripcion):
    return {'id': id, 'nombre': nombre, 'cve': cve, 'dificultad': dificultad, 'tactica': tactica, 'descripcion': descripcion}


def pymes01():
    nodos = [
        _nodo(id='router', nombre='Router Perimetral', tipo='router', servicios=['http', 'dns', 'snmp'], valor=2, pos=(0.5, 0.12),
              archivosSensibles=['.env.gateway', 'router_config.bak', 'snmp_community.secret'],
              vulnerabilidades=[
                  _vuln('cfg-debil', 'Credenciales default SNMP', 'CVE-2022-29303', 0.55, 'Discovery', 'Comunidad SNMP pública expuesta para lectura de rutas.'),
              ]),
        _nodo(id='ws1', nombre='PC Recepción', tipo='workstation', servicios=['http', 'smb', 'rdp'], valor=1, pos=(0.14, 0.42),
              archivosSensibles=['.env.local', 'memorando_2026.docx', 'passwords_backup.txt', 'id_rsa_ws1'],
              vulnerabilidades=[
                  _vuln('phish', 'Spearphishing Macro Doc', 'CVE-2023-38831', 0.3, 'Initial Access', 'Fuga de token de sesión en documento infectado.'),
                  _vuln('local-priv', 'Token Impersonation', 'CVE-2022-26923', 0.45, 'Priv Esc', 'Elevación de usuario local a SYSTEM manipulando tokens.'),
              ]),
        _nodo(id='ws2', nombre='PC Contabilidad', tipo='workstation', servicios=['smb', 'winrm'], valor=2, pos=(0.18, 0.82),
              archivosSensibles=['estados_financieros_2026.xlsx', 'planillas.pdf', 'api_banco_prod.env', 'cert_afip.pfx'],
              vulnerabilidades=[
                  _vuln('smb-old', 'EternalBlue SMBv1', 'CVE-2017-0144', 0.4, 'Lateral Movement', 'Desbordamiento en srv.sys para RCE.'),
              ]),
        _nodo(id='web', nombre='Servidor Web Producción', tipo='server', servicios=['http', 'ssh', 'nginx'], valor=3, pos=(0.62, 0.55),
              archivosSensibles=['.env.production', 'nginx.conf', 'database_credentials.json', 'jwt_private.key', 'api_keys.vault'],
              vulnerabilidades=[
                  _vuln('svc-exploit', 'Log4Shell RCE', 'CVE-2021-44228', 0.6, 'Initial Access', 'Inyección JNDI en cabeceras HTTP que entrega reverse shell.'),
                  _vuln('ssh-weak', 'Clave SSH débil', 'CWE-308', 0.45, 'Credential Access', 'Clave SSH reutilizada: escalada sin contraseña.'),
              ]),
        _nodo(id='db', nombre='Servidor Base de Datos SQL', tipo='database', servicios=['sql', 'ssh'], valor=6, pos=(0.88, 0.8),
              archivosSensibles=['clientes_tarjetas.sql', 'password_hashes.dump', 'backup_db_completo.tar.gz', 'master_secrets.env'],
              vulnerabilidades=[
                  _vuln('sql-escalate', 'PostgreSQL UDF PrivEsc', 'CVE-2023-39325', 0.55, 'Priv Esc', 'Función de usuario maliciosa para ejecutar comandos como root de BD.'),
              ]),
    ]
    aristas = [
        {'from': 'router', 'to': 'ws1', 'tipo': 'red'},
        {'from': 'router', 'to': 'web', 'tipo': 'red'},
        {'from': 'ws1', 'to': 'ws2', 'tipo': 'red'},
        {'from': 'ws1', 'to': 'web', 'tipo': 'red'},
        {'from': 'web', 'to': 'db', 'tipo': 'red'},
        {'from': 'ws2', 'to': 'db', 'tipo': 'red'},
    ]
    return {
        'id': 'pymes01', 'nombre': 'PYMES-01',
        'descripcion': 'Red corporativa pequeña: router, 2 PCs, servidor web y base de datos. El atacante entra por Recepción y busca exfiltrar la base de datos.',
        'dificultad': 'Normal', 'tickMax': 240, 'metaExfiltracion': 6,
        'nodos': nodos, 'aristas': aristas, 'entrada': 'ws1', 'objetivo': 'db',
    }


def datacenter02():
    """Nivel 2: más grande y endurecido (vulnerabilidades más difíciles, meta mayor)."""
    nodos = [
        _nodo(id='edge', nombre='Firewall / Edge', tipo='router', servicios=['https', 'vpn'], valor=2, pos=(0.5, 0.1),
              archivosSensibles=['vpn_config.ovpn', '.env.edge'],
              vulnerabilidades=[_vuln('vpn-cve', 'VPN Pre-Auth RCE', 'CVE-2024-3400', 0.65, 'Initial Access', 'Ejecución remota pre-autenticación en el gateway VPN.')]),
        _nodo(id='dmz', nombre='Servidor DMZ (API)', tipo='server', servicios=['https', 'api'], valor=2, pos=(0.22, 0.4),
              archivosSensibles=['.env.api', 'swagger.json', 'tokens_oauth.vault'],
              vulnerabilidades=[_vuln('ssrf', 'SSRF a metadata interna', 'CVE-2023-0001', 0.55, 'Discovery', 'Falsificación de petición del lado servidor hacia servicios internos.')]),
        _nodo(id='app', nombre='App Server (Microservicios)', tipo='server', servicios=['http', 'grpc'], valor=3, pos=(0.5, 0.5),
              archivosSensibles=['.env.cluster', 'kubeconfig', 'service_account.json'],
              vulnerabilidades=[_vuln('deserial', 'Deserialización insegura', 'CVE-2023-34040', 0.6, 'Initial Access', 'Objeto malicioso ejecuta código al deserializarse.')]),
        _nodo(id='ad', nombre='Controlador de Dominio', tipo='server', servicios=['ldap', 'kerberos', 'smb'], valor=4, pos=(0.78, 0.4),
              archivosSensibles=['ntds.dit', 'krbtgt.keytab', 'gpo_backup.xml'],
              vulnerabilidades=[_vuln('zerologon', 'Zerologon', 'CVE-2020-1472', 0.5, 'Priv Esc', 'Reset del password de la cuenta de máquina del DC.')]),
        _nodo(id='vault', nombre='Vault de Secretos', tipo='database', servicios=['https', 'kv'], valor=5, pos=(0.5, 0.82),
              archivosSensibles=['root_token.vault', 'pki_ca.key', 'db_dynamic_creds.json'],
              vulnerabilidades=[_vuln('vault-cve', 'Fuga de policy ACL', 'CVE-2023-25000', 0.7, 'Credential Access', 'Escalada de política por ruta mal normalizada.')]),
        _nodo(id='db', nombre='Data Lake (PII)', tipo='database', servicios=['sql', 'ssh'], valor=8, pos=(0.85, 0.82),
              archivosSensibles=['clientes_pii.sql', 'tarjetas_pan.dump', 'backup_full.tar.gz', 'master.env'],
              vulnerabilidades=[_vuln('sqli-core', 'SQLi en reporting', 'CVE-2023-39999', 0.6, 'Collection', 'Inyección en el motor de reportes con acceso a todo el esquema.')]),
    ]
    aristas = [
        {'from': 'edge', 'to': 'dmz', 'tipo': 'red'},
        {'from': 'dmz', 'to': 'app', 'tipo': 'red'},
        {'from': 'app', 'to': 'ad', 'tipo': 'red'},
        {'from': 'app', 'to': 'vault', 'tipo': 'red'},
        {'from': 'ad', 'to': 'db', 'tipo': 'red'},
        {'from': 'vault', 'to': 'db', 'tipo': 'red'},
    ]
    return {
        'id': 'datacenter02', 'nombre': 'DATACENTER-02',
        'descripcion': 'Datacenter endurecido: VPN, DMZ, microservicios, Active Directory y un vault de secretos protegen un data lake con PII. Nivel difícil.',
        'dificultad': 'Difícil', 'tickMax': 300, 'metaExfiltracion': 10,
        'nodos': nodos, 'aristas': aristas, 'entrada': 'dmz', 'objetivo': 'db',
    }


ESCENARIOS = {'pymes01': pymes01, 'datacenter02': datacenter02}


def cargar_escenario(escenario_id: str):
    factory = ESCENARIOS.get(escenario_id, pymes01)
    return copy.deepcopy(factory())


def catalogo():
    """Metadatos de niveles para el lobby (sin copiar toda la topología)."""
    out = []
    for f in ESCENARIOS.values():
        e = f()
        out.append({'id': e['id'], 'nombre': e['nombre'], 'descripcion': e['descripcion'],
                    'dificultad': e['dificultad'], 'nodos': len(e['nodos']), 'metaExfiltracion': e['metaExfiltracion']})
    return out
