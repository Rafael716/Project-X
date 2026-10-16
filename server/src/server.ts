import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { WebSocketServer, WebSocket } from 'ws';
import type { ClientMsg, ServerMsg, Role } from '../../shared/protocol';
import { TECNICAS } from './techniques';
import { RESPUESTAS } from './response';
import { Match } from './match';

const PORT = Number(process.env.PORT ?? 8787);
const __dirname = path.dirname(fileURLToPath(import.meta.url));
const WEB_DIST = path.resolve(__dirname, '../../web/dist'); // build de producción (opcional)

const partidas = new Map<string, Match>();
const socketCliente = new WeakMap<WebSocket, string>(); // socket -> clientId
const clienteSocket = new Map<string, WebSocket>();      // clientId -> socket
const clientePartida = new Map<string, string>();        // clientId -> codigo

function nuevoCodigo(): string {
  const abc = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  let c = '';
  do { c = Array.from({ length: 6 }, () => abc[Math.floor(Math.random() * abc.length)]).join(''); }
  while (partidas.has(c));
  return c;
}
const nuevoClientId = () => Math.random().toString(36).slice(2, 10);

// Difunde el estado de una partida a todos sus clientes conectados.
function broadcast(codigo: string): void {
  const m = partidas.get(codigo);
  if (!m) return;
  const msg: ServerMsg = { t: 'estado', estado: m.snapshot() };
  const data = JSON.stringify(msg);
  for (const [cid, cod] of clientePartida) {
    if (cod !== codigo) continue;
    const sock = clienteSocket.get(cid);
    if (sock && sock.readyState === WebSocket.OPEN) sock.send(data);
  }
}

function enviar(sock: WebSocket, msg: ServerMsg): void {
  if (sock.readyState === WebSocket.OPEN) sock.send(JSON.stringify(msg));
}
const error = (sock: WebSocket, mensaje: string) => enviar(sock, { t: 'error', mensaje });

// ---------------- servidor HTTP (sirve el build de la web si existe) ----------------
const MIME: Record<string, string> = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.json': 'application/json', '.ico': 'image/x-icon' };
const http_server = http.createServer((req, res) => {
  if (!fs.existsSync(WEB_DIST)) { res.writeHead(200, { 'content-type': 'text/plain' }); res.end('Project X server OK. Build web no encontrado (modo dev: usa Vite en :5174).'); return; }
  let rel = decodeURIComponent((req.url ?? '/').split('?')[0]);
  if (rel === '/') rel = '/index.html';
  let file = path.join(WEB_DIST, rel);
  if (!file.startsWith(WEB_DIST) || !fs.existsSync(file)) file = path.join(WEB_DIST, 'index.html'); // SPA fallback
  res.writeHead(200, { 'content-type': MIME[path.extname(file)] ?? 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
});

// ---------------- WebSocket gateway (ADR-0003) ----------------
const wss = new WebSocketServer({ server: http_server });

wss.on('connection', (sock) => {
  const clientId = nuevoClientId();
  socketCliente.set(sock, clientId);
  clienteSocket.set(clientId, sock);

  sock.on('message', (raw) => {
    let msg: ClientMsg;
    try { msg = JSON.parse(raw.toString()); } catch { return error(sock, 'JSON inválido'); }
    manejar(sock, clientId, msg);
  });

  sock.on('close', () => {
    const cod = clientePartida.get(clientId);
    if (cod) { partidas.get(cod)?.desconectar(clientId); broadcast(cod); }
    clienteSocket.delete(clientId);
  });
});

function bienvenida(sock: WebSocket, clientId: string, codigo: string, role: Role): void {
  enviar(sock, { t: 'bienvenida', clientId, codigo, role, tecnicas: TECNICAS, respuestas: RESPUESTAS });
  broadcast(codigo);
}

function manejar(sock: WebSocket, clientId: string, msg: ClientMsg): void {
  switch (msg.t) {
    case 'crear': {
      const codigo = nuevoCodigo();
      const m = new Match(codigo, msg.escenarioId, msg.semilla ?? (Math.random() * 1e9) | 0, () => broadcast(codigo));
      partidas.set(codigo, m);
      m.unir(clientId, msg.nombre, msg.role);
      clientePartida.set(clientId, codigo);
      return bienvenida(sock, clientId, codigo, msg.role);
    }
    case 'unir': {
      const m = partidas.get(msg.codigo);
      if (!m) return error(sock, 'Código inexistente');
      const motivo = m.unir(clientId, msg.nombre, msg.role);
      if (motivo) return error(sock, motivo);
      clientePartida.set(clientId, msg.codigo);
      return bienvenida(sock, clientId, msg.codigo, msg.role);
    }
    case 'reconectar': {
      const m = partidas.get(msg.codigo);
      if (!m) return error(sock, 'Código inexistente');
      // el clientId pudo cambiar; reasignamos el socket al clientId previo
      const prev = msg.clientId;
      clienteSocket.set(prev, sock);
      socketCliente.set(sock, prev);
      const role = m.reconectar(prev);
      if (!role) return error(sock, 'No estabas en esta partida');
      clientePartida.set(prev, msg.codigo);
      return bienvenida(sock, prev, msg.codigo, role);
    }
    default: {
      // acciones que requieren partida y rol
      const codigo = clientePartida.get(clientId);
      const m = codigo ? partidas.get(codigo) : undefined;
      if (!m || !codigo) return error(sock, 'No estás en una partida');
      const role = m.roleDe(clientId);
      if (!role) return error(sock, 'Sin rol asignado');
      despachar(sock, m, codigo, role, msg);
    }
  }
}

function despachar(sock: WebSocket, m: Match, codigo: string, role: Role, msg: ClientMsg): void {
  switch (msg.t) {
    case 'elegir_modo': m.elegirModo(role, msg.modo); break;
    case 'listo': m.listo(role, msg.valor); break;
    case 'iniciar': { const e = m.iniciar(); if (e) return error(sock, e); break; }
    case 'pausar': m.pausar(msg.valor); break;
    case 'atacar': {
      if (role !== 'attacker') return error(sock, 'Solo el atacante puede atacar');
      const e = m.encolarAtaque({ tecnicaId: msg.tecnicaId, nodoId: msg.nodoId });
      if (e) return error(sock, e);
      break;
    }
    case 'responder': {
      if (role !== 'defender') return error(sock, 'Solo el defensor puede responder');
      const e = m.encolarRespuesta({ respuesta: msg.respuesta, nodoId: msg.nodoId });
      if (e) return error(sock, e);
      break;
    }
  }
  broadcast(codigo);
}

http_server.listen(PORT, '0.0.0.0', () => {
  console.log(`Project X server escuchando en http://0.0.0.0:${PORT}`);
  console.log(`Desde otra PC en la LAN: http://<IP-DE-ESTA-PC>:${PORT}`);
});
