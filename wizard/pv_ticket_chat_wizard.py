# Part of Crucianelli Posventa Module
import json
import requests
from markupsafe import Markup
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError, AccessError


class PvTicketChatWizard(models.TransientModel):
    _name = 'pv.ticket.chat.wizard'
    _description = 'Asistente de Chat de IA para Tickets'

    ticket_id = fields.Many2one(
        'pv.ticket',
        string='Ticket',
        required=True,
        ondelete='cascade',
        default=lambda self: self.env.context.get('active_id'),
    )
    ticket_estado = fields.Selection(
        related='ticket_id.estado',
        string='Estado del Ticket',
    )
    conversation_state = fields.Text(
        string='Estado de Conversación',
        default='[]',
    )
    conversation_html = fields.Html(
        string='Conversación',
        readonly=True,
    )
    user_message = fields.Text(
        string='Tu mensaje',
    )

    def _initialize_chat(self):
        self.ensure_one()
        ticket = self.ticket_id
        similar_count = len(self._get_similar_tickets())

        welcome_msg = ""
        if ticket.estado == 'borrador':
            welcome_msg = (
                f"Hola, soy tu <b>Asistente de IA de Posventa</b>.<br/>"
                f"He cargado los datos del ticket en borrador. "
            )
            if similar_count > 0:
                welcome_msg += f"He encontrado <b>{similar_count} tickets similares solucionados</b> en la base de datos para asistirte.<br/>"
            else:
                welcome_msg += "No encontré tickets similares previos, pero puedo ayudarte a revisar los detalles de la falla.<br/>"
            welcome_msg += "Puedes consultarme sobre el diagnóstico, pedirme que ajuste la descripción, o enviar el ticket cuando estés listo."
        else:
            welcome_msg = (
                f"Hola, soy tu <b>Asistente de IA de Posventa</b>.<br/>"
                f"El ticket actual se encuentra en estado <b>{ticket.estado.upper()}</b>. "
            )
            if similar_count > 0:
                welcome_msg += f"Encontré <b>{similar_count} tickets similares resueltos</b> para ayudarte a diagnosticar o proponer medidas.<br/>"
            welcome_msg += "Puedes pedirme sugerencias de resolución, medidas de seguimiento, o pedirme operar el ticket (ej. derivar, aceptar, cerrar)."

        initial_html = f"""
        <div style="display: flex; margin-bottom: 12px; align-items: start;">
            <div style="background-color: #e0f2fe; color: #0369a1; padding: 12px; border-radius: 8px; max-width: 85%; font-family: sans-serif; font-size: 14px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
                <strong>Asistente IA</strong><br/>
                {welcome_msg}
            </div>
        </div>
        """

        initial_history = [
            {
                "role": "model",
                "parts": [{
                    "text": welcome_msg.replace("<br/>", "\n").replace("<b>", "**").replace("</b>", "**")
                }]
            }
        ]

        self.write({
            'conversation_html': initial_html,
            'conversation_state': json.dumps(initial_history),
        })

    def _get_similar_tickets(self):
        self.ensure_one()
        ticket = self.ticket_id
        domain = [
            ('estado', 'in', ('aceptado', 'cerrado')),
            ('id', '!=', ticket.id),
        ]

        if ticket.tipo_ticket == 'post_pm':
            if ticket.subsistema_id:
                domain_sub = domain + [('subsistema_id', '=', ticket.subsistema_id.id)]
                similar = self.env['pv.ticket'].search(domain_sub, limit=5)
                if len(similar) >= 3:
                    return similar
            if ticket.sistema_id:
                domain_sis = domain + [('sistema_id', '=', ticket.sistema_id.id)]
                return self.env['pv.ticket'].search(domain_sis, limit=5)
        else:
            if ticket.desvio_tipo:
                domain_desvio = domain + [('desvio_tipo', '=', ticket.desvio_tipo)]
                return self.env['pv.ticket'].search(domain_desvio, limit=5)

        return self.env['pv.ticket'].search(domain, limit=3)

    def _get_staff_users_text(self):
        staff_group = self.env.ref('posventa.group_pv_staff', raise_if_not_found=False)
        if not staff_group:
            return "No hay usuarios del staff de posventa configurados."
        users_list = []
        for user in staff_group.all_user_ids:
            users_list.append(f"- ID: {user.id}, Nombre: {user.name} (Email: {user.email or 'N/A'})")
        return "\n".join(users_list)

    def _get_tools_definition(self):
        return [{
            "functionDeclarations": [
                {
                    "name": "enviar_ticket",
                    "description": "Envía el ticket para revisión técnica (cambia el estado de Borrador a Abierto)."
                },
                {
                    "name": "tomar_ticket",
                    "description": "El técnico toma el ticket para empezar a procesarlo (cambia el estado de Abierto a En Proceso)."
                },
                {
                    "name": "aceptar_ticket",
                    "description": "Acepta y valida el reclamo de posventa (cambia el estado de En Proceso a Aceptado) y envía notificación al concesionario."
                },
                {
                    "name": "rechazar_ticket",
                    "description": "Rechaza el reclamo del ticket. Requiere especificar un motivo del rechazo.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "motivo": {
                                "type": "STRING",
                                "description": "Motivo claro y detallado del rechazo."
                            }
                        },
                        "required": ["motivo"]
                    }
                },
                {
                    "name": "cerrar_ticket",
                    "description": "Cierra definitivamente el ticket (cambia el estado de Aceptado a Cerrado)."
                },
                {
                    "name": "derivar_ticket",
                    "description": "Deriva/asigna el ticket a otro responsable técnico del staff de posventa usando su ID de usuario.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "responsable_id": {
                                "type": "INTEGER",
                                "description": "ID del usuario res.users al cual asignar el ticket."
                            }
                        },
                        "required": ["responsable_id"]
                    }
                },
                {
                    "name": "actualizar_datos_ticket",
                    "description": "Actualiza la descripción o acciones realizadas del ticket en Odoo.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "descripcion": {
                                "type": "STRING",
                                "description": "Nueva descripción detallada del problema."
                            },
                            "acciones_realizadas": {
                                "type": "STRING",
                                "description": "Acciones correctivas o preventivas realizadas en la máquina."
                            }
                        }
                    }
                },
                {
                    "name": "crear_medida_seguimiento",
                    "description": "Crea una medida de seguimiento o tarea correctiva asociada a este ticket en Odoo.",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "titulo": {
                                "type": "STRING",
                                "description": "Título o nombre descriptivo de la medida/tarea."
                            },
                            "tipo": {
                                "type": "STRING",
                                "description": "Tipo de medida. Opciones: 'accion', 'medida', 'actualizacion', 'resolucion_parcial', 'resolucion_definitiva'."
                            },
                            "responsable_id": {
                                "type": "INTEGER",
                                "description": "ID del usuario res.users responsable (opcional, por defecto el usuario actual)."
                            },
                            "fecha_vencimiento": {
                                "type": "STRING",
                                "description": "Fecha de vencimiento en formato YYYY-MM-DD (opcional)."
                            },
                            "comentario": {
                                "type": "STRING",
                                "description": "Comentarios adicionales sobre la medida (opcional)."
                            }
                        },
                        "required": ["titulo", "tipo"]
                    }
                }
            ]
        }]

    def _get_system_instruction(self):
        self.ensure_one()
        ticket = self.ticket_id

        similar = self._get_similar_tickets()
        rag_text = ""
        if similar:
            for idx, t in enumerate(similar, 1):
                rag_text += f"{idx}. Ticket: {t.name}\n"
                rag_text += f"   Tipo: {t.tipo_ticket == 'pre_pm' and 'Pre Puesta en Marcha' or 'Post Puesta en Marcha'}\n"
                if t.sistema_id:
                    rag_text += f"   Sistema: {t.sistema_id.name}\n"
                if t.subsistema_id:
                    rag_text += f"   Subsistema: {t.subsistema_id.name}\n"
                if t.problema_id:
                    rag_text += f"   Problema: {t.problema_id.name}\n"
                if t.desvio_tipo:
                    rag_text += f"   Desvío: {t.desvio_tipo}\n"
                rag_text += f"   Descripción: {t.descripcion or 'N/A'}\n"
                rag_text += f"   Acciones Realizadas: {t.acciones_realizadas or 'N/A'}\n"
                if t.motivo_rechazo:
                    rag_text += f"   Motivo de Rechazo: {t.motivo_rechazo}\n"
                rag_text += "\n"
        else:
            rag_text = "No se encontraron tickets similares resueltos en el sistema.\n"

        staff_users = self._get_staff_users_text()

        instruction = f"""Eres el Asistente de IA de Posventa oficial de Crucianelli.
Tu función es ayudar a los usuarios (concesionarios y personal técnico) a diagnosticar, clasificar, solucionar, asignar y procesar el ticket de reclamo actual.

DATOS DEL TICKET ACTUAL:
- Número: {ticket.name}
- Estado actual: {ticket.estado.upper()}
- Tipo de Ticket: {ticket.tipo_ticket == 'pre_pm' and 'Pre Puesta en Marcha' or 'Post Puesta en Marcha'}
- Máquina: {ticket.maquina_id.name} (Tipo: {ticket.tipo_maquina or 'N/A'}, Orden Fab: {ticket.of or 'N/A'})
- Concesionario: {ticket.concesionario_id.name if ticket.concesionario_id else 'N/A'}
- Cliente: {ticket.cliente_id.name if ticket.cliente_id else 'N/A'}
- Operador/Cargado por: {ticket.operador_id.name if ticket.operador_id else 'N/A'}
- Sistema: {ticket.sistema_id.name if ticket.sistema_id else 'No especificado'}
- Subsistema: {ticket.subsistema_id.name if ticket.subsistema_id else 'No especificado'}
- Problema: {ticket.problema_id.name if ticket.problema_id else 'No especificado'}
- Descripción: {ticket.descripcion or 'No ingresada aún'}
- Acciones realizadas: {ticket.acciones_realizadas or 'Ninguna registrada'}
- Responsable Técnico Asignado: {ticket.responsable_id.name if ticket.responsable_id else 'Sin asignar'}

TICKETS SIMILARES RESUELTOS (RAG):
{rag_text}

USUARIOS DEL STAFF DE POSVENTA DISPONIBLES PARA ASIGNAR (RESPONSABLES):
{staff_users}

GUARDRAILS (REGLAS DE SEGURIDAD Y COMPORTAMIENTO):
1. Solo debes responder dudas y consultas relativas a este ticket, la máquina asociada, y temas afines de posventa / mecánica / sistemas hidráulicos / componentes de Crucianelli.
2. Si el usuario te hace consultas fuera del contexto del ticket o de la posventa (por ejemplo, programación, entretenimiento, política, finanzas, etc.), debes declinar amablemente responder indicando que eres un asistente dedicado exclusivamente al soporte del ticket {ticket.name}.
3. Recomienda soluciones al usuario basándote en los tickets similares (RAG) o en las buenas prácticas de posventa.
4. Tienes herramientas de Odoo a tu disposición. Si el usuario te indica que desea derivar, cambiar la descripción, enviar el ticket para revisión, aceptarlo, rechazarlo o agregar una medida de seguimiento, debes invocar la herramienta correspondiente de manera inmediata.

5. MANEJO DE ERRORES EN LAS HERRAMIENTAS (CRÍTICO):
- Si ejecutas una herramienta y el sistema responde con un JSON que contiene 'status': 'error', analiza el 'error_type'.
- Si el 'error_type' es 'AccessError', infórmale al usuario con mucha educación y profesionalismo que su usuario actual de Odoo NO posee los privilegios o permisos de acceso necesarios para realizar esa acción en este momento. No vuelvas a intentar la acción.
- Si el 'error_type' es 'UserError' o 'ValidationError', explícale claramente al usuario el motivo del rechazo del sistema (utilizando la información provista en 'message') para que corrija los datos o entienda la restricción del negocio.
- JAMÁS le digas al usuario que la acción fue exitosa si el resultado de la herramienta arrojó un 'error'.
"""
        return instruction

    def _call_gemini_api(self, contents, tools=None):
        enabled_param = self.env['ir.config_parameter'].sudo().get_param('posventa.enable_ai_integration', 'True')
        if str(enabled_param).lower() not in ('true', '1'):
            raise UserError(_("La integración con Inteligencia Artificial está deshabilitada en los ajustes del módulo."))

        api_key = self.env['ir.config_parameter'].sudo().get_param('posventa.gemini_api_key')
        if not api_key or api_key == 'TU_API_KEY_AQUI':
            raise ValidationError(_(
                "La API Key de Gemini no está configurada o es inválida. "
                "Por favor configure la clave 'posventa.gemini_api_key' en Ajustes -> Parámetros del Sistema."
            ))

        model_name = self.env['ir.config_parameter'].sudo().get_param('posventa.gemini_model') or 'gemini-2.5-flash'
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

        payload = {
            "contents": contents,
            "systemInstruction": {
                "parts": [{"text": self._get_system_instruction()}]
            }
        }
        if tools:
            payload["tools"] = tools

        headers = {'Content-Type': 'application/json'}
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=30)
            if res.status_code != 200:
                raise ValidationError(_("Error al llamar a Gemini API (Status %s): %s", res.status_code, res.text))
            return res.json()
        except requests.exceptions.RequestException as e:
            raise ValidationError(_("Error de conexión al llamar a Gemini API: %s", str(e)))

    def _execute_tool(self, tool_name, args):
        ticket = self.ticket_id
        try:
            if tool_name == 'enviar_ticket':
                if ticket.estado != 'borrador':
                    return {'status': 'error', 'message': f"El ticket ya no está en borrador. Estado actual: {ticket.estado}"}
                ticket._action_enviar_ticket_direct()
                return {'status': 'success', 'message': "Ticket enviado a revisión técnica. El estado cambió a ABIERTO."}

            elif tool_name == 'tomar_ticket':
                if ticket.estado != 'abierto':
                    return {'status': 'error', 'message': f"Solo se pueden tomar tickets en estado ABIERTO. Estado actual: {ticket.estado}"}
                ticket.action_tomar_ticket()
                return {'status': 'success', 'message': f"Ticket tomado por {self.env.user.name}. Estado actual: EN PROCESO."}

            elif tool_name == 'aceptar_ticket':
                if ticket.estado != 'en_proceso':
                    return {'status': 'error', 'message': f"Solo se pueden aceptar tickets en estado EN PROCESO. Estado actual: {ticket.estado}"}
                ticket.action_aceptar_ticket_direct()
                return {'status': 'success', 'message': "Reclamo aceptado y validado. Notificación enviada."}

            elif tool_name == 'rechazar_ticket':
                if ticket.estado != 'en_proceso':
                    return {'status': 'error', 'message': f"Solo se pueden rechazar tickets en estado EN PROCESO. Estado actual: {ticket.estado}"}
                motivo = args.get('motivo')
                if not motivo:
                    return {'status': 'error', 'message': "Debe especificar un motivo de rechazo."}
                ticket.action_rechazar_ticket_direct(motivo)
                return {'status': 'success', 'message': f"Reclamo rechazado. Motivo: {motivo}. Notificación enviada."}

            elif tool_name == 'cerrar_ticket':
                if ticket.estado != 'aceptado':
                    return {'status': 'error', 'message': f"Solo se pueden cerrar tickets en estado ACEPTADO. Estado actual: {ticket.estado}"}
                ticket.action_cerrar_ticket()
                return {'status': 'success', 'message': "Ticket cerrado definitivamente. Expediente completo."}

            elif tool_name == 'derivar_ticket':
                resp_id = args.get('responsable_id')
                user = self.env['res.users'].browse(int(resp_id))
                if not user.exists():
                    return {'status': 'error', 'message': f"El usuario con ID {resp_id} no existe."}
                ticket.write({'responsable_id': user.id})
                ticket.message_post(
                    body=_(f"Ticket derivado a {user.name} por el Asistente IA."),
                    message_type='notification',
                    subtype_xmlid='mail.mt_note',
                )
                return {'status': 'success', 'message': f"Ticket derivado exitosamente al usuario {user.name} (ID {user.id})."}

            elif tool_name == 'actualizar_datos_ticket':
                vals = {}
                if 'descripcion' in args:
                    vals['descripcion'] = args['descripcion']
                if 'acciones_realizadas' in args:
                    vals['acciones_realizadas'] = args['acciones_realizadas']
                if vals:
                    ticket.write(vals)
                    return {'status': 'success', 'message': "Campos del ticket actualizados en Odoo."}
                return {'status': 'info', 'message': "No se especificaron campos para actualizar."}

            elif tool_name == 'crear_medida_seguimiento':
                titulo = args.get('titulo')
                tipo = args.get('tipo')
                resp_id = args.get('responsable_id') or self.env.user.id
                fecha_vencimiento = args.get('fecha_vencimiento') or False
                comentario = args.get('comentario') or ""

                medida_vals = {
                    'name': titulo,
                    'ticket_id': ticket.id,
                    'tipo': tipo,
                    'responsable_id': int(resp_id),
                    'comentario': comentario,
                }
                if fecha_vencimiento:
                    medida_vals['fecha_vencimiento'] = fields.Date.from_string(fecha_vencimiento)

                medida = self.env['pv.ticket.medida'].create(medida_vals)
                return {'status': 'success', 'message': f"Medida de seguimiento '{medida.name}' creada exitosamente."}

            else:
                return {'status': 'error', 'message': f"Herramienta '{tool_name}' desconocida."}

        except AccessError as e:
            # Captura fallos de ir.model.access o ir.rule (Reglas de registro)
            return {
                'status': 'error',
                'error_type': 'AccessError',
                'message': "El usuario actual no tiene permisos suficientes en Odoo (reglas de registro o grupos de seguridad) para ejecutar esta acción sobre este registro."
            }

        except ValidationError as e:
            # Captura restricciones de campos o métodos de validación
            return {
                'status': 'error',
                'error_type': 'ValidationError',
                'message': f"Error de validación de datos en Odoo: {str(e)}"
            }

        except UserError as e:
            # Captura alertas de negocio (como las que tenés de 'Solo el concesionario destino puede aceptar')
            return {
                'status': 'error',
                'error_type': 'UserError',
                'message': f"La acción fue rechazada por el sistema. Razón: {str(e)}"
            }

        except Exception as e:
            # Cualquier otro error inesperado de código
            return {
                'status': 'error',
                'error_type': 'UnexpectedError',
                'message': f"Ocurrió un error inesperado en el servidor al intentar procesar la acción: {str(e)}"
            }

    def _markdown_to_html(self, text):
        if not text:
            return ""
        import html
        import re
        # Escape HTML tags from text to prevent injection, but allow formatting
        escaped_text = html.escape(text)
        
        # Convert **bold** to <strong>
        escaped_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', escaped_text)
        
        # Convert *italic* to <em>
        escaped_text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', escaped_text)
        
        # Convert list items (* or -) to <li>
        lines = escaped_text.split('\n')
        html_lines = []
        in_list = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('* ') or stripped.startswith('- '):
                content = stripped[2:]
                if not in_list:
                    html_lines.append('<ul style="margin-top: 5px; margin-bottom: 5px; padding-left: 20px;">')
                    in_list = True
                html_lines.append(f'<li>{content}</li>')
            else:
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
                html_lines.append(line)
        if in_list:
            html_lines.append('</ul>')
            
        final_html = ""
        for line in html_lines:
            if line.startswith('<ul') or line.startswith('</ul') or line.startswith('<li'):
                final_html += line
            else:
                final_html += line + "<br/>"
        return final_html

    def _render_conversation_html(self, history):
        html = """
        <div class="o_chat_history" style="max-height: 400px; overflow-y: auto; padding: 10px; background-color: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px;">
        """
        for msg in history:
            role = msg.get('role')
            parts = msg.get('parts', [])
            text = ""
            for p in parts:
                if 'text' in p:
                    text += p['text']
                elif 'functionCall' in p:
                    fc = p['functionCall']
                    text += f"<i>[Ejecutando acción del sistema: {fc['name']} con argumentos {fc.get('args', {})}]</i>"
                elif 'functionResponse' in p:
                    fr = p['functionResponse']
                    text += f"<i>[Resultado de acción: {fr.get('response', {}).get('message', 'Completado')} ]</i>"

            if not text.strip():
                continue

            # Convert markdown formatting to clean HTML safely
            formatted_text = self._markdown_to_html(text)

            if role == 'user':
                html += f"""
                <div style="display: flex; justify-content: flex-end; margin-bottom: 12px;">
                    <div style="background-color: #f3f4f6; color: #1f2937; padding: 12px; border-radius: 8px; max-width: 85%; font-family: sans-serif; font-size: 14px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
                        <strong>Tú</strong><br/>
                        {formatted_text}
                    </div>
                </div>
                """
            elif role == 'model':
                html += f"""
                <div style="display: flex; justify-content: flex-start; margin-bottom: 12px;">
                    <div style="background-color: #e0f2fe; color: #0369a1; padding: 12px; border-radius: 8px; max-width: 85%; font-family: sans-serif; font-size: 14px; box-shadow: 0 1px 2px rgba(0,0,0,0.05);">
                        <strong>Asistente IA</strong><br/>
                        {formatted_text}
                    </div>
                </div>
                """
            else: # function response logs
                html += f"""
                <div style="display: flex; justify-content: center; margin-bottom: 8px;">
                    <div style="background-color: #fef3c7; color: #d97706; padding: 6px 12px; border-radius: 6px; font-family: sans-serif; font-size: 12px; font-style: italic; box-shadow: 0 1px 2px rgba(0,0,0,0.02);">
                        {formatted_text}
                    </div>
                </div>
                """
        html += "</div>"
        return html

    def action_send_message(self):
        self.ensure_one()
        if not self.user_message or not self.user_message.strip():
            return {
                'type': 'ir.actions.act_window',
                'res_model': self._name,
                'res_id': self.id,
                'view_mode': 'form',
                'target': 'new',
            }

        try:
            history = json.loads(self.conversation_state or '[]')
        except:
            history = []

        history.append({
            "role": "user",
            "parts": [{"text": self.user_message.strip()}]
        })

        self.user_message = ""

        tools = self._get_tools_definition()
        has_new_messages = True
        iterations = 0
        while has_new_messages and iterations < 5:
            iterations += 1
            res_data = self._call_gemini_api(history, tools=tools)

            candidates = res_data.get('candidates', [])
            if not candidates:
                break

            candidate = candidates[0]
            content = candidate.get('content', {})
            parts = content.get('parts', [])

            func_call = None
            for p in parts:
                if 'functionCall' in p:
                    func_call = p['functionCall']
                    break

            if func_call:
                history.append({
                    "role": "model",
                    "parts": parts
                })

                tool_name = func_call.get('name')
                args = func_call.get('args', {})
                tool_res = self._execute_tool(tool_name, args)

                history.append({
                    "role": "function",
                    "parts": [{
                        "functionResponse": {
                            "name": tool_name,
                            "response": tool_res
                        }
                    }]
                })
            else:
                history.append({
                    "role": "model",
                    "parts": parts
                })
                break

        html_content = self._render_conversation_html(history)

        self.write({
            'conversation_state': json.dumps(history),
            'conversation_html': html_content,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Asistente IA - Chat de Consulta'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def action_close_with_summary(self):
        self.ensure_one()
        try:
            history = json.loads(self.conversation_state or '[]')
        except:
            history = []

        if not history:
            return {'type': 'ir.actions.act_window_close'}

        summary_prompt = (
            "Genera un resumen breve en español de las sugerencias y decisiones tomadas en este chat. "
            "DEBES devolver la respuesta EXCLUSIVAMENTE en formato HTML (utilizando etiquetas <ul>, <li>, <strong>, etc.). "
            "No utilices formato Markdown como asteriscos o guiones para las viñetas ni texto entre asteriscos para negritas. "
            "No envuelvas la respuesta en bloques de código (no uses ```html)."
        )

        contents = history + [{
            "role": "user",
            "parts": [{"text": summary_prompt}]
        }]

        try:
            res = self._call_gemini_api(contents)
            summary_text = res['candidates'][0]['content']['parts'][0]['text']
        except Exception:
            summary_text = "Se realizó una consulta al Asistente IA de Posventa."

        # Clean up any ```html or ``` blocks if the model still generated them
        if summary_text.startswith("```html"):
            summary_text = summary_text[7:]
        elif summary_text.startswith("```"):
            summary_text = summary_text[3:]
        if summary_text.endswith("```"):
            summary_text = summary_text[:-3]
        summary_text = summary_text.strip()

        # Robust markdown fallback parser to ensure valid HTML lists/formatting in Odoo chatter
        import re
        summary_text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', summary_text)
        
        # If we see markdown list elements but not HTML <li> tags, convert them
        if '<li>' not in summary_text and ('* ' in summary_text or '- ' in summary_text):
            lines = summary_text.split('\n')
            html_lines = []
            in_list = False
            for line in lines:
                clean_line = line.strip()
                if clean_line.startswith('* ') or clean_line.startswith('- '):
                    if not in_list:
                        html_lines.append('<ul>')
                        in_list = True
                    html_lines.append(f'<li>{clean_line[2:]}</li>')
                else:
                    if in_list:
                        html_lines.append('</ul>')
                        in_list = False
                    html_lines.append(clean_line)
            if in_list:
                html_lines.append('</ul>')
            summary_text = ''.join(html_lines)
        else:
            # If the model returned standard newlines instead of HTML breaks, replace them
            summary_text = summary_text.replace('\n', '<br/>')

        self.ticket_id.message_post(
            body=Markup(f"<h4><b>Resumen de Consulta al Asistente IA:</b></h4><div>{summary_text}</div>"),
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )

        return {'type': 'ir.actions.act_window_close'}

    def action_wizard_enviar_ticket(self):
        self.ensure_one()
        self.ticket_id._action_enviar_ticket_direct()
        return {'type': 'ir.actions.act_window_close'}
