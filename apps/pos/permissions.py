POS_PERMISSION_DEFINITIONS = (
    ("read", "pos", "Acceder al punto de venta"),
    ("read", "pos.cash_sessions", "Consultar sesiones de caja propias"),
    ("read", "pos.cash_sessions_all", "Auditar todas las sesiones de caja"),
    ("manage", "pos.configuration", "Configurar cajas del punto de venta"),
    ("sell", "pos", "Registrar ventas en el punto de venta"),
    ("sell", "pos.credit", "Registrar ventas a credito en el punto de venta"),
    ("manage", "pos.collections", "Registrar cobranzas de ventas a credito"),
    ("open", "pos.cash", "Abrir sesiones de caja"),
    ("close", "pos.cash", "Cerrar sesiones de caja"),
    ("manage", "pos.cash_movements", "Registrar ingresos y retiros de caja"),
    ("authorize", "pos.cash_movement", "Autorizar retiros y depositos de caja"),
    ("authorize", "pos.cash_difference", "Autorizar diferencias de caja"),
    ("manage", "pos.cash_safe", "Gestionar ingresos y retiros de caja fuerte"),
    ("change", "pos.pricelist", "Cambiar la lista de precios del POS"),
    ("change", "pos.price", "Modificar precios en el POS"),
    ("apply", "pos.discount", "Aplicar descuentos en el POS"),
    ("authorize", "pos.discount", "Autorizar descuentos especiales"),
    ("create", "pos.customer", "Registrar clientes desde el POS"),
    ("create", "pos.product", "Registrar productos desde el POS"),
    ("issue", "pos.invoice", "Emitir comprobantes desde el POS"),
    ("consolidate", "pos.invoice", "Consolidar Notas de Venta en una factura"),
    ("void", "pos.sale", "Anular ventas POS"),
    ("refund", "pos.sale", "Registrar devoluciones POS"),
    ("reprint", "pos.receipt", "Reimprimir tickets POS"),
)


POS_ROLE_ACTIONS = {
    "ADMIN": "*",
    "SUPERUSER": "*",
    "SELLER": {
        "read.pos", "sell.pos", "change.pos.pricelist", "change.pos.price", "apply.pos.discount",
        "create.pos.customer", "create.pos.product", "issue.pos.invoice", "reprint.pos.receipt",
    },
    "CASHIER": {
        "read.pos", "sell.pos", "open.pos.cash", "close.pos.cash",
        "read.pos.cash_sessions",
        "manage.pos.cash_movements", "create.pos.customer", "create.pos.product", "issue.pos.invoice",
        "manage.pos.collections",
        "consolidate.pos.invoice", "reprint.pos.receipt", "change.pos.price",
        "apply.pos.discount",
    },
}
