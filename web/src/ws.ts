import { useEffect, useRef, useState, useCallback } from 'react';
import type { ClientMsg, ServerMsg, GameState, Role, TechniqueMeta, ResponseMeta } from '../../shared/protocol';

// URL del servidor WebSocket.
// - Dev de Vite (:5174): el WS vive en el Node :8787.
// - Cualquier otro caso (server propio en :8787, o detrás de un proxy/ngrok/Cloudflare
//   sin puerto en 80/443): mismo origen. location.host ya incluye el puerto si lo hay.
function wsUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  if (['5173', '5174', '3000'].includes(location.port)) {
    return `${proto}://${location.hostname}:8787/ws`;
  }
  return `${proto}://${location.host}/ws`;
}

export interface Game {
  conectado: boolean;
  clientId: string | null;
  codigo: string | null;
  role: Role | null;
  estado: GameState | null;
  tecnicas: TechniqueMeta[];
  respuestas: ResponseMeta[];
  error: string | null;
  send: (m: ClientMsg) => void;
}

export function useGame(): Game {
  const ws = useRef<WebSocket | null>(null);
  const [conectado, setConectado] = useState(false);
  const [clientId, setClientId] = useState<string | null>(null);
  const [codigo, setCodigo] = useState<string | null>(null);
  const [role, setRole] = useState<Role | null>(null);
  const [estado, setEstado] = useState<GameState | null>(null);
  const [tecnicas, setTecnicas] = useState<TechniqueMeta[]>([]);
  const [respuestas, setRespuestas] = useState<ResponseMeta[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const sock = new WebSocket(wsUrl());
    ws.current = sock;
    sock.onopen = () => {
      setConectado(true);
      // reconexión automática si teníamos sesión previa (RNF-07)
      const prev = sessionStorage.getItem('px');
      if (prev) { const { codigo, clientId } = JSON.parse(prev); sock.send(JSON.stringify({ t: 'reconectar', codigo, clientId } satisfies ClientMsg)); }
    };
    sock.onclose = () => setConectado(false);
    sock.onmessage = (e) => {
      const msg: ServerMsg = JSON.parse(e.data);
      if (msg.t === 'bienvenida') {
        setClientId(msg.clientId); setCodigo(msg.codigo); setRole(msg.role);
        setTecnicas(msg.tecnicas); setRespuestas(msg.respuestas); setError(null);
        sessionStorage.setItem('px', JSON.stringify({ codigo: msg.codigo, clientId: msg.clientId }));
      } else if (msg.t === 'estado') {
        setEstado(msg.estado);
      } else if (msg.t === 'error') {
        setError(msg.mensaje);
        setTimeout(() => setError(null), 4000);
      }
    };
    return () => sock.close();
  }, []);

  const send = useCallback((m: ClientMsg) => {
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(m));
  }, []);

  return { conectado, clientId, codigo, role, estado, tecnicas, respuestas, error, send };
}
