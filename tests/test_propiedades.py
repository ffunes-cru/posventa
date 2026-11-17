# Part of Crucianelli Posventa Module
"""Pruebas basadas en propiedades (Hypothesis): secuencias al azar de operaciones sobre máquinas, certificados,
reclamos y traslados, y después de cada paso se verifica que se cumplan los invariantes del módulo.

Cada operación la intenta un usuario elegido por su rol frente al registro: casi siempre el que corresponde
(el concesionario dueño, el Staff) y a veces otro. Con usuarios uniformes al azar casi nunca se arma la
cadena FRU -> reclamo -> enviar -> tomar -> aceptar -> cerrar, y los invariantes se cumplirían sin probar
nada; con roles, la exploración llega a todos los estados y sigue probando que al que no le corresponde se
le rechace (y si no se le rechaza, el test falla).

Un test común prueba un caso que alguien pensó. Acá Hypothesis arma cientos de secuencias (cargar un FRU,
trasladar la máquina, que otro concesionario intente enviar el reclamo, devolverlo a En Proceso...) y, si
alguna rompe un invariante, la achica hasta la secuencia mínima que lo rompe y la muestra.

Hypothesis no es dependencia del módulo: si no está instalado, el test se saltea (en el CI se instala y
`POSVENTA_EXIGIR_HYPOTHESIS=1` hace que su ausencia sea un error). Variables de entorno:

- `POSVENTA_HYPOTHESIS_EJEMPLOS`: cantidad de secuencias (por defecto 100).
- `POSVENTA_HYPOTHESIS_AL_AZAR=1`: secuencias distintas en cada corrida. Por defecto son siempre las mismas,
  para que el CI no falle un día sí y otro no.
"""
import logging
import os
import unittest
from collections import Counter
from itertools import count

from odoo import fields
from odoo.exceptions import UserError

from .common import DUMMY_PDF_BASE64, TestPosventaCommon

try:
    from hypothesis import HealthCheck, settings, strategies as st
    from hypothesis.stateful import (Bundle, RuleBasedStateMachine, initialize, invariant, multiple, rule,
                                     run_state_machine_as_test)
except ImportError:
    st = None

## Transiciones de estado del reclamo que el módulo permite (incluye los retrocesos).
TRANSICIONES = {
    ('borrador', 'abierto'), ('abierto', 'en_proceso'), ('en_proceso', 'aceptado'), ('en_proceso', 'rechazado'),
    ('aceptado', 'cerrado'),
    ('abierto', 'borrador'), ('en_proceso', 'abierto'), ('aceptado', 'en_proceso'), ('rechazado', 'en_proceso'),
    ('cerrado', 'aceptado'),
}
## Quién puede hacer cada operación sobre un reclamo: 'staff' incluye al admin.
PERMISOS = {
    'tomar': {'staff', 'admin'}, 'aceptar': {'staff', 'admin'}, 'rechazar': {'staff', 'admin'},
    'cerrar': {'staff', 'admin'}, 'a_abierto': {'staff', 'admin'}, 'a_en_proceso': {'staff', 'admin'},
    'a_borrador': {'admin'}, 'a_aceptado': {'admin'},
}
if st:
    ## Quién intenta una operación de concesionario, de Staff o de admin; el primero es el habitual.
    ROL_CONCESIONARIO = st.sampled_from(['dueño', 'dueño', 'dueño', 'otro', 'staff', 'admin'])
    ROL_STAFF = st.sampled_from(['staff', 'staff', 'staff', 'admin', 'dueño', 'otro'])
    ROL_ADMIN = st.sampled_from(['admin', 'admin', 'staff', 'dueño'])
    ROL_DESTINO = st.sampled_from(['destino', 'destino', 'destino', 'dueño', 'otro', 'admin'])

_logger = logging.getLogger(__name__)


