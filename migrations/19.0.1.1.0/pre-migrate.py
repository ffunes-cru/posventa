# Part of Crucianelli Posventa Module
def migrate(cr, version):
    # El estado 'subiendo' se eliminó: el registro multimedia se crea recién al terminar la subida
    cr.execute("UPDATE pv_ticket_multimedia SET estado_sync = 'procesando' WHERE estado_sync = 'subiendo'")
