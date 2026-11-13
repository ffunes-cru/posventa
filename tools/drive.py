# Part of Crucianelli Posventa Module
"""Unidad compartida de Google Drive vía rclone, configurada desde los Ajustes de Odoo.

rclone recibe la cuenta de servicio y la unidad por variables de entorno (configuración en memoria):
en el servidor solo hace falta el programa rclone instalado, sin `rclone config` ni rclone.conf.
"""
import json
import os
import re
import shutil
import subprocess

REMOTO = 'posventa'
CARPETA_BASE_DEFAULT = 'Crucianelli_Posventa/Reclamos'

PARAM_CREDENCIALES = 'posventa.drive_credentials'
PARAM_UNIDAD = 'posventa.drive_shared_drive_id'
PARAM_CARPETA = 'posventa.drive_folder'


class DriveError(Exception):
    """Drive no configurado o inaccesible. El mensaje es apto para mostrar al usuario."""


def cuenta_de_servicio(credenciales):
    """Email de la cuenta de servicio del JSON de credenciales ('' si el JSON no es válido)."""
    try:
        return json.loads(credenciales or '').get('client_email', '')
    except (ValueError, AttributeError):
        return ''


class RcloneDrive:

    def __init__(self, credenciales, unidad_id, carpeta_base):
        self.credenciales = (credenciales or '').strip()
        self.unidad_id = (unidad_id or '').strip()
        self.carpeta_base = (carpeta_base or CARPETA_BASE_DEFAULT).strip('/ ')

    @classmethod
    def desde_ajustes(cls, env):
        get = env['ir.config_parameter'].sudo().get_param
        return cls(get(PARAM_CREDENCIALES), get(PARAM_UNIDAD), get(PARAM_CARPETA))

    def ruta(self, *partes):
        """Ruta rclone dentro de la carpeta base: posventa:<base>/<partes...>."""
        return f"{REMOTO}:" + '/'.join([self.carpeta_base, *partes])

    # --- Operaciones (levantan DriveError si rclone falla) ---
    def verificar(self):
        """Comprueba configuración, conexión y permiso de escritura (crea la carpeta base si falta)."""
        if not cuenta_de_servicio(self.credenciales):
            raise DriveError("Falta cargar el JSON de la cuenta de servicio de Google en Ajustes de Posventa.")
        if not self.unidad_id:
            raise DriveError("Falta cargar el ID de la unidad compartida de Google Drive en Ajustes de Posventa.")
        self._rclone('mkdir', self.ruta(), timeout=60)

    def copiar(self, archivo_local, carpeta, mimetype):
        self._rclone('copy', archivo_local, self.ruta(carpeta), '-M', '--metadata-set', f'content-type={mimetype}',
                     timeout=1200)

    def existe(self, carpeta, nombre):
        try:
            salida = self._rclone('lsf', self.ruta(carpeta), '--files-only', timeout=30)
        except DriveError:
            return False
        return nombre in salida.splitlines()

    def enlace(self, carpeta, nombre=None):
        """Enlace para compartir; si la unidad no permite enlaces públicos, el enlace interno por ID."""
        ruta = self.ruta(carpeta, nombre) if nombre else self.ruta(carpeta)
        try:
            return self._rclone('link', ruta, timeout=60).strip()
        except DriveError:
            pass
        try:
            item = json.loads(self._rclone('lsjson', '--stat', ruta, timeout=60))
        except (DriveError, ValueError):
            return ''
        if item.get('IsDir'):
            return f"https://drive.google.com/drive/folders/{item['ID']}"
        return f"https://drive.google.com/file/d/{item['ID']}/view"

    # --- rclone ---
    def _rclone(self, *args, timeout):
        try:
            # Un solo intento por llamada: los reintentos los maneja el cron
            res = subprocess.run([_binario(), '--config', '', '--retries', '1', *args], env=self._entorno(),
                                 capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise DriveError(f"Google Drive no respondió en {timeout} segundos.") from None
        if res.returncode != 0:
            raise DriveError(_ultima_linea(res.stderr) or f"rclone terminó con código {res.returncode}.")
        return res.stdout

    def _entorno(self):
        prefijo = f'RCLONE_CONFIG_{REMOTO.upper()}_'
        return {
            **os.environ,
            prefijo + 'TYPE': 'drive',
            prefijo + 'SCOPE': 'drive',
            prefijo + 'SERVICE_ACCOUNT_CREDENTIALS': self.credenciales,
            prefijo + 'TEAM_DRIVE': self.unidad_id,
        }


def _binario():
    binario = shutil.which('rclone') or os.path.expanduser('~/.local/bin/rclone')
    if not os.path.exists(binario):
        raise DriveError("rclone no está instalado en el servidor de Odoo.")
    return binario


def _ultima_linea(stderr):
    """Último error de rclone, sin fecha, nivel de log ni las URLs de la API de Google."""
    lineas = [linea for linea in (stderr or '').splitlines() if linea.strip()]
    if not lineas:
        return ''
    # El nivel de log ('ERROR :') no aparece en todas las versiones de rclone
    mensaje = re.sub(r'^\d{4}/\d\d/\d\d \d\d:\d\d:\d\d (?:[A-Z]+\s*:\s*)?', '', lineas[-1])
    mensaje = re.sub(r'\w+ "https?://[^"]*": ', '', mensaje)
    return mensaje.strip()[:300]