def _maquina_de_estados(caso, estadisticas):
    """Arma la máquina de estados de Hypothesis sobre los datos del caso de test.

    @param caso Instancia de TestPropiedades (usuarios, concesionarios, catálogo).
    @param estadisticas Counter donde se anotan las operaciones hechas y rechazadas y las transiciones vistas,
           para comprobar que la exploración no fue vacía.
    @return Clase RuleBasedStateMachine.
    """
    env = caso.env
    usuarios = {'conc_a': caso.user_concesionario_a, 'conc_b': caso.user_concesionario_b,
                'staff': caso.user_staff, 'admin': caso.user_admin}
    concesionarios = {'conc_a': caso.concesionario_a, 'conc_b': caso.concesionario_b}
    provincia = env['res.country.state'].search([('country_id.code', '=', 'AR')], limit=1)
    numero_of = count(1)

    class Posventa(RuleBasedStateMachine):
        maquinas = Bundle('maquinas')
        tickets = Bundle('tickets')

        def __init__(self):
            super().__init__()
            # Cada secuencia corre en su propio savepoint y se deshace al terminar
            self.punto = env.cr.savepoint()
            self.estado_ticket = {}  # id -> último estado visto, para validar las transiciones

        def teardown(self):
            self.punto.close(rollback=True)
            env.invalidate_all()

        # --- Ayudas ---

        def _como(self, actor, registros):
            return registros.with_user(usuarios[actor])

        def _actor(self, rol, dueno, destino=None):
            """Usuario (clave de `usuarios`) que cumple `rol` frente a un concesionario dueño.

            @param rol 'dueño', 'otro' (el otro concesionario), 'destino' (el de un traslado pendiente; si no
                   hay, el otro), 'staff' o 'admin'.
            """
            if rol in ('staff', 'admin'):
                return rol
            if rol == 'destino' and destino:
                dueno = destino
            elif rol in ('destino', 'otro'):
                return next(k for k, c in concesionarios.items() if c != dueno)
            return next((k for k, c in concesionarios.items() if c == dueno), 'conc_a')

        def _intentar(self, operacion, nombre='operación'):
            """Ejecuta `operacion` en un savepoint. Un rechazo de negocio (UserError y sus derivadas:
            ValidationError, AccessError, MissingError) deshace todo y es un resultado válido; cualquier otra
            excepción es un error del módulo y hace fallar el test.

            @return True si la operación se hizo.
            """
            try:
                with env.cr.savepoint():
                    operacion()
            except UserError as error:
                env.invalidate_all()
                estadisticas[f'{nombre}: rechazada'] += 1
                if os.environ.get('POSVENTA_HYPOTHESIS_MOTIVOS'):
                    estadisticas[f'  motivo de {nombre}: {str(error)[:90]}'] += 1
                return False
            env.invalidate_all()
            estadisticas[f'{nombre}: hecha'] += 1
            return True

        # --- Estado inicial: dos máquinas del concesionario A y una del B, recién liberadas ---

        @initialize(target=maquinas)
        def crear_maquinas(self):
            creadas = env['pv.maquina'].create([
                {'tipo': 'plantor', 'of': f'OF-PROP-{next(numero_of)}', 'concesionario_id': conc.id}
                for conc in (caso.concesionario_a, caso.concesionario_a, caso.concesionario_b)])
            return multiple(*creadas.ids)

        # --- Certificados ---

        @rule(maquina=maquinas, tipo=st.sampled_from(['fru', 'feu', 'cpm']), rol=ROL_CONCESIONARIO)
        def cargar_certificado(self, maquina, tipo, rol):
            dueno = env['pv.maquina'].browse(maquina).concesionario_id
            actor = self._actor(rol, dueno)
            hecho = self._intentar(lambda: self._como(actor, env['pv.certificado']).create({
                'maquina_id': maquina, 'tipo': tipo, 'fecha': fields.Date.today(),
                'archivo': DUMMY_PDF_BASE64, 'archivo_nombre': f'{tipo}.pdf',
            }), f'certificado {tipo}')
            if hecho and actor.startswith('conc'):
                assert concesionarios[actor] == dueno, f'{actor} cargó un certificado en una máquina ajena'

        # --- Reclamos ---

        @rule(target=tickets, maquina=maquinas, rol=ROL_CONCESIONARIO)
        def crear_ticket(self, maquina, rol):
            actor = self._actor(rol, env['pv.maquina'].browse(maquina).concesionario_id)
            creado = env['pv.ticket']

            def crear():
                nonlocal creado
                creado = self._como(actor, env['pv.ticket']).create({
                    'maquina_id': maquina, 'desvio_tipo_id': caso.desvio_rotura.id, 'descripcion': 'Falla',
                    'sistema_id': caso.sistema.id, 'subsistema_id': caso.subsistema.id,
                    'problema_id': caso.problema.id, 'hectareas': 100,
                    'multimedia_url': 'https://drive.google.com/prueba',
                })
            if not self._intentar(crear, 'crear reclamo'):
                return multiple()
            self.estado_ticket[creado.id] = 'borrador'
            return creado.id

        @rule(ticket=tickets, rol=ROL_CONCESIONARIO)
        def enviar(self, ticket, rol):
            dueno = env['pv.ticket'].browse(ticket).concesionario_id
            actor = self._actor(rol, dueno)
            hecho = self._intentar(
                lambda: self._como(actor, env['pv.ticket'].browse(ticket)).action_enviar_ticket(), 'enviar')
            if hecho:
                assert actor == 'admin' or concesionarios.get(actor) == dueno, f'{actor} envió un reclamo ajeno'

        @rule(ticket=tickets, rol=ROL_STAFF,
              accion=st.sampled_from(['tomar', 'aceptar', 'cerrar', 'rechazar',
                                      'a_abierto', 'a_en_proceso', 'a_borrador', 'a_aceptado']))
        def operar(self, ticket, rol, accion):
            if accion in ('a_borrador', 'a_aceptado') and rol == 'staff':
                rol = 'admin'  # los retrocesos de admin, casi siempre los intenta el admin
            actor = self._actor(rol, env['pv.ticket'].browse(ticket).concesionario_id)
            registro = self._como(actor, env['pv.ticket'].browse(ticket))
            metodos = {
                'tomar': registro.action_tomar_ticket, 'aceptar': registro.action_aceptar_ticket,
                'rechazar': lambda: self._rechazar(registro), 'cerrar': lambda: self._cerrar(actor, ticket),
                'a_borrador': registro.action_back_to_borrador, 'a_abierto': registro.action_back_to_abierto,
                'a_en_proceso': registro.action_back_to_en_proceso, 'a_aceptado': registro.action_back_to_aceptado,
            }
            if self._intentar(metodos[accion], accion):
                assert actor in PERMISOS[accion], f'{actor} pudo {accion}'

        def _rechazar(self, registro):
            registro.write({'rechazo_tag_ids': [(6, 0, caso.motivo_rechazo.ids)]})
            registro.action_rechazar_ticket()

        def _cerrar(self, actor, ticket):
            self._como(actor, env['pv.cerrar.ticket.wizard']).create({
                'ticket_id': ticket, 'solucion_aplicada': 'Cambio de pieza', 'garantia_aceptada': True,
            }).action_confirmar()

        # --- Traslados y liberación ---

        @rule(maquina=maquinas, rol=ROL_CONCESIONARIO, destino=st.sampled_from(['otro', 'otro', 'dueño']))
        def trasladar(self, maquina, rol, destino):
            dueno = env['pv.maquina'].browse(maquina).concesionario_id
            actor, destino = self._actor(rol, dueno), self._actor(destino, dueno)
            self._intentar(lambda: self._como(actor, env['pv.maquina'].browse(maquina))._iniciar_transferencia(
                concesionarios[destino], provincia, 'Ciudad'), 'trasladar')

        @rule(maquina=maquinas, rol=ROL_DESTINO,
              accion=st.sampled_from(['action_aceptar_transferencia', 'action_rechazar_transferencia',
                                      'action_cancelar_transferencia']))
        def responder_traslado(self, maquina, rol, accion):
            registro = env['pv.maquina'].browse(maquina)
            if accion == 'action_cancelar_transferencia' and rol == 'destino':
                rol = 'dueño'  # cancela el origen
            actor = self._actor(rol, registro.concesionario_id, registro.concesionario_destino_id)
            self._intentar(lambda: getattr(self._como(actor, env['pv.maquina'].browse(maquina)), accion)(),
                           accion.removeprefix('action_'))

        @rule(maquina=maquinas, rol=ROL_ADMIN, directa=st.booleans())
        def liberar(self, maquina, rol, directa):
            dueno = env['pv.maquina'].browse(maquina).concesionario_id
            actor = self._actor('dueño' if not directa and rol == 'admin' else rol, dueno)
            registro = self._como(actor, env['pv.maquina'].browse(maquina))
            if directa:
                hecho = self._intentar(lambda: registro.action_liberar_maquina('Canje'), 'liberar')
            else:
                self._intentar(lambda: registro.action_solicitar_liberacion('Canje'), 'solicitar liberación')
                hecho = self._intentar(lambda: self._como('admin', registro).action_aprobar_liberacion(),
                                       'aprobar liberación')
            if hecho and directa:
                assert actor == 'admin', f'{actor} liberó una máquina'

        # --- Paso guiado: lo que haría la gente en el orden habitual ---

        @rule(target=tickets, maquina=maquinas, quien=st.sampled_from(['correcto', 'correcto', 'correcto', 'otro']),
              variante=st.sampled_from(['seguir', 'seguir', 'seguir', 'rechazar', 'certificado', 'traslado']))
        def avanzar(self, maquina, quien, variante):
            """El paso natural siguiente en el ciclo de una máquina: su primer certificado, un reclamo, el paso
            siguiente del reclamo en curso (o reabrir uno si ya terminaron todos), el certificado que le falta o
            un traslado.

            Las reglas sueltas de arriba y de abajo prueban operaciones en cualquier orden y por cualquiera;
            esta lleva la máquina a los estados profundos (reclamos cerrados, máquinas vendidas o trasladadas).
            """
            # Un solo parámetro para los dos roles: Hypothesis correlaciona a propósito los valores que genera
            # y con dos roles independientes los pasos de Staff caían casi siempre en un concesionario
            rol_concesionario, rol_staff = ('dueño', 'staff') if quien == 'correcto' else ('otro', 'dueño')
            m = env['pv.maquina'].browse(maquina)
            if variante == 'traslado':
                if m.estado == 'pendiente':
                    self.responder_traslado(maquina, 'destino', 'action_aceptar_transferencia')
                else:
                    self.trasladar(maquina, rol_concesionario, 'otro')
                return multiple()
            if not m.tiene_fru or variante == 'certificado':
                tipo = 'fru' if not m.tiene_fru else 'feu' if not m.tiene_feu_vigente else 'cpm'
                self.cargar_certificado(maquina, tipo, rol_concesionario)
                return multiple()
            # El reclamo en curso más avanzado: concentra el progreso en vez de repartirlo
            orden = {'borrador': 0, 'abierto': 1, 'en_proceso': 2, 'aceptado': 3}
            # (un borrador cuyo certificado se archivó por un traslado o una liberación ya no se puede enviar)
            en_curso = m.ticket_ids.filtered(lambda t: t.estado in orden and (
                t.estado != 'borrador' or t.certificado_id._es_vigente_para_reclamos()))
            en_curso = en_curso.sorted(lambda t: -orden[t.estado])[:1]
            if not en_curso and len(m.ticket_ids) >= 3:
                # Ya tuvo varios reclamos y todos terminaron: se reabre uno
                self.retroceder(maquina, quien, 0)
                return multiple()
            if not en_curso:
                return self.crear_ticket(maquina, rol_concesionario)
            ticket = en_curso
            if ticket.estado == 'borrador':
                self.enviar(ticket.id, rol_concesionario)
                return multiple()
            accion = {'abierto': 'tomar', 'en_proceso': 'rechazar' if variante == 'rechazar' else 'aceptar',
                      'aceptado': 'cerrar'}
            self.operar(ticket.id, rol_staff, accion[ticket.estado])
            return multiple()

        @rule(maquina=maquinas, quien=st.sampled_from(['correcto', 'correcto', 'correcto', 'otro']),
              indice=st.integers(0, 3))
        def retroceder(self, maquina, quien, indice):
            """Devuelve un paso atrás un reclamo enviado de la máquina (0 = el más avanzado)."""
            orden = {'abierto': 1, 'en_proceso': 2, 'aceptado': 3, 'rechazado': 4, 'cerrado': 5}
            enviados = env['pv.maquina'].browse(maquina).ticket_ids.filtered(lambda t: t.estado in orden)
            enviados = enviados.sorted(lambda t: -orden[t.estado])
            if enviados:
                ticket = enviados[indice % len(enviados)]
                accion = {'abierto': 'a_borrador', 'en_proceso': 'a_abierto', 'aceptado': 'a_en_proceso',
                          'rechazado': 'a_en_proceso', 'cerrado': 'a_aceptado'}[ticket.estado]
                self.operar(ticket.id, 'staff' if quien == 'correcto' else 'dueño', accion)

        # --- Invariantes: se verifican después de cada paso ---

        @invariant()
        def transiciones_de_reclamo_permitidas(self):
            for ticket in env['pv.ticket'].browse(list(self.estado_ticket)):
                anterior, actual = self.estado_ticket[ticket.id], ticket.estado
                assert anterior == actual or (anterior, actual) in TRANSICIONES, \
                    f'{ticket.name}: {anterior} -> {actual} no es una transición válida'
                if anterior != actual:
                    estadisticas[f'transición {anterior} -> {actual}'] += 1
                self.estado_ticket[ticket.id] = actual

        @invariant()
        def datos_que_exige_cada_estado(self):
            for t in env['pv.ticket'].browse(list(self.estado_ticket)):
                if t.estado in ('en_proceso', 'aceptado', 'rechazado', 'cerrado'):
                    assert t.responsable_id and t.fecha_primera_atencion, f'{t.name} en {t.estado} sin responsable'
                if t.estado in ('aceptado', 'cerrado'):
                    assert t.fecha_solucion, f'{t.name} en {t.estado} sin fecha de solución'
                if t.estado == 'rechazado':
                    assert t.rechazo_tag_ids and t.fecha_cierre, f'{t.name} rechazado sin motivo o fecha'
                if t.estado == 'cerrado':
                    assert t.solucion_aplicada and t.fecha_cierre, f'{t.name} cerrado sin solución o fecha'
                assert min(t.t1_horas, t.t2_horas, t.t3_horas) >= 0, f'{t.name} con tiempos negativos'

        @invariant()
        def certificados_en_secuencia(self):
            Cert = env['pv.certificado']
            for maquina in env['pv.maquina'].search([('of', 'like', 'OF-PROP-')]):
                activos = Cert.search([('maquina_id', '=', maquina.id), ('active', '=', True)])
                vigentes = activos.filtered(lambda c: c.estado_certificado == 'vigente')
                cargados = activos.filtered(lambda c: c.estado_certificado in ('vigente', 'vencido'))
                for tipo in ('fru', 'feu', 'cpm'):
                    assert len(vigentes.filtered(lambda c: c.tipo == tipo)) <= 1, f'{maquina.of}: dos {tipo} vigentes'
                if cargados.filtered(lambda c: c.tipo in ('feu', 'cpm')):
                    assert cargados.filtered(lambda c: c.tipo == 'fru'), f'{maquina.of}: FEU o CPM sin FRU'

        @invariant()
        def estado_de_maquina_coherente(self):
            for m in env['pv.maquina'].search([('of', 'like', 'OF-PROP-')]):
                assert (m.estado == 'pendiente') == bool(m.concesionario_destino_id), \
                    f'{m.of}: estado {m.estado} y destino {m.concesionario_destino_id.name}'
                assert m.concesionario_destino_id != m.concesionario_id, f'{m.of}: se traslada a su propio dueño'
                if m.tiene_cpm:
                    assert m.estado in ('vendida', 'pendiente'), f'{m.of}: CPM vigente y estado {m.estado}'
                if m.estado in ('stock', 'vendida'):
                    assert m.tiene_fru, f'{m.of}: {m.estado} sin FRU'
                if m.estado == 'liberada':
                    assert not m.tiene_fru, f'{m.of}: liberada con FRU cargado'

        @invariant()
        def cada_uno_ve_solo_lo_suyo(self):
            tickets = env['pv.ticket'].browse(list(self.estado_ticket))
            maquinas = env['pv.maquina'].search([('of', 'like', 'OF-PROP-')])
            for actor, conc in concesionarios.items():
                ve = self._como(actor, env['pv.ticket']).search([('id', 'in', tickets.ids)])
                assert set(ve.ids) == set(tickets.filtered(lambda t: t.concesionario_id == conc).ids), \
                    f'{actor} ve reclamos que no son de su concesionario (o no ve los suyos)'
                ve = self._como(actor, env['pv.maquina']).search([('id', 'in', maquinas.ids)])
                esperado = maquinas.filtered(lambda m: m.concesionario_id == conc or (
                    m.estado == 'pendiente' and m.concesionario_destino_id == conc))
                assert set(ve.ids) == set(esperado.ids), f'{actor} ve máquinas que no le corresponden'
            ve = self._como('staff', env['pv.ticket']).search([('id', 'in', tickets.ids)])
            assert set(ve.ids) == set(tickets.filtered(lambda t: t.estado != 'borrador').ids), \
                'el Staff ve borradores (o no ve reclamos enviados)'

    return Posventa


