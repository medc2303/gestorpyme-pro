"""
Asistente Comercial con IA Gratuita para PyMEs.
Analiza en tiempo real las ventas históricas, rotación de inventario, márgenes,
tiempos de entrega de proveedores y fechas de caducidad para recomendar:
  1. Futuras compras priorizadas (en Cajas/Lotes y Unidades).
  2. Ofertas dinámicas y liquidación preventiva de productos próximos a vencer.
  3. Combos / Packs cruzados (producto estrella + producto por rotar) para subir el ticket.

Arquitectura Híbrida Gratuita (Cero Bloqueos en Presentación):
  - Soporta IA Generativa Gratuita en la nube sin API Key (Pollinations Text API).
  - Soporta API Keys gratuitas opcionales de Google Gemini (AI Studio) o Groq.
  - Incluye un Motor Analítico Experto Local como respaldo automático (100% offline/instantáneo).
"""

from __future__ import annotations

from typing import Any
import requests

from core.store import (
    obtener_alertas_caducidad,
    obtener_inventario_consolidado,
    obtener_productos_mas_vendidos,
    obtener_promedios_por_categoria,
    obtener_recomendaciones_reabastecimiento,
    obtener_resumen_ejecutivo,
)
from core.ui_components import moneda


def construir_contexto_tienda() -> dict[str, Any]:
    """Recopila una radiografía en tiempo real del negocio para alimentar a la IA."""
    resumen = obtener_resumen_ejecutivo()
    inventario = obtener_inventario_consolidado()
    top_ventas = obtener_productos_mas_vendidos(limite=8)
    reabastecer = obtener_recomendaciones_reabastecimiento()
    caducidad = obtener_alertas_caducidad(dias_umbral=30)
    categorias = obtener_promedios_por_categoria()

    ids_top = {t["id_producto"] for t in top_ventas[:4]}
    baja_rotacion = [
        p
        for p in inventario
        if p["stock_actual"] >= 12 and p["unidades_vendidas_total"] <= 4 and p["id_producto"] not in ids_top
    ]
    baja_rotacion.sort(key=lambda x: (-x["valor_stock_costo"], x["unidades_vendidas_total"]))

    return {
        "resumen": resumen,
        "inventario": inventario,
        "top_ventas": top_ventas,
        "reabastecer": reabastecer,
        "caducidad": caducidad,
        "categorias": categorias,
        "baja_rotacion": baja_rotacion,
    }


