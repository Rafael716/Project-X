import type { SimNode, Edge } from '../../shared/protocol';

export interface Scenario {
  id: string;
  nombre: string;
  descripcion: string;
  tickMax: number;
  metaExfiltracion: number;
  nodos: SimNode[];
  aristas: Edge[];
  entrada: string; // nodo por el que el atacante empieza (expuesto)
  objetivo: string; // nodo cuyo valor quiere exfiltrar
}

function nodo(p: Partial<SimNode> & Pick<SimNode, 'id' | 'nombre' | 'tipo'>): SimNode {
  return {
    servicios: [], vulnerabilidades: [], archivosSensibles: [], valor: 1, estado: 'limpio', fase: null,
    compromisoReal: false, posturaDefensiva: 0, score: 0, senales: {},
    ...p,
  };
}

// Escenario base PYMES-01 (ver documentacion/06). Topología pequeña y legible.
export function pymes01(): Scenario {
  const nodos: SimNode[] = [
    nodo({
      id: 'router', nombre: 'Router Perimetral', tipo: 'router', servicios: ['http', 'dns', 'snmp'], valor: 2,
      archivosSensibles: ['.env.gateway', 'router_config.bak', 'snmp_community.secret'],
      vulnerabilidades: [
        { id: 'cfg-debil', nombre: 'Credenciales default SNMP', cve: 'CVE-2022-29303', dificultad: 0.55, tactica: 'Discovery', descripcion: 'Comunidad SNMP pública expuesta para lectura de rutas.' },
      ],
    }),
    nodo({
      id: 'ws1', nombre: 'PC Recepción', tipo: 'workstation', servicios: ['http', 'smb', 'rdp'], valor: 1,
      archivosSensibles: ['.env.local', 'memorando_personal_2026.docx', 'passwords_backup.txt', 'id_rsa_ws1'],
      vulnerabilidades: [
        { id: 'phish', nombre: 'Spearphishing Macro Doc', cve: 'CVE-2023-38831', dificultad: 0.3, tactica: 'Initial Access', descripcion: 'Fuga de token de sesión en documento infectado de Outlook.' },
        { id: 'local-priv', nombre: 'Token Impersonation SeDebugPrivilege', cve: 'CVE-2022-26923', dificultad: 0.45, tactica: 'Priv Esc', descripcion: 'Elevación de usuario local a SYSTEM mediante manipulación de tokens.' },
      ],
    }),
    nodo({
      id: 'ws2', nombre: 'PC Contabilidad', tipo: 'workstation', servicios: ['smb', 'winrm'], valor: 2,
      archivosSensibles: ['estados_financieros_2026.xlsx', 'planillas_remuneraciones.pdf', 'api_banco_prod.env', 'cert_afip.pfx'],
      vulnerabilidades: [
        { id: 'smb-old', nombre: 'EternalBlue SMBv1 Exploit', cve: 'CVE-2017-0144', dificultad: 0.4, tactica: 'Lateral Movement', descripcion: 'Desbordamiento de búfer en driver srv.sys para ejecución remota de código.' },
      ],
    }),
    nodo({
      id: 'web', nombre: 'Servidor Web Producción', tipo: 'server', servicios: ['http', 'ssh', 'nginx'], valor: 3,
      archivosSensibles: ['.env.production', 'nginx.conf', 'database_credentials.json', 'jwt_private.key', 'api_keys.vault'],
      vulnerabilidades: [
        { id: 'svc-exploit', nombre: 'Log4Shell / Spring4Shell RCE', cve: 'CVE-2021-44228', dificultad: 0.6, tactica: 'Initial Access', descripcion: 'Inyección JNDI en cabeceras HTTP que entrega reverse shell al atacante.' },
        { id: 'ssh-weak', nombre: 'Clave SSH débil en authorized_keys', cve: 'CWE-308', dificultad: 0.45, tactica: 'Credential Access', descripcion: 'Clave SSH reutilizada permitiendo escalada sin contraseña.' },
      ],
    }),
    nodo({
      id: 'db', nombre: 'Servidor Base de Datos SQL', tipo: 'database', servicios: ['sql', 'ssh'], valor: 6,
      archivosSensibles: ['clientes_tarjetas.sql', 'usuarios_password_hashes.dump', 'backup_db_completo.tar.gz', 'master_secrets.env'],
      vulnerabilidades: [
        { id: 'sql-escalate', nombre: 'PostgreSQL/MySQL UDF PrivEsc', cve: 'CVE-2023-39325', dificultad: 0.55, tactica: 'Priv Esc', descripcion: 'Carga de función de usuario maliciosa para ejecutar comandos como root de base de datos.' },
      ],
    }),
  ];
  const aristas: Edge[] = [
    { from: 'router', to: 'ws1', tipo: 'red' },
    { from: 'router', to: 'web', tipo: 'red' },
    { from: 'ws1', to: 'ws2', tipo: 'red' },
    { from: 'ws1', to: 'web', tipo: 'red' },
    { from: 'web', to: 'db', tipo: 'red' },
    { from: 'ws2', to: 'db', tipo: 'red' },
  ];
  return {
    id: 'pymes01', nombre: 'PYMES-01',
    descripcion: 'Red corporativa: Router perimetral, Estaciones de Trabajo (Recepción y Contabilidad), Servidor Web y Base de Datos central. El atacante busca descubrir vulnerabilidades (.env, credenciales, docs clasificados) y exfiltrar la base de datos principal.',
    tickMax: 240, metaExfiltracion: 6,
    nodos, aristas, entrada: 'ws1', objetivo: 'db',
  };
}

export const ESCENARIOS: Record<string, () => Scenario> = { pymes01 };
