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
import hashlib
from typing import Any
import streamlit as st

from core.ai_assistant import generar_respuesta_asistente
from core.vision_scanner import (
    cargar_memoria_visual,
    detectar_producto_en_imagen,
    eliminar_referencia_memoria_visual,
    generar_imagen_referencia_chilena,
    guardar_referencia_memoria_visual,
    obtener_catalogo_chileno_referencia,
    vincular_producto_creado_en_memoria,
)
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
    render_banner_producto_confirmado,
    render_card_header,
    render_conversion_preview,
    render_grafico_ventas_svg,
    render_kpi_grid,
    render_login_hero,
    render_sidebar_brand,
    render_tabla_caducidad_principal,
    render_tabla_inventario,
    render_tabla_mas_vendidos,
    render_tabla_movimientos,
    render_tabla_perdidas,
    render_tabla_promedios_categoria,
    render_tabla_reabastecimiento,
    render_tarjeta_deteccion_ia,
    render_topbar,
)

st.set_page_config(
    page_title="GestorPyME Pro | Ventas, Inventario y Caducidad",
    page_icon=None,
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

if "camara_activa" not in st.session_state:
    st.session_state["camara_activa"] = False

if "scanner_estado" not in st.session_state:
    st.session_state["scanner_estado"] = "SIN_CAPTURA"
    # Estados: SIN_CAPTURA -> ESPERANDO_CONFIRMACION -> CORRIGIENDO_PRODUCTO -> CONFIRMADO_INGRESAR_CANTIDAD

if "scanner_deteccion" not in st.session_state:
    st.session_state["scanner_deteccion"] = None

if "scanner_last_img_hash" not in st.session_state:
    st.session_state["scanner_last_img_hash"] = None

if "scanner_mensaje_exito" not in st.session_state:
    st.session_state["scanner_mensaje_exito"] = None

if "scanner_cam_nonce" not in st.session_state:
    st.session_state["scanner_cam_nonce"] = 0

if "scanner_simulada_bytes" not in st.session_state:
    st.session_state["scanner_simulada_bytes"] = None

if "flash_ingreso" not in st.session_state:
    st.session_state["flash_ingreso"] = None

if "flash_merma" not in st.session_state:
    st.session_state["flash_merma"] = None

if "nav_admin" not in st.session_state:
    st.session_state["nav_admin"] = "Resumen Ejecutivo"

if "mensajes_ia" not in st.session_state:
    st.session_state["mensajes_ia"] = [
        {
            "role": "assistant",
            "content": (
                "Hola, soy **AsesorIA PyME**. Estoy conectado en tiempo real a tu inventario, "
                "ventas y fechas de caducidad. Pregúntame qué comprar, qué ofertas activar o cómo armar combos."
            ),
            "motor": "Sistema Listo",
        }
    ]


# ============================================================================
# VISTA 1: INICIO DE SESIÓN (LOGIN)
# ============================================================================


def vista_login() -> None:
    col_izq, col_centro, col_der = st.columns([1.05, 1.25, 1.05])

    with col_centro:
        render_login_hero()

        with st.container(border=True):
            st.markdown("##### Acceso a la Plataforma")
            with st.form("form_login_principal", clear_on_submit=False):
                username = st.text_input(
                    "Usuario",
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
            st.caption("Acceso rápido de demostración")
            c_demo1, c_demo2 = st.columns(2)
            with c_demo1:
                if st.button(
                    "Dueño / Administrador",
                    width="stretch",
                    help="Usuario: admin | Clave: admin123",
                ):
                    st.session_state["usuario"] = autenticar_usuario("admin", "admin123")
                    st.rerun()
            with c_demo2:
                if st.button(
                    "Cajero / Punto de Venta",
                    width="stretch",
                    help="Usuario: empleado | Clave: caja123",
                ):
                    st.session_state["usuario"] = autenticar_usuario("empleado", "caja123")
                    st.rerun()

        st.html(
            """
            <div class="card" style="margin-top:0.85rem;padding:0.95rem 1.2rem;border-left:4px solid #1d4ed8;">
                <div style="font-size:0.81rem;color:#475569;line-height:1.6;">
                    <strong style="color:#0f172a;">Capacidades Clave</strong><br/>
                    &bull; <strong>Conversión automática:</strong> Ingresa por Caja o Lote y controla en Unidades.<br/>
                    &bull; <strong>Control FEFO:</strong> Alertas tempranas de caducidad y mermas valorizadas.<br/>
                    &bull; <strong>Visión IA + Asesor:</strong> Escaneo con cámara OCR y chat asistente flotante.
                </div>
            </div>
            """
        )


# ============================================================================
# BARRA LATERAL (NAVEGACIÓN SAAS Y ESTADO DEL LOCAL)
# ============================================================================


def render_sidebar(usuario: dict[str, Any]) -> None:
    resumen = obtener_resumen_ejecutivo()
    es_admin = usuario.get("rol") == "Administrador"

    with st.sidebar:
        render_sidebar_brand()

        if es_admin:
            st.html('<div class="sidebar-section-label">Módulos</div>')
            with st.container(key="sidebar_nav"):
                st.radio(
                    "Módulos",
                    options=[
                        "Resumen Ejecutivo",
                        "Punto de Venta (Caja)",
                        "Inventario y Catálogo",
                        "Recepción y Escáner IA",
                        "Analítica e Historial",
                    ],
                    key="nav_admin",
                    label_visibility="collapsed",
                )
            st.divider()

        st.html('<div class="sidebar-section-label">Estado del Local</div>')
        c1, c2 = st.columns(2)
        c1.metric("Catálogo", f"{resumen['total_productos_activos']}")
        c2.metric("Stock Crítico", f"{resumen['productos_stock_critico']}")

        c3, c4 = st.columns(2)
        c3.metric("Por Vencer", f"{resumen['productos_proximos_vencer']}")
        c4.metric("Boletas", f"{resumen['total_ventas_completadas']}")

        if resumen["productos_vencidos"] > 0:
            st.error(
                f"Hay {resumen['productos_vencidos']} producto(s) vencido(s) por retirar."
            )
        elif resumen["productos_caducidad_urgente"] > 0:
            st.warning(
                f"{resumen['productos_caducidad_urgente']} producto(s) vencen en ≤ 7 días."
            )

        if es_admin:
            with st.expander("Herramientas de Demo"):
                st.caption(
                    "Restablece inventario, caducidades y ventas iniciales de prueba."
                )
                if st.button("Restaurar Datos Demo", width="stretch"):
                    restaurar_datos_demo()
                    st.session_state["carrito"] = {}
                    st.session_state["ultimo_comprobante"] = None
                    st.toast("Datos de demostración restaurados.", icon=None)
                    st.rerun()

        st.divider()
        st.caption(f"Sesión: **{usuario['nombre_completo']}** ({usuario['rol']})")
        if st.button("Cerrar Sesión", width="stretch"):
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
                                "Vencido",
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
                    '<div class="empty-state">El carrito está vacío.<br/>Seleccione productos del catálogo izquierdo.</div>'
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
                        if st.button("", key=f"{prefijo_key}_del_{idp}", help="Quitar"):
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
                    if st.button("Vaciar", key=f"{prefijo_key}_vaciar", width="stretch"):
                        st.session_state["carrito"] = {}
                        st.rerun()
                with btn_ok:
                    if st.button(
                        "Confirmar Venta",
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
                                icon=None,
                            )
                            st.rerun()
                        except ErrorNegocio as err:
                            st.error(str(err))

            if st.session_state.get("ultimo_comprobante"):
                comp = st.session_state["ultimo_comprobante"]
                st.success(
                    f"**Boleta {comp['numero_folio']} emitida** | "
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
# MÓDULO DE ESCANEO DE PRODUCTOS CON CÁMARA E IA (CONFIRMACIÓN DEL OPERARIO)
# ============================================================================


def render_bloque_escaner_camara(
    usuario: dict[str, Any],
    mapa_cat_form: dict[int, str],
    mapa_prov_form: dict[int, str],
) -> None:
    """
    Gestiona el flujo completo de escaneo por cámara:
      1. Botón para activar/desactivar la cámara.
      2. Captura de foto y detección automática del objeto con IA de Visión.
      3. Pregunta al operario para confirmar si el objeto en pantalla es el que cree la IA
         (o corregirlo si corresponde a otro).
      4. Una vez confirmado, ingreso de cantidad en Lote, Caja o Unidades con conversión automática.
    """
    if st.session_state.get("scanner_mensaje_exito"):
        st.success(st.session_state["scanner_mensaje_exito"])

    if not st.session_state.get("camara_activa", False):
        with st.container(border=True):
            c_txt, c_btn = st.columns([1.85, 1.15])
            with c_txt:
                st.markdown(
                    "**Escáner Inteligente con Cámara e IA**  \n"
                    "<span style='font-size:0.82rem;color:#475569;'>"
                    "Activa la cámara para que la IA reconozca el producto, confirma en pantalla "
                    "y luego ingresa la cantidad en Lote, Caja o Unidades."
                    "</span>",
                    unsafe_allow_html=True,
                )
            with c_btn:
                if st.button(
                    "Activar Cámara con IA",
                    type="primary",
                    width="stretch",
                    key="btn_activar_camara_ia",
                ):
                    st.session_state["camara_activa"] = True
                    st.session_state["scanner_mensaje_exito"] = None
                    st.rerun()
        return

    # --- PANEL CON CÁMARA ACTIVA ---
    with st.container(border=True):
        h_izq, h_der = st.columns([2.2, 0.9])
        with h_izq:
            render_card_header(
                "Escáner Inteligente con Cámara e IA",
                "1. Captura el producto  •  2. Confirma la detección  •  3. Ingresa Lote, Caja o Unidades",
                "Visión IA + OCR",
                "module-pill-purple",
            )
        with h_der:
            if st.button(
                "Cerrar Cámara",
                width="stretch",
                key="btn_cerrar_camara_ia",
            ):
                st.session_state["camara_activa"] = False
                st.session_state["scanner_estado"] = "SIN_CAPTURA"
                st.session_state["scanner_deteccion"] = None
                st.session_state["scanner_last_img_hash"] = None
                st.session_state["scanner_simulada_bytes"] = None
                st.session_state["scanner_cam_nonce"] = st.session_state.get("scanner_cam_nonce", 0) + 1
                st.rerun()

        nonce = st.session_state.get("scanner_cam_nonce", 0)

        foto_camara = st.camera_input(
            "Apunta la cámara al producto y presiona 'Take Photo' para que la IA detecte el objeto",
            key=f"widget_camara_ia_{nonce}",
        )

        catalogo_chileno = obtener_catalogo_chileno_referencia()
        with st.expander("¿Sin cámara web o deseas probar con la Base Precargada del Mercado Chileno?"):
            cf_up, cf_ch = st.columns([1.15, 1.35])
            with cf_up:
                foto_archivo = st.file_uploader(
                    "Subir fotografía de producto (JPG/PNG)",
                    type=["jpg", "jpeg", "png", "webp"],
                    key=f"widget_archivo_ia_{nonce}",
                )
            with cf_ch:
                opciones_sim = {
                    i: f"🇨🇱 {item['marca']} — {item['nombre']}"
                    for i, item in enumerate(catalogo_chileno)
                }
                idx_sim = st.selectbox(
                    "O probar con referencia chilena precargada",
                    options=list(opciones_sim.keys()),
                    format_func=lambda k: opciones_sim[k],
                    key="sel_sim_chileno",
                )
                if st.button(
                    "Cargar Referencia Chilena en el Escáner",
                    width="stretch",
                    key="btn_cargar_ref_chilena",
                ):
                    item_sim = catalogo_chileno[idx_sim]
                    img_sim_bytes = generar_imagen_referencia_chilena(item_sim)
                    st.session_state["scanner_simulada_bytes"] = img_sim_bytes
                    st.session_state["scanner_last_img_bytes"] = img_sim_bytes
                    st.session_state["scanner_last_img_hash"] = hashlib.md5(img_sim_bytes).hexdigest()
                    st.session_state["scanner_deteccion"] = detectar_producto_en_imagen(
                        img_sim_bytes,
                        api_key_gemini=st.session_state.get("cfg_apikey_ia", ""),
                    )
                    st.session_state["scanner_estado"] = "ESPERANDO_CONFIRMACION"
                    st.session_state["scanner_mensaje_exito"] = None
                    st.rerun()

        referencias_mem = cargar_memoria_visual()
        refs_op = [r for r in referencias_mem if r.get("origen") != "BASE_CHILENA_PRECARGADA"]
        refs_ch = [r for r in referencias_mem if r.get("origen") == "BASE_CHILENA_PRECARGADA"]

        with st.expander(
            f"Base de Imágenes de Referencia ({len(refs_op)} aprendida(s) del operario + {len(refs_ch)} precargadas del mercado chileno)"
        ):
            tab_mem_op, tab_mem_ch = st.tabs(
                [
                    f"Aprendidas del Operario ({len(refs_op)})",
                    f"🇨🇱 Base Precargada Mercado Chileno ({len(refs_ch)})",
                ]
            )
            with tab_mem_op:
                if not refs_op:
                    st.caption(
                        "Cuando corrijas o confirmes una foto tomada con tu cámara, se guardará aquí para que la IA la recuerde siempre."
                    )
                else:
                    for ref in refs_op[:10]:
                        cr_img, cr_info, cr_del = st.columns([0.65, 2.5, 0.7])
                        with cr_img:
                            b64_t = ref.get("huella", {}).get("miniatura_b64", "")
                            if b64_t:
                                st.html(
                                    f'<img src="data:image/jpeg;base64,{b64_t}" '
                                    f'style="width:72px;height:52px;object-fit:cover;border-radius:6px;border:1px solid #cbd5e1;" />'
                                )
                        with cr_info:
                            origen_lbl = (
                                "Enseñada por corrección del operario"
                                if ref.get("origen") == "CORRECCION_OPERARIO"
                                else "Confirmada por operario"
                            )
                            st.markdown(
                                f"**`{ref.get('codigo_sku', '')}` — {ref.get('nombre_producto', '')}**  \n"
                                f"<span style='font-size:0.76rem;color:#64748b;'>"
                                f"{origen_lbl} &bull; Guardada: {ref.get('fecha_aprendizaje', '')}"
                                f"</span>",
                                unsafe_allow_html=True,
                            )
                        with cr_del:
                            if st.button(
                                "Olvidar",
                                key=f"del_mem_ref_{ref.get('id_referencia')}",
                                width="stretch",
                            ):
                                eliminar_referencia_memoria_visual(int(ref["id_referencia"]))
                                st.session_state["scanner_last_img_hash"] = None
                                st.toast("Referencia eliminada en tiempo real.", icon=None)
                                st.rerun()

            with tab_mem_ch:
                st.caption(
                    "Base permanente de productos comunes en almacenes y minimarkets chilenos usada como referencia visual y de marcas (OCR):"
                )
                cols_ch = st.columns(3)
                for idx_c, ref_c in enumerate(refs_ch[:18]):
                    with cols_ch[idx_c % 3]:
                        b64_c = ref_c.get("huella", {}).get("miniatura_b64", "")
                        img_tag = (
                            f'<img src="data:image/jpeg;base64,{b64_c}" '
                            f'style="width:52px;height:38px;object-fit:cover;border-radius:4px;border:1px solid #cbd5e1;flex-shrink:0;" />'
                            if b64_c
                            else ""
                        )
                        st.html(
                            f"""
                            <div style="display:flex;align-items:center;gap:0.5rem;padding:0.35rem;border:1px solid #e2e8f0;border-radius:6px;margin-bottom:0.35rem;background:#f8fafc;">
                                {img_tag}
                                <div style="font-size:0.75rem;line-height:1.25;">
                                    <strong>{esc(ref_c.get("nombre_producto", ""))}</strong><br/>
                                    <span style="color:#64748b;">{esc(ref_c.get("nombre_categoria", ""))}</span>
                                </div>
                            </div>
                            """
                        )

        archivo_activo = foto_camara if foto_camara is not None else foto_archivo

        if archivo_activo is not None:
            bytes_img = archivo_activo.getvalue()
            st.session_state["scanner_simulada_bytes"] = None
            st.session_state["scanner_last_img_bytes"] = bytes_img
            hash_actual = hashlib.md5(bytes_img).hexdigest()

            if hash_actual != st.session_state.get("scanner_last_img_hash"):
                with st.spinner("Analizando objeto en pantalla (Memoria Visual + Base Chilena + OCR)..."):
                    det = detectar_producto_en_imagen(
                        bytes_img,
                        api_key_gemini=st.session_state.get("cfg_apikey_ia", ""),
                    )
                st.session_state["scanner_deteccion"] = det
                st.session_state["scanner_last_img_hash"] = hash_actual
                st.session_state["scanner_estado"] = "ESPERANDO_CONFIRMACION"
                st.session_state["scanner_mensaje_exito"] = None
        elif st.session_state.get("scanner_simulada_bytes") is not None:
            bytes_img = st.session_state["scanner_simulada_bytes"]
            st.session_state["scanner_last_img_bytes"] = bytes_img
        else:
            if st.session_state.get("scanner_estado") != "CONFIRMADO_INGRESAR_CANTIDAD":
                st.session_state["scanner_estado"] = "SIN_CAPTURA"
                st.session_state["scanner_deteccion"] = None
                st.session_state["scanner_last_img_hash"] = None
                st.session_state["scanner_last_img_bytes"] = None

        det_actual = st.session_state.get("scanner_deteccion")
        estado_scan = st.session_state.get("scanner_estado", "SIN_CAPTURA")
        img_bytes_guardados = st.session_state.get("scanner_last_img_bytes")

        if not det_actual or estado_scan == "SIN_CAPTURA":
            st.caption(
                "Captura una imagen con la cámara superior (o elige una referencia chilena en el desplegable) para que la IA identifique el producto."
            )
            return

        # ====================================================================
        # PASO 2: PREGUNTAR AL OPERARIO SI EL OBJETO EN PANTALLA ES EL CORRECTO
        # ====================================================================
        if estado_scan == "ESPERANDO_CONFIRMACION":
            render_tarjeta_deteccion_ia(det_actual)

            b_si, b_no = st.columns([1.3, 1.1])
            with b_si:
                if st.button(
                    f"Sí, confirmar que es «{det_actual['nombre_detectado']}»",
                    type="primary",
                    width="stretch",
                    key="btn_operario_confirma_si",
                ):
                    if img_bytes_guardados:
                        guardar_referencia_memoria_visual(
                            img_bytes_guardados,
                            det_actual,
                            origen="CONFIRMACION_OPERARIO",
                        )
                    st.session_state["scanner_estado"] = "CONFIRMADO_INGRESAR_CANTIDAD"
                    st.rerun()
            with b_no:
                if st.button(
                    "No es este, corregir y guardar en Memoria Visual",
                    width="stretch",
                    key="btn_operario_confirma_no",
                ):
                    st.session_state["scanner_estado"] = "CORRIGIENDO_PRODUCTO"
                    st.rerun()

        # ====================================================================
        # PASO 2B: CORRECCIÓN MANUAL Y APRENDIZAJE EN MEMORIA VISUAL
        # ====================================================================
        elif estado_scan == "CORRIGIENDO_PRODUCTO":
            st.warning(
                "**Enseñar a la IA (Corrección del Operario):** Indica cuál es realmente el producto en pantalla. "
                "La imagen se guardará en tiempo real en la **Memoria Visual** para recordarlo siempre en futuros escaneos."
            )
            tipo_corr = st.radio(
                "¿Dónde quieres elegir el producto correcto?",
                options=["EXISTENTE", "BASE_CHILENA", "NUEVO"],
                format_func=lambda t: {
                    "EXISTENTE": "Producto actual de mi Inventario",
                    "BASE_CHILENA": f"🇨🇱 Elegir de la Base de Productos del Mercado Chileno ({len(catalogo_chileno)} precargados)",
                    "NUEVO": "Escribir otro producto nuevo personalizado",
                }[t],
                horizontal=True,
                key="scan_corr_tipo",
            )

            inv_disp = obtener_inventario_consolidado()
            if tipo_corr == "EXISTENTE" and inv_disp:
                mapa_corr = {
                    p["id_producto"]: f"{p['codigo_sku']} — {p['nombre_producto']} (Stock: {p['stock_actual']} uds)"
                    for p in inv_disp
                }
                id_elegido = st.selectbox(
                    "Selecciona el producto correcto de tu inventario *",
                    options=list(mapa_corr.keys()),
                    format_func=lambda k: mapa_corr[k],
                    key="scan_corr_prod_id",
                )
                prod_elegido = next(p for p in inv_disp if p["id_producto"] == id_elegido)

                c_ok, c_back = st.columns(2)
                with c_ok:
                    if st.button(
                        "Guardar en Memoria Visual y Pasar a Cantidad",
                        type="primary",
                        width="stretch",
                        key="btn_guardar_corr_exist",
                    ):
                        nueva_det = {
                            "es_existente": True,
                            "id_producto": prod_elegido["id_producto"],
                            "codigo_sku": prod_elegido["codigo_sku"],
                            "nombre_detectado": prod_elegido["nombre_producto"],
                            "nombre_categoria": prod_elegido["nombre_categoria"],
                            "id_categoria": prod_elegido["id_categoria"],
                            "stock_actual": prod_elegido["stock_actual"],
                            "formato_sugerido": prod_elegido["formato_habitual"],
                            "unidades_por_formato_sugeridas": prod_elegido["unidades_por_formato"],
                            "peso_sugerido": prod_elegido["peso_unitario"],
                            "unidad_peso_sugerida": prod_elegido["unidad_peso"],
                            "precio_compra_sugerido": prod_elegido["precio_compra"],
                            "precio_venta_sugerido": prod_elegido["precio_venta"],
                            "perecible_sugerido": prod_elegido["perecible"],
                            "confianza_pct": 100,
                            "descripcion_visual": "Aprendido en tiempo real por corrección del operario",
                            "motor_vision": "Memoria Visual Aprendida",
                            "recordado_de_memoria": True,
                        }
                        if img_bytes_guardados:
                            guardar_referencia_memoria_visual(
                                img_bytes_guardados,
                                nueva_det,
                                origen="CORRECCION_OPERARIO",
                            )
                            st.toast(
                                f"¡Imagen aprendida! La IA recordará «{prod_elegido['nombre_producto']}» en futuros escaneos.",
                                icon=None,
                            )
                        st.session_state["scanner_deteccion"] = nueva_det
                        st.session_state["scanner_estado"] = "CONFIRMADO_INGRESAR_CANTIDAD"
                        st.rerun()
                with c_back:
                    if st.button("↩️ Volver", width="stretch", key="btn_volver_corr_1"):
                        st.session_state["scanner_estado"] = "ESPERANDO_CONFIRMACION"
                        st.rerun()

            elif tipo_corr == "BASE_CHILENA":
                mapa_ch = {
                    i: (
                        f"🇨🇱 {item['marca']} — {item['nombre']} "
                        f"({item['formato']} ×{item['upf']}u | Venta sug.: {moneda(item['venta'])})"
                    )
                    for i, item in enumerate(catalogo_chileno)
                }
                idx_ch_sel = st.selectbox(
                    "Selecciona el producto común del mercado chileno *",
                    options=list(mapa_ch.keys()),
                    format_func=lambda k: mapa_ch[k],
                    key="scan_corr_chileno_idx",
                )
                item_ch_sel = catalogo_chileno[idx_ch_sel]

                c_ok_ch, c_back_ch = st.columns(2)
                with c_ok_ch:
                    if st.button(
                        "Guardar Referencia Chilena en Memoria Visual y Pasar a Cantidad",
                        type="primary",
                        width="stretch",
                        key="btn_guardar_corr_chileno",
                    ):
                        # Verificar si ya existe en el inventario activo
                        match_inv = next(
                            (
                                p
                                for p in inv_disp
                                if (
                                    item_ch_sel.get("sku_tienda")
                                    and p["codigo_sku"].upper() == item_ch_sel["sku_tienda"].upper()
                                )
                                or p["nombre_producto"].strip().lower()
                                == item_ch_sel["nombre"].strip().lower()
                            ),
                            None,
                        )
                        if match_inv is not None:
                            nueva_det = {
                                "es_existente": True,
                                "id_producto": match_inv["id_producto"],
                                "codigo_sku": match_inv["codigo_sku"],
                                "nombre_detectado": match_inv["nombre_producto"],
                                "nombre_categoria": match_inv["nombre_categoria"],
                                "id_categoria": match_inv["id_categoria"],
                                "stock_actual": match_inv["stock_actual"],
                                "formato_sugerido": match_inv["formato_habitual"],
                                "unidades_por_formato_sugeridas": match_inv["unidades_por_formato"],
                                "peso_sugerido": match_inv["peso_unitario"],
                                "unidad_peso_sugerida": match_inv["unidad_peso"],
                                "precio_compra_sugerido": match_inv["precio_compra"],
                                "precio_venta_sugerido": match_inv["precio_venta"],
                                "perecible_sugerido": match_inv["perecible"],
                                "confianza_pct": 100,
                                "descripcion_visual": "Vinculado con Base del Mercado Chileno y aprendido en Memoria Visual",
                                "motor_vision": "Memoria Visual Aprendida",
                                "recordado_de_memoria": True,
                            }
                        else:
                            nueva_det = {
                                "es_existente": False,
                                "id_producto": None,
                                "codigo_sku": item_ch_sel["sku_ref"],
                                "nombre_detectado": item_ch_sel["nombre"],
                                "nombre_categoria": mapa_cat_form.get(
                                    item_ch_sel["id_categoria"], "General"
                                ),
                                "id_categoria": item_ch_sel["id_categoria"],
                                "stock_actual": 0,
                                "formato_sugerido": item_ch_sel["formato"],
                                "unidades_por_formato_sugeridas": item_ch_sel["upf"],
                                "peso_sugerido": item_ch_sel["peso"],
                                "unidad_peso_sugerida": item_ch_sel["unidad_peso"],
                                "precio_compra_sugerido": item_ch_sel["compra"],
                                "precio_venta_sugerido": item_ch_sel["venta"],
                                "perecible_sugerido": item_ch_sel["perecible"],
                                "confianza_pct": 100,
                                "descripcion_visual": "Aprendido desde Base del Mercado Chileno por corrección del operario",
                                "motor_vision": "Memoria Visual Aprendida",
                                "recordado_de_memoria": True,
                            }

                        if img_bytes_guardados:
                            guardar_referencia_memoria_visual(
                                img_bytes_guardados,
                                nueva_det,
                                origen="CORRECCION_OPERARIO",
                            )
                            st.toast(
                                f"¡Aprendido en tiempo real! La IA recordará «{nueva_det['nombre_detectado']}».",
                                icon=None,
                            )
                        st.session_state["scanner_deteccion"] = nueva_det
                        st.session_state["scanner_estado"] = "CONFIRMADO_INGRESAR_CANTIDAD"
                        st.rerun()
                with c_back_ch:
                    if st.button("↩️ Volver", width="stretch", key="btn_volver_corr_ch"):
                        st.session_state["scanner_estado"] = "ESPERANDO_CONFIRMACION"
                        st.rerun()

            else:
                cn1, cn2 = st.columns(2)
                with cn1:
                    corr_nombre = st.text_input(
                        "Nombre real del producto *",
                        value=det_actual.get("nombre_detectado", ""),
                        placeholder="Ej: Galletas McKay Kuky ChipChipers Blanco 120g",
                        key="scan_corr_nuevo_nom",
                    )
                with cn2:
                    corr_cat = st.selectbox(
                        "Categoría *",
                        options=list(mapa_cat_form.keys()),
                        format_func=lambda k: mapa_cat_form[k],
                        key="scan_corr_nuevo_cat",
                    )
                c_ok2, c_back2 = st.columns(2)
                with c_ok2:
                    if st.button(
                        "Guardar Nuevo Producto en Memoria Visual y Pasar a Cantidad",
                        type="primary",
                        width="stretch",
                        key="btn_guardar_corr_nuevo",
                    ):
                        pref = mapa_cat_form[corr_cat][:3].upper()
                        det_actual["es_existente"] = False
                        det_actual["id_producto"] = None
                        det_actual["codigo_sku"] = f"{pref}-{len(inv_disp) + 15:03d}"
                        det_actual["nombre_detectado"] = corr_nombre.strip() or "Producto Escaneado"
                        det_actual["id_categoria"] = int(corr_cat)
                        det_actual["nombre_categoria"] = mapa_cat_form[corr_cat]
                        det_actual["confianza_pct"] = 100
                        det_actual["descripcion_visual"] = (
                            "Aprendido y guardado en Memoria Visual por corrección del operario"
                        )
                        det_actual["motor_vision"] = "Memoria Visual Aprendida"
                        det_actual["recordado_de_memoria"] = True

                        if img_bytes_guardados:
                            guardar_referencia_memoria_visual(
                                img_bytes_guardados,
                                det_actual,
                                origen="CORRECCION_OPERARIO",
                            )
                            st.toast(
                                f"¡Imagen aprendida! La IA recordará «{det_actual['nombre_detectado']}» en futuros escaneos.",
                                icon=None,
                            )
                        st.session_state["scanner_deteccion"] = det_actual
                        st.session_state["scanner_estado"] = "CONFIRMADO_INGRESAR_CANTIDAD"
                        st.rerun()
                with c_back2:
                    if st.button("↩️ Volver", width="stretch", key="btn_volver_corr_2"):
                        st.session_state["scanner_estado"] = "ESPERANDO_CONFIRMACION"
                        st.rerun()

        # ====================================================================
        # PASO 3: PRODUCTO CONFIRMADO -> INGRESAR CANTIDAD (LOTE, CAJA O UNIDADES)
        # ====================================================================
        elif estado_scan == "CONFIRMADO_INGRESAR_CANTIDAD":
            render_banner_producto_confirmado(det_actual)

            st.markdown("###### Indica cuánto del producto confirmado vas a ingresar (Lote, Caja o Unidades)")
            fmt_def = det_actual.get("formato_sugerido", "CAJA")
            idx_f = (
                ["CAJA", "LOTE", "UNIDAD"].index(fmt_def)
                if fmt_def in ("CAJA", "LOTE", "UNIDAD")
                else 0
            )

            sc1, sc2, sc3 = st.columns(3)
            with sc1:
                scan_formato = st.selectbox(
                    "Formato de Ingreso *",
                    options=["CAJA", "LOTE", "UNIDAD"],
                    index=idx_f,
                    format_func=lambda f: {
                        "CAJA": "Caja",
                        "LOTE": "Lote / Pack",
                        "UNIDAD": "Unidades",
                    }[f],
                    key="scan_ing_formato",
                )
            with sc2:
                etiq_c = (
                    "Cantidad de Cajas *"
                    if scan_formato == "CAJA"
                    else (
                        "Cantidad de Lotes *"
                        if scan_formato == "LOTE"
                        else "Cantidad de Unidades *"
                    )
                )
                scan_cant = st.number_input(
                    etiq_c,
                    min_value=1,
                    max_value=5000,
                    value=2 if scan_formato != "UNIDAD" else 12,
                    step=1,
                    key="scan_ing_cant",
                )
            with sc3:
                if scan_formato == "UNIDAD":
                    scan_upf = 1
                    st.text_input(
                        "Unidades por formato",
                        value="1 unidad (directo)",
                        disabled=True,
                        key="scan_upf_dis",
                    )
                else:
                    upf_sug = max(2, int(det_actual.get("unidades_por_formato_sugeridas", 12) or 12))
                    scan_upf = st.number_input(
                        f"Unidades por {scan_formato.title()} *",
                        min_value=2,
                        max_value=1000,
                        value=upf_sug,
                        step=1,
                        key="scan_ing_upf",
                    )

            sd1, sd2 = st.columns(2)
            with sd1:
                scan_perecible = st.checkbox(
                    "Tiene fecha de caducidad (perecible)",
                    value=bool(det_actual.get("perecible_sugerido", True)),
                    key="scan_ing_perecible",
                )
            with sd2:
                if scan_perecible:
                    scan_fecha_cad = st.date_input(
                        "Fecha de Caducidad del Lote *",
                        value=date.today() + timedelta(days=25),
                        key="scan_ing_cad",
                    )
                else:
                    scan_fecha_cad = None

            if not det_actual.get("es_existente", True):
                st.markdown("###### Datos del Nuevo Producto Detectado")
                sn1, sn2, sn3, sn4 = st.columns(4)
                with sn1:
                    scan_sku_nuevo = st.text_input(
                        "SKU *",
                        value=det_actual.get("codigo_sku", "PRD-020"),
                        key="scan_nuevo_sku",
                    )
                with sn2:
                    scan_peso_nuevo = st.number_input(
                        "Peso Unit. *",
                        min_value=0.01,
                        value=float(det_actual.get("peso_sugerido", 1.0)),
                        step=0.1,
                        key="scan_nuevo_peso",
                    )
                with sn3:
                    scan_costo_nuevo = st.number_input(
                        "Costo Unit. ($) *",
                        min_value=0.0,
                        value=float(det_actual.get("precio_compra_sugerido", 850.0)),
                        step=50.0,
                        key="scan_nuevo_costo",
                    )
                with sn4:
                    scan_venta_nuevo = st.number_input(
                        "Precio Venta ($) *",
                        min_value=1.0,
                        value=float(det_actual.get("precio_venta_sugerido", 1350.0)),
                        step=50.0,
                        key="scan_nuevo_venta",
                    )
                peso_preview = float(scan_peso_nuevo)
                costo_preview = float(scan_costo_nuevo)
            else:
                peso_preview = float(det_actual.get("peso_sugerido", 1.0))
                costo_preview = float(det_actual.get("precio_compra_sugerido", 850.0))

            render_conversion_preview(
                formato=scan_formato,
                cantidad_formato=int(scan_cant),
                unidades_por_formato=int(scan_upf),
                peso_unitario=peso_preview,
                unidad_peso=det_actual.get("unidad_peso_sugerida", "kg"),
                costo_unitario=costo_preview,
            )

            b_ing, b_cambiar = st.columns([1.8, 1])
            with b_ing:
                if st.button(
                    "Confirmar e Ingresar al Inventario",
                    type="primary",
                    width="stretch",
                    key="btn_ejecutar_ingreso_scanner",
                ):
                    try:
                        fecha_cad_str = (
                            scan_fecha_cad.strftime("%Y-%m-%d")
                            if (scan_perecible and scan_fecha_cad)
                            else None
                        )
                        if det_actual.get("es_existente", True):
                            res = reabastecer_producto(
                                id_producto=int(det_actual["id_producto"]),
                                formato_ingreso=scan_formato,
                                cantidad_formato=int(scan_cant),
                                unidades_por_formato=int(scan_upf),
                                modo_costo="POR_UNIDAD",
                                costo_ingresado=costo_preview,
                                fecha_caducidad=fecha_cad_str,
                                usuario=usuario,
                            )
                            st.session_state["scanner_mensaje_exito"] = (
                                f"**Escaneo IA ingresado:** Se sumaron **+{res['unidades_ingresadas']} unidades** "
                                f"({scan_cant} {scan_formato} × {scan_upf}u) a **{res['nombre_producto']}**. "
                                f"Stock actualizado: **{res['stock_posterior']} uds**."
                            )
                        else:
                            creado = registrar_producto(
                                codigo_sku=scan_sku_nuevo,
                                nombre_producto=det_actual["nombre_detectado"],
                                id_categoria=int(det_actual["id_categoria"]),
                                id_proveedor=None,
                                formato_ingreso=scan_formato,
                                cantidad_formato=int(scan_cant),
                                unidades_por_formato=int(scan_upf),
                                modo_costo="POR_UNIDAD",
                                costo_ingresado=float(scan_costo_nuevo),
                                precio_venta_unitario=float(scan_venta_nuevo),
                                stock_minimo_unidades=6,
                                peso_unitario=float(scan_peso_nuevo),
                                unidad_peso=det_actual.get("unidad_peso_sugerida", "kg"),
                                perecible=bool(scan_perecible),
                                fecha_caducidad=fecha_cad_str,
                                usuario=usuario,
                            )
                            vincular_producto_creado_en_memoria(
                                creado["nombre_producto"], creado
                            )
                            st.session_state["scanner_mensaje_exito"] = (
                                f"**Nuevo producto creado y aprendido por Escáner IA:** **{creado['nombre_producto']}** "
                                f"(`{creado['codigo_sku']}`) ingresado con **{creado['stock_actual']} unidades**."
                            )

                        st.session_state["scanner_estado"] = "SIN_CAPTURA"
                        st.session_state["scanner_deteccion"] = None
                        st.session_state["scanner_last_img_hash"] = None
                        st.session_state["scanner_last_img_bytes"] = None
                        st.session_state["scanner_simulada_bytes"] = None
                        st.session_state["scanner_cam_nonce"] = (
                            st.session_state.get("scanner_cam_nonce", 0) + 1
                        )
                        st.toast("Inventario actualizado en tiempo real desde el Escáner IA.", icon=None)
                        st.rerun()
                    except ErrorNegocio as err:
                        st.error(str(err))
            with b_cambiar:
                if st.button(
                    "↩️ Cambiar producto detectado",
                    width="stretch",
                    key="btn_volver_a_confirmacion_scan",
                ):
                    st.session_state["scanner_estado"] = "ESPERANDO_CONFIRMACION"
                    st.rerun()


# ============================================================================
# VISTA 2: PANEL INTEGRAL DEL DUEÑO / ADMINISTRADOR DE LA PYME
# ============================================================================


def vista_administrador(usuario: dict[str, Any]) -> None:
    seccion = st.session_state.get("nav_admin", "Resumen Ejecutivo")
    subtitulos = {
        "Resumen Ejecutivo": "Indicadores financieros clave, rotación de ventas y control FEFO de caducidad",
        "Punto de Venta (Caja)": "Cobro rápido al cliente con cálculo de precios, ofertas activas y boleta instantánea",
        "Inventario y Catálogo": "Supervisión en tiempo real de unidades convertidas, peso total y liquidaciones",
        "Recepción y Escáner IA": "Escaneo inteligente con cámara OCR, ingreso manual por Caja/Lote y control de mermas",
        "Analítica e Historial": "Planificación de reabastecimiento, ranking de rentabilidad y auditoría completa",
    }
    render_topbar(
        usuario,
        titulo_seccion=seccion,
        subtitulo_seccion=subtitulos.get(seccion, ""),
    )

    # ========================================================================
    # MÓDULO 1: RESUMEN EJECUTIVO (KPIs, GRÁFICO Y CADUCIDAD FEFO)
    # ========================================================================
    if seccion == "Resumen Ejecutivo":
        resumen = obtener_resumen_ejecutivo()
        alertas_cad = obtener_alertas_caducidad(dias_umbral=30)

        render_kpi_grid(
            [
                {
                    "etiqueta": "Ingresos por Ventas",
                    "valor": moneda(resumen["ingresos_acumulados"]),
                    "nota": f"{resumen['total_ventas_completadas']} boletas completadas",
                    "acento": "kpi-card-accent-blue",
                    "icono": "chart",
                },
                {
                    "etiqueta": "Utilidad Neta Estimada",
                    "valor": moneda(resumen["utilidad_estimada_total"]),
                    "nota": "Ganancia descontando costo",
                    "acento": "kpi-card-accent-green",
                    "color": "#15803d",
                    "icono": "trending",
                },
                {
                    "etiqueta": "Ticket Promedio",
                    "valor": moneda(resumen["ticket_promedio_general"]),
                    "nota": f"Promedio {resumen['promedio_unidades_por_venta']} uds/boleta",
                    "acento": "kpi-card-accent-purple",
                    "icono": "ticket",
                },
                {
                    "etiqueta": "Riesgo Caducidad (30d)",
                    "valor": f"{resumen['productos_proximos_vencer']} prod.",
                    "nota": f"Capital expuesto: {moneda(resumen['valor_riesgo_caducidad'])}",
                    "acento": "kpi-card-accent-orange",
                    "color": "#c2410c" if resumen["productos_proximos_vencer"] > 0 else "#15803d",
                    "icono": "clock",
                },
                {
                    "etiqueta": "Stock Crítico / Agotado",
                    "valor": f"{resumen['productos_stock_critico']} prod.",
                    "nota": "Requieren reposición",
                    "acento": "kpi-card-accent-red",
                    "icono": "alert",
                },
                {
                    "etiqueta": "Capital en Bodega",
                    "valor": moneda(resumen["valor_bodega_costo"]),
                    "nota": f"Valor venta: {moneda(resumen['valor_bodega_venta'])}",
                    "acento": "kpi-card-accent-amber",
                    "icono": "box",
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
                    "##### Acción Rápida Anti-Merma: Activar Oferta en Productos Próximos a Vencer"
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
                        "Aplicar Precio Oferta",
                        type="primary",
                        width="stretch",
                        key="btn_inicio_promo",
                    ):
                        res_of = aplicar_oferta_producto(id_prod_promo, float(pct_sel))
                        if res_of["descuento_oferta_pct"] > 0:
                            st.toast(
                                f"Oferta activa en {res_of['nombre_producto']}: {moneda(res_of['precio_oferta'])} (-{res_of['descuento_oferta_pct']:g}%)",
                                icon=None,
                            )
                        else:
                            st.toast(
                                f"Oferta desactivada para {res_of['nombre_producto']}.",
                                icon=None,
                            )
                        st.rerun()

        st.markdown("")
        col_graf, col_resumen_lat = st.columns([1.45, 1], gap="large")

        with col_graf:
            with st.container(border=True):
                cg_head, cg_sel = st.columns([1.8, 1])
                with cg_head:
                    st.markdown("##### Evolución de Ingresos y Ventas")
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
                            <h2>Top 5 Productos Estrella</h2>
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
                                <h2>Reposición Urgente</h2>
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
    # MÓDULO 2: PUNTO DE VENTA (CAJA)
    # ========================================================================
    elif seccion == "Punto de Venta (Caja)":
        render_modulo_caja(usuario, prefijo_key="admin_pos")

    # ========================================================================
    # MÓDULO 3: INVENTARIO Y CATÁLOGO (UNIDADES CONVERTIDAS, PESO Y CADUCIDAD)
    # ========================================================================
    elif seccion == "Inventario y Catálogo":
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
                        "ALERTA_CADUCIDAD": "Con alerta (≤ 30 días o vencido)",
                        "VENCIDO": "Vencidos",
                        "URGENTE": "Urgentes (1 a 7 días)",
                        "PROXIMO": "Próximos (8 a 30 días)",
                        "VIGENTE": "Vigentes (> 30 días)",
                        "NO_PERECIBLE": "No perecibles",
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
                with st.expander("Ver Desglose de Lotes y Fechas de Caducidad por Producto"):
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
                with st.expander("Configurar Descuento / Oferta Comercial a un Producto"):
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
                        st.toast(
                            f"Oferta guardada en tiempo real: {r_of['nombre_producto']} a {moneda(r_of['precio_oferta'])} (-{r_of['descuento_oferta_pct']:g}%).",
                            icon=None,
                        )
                        st.rerun()

    # ========================================================================
    # MÓDULO 4: RECEPCIÓN, ESCÁNER IA Y MERMAS
    # ========================================================================
    elif seccion == "Recepción y Escáner IA":
        catalogos = obtener_catalogos()
        mapa_cat_form = {
            c["id_categoria"]: c["nombre_categoria"] for c in catalogos["categorias"]
        }
        mapa_prov_form = {0: "-- Sin proveedor asignado --"}
        for pr in catalogos["proveedores"]:
            mapa_prov_form[pr["id_proveedor"]] = (
                f"{pr['nombre_proveedor']} ({pr['dias_entrega_estimados']}d entrega)"
            )

        sub_rec = st.segmented_control(
            "Operación de bodega",
            options=[
                "Escáner con Cámara IA",
                "Ingreso Manual (Nuevo / Lote)",
                "Registro de Mermas y Bajas",
            ],
            default="Escáner con Cámara IA",
            label_visibility="collapsed",
            key="seg_recepcion_modo",
        )
        st.markdown("")

        # --- SUBMÓDULO A: ESCÁNER CON CÁMARA IA ---
        if not sub_rec or sub_rec == "Escáner con Cámara IA":
            render_bloque_escaner_camara(usuario, mapa_cat_form, mapa_prov_form)

        # --- SUBMÓDULO B: INGRESO MANUAL CON CONVERSIÓN AUTOMÁTICA ---
        if sub_rec == "Ingreso Manual (Nuevo / Lote)":

            with st.container(border=True):
                if st.session_state.get("flash_ingreso"):
                    st.success(st.session_state["flash_ingreso"])

                modo_operacion = st.radio(
                    "Tipo de Operación de Entrada",
                    options=["NUEVO_PRODUCTO", "ABASTECER_EXISTENTE"],
                    format_func=lambda m: (
                        "Registrar Nuevo Producto"
                        if m == "NUEVO_PRODUCTO"
                        else "Ingresar Stock / Nuevo Lote a Producto Existente"
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

                    st.markdown("###### 1. Formato de Ingreso y Conversión a Unidades")
                    f1, f2, f3 = st.columns(3)
                    with f1:
                        np_formato = st.selectbox(
                            "Formato de Ingreso *",
                            options=["CAJA", "LOTE", "UNIDAD"],
                            format_func=lambda f: {
                                "CAJA": "Caja cerrada",
                                "LOTE": "Lote / Pack mayorista",
                                "UNIDAD": "Unidad individual (1x1)",
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

                    st.markdown("###### 2. Peso / Contenido Neto y Fecha de Caducidad")
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

                    st.markdown("###### 3. Precios y Stock Mínimo de Seguridad")
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
                        "Registrar Producto y Convertir a Unidades",
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
                            st.session_state["flash_ingreso"] = (
                                f"Producto **{creado['nombre_producto']}** (`{creado['codigo_sku']}`) creado en tiempo real con "
                                f"**{creado['stock_actual']} unidades** en inventario."
                            )
                            st.toast(
                                f"Producto {creado['nombre_producto']} guardado en tiempo real.",
                                icon=None,
                            )
                            st.rerun()
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
                                "CAJA": "Caja cerrada",
                                "LOTE": "Lote / Pack",
                                "UNIDAD": "Unidades sueltas",
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
                        "Confirmar Ingreso y Sumar Unidades al Stock",
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
                            st.session_state["flash_ingreso"] = (
                                f"Se sumaron **+{res_ab['unidades_ingresadas']} unidades** a **{res_ab['nombre_producto']}** en tiempo real. "
                                f"Nuevo stock disponible: **{res_ab['stock_posterior']} uds**."
                            )
                            st.toast(
                                f"+{res_ab['unidades_ingresadas']} uds sumadas a {res_ab['nombre_producto']} en tiempo real.",
                                icon=None,
                            )
                            st.rerun()
                        except ErrorNegocio as err:
                            st.error(str(err))

        # --- SUBMÓDULO C: REGISTRO DE PÉRDIDAS O BAJAS (MERMA) ---
        if sub_rec == "Registro de Mermas y Bajas":
            with st.container(border=True):
                if st.session_state.get("flash_merma"):
                    st.success(st.session_state["flash_merma"])

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
                            f"{'[VENCIDO] ' if p['estado_caducidad'] == 'VENCIDO' else ''}"
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
                            "VENCIMIENTO": "Vencimiento / Producto caducado",
                            "DAÑO": "Daño / Rotura / Deterioro",
                            "ROBO": "Robo / Hurto / Faltante",
                            "OTRO": "Otra pérdida de inventario",
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
                        "Registrar Pérdida y Descontar Stock",
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
                            st.session_state["flash_merma"] = (
                                f"Pérdida auditada en tiempo real: **-{reg['cantidad']} uds** de *{reg['nombre_producto']}* "
                                f"({moneda(reg['costo_estimado'])}). Stock restante: **{reg['stock_posterior']} uds**."
                            )
                            st.toast(
                                f"Merma de {reg['nombre_producto']} descontada en tiempo real.",
                                icon=None,
                            )
                            st.rerun()
                        except ErrorNegocio as err:
                            st.error(str(err))

    # ========================================================================
    # MÓDULO 5: ANALÍTICA E HISTORIAL COMPLETO
    # ========================================================================
    elif seccion == "Analítica e Historial":
        sub_reab, sub_ranking, sub_hist, sub_perd = st.tabs(
            [
                "Cálculo de Reabastecimiento",
                "Más Vendidos y Categorías",
                "Historial Ventas y Compras",
                "Historial de Pérdidas",
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

# ============================================================================
# BOTÓN FLOTANTE DE CHAT IA (MINI CHAT ACCESIBLE EN TODA LA APP)
# ============================================================================


def render_chat_flotante_ia() -> None:
    """Botón flotante en la esquina inferior derecha que abre un mini chat con el Asesor IA."""
    with st.container(key="chat_fab_wrap"):
        with st.popover("Asesor IA", key="popover_chat_ia"):
            st.html(
                """
                <div class="mini-chat-header">
                    <div>
                        <div class="mini-chat-header-title">AsesorIA PyME</div>
                        <div class="mini-chat-header-sub">Compras, ofertas FEFO y ventas en vivo</div>
                    </div>
                    <span class="mini-chat-pill">En línea</span>
                </div>
                """
            )

            with st.expander("Ajustes del motor IA", expanded=False):
                modo_ia = st.selectbox(
                    "Proveedor",
                    options=["AUTO_GRATIS", "LOCAL", "GEMINI", "GROQ"],
                    format_func=lambda m: {
                        "AUTO_GRATIS": "Automático Gratuito (Nube + Local)",
                        "LOCAL": "Motor Local Instantáneo (Offline)",
                        "GEMINI": "Google Gemini 2.5 Flash",
                        "GROQ": "Groq Llama 3.3 70B",
                    }[m],
                    key="cfg_modo_ia",
                )
                api_key_ia = st.text_input(
                    "API Key opcional",
                    type="password",
                    placeholder="Opcional en Gemini / Groq",
                    key="cfg_apikey_ia",
                )

            q1, q2, q3, q4 = st.columns([1.05, 1.0, 1.0, 0.9])
            pregunta_boton: str | None = None
            with q1:
                if st.button("Compras", width="stretch", key="mini_q_compras"):
                    pregunta_boton = (
                        "Según mis ventas y el stock actual, ¿qué productos debo comprar con prioridad esta semana, "
                        "en qué cantidad de cajas/lotes y cuánto presupuesto necesito?"
                    )
            with q2:
                if st.button("Ofertas", width="stretch", key="mini_q_ofertas"):
                    pregunta_boton = (
                        "Revisa los productos próximos a vencer y dime qué ofertas o porcentajes de descuento exactos "
                        "me recomiendas aplicar hoy para no perder dinero."
                    )
            with q3:
                if st.button("Combos", width="stretch", key="mini_q_combos"):
                    pregunta_boton = (
                        "Propón combos o packs combinando mis productos más vendidos con los de menor rotación o próximos "
                        "a vencer para aumentar el ticket promedio."
                    )
            with q4:
                if st.button("Limpiar", width="stretch", key="mini_q_limpiar"):
                    st.session_state["mensajes_ia"] = st.session_state["mensajes_ia"][:1]

            placeholder_historial = st.container(height=280, border=False)

            with st.form("mini_chat_ia_form", clear_on_submit=True):
                c_inp, c_btn = st.columns([3.1, 1.1])
                with c_inp:
                    txt_usuario = st.text_input(
                        "Consulta",
                        placeholder="Pregunta sobre stock, compras u ofertas...",
                        label_visibility="collapsed",
                        key="mini_chat_input",
                    )
                with c_btn:
                    enviado = st.form_submit_button(
                        "Enviar", type="primary", width="stretch"
                    )

            consulta_final = pregunta_boton or (
                txt_usuario.strip() if enviado and txt_usuario.strip() else None
            )

            if consulta_final:
                st.session_state["mensajes_ia"].append(
                    {"role": "user", "content": consulta_final}
                )
                with st.spinner("Consultando inventario y ventas..."):
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

            with placeholder_historial:
                for msg in st.session_state["mensajes_ia"]:
                    if msg["role"] == "user":
                        st.html(
                            f'<div class="chat-bubble-user">{esc(msg["content"])}</div>'
                        )
                    else:
                        with st.container(border=True):
                            st.markdown(msg["content"])
                            if msg.get("motor"):
                                st.caption(f"Fuente: {msg['motor']}")


# ============================================================================
# VISTA 3: PANEL EXCLUSIVO DE EMPLEADO / CAJERO
# ============================================================================


def vista_empleado(usuario: dict[str, Any]) -> None:
    render_topbar(
        usuario,
        titulo_seccion="Punto de Venta (Caja)",
        subtitulo_seccion="Cobro rápido, control automático de stock y descuento FEFO",
    )
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

    render_chat_flotante_ia()


if __name__ == "__main__":
    main()