def _formatear_prompt_sistema(ctx: dict[str, Any]) -> str:
    """Convierte los datos vivos de la tienda en un contexto estructurado para el LLM."""
    r = ctx["resumen"]

    lineas_top = "\n".join(
        f"  - #{t['ranking']} {t['nombre_producto']} ({t['codigo_sku']}): "
        f"{t['unidades_vendidas']} uds vendidas, ingresos {moneda(t['ingresos_generados'])}, "
        f"utilidad {moneda(t['utilidad_estimada'])}, stock actual {t['stock_actual']} uds."
        for t in ctx["top_ventas"][:6]
    ) or "  - Sin ventas registradas aún."

    lineas_compra = "\n".join(
        f"  - [{c['nivel_alerta']}] {c['nombre_producto']} ({c['codigo_sku']}): "
        f"stock {c['stock_actual']}/{c['stock_minimo']} uds, rotación {c['unidades_vendidas_30d']} uds/30d, "
        f"sugerido comprar {c['sugerencia_formato']} (costo est. {moneda(c['costo_estimado_compra'])}) "
        f"a '{c['nombre_proveedor']}' ({c['dias_entrega_estimados']}d entrega)."
        for c in ctx["reabastecer"][:8]
    ) or "  - Ningún producto requiere reposición urgente."

    lineas_cad = "\n".join(
        f"  - [{a['estado_caducidad']}] {a['nombre_producto']} ({a['codigo_sku']}): "
        f"{a['etiqueta_caducidad']} ({a['fecha_caducidad_fmt']}), {a['stock_actual']} uds en riesgo "
        f"(costo {moneda(a['valor_stock_costo'])}, precio venta {moneda(a['precio_venta'])}, "
        f"oferta actual {a['descuento_oferta_pct']:g}%)."
        for a in ctx["caducidad"][:8]
    ) or "  - No hay productos próximos a vencer."

    lineas_lentos = "\n".join(
        f"  - {b['nombre_producto']} ({b['codigo_sku']}): {b['stock_actual']} uds en bodega, "
        f"solo {b['unidades_vendidas_total']} uds vendidas, margen {b['porcentaje_margen']:.1f}%."
        for b in ctx["baja_rotacion"][:5]
    ) or "  - Sin productos estancados relevantes."

    return f"""Eres 'AsesorIA PyME', un consultor comercial experto para pequeñas y medianas empresas (almacenes, minimarkets y comercios detallistas en Chile).
Responde SIEMPRE en español claro, cercano, ejecutivo y accionable, usando formato Markdown con viñetas, negritas y cifras reales del negocio en pesos chilenos ($).
Basa TODAS tus recomendaciones estrictamente en estos datos en vivo de la tienda:

RESUMEN EJECUTIVO ACTUAL:
- Ventas completadas: {r['total_ventas_completadas']} boletas | Ingresos acumulados: {moneda(r['ingresos_acumulados'])}
- Utilidad neta estimada: {moneda(r['utilidad_estimada_total'])} | Ticket promedio: {moneda(r['ticket_promedio_general'])} ({r['promedio_unidades_por_venta']} uds/boleta)
- Capital en bodega (costo): {moneda(r['valor_bodega_costo'])} | Valor venta proyectado: {moneda(r['valor_bodega_venta'])}
- Productos en alerta de stock: {r['productos_stock_critico']} | Productos próximos a vencer/vencidos: {r['productos_proximos_vencer']} (Capital en riesgo: {moneda(r['valor_riesgo_caducidad'])})

PRODUCTOS MÁS VENDIDOS (TRACCIÓN DE CLIENTES):
{lineas_top}

NECESIDADES DE COMPRA Y REABASTECIMIENTO:
{lineas_compra}

PRODUCTOS VENCIDOS O PRÓXIMOS A VENCER (FEFO):
{lineas_cad}

PRODUCTOS CON BAJA ROTACIÓN (CAPITAL INMOVILIZADO):
{lineas_lentos}

INSTRUCCIONES CLAVE:
1. Cuando te pidan recomendaciones de compras, prioriza primero AGOTADOS y CRÍTICOS de alta rotación, indicando cuántas Cajas/Lotes o Unidades pedir, a qué proveedor y el presupuesto necesario.
2. Cuando te pidan ofertas o promociones, prioriza liquidar los productos con alerta URGENTE o PRÓXIMO A VENCER (nunca vendas productos ya VENCIDOS; para los vencidos recomienda darlos de baja en el módulo de Mermas). Propón porcentajes concretos de descuento cuidando no perder todo el costo, o arma Packs/Combos juntando un producto estrella con uno próximo a vencer o de baja rotación.
3. Sé conciso, práctico y enfocado en maximizar ganancias y reducir pérdidas de la PyME.
"""


def _consultar_pollinations_gratis(
    mensajes_llm: list[dict[str, str]],
) -> str | None:
    """Consulta el endpoint gratuito sin API Key de Pollinations (compatible OpenAI)."""
    try:
        resp = requests.post(
            "https://text.pollinations.ai/openai",
            json={
                "model": "openai",
                "messages": mensajes_llm,
                "temperature": 0.4,
            },
            timeout=11,
        )
        if resp.status_code == 200:
            data = resp.json()
            contenido = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            if len(contenido) > 40:
                return contenido
    except Exception:
        pass
    return None