@unittest.skipUnless(st or os.environ.get('POSVENTA_EXIGIR_HYPOTHESIS'),
                     'Hypothesis no está instalado (pip install hypothesis)')
class TestPropiedades(TestPosventaCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.motivo_rechazo = cls.env.ref('posventa.rechazo_reclamo_info_incompleta')

    def test_invariantes_en_secuencias_al_azar(self):
        self.assertIsNotNone(st, 'POSVENTA_EXIGIR_HYPOTHESIS está activo y Hypothesis no está instalado')
        estadisticas = Counter()
        run_state_machine_as_test(_maquina_de_estados(self, estadisticas), settings=settings(
            max_examples=int(os.environ.get('POSVENTA_HYPOTHESIS_EJEMPLOS', 100)),
            stateful_step_count=80,
            derandomize=not os.environ.get('POSVENTA_HYPOTHESIS_AL_AZAR'),
            deadline=None,
            database=None,
            suppress_health_check=list(HealthCheck),
        ))
        _logger.info('Operaciones y transiciones exploradas:\n%s',
                     '\n'.join(f'  {n:6} {clave}' for clave, n in sorted(estadisticas.items())))
        # Que la exploración no haya sido vacía: si todo se rechazara, los invariantes se cumplirían sin probar nada.
        # El camino principal es obligatorio; los retrocesos y los caminos raros dependen de la semilla, y si no
        # aparecen solo se avisa (con POSVENTA_HYPOTHESIS_AL_AZAR o tras cambiar el código puede pasar).
        principal = {'transición borrador -> abierto', 'transición abierto -> en_proceso',
                     'transición en_proceso -> aceptado', 'transición aceptado -> cerrado',
                     'trasladar: hecha', 'aceptar_transferencia: hecha', 'aprobar liberación: hecha'}
        self.assertFalse(principal - set(estadisticas),
                         'La exploración no recorrió el camino principal: subir POSVENTA_HYPOTHESIS_EJEMPLOS o revisar '
                         'la regla avanzar')
        otros = {f'transición {a} -> {b}' for a, b in TRANSICIONES} | {
            f'{op}: hecha' for op in ('rechazar', 'rechazar_transferencia', 'cancelar_transferencia', 'liberar')}
        if faltan := sorted(otros - set(estadisticas)):
            _logger.warning('La exploración no llegó a: %s', ', '.join(faltan))
