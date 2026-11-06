"""
GestorPyME Pro — Prototipo / MVP de Gestión de Ventas, Inventario y Caducidad.
Desarrollado en Streamlit + HTML/CSS, 100% libre de SQL (persistencia JSON).
Incluye:
  - Conversión automática de Caja / Lote -> Unidades individuales en inventario.
  - Control de peso unitario y peso total en bodega.
  - Seguimiento de caducidad por lotes (FEFO) destacado en la Pestaña Principal.
  - Punto de Venta (Caja) rápido con soporte de ofertas anti-vencimiento.
  - Asistente Comercial con IA Gratuita para compras futuras, ofertas y combos.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
import streamlit as st

from core.ai_assistant import generar_respuesta_asistente
from core.store import (
    ErrorNegocio,
    aplicar_oferta_producto,
    autenticar_usuario,
    obtener_alertas_caducidad,
    obtener_catalogos,
    obtener_historial_movimientos,
    obtener_historial_perdidas,
    obtener_inventario_consolidado,
    obtener_productos_mas_vendidos,
    obtener_promedios_por_categoria,
    obtener_recomendaciones_reabastecimiento,
    obtener_resumen_ejecutivo,
    obtener_serie_ventas_tiempo,
    obtener_ultimas_ventas,
    procesar_venta,
    reabastecer_producto,
    registrar_merma,
    registrar_producto,
    restaurar_datos_demo,
)
from core.ui_components import (
    badge_caducidad,
    badge_estado_stock,
    esc,
    inyectar_estilos,
    moneda,
    render_card_header,
    render_conversion_preview,
    render_grafico_ventas_svg,
    render_kpi_grid,
    render_tabla_caducidad_principal,
    render_tabla_inventario,
    render_tabla_mas_vendidos,
    render_tabla_movimientos,
    render_tabla_perdidas,
    render_tabla_promedios_categoria,
    render_tabla_reabastecimiento,
    render_topbar,
)

st.set_page_config(
    page_title="GestorPyME Pro | Ventas, Inventario y Caducidad",
    page_icon="🏪",
    layout="wide",
    initial_sidebar_state="expanded",
)

inyectar_estilos()


# ============================================================================
# ESTADO DE SESIÓN INICIAL
# ============================================================================

if "usuario" not in st.session_state:
    st.session_state["usuario"] = None

if "carrito" not in st.session_state:
    st.session_state["carrito"] = {}  # {id_producto: cantidad}

if "ultimo_comprobante" not in st.session_state:
    st.session_state["ultimo_comprobante"] = None

if "mensajes_ia" not in st.session_state:
    st.session_state["mensajes_ia"] = [
        {
            "role": "assistant",
            "content": (
                "¡Hola! Soy **AsesorIA PyME** 🤖. Estoy conectado en tiempo real a tu inventario, "
                "ventas históricas y fechas de caducidad.\n\n"
                "Puedo ayudarte a decidir **qué comprar para reabastecer**, **qué ofertas lanzar para "
                "liquidar productos próximos a vencer** o **qué combos armar** para subir tu boleta promedio. "
                "Usa los botones rápidos de arriba o escríbeme tu consulta."
            ),
            "motor": "Sistema Listo",
        }
    ]


# ============================================================================
# VISTA 1: INICIO DE SESIÓN (LOGIN)
# ============================================================================


def vista_login() -> None:
    col_izq, col_centro, col_der = st.columns([1, 1.35, 1])

    with col_centro:
        st.html(
            """
            <div class="login-hero-card">
                <div class="brand-icon">PM</div>
                <h1>GestorPyME Pro</h1>
                <p>Plataforma simple e inteligente para gestionar ventas, stock en unidades y caducidad en PyMEs</p>
            </div>
            """
        )

        with st.container(border=True):
            st.markdown("##### 🔐 Ingreso con Credenciales")
            with st.form("form_login_principal", clear_on_submit=False):
                username = st.text_input(
                    "Nombre de usuario",
                    placeholder="Ej: admin o empleado",
                )
                password = st.text_input(
                    "Contraseña",
                    type="password",
                    placeholder="Ingrese su contraseña",
                )
                submit = st.form_submit_button(
                    "Iniciar Sesión", type="primary", width="stretch"
                )

                if submit:
                    try:
                        usr = autenticar_usuario(username, password)
                        st.session_state["usuario"] = usr
                        st.session_state["carrito"] = {}
                        st.session_state["ultimo_comprobante"] = None
                        st.rerun()
                    except ErrorNegocio as err:
                        st.error(str(err))

            st.divider()
            st.caption("⚡ **Acceso rápido de demostración (Taller de Emprendimiento):**")
            c_demo1, c_demo2 = st.columns(2)
            with c_demo1:
                if st.button(
                    "👨‍💼 Dueño / Admin",
                    width="stretch",
                    help="Usuario: admin | Clave: admin123",
                ):
                    st.session_state["usuario"] = autenticar_usuario("admin", "admin123")
                    st.rerun()
            with c_demo2:
                if st.button(
                    "🛒 Cajero / Ventas",
                    width="stretch",
                    help="Usuario: empleado | Clave: caja123",
                ):
                    st.session_state["usuario"] = autenticar_usuario("empleado", "caja123")
                    st.rerun()

        st.html(
            """
            <div class="card" style="margin-top:0.9rem;padding:1rem 1.2rem;">
                <div style="font-size:0.82rem;color:#475569;line-height:1.55;">
                    <strong>✨ Propuesta de Valor MVP PyME:</strong><br/>
                    &bull; <strong>Conversión automática:</strong> Ingresa por Caja o Lote y controla en Unidades.<br/>
                    &bull; <strong>Cero mermas por descuido:</strong> Alertas tempranas de caducidad y despacho FEFO.<br/>
                    &bull; <strong>Asesor Comercial IA:</strong> Recomendaciones gratuitas de compras y ofertas.
                </div>
            </div>
            """
        )


# ============================================================================
# BARRA LATERAL (SESIÓN Y CONTROLES RÁPIDOS)
# ============================================================================


def render_sidebar(usuario: dict[str, Any]) -> None:
    resumen = obtener_resumen_ejecutivo()
    es_admin = usuario.get("rol") == "Administrador"

    with st.sidebar:
        st.markdown(f"### 🏪 GestorPyME Pro")
        st.caption(f"👤 **{usuario['nombre_completo']}**")
        st.caption(f"🔑 Rol activo: **{usuario['rol']}**")

        st.divider()
        st.markdown("##### 📌 Estado Rápido del Local")
        c1, c2 = st.columns(2)
        c1.metric("Catálogo", f"{resumen['total_productos_activos']} prod.")
        c2.metric("Stock Crítico", f"{resumen['productos_stock_critico']}")

        c3, c4 = st.columns(2)
        c3.metric("Por Vencer (30d)", f"{resumen['productos_proximos_vencer']}")
        c4.metric("Ventas Hoy/Hist.", f"{resumen['total_ventas_completadas']}")

        if resumen["productos_vencidos"] > 0:
            st.error(
                f"🚨 Hay **{resumen['productos_vencidos']}** producto(s) vencido(s) que requieren retiro por Merma."
            )
        elif resumen["productos_caducidad_urgente"] > 0:
            st.warning(
                f"⏰ **{resumen['productos_caducidad_urgente']}** producto(s) vencen en ≤ 7 días."
            )

        if es_admin:
            with st.expander("🛠️ Herramientas de Presentación"):
                st.caption(
                    "Restablece el inventario, fechas de caducidad y ventas de ejemplo para repetir la demo."
                )
                if st.button("🔄 Restaurar Datos Demo", width="stretch"):
                    restaurar_datos_demo()
                    st.session_state["carrito"] = {}
                    st.session_state["ultimo_comprobante"] = None
                    st.toast("Datos de demostración restaurados correctamente.", icon="✅")
                    st.rerun()

        st.divider()
        if st.button("🚪 Cerrar Sesión", width="stretch"):
            st.session_state["usuario"] = None
            st.session_state["carrito"] = {}
            st.session_state["ultimo_comprobante"] = None
            st.rerun()


# ============================================================================
# MÓDULO COMPARTIDO: PUNTO DE VENTA (CAJA)
# ============================================================================


def render_modulo_caja(usuario: dict[str, Any], prefijo_key: str = "pos") -> None:
    catalogos = obtener_catalogos()
    categorias = catalogos["categorias"]
    opciones_cat = {0: "Todas las categorías"}
    for c in categorias:
        opciones_cat[c["id_categoria"]] = c["nombre_categoria"]

    col_catalogo, col_carrito = st.columns([1.45, 1], gap="large")

    # --- COLUMNA IZQUIERDA: CATÁLOGO DE PRODUCTOS ---
    with col_catalogo:
        with st.container(border=True):
            render_card_header(
                "Catálogo de Productos Disponibles",
                "Búsqueda instantánea por nombre o SKU con visibilidad de ofertas y caducidad",
                "Salida automática FEFO",
            )

            f_col1, f_col2 = st.columns([1.6, 1])
            with f_col1:
                busqueda = st.text_input(
                    "Buscar producto",
                    placeholder="Ej: Leche, Arroz, BEB-001...",
                    label_visibility="collapsed",
                    key=f"{prefijo_key}_busq",
                )
            with f_col2:
                id_cat_sel = st.selectbox(
                    "Categoría",
                    options=list(opciones_cat.keys()),
                    format_func=lambda k: opciones_cat[k],
                    label_visibility="collapsed",
                    key=f"{prefijo_key}_cat",
                )

            productos_caja = obtener_inventario_consolidado(
                busqueda=busqueda, id_categoria=id_cat_sel
            )

            if not productos_caja:
                st.info("No se encontraron productos para este criterio.")
            else:
                for prod in productos_caja:
                    idp = prod["id_producto"]
                    stock = prod["stock_actual"]
                    en_carrito = int(st.session_state["carrito"].get(idp, 0))
                    disponible_agregar = max(0, stock - en_carrito)
                    es_vencido = prod["estado_caducidad"] == "VENCIDO"

                    c_info, c_precio, c_accion = st.columns([2.3, 1.15, 0.95])
                    with c_info:
                        etiqueta_oferta = (
                            f' <span class="badge badge-oferta">-{prod["descuento_oferta_pct"]:g}% OFERTA</span>'
                            if prod["descuento_oferta_pct"] > 0
                            else ""
                        )
                        badge_cad = (
                            badge_caducidad(prod["estado_caducidad"], prod["etiqueta_caducidad"])
                            if prod["perecible"]
                            else ""
                        )
                        st.html(
                            f"""
                            <div style="padding:2px 0;">
                                <span class="mono" style="color:#64748b;">{esc(prod["codigo_sku"])}</span>
                                <strong> {esc(prod["nombre_producto"])}</strong>{etiqueta_oferta}
                                <div style="font-size:0.77rem;color:#64748b;margin-top:2px;">
                                    {esc(prod["nombre_categoria"])} &bull; Peso: {esc(prod["peso_unitario_texto"])}
                                    &bull; Stock: <strong>{stock} uds</strong> {badge_cad}
                                </div>
                            </div>
                            """
                        )

                    with c_precio:
                        if prod["descuento_oferta_pct"] > 0:
                            st.html(
                                f"""
                                <div style="text-align:right;padding-top:3px;">
                                    <span style="text-decoration:line-through;color:#94a3b8;font-size:0.78rem;">{esc(moneda(prod["precio_venta"]))}</span><br/>
                                    <strong style="color:#15803d;font-size:0.98rem;">{esc(moneda(prod["precio_efectivo"]))}</strong>
                                </div>
                                """
                            )
                        else:
                            st.html(
                                f"""
                                <div style="text-align:right;padding-top:6px;">
                                    <strong style="font-size:0.96rem;">{esc(moneda(prod["precio_venta"]))}</strong>
                                </div>
                                """
                            )

                    with c_accion:
                        if stock <= 0:
                            st.button(
                                "Agotado",
                                key=f"{prefijo_key}_add_{idp}",
                                disabled=True,
                                width="stretch",
                            )
                        elif es_vencido:
                            st.button(
                                "Vencido ⚠️",
                                key=f"{prefijo_key}_add_{idp}",
                                disabled=True,
                                help="Producto vencido: retírelo en la pestaña de Mermas.",
                                width="stretch",
                            )
                        elif disponible_agregar <= 0:
                            st.button(
                                "Máx. en carro",
                                key=f"{prefijo_key}_add_{idp}",
                                disabled=True,
                                width="stretch",
                            )
                        else:
                            if st.button(
                                "+ Agregar",
                                key=f"{prefijo_key}_add_{idp}",
                                type="primary",
                                width="stretch",
                            ):
                                st.session_state["carrito"][idp] = en_carrito + 1
                                st.session_state["ultimo_comprobante"] = None
                                st.rerun()

                    st.markdown(
                        "<hr style='margin:0.35rem 0;border:none;border-top:1px solid #f1f5f9;'/>",
                        unsafe_allow_html=True,
                    )

    # --- COLUMNA DERECHA: CARRITO DE SALIDA ---
    with col_carrito:
        with st.container(border=True):
            render_card_header(
                "Carrito de Salida (Boleta)",
                "Descuento automático de unidades y priorización de lotes próximos a vencer",
            )

            mapa_inv = {p["id_producto"]: p for p in obtener_inventario_consolidado()}
            carrito_actual: dict[int, int] = st.session_state["carrito"]

            # Limpiar ítems que hayan quedado sin stock
            ids_invalidos = [
                idp
                for idp, c in carrito_actual.items()
                if idp not in mapa_inv or mapa_inv[idp]["stock_actual"] <= 0
            ]
            for id_inv in ids_invalidos:
                carrito_actual.pop(id_inv, None)

            if not carrito_actual:
                st.html(
                    '<div class="empty-state">🛒 El carrito está vacío.<br/>Seleccione productos del catálogo izquierdo.</div>'
                )
            else:
                subtotal_sin_dcto = 0.0
                total_carro = 0.0

                for idp, cant in list(carrito_actual.items()):
                    prod = mapa_inv[idp]
                    max_disp = prod["stock_actual"]
                    if cant > max_disp:
                        cant = max_disp
                        carrito_actual[idp] = cant

                    p_unit = prod["precio_efectivo"]
                    sub_item = round(cant * p_unit, 2)
                    subtotal_sin_dcto += round(cant * prod["precio_venta"], 2)
                    total_carro += sub_item

                    ci1, ci2, ci3, ci4 = st.columns([2.1, 1.25, 1.0, 0.45])
                    with ci1:
                        nota_dcto = (
                            f" (-{prod['descuento_oferta_pct']:g}%)"
                            if prod["descuento_oferta_pct"] > 0
                            else ""
                        )
                        st.markdown(
                            f"**{prod['nombre_producto']}**{nota_dcto}  \n"
                            f"<span style='font-size:0.78rem;color:#64748b;'>{moneda(p_unit)} c/u</span>",
                            unsafe_allow_html=True,
                        )
                    with ci2:
                        b_menos, b_cant, b_mas = st.columns([1, 1, 1])
                        with b_menos:
                            if st.button("−", key=f"{prefijo_key}_dec_{idp}"):
                                if cant > 1:
                                    carrito_actual[idp] = cant - 1
                                else:
                                    carrito_actual.pop(idp, None)
                                st.rerun()
                        with b_cant:
                            st.markdown(
                                f"<div style='text-align:center;padding-top:6px;font-weight:700;'>{cant}</div>",
                                unsafe_allow_html=True,
                            )
                        with b_mas:
                            if st.button(
                                "+",
                                key=f"{prefijo_key}_inc_{idp}",
                                disabled=(cant >= max_disp),
                            ):
                                carrito_actual[idp] = cant + 1
                                st.rerun()
                    with ci3:
                        st.markdown(
                            f"<div style='text-align:right;padding-top:6px;font-weight:700;'>{moneda(sub_item)}</div>",
                            unsafe_allow_html=True,
                        )
                    with ci4:
                        if st.button("✕", key=f"{prefijo_key}_del_{idp}", help="Quitar"):
                            carrito_actual.pop(idp, None)
                            st.rerun()

                st.divider()
                mp_col, dcto_col = st.columns(2)
                with mp_col:
                    metodo_pago = st.selectbox(
                        "Medio de Pago",
                        ["Efectivo", "Tarjeta Débito", "Tarjeta Crédito", "Transferencia"],
                        key=f"{prefijo_key}_mpago",
                    )
                with dcto_col:
                    dcto_caja = st.selectbox(
                        "Descuento especial caja",
                        options=[0, 5, 10, 15, 20],
                        format_func=lambda x: f"{x}% (Sin dcto extra)" if x == 0 else f"-{x}% Promo Caja",
                        key=f"{prefijo_key}_dctocaja",
                    )

                total_con_dcto_caja = round(total_carro * (1.0 - dcto_caja / 100.0), 2)
                ahorro_total = round(max(0.0, subtotal_sin_dcto - total_con_dcto_caja), 2)

                st.html(
                    f"""
                    <div class="cart-total-banner">
                        <div>
                            <div class="total-label">TOTAL A PAGAR ({sum(carrito_actual.values())} uds)</div>
                            <div style="font-size:0.76rem;color:#94a3b8;">
                                {f"Ahorro aplicado en boleta: {moneda(ahorro_total)}" if ahorro_total > 0 else "Precios con IVA incluido"}
                            </div>
                        </div>
                        <div class="total-amount">{esc(moneda(total_con_dcto_caja))}</div>
                    </div>
                    """
                )

                btn_v, btn_ok = st.columns([1, 2])
                with btn_v:
                    if st.button("🗑️ Vaciar", key=f"{prefijo_key}_vaciar", width="stretch"):
                        st.session_state["carrito"] = {}
                        st.rerun()
                with btn_ok:
                    if st.button(
                        "✅ Confirmar Venta",
                        key=f"{prefijo_key}_procesar",
                        type="primary",
                        width="stretch",
                    ):
                        try:
                            payload_items = [
                                {"id_producto": k, "cantidad": v}
                                for k, v in carrito_actual.items()
                            ]
                            comprobante = procesar_venta(
                                items_carrito=payload_items,
                                metodo_pago=metodo_pago,
                                descuento_adicional_pct=float(dcto_caja),
                                usuario=usuario,
                            )
                            st.session_state["carrito"] = {}
                            st.session_state["ultimo_comprobante"] = comprobante
                            st.toast(
                                f"Venta {comprobante['numero_folio']} registrada exitosamente.",
                                icon="🧾",
                            )
                            st.rerun()
                        except ErrorNegocio as err:
                            st.error(str(err))

            if st.session_state.get("ultimo_comprobante"):
                comp = st.session_state["ultimo_comprobante"]
                st.success(
                    f"🧾 **Boleta {comp['numero_folio']} emitida** | "
                    f"Medio: {comp['metodo_pago']} | Total cobrado: **{moneda(comp['total_venta'])}**"
                )

    # --- HISTORIAL DE ÚLTIMAS VENTAS DEL TURNO ---
    st.markdown("")
    filtro_usr = usuario["id_usuario"] if usuario["rol"] == "Empleado" else None
    ultimas = obtener_ultimas_ventas(id_usuario=filtro_usr, limite=8)
    if ultimas:
        filas_v = "".join(
            f"""
            <tr>
                <td class="mono"><strong>{esc(v.get("numero_folio", f"#{v['id_venta']}"))}</strong></td>
                <td class="mono">{esc(v["fecha_venta"])}</td>
                <td>{esc(v.get("metodo_pago", "Efectivo"))}</td>
                <td class="text-center">{v["lineas_distintas"]}</td>
                <td class="text-center"><strong>{v["total_unidades"]} uds</strong></td>
                <td class="text-right"><strong>{esc(moneda(v["total_venta"]))}</strong></td>
                <td class="text-center"><span class="badge badge-venta">{esc(v["estado"])}</span></td>
            </tr>
            """
            for v in ultimas
        )
        st.html(
            f"""
            <div class="card">
                <div class="card-header">
                    <div>
                        <h2>Últimas Ventas Registradas en Caja</h2>
                        <span class="card-subtitle">Comprobación inmediata de boletas emitidas y unidades descontadas</span>
                    </div>
                </div>
                <div class="table-wrapper">
                    <table class="custom-table">
                        <thead>
                            <tr>
                                <th>Folio Boleta</th>
                                <th>Fecha y Hora</th>
                                <th>Medio de Pago</th>
                                <th class="text-center">Líneas</th>
                                <th class="text-center">Unidades</th>
                                <th class="text-right">Total Boleta</th>
                                <th class="text-center">Estado</th>
                            </tr>
                        </thead>
                        <tbody>{filas_v}</tbody>
                    </table>
                </div>
            </div>
            """
        )


# ============================================================================
# VISTA 2: PANEL INTEGRAL DEL DUEÑO / ADMINISTRADOR DE LA PYME
# ============================================================================


def vista_administrador(usuario: dict[str, Any]) -> None:
    render_topbar(usuario)

    (
        tab_inicio,
        tab_caja,
        tab_inventario,
        tab_ingreso,
        tab_analitica,
        tab_ia,
    ) = st.tabs(
        [
            "🏠 Panel Principal",
            "🛒 Punto de Venta (Caja)",
            "📦 Chequeo de Inventario",
            "📥 Ingresar Inventario y Mermas",
            "📊 Analítica e Historial",
            "🤖 Asesor IA Comercial",
        ]
    )

    # ========================================================================
    # PESTAÑA 1: PANEL PRINCIPAL (INGRESOS, KPIs Y LO PRÓXIMO A VENCER)
    # ========================================================================
    with tab_inicio:
        resumen = obtener_resumen_ejecutivo()
        alertas_cad = obtener_alertas_caducidad(dias_umbral=30)

        render_kpi_grid(
            [
                {
                    "etiqueta": "Ingresos por Ventas",
                    "valor": moneda(resumen["ingresos_acumulados"]),
                    "nota": f"{resumen['total_ventas_completadas']} boletas completadas",
                    "acento": "kpi-card-accent-blue",
                },
                {
                    "etiqueta": "Utilidad Neta Estimada",
                    "valor": moneda(resumen["utilidad_estimada_total"]),
                    "nota": "Ganancia descontando costo de compra",
                    "acento": "kpi-card-accent-green",
                    "color": "#15803d",
                },
                {
                    "etiqueta": "Ticket Promedio",
                    "valor": moneda(resumen["ticket_promedio_general"]),
                    "nota": f"Promedio {resumen['promedio_unidades_por_venta']} uds por boleta",
                    "acento": "kpi-card-accent-purple",
                },
                {
                    "etiqueta": "Próximos a Vencer / Vencidos",
                    "valor": f"{resumen['productos_proximos_vencer']} prod.",
                    "nota": f"Capital expuesto: {moneda(resumen['valor_riesgo_caducidad'])}",
                    "acento": "kpi-card-accent-orange",
                    "color": "#c2410c" if resumen["productos_proximos_vencer"] > 0 else "#15803d",
                },
                {
                    "etiqueta": "Alertas de Stock Bajo/Agotado",
                    "valor": f"{resumen['productos_stock_critico']} prod.",
                    "nota": "Requieren compra o reposición",
                    "acento": "kpi-card-accent-red",
                },
                {
                    "etiqueta": "Capital en Bodega (Costo)",
                    "valor": moneda(resumen["valor_bodega_costo"]),
                    "nota": f"Proyección venta: {moneda(resumen['valor_bodega_venta'])}",
                    "acento": "kpi-card-accent-amber",
                },
            ]
        )

        # BLOQUE CENTRAL PRIORITARIO: LO PRÓXIMO A VENCER
        render_tabla_caducidad_principal(alertas_cad)

        # Acción rápida para poner en oferta productos próximos a vencer sin salir del inicio
        candidatos_promo = [
            a for a in alertas_cad if a["estado_caducidad"] in ("URGENTE", "PROXIMO")
        ]
        if candidatos_promo:
            with st.container(border=True):
                st.markdown(
                    "##### 🏷️ Acción Rápida Anti-Merma: Activar Oferta en Productos Próximos a Vencer"
                )
                cp1, cp2, cp3 = st.columns([2.2, 1.1, 1.1])
                mapa_cand = {
                    a["id_producto"]: (
                        f"{a['nombre_producto']} ({a['etiqueta_caducidad']} — {a['stock_actual']} uds — "
                        f"Precio: {moneda(a['precio_venta'])})"
                    )
                    for a in candidatos_promo
                }
                with cp1:
                    id_prod_promo = st.selectbox(
                        "Producto a promocionar",
                        options=list(mapa_cand.keys()),
                        format_func=lambda x: mapa_cand[x],
                        label_visibility="collapsed",
                        key="inicio_promo_prod",
                    )
                prod_sel_obj = next(
                    a for a in candidatos_promo if a["id_producto"] == id_prod_promo
                )
                with cp2:
                    pct_sel = st.selectbox(
                        "Descuento",
                        options=[10, 15, 20, 25, 30, 35, 40, 0],
                        index=[10, 15, 20, 25, 30, 35, 40, 0].index(
                            prod_sel_obj["descuento_sugerido"]
                            if prod_sel_obj["descuento_sugerido"] in (10, 15, 20, 25, 30, 35, 40)
                            else 25
                        ),
                        format_func=lambda p: "Quitar oferta (0%)" if p == 0 else f"Aplicar -{p}% de descuento",
                        label_visibility="collapsed",
                        key="inicio_promo_pct",
                    )
                with cp3:
                    if st.button(
                        "⚡ Aplicar Precio Oferta",
                        type="primary",
                        width="stretch",
                        key="btn_inicio_promo",
                    ):
                        res_of = aplicar_oferta_producto(id_prod_promo, float(pct_sel))
                        if res_of["descuento_oferta_pct"] > 0:
                            st.toast(
                                f"Oferta activa en {res_of['nombre_producto']}: {moneda(res_of['precio_oferta'])} (-{res_of['descuento_oferta_pct']:g}%)",
                                icon="🏷️",
                            )
                        else:
                            st.toast(
                                f"Oferta desactivada para {res_of['nombre_producto']}.",
                                icon="ℹ️",
                            )
                        st.rerun()

        st.markdown("")
        col_graf, col_resumen_lat = st.columns([1.45, 1], gap="large")

        with col_graf:
            with st.container(border=True):
                cg_head, cg_sel = st.columns([1.8, 1])
                with cg_head:
                    st.markdown("##### 📈 Evolución de Ingresos y Ventas")
                    st.caption("Comportamiento temporal continuo del negocio")
                with cg_sel:
                    rango_inicio = st.selectbox(
                        "Período",
                        options=["24h", "7d", "15d", "30d", "todo"],
                        index=2,
                        format_func=lambda r: {
                            "24h": "Últimas 24 horas",
                            "7d": "Últimos 7 días",
                            "15d": "Últimos 15 días",
                            "30d": "Últimos 30 días",
                            "todo": "Todo el historial",
                        }[r],
                        label_visibility="collapsed",
                        key="rango_graf_inicio",
                    )

                datos_serie = obtener_serie_ventas_tiempo(rango_inicio)
                m1, m2, m3 = st.columns(3)
                m1.metric("Ingresos Período", moneda(datos_serie["total_periodo"]))
                m2.metric("Boletas Emitidas", f"{datos_serie['transacciones_periodo']}")
                m3.metric("Unidades Vendidas", f"{datos_serie['unidades_periodo']} uds")
                render_grafico_ventas_svg(datos_serie["serie"], datos_serie["modo"])

        with col_resumen_lat:
            top_5 = obtener_productos_mas_vendidos(limite=5)
            filas_top5 = "".join(
                f"""
                <tr>
                    <td class="text-center"><strong>#{t["ranking"]}</strong></td>
                    <td>
                        <strong>{esc(t["nombre_producto"])}</strong>
                        <div style="font-size:0.74rem;color:#64748b;">Stock: {t["stock_actual"]} uds</div>
                    </td>
                    <td class="text-center">{t["unidades_vendidas"]} uds</td>
                    <td class="text-right" style="color:#15803d;font-weight:700;">{esc(moneda(t["ingresos_generados"]))}</td>
                </tr>
                """
                for t in top_5
            )
            st.html(
                f"""
                <div class="card">
                    <div class="card-header">
                        <div>
                            <h2>🏆 Top 5 Productos Estrella</h2>
                            <span class="card-subtitle">Artículos que generan mayor flujo de caja</span>
                        </div>
                    </div>
                    <div class="table-wrapper">
                        <table class="custom-table">
                            <thead>
                                <tr>
                                    <th class="text-center">#</th>
                                    <th>Producto</th>
                                    <th class="text-center">Vendidos</th>
                                    <th class="text-right">Ingresos</th>
                                </tr>
                            </thead>
                            <tbody>{filas_top5}</tbody>
                        </table>
                    </div>
                </div>
                """
            )

            reab_urg = [
                r
                for r in obtener_recomendaciones_reabastecimiento()
                if "NECESARIO" in r["nivel_alerta"]
            ][:4]
            if reab_urg:
                filas_ru = "".join(
                    f"""
                    <tr>
                        <td><strong>{esc(r["nombre_producto"])}</strong></td>
                        <td class="text-center">{r["stock_actual"]} / {r["stock_minimo"]}</td>
                        <td class="text-center"><span class="badge badge-critico">{esc(r["sugerencia_formato"])}</span></td>
                    </tr>
                    """
                    for r in reab_urg
                )
                st.html(
                    f"""
                    <div class="card">
                        <div class="card-header">
                            <div>
                                <h2>🚨 Reposición Urgente</h2>
                                <span class="card-subtitle">Productos agotados o bajo el mínimo</span>
                            </div>
                        </div>
                        <div class="table-wrapper">
                            <table class="custom-table">
                                <thead>
                                    <tr>
                                        <th>Producto</th>
                                        <th class="text-center">Stock</th>
                                        <th class="text-center">Pedir</th>
                                    </tr>
                                </thead>
                                <tbody>{filas_ru}</tbody>
                            </table>
                        </div>
                    </div>
                    """
                )

    # ========================================================================
    # PESTAÑA 2: PUNTO DE VENTA (CAJA)
    # ========================================================================
    with tab_caja:
        render_modulo_caja(usuario, prefijo_key="admin_pos")

    # ========================================================================
    # PESTAÑA 3: CHEQUEO DE INVENTARIO (UNIDADES CONVERTIDAS, PESO Y CADUCIDAD)
    # ========================================================================
    with tab_inventario:
        catalogos = obtener_catalogos()
        opciones_cat_inv = {0: "Todas las categorías"}
        for c in catalogos["categorias"]:
            opciones_cat_inv[c["id_categoria"]] = c["nombre_categoria"]

        with st.container(border=True):
            fc1, fc2, fc3, fc4 = st.columns([1.5, 1.1, 1.0, 1.15])
            with fc1:
                inv_busq = st.text_input(
                    "Buscar SKU o Nombre",
                    placeholder="Filtrar por nombre o código SKU...",
                    key="inv_filtro_busq",
                )
            with fc2:
                inv_cat = st.selectbox(
                    "Categoría",
                    options=list(opciones_cat_inv.keys()),
                    format_func=lambda k: opciones_cat_inv[k],
                    key="inv_filtro_cat",
                )
            with fc3:
                inv_est = st.selectbox(
                    "Estado de Stock",
                    options=["", "AGOTADO", "CRITICO", "BAJO", "OPTIMO"],
                    format_func=lambda s: "Todos los estados" if s == "" else s,
                    key="inv_filtro_est",
                )
            with fc4:
                inv_cad = st.selectbox(
                    "Estado de Caducidad",
                    options=[
                        "",
                        "ALERTA_CADUCIDAD",
                        "VENCIDO",
                        "URGENTE",
                        "PROXIMO",
                        "VIGENTE",
                        "NO_PERECIBLE",
                    ],
                    format_func=lambda c: {
                        "": "Todas las caducidades",
                        "ALERTA_CADUCIDAD": "⚠️ Con alerta (≤ 30 días o vencido)",
                        "VENCIDO": "🚨 Vencidos",
                        "URGENTE": "⏰ Urgentes (1 a 7 días)",
                        "PROXIMO": "📅 Próximos (8 a 30 días)",
                        "VIGENTE": "✅ Vigentes (> 30 días)",
                        "NO_PERECIBLE": "📦 No perecibles",
                    }[c],
                    key="inv_filtro_cad",
                )

        lista_inv = obtener_inventario_consolidado(
            busqueda=inv_busq,
            id_categoria=inv_cat,
            estado_stock=inv_est,
            filtro_caducidad=inv_cad,
        )

        unidades_bodega = sum(p["stock_actual"] for p in lista_inv)
        costo_inv = sum(p["valor_stock_costo"] for p in lista_inv)
        venta_inv = sum(p["valor_stock_venta"] for p in lista_inv)
        alertas_inv = sum(
            1
            for p in lista_inv
            if p["estado_stock"] in ("AGOTADO", "CRITICO")
            or p["estado_caducidad"] in ("VENCIDO", "URGENTE")
        )

        render_kpi_grid(
            [
                {
                    "etiqueta": "Productos Listados",
                    "valor": str(len(lista_inv)),
                    "nota": "Registros activos según filtro",
                    "acento": "kpi-card-accent-blue",
                },
                {
                    "etiqueta": "Total Unidades Físicas",
                    "valor": f"{unidades_bodega:,}".replace(",", ".") + " uds",
                    "nota": "Cajas y lotes convertidos a unidades",
                    "acento": "kpi-card-accent-purple",
                },
                {
                    "etiqueta": "Valor Inventario (Costo)",
                    "valor": moneda(costo_inv),
                    "nota": "Capital invertido en mercadería",
                    "acento": "kpi-card-accent-amber",
                },
                {
                    "etiqueta": "Retorno Bruto (Venta)",
                    "valor": moneda(venta_inv),
                    "nota": f"Productos en alerta crítica: {alertas_inv}",
                    "acento": "kpi-card-accent-green",
                },
            ]
        )

        render_tabla_inventario(lista_inv)

        if lista_inv:
            col_lotes, col_oferta = st.columns(2, gap="large")
            with col_lotes:
                with st.expander("🔍 Ver Desglose de Lotes y Fechas de Caducidad por Producto"):
                    mapa_p_lote = {
                        p["id_producto"]: f"{p['codigo_sku']} — {p['nombre_producto']} ({p['stock_actual']} uds)"
                        for p in lista_inv
                    }
                    idp_lote = st.selectbox(
                        "Seleccione producto",
                        options=list(mapa_p_lote.keys()),
                        format_func=lambda k: mapa_p_lote[k],
                        key="det_lote_sel",
                    )
                    prod_det = next(p for p in lista_inv if p["id_producto"] == idp_lote)
                    lotes_p = [
                        l for l in prod_det.get("lotes", []) if int(l.get("unidades_restantes", 0)) > 0
                    ]
                    if not lotes_p:
                        st.caption("Este producto no tiene unidades activas en lotes actualmente.")
                    else:
                        for l in lotes_p:
                            st.markdown(
                                f"- **Lote `{l['codigo_lote']}`**: Ingresado como **{l['cantidad_formato']} {l['formato_ingreso']}(s) × {l['unidades_por_formato']}u** "
                                f"→ Quedan **{l['unidades_restantes']} uds** | Vencimiento: **{l.get('fecha_caducidad') or 'No perecible'}**"
                            )

            with col_oferta:
                with st.expander("🏷️ Configurar Descuento / Oferta Comercial a un Producto"):
                    mapa_p_of = {
                        p["id_producto"]: (
                            f"{p['nombre_producto']} (Precio: {moneda(p['precio_venta'])}"
                            + (
                                f" | Oferta actual: -{p['descuento_oferta_pct']:g}%"
                                if p["descuento_oferta_pct"] > 0
                                else ""
                            )
                            + ")"
                        )
                        for p in lista_inv
                    }
                    idp_of = st.selectbox(
                        "Producto",
                        options=list(mapa_p_of.keys()),
                        format_func=lambda k: mapa_p_of[k],
                        key="inv_oferta_prod",
                    )
                    pct_nuevo = st.slider(
                        "Porcentaje de descuento (%)",
                        min_value=0,
                        max_value=60,
                        value=20,
                        step=5,
                        key="inv_oferta_slider",
                    )
                    if st.button("Guardar Descuento en Caja e Inventario", key="btn_inv_oferta"):
                        r_of = aplicar_oferta_producto(idp_of, float(pct_nuevo))
                        st.success(
                            f"Actualizado: **{r_of['nombre_producto']}** ahora se vende a **{moneda(r_of['precio_oferta'])}** (-{r_of['descuento_oferta_pct']:g}%)."
                        )
                        st.rerun()

    # ========================================================================
    # PESTAÑA 4: INGRESAR INVENTARIO (CAJA / LOTE / UNIDAD, PESO, CADUCIDAD) + MERMAS
    # ========================================================================
    with tab_ingreso:
        catalogos = obtener_catalogos()
        mapa_cat_form = {
            c["id_categoria"]: c["nombre_categoria"] for c in catalogos["categorias"]
        }
        mapa_prov_form = {0: "-- Sin proveedor asignado --"}
        for pr in catalogos["proveedores"]:
            mapa_prov_form[pr["id_proveedor"]] = (
                f"{pr['nombre_proveedor']} ({pr['dias_entrega_estimados']}d entrega)"
            )

        col_ingreso_izq, col_merma_der = st.columns([1.38, 1], gap="large")

        # --- COLUMNA IZQUIERDA: INGRESO DE INVENTARIO CON CONVERSIÓN AUTOMÁTICA ---
        with col_ingreso_izq:
            with st.container(border=True):
                modo_operacion = st.radio(
                    "Tipo de Operación de Entrada",
                    options=["NUEVO_PRODUCTO", "ABASTECER_EXISTENTE"],
                    format_func=lambda m: (
                        "➕ Registrar Nuevo Producto"
                        if m == "NUEVO_PRODUCTO"
                        else "📦 Ingresar Stock / Nuevo Lote a Producto Existente"
                    ),
                    horizontal=True,
                    key="modo_ingreso_inv",
                )

                st.divider()

                if modo_operacion == "NUEVO_PRODUCTO":
                    render_card_header(
                        "Alta de Nuevo Producto en Inventario",
                        "Elige ingreso por Unidad, Caja o Lote: el sistema convierte automáticamente a unidades, registra peso y caducidad",
                        "Conversión Automática",
                    )

                    g1, g2 = st.columns(2)
                    with g1:
                        np_sku = st.text_input(
                            "Código SKU *", placeholder="Ej: LAC-015", key="np_sku"
                        )
                        np_cat = st.selectbox(
                            "Categoría *",
                            options=list(mapa_cat_form.keys()),
                            format_func=lambda k: mapa_cat_form[k],
                            key="np_cat",
                        )
                    with g2:
                        np_nombre = st.text_input(
                            "Nombre del Producto *",
                            placeholder="Ej: Leche Semidescremada 1L",
                            key="np_nombre",
                        )
                        np_prov = st.selectbox(
                            "Proveedor Habitual",
                            options=list(mapa_prov_form.keys()),
                            format_func=lambda k: mapa_prov_form[k],
                            key="np_prov",
                        )

                    st.markdown("###### 📦 1. Formato de Ingreso y Conversión a Unidades")
                    f1, f2, f3 = st.columns(3)
                    with f1:
                        np_formato = st.selectbox(
                            "Formato de Ingreso *",
                            options=["CAJA", "LOTE", "UNIDAD"],
                            format_func=lambda f: {
                                "CAJA": "📦 Caja cerrada",
                                "LOTE": "🧱 Lote / Pack mayorista",
                                "UNIDAD": "🔹 Unidad individual (1x1)",
                            }[f],
                            key="np_formato",
                        )
                    with f2:
                        lbl_cant = (
                            "Cantidad de Cajas *"
                            if np_formato == "CAJA"
                            else (
                                "Cantidad de Lotes *"
                                if np_formato == "LOTE"
                                else "Cantidad de Unidades *"
                            )
                        )
                        np_cant_fmt = st.number_input(
                            lbl_cant, min_value=0, max_value=5000, value=3, step=1, key="np_cant_fmt"
                        )
                    with f3:
                        if np_formato == "UNIDAD":
                            np_upf = 1
                            st.text_input(
                                "Unidades por formato",
                                value="1 unidad",
                                disabled=True,
                                key="np_upf_disabled",
                            )
                        else:
                            lbl_upf = (
                                "Unidades por Caja *"
                                if np_formato == "CAJA"
                                else "Unidades por Lote *"
                            )
                            np_upf = st.number_input(
                                lbl_upf,
                                min_value=2,
                                max_value=1000,
                                value=12,
                                step=1,
                                key="np_upf",
                            )

                    st.markdown("###### ⚖️ 2. Peso / Contenido Neto y Fecha de Caducidad")
                    w1, w2, w3 = st.columns([1, 0.85, 1.35])
                    with w1:
                        np_peso_val = st.number_input(
                            "Peso / Contenido por Unidad *",
                            min_value=0.01,
                            max_value=50000.0,
                            value=1.0,
                            step=0.1,
                            key="np_peso_val",
                        )
                    with w2:
                        np_peso_unid = st.selectbox(
                            "Unidad Medida *",
                            options=["kg", "g", "L", "ml"],
                            index=2,
                            key="np_peso_unid",
                        )
                    with w3:
                        np_perecible = st.checkbox(
                            "Producto perecible (tiene fecha de caducidad)",
                            value=True,
                            key="np_perecible",
                        )

                    if np_perecible:
                        cad1, cad2 = st.columns(2)
                        with cad1:
                            np_fecha_cad = st.date_input(
                                "Fecha de Caducidad / Vencimiento *",
                                value=date.today() + timedelta(days=15),
                                key="np_fecha_cad",
                            )
                        with cad2:
                            np_cod_lote = st.text_input(
                                "Código de Lote (Opcional)",
                                placeholder="Autogenerado si se deja vacío",
                                key="np_cod_lote",
                            )
                    else:
                        np_fecha_cad = None
                        np_cod_lote = ""

                    st.markdown("###### 💰 3. Precios y Stock Mínimo de Seguridad")
                    p1, p2, p3, p4 = st.columns([1.25, 1, 1, 1])
                    with p1:
                        if np_formato in ("CAJA", "LOTE"):
                            np_modo_costo = st.selectbox(
                                "Ingreso del Costo",
                                options=["POR_UNIDAD", "POR_FORMATO"],
                                format_func=lambda m: (
                                    "Costo por cada Unidad"
                                    if m == "POR_UNIDAD"
                                    else f"Costo total por {np_formato.title()}"
                                ),
                                key="np_modo_costo",
                            )
                        else:
                            np_modo_costo = "POR_UNIDAD"
                            st.text_input(
                                "Ingreso del Costo",
                                value="Por Unidad",
                                disabled=True,
                                key="np_mc_dis",
                            )
                    with p2:
                        np_costo_raw = st.number_input(
                            "Costo Compra ($) *",
                            min_value=0.0,
                            value=850.0 if np_modo_costo == "POR_UNIDAD" else float(850 * np_upf),
                            step=50.0,
                            key="np_costo_raw",
                        )
                    with p3:
                        np_precio_venta = st.number_input(
                            "Precio Venta Unit. ($) *",
                            min_value=1.0,
                            value=1350.0,
                            step=50.0,
                            key="np_precio_venta",
                        )
                    with p4:
                        np_stock_min = st.number_input(
                            "Alerta Stock Mín. (uds) *",
                            min_value=0,
                            value=8,
                            step=1,
                            key="np_stock_min",
                        )

                    costo_unit_preview = (
                        round(np_costo_raw / max(1, np_upf), 2)
                        if (np_modo_costo == "POR_FORMATO" and np_formato in ("CAJA", "LOTE"))
                        else np_costo_raw
                    )

                    render_conversion_preview(
                        formato=np_formato,
                        cantidad_formato=int(np_cant_fmt),
                        unidades_por_formato=int(np_upf),
                        peso_unitario=float(np_peso_val),
                        unidad_peso=np_peso_unid,
                        costo_unitario=costo_unit_preview,
                    )

                    if st.button(
                        "💾 Registrar Producto y Convertir a Unidades",
                        type="primary",
                        width="stretch",
                        key="btn_guardar_nuevo_prod",
                    ):
                        try:
                            creado = registrar_producto(
                                codigo_sku=np_sku,
                                nombre_producto=np_nombre,
                                id_categoria=int(np_cat),
                                id_proveedor=int(np_prov) if np_prov > 0 else None,
                                formato_ingreso=np_formato,
                                cantidad_formato=int(np_cant_fmt),
                                unidades_por_formato=int(np_upf),
                                modo_costo=np_modo_costo,
                                costo_ingresado=float(np_costo_raw),
                                precio_venta_unitario=float(np_precio_venta),
                                stock_minimo_unidades=int(np_stock_min),
                                peso_unitario=float(np_peso_val),
                                unidad_peso=np_peso_unid,
                                perecible=bool(np_perecible),
                                fecha_caducidad=(
                                    np_fecha_cad.strftime("%Y-%m-%d")
                                    if (np_perecible and np_fecha_cad)
                                    else None
                                ),
                                codigo_lote=np_cod_lote,
                                usuario=usuario,
                            )
                            st.success(
                                f"✅ Producto **{creado['nombre_producto']}** (`{creado['codigo_sku']}`) creado con "
                                f"**{creado['stock_actual']} unidades** en inventario."
                            )
                        except ErrorNegocio as err:
                            st.error(str(err))

                else:
                    # --- ABASTECER PRODUCTO EXISTENTE POR CAJA / LOTE / UNIDAD ---
                    render_card_header(
                        "Abastecer Producto Existente (Por Caja, Lote o Unidad)",
                        "Suma nueva mercadería convirtiendo automáticamente a unidades y registrando la caducidad del nuevo lote",
                        "Control FEFO",
                    )

                    inv_todos = obtener_inventario_consolidado()
                    mapa_prod_ab = {
                        p["id_producto"]: (
                            f"{p['codigo_sku']} — {p['nombre_producto']} "
                            f"(Stock actual: {p['stock_actual']} uds | Peso: {p['peso_unitario_texto']})"
                        )
                        for p in inv_todos
                    }

                    id_ab_prod = st.selectbox(
                        "Seleccione Producto a Abastecer *",
                        options=list(mapa_prod_ab.keys()),
                        format_func=lambda k: mapa_prod_ab[k],
                        key="ab_prod_sel",
                    )
                    prod_ab = next(p for p in inv_todos if p["id_producto"] == id_ab_prod)

                    a1, a2, a3 = st.columns(3)
                    idx_fmt_def = ["CAJA", "LOTE", "UNIDAD"].index(
                        prod_ab["formato_habitual"]
                        if prod_ab["formato_habitual"] in ("CAJA", "LOTE", "UNIDAD")
                        else "CAJA"
                    )
                    with a1:
                        ab_formato = st.selectbox(
                            "Formato que Ingresa *",
                            options=["CAJA", "LOTE", "UNIDAD"],
                            index=idx_fmt_def,
                            format_func=lambda f: {
                                "CAJA": "📦 Caja cerrada",
                                "LOTE": "🧱 Lote / Pack",
                                "UNIDAD": "🔹 Unidades sueltas",
                            }[f],
                            key="ab_formato",
                        )
                    with a2:
                        ab_cant_fmt = st.number_input(
                            f"Cantidad de {ab_formato.title()}(s) *",
                            min_value=1,
                            max_value=5000,
                            value=2,
                            step=1,
                            key="ab_cant_fmt",
                        )
                    with a3:
                        if ab_formato == "UNIDAD":
                            ab_upf = 1
                            st.text_input(
                                "Unidades por formato",
                                value="1 unidad",
                                disabled=True,
                                key="ab_upf_dis",
                            )
                        else:
                            val_upf_def = max(2, int(prod_ab["unidades_por_formato"] or 12))
                            ab_upf = st.number_input(
                                f"Unidades por {ab_formato.title()} *",
                                min_value=2,
                                max_value=1000,
                                value=val_upf_def,
                                step=1,
                                key="ab_upf",
                            )

                    ac1, ac2 = st.columns(2)
                    with ac1:
                        ab_tiene_cad = st.checkbox(
                            "Registrar fecha de caducidad para este ingreso",
                            value=bool(prod_ab["perecible"]),
                            key="ab_tiene_cad",
                        )
                    with ac2:
                        if ab_tiene_cad:
                            ab_fecha_cad = st.date_input(
                                "Fecha de Caducidad del Lote *",
                                value=date.today() + timedelta(days=30),
                                key="ab_fecha_cad",
                            )
                        else:
                            ab_fecha_cad = None

                    ap1, ap2, ap3 = st.columns(3)
                    with ap1:
                        ab_prov = st.selectbox(
                            "Proveedor (Opcional para Factura)",
                            options=list(mapa_prov_form.keys()),
                            index=(
                                list(mapa_prov_form.keys()).index(prod_ab["id_proveedor"])
                                if prod_ab["id_proveedor"] in mapa_prov_form
                                else 0
                            ),
                            format_func=lambda k: mapa_prov_form[k],
                            key="ab_prov",
                        )
                    with ap2:
                        ab_factura = st.text_input(
                            "Nº Factura / Guía (Opcional)",
                            placeholder="Ej: FAC-20910",
                            key="ab_factura",
                        )
                    with ap3:
                        ab_costo_unit = st.number_input(
                            "Costo Unitario Compra ($)",
                            min_value=0.0,
                            value=float(prod_ab["precio_compra"]),
                            step=50.0,
                            key="ab_costo_unit",
                        )

                    render_conversion_preview(
                        formato=ab_formato,
                        cantidad_formato=int(ab_cant_fmt),
                        unidades_por_formato=int(ab_upf),
                        peso_unitario=float(prod_ab["peso_unitario"]),
                        unidad_peso=prod_ab["unidad_peso"],
                        costo_unitario=float(ab_costo_unit),
                    )

                    if st.button(
                        "✅ Confirmar Ingreso y Sumar Unidades al Stock",
                        type="primary",
                        width="stretch",
                        key="btn_confirmar_abastecer",
                    ):
                        try:
                            res_ab = reabastecer_producto(
                                id_producto=id_ab_prod,
                                formato_ingreso=ab_formato,
                                cantidad_formato=int(ab_cant_fmt),
                                unidades_por_formato=int(ab_upf),
                                id_proveedor=int(ab_prov) if ab_prov > 0 else None,
                                numero_factura=ab_factura,
                                modo_costo="POR_UNIDAD",
                                costo_ingresado=float(ab_costo_unit),
                                fecha_caducidad=(
                                    ab_fecha_cad.strftime("%Y-%m-%d")
                                    if (ab_tiene_cad and ab_fecha_cad)
                                    else None
                                ),
                                usuario=usuario,
                            )
                            st.success(
                                f"✅ Se sumaron **+{res_ab['unidades_ingresadas']} unidades** a **{res_ab['nombre_producto']}**. "
                                f"Nuevo stock disponible: **{res_ab['stock_posterior']} uds**."
                            )
                        except ErrorNegocio as err:
                            st.error(str(err))

        # --- COLUMNA DERECHA: REGISTRO DE PÉRDIDAS O BAJAS (MERMA) ---
        with col_merma_der:
            with st.container(border=True):
                render_card_header(
                    "Registrar Pérdida o Baja (Merma)",
                    "Descuenta unidades vencidas, dañadas o faltantes auditando su costo",
                    "Auditoría de Pérdidas",
                    "module-pill-danger",
                )

                inv_merma = obtener_inventario_consolidado()
                if not inv_merma:
                    st.info("No hay productos activos en inventario.")
                else:
                    # Priorizar vencidos arriba para facilitar su retiro en la demo
                    inv_merma_ord = sorted(
                        inv_merma,
                        key=lambda x: (
                            0 if x["estado_caducidad"] == "VENCIDO" else 1,
                            x["nombre_producto"],
                        ),
                    )
                    mapa_m = {
                        p["id_producto"]: (
                            f"{'🚨 [VENCIDO] ' if p['estado_caducidad'] == 'VENCIDO' else ''}"
                            f"{p['codigo_sku']} — {p['nombre_producto']} ({p['stock_actual']} uds)"
                        )
                        for p in inv_merma_ord
                    }
                    id_m_prod = st.selectbox(
                        "Producto Afectado *",
                        options=list(mapa_m.keys()),
                        format_func=lambda k: mapa_m[k],
                        key="merma_prod_sel",
                    )
                    prod_m = next(p for p in inv_merma_ord if p["id_producto"] == id_m_prod)

                    m_causa = st.selectbox(
                        "Motivo de Pérdida *",
                        options=["VENCIMIENTO", "DAÑO", "ROBO", "OTRO"],
                        format_func=lambda c: {
                            "VENCIMIENTO": "⏰ Vencimiento / Producto caducado",
                            "DAÑO": "📦 Daño / Rotura / Deterioro",
                            "ROBO": "🚨 Robo / Hurto / Faltante",
                            "OTRO": "📝 Otra pérdida de inventario",
                        }[c],
                        key="merma_causa_sel",
                    )

                    max_merma = max(0, int(prod_m["stock_actual"]))
                    val_def_m = (
                        max_merma
                        if prod_m["estado_caducidad"] == "VENCIDO" and max_merma > 0
                        else min(1, max_merma)
                    )
                    m_cant = st.number_input(
                        "Unidades a Eliminar del Inventario *",
                        min_value=0,
                        max_value=max(10000, max_merma),
                        value=val_def_m,
                        step=1,
                        key=f"merma_cant_{id_m_prod}",
                    )

                    costo_merma_est = round(m_cant * prod_m["precio_compra"], 2)
                    st.html(
                        f"""
                        <div class="merma-stock-box">
                            <span>Stock actual: <strong>{prod_m["stock_actual"]} uds</strong></span>
                            <span>Pérdida valorizada: <strong style="color:#b91c1c;">{esc(moneda(costo_merma_est))}</strong></span>
                        </div>
                        """
                    )

                    m_obs = st.text_input(
                        "Observación / Detalle (Opcional)",
                        placeholder="Ej: Lote vencido retirado de vitrina refrigerada",
                        key="merma_obs",
                    )
                    m_baja = st.checkbox(
                        "Dar de baja el producto del catálogo activo tras descontar",
                        value=False,
                        key="merma_baja",
                    )

                    if st.button(
                        "🚨 Registrar Pérdida y Descontar Stock",
                        width="stretch",
                        key="btn_guardar_merma",
                    ):
                        try:
                            reg = registrar_merma(
                                id_producto=id_m_prod,
                                causa=m_causa,
                                cantidad=int(m_cant),
                                observacion=m_obs,
                                desactivar_producto=bool(m_baja),
                                usuario=usuario,
                            )
                            st.success(
                                f"Pérdida auditada: **-{reg['cantidad']} uds** de *{reg['nombre_producto']}* "
                                f"({moneda(reg['costo_estimado'])}). Stock restante: **{reg['stock_posterior']} uds**."
                            )
                        except ErrorNegocio as err:
                            st.error(str(err))

    # ========================================================================
    # PESTAÑA 5: ANALÍTICA E HISTORIAL COMPLETO
    # ========================================================================
    with tab_analitica:
        sub_reab, sub_ranking, sub_hist, sub_perd = st.tabs(
            [
                "📦 Cálculo de Reabastecimiento",
                "🏆 Más Vendidos y Categorías",
                "📜 Historial Ventas y Compras",
                "🚨 Historial de Pérdidas",
            ]
        )

        with sub_reab:
            filtro_al = st.selectbox(
                "Filtrar prioridad de compra",
                options=["", "NECESARIO", "RECOMENDADO"],
                format_func=lambda f: {
                    "": "Todos (Necesarios y Recomendados)",
                    "NECESARIO": "Solo NECESARIO (Stock ≤ Mínimo o Agotado)",
                    "RECOMENDADO": "Solo RECOMENDADO (Alta rotación / Preventivo)",
                }[f],
                key="an_filtro_reab",
            )
            datos_reab = obtener_recomendaciones_reabastecimiento(filtro_al)
            render_tabla_reabastecimiento(datos_reab)

        with sub_ranking:
            lim_top = st.selectbox(
                "Mostrar en Ranking",
                options=[5, 10, 25],
                index=1,
                format_func=lambda n: f"Top {n} productos",
                key="an_lim_top",
            )
            render_tabla_mas_vendidos(obtener_productos_mas_vendidos(limite=lim_top))
            render_tabla_promedios_categoria(obtener_promedios_por_categoria())

        with sub_hist:
            hc1, hc2 = st.columns([1, 2])
            with hc1:
                h_tipo = st.selectbox(
                    "Tipo de Movimiento",
                    options=["", "VENTA", "COMPRA"],
                    format_func=lambda t: "Todos (Ventas y Compras)" if t == "" else f"Solo {t}S",
                    key="hist_tipo_sel",
                )
            with hc2:
                h_busq = st.text_input(
                    "Buscar en el historial",
                    placeholder="Buscar por producto, SKU, boleta, factura o responsable...",
                    key="hist_busq_txt",
                )
            render_tabla_movimientos(
                obtener_historial_movimientos(tipo=h_tipo, busqueda=h_busq)
            )

        with sub_perd:
            pc1, pc2 = st.columns([1, 2])
            with pc1:
                p_causa = st.selectbox(
                    "Filtrar por causa",
                    options=["", "VENCIMIENTO", "DAÑO", "ROBO", "OTRO"],
                    format_func=lambda c: "Todas las causas" if c == "" else c,
                    key="perd_causa_sel",
                )
            with pc2:
                p_busq = st.text_input(
                    "Buscar en pérdidas",
                    placeholder="Producto, SKU, observación o responsable...",
                    key="perd_busq_txt",
                )
            datos_perd = obtener_historial_perdidas(causa=p_causa, busqueda=p_busq)
            res_p = datos_perd["resumen"]
            render_kpi_grid(
                [
                    {
                        "etiqueta": "Eventos de Pérdida",
                        "valor": str(res_p["total_eventos"]),
                        "nota": "Registros de merma auditados",
                        "acento": "kpi-card-accent-red",
                    },
                    {
                        "etiqueta": "Unidades Descontadas",
                        "valor": f"{res_p['total_unidades']} uds",
                        "nota": "Artículos dados de baja por merma",
                        "acento": "kpi-card-accent-orange",
                    },
                    {
                        "etiqueta": "Valorización de Pérdidas",
                        "valor": moneda(res_p["costo_total"]),
                        "nota": "Impacto acumulado a precio costo",
                        "acento": "kpi-card-accent-red",
                        "color": "#b91c1c",
                    },
                ]
            )
            render_tabla_perdidas(datos_perd)

    # ========================================================================
    # PESTAÑA 6: ASESOR COMERCIAL CON IA GRATUITA
    # ========================================================================
    with tab_ia:
        st.html(
            """
            <div class="card card-ia">
                <div class="card-header" style="margin-bottom:0.4rem;border-bottom:none;padding-bottom:0;">
                    <div>
                        <h2>🤖 AsesorIA PyME — Recomendaciones de Compras, Ofertas y Ventas</h2>
                        <span class="card-subtitle">
                            Analiza en vivo tus ventas, rotación de 30 días, márgenes y fechas de caducidad para sugerir decisiones rentables
                        </span>
                    </div>
                    <span class="module-pill module-pill-purple">100% Gratuito</span>
                </div>
            </div>
            """
        )

        with st.expander("⚙️ Motor de Inteligencia Artificial (Funciona gratis sin configurar nada)"):
            ia_c1, ia_c2 = st.columns([1.3, 1.7])
            with ia_c1:
                modo_ia = st.selectbox(
                    "Proveedor de IA",
                    options=["AUTO_GRATIS", "LOCAL", "GEMINI", "GROQ"],
                    format_func=lambda m: {
                        "AUTO_GRATIS": "🌐 Automático Gratuito (IA Nube sin Key + Respaldo Local)",
                        "LOCAL": "⚡ Motor Analítico Experto Local (Instantáneo / Offline)",
                        "GEMINI": "✨ Google Gemini 2.5 Flash (API Key gratis AI Studio)",
                        "GROQ": "🚀 Groq Llama 3.3 70B (API Key gratis Groq)",
                    }[m],
                    key="cfg_modo_ia",
                )
            with ia_c2:
                api_key_ia = st.text_input(
                    "API Key opcional (solo si elegiste Gemini o Groq)",
                    type="password",
                    placeholder="No requerida en modo Automático ni Local",
                    key="cfg_apikey_ia",
                )

        st.markdown("###### 💡 Consultas Estratégicas en 1 Clic:")
        q_col1, q_col2, q_col3, q_col4 = st.columns(4)
        pregunta_boton: str | None = None

        with q_col1:
            if st.button("📦 ¿Qué comprar esta semana?", width="stretch"):
                pregunta_boton = (
                    "Según mis ventas y el stock actual, ¿qué productos debo comprar con prioridad esta semana, "
                    "en qué cantidad de cajas/lotes y cuánto presupuesto necesito?"
                )
        with q_col2:
            if st.button("🏷️ Ofertas por caducidad", width="stretch"):
                pregunta_boton = (
                    "Revisa los productos próximos a vencer y dime qué ofertas o porcentajes de descuento exactos "
                    "me recomiendas aplicar hoy para no perder dinero."
                )
        with q_col3:
            if st.button("🤝 Crear packs y combos", width="stretch"):
                pregunta_boton = (
                    "Propón combos o packs combinando mis productos más vendidos con los de menor rotación o próximos "
                    "a vencer para aumentar el ticket promedio."
                )
        with q_col4:
            if st.button("🧹 Limpiar chat", width="stretch"):
                st.session_state["mensajes_ia"] = st.session_state["mensajes_ia"][:1]
                st.rerun()

        contenedor_chat = st.container(border=True)
        with contenedor_chat:
            for msg in st.session_state["mensajes_ia"]:
                avatar = "🤖" if msg["role"] == "assistant" else "🧑‍💼"
                with st.chat_message(msg["role"], avatar=avatar):
                    st.markdown(msg["content"])
                    if msg.get("motor") and msg["role"] == "assistant":
                        st.caption(f"⚙️ Fuente: {msg['motor']}")

        entrada_chat = st.chat_input(
            "Pregúntale a la IA sobre futuras compras, descuentos, caducidad o productos específicos..."
        )
        consulta_final = pregunta_boton or entrada_chat

        if consulta_final:
            st.session_state["mensajes_ia"].append(
                {"role": "user", "content": consulta_final}
            )
            with st.spinner("Analizando inventario, rotación de ventas y caducidades..."):
                texto_ia, fuente_motor = generar_respuesta_asistente(
                    pregunta_usuario=consulta_final,
                    historial_chat=st.session_state["mensajes_ia"][:-1],
                    proveedor_ia=modo_ia,
                    api_key=api_key_ia,
                )
            st.session_state["mensajes_ia"].append(
                {
                    "role": "assistant",
                    "content": texto_ia,
                    "motor": fuente_motor,
                }
            )
            st.rerun()


# ============================================================================
# VISTA 3: PANEL EXCLUSIVO DE EMPLEADO / CAJERO
# ============================================================================


def vista_empleado(usuario: dict[str, Any]) -> None:
    render_topbar(usuario)
    render_modulo_caja(usuario, prefijo_key="emp_pos")


# ============================================================================
# ENRUTADOR PRINCIPAL
# ============================================================================


def main() -> None:
    usuario_actual = st.session_state.get("usuario")
    if not usuario_actual:
        vista_login()
        return

    render_sidebar(usuario_actual)
    if usuario_actual.get("rol") == "Administrador":
        vista_administrador(usuario_actual)
    else:
        vista_empleado(usuario_actual)


if __name__ == "__main__":
    main()