def _consultar_gemini_gratis(
    prompt_sistema: str, pregunta_usuario: str, api_key: str
) -> str | None:
    """Consulta Google Gemini Free Tier (gemini-2.5-flash) si el usuario ingresó clave."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key.strip()}"
    payload = {
        "system_instruction": {"parts": [{"text": prompt_sistema}]},
        "contents": [{"role": "user", "parts": [{"text": pregunta_usuario}]}],
        "generationConfig": {"temperature": 0.35, "maxOutputTokens": 1100},
    }
    resp = requests.post(url, json=payload, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini respondió con código {resp.status_code}.")
    data = resp.json()
    partes = (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [])
    )
    texto = "".join(p.get("text", "") for p in partes).strip()
    return texto or None


def _consultar_groq_gratis(
    mensajes_llm: list[dict[str, str]], api_key: str
) -> str | None:
    """Consulta Groq Cloud Free Tier (Llama 3.3 70B) si el usuario ingresó clave."""
    resp = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        },
        json={
            "model": "llama-3.3-70b-versatile",
            "messages": mensajes_llm,
            "temperature": 0.35,
            "max_tokens": 1100,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Groq respondió con código {resp.status_code}.")
    data = resp.json()
    return (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
        or None
    )


def _motor_analitico_local(pregunta: str, ctx: dict[str, Any]) -> str:
    """
    Motor experto local basado en reglas comerciales e indicadores reales de la PyME.
    Garantiza respuestas ricas, exactas e instantáneas incluso sin conexión a internet.
    """
    q = pregunta.lower()
    r = ctx["resumen"]
    reab = ctx["reabastecer"]
    cad = ctx["caducidad"]
    top = ctx["top_ventas"]
    lentos = ctx["baja_rotacion"]
    inv = ctx["inventario"]

    # Detectar si pregunta por un producto específico del catálogo
    for p in inv:
        if p["nombre_producto"].lower() in q or p["codigo_sku"].lower() in q:
            return (
                f"### 🔎 Análisis Específico: **{p['nombre_producto']}** (`{p['codigo_sku']}`)\n\n"
                f"- **Stock actual convertido:** **{p['stock_actual']} unidades** ({p['equivalencia_formato']}) | Mínimo de seguridad: {p['stock_minimo']} uds.\n"
                f"- **Peso registrado:** {p['peso_unitario_texto']} por unidad (**{p['peso_total_texto']}** totales en bodega).\n"
                f"- **Rentabilidad:** Costo {moneda(p['precio_compra'])} → Venta {moneda(p['precio_efectivo'])} (**Margen {p['porcentaje_margen']:.1f}%**).\n"
                f"- **Ventas acumuladas:** {p['unidades_vendidas_total']} unidades despachadas.\n"
                f"- **Estado de Caducidad:** **{p['etiqueta_caducidad']}** (Fecha: {p['fecha_caducidad_fmt']}).\n\n"
                + (
                    f"⚠️ **Acción inmediata:** Este lote está **vencido**. Retíralo de sala y regístralo en la pestaña *Ingresar Inventario y Mermas*."
                    if p["estado_caducidad"] == "VENCIDO"
                    else (
                        f"🏷️ **Recomendación comercial:** Quedan pocos días para su vencimiento. Activa una **oferta del 25% al 35%** desde el Chequeo de Inventario para recuperar los **{moneda(p['valor_stock_costo'])}** invertidos."
                        if p["estado_caducidad"] == "URGENTE"
                        else (
                            f"📦 **Recomendación de compra:** El stock está en nivel **{p['estado_stock']}**. Conviene reabastecer con **{p['nombre_proveedor']}**."
                            if p["estado_stock"] in ("AGOTADO", "CRITICO")
                            else "✅ **Diagnóstico:** Producto saludable en inventario y margen. Puedes incluirlo en combos promocionales para impulsar el ticket promedio."
                        )
                    )
                )
            )

    pide_compras = any(
        k in q
        for k in ("compr", "reabastec", "pedir", "proveedor", "stock", "reponer", "falt")
    )
    pide_ofertas = any(
        k in q
        for k in ("ofert", "descuent", "venc", "caduc", "liquid", "merma", "promoc")
    )
    pide_combos = any(
        k in q for k in ("combo", "pack", "ticket", "vender mas", "vender más", "rotaci", "estancad")
    )

    bloques: list[str] = []

    if pide_compras or (not pide_ofertas and not pide_combos):
        urgentes_c = [c for c in reab if "NECESARIO" in c["nivel_alerta"]]
        recom_c = [c for c in reab if c["nivel_alerta"] == "RECOMENDADO"]
        presupuesto_total = sum(c["costo_estimado_compra"] for c in reab)
        presupuesto_urg = sum(c["costo_estimado_compra"] for c in urgentes_c)

        lineas_u = "\n".join(
            f"1. **{c['nombre_producto']}** (`{c['codigo_sku']}`) — **{c['nivel_alerta']}**: "
            f"Tienes **{c['stock_actual']} uds** (mín. {c['stock_minimo']}). "
            f"Pide **{c['sugerencia_formato']}** a *{c['nombre_proveedor']}* "
            f"(demora {c['dias_entrega_estimados']} días) → Inversión est.: **{moneda(c['costo_estimado_compra'])}**."
            for c in urgentes_c[:5]
        ) or "- No tienes quiebres críticos de stock hoy."

        lineas_r = "\n".join(
            f"- **{c['nombre_producto']}** (`{c['codigo_sku']}`): Alta rotación (**{c['unidades_vendidas_30d']} uds/mes**). "
            f"Sugerido pedir **{c['sugerencia_formato']}** ({moneda(c['costo_estimado_compra'])}) antes de caer en quiebre."
            for c in recom_c[:4]
        )

        bloques.append(
            f"### 📦 Plan Inteligente de Próximas Compras\n"
            f"Guiándome por la velocidad real de ventas de los últimos 30 días y los tiempos de despacho de tus proveedores:\n\n"
            f"**Prioridad 1 — Reposición Inmediata (Presupuesto urgente: {moneda(presupuesto_urg)}):**\n"
            f"{lineas_u}\n\n"
            + (
                f"**Prioridad 2 — Productos de Alta Rotación (Preventivo):**\n{lineas_r}\n\n"
                if lineas_r
                else ""
            )
            + f"💡 *Presupuesto total sugerido para dejar toda la bodega en nivel óptimo:* **{moneda(presupuesto_total)}**."
        )

    if pide_ofertas or (not pide_compras and not pide_combos):
        vencidos = [a for a in cad if a["estado_caducidad"] == "VENCIDO"]
        por_vencer = [a for a in cad if a["estado_caducidad"] in ("URGENTE", "PROXIMO")]

        txt_venc = ""
        if vencidos:
            items_v = ", ".join(
                f"**{v['nombre_producto']}** ({v['stock_actual']} uds, {v['etiqueta_caducidad']})"
                for v in vencidos
            )
            txt_venc = (
                f"⚠️ **Alerta Sanitaria Inmediata:** Retira de sala {items_v} y regístralos como **Merma por Vencimiento** "
                f"(no deben ponerse en oferta).\n\n"
            )

        lineas_of = []
        for a in por_vencer[:5]:
            dcto = a["descuento_sugerido"]
            p_promo = round(a["precio_venta"] * (1.0 - dcto / 100.0))
            ganancia_unit = round(p_promo - a["precio_compra"])
            nota_margen = (
                f"aún ganas **{moneda(ganancia_unit)}/ud**"
                if ganancia_unit >= 0
                else f"recuperas **{moneda(p_promo)}/ud** de capital antes de perder el 100%"
            )
            lineas_of.append(
                f"- **{a['nombre_producto']}** ({a['etiqueta_caducidad']} — **{a['stock_actual']} uds**): "
                f"Bajar de {moneda(a['precio_venta'])} a **{moneda(p_promo)} (-{dcto}% dcto)** → {nota_margen}."
            )

        bloques.append(
            f"### 🏷️ Estrategia de Ofertas Anti-Vencimiento\n"
            f"{txt_venc}"
            + (
                "Para evitar que el stock próximo a caducar se convierta en pérdida, activa hoy estas promociones:\n\n"
                + "\n".join(lineas_of)
                + "\n\n👉 *Tip práctico: Puedes activar estos descuentos con 1 clic en la pestaña **Inicio** o en **Chequeo de Inventario**, y se aplicarán automáticamente en Caja.*"
                if lineas_of
                else "✅ No tienes productos próximos a vencer que requieran descuentos de liquidación hoy."
            )
        )

    if pide_combos or (not pide_compras and not pide_ofertas):
        estrella_1 = top[0] if len(top) > 0 else None
        estrella_2 = top[1] if len(top) > 1 else None
        candidato_urg = next(
            (a for a in cad if a["estado_caducidad"] in ("URGENTE", "PROXIMO") and a["stock_actual"] >= 4),
            None,
        )
        candidato_lento = lentos[0] if lentos else None

        ideas_combo = []
        if estrella_1 and candidato_urg and estrella_1["id_producto"] != candidato_urg["id_producto"]:
            suma_normal = estrella_1["ingresos_generados"] / max(1, estrella_1["unidades_vendidas"]) + candidato_urg["precio_venta"]
            precio_pack = round((suma_normal * 0.85) / 10) * 10
            ideas_combo.append(
                f"1. **Pack Desayuno / Colación Ahorro:** 1x *{estrella_1['nombre_producto']}* (tu #1 en ventas) + "
                f"1x *{candidato_urg['nombre_producto']}* (vence pronto, {candidato_urg['stock_actual']} uds en stock) "
                f"por **{moneda(precio_pack)}** (15% dcto al llevar ambos). Acelera de inmediato la salida del lote por vencer."
            )
        if estrella_2 and candidato_lento and estrella_2["id_producto"] != candidato_lento["id_producto"]:
            ideas_combo.append(
                f"2. **Combo Despensa Inteligente:** Al llevar 2x *{estrella_2['nombre_producto']}*, ofrece "
                f"*{candidato_lento['nombre_producto']}* (tienes {candidato_lento['stock_actual']} uds acumuladas) con **20% de descuento**."
            )
        ideas_combo.append(
            f"3. **Meta de Ticket Promedio:** Tu boleta promedio actual es de **{moneda(r['ticket_promedio_general'])}** "
            f"({r['promedio_unidades_por_venta']} uds). Ofrecer promoción *'3x2 en Snacks o Bebidas seleccionadas'* en caja puede elevar el ticket sobre **{moneda(r['ticket_promedio_general'] * 1.18)}**."
        )

        bloques.append(
            "### 🤝 Packs y Estrategias para Aumentar Ventas\n" + "\n".join(ideas_combo)
        )

    return "\n\n---\n\n".join(bloques)


def generar_respuesta_asistente(
    pregunta_usuario: str,
    historial_chat: list[dict[str, str]],
    proveedor_ia: str = "AUTO_GRATIS",
    api_key: str = "",
) -> tuple[str, str]:
    """
    Genera una recomendación comercial guiada por los datos actuales de la tienda.
    Retorna `(texto_respuesta, etiqueta_motor_usado)`.
    """
    ctx = construir_contexto_tienda()
    prompt_sistema = _formatear_prompt_sistema(ctx)

    mensajes_llm: list[dict[str, str]] = [{"role": "system", "content": prompt_sistema}]
    for msg in historial_chat[-6:]:
        rol = "assistant" if msg["role"] == "assistant" else "user"
        mensajes_llm.append({"role": rol, "content": msg["content"]})
    mensajes_llm.append({"role": "user", "content": pregunta_usuario})

    modo = proveedor_ia.upper()

    if modo == "GEMINI" and api_key.strip():
        try:
            resp = _consultar_gemini_gratis(prompt_sistema, pregunta_usuario, api_key)
            if resp:
                return resp, "Google Gemini 2.5 Flash (Gratis)"
        except Exception:
            pass

    if modo == "GROQ" and api_key.strip():
        try:
            resp = _consultar_groq_gratis(mensajes_llm, api_key)
            if resp:
                return resp, "Groq Llama 3.3 70B (Gratis)"
        except Exception:
            pass

    if modo in ("AUTO_GRATIS", "POLLINATIONS"):
        resp_nube = _consultar_pollinations_gratis(mensajes_llm)
        if resp_nube:
            return resp_nube, "IA Generativa en la Nube (Gratuita sin API Key)"

    # Respaldo instantáneo garantizado con el motor analítico local
    resp_local = _motor_analitico_local(pregunta_usuario, ctx)
    return resp_local, "Motor Analítico Inteligente Local (100% Gratuito)"
