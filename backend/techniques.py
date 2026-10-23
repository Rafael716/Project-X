"""Catálogo de técnicas del atacante (abstraído de MITRE ATT&CK).

Sesión 2 — polimorfismo y enlace dinámico: cada técnica es una CLASE que
hereda de `Tecnica` y sobreescribe `validar()` y/o `efecto()`. El motor llama
`tecnica.efecto(e, nodo)` sin saber cuál es: el runtime despacha al método
correcto según el tipo real del objeto (la "V-Table"). Para agregar una técnica
nueva se escribe una subclase y se registra; el motor NO se toca (abierto a
extensión, cerrado a modificación).

El registro TECNICA_POR_ID es un diccionario CERRADO: el id que manda el
cliente solo sirve como clave, nunca para importar código (sin reflexión).

Son PARÁMETROS de simulación, no comandos reales: `comandoEjemplo` y los textos
de salida son decorativos para la terminal del juego. Están escritos en lenguaje
sencillo a propósito (fácil de entender, sin jerga), sin perder la sensación de
estar frente a un sistema real.
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
            return 'Todavía no puedes llegar aquí: primero toma una PC vecina.'
        fx = fase_index(n['fase'])
        if fx < fase_index(self.faseRequiere):
            return 'Te falta un paso antes de poder hacer esto en esta PC.'
        if fx >= fase_index(self.faseProduce):
            return 'Ya hiciste esto en esta PC.'
        return None

    def efecto(self, e, n) -> str:
        """Aplica el éxito y devuelve la salida para la terminal del atacante."""
        n['fase'] = fase_max(n['fase'], self.faseProduce)
        return f"Listo: {self.nombre} funcionó en {n['nombre']}."


class _SinRequisitoDeFase(Tecnica):
    """Basta con que el nodo sea alcanzable (se puede repetir)."""

    def validar(self, e, n):
        if not e.alcanzable(n['id']):
            return 'Todavía no puedes llegar aquí: primero toma una PC vecina.'
        return None


class Portscan(Tecnica):
    id, nombre, tacticaMitre = 'portscan', 'Escanear la red', 'TA0007 Discovery'
    faseProduce, ruido, facilidadBase, costo, puntos = 'recon', 'alto', 0.9, 1, 5
    descripcion = 'Mira qué programas tiene una PC y descubre sus vecinas. Hace mucho ruido: es fácil que te descubran.'
    comandoEjemplo = 'escanear-red {target}'

    def efecto(self, e, n):
        super().efecto(e, n)
        return f"Revisé {n['nombre']}. Programas que encontré: {', '.join(n['servicios'])}. Ya aparecen sus PCs vecinas en el mapa."


class Enumeracion(Tecnica):
    id, nombre, tacticaMitre = 'enum', 'Buscar fallas', 'TA0007 Discovery'
    faseProduce, ruido, facilidadBase, costo, puntos = 'recon', 'medio', 0.8, 1, 5
    descripcion = 'Averigua qué versiones usa la PC para encontrarle fallas conocidas. Más silencioso que escanear toda la red.'
    comandoEjemplo = 'buscar-fallas {target}'

    def efecto(self, e, n):
        super().efecto(e, n)
        cves = ', '.join(v.get('cve') or v['id'] for v in n['vulnerabilidades']) or 'ninguna'
        return f"Encontré las fallas de {n['nombre']}: {cves}."


class ScanDocs(_SinRequisitoDeFase):
    id, nombre, tacticaMitre = 'scan_docs', 'Buscar archivos secretos', 'TA0009 Collection'
    faseProduce, ruido, facilidadBase, costo, puntos = 'recon', 'bajo', 0.85, 2, 5
    descripcion = 'Rebusca contraseñas, archivos de configuración, copias de seguridad y documentos confidenciales que quedaron expuestos.'
    comandoEjemplo = 'buscar-archivos {target}'

    def efecto(self, e, n):
        n['fase'] = n['fase'] or 'recon'
        sensibles = n.get('archivosSensibles') or []
        nuevos = 0
        for archivo in sensibles:
            tipo, secreto = 'doc', 'Documento interno confidencial de la organización.'
            if 'env' in archivo:
                tipo, secreto = 'env', f"Usuario y contraseña de la base de datos de {n['nombre']} (información muy sensible)."
            elif 'sql' in archivo or 'dump' in archivo or 'tar.gz' in archivo:
                tipo, secreto = 'db', f"Copia de la base de datos: {archivo} ({n['valor'] * 2.8:.1f} MB de registros confidenciales)."
            elif any(k in archivo for k in ('pass', 'rsa', 'vault', 'key')):
                tipo, secreto = 'cred', f'Contraseña o llave privada sacada de {archivo}.'
            nuevos += e.agregar_loot(n, archivo, tipo, secreto)
        lista = '\n'.join(f'    • {s}' for s in sensibles)
        return f"Encontré {nuevos} archivos secretos nuevos en {n['nombre']}:\n{lista}"


class Bruteforce(Tecnica):
    id, nombre, tacticaMitre = 'bruteforce', 'Adivinar la contraseña', 'TA0006 Credential Access'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'recon', 'acceso_inicial', 'medio', 0.55, 2, 20
    descripcion = 'Prueba miles de contraseñas comunes hasta que una entra. Deja rastro.'
    comandoEjemplo = 'adivinar-contraseña {target}'


class Exploit(Tecnica):
    id, nombre, tacticaMitre = 'exploit', 'Entrar por una falla', 'TA0001 Initial Access'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'recon', 'acceso_inicial', 'bajo', 0.45, 3, 25
    descripcion = 'Aprovecha una falla grave del programa para meterse. Es silencioso, pero no siempre funciona.'
    comandoEjemplo = 'entrar-por-falla {target}'

    def efecto(self, e, n):
        super().efecto(e, n)
        return f"¡Entré! Conseguí el control de {n['nombre']} aprovechando una falla."


class SqliDump(Tecnica):
    id, nombre, tacticaMitre = 'sqli_dump', 'Robar la base de datos', 'TA0001 Initial Access / TA0009 Collection'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'recon', 'acceso_inicial', 'medio', 0.6, 3, 25
    descripcion = 'Aprovecha una falla en la página web para sacar tablas, usuarios y contraseñas de la base de datos.'
    comandoEjemplo = 'robar-base-datos {target}'

    def validar(self, e, n):
        if 'sql' not in n['servicios'] and 'http' not in n['servicios']:
            return 'Esta PC no tiene una página web ni una base de datos para atacar.'
        return _SinRequisitoDeFase.validar(self, e, n)

    def efecto(self, e, n):
        n['fase'] = fase_max(n['fase'], 'acceso_inicial')
        e.agregar_loot(n, f"datos_{n['id']}.sql", 'db',
                       f"Tablas robadas: usuarios, roles y transacciones ({n['valor'] * 1.8:.1f} MB).")
        for archivo in n.get('archivosSensibles') or []:
            if 'sql' in archivo or 'dump' in archivo:
                e.agregar_loot(n, archivo, 'db', f'Tabla extraída de la base de datos: {archivo}.')
        return (f"¡Robé la base de datos de {n['nombre']}!\n"
                f"    • Tablas: usuarios, cuentas y sesiones\n"
                f"    • Guardado como: datos_{n['id']}.sql")


class Privesc(Tecnica):
    id, nombre, tacticaMitre = 'privesc', 'Volverse administrador', 'TA0004 Privilege Escalation'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'acceso_inicial', 'escalada', 'bajo', 0.5, 3, 30
    descripcion = 'Aprovecha un descuido para pasar de usuario normal a administrador (control total de la PC).'
    comandoEjemplo = 'subir-a-administrador {target}'

    def efecto(self, e, n):
        super().efecto(e, n)
        return f"Ahora soy administrador de {n['nombre']}: tengo control total."


class DumpLsass(Tecnica):
    id, nombre, tacticaMitre = 'dump_lsass', 'Robar contraseñas guardadas', 'TA0006 Credential Access'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'escalada', 'escalada', 'medio', 0.7, 3, 15
    descripcion = 'Saca las contraseñas y llaves que la PC tiene guardadas en memoria (hay que ser administrador).'
    comandoEjemplo = 'copiar-contraseñas {target}'

    def validar(self, e, n):
        if fase_index(n['fase']) < fase_index('escalada'):
            return 'Primero tienes que ser administrador de esta PC.'
        return None

    def efecto(self, e, n):
        e.agregar_loot(n, f"contrasenas_{n['id']}.txt", 'cred',
                       'Contraseñas de administrador copiadas de la memoria de la PC.')
        for archivo in n.get('archivosSensibles') or []:
            if any(k in archivo for k in ('pass', 'rsa', 'key')):
                e.agregar_loot(n, archivo, 'cred', f'Contraseña o llave guardada: {archivo}.')
        return f"Copié las contraseñas guardadas en {n['nombre']}."


class PersistBackdoor(Tecnica):
    id, nombre, tacticaMitre = 'persist_backdoor', 'Dejar una puerta trasera', 'TA0003 Persistence'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'acceso_inicial', 'escalada', 'bajo', 0.65, 2, 15
    descripcion = 'Deja una entrada oculta para volver cuando quieras. Aguanta aunque el defensor cierre el programa.'
    comandoEjemplo = 'dejar-puerta-trasera {target}'

    def validar(self, e, n):
        if fase_index(n['fase']) < fase_index('acceso_inicial'):
            return 'Primero tienes que entrar a esta PC.'
        if n.get('persistente'):
            return 'Ya dejaste una puerta trasera aquí.'
        return None

    def efecto(self, e, n):
        n['fase'] = fase_max(n['fase'], 'escalada')
        n['persistente'] = True
        return f"Dejé una puerta trasera oculta en {n['nombre']}: puedo volver aunque me cierren el programa."


class PhishingSpray(_SinRequisitoDeFase):
    id, nombre, tacticaMitre = 'phishing_spray', 'Probar contraseñas robadas', 'TA0008 Lateral Movement'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'recon', 'acceso_inicial', 'medio', 0.55, 2, 20
    descripcion = 'Usa contraseñas que ya robaste para entrar a otras PCs que usan la misma clave.'
    comandoEjemplo = 'probar-contraseñas {target}'

    def validar(self, e, n):
        if fase_index(n['fase']) >= fase_index('acceso_inicial'):
            return 'Esta PC ya es tuya.'
        return super().validar(e, n)

    def efecto(self, e, n):
        n['fase'] = fase_max(n['fase'], 'acceso_inicial')
        return f"Entré a {n['nombre']} reusando una contraseña robada."


class Pivot(Tecnica):
    id, nombre, tacticaMitre = 'pivot', 'Saltar a otra PC', 'TA0008 Lateral Movement'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'escalada', 'acceso_inicial', 'medio', 0.55, 3, 30
    descripcion = 'Desde una PC que ya controlas, saltas a una vecina y la tomas directamente.'
    comandoEjemplo = 'saltar-a-otra-pc {target}'

    def validar(self, e, n):
        if fase_index(n['fase']) >= fase_index('acceso_inicial'):
            return 'Esta PC ya es tuya.'
        if not e.tiene_salto_lateral(n['id']):
            return 'Necesitas una PC vecina donde ya seas administrador.'
        return None

    def efecto(self, e, n):
        super().efecto(e, n)
        return f"Salté a {n['nombre']} desde una PC vecina que ya controlaba."


class Exfil(Tecnica):
    id, nombre, tacticaMitre = 'exfil', 'Llevarse los datos', 'TA0010 Exfiltration'
    faseRequiere, faseProduce, ruido, facilidadBase, costo, puntos = 'acceso_inicial', 'exfiltracion', 'alto', 0.65, 4, 0
    descripcion = 'Empaqueta y se lleva los datos de la PC. Esto es lo que te acerca a ganar.'
    comandoEjemplo = 'llevarse-datos {target}'

    def validar(self, e, n):
        if fase_index(n['fase']) < fase_index('acceso_inicial'):
            return 'Primero tienes que tomar esta PC.'
        if n['valor'] <= 0:
            return 'Esta PC no tiene datos que valga la pena robar.'
        if n['id'] in e.exfiltrados:
            return 'Ya te llevaste los datos de esta PC.'
        return None

    def efecto(self, e, n):
        e.registrar_exfiltracion(n)
        return (f"¡Me llevé {n['valor']} MB de {n['nombre']}! "
                f"(llevas {e.datos_exfiltrados} de {e.meta_exfiltracion} MB para ganar).")


# Registro cerrado (orden = orden en el panel del atacante).
TECNICA_POR_ID = {t.id: t for t in (
    Portscan(), Enumeracion(), ScanDocs(), Bruteforce(), Exploit(), SqliDump(),
    Privesc(), DumpLsass(), PersistBackdoor(), PhishingSpray(), Pivot(), Exfil(),
)}
TECNICAS = [t.meta() for t in TECNICA_POR_ID.values()]
