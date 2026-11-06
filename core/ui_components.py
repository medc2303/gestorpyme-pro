"""
Componentes HTML, CSS y SVG para la interfaz en Streamlit.
Adapta fielmente la estética limpia y profesional del proyecto original en HTML/CSS,
eliminando referencias técnicas a SQL y añadiendo visualizaciones para caducidad,
conversión Caja/Lote -> Unidades, peso de inventario y asistente comercial PyME.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any
import streamlit as st

RUTA_CSS = Path(__file__).resolve().parent.parent / "styles" / "theme.css"


def esc(valor: Any) -> str:
    """Escapa texto para inserción segura en bloques HTML."""
    return html.escape(str(valor if valor is not None else ""))


def moneda(valor: float | int | None) -> str:
    """Formatea montos en pesos chilenos ($15.070) con separador de miles '.'."""
    num = float(valor or 0.0)
    entero = round(num)
    if abs(num - entero) < 0.01:
        return "$" + f"{entero:,}".replace(",", ".")
    entero_parte = int(num)
    dec_parte = round(abs(num - entero_parte) * 100)
    return "$" + f"{entero_parte:,}".replace(",", ".") + f",{dec_parte:02d}"


def _eje_corto(valor: float) -> str:
    if valor >= 1_000_000:
        return f"${valor / 1_000_000:.1f}M"
    if valor >= 1_000:
        return f"${round(valor / 1_000)}k"
    return f"${round(valor)}"


def inyectar_estilos() -> None:
    """Carga e inyecta la hoja de estilos CSS en la aplicación Streamlit."""
    if RUTA_CSS.exists():
        css = RUTA_CSS.read_text(encoding="utf-8")
        st.html(f"<style>{css}</style>")


def render_topbar(usuario: dict[str, Any]) -> None:
    """Renderiza el encabezado superior con marca PyME y rol activo."""
    es_admin = usuario.get("rol") == "Administrador"
    sigla = "PM" if es_admin else "CJ"
    titulo = (
        "GestorPyME Pro — Control Comercial, Inventario y Ventas"
        if es_admin
        else "Punto de Venta y Caja Rápida — Módulo Operativo"
    )
    subtitulo = (
        "Gestión integral de stock en unidades, caducidad FEFO, ingresos y recomendaciones con IA"
        if es_admin
        else "Atención ágil de clientes, control de stock en tiempo real y alertas de caducidad"
    )
    clase_rol = "badge-role-admin" if es_admin else "badge-role-emp"

    bloque = f"""
    <header class="topbar">
        <div class="topbar-brand">
            <div class="brand-icon">{sigla}</div>
            <div class="topbar-title">
                <h1>{esc(titulo)}</h1>
                <span>{esc(subtitulo)}</span>
            </div>
        </div>
        <div class="topbar-user">
            <div class="user-meta">
                <strong>{esc(usuario.get("nombre_completo", "Usuario"))}</strong>
                <span class="badge {clase_rol}">Rol: {esc(usuario.get("rol", ""))}</span>
            </div>
        </div>
    </header>
    """
    st.html(bloque)


def render_kpi_grid(tarjetas: list[dict[str, str]]) -> None:
    """Renderiza una grilla responsiva de tarjetas KPI en HTML."""
    items_html = []
    for t in tarjetas:
        acento = t.get("acento", "kpi-card-accent-blue")
        color_val = f'style="color: {t["color"]};"' if t.get("color") else ""
        items_html.append(
            f"""
            <div class="kpi-card {esc(acento)}">
                <div class="kpi-label">{esc(t["etiqueta"])}</div>
                <div class="kpi-value" {color_val}>{esc(t["valor"])}</div>
                <div class="kpi-note">{esc(t.get("nota", ""))}</div>
            </div>
            """
        )
    st.html(f'<div class="kpi-grid">{"".join(items_html)}</div>')


def render_card_header(
    titulo: str, subtitulo: str, pill_texto: str = "", pill_tipo: str = ""
) -> None:
    """Renderiza un encabezado estilizado de sección."""
    clase_pill = f"module-pill {pill_tipo}".strip()
    pill_html = (
        f'<span class="{esc(clase_pill)}">{esc(pill_texto)}</span>'
        if pill_texto
        else ""
    )
    st.html(
        f"""
        <div class="card-header" style="margin-bottom: 0.65rem;">
            <div>
                <h2>{esc(titulo)}</h2>
                <span class="card-subtitle">{esc(subtitulo)}</span>
            </div>
            {pill_html}
        </div>
        """
    )


def badge_estado_stock(estado: str) -> str:
    mapa = {
        "OPTIMO": ("badge-optimo", "ÓPTIMO"),
        "BAJO": ("badge-bajo", "BAJO"),
        "CRITICO": ("badge-critico", "CRÍTICO"),
        "AGOTADO": ("badge-agotado", "AGOTADO"),
    }
    clase, texto = mapa.get(estado.upper(), ("badge-noperecible", estado))
    return f'<span class="badge {clase}">{esc(texto)}</span>'


def badge_caducidad(estado_cad: str, etiqueta: str) -> str:
    mapa = {
        "VENCIDO": "badge-vencido",
        "URGENTE": "badge-urgente",
        "PROXIMO": "badge-proximo",
        "VIGENTE": "badge-vigente",
        "NO_PERECIBLE": "badge-noperecible",
        "SIN_STOCK": "badge-noperecible",
    }
    clase = mapa.get(estado_cad, "badge-noperecible")
    return f'<span class="badge {clase}">{esc(etiqueta)}</span>'


def render_conversion_preview(
    formato: str,
    cantidad_formato: int,
    unidades_por_formato: int,
    peso_unitario: float,
    unidad_peso: str,
    costo_unitario: float,
) -> None:
    """Muestra la caja visual de conversión automática Caja/Lote -> Unidades y peso."""
    fmt = formato.upper()
    upf = 1 if fmt == "UNIDAD" else max(1, int(unidades_por_formato))
    total_uds = max(0, int(cantidad_formato)) * upf

    if fmt == "UNIDAD":
        formula_txt = f"{total_uds} unidad(es) directa(s)"
    else:
        etiqueta = "Caja(s)" if fmt == "CAJA" else "Lote(s)"
        formula_txt = f"{cantidad_formato} {etiqueta} × {upf} uds c/u"

    bruto_peso = total_uds * max(0.0, float(peso_unitario))
    if unidad_peso == "g" and bruto_peso >= 1000:
        peso_tot_str = f"{bruto_peso / 1000.0:.2f} kg"
    elif unidad_peso == "ml" and bruto_peso >= 1000:
        peso_tot_str = f"{bruto_peso / 1000.0:.2f} L"
    else:
        peso_tot_str = f"{bruto_peso:g} {unidad_peso}"

    inversion_tot = moneda(total_uds * max(0.0, costo_unitario))

    st.html(
        f"""
        <div class="conversion-box">
            <div>
                <div class="conversion-title">Conversión Automática para Inventario</div>
                <div class="conversion-formula">
                    {esc(formula_txt)} &bull; Peso total ingreso: <strong>{esc(peso_tot_str)}</strong>
                    &bull; Costo unitario: <strong>{esc(moneda(costo_unitario))}</strong> (Total: {esc(inversion_tot)})
                </div>
            </div>
            <div class="conversion-highlight">
                = {total_uds} Unidades en Stock
            </div>
        </div>
        """
    )


def render_tabla_caducidad_principal(alertas: list[dict[str, Any]]) -> None:
    """Renderiza en la Pestaña Principal los productos vencidos y próximos a vencer."""
    if not alertas:
        st.html(
            """
            <div class="card card-caducidad">
                <div class="empty-state">
                    ✅ Excelente: No hay productos vencidos ni próximos a vencer en los próximos 30 días.
                </div>
            </div>
            """
        )
        return

    filas = []
    for a in alertas:
        est = a["estado_caducidad"]
        clase_fila = (
            "row-vencido"
            if est == "VENCIDO"
            else ("row-urgente" if est == "URGENTE" else "")
        )
        oferta_html = (
            f' <span class="badge badge-oferta">-{a["descuento_oferta_pct"]:g}% OFERTA</span>'
            if a.get("descuento_oferta_pct", 0) > 0
            else ""
        )
        filas.append(
            f"""
            <tr class="{clase_fila}">
                <td class="mono">{esc(a["codigo_sku"])}</td>
                <td>
                    <strong>{esc(a["nombre_producto"])}</strong>{oferta_html}
                    <div style="font-size:0.76rem;color:#64748b;">{esc(a["nombre_categoria"])} &bull; Peso: {esc(a["peso_unitario_texto"])}</div>
                </td>
                <td class="text-center">{badge_caducidad(est, a["etiqueta_caducidad"])}</td>
                <td class="text-center mono">{esc(a["fecha_caducidad_fmt"])}</td>
                <td class="text-center">
                    <strong>{a["stock_actual"]} uds</strong>
                    <div style="font-size:0.74rem;color:#64748b;">{esc(a["peso_total_texto"])}</div>
                </td>
                <td class="text-right">
                    <strong>{esc(moneda(a["valor_stock_costo"]))}</strong>
                    <div style="font-size:0.74rem;color:#64748b;">Venta: {esc(moneda(a["valor_stock_venta"]))}</div>
                </td>
                <td style="font-size:0.81rem;color:#334155;">{esc(a["accion_recomendada"])}</td>
            </tr>
            """
        )

    st.html(
        f"""
        <div class="card card-caducidad">
            <div class="card-header">
                <div>
                    <h2>⏰ Alertas de Caducidad: Productos Próximos a Vencer y Vencidos</h2>
                    <span class="card-subtitle">
                        Control FEFO (Primero en Vencer, Primero en Salir) para activar ofertas a tiempo y evitar pérdidas de capital
                    </span>
                </div>
                <span class="module-pill module-pill-warn">{len(alertas)} producto(s) en seguimiento</span>
            </div>
            <div class="table-wrapper">
                <table class="custom-table">
                    <thead>
                        <tr>
                            <th>SKU</th>
                            <th>Producto / Peso</th>
                            <th class="text-center">Urgencia</th>
                            <th class="text-center">Fecha Venc.</th>
                            <th class="text-center">Stock en Riesgo</th>
                            <th class="text-right">Capital en Riesgo</th>
                            <th>Acción Comercial Sugerida</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(filas)}
                    </tbody>
                </table>
            </div>
        </div>
        """
    )


def render_tabla_inventario(productos: list[dict[str, Any]]) -> None:
    """Renderiza el Chequeo de Inventario con conversión a unidades, peso y caducidad."""
    if not productos:
        st.html(
            '<div class="card"><div class="empty-state">No se encontraron productos para los filtros seleccionados.</div></div>'
        )
        return

    filas = []
    for p in productos:
        est_cad = p["estado_caducidad"]
        clase_fila = (
            "row-vencido"
            if est_cad == "VENCIDO"
            else ("row-urgente" if est_cad == "URGENTE" else "")
        )
        oferta_pct = float(p.get("descuento_oferta_pct", 0.0) or 0.0)
        if oferta_pct > 0:
            precio_html = (
                f'<span style="text-decoration:line-through;color:#94a3b8;font-size:0.78rem;">{esc(moneda(p["precio_venta"]))}</span> '
                f'<strong>{esc(moneda(p["precio_efectivo"]))}</strong> '
                f'<span class="badge badge-oferta">-{oferta_pct:g}%</span>'
            )
        else:
            precio_html = f'<strong>{esc(moneda(p["precio_venta"]))}</strong>'

        filas.append(
            f"""
            <tr class="{clase_fila}">
                <td class="mono">{esc(p["codigo_sku"])}</td>
                <td>
                    <strong>{esc(p["nombre_producto"])}</strong>
                    <div style="font-size:0.75rem;color:#64748b;">{esc(p["nombre_categoria"])} &bull; {esc(p["nombre_proveedor"])}</div>
                </td>
                <td class="text-center">
                    <strong style="font-size:0.95rem;">{p["stock_actual"]} uds</strong>
                    <div style="font-size:0.73rem;color:#64748b;">Mín: {p["stock_minimo"]} uds</div>
                </td>
                <td>
                    <span class="badge badge-formato">{esc(p["formato_habitual"])}</span>
                    <div style="font-size:0.75rem;color:#475569;margin-top:2px;">{esc(p["equivalencia_formato"])}</div>
                </td>
                <td class="text-center">
                    <strong>{esc(p["peso_unitario_texto"])}</strong> / ud
                    <div style="font-size:0.75rem;color:#64748b;">Total: {esc(p["peso_total_texto"])}</div>
                </td>
                <td class="text-center">
                    {badge_caducidad(est_cad, p["etiqueta_caducidad"])}
                    <div class="mono" style="font-size:0.73rem;color:#64748b;margin-top:2px;">{esc(p["fecha_caducidad_fmt"])}</div>
                </td>
                <td class="text-right">{esc(moneda(p["precio_compra"]))}</td>
                <td class="text-right">
                    {precio_html}
                    <div style="font-size:0.74rem;color:#15803d;">Margen: {p["porcentaje_margen"]:.1f}%</div>
                </td>
                <td class="text-center">{badge_estado_stock(p["estado_stock"])}</td>
            </tr>
            """
        )

    st.html(
        f"""
        <div class="card">
            <div class="card-header">
                <div>
                    <h2>Inventario Maestro Consolidado (Convertido a Unidades)</h2>
                    <span class="card-subtitle">
                        Todas las entradas por Caja o Lote se reflejan automáticamente en unidades individuales junto a su peso y caducidad
                    </span>
                </div>
                <span class="module-pill">{len(productos)} registros mostrados</span>
            </div>
            <div class="table-wrapper">
                <table class="custom-table">
                    <thead>
                        <tr>
                            <th>SKU</th>
                            <th>Producto / Categoría / Proveedor</th>
                            <th class="text-center">Stock (Unidades)</th>
                            <th>Formato y Conversión</th>
                            <th class="text-center">Peso Unit. / Total</th>
                            <th class="text-center">Caducidad</th>
                            <th class="text-right">Costo Unit.</th>
                            <th class="text-right">Precio Venta</th>
                            <th class="text-center">Estado Stock</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(filas)}
                    </tbody>
                </table>
            </div>
        </div>
        """
    )


def render_grafico_ventas_svg(serie: list[dict[str, Any]], modo: str = "dia") -> None:
    """Genera el gráfico vectorial SVG de evolución de ventas en el tiempo."""
    if not serie:
        st.html(
            '<div class="chart-container"><div class="empty-state">No hay datos temporales para graficar.</div></div>'
        )
        return

    ancho = 920
    alto = 275
    pad_izq = 66
    pad_der = 26
    pad_arr = 22
    pad_abj = 42
    ancho_util = ancho - pad_izq - pad_der
    alto_util = alto - pad_arr - pad_abj

    max_bruto = max((float(p.get("total_ventas", 0.0)) for p in serie), default=0.0)
    max_y = float(((int(max_bruto * 1.15) // 1000) + 1) * 1000) if max_bruto > 0 else 10000.0

    puntos = []
    n = len(serie)
    for idx, item in enumerate(serie):
        x = pad_izq + (ancho_util / 2.0 if n == 1 else (idx / (n - 1)) * ancho_util)
        val = float(item.get("total_ventas", 0.0))
        y = pad_arr + alto_util - (val / max_y) * alto_util
        puntos.append({**item, "x": x, "y": y, "val": val})

    niveles_y = 4
    grilla_partes = []
    for i in range(niveles_y + 1):
        fraccion = i / niveles_y
        valor_nivel = max_y * (1.0 - fraccion)
        y = pad_arr + fraccion * alto_util
        dash = "0" if i == niveles_y else "4 4"
        grilla_partes.append(
            f'<line x1="{pad_izq}" y1="{y:.1f}" x2="{ancho - pad_der}" y2="{y:.1f}" '
            f'stroke="#e2e8f0" stroke-dasharray="{dash}" stroke-width="1" />'
            f'<text x="{pad_izq - 10}" y="{y + 4:.1f}" text-anchor="end" '
            f'fill="#64748b" font-size="11.5" font-family="Segoe UI, sans-serif">'
            f'{esc(_eje_corto(valor_nivel))}</text>'
        )

    coords_linea = " ".join(f"{p['x']:.1f},{p['y']:.1f}" for p in puntos)
    base_abajo = f"{pad_arr + alto_util:.1f}"
    coords_area = (
        f"{puntos[0]['x']:.1f},{base_abajo} {coords_linea} {puntos[-1]['x']:.1f},{base_abajo}"
    )

    paso_etiq = max(1, (n + 11) // 12)
    etiquetas_x = []
    for idx, p in enumerate(puntos):
        if idx % paso_etiq != 0 and idx != n - 1:
            continue
        etiquetas_x.append(
            f'<text x="{p["x"]:.1f}" y="{alto - 13}" text-anchor="middle" '
            f'fill="#475569" font-size="11.5" font-family="Segoe UI, sans-serif">'
            f'{esc(p["etiqueta"])}</text>'
        )

    nodos = []
    for p in puntos:
        radio = "5.2" if p["val"] > 0 else "3.3"
        relleno = "#1d4ed8" if p["val"] > 0 else "#ffffff"
        pref = "Hora" if modo == "hora" else "Fecha"
        tooltip_nativo = (
            f"{pref}: {p['fecha_iso']} | Ventas: {moneda(p['val'])} "
            f"({p['cantidad_ventas']} tickets, {p['unidades_vendidas']} uds)"
        )
        nodos.append(
            f'<circle cx="{p["x"]:.1f}" cy="{p["y"]:.1f}" r="{radio}" '
            f'fill="{relleno}" stroke="#1d4ed8" stroke-width="2">'
            f"<title>{esc(tooltip_nativo)}</title></circle>"
        )

    st.html(
        f"""
        <div class="chart-container">
            <svg viewBox="0 0 {ancho} {alto}" class="chart-svg" role="img" aria-label="Evolución de ventas">
                <defs>
                    <linearGradient id="gradVentasPyme" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stop-color="#1d4ed8" stop-opacity="0.26" />
                        <stop offset="100%" stop-color="#1d4ed8" stop-opacity="0.02" />
                    </linearGradient>
                </defs>
                {"".join(grilla_partes)}
                <polygon points="{coords_area}" fill="url(#gradVentasPyme)" />
                <polyline fill="none" stroke="#1d4ed8" stroke-width="2.7" stroke-linejoin="round" stroke-linecap="round" points="{coords_linea}" />
                {"".join(etiquetas_x)}
                {"".join(nodos)}
            </svg>
        </div>
        """
    )


def render_tabla_reabastecimiento(recomendaciones: list[dict[str, Any]]) -> None:
    """Renderiza el cálculo inteligente de reabastecimiento Necesario vs Recomendado."""
    if not recomendaciones:
        st.html(
            '<div class="card"><div class="empty-state">Todo el inventario supera su punto de reorden óptimo.</div></div>'
        )
        return

    filas = []
    for r in recomendaciones:
        alerta = r["nivel_alerta"]
        clase_b = (
            "badge-agotado"
            if "AGOTADO" in alerta
            else ("badge-necesario" if alerta == "NECESARIO" else "badge-recomendado")
        )
        filas.append(
            f"""
            <tr>
                <td class="mono">{esc(r["codigo_sku"])}</td>
                <td>
                    <strong>{esc(r["nombre_producto"])}</strong>
                    <div style="font-size:0.75rem;color:#64748b;">{esc(r["nombre_categoria"])}</div>
                </td>
                <td>
                    {esc(r["nombre_proveedor"])}
                    <div style="font-size:0.74rem;color:#64748b;">Entrega est.: {r["dias_entrega_estimados"]} días</div>
                </td>
                <td class="text-center"><strong>{r["stock_actual"]}</strong> / {r["stock_minimo"]} uds</td>
                <td class="text-center">{r["unidades_vendidas_30d"]} uds ({r["promedio_venta_diaria"]:.2f}/día)</td>
                <td class="text-center">{r["punto_reorden"]} uds</td>
                <td class="text-center"><span class="badge {clase_b}">{esc(alerta)}</span></td>
                <td class="text-center">
                    <strong>+{r["cantidad_sugerida"]} uds</strong>
                    <div style="font-size:0.74rem;color:#0369a1;">{esc(r["sugerencia_formato"])}</div>
                </td>
                <td class="text-right"><strong>{esc(moneda(r["costo_estimado_compra"]))}</strong></td>
            </tr>
            """
        )

    costo_total = sum(r["costo_estimado_compra"] for r in recomendaciones)
    st.html(
        f"""
        <div class="card">
            <div class="card-header">
                <div>
                    <h2>Sugerencias de Compra y Reabastecimiento Inteligente</h2>
                    <span class="card-subtitle">
                        Calculado según velocidad de venta (últimos 30 días), stock mínimo, días de entrega del proveedor y formato Caja/Lote
                    </span>
                </div>
                <span class="module-pill">Inversión sugerida: {esc(moneda(costo_total))}</span>
            </div>
            <div class="table-wrapper">
                <table class="custom-table">
                    <thead>
                        <tr>
                            <th>SKU</th>
                            <th>Producto</th>
                            <th>Proveedor (Entrega)</th>
                            <th class="text-center">Stock / Mín.</th>
                            <th class="text-center">Ventas 30d</th>
                            <th class="text-center">Punto Reorden</th>
                            <th class="text-center">Prioridad</th>
                            <th class="text-center">Compra Sugerida</th>
                            <th class="text-right">Costo Est.</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(filas)}
                    </tbody>
                </table>
            </div>
        </div>
        """
    )


def render_tabla_mas_vendidos(ranking: list[dict[str, Any]]) -> None:
    """Renderiza la tabla del ranking de productos más vendidos."""
    if not ranking:
        st.html('<div class="card"><div class="empty-state">Aún no hay ventas registradas.</div></div>')
        return

    filas = []
    for r in ranking:
        filas.append(
            f"""
            <tr>
                <td class="text-center"><strong>#{r["ranking"]}</strong></td>
                <td class="mono">{esc(r["codigo_sku"])}</td>
                <td><strong>{esc(r["nombre_producto"])}</strong></td>
                <td>{esc(r["nombre_categoria"])}</td>
                <td class="text-center"><strong>{r["unidades_vendidas"]} uds</strong></td>
                <td class="text-center">{r["numero_ventas"]}</td>
                <td class="text-center">{r["promedio_unidades_por_ticket"]:.1f}</td>
                <td class="text-right">{esc(moneda(r["ingresos_generados"]))}</td>
                <td class="text-right" style="color:#15803d;font-weight:700;">{esc(moneda(r["utilidad_estimada"]))}</td>
                <td class="text-center">{r["stock_actual"]} uds</td>
            </tr>
            """
        )

    st.html(
        f"""
        <div class="card">
            <div class="card-header">
                <div>
                    <h2>Ranking de Productos Estrella (Más Vendidos)</h2>
                    <span class="card-subtitle">Volumen despachado, frecuencia en boletas, ingresos y ganancia neta estimada</span>
                </div>
                <span class="module-pill">Top {len(ranking)} productos</span>
            </div>
            <div class="table-wrapper">
                <table class="custom-table">
                    <thead>
                        <tr>
                            <th class="text-center">Rank</th>
                            <th>SKU</th>
                            <th>Producto</th>
                            <th>Categoría</th>
                            <th class="text-center">Uds. Vendidas</th>
                            <th class="text-center">Nº Boletas</th>
                            <th class="text-center">Prom. Uds/Ticket</th>
                            <th class="text-right">Ingresos</th>
                            <th class="text-right">Utilidad Est.</th>
                            <th class="text-center">Stock Actual</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(filas)}
                    </tbody>
                </table>
            </div>
        </div>
        """
    )


def render_tabla_promedios_categoria(categorias: list[dict[str, Any]]) -> None:
    """Renderiza el desglose de promedios de ventas por categoría."""
    if not categorias:
        return
    filas = []
    for c in categorias:
        filas.append(
            f"""
            <tr>
                <td><strong>{esc(c["nombre_categoria"])}</strong></td>
                <td class="text-center">{c["productos_distintos_vendidos"]}</td>
                <td class="text-center">{c["total_transacciones"]}</td>
                <td class="text-center">{c["total_unidades_vendidas"]} uds</td>
                <td class="text-right">{esc(moneda(c["ticket_promedio_categoria"]))}</td>
                <td class="text-right">{esc(moneda(c["precio_unitario_promedio"]))}</td>
                <td class="text-center">{c["promedio_unidades_por_transaccion"]:.1f}</td>
                <td class="text-right"><strong>{esc(moneda(c["ingresos_categoria"]))}</strong></td>
            </tr>
            """
        )

    st.html(
        f"""
        <div class="card">
            <div class="card-header">
                <div>
                    <h2>Rendimiento y Promedios por Categoría</h2>
                    <span class="card-subtitle">Desempeño comercial agrupado por línea de negocio</span>
                </div>
            </div>
            <div class="table-wrapper">
                <table class="custom-table">
                    <thead>
                        <tr>
                            <th>Categoría</th>
                            <th class="text-center">Prod. Vendidos</th>
                            <th class="text-center">Transacciones</th>
                            <th class="text-center">Unidades Totales</th>
                            <th class="text-right">Ticket Prom. Cat.</th>
                            <th class="text-right">Precio Unit. Prom.</th>
                            <th class="text-center">Prom. Uds/Venta</th>
                            <th class="text-right">Ingresos Categoría</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(filas)}
                    </tbody>
                </table>
            </div>
        </div>
        """
    )


def render_tabla_movimientos(datos_hist: dict[str, Any]) -> None:
    """Renderiza el historial consolidado de ventas y compras con chips de productos."""
    movs = datos_hist.get("movimientos", [])
    res = datos_hist.get("resumen", {})
    if not movs:
        st.html('<div class="card"><div class="empty-state">No hay movimientos para el filtro aplicado.</div></div>')
        return

    filas = []
    for m in movs:
        es_venta = m["tipo_operacion"] == "VENTA"
        clase_b = "badge-venta" if es_venta else "badge-compra"
        chips = "".join(
            f'<span class="product-chip">{esc(part.strip())}</span>'
            for part in str(m["productos_afectados"]).split("|")
            if part.strip()
        )
        filas.append(
            f"""
            <tr>
                <td class="mono">{esc(m["fecha_hora"])}</td>
                <td class="text-center"><span class="badge {clase_b}">{esc(m["tipo_operacion"])}</span></td>
                <td>
                    <strong>{esc(m["documento"])}</strong>
                    <div style="font-size:0.75rem;color:#64748b;">{esc(m["contraparte"])}</div>
                </td>
                <td><div class="affected-products-list">{chips}</div></td>
                <td class="text-center"><strong>{m["total_unidades"]} uds</strong></td>
                <td>{esc(m["responsable"])}</td>
                <td class="text-right"><strong>{esc(moneda(m["monto_total"]))}</strong></td>
            </tr>
            """
        )

    resumen_txt = (
        f"Ventas: {res.get('cantidad_ventas', 0)} ({moneda(res.get('total_ventas', 0))}) | "
        f"Compras: {res.get('cantidad_compras', 0)} ({moneda(res.get('total_compras', 0))})"
    )

    st.html(
        f"""
        <div class="card">
            <div class="card-header">
                <div>
                    <h2>Historial Consolidado de Ventas y Compras</h2>
                    <span class="card-subtitle">Trazabilidad cronológica de salidas en caja y entradas de abastecimiento</span>
                </div>
                <span class="module-pill">{esc(resumen_txt)}</span>
            </div>
            <div class="table-wrapper">
                <table class="custom-table">
                    <thead>
                        <tr>
                            <th>Fecha y Hora</th>
                            <th class="text-center">Tipo</th>
                            <th>Documento / Contraparte</th>
                            <th>Productos Afectados</th>
                            <th class="text-center">Unidades</th>
                            <th>Responsable</th>
                            <th class="text-right">Monto Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(filas)}
                    </tbody>
                </table>
            </div>
        </div>
        """
    )


def render_tabla_perdidas(datos_perd: dict[str, Any]) -> None:
    """Renderiza la auditoría valorizada de pérdidas y mermas."""
    registros = datos_perd.get("registros", [])
    if not registros:
        st.html(
            '<div class="card card-perdida"><div class="empty-state">Sin registros de pérdidas o mermas para este filtro.</div></div>'
        )
        return

    filas = []
    for r in registros:
        filas.append(
            f"""
            <tr>
                <td class="mono">{esc(r.get("fecha", ""))}</td>
                <td>
                    <span class="mono">{esc(r.get("codigo_sku", ""))}</span> —
                    <strong>{esc(r.get("nombre_producto", ""))}</strong>
                </td>
                <td><span class="badge badge-merma">{esc(r.get("motivo", "MERMA"))}</span></td>
                <td class="text-center"><strong>-{r.get("cantidad", 0)} uds</strong></td>
                <td class="text-center">{r.get("stock_anterior", 0)} &rarr; {r.get("stock_posterior", 0)} uds</td>
                <td class="text-right" style="color:#b91c1c;font-weight:700;">{esc(moneda(r.get("costo_total", 0)))}</td>
                <td>{esc(r.get("responsable", ""))}</td>
            </tr>
            """
        )

    st.html(
        f"""
        <div class="card card-perdida">
            <div class="card-header">
                <div>
                    <h2>Auditoría de Pérdidas y Mermas de Inventario</h2>
                    <span class="card-subtitle">Control de bajas por vencimiento, daño o sustracción valorizadas a costo</span>
                </div>
                <span class="module-pill module-pill-danger">{len(registros)} evento(s)</span>
            </div>
            <div class="table-wrapper">
                <table class="custom-table">
                    <thead>
                        <tr>
                            <th>Fecha y Hora</th>
                            <th>SKU / Producto Afectado</th>
                            <th>Causa y Detalle</th>
                            <th class="text-center">Unidades</th>
                            <th class="text-center">Stock (Antes &rarr; Después)</th>
                            <th class="text-right">Pérdida (Costo)</th>
                            <th>Registrado por</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(filas)}
                    </tbody>
                </table>
            </div>
        </div>
        """
    )
