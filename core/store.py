"""
Motor de persistencia en JSON y lógica de negocio (100% libre de SQL).
Mantiene todo el sistema de inventario, punto de venta (Caja), compras, mermas,
analítica de reabastecimiento e incorpora:
  - Ingreso por Unidad, Caja o Lote con conversión automática a Unidades.
  - Registro de peso/contenido neto unitario y cálculo de peso total en bodega.
  - Control de caducidad por lotes (FEFO: Primero en Vencer, Primero en Salir).
  - Gestión de descuentos promocionales rápidos para liquidar stock próximo a vencer.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
from typing import Any

DIRECTORIO_BASE = Path(__file__).resolve().parent.parent
DIRECTORIO_DATOS = DIRECTORIO_BASE / "data"
ARCHIVO_DATOS = DIRECTORIO_DATOS / "tienda_inventario.json"


class ErrorNegocio(Exception):
    """Error controlado de validación de reglas de negocio."""


def hash_password(texto: str) -> str:
    """Genera hash SHA-256 compatible con las credenciales originales."""
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def formatear_peso(valor: float, unidad: str) -> str:
    """Formatea un valor de peso o volumen de forma legible."""
    u = (unidad or "g").strip()
    if valor <= 0:
        return "N/A"
    if u == "g" and valor >= 1000:
        kg = valor / 1000.0
        return f"{kg:g} kg"
    if u == "ml" and valor >= 1000:
        litros = valor / 1000.0
        return f"{litros:g} L"
    return f"{valor:g} {u}"


def calcular_peso_total_stock(stock_unidades: int, peso_unitario: float, unidad: str) -> tuple[float, str]:
    """
    Calcula el peso/volumen total en bodega multiplicando unidades por peso unitario
    y normalizando a kg o L cuando corresponde para facilitar la lectura en inventario.
    """
    if stock_unidades <= 0 or peso_unitario <= 0:
        return 0.0, "0 kg"

    u = (unidad or "g").strip()
    bruto = stock_unidades * peso_unitario

    if u == "g":
        if bruto >= 1000:
            kg = round(bruto / 1000.0, 2)
            return kg, f"{kg:g} kg"
        return round(bruto, 1), f"{bruto:g} g"
    if u == "kg":
        kg = round(bruto, 2)
        return kg, f"{kg:g} kg"
    if u == "ml":
        if bruto >= 1000:
            litros = round(bruto / 1000.0, 2)
            return litros, f"{litros:g} L"
        return round(bruto, 1), f"{bruto:g} ml"
    if u == "L":
        litros = round(bruto, 2)
        return litros, f"{litros:g} L"

    return round(bruto, 2), f"{round(bruto, 2):g} {u}"


def calcular_equivalencia_formato(
    stock_unidades: int, formato: str, unidades_por_formato: int
) -> str:
    """Devuelve texto descriptivo de conversión entre Cajas/Lotes y Unidades."""
    fmt = (formato or "UNIDAD").upper()
    upf = max(1, int(unidades_por_formato or 1))
    if fmt == "UNIDAD" or upf <= 1:
        return "Ingreso unitario (1x1)"

    etiqueta_plural = "Cajas" if fmt == "CAJA" else "Lotes"
    etiqueta_sing = "Caja" if fmt == "CAJA" else "Lote"
    completos = stock_unidades // upf
    sueltas = stock_unidades % upf

    if stock_unidades == 0:
        return f"Formato {etiqueta_sing} × {upf} uds"
    if completos > 0 and sueltas > 0:
        nom = etiqueta_sing if completos == 1 else etiqueta_plural
        return f"{completos} {nom} (×{upf}u) + {sueltas} uds"
    if completos > 0:
        nom = etiqueta_sing if completos == 1 else etiqueta_plural
        return f"Equiv. {completos} {nom} × {upf} uds"
    return f"{sueltas} uds sueltas ({etiqueta_sing} ×{upf}u)"


def _sincronizar_caducidad_producto(prod: dict[str, Any]) -> None:
    """
    Sincroniza la fecha de caducidad principal del producto tomando el lote activo
    con unidades restantes que venza más pronto (criterio FEFO).
    """
    if not prod.get("perecible", False):
        prod["fecha_caducidad"] = None
        return

    lotes_activos = [
        lote
        for lote in prod.get("lotes", [])
        if int(lote.get("unidades_restantes", 0)) > 0 and lote.get("fecha_caducidad")
    ]
    if lotes_activos:
        lotes_activos.sort(key=lambda x: x["fecha_caducidad"])
        prod["fecha_caducidad"] = lotes_activos[0]["fecha_caducidad"]
    elif prod.get("stock_actual", 0) == 0:
        # Mantener última referencia o dejar None si no quedan unidades
        pass


def evaluar_estado_caducidad(
    perecible: bool, fecha_caducidad: str | None, stock_actual: int = 1
) -> dict[str, Any]:
    """
    Evalúa los días restantes hasta el vencimiento y clasifica la urgencia:
      - NO_PERECIBLE : No aplica caducidad
      - SIN_STOCK    : Perecible pero agotado actualmente
      - VENCIDO      : Días <= 0
      - URGENTE      : 1 a 7 días
      - PROXIMO      : 8 a 30 días
      - VIGENTE      : > 30 días
    """
    if not perecible or not fecha_caducidad:
        return {
            "estado_caducidad": "NO_PERECIBLE",
            "etiqueta_caducidad": "No perecible",
            "dias_para_vencer": None,
            "fecha_formateada": "No aplica",
        }

    try:
        fecha_obj = datetime.strptime(fecha_caducidad, "%Y-%m-%d").date()
    except ValueError:
        return {
            "estado_caducidad": "NO_PERECIBLE",
            "etiqueta_caducidad": "Sin fecha",
            "dias_para_vencer": None,
            "fecha_formateada": "Sin fecha",
        }

    hoy = date.today()
    dias = (fecha_obj - hoy).days
    fecha_fmt = fecha_obj.strftime("%d/%m/%Y")

    if stock_actual <= 0:
        return {
            "estado_caducidad": "SIN_STOCK",
            "etiqueta_caducidad": f"Sin stock ({fecha_fmt})",
            "dias_para_vencer": dias,
            "fecha_formateada": fecha_fmt,
        }

    if dias < 0:
        etiqueta = f"Vencido hace {abs(dias)}d"
        estado = "VENCIDO"
    elif dias == 0:
        etiqueta = "¡Vence HOY!"
        estado = "VENCIDO"
    elif dias <= 7:
        etiqueta = f"Vence en {dias} día{'s' if dias != 1 else ''}"
        estado = "URGENTE"
    elif dias <= 30:
        etiqueta = f"En {dias} días"
        estado = "PROXIMO"
    else:
        etiqueta = f"Vigente ({dias}d)"
        estado = "VIGENTE"

    return {
        "estado_caducidad": estado,
        "etiqueta_caducidad": etiqueta,
        "dias_para_vencer": dias,
        "fecha_formateada": fecha_fmt,
    }


def _generar_datos_semilla() -> dict[str, Any]:
    """
    Construye los datos semilla iniciales (sin SQL) manteniendo los productos,
    categorías, proveedores, usuarios y ventas del proyecto original, enriquecidos
    con formatos de Caja/Lote, pesos y fechas de caducidad dinámicas para el MVP PyME.
    """
    ahora = datetime.now()
    hoy = date.today()

    def f_cad(dias_offset: int) -> str:
        return (hoy + timedelta(days=dias_offset)).strftime("%Y-%m-%d")

    def f_ts(dias_atras: int, hora: int = 12, minuto: int = 30) -> str:
        dt = (ahora - timedelta(days=dias_atras)).replace(
            hour=hora, minute=minuto, second=0, microsecond=0
        )
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    usuarios = [
        {
            "id_usuario": 1,
            "nombre_completo": "María González (Dueña / Admin)",
            "username": "admin",
            "password_hash": "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9",  # admin123
            "rol": "Administrador",
            "activo": True,
        },
        {
            "id_usuario": 2,
            "nombre_completo": "Carlos Pérez (Cajero)",
            "username": "empleado",
            "password_hash": "682b1787210953a4a1f91a9eed757bc3b3e8827fd464a2d970db063a24b1526a",  # caja123
            "rol": "Empleado",
            "activo": True,
        },
    ]

    categorias = [
        {
            "id_categoria": 1,
            "nombre_categoria": "Bebidas y Lácteos",
            "descripcion": "Leches, yogures, jugos, aguas minerales y gaseosas",
        },
        {
            "id_categoria": 2,
            "nombre_categoria": "Abarrotes y Despensa",
            "descripcion": "Arroz, pastas, aceites, harinas y conservas",
        },
        {
            "id_categoria": 3,
            "nombre_categoria": "Snacks y Confitería",
            "descripcion": "Galletas, chocolates y aperitivos salados",
        },
        {
            "id_categoria": 4,
            "nombre_categoria": "Limpieza del Hogar",
            "descripcion": "Detergentes, desinfectantes y artículos de aseo",
        },
        {
            "id_categoria": 5,
            "nombre_categoria": "Cuidado Personal",
            "descripcion": "Jabones, shampoo, higiene dental y cuidado diario",
        },
    ]

    proveedores = [
        {
            "id_proveedor": 1,
            "nombre_proveedor": "Distribuidora Sur Lácteos S.A.",
            "telefono": "+56 9 8111 2233",
            "email": "pedidos@surlacteos.cl",
            "dias_entrega_estimados": 2,
            "activo": True,
        },
        {
            "id_proveedor": 2,
            "nombre_proveedor": "Mayorista Central Alimentos",
            "telefono": "+56 9 8444 5566",
            "email": "ventas@centralalimentos.cl",
            "dias_entrega_estimados": 4,
            "activo": True,
        },
        {
            "id_proveedor": 3,
            "nombre_proveedor": "Comercial AseoLimpio Ltda.",
            "telefono": "+56 9 8777 8899",
            "email": "contacto@aseolimpio.cl",
            "dias_entrega_estimados": 5,
            "activo": True,
        },
        {
            "id_proveedor": 4,
            "nombre_proveedor": "Importadora HigieneTotal",
            "telefono": "+56 9 8999 0011",
            "email": "despacho@higienetotal.cl",
            "dias_entrega_estimados": 3,
            "activo": True,
        },
    ]

    def crear_prod(
        id_p: int,
        sku: str,
        nombre: str,
        cat: int,
        prov: int | None,
        compra: float,
        venta: float,
        stock: int,
        minimo: int,
        formato: str,
        upf: int,
        peso_val: float,
        peso_u: str,
        perecible: bool,
        dias_vence: int | None,
        oferta_pct: float = 0.0,
    ) -> dict[str, Any]:
        fecha_cad = f_cad(dias_vence) if (perecible and dias_vence is not None) else None
        lotes = []
        if stock > 0:
            envases = max(1, round(stock / max(1, upf)))
            lotes.append(
                {
                    "id_lote": 1,
                    "codigo_lote": f"LT-{sku}-01",
                    "formato_ingreso": formato,
                    "cantidad_formato": envases,
                    "unidades_por_formato": upf,
                    "unidades_ingresadas": stock,
                    "unidades_restantes": stock,
                    "fecha_caducidad": fecha_cad,
                    "fecha_ingreso": f_ts(16, 9, 0),
                }
            )
        return {
            "id_producto": id_p,
            "codigo_sku": sku,
            "nombre_producto": nombre,
            "id_categoria": cat,
            "id_proveedor": prov,
            "precio_compra": float(compra),
            "precio_venta": float(venta),
            "descuento_oferta_pct": float(oferta_pct),
            "stock_actual": int(stock),
            "stock_minimo": int(minimo),
            "formato_habitual": formato,
            "unidades_por_formato": int(upf),
            "peso_unitario": float(peso_val),
            "unidad_peso": peso_u,
            "perecible": bool(perecible),
            "fecha_caducidad": fecha_cad,
            "lotes": lotes,
            "activo": True,
            "fecha_registro": f_ts(20, 8, 30),
        }

    productos = [
        crear_prod(
            1, "BEB-001", "Leche Entera 1L", 1, 1,
            850.0, 1250.0, 13, 10, "CAJA", 12, 1.0, "L", True, 6
        ),
        crear_prod(
            2, "BEB-002", "Agua Mineral Sin Gas 1.5L", 1, 1,
            500.0, 950.0, 35, 12, "LOTE", 6, 1.5, "L", True, 180
        ),
        crear_prod(
            3, "BEB-003", "Jugo Naranja Natural 1L", 1, 1,
            1100.0, 1690.0, 4, 8, "CAJA", 12, 1.0, "L", True, 2
        ),
        crear_prod(
            4, "ABA-001", "Arroz Grado 1 (1kg)", 2, 2,
            1050.0, 1590.0, 10, 8, "LOTE", 10, 1.0, "kg", True, 240
        ),
        crear_prod(
            5, "ABA-002", "Aceite Vegetal Maravilla 900ml", 2, 2,
            1650.0, 2390.0, 3, 8, "CAJA", 12, 900.0, "ml", True, 21
        ),
        crear_prod(
            6, "ABA-003", "Fideos Spaghetti 400g", 2, 2,
            620.0, 990.0, 42, 10, "CAJA", 20, 400.0, "g", True, 320
        ),
        crear_prod(
            7, "SNK-001", "Galletas Artesanales Avena", 3, None,
            900.0, 1500.0, 22, 6, "CAJA", 12, 250.0, "g", True, 5
        ),
        crear_prod(
            8, "SNK-002", "Papas Fritas Clásicas 150g", 3, 2,
            1200.0, 1990.0, 18, 8, "CAJA", 18, 150.0, "g", True, 14
        ),
        crear_prod(
            9, "LIM-001", "Detergente Líquido Ropa 3L", 4, 3,
            4200.0, 6490.0, 0, 5, "CAJA", 4, 3.0, "L", False, None
        ),
        crear_prod(
            10, "LIM-002", "Cloro Gel Desinfectante 1L", 4, 3,
            1150.0, 1850.0, 16, 6, "CAJA", 12, 1.0, "L", False, None
        ),
        crear_prod(
            11, "PER-001", "Shampoo Hidratante 400ml", 5, 4,
            2100.0, 3490.0, 5, 5, "CAJA", 12, 400.0, "ml", True, 365
        ),
        crear_prod(
            12, "PER-002", "Pasta Dental Triple Acción", 5, 4,
            980.0, 1650.0, 25, 7, "LOTE", 12, 120.0, "g", True, 19
        ),
        crear_prod(
            13, "BEB-004", "Yogurt Griego Natural 150g", 1, 1,
            520.0, 890.0, 6, 8, "LOTE", 6, 150.0, "g", True, -1
        ),
    ]

    mapa_prod = {p["id_producto"]: p for p in productos}

    def armar_venta(
        id_v: int, dias_atras: int, hora: int, lineas: list[tuple[int, int]], metodo: str = "Efectivo"
    ) -> dict[str, Any]:
        detalles = []
        total = 0.0
        for id_p, cant in lineas:
            pr = mapa_prod[id_p]
            pu = pr["precio_venta"]
            sub = round(cant * pu, 2)
            total += sub
            detalles.append(
                {
                    "id_producto": id_p,
                    "codigo_sku": pr["codigo_sku"],
                    "nombre_producto": pr["nombre_producto"],
                    "cantidad": cant,
                    "precio_lista": pu,
                    "descuento_pct": 0.0,
                    "precio_unitario": pu,
                    "subtotal": sub,
                }
            )
        total = round(total, 2)
        return {
            "id_venta": id_v,
            "numero_folio": f"BOL-{id_v:06d}",
            "id_usuario": 2,
            "responsable": "Carlos Pérez (Cajero)",
            "metodo_pago": metodo,
            "fecha_venta": f_ts(dias_atras, hora, 15),
            "subtotal": total,
            "descuento_total": 0.0,
            "total_venta": total,
            "estado": "COMPLETADA",
            "detalles": detalles,
        }

    ventas = [
        armar_venta(1, 14, 10, [(1, 4), (4, 3), (2, 4), (7, 1)], "Efectivo"),
        armar_venta(2, 12, 12, [(1, 5), (5, 3), (6, 4), (8, 2)], "Tarjeta Débito"),
        armar_venta(3, 10, 16, [(9, 2), (4, 4), (12, 2)], "Tarjeta Débito"),
        armar_venta(4, 8, 11, [(1, 4), (3, 3), (10, 3)], "Transferencia"),
        armar_venta(5, 6, 18, [(9, 2), (11, 2), (4, 4)], "Tarjeta Crédito"),
        armar_venta(6, 4, 13, [(1, 5), (8, 3), (6, 6)], "Efectivo"),
        armar_venta(7, 2, 17, [(1, 6), (2, 5), (4, 3), (12, 2)], "Tarjeta Débito"),
        armar_venta(8, 1, 11, [(1, 4), (3, 2), (7, 3), (10, 1)], "Efectivo"),
        armar_venta(9, 0, max(8, ahora.hour - 2), [(1, 2), (8, 2), (2, 3)], "Tarjeta Débito"),
    ]

    compras = [
        {
            "id_compra": 1,
            "id_proveedor": 1,
            "nombre_proveedor": "Distribuidora Sur Lácteos S.A.",
            "id_usuario": 1,
            "responsable": "María González (Dueña / Admin)",
            "numero_factura_proveedor": "FAC-10420",
            "fecha_compra": f_ts(7, 9, 40),
            "total": 33600.0,
            "estado": "COMPLETADA",
            "detalles": [
                {
                    "id_producto": 1,
                    "codigo_sku": "BEB-001",
                    "nombre_producto": "Leche Entera 1L",
                    "formato_ingreso": "CAJA",
                    "cantidad_formato": 2,
                    "unidades_por_formato": 12,
                    "cantidad": 24,
                    "precio_costo_unitario": 850.0,
                    "subtotal": 20400.0,
                    "fecha_caducidad": f_cad(6),
                },
                {
                    "id_producto": 3,
                    "codigo_sku": "BEB-003",
                    "nombre_producto": "Jugo Naranja Natural 1L",
                    "formato_ingreso": "CAJA",
                    "cantidad_formato": 1,
                    "unidades_por_formato": 12,
                    "cantidad": 12,
                    "precio_costo_unitario": 1100.0,
                    "subtotal": 13200.0,
                    "fecha_caducidad": f_cad(2),
                },
            ],
        }
    ]

    movimientos = [
        {
            "id_movimiento": 1,
            "id_producto": 3,
            "codigo_sku": "BEB-003",
            "nombre_producto": "Jugo Naranja Natural 1L",
            "tipo_movimiento": "MERMA",
            "cantidad": 2,
            "stock_anterior": 6,
            "stock_posterior": 4,
            "costo_unitario": 1100.0,
            "costo_total": 2200.0,
            "motivo": "VENCIMIENTO: Envases de lote anterior fuera de fecha en vitrina",
            "fecha": f_ts(3, 19, 10),
            "id_usuario": 1,
            "responsable": "María González (Dueña / Admin)",
        },
        {
            "id_movimiento": 2,
            "id_producto": 8,
            "codigo_sku": "SNK-002",
            "nombre_producto": "Papas Fritas Clásicas 150g",
            "tipo_movimiento": "MERMA",
            "cantidad": 1,
            "stock_anterior": 19,
            "stock_posterior": 18,
            "costo_unitario": 1200.0,
            "costo_total": 1200.0,
            "motivo": "DAÑO: Bolsa rota durante reposición de estantería",
            "fecha": f_ts(5, 15, 25),
            "id_usuario": 1,
            "responsable": "María González (Dueña / Admin)",
        },
    ]

    return {
        "meta": {
            "version": "2.0-pyme-mvp",
            "ultima_actualizacion": ahora.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "usuarios": usuarios,
        "categorias": categorias,
        "proveedores": proveedores,
        "productos": productos,
        "ventas": ventas,
        "compras": compras,
        "movimientos": movimientos,
    }


def cargar_datos() -> dict[str, Any]:
    """Carga el almacén JSON en memoria; si no existe, lo inicializa con datos semilla."""
    DIRECTORIO_DATOS.mkdir(parents=True, exist_ok=True)
    if not ARCHIVO_DATOS.exists():
        semilla = _generar_datos_semilla()
        guardar_datos(semilla)
        return semilla

    try:
        contenido = ARCHIVO_DATOS.read_text(encoding="utf-8")
        datos = json.loads(contenido)
        return datos
    except Exception:
        semilla = _generar_datos_semilla()
        guardar_datos(semilla)
        return semilla


def guardar_datos(datos: dict[str, Any]) -> None:
    """Persiste los datos de forma atómica en disco sin requerir ningún motor SQL."""
    DIRECTORIO_DATOS.mkdir(parents=True, exist_ok=True)
    datos.setdefault("meta", {})["ultima_actualizacion"] = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    ruta_tmp = ARCHIVO_DATOS.with_suffix(".tmp")
    ruta_tmp.write_text(
        json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ruta_tmp.replace(ARCHIVO_DATOS)


def restaurar_datos_demo() -> None:
    """Restaura los datos iniciales de demostración para presentaciones del taller."""
    semilla = _generar_datos_semilla()
    guardar_datos(semilla)


# ============================================================================
# AUTENTICACIÓN Y CATÁLOGOS
# ============================================================================


def autenticar_usuario(username: str, password: str) -> dict[str, Any]:
    """Valida credenciales de acceso y retorna los datos del usuario y su rol."""
    datos = cargar_datos()
    limpio = username.strip().lower()
    hash_ingresado = hash_password(password)

    for usr in datos["usuarios"]:
        if usr["username"].lower() == limpio:
            if usr["password_hash"] != hash_ingresado:
                raise ErrorNegocio("Usuario o contraseña incorrectos.")
            if not usr.get("activo", True):
                raise ErrorNegocio("Esta cuenta de usuario se encuentra deshabilitada.")
            return {
                "id_usuario": usr["id_usuario"],
                "nombre_completo": usr["nombre_completo"],
                "username": usr["username"],
                "rol": usr["rol"],
            }

    raise ErrorNegocio("Usuario o contraseña incorrectos.")


def obtener_catalogos() -> dict[str, list[dict[str, Any]]]:
    """Retorna categorías y proveedores activos ordenados alfabéticamente."""
    datos = cargar_datos()
    categorias = sorted(datos["categorias"], key=lambda c: c["nombre_categoria"])
    proveedores = sorted(
        [p for p in datos["proveedores"] if p.get("activo", True)],
        key=lambda p: p["nombre_proveedor"],
    )
    return {"categorias": categorias, "proveedores": proveedores}


# ============================================================================
# INVENTARIO CONSOLIDADO Y CADUCIDAD
# ============================================================================


def _calcular_unidades_vendidas_por_producto(
    ventas: list[dict[str, Any]], dias_ventana: int | None = None
) -> dict[int, int]:
    """Suma unidades vendidas por producto (histórico total o ventana de N días)."""
    conteo: dict[int, int] = {}
    limite_dt = (
        datetime.now() - timedelta(days=dias_ventana)
        if dias_ventana is not None
        else None
    )

    for v in ventas:
        if v.get("estado") != "COMPLETADA":
            continue
        if limite_dt is not None:
            try:
                f_venta = datetime.strptime(v["fecha_venta"], "%Y-%m-%d %H:%M:%S")
                if f_venta < limite_dt:
                    continue
            except ValueError:
                pass
        for det in v.get("detalles", []):
            idp = int(det["id_producto"])
            conteo[idp] = conteo.get(idp, 0) + int(det["cantidad"])

    return conteo


def obtener_inventario_consolidado(
    busqueda: str = "",
    id_categoria: int = 0,
    estado_stock: str = "",
    filtro_caducidad: str = "",
) -> list[dict[str, Any]]:
    """
    Construye el inventario consolidado convirtiendo todo el stock a Unidades,
    calculando peso unitario y peso total, estado de stock, márgenes y caducidad.
    """
    datos = cargar_datos()
    mapa_cat = {c["id_categoria"]: c["nombre_categoria"] for c in datos["categorias"]}
    mapa_prov = {
        p["id_proveedor"]: p["nombre_proveedor"] for p in datos["proveedores"]
    }
    vendidos_total = _calcular_unidades_vendidas_por_producto(datos["ventas"])

    termino = busqueda.strip().lower()
    est_filtro = estado_stock.strip().upper()
    cad_filtro = filtro_caducidad.strip().upper()

    resultado: list[dict[str, Any]] = []

    for p in datos["productos"]:
        if not p.get("activo", True):
            continue

        _sincronizar_caducidad_producto(p)

        sku = p["codigo_sku"]
        nombre = p["nombre_producto"]
        if termino and termino not in nombre.lower() and termino not in sku.lower():
            continue
        if id_categoria > 0 and int(p["id_categoria"]) != int(id_categoria):
            continue

        stock = int(p["stock_actual"])
        minimo = int(p["stock_minimo"])
        compra = float(p["precio_compra"])
        venta_lista = float(p["precio_venta"])
        oferta_pct = float(p.get("descuento_oferta_pct", 0.0) or 0.0)
        precio_efectivo = round(venta_lista * (1.0 - oferta_pct / 100.0), 2)

        if stock == 0:
            est_stock = "AGOTADO"
        elif stock <= minimo:
            est_stock = "CRITICO"
        elif stock <= int((minimo * 1.5) + 0.9999):
            est_stock = "BAJO"
        else:
            est_stock = "OPTIMO"

        if est_filtro and est_stock != est_filtro:
            continue

        info_cad = evaluar_estado_caducidad(
            bool(p.get("perecible", False)), p.get("fecha_caducidad"), stock
        )

        if cad_filtro:
            if cad_filtro == "ALERTA_CADUCIDAD":
                if info_cad["estado_caducidad"] not in ("VENCIDO", "URGENTE", "PROXIMO"):
                    continue
            elif info_cad["estado_caducidad"] != cad_filtro:
                continue

        margen_unit = round(precio_efectivo - compra, 2)
        pct_margen = (
            round((margen_unit / precio_efectivo) * 100.0, 1)
            if precio_efectivo > 0
            else 0.0
        )

        peso_u = float(p.get("peso_unitario", 0.0) or 0.0)
        unid_peso = p.get("unidad_peso", "g")
        _, peso_total_texto = calcular_peso_total_stock(stock, peso_u, unid_peso)

        formato_hab = p.get("formato_habitual", "UNIDAD")
        upf = int(p.get("unidades_por_formato", 1) or 1)

        resultado.append(
            {
                "id_producto": p["id_producto"],
                "codigo_sku": sku,
                "nombre_producto": nombre,
                "id_categoria": p["id_categoria"],
                "nombre_categoria": mapa_cat.get(p["id_categoria"], "Sin categoría"),
                "id_proveedor": p.get("id_proveedor"),
                "nombre_proveedor": mapa_prov.get(
                    p.get("id_proveedor"), "Sin proveedor asignado"
                ),
                "precio_compra": compra,
                "precio_venta": venta_lista,
                "descuento_oferta_pct": oferta_pct,
                "precio_efectivo": precio_efectivo,
                "margen_unitario": margen_unit,
                "porcentaje_margen": pct_margen,
                "stock_actual": stock,
                "stock_minimo": minimo,
                "valor_stock_costo": round(stock * compra, 2),
                "valor_stock_venta": round(stock * precio_efectivo, 2),
                "unidades_vendidas_total": vendidos_total.get(p["id_producto"], 0),
                "estado_stock": est_stock,
                "formato_habitual": formato_hab,
                "unidades_por_formato": upf,
                "equivalencia_formato": calcular_equivalencia_formato(
                    stock, formato_hab, upf
                ),
                "peso_unitario": peso_u,
                "unidad_peso": unid_peso,
                "peso_unitario_texto": formatear_peso(peso_u, unid_peso),
                "peso_total_texto": peso_total_texto,
                "perecible": bool(p.get("perecible", False)),
                "fecha_caducidad": p.get("fecha_caducidad"),
                "fecha_caducidad_fmt": info_cad["fecha_formateada"],
                "dias_para_vencer": info_cad["dias_para_vencer"],
                "estado_caducidad": info_cad["estado_caducidad"],
                "etiqueta_caducidad": info_cad["etiqueta_caducidad"],
                "lotes": p.get("lotes", []),
            }
        )

    orden_prioridad = {"AGOTADO": 1, "CRITICO": 2, "BAJO": 3, "OPTIMO": 4}
    resultado.sort(
        key=lambda r: (orden_prioridad.get(r["estado_stock"], 5), r["nombre_producto"])
    )
    return resultado


def obtener_alertas_caducidad(dias_umbral: int = 30) -> list[dict[str, Any]]:
    """
    Obtiene todos los productos activos con stock > 0 cuya fecha de caducidad esté
    vencida o dentro de los próximos `dias_umbral` días, ordenados desde el más urgente.
    Incluye sugerencias comerciales concretas para evitar pérdidas en la PyME.
    """
    inventario = obtener_inventario_consolidado()
    alertas: list[dict[str, Any]] = []

    for item in inventario:
        if not item["perecible"] or item["stock_actual"] <= 0:
            continue
        dias = item["dias_para_vencer"]
        if dias is None or dias > dias_umbral:
            continue

        if dias <= 0:
            accion = "Retirar de sala de inmediato y registrar baja por Merma (Vencimiento)."
            descuento_sugerido = 0
        elif dias <= 3:
            accion = "Liquidación urgente: Oferta 35% - 40% dcto o Pack 2x1 en caja hoy."
            descuento_sugerido = 35
        elif dias <= 7:
            accion = "Promoción activa: Aplicar 25% dcto o armar combo con producto estrella."
            descuento_sugerido = 25
        elif dias <= 15:
            accion = "Preventivo: Destacar en vitrina con 15% dcto por compra de 2+ unidades."
            descuento_sugerido = 15
        else:
            accion = "Monitorear salida FEFO (priorizar este lote en estantería frontal)."
            descuento_sugerido = 10

        alertas.append(
            {
                **item,
                "accion_recomendada": accion,
                "descuento_sugerido": descuento_sugerido,
            }
        )

    alertas.sort(key=lambda x: (x["dias_para_vencer"], -x["valor_stock_costo"]))
    return alertas


# ============================================================================
# OPERACIONES DE INGRESO (UNIDAD / CAJA / LOTE), ABASTECIMIENTO, OFERTAS Y MERMAS
# ============================================================================


def registrar_producto(
    *,
    codigo_sku: str,
    nombre_producto: str,
    id_categoria: int,
    id_proveedor: int | None,
    formato_ingreso: str,
    cantidad_formato: int,
    unidades_por_formato: int,
    modo_costo: str,
    costo_ingresado: float,
    precio_venta_unitario: float,
    stock_minimo_unidades: int,
    peso_unitario: float,
    unidad_peso: str,
    perecible: bool,
    fecha_caducidad: str | None,
    codigo_lote: str = "",
    usuario: dict[str, Any],
) -> dict[str, Any]:
    """
    Registra un nuevo producto convirtiendo automáticamente Cajas o Lotes a Unidades,
    calculando el costo unitario real, registrando su peso y su fecha de caducidad.
    """
    datos = cargar_datos()

    sku_limpio = codigo_sku.strip().upper()
    nombre_limpio = nombre_producto.strip()

    if len(sku_limpio) < 2:
        raise ErrorNegocio("El código SKU debe tener al menos 2 caracteres.")
    if len(nombre_limpio) < 2:
        raise ErrorNegocio("El nombre del producto es obligatorio.")

    for p in datos["productos"]:
        if p["codigo_sku"].upper() == sku_limpio:
            raise ErrorNegocio(f"Ya existe un producto registrado con el SKU '{sku_limpio}'.")

    formato = formato_ingreso.strip().upper()
    if formato not in ("UNIDAD", "CAJA", "LOTE"):
        formato = "UNIDAD"

    upf = 1 if formato == "UNIDAD" else int(unidades_por_formato)
    if upf <= 0:
        raise ErrorNegocio("Las unidades contenidas por Caja o Lote deben ser al menos 1.")

    cant_envases = int(cantidad_formato)
    if cant_envases < 0:
        raise ErrorNegocio("La cantidad inicial no puede ser negativa.")

    stock_unidades = cant_envases * upf

    if modo_costo == "POR_FORMATO" and formato in ("CAJA", "LOTE"):
        precio_compra_unit = round(float(costo_ingresado) / upf, 2)
    else:
        precio_compra_unit = round(float(costo_ingresado), 2)

    precio_venta = round(float(precio_venta_unitario), 2)
    if precio_compra_unit < 0 or precio_venta <= 0:
        raise ErrorNegocio("Los precios deben ser valores positivos válidos.")
    if precio_venta < precio_compra_unit:
        raise ErrorNegocio(
            f"El precio de venta unitario (${precio_venta:,.0f}) no puede ser menor al costo unitario calculado (${precio_compra_unit:,.0f})."
        )

    if peso_unitario <= 0:
        raise ErrorNegocio("Indique un peso o contenido neto mayor a cero para el producto.")

    fecha_cad_str = None
    if perecible:
        if not fecha_caducidad:
            raise ErrorNegocio("Debe indicar la fecha de caducidad para productos perecibles.")
        fecha_cad_str = fecha_caducidad.strip()

    nuevo_id = max((p["id_producto"] for p in datos["productos"]), default=0) + 1
    ahora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lote_tag = codigo_lote.strip() or f"LT-{sku_limpio}-01"

    lotes = []
    if stock_unidades > 0:
        lotes.append(
            {
                "id_lote": 1,
                "codigo_lote": lote_tag,
                "formato_ingreso": formato,
                "cantidad_formato": cant_envases,
                "unidades_por_formato": upf,
                "unidades_ingresadas": stock_unidades,
                "unidades_restantes": stock_unidades,
                "fecha_caducidad": fecha_cad_str,
                "fecha_ingreso": ahora_str,
            }
        )

    nuevo_prod = {
        "id_producto": nuevo_id,
        "codigo_sku": sku_limpio,
        "nombre_producto": nombre_limpio,
        "id_categoria": int(id_categoria),
        "id_proveedor": int(id_proveedor) if id_proveedor else None,
        "precio_compra": precio_compra_unit,
        "precio_venta": precio_venta,
        "descuento_oferta_pct": 0.0,
        "stock_actual": stock_unidades,
        "stock_minimo": max(0, int(stock_minimo_unidades)),
        "formato_habitual": formato,
        "unidades_por_formato": upf,
        "peso_unitario": float(peso_unitario),
        "unidad_peso": unidad_peso,
        "perecible": bool(perecible),
        "fecha_caducidad": fecha_cad_str,
        "lotes": lotes,
        "activo": True,
        "fecha_registro": ahora_str,
    }
    datos["productos"].append(nuevo_prod)

    if stock_unidades > 0:
        id_mov = max((m["id_movimiento"] for m in datos["movimientos"]), default=0) + 1
        desc_fmt = (
            f"{cant_envases} {formato.title()}(s) × {upf}u = {stock_unidades} uds"
            if formato != "UNIDAD"
            else f"{stock_unidades} unidades"
        )
        datos["movimientos"].append(
            {
                "id_movimiento": id_mov,
                "id_producto": nuevo_id,
                "codigo_sku": sku_limpio,
                "nombre_producto": nombre_limpio,
                "tipo_movimiento": "AJUSTE",
                "cantidad": stock_unidades,
                "stock_anterior": 0,
                "stock_posterior": stock_unidades,
                "costo_unitario": precio_compra_unit,
                "costo_total": round(stock_unidades * precio_compra_unit, 2),
                "motivo": f"ALTA INICIAL ({desc_fmt})",
                "fecha": ahora_str,
                "id_usuario": usuario["id_usuario"],
                "responsable": usuario["nombre_completo"],
            }
        )

    guardar_datos(datos)
    return nuevo_prod


def reabastecer_producto(
    *,
    id_producto: int,
    formato_ingreso: str,
    cantidad_formato: int,
    unidades_por_formato: int,
    id_proveedor: int | None = None,
    numero_factura: str = "",
    modo_costo: str = "POR_UNIDAD",
    costo_ingresado: float | None = None,
    fecha_caducidad: str | None = None,
    codigo_lote: str = "",
    usuario: dict[str, Any],
) -> dict[str, Any]:
    """
    Ingresa nuevo stock a un producto existente permitiendo elegir Unidad, Caja o Lote,
    convirtiendo automáticamente a unidades individuales y registrando su lote/caducidad.
    """
    datos = cargar_datos()
    prod = next(
        (
            p
            for p in datos["productos"]
            if p["id_producto"] == int(id_producto) and p.get("activo", True)
        ),
        None,
    )
    if not prod:
        raise ErrorNegocio("El producto seleccionado no existe o está inactivo.")

    formato = formato_ingreso.strip().upper()
    if formato not in ("UNIDAD", "CAJA", "LOTE"):
        formato = "UNIDAD"

    upf = 1 if formato == "UNIDAD" else int(unidades_por_formato)
    if upf <= 0:
        raise ErrorNegocio("Las unidades por Caja o Lote deben ser mayores a 0.")

    cant_envases = int(cantidad_formato)
    if cant_envases <= 0:
        raise ErrorNegocio("La cantidad a ingresar debe ser al menos 1.")

    unidades_ingreso = cant_envases * upf
    if unidades_ingreso > 50000:
        raise ErrorNegocio("La cantidad total convertida supera el límite de seguridad (50.000 uds).")

    costo_unit = prod["precio_compra"]
    if costo_ingresado is not None and costo_ingresado > 0:
        if modo_costo == "POR_FORMATO" and formato in ("CAJA", "LOTE"):
            costo_unit = round(float(costo_ingresado) / upf, 2)
        else:
            costo_unit = round(float(costo_ingresado), 2)
        if costo_unit <= prod["precio_venta"]:
            prod["precio_compra"] = costo_unit

    ahora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stock_ant = int(prod["stock_actual"])
    stock_post = stock_ant + unidades_ingreso
    prod["stock_actual"] = stock_post
    prod["formato_habitual"] = formato
    prod["unidades_por_formato"] = upf

    fecha_cad_lote = fecha_caducidad.strip() if fecha_caducidad else prod.get("fecha_caducidad")
    if fecha_cad_lote:
        prod["perecible"] = True

    lotes = prod.setdefault("lotes", [])
    nuevo_id_lote = max((l.get("id_lote", 0) for l in lotes), default=0) + 1
    lote_tag = codigo_lote.strip() or f"LT-{prod['codigo_sku']}-{nuevo_id_lote:02d}"

    lotes.append(
        {
            "id_lote": nuevo_id_lote,
            "codigo_lote": lote_tag,
            "formato_ingreso": formato,
            "cantidad_formato": cant_envases,
            "unidades_por_formato": upf,
            "unidades_ingresadas": unidades_ingreso,
            "unidades_restantes": unidades_ingreso,
            "fecha_caducidad": fecha_cad_lote,
            "fecha_ingreso": ahora_str,
        }
    )
    _sincronizar_caducidad_producto(prod)

    factura_limpia = numero_factura.strip().upper()
    es_compra = bool(id_proveedor and factura_limpia)

    if es_compra:
        prov = next(
            (pr for pr in datos["proveedores"] if pr["id_proveedor"] == int(id_proveedor)),
            None,
        )
        if not prov:
            raise ErrorNegocio("El proveedor indicado no existe.")
        for comp in datos["compras"]:
            if (
                comp["id_proveedor"] == int(id_proveedor)
                and comp["numero_factura_proveedor"].upper() == factura_limpia
            ):
                raise ErrorNegocio(
                    f"Ya existe una compra registrada con la factura '{factura_limpia}' para este proveedor."
                )

        id_comp = max((c["id_compra"] for c in datos["compras"]), default=0) + 1
        subtotal_compra = round(unidades_ingreso * costo_unit, 2)
        datos["compras"].append(
            {
                "id_compra": id_comp,
                "id_proveedor": int(id_proveedor),
                "nombre_proveedor": prov["nombre_proveedor"],
                "id_usuario": usuario["id_usuario"],
                "responsable": usuario["nombre_completo"],
                "numero_factura_proveedor": factura_limpia,
                "fecha_compra": ahora_str,
                "total": subtotal_compra,
                "estado": "COMPLETADA",
                "detalles": [
                    {
                        "id_producto": prod["id_producto"],
                        "codigo_sku": prod["codigo_sku"],
                        "nombre_producto": prod["nombre_producto"],
                        "formato_ingreso": formato,
                        "cantidad_formato": cant_envases,
                        "unidades_por_formato": upf,
                        "cantidad": unidades_ingreso,
                        "precio_costo_unitario": costo_unit,
                        "subtotal": subtotal_compra,
                        "fecha_caducidad": fecha_cad_lote,
                    }
                ],
            }
        )
        tipo_mov = "ENTRADA_COMPRA"
        motivo_mov = f"COMPRA {factura_limpia} ({cant_envases} {formato} × {upf}u)"
    else:
        tipo_mov = "AJUSTE"
        motivo_mov = (
            f"INGRESO BODEGA ({cant_envases} {formato} × {upf}u = {unidades_ingreso} uds)"
            if formato != "UNIDAD"
            else f"INGRESO BODEGA ({unidades_ingreso} uds)"
        )

    id_mov = max((m["id_movimiento"] for m in datos["movimientos"]), default=0) + 1
    datos["movimientos"].append(
        {
            "id_movimiento": id_mov,
            "id_producto": prod["id_producto"],
            "codigo_sku": prod["codigo_sku"],
            "nombre_producto": prod["nombre_producto"],
            "tipo_movimiento": tipo_mov,
            "cantidad": unidades_ingreso,
            "stock_anterior": stock_ant,
            "stock_posterior": stock_post,
            "costo_unitario": costo_unit,
            "costo_total": round(unidades_ingreso * costo_unit, 2),
            "motivo": motivo_mov,
            "fecha": ahora_str,
            "id_usuario": usuario["id_usuario"],
            "responsable": usuario["nombre_completo"],
        }
    )

    guardar_datos(datos)
    return {
        "id_producto": prod["id_producto"],
        "codigo_sku": prod["codigo_sku"],
        "nombre_producto": prod["nombre_producto"],
        "unidades_ingresadas": unidades_ingreso,
        "stock_posterior": stock_post,
        "formato": formato,
        "cantidad_formato": cant_envases,
        "unidades_por_formato": upf,
        "fecha_caducidad": prod.get("fecha_caducidad"),
    }


def aplicar_oferta_producto(id_producto: int, descuento_pct: float) -> dict[str, Any]:
    """Activa o desactiva un porcentaje de descuento promocional sobre un producto."""
    if descuento_pct < 0 or descuento_pct > 70:
        raise ErrorNegocio("El descuento promocional debe estar entre 0% y 70%.")

    datos = cargar_datos()
    prod = next(
        (p for p in datos["productos"] if p["id_producto"] == int(id_producto)),
        None,
    )
    if not prod:
        raise ErrorNegocio("Producto no encontrado.")

    prod["descuento_oferta_pct"] = round(float(descuento_pct), 1)
    guardar_datos(datos)
    precio_nuevo = round(prod["precio_venta"] * (1.0 - prod["descuento_oferta_pct"] / 100.0), 2)
    return {
        "nombre_producto": prod["nombre_producto"],
        "descuento_oferta_pct": prod["descuento_oferta_pct"],
        "precio_lista": prod["precio_venta"],
        "precio_oferta": precio_nuevo,
    }


def _descontar_unidades_fefo(prod: dict[str, Any], cantidad_descontar: int) -> None:
    """Descuenta unidades empezando por los lotes con fecha de caducidad más próxima (FEFO)."""
    restante = int(cantidad_descontar)
    lotes = prod.get("lotes", [])
    lotes_con_stock = [l for l in lotes if int(l.get("unidades_restantes", 0)) > 0]
    lotes_con_stock.sort(
        key=lambda l: (
            0 if l.get("fecha_caducidad") else 1,
            l.get("fecha_caducidad") or "9999-12-31",
            l.get("id_lote", 0),
        )
    )

    for lote in lotes_con_stock:
        if restante <= 0:
            break
        disp = int(lote["unidades_restantes"])
        usar = min(disp, restante)
        lote["unidades_restantes"] = disp - usar
        restante -= usar

    _sincronizar_caducidad_producto(prod)


def registrar_merma(
    *,
    id_producto: int,
    causa: str,
    cantidad: int,
    observacion: str,
    desactivar_producto: bool,
    usuario: dict[str, Any],
) -> dict[str, Any]:
    """Registra una pérdida (vencimiento, daño, robo) descontando stock con criterio FEFO."""
    datos = cargar_datos()
    prod = next(
        (
            p
            for p in datos["productos"]
            if p["id_producto"] == int(id_producto) and p.get("activo", True)
        ),
        None,
    )
    if not prod:
        raise ErrorNegocio("El producto seleccionado no existe o ya fue dado de baja.")

    cant = int(cantidad)
    if not desactivar_producto and cant <= 0:
        raise ErrorNegocio("La cantidad a descontar por pérdida debe ser de al menos 1 unidad.")
    if cant < 0:
        raise ErrorNegocio("La cantidad no puede ser negativa.")
    if cant > int(prod["stock_actual"]):
        raise ErrorNegocio(
            f"No se pueden descontar {cant} unidades de '{prod['nombre_producto']}' "
            f"porque su stock actual es de {prod['stock_actual']} unidades."
        )

    stock_ant = int(prod["stock_actual"])
    stock_post = stock_ant - cant
    prod["stock_actual"] = stock_post

    if cant > 0:
        _descontar_unidades_fefo(prod, cant)

    if desactivar_producto:
        prod["activo"] = False

    causa_limpia = causa.strip().upper()
    obs_limpia = observacion.strip()
    motivo = f"{causa_limpia}: {obs_limpia}" if obs_limpia else causa_limpia
    costo_estimado = round(cant * float(prod["precio_compra"]), 2)

    if cant > 0:
        id_mov = max((m["id_movimiento"] for m in datos["movimientos"]), default=0) + 1
        datos["movimientos"].append(
            {
                "id_movimiento": id_mov,
                "id_producto": prod["id_producto"],
                "codigo_sku": prod["codigo_sku"],
                "nombre_producto": prod["nombre_producto"],
                "tipo_movimiento": "MERMA",
                "cantidad": cant,
                "stock_anterior": stock_ant,
                "stock_posterior": stock_post,
                "costo_unitario": float(prod["precio_compra"]),
                "costo_total": costo_estimado,
                "motivo": motivo,
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "id_usuario": usuario["id_usuario"],
                "responsable": usuario["nombre_completo"],
            }
        )

    guardar_datos(datos)
    return {
        "id_producto": prod["id_producto"],
        "nombre_producto": prod["nombre_producto"],
        "cantidad": cant,
        "stock_anterior": stock_ant,
        "stock_posterior": stock_post,
        "costo_estimado": costo_estimado,
        "activo": prod["activo"],
    }


# ============================================================================
# PUNTO DE VENTA (CAJA)
# ============================================================================


def procesar_venta(
    *,
    items_carrito: list[dict[str, Any]],
    metodo_pago: str = "Efectivo",
    descuento_adicional_pct: float = 0.0,
    usuario: dict[str, Any],
) -> dict[str, Any]:
    """
    Ejecuta una venta en Caja validando disponibilidad, aplicando ofertas activas,
    descontando stock por FEFO (lote más próximo a vencer primero) y emitiendo comprobante.
    """
    if not items_carrito:
        raise ErrorNegocio("El carrito de venta está vacío.")

    datos = cargar_datos()
    mapa_prod = {
        p["id_producto"]: p for p in datos["productos"] if p.get("activo", True)
    }

    consolidado: dict[int, int] = {}
    for item in items_carrito:
        idp = int(item["id_producto"])
        cant = int(item["cantidad"])
        if cant <= 0:
            raise ErrorNegocio("Todas las cantidades del carrito deben ser mayores a cero.")
        consolidado[idp] = consolidado.get(idp, 0) + cant

    # Validar disponibilidad antes de modificar
    for idp, cant in consolidado.items():
        prod = mapa_prod.get(idp)
        if not prod:
            raise ErrorNegocio("Uno de los productos seleccionados ya no está disponible.")
        if int(prod["stock_actual"]) < cant:
            raise ErrorNegocio(
                f"Stock insuficiente para '{prod['nombre_producto']}'. "
                f"Solicitado: {cant}, Disponible: {prod['stock_actual']} uds."
            )

    ahora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    id_nueva_venta = max((v["id_venta"] for v in datos["ventas"]), default=0) + 1
    folio = f"BOL-{id_nueva_venta:06d}"

    detalles_venta = []
    subtotal_bruto = 0.0
    total_final = 0.0
    dcto_extra = max(0.0, min(50.0, float(descuento_adicional_pct or 0.0)))

    id_mov_actual = max((m["id_movimiento"] for m in datos["movimientos"]), default=0)

    for idp, cant in consolidado.items():
        prod = mapa_prod[idp]
        precio_lista = float(prod["precio_venta"])
        dcto_prod = float(prod.get("descuento_oferta_pct", 0.0) or 0.0)
        dcto_combinado = min(70.0, round(dcto_prod + dcto_extra, 1))
        precio_unit_final = round(precio_lista * (1.0 - dcto_combinado / 100.0), 2)
        sub_linea = round(cant * precio_unit_final, 2)

        subtotal_bruto += round(cant * precio_lista, 2)
        total_final += sub_linea

        stock_ant = int(prod["stock_actual"])
        stock_post = stock_ant - cant
        prod["stock_actual"] = stock_post
        _descontar_unidades_fefo(prod, cant)

        detalles_venta.append(
            {
                "id_producto": idp,
                "codigo_sku": prod["codigo_sku"],
                "nombre_producto": prod["nombre_producto"],
                "cantidad": cant,
                "precio_lista": precio_lista,
                "descuento_pct": dcto_combinado,
                "precio_unitario": precio_unit_final,
                "subtotal": sub_linea,
            }
        )

        id_mov_actual += 1
        datos["movimientos"].append(
            {
                "id_movimiento": id_mov_actual,
                "id_producto": idp,
                "codigo_sku": prod["codigo_sku"],
                "nombre_producto": prod["nombre_producto"],
                "tipo_movimiento": "SALIDA_VENTA",
                "cantidad": cant,
                "stock_anterior": stock_ant,
                "stock_posterior": stock_post,
                "costo_unitario": float(prod["precio_compra"]),
                "costo_total": round(cant * float(prod["precio_compra"]), 2),
                "motivo": f"VENTA EN CAJA ({folio})",
                "fecha": ahora_str,
                "id_usuario": usuario["id_usuario"],
                "responsable": usuario["nombre_completo"],
            }
        )

    subtotal_bruto = round(subtotal_bruto, 2)
    total_final = round(total_final, 2)
    descuento_pesos = round(max(0.0, subtotal_bruto - total_final), 2)

    registro_venta = {
        "id_venta": id_nueva_venta,
        "numero_folio": folio,
        "id_usuario": usuario["id_usuario"],
        "responsable": usuario["nombre_completo"],
        "metodo_pago": metodo_pago,
        "fecha_venta": ahora_str,
        "subtotal": subtotal_bruto,
        "descuento_total": descuento_pesos,
        "total_venta": total_final,
        "estado": "COMPLETADA",
        "detalles": detalles_venta,
    }
    datos["ventas"].append(registro_venta)
    guardar_datos(datos)
    return registro_venta


def obtener_ultimas_ventas(id_usuario: int | None = None, limite: int = 10) -> list[dict[str, Any]]:
    """Retorna las ventas completadas más recientes."""
    datos = cargar_datos()
    filtradas = [
        v
        for v in datos["ventas"]
        if v.get("estado") == "COMPLETADA"
        and (id_usuario is None or v.get("id_usuario") == id_usuario)
    ]
    filtradas.sort(key=lambda v: (v["fecha_venta"], v["id_venta"]), reverse=True)
    res = []
    for v in filtradas[:limite]:
        lineas = len(v.get("detalles", []))
        unidades = sum(int(d["cantidad"]) for d in v.get("detalles", []))
        res.append(
            {
                **v,
                "lineas_distintas": lineas,
                "total_unidades": unidades,
            }
        )
    return res


# ============================================================================
# ANALÍTICA, REABASTECIMIENTO E HISTORIALES
# ============================================================================


def obtener_resumen_ejecutivo() -> dict[str, Any]:
    """Calcula todos los KPIs globales del negocio para la Pestaña Principal."""
    datos = cargar_datos()
    mapa_costo = {p["id_producto"]: float(p["precio_compra"]) for p in datos["productos"]}

    ventas_ok = [v for v in datos["ventas"] if v.get("estado") == "COMPLETADA"]
    total_ventas = len(ventas_ok)
    ingresos_totales = round(sum(float(v["total_venta"]) for v in ventas_ok), 2)

    utilidad_acumulada = 0.0
    unidades_totales_vendidas = 0
    totales_por_ticket: list[float] = []
    unidades_por_ticket: list[int] = []

    for v in ventas_ok:
        totales_por_ticket.append(float(v["total_venta"]))
        uds_v = 0
        for d in v.get("detalles", []):
            cant = int(d["cantidad"])
            uds_v += cant
            costo_u = mapa_costo.get(int(d["id_producto"]), 0.0)
            utilidad_acumulada += (float(d["precio_unitario"]) - costo_u) * cant
        unidades_totales_vendidas += uds_v
        unidades_por_ticket.append(uds_v)

    ticket_promedio = (
        round(ingresos_totales / total_ventas, 2) if total_ventas > 0 else 0.0
    )
    prom_unidades = (
        round(sum(unidades_por_ticket) / total_ventas, 1) if total_ventas > 0 else 0.0
    )
    venta_min = min(totales_por_ticket) if totales_por_ticket else 0.0
    venta_max = max(totales_por_ticket) if totales_por_ticket else 0.0

    inventario = obtener_inventario_consolidado()
    valor_bodega_costo = round(sum(i["valor_stock_costo"] for i in inventario), 2)
    valor_bodega_venta = round(sum(i["valor_stock_venta"] for i in inventario), 2)
    stock_alerta = sum(
        1 for i in inventario if i["estado_stock"] in ("AGOTADO", "CRITICO")
    )

    alertas_cad = obtener_alertas_caducidad(dias_umbral=30)
    vencidos_count = sum(1 for a in alertas_cad if a["estado_caducidad"] == "VENCIDO")
    urgentes_count = sum(
        1 for a in alertas_cad if a["estado_caducidad"] in ("VENCIDO", "URGENTE")
    )
    valor_riesgo_caducidad = round(
        sum(a["valor_stock_costo"] for a in alertas_cad), 2
    )

    mermas = [m for m in datos["movimientos"] if m.get("tipo_movimiento") == "MERMA"]
    costo_mermas = round(sum(float(m.get("costo_total", 0.0)) for m in mermas), 2)

    return {
        "total_ventas_completadas": total_ventas,
        "ingresos_acumulados": ingresos_totales,
        "utilidad_estimada_total": round(utilidad_acumulada, 2),
        "unidades_totales_vendidas": unidades_totales_vendidas,
        "ticket_promedio_general": ticket_promedio,
        "promedio_unidades_por_venta": prom_unidades,
        "venta_minima": venta_min,
        "venta_maxima": venta_max,
        "total_productos_activos": len(inventario),
        "valor_bodega_costo": valor_bodega_costo,
        "valor_bodega_venta": valor_bodega_venta,
        "productos_stock_critico": stock_alerta,
        "productos_proximos_vencer": len(alertas_cad),
        "productos_vencidos": vencidos_count,
        "productos_caducidad_urgente": urgentes_count,
        "valor_riesgo_caducidad": valor_riesgo_caducidad,
        "costo_total_mermas": costo_mermas,
    }


def obtener_promedios_por_categoria() -> list[dict[str, Any]]:
    """Agrupa métricas y promedios de ventas por categoría de producto."""
    datos = cargar_datos()
    mapa_prod = {p["id_producto"]: p for p in datos["productos"]}
    mapa_cat = {c["id_categoria"]: c["nombre_categoria"] for c in datos["categorias"]}

    acum: dict[int, dict[str, Any]] = {}
    for v in datos["ventas"]:
        if v.get("estado") != "COMPLETADA":
            continue
        id_v = v["id_venta"]
        for d in v.get("detalles", []):
            prod = mapa_prod.get(int(d["id_producto"]))
            if not prod:
                continue
            idc = int(prod["id_categoria"])
            nodo = acum.setdefault(
                idc,
                {
                    "productos_set": set(),
                    "ventas_set": set(),
                    "unidades": 0,
                    "ingresos": 0.0,
                    "lineas": 0,
                    "suma_precios": 0.0,
                },
            )
            nodo["productos_set"].add(prod["id_producto"])
            nodo["ventas_set"].add(id_v)
            nodo["unidades"] += int(d["cantidad"])
            nodo["ingresos"] += float(d["subtotal"])
            nodo["lineas"] += 1
            nodo["suma_precios"] += float(d["precio_unitario"])

    salida = []
    for idc, info in acum.items():
        n_tx = len(info["ventas_set"])
        n_lin = info["lineas"]
        salida.append(
            {
                "id_categoria": idc,
                "nombre_categoria": mapa_cat.get(idc, "Otra"),
                "productos_distintos_vendidos": len(info["productos_set"]),
                "total_transacciones": n_tx,
                "total_unidades_vendidas": info["unidades"],
                "ingresos_categoria": round(info["ingresos"], 2),
                "promedio_importe_por_linea": round(info["ingresos"] / n_lin, 2) if n_lin else 0.0,
                "ticket_promedio_categoria": round(info["ingresos"] / n_tx, 2) if n_tx else 0.0,
                "precio_unitario_promedio": round(info["suma_precios"] / n_lin, 2) if n_lin else 0.0,
                "promedio_unidades_por_transaccion": round(info["unidades"] / n_tx, 1) if n_tx else 0.0,
            }
        )

    salida.sort(key=lambda x: x["ingresos_categoria"], reverse=True)
    return salida


def obtener_productos_mas_vendidos(limite: int = 10) -> list[dict[str, Any]]:
    """Calcula el ranking de productos más vendidos, ingresos y utilidad estimada."""
    datos = cargar_datos()
    mapa_prod = {p["id_producto"]: p for p in datos["productos"]}
    mapa_cat = {c["id_categoria"]: c["nombre_categoria"] for c in datos["categorias"]}

    agrup: dict[int, dict[str, Any]] = {}
    for v in datos["ventas"]:
        if v.get("estado") != "COMPLETADA":
            continue
        id_v = v["id_venta"]
        for d in v.get("detalles", []):
            idp = int(d["id_producto"])
            prod = mapa_prod.get(idp)
            if not prod:
                continue
            cant = int(d["cantidad"])
            sub = float(d["subtotal"])
            util = (float(d["precio_unitario"]) - float(prod["precio_compra"])) * cant

            item = agrup.setdefault(
                idp,
                {
                    "unidades_vendidas": 0,
                    "ventas_set": set(),
                    "ingresos_generados": 0.0,
                    "utilidad_estimada": 0.0,
                    "lineas": 0,
                },
            )
            item["unidades_vendidas"] += cant
            item["ventas_set"].add(id_v)
            item["ingresos_generados"] += sub
            item["utilidad_estimada"] += util
            item["lineas"] += 1

    lista = []
    for idp, met in agrup.items():
        prod = mapa_prod[idp]
        n_ventas = len(met["ventas_set"])
        lista.append(
            {
                "id_producto": idp,
                "codigo_sku": prod["codigo_sku"],
                "nombre_producto": prod["nombre_producto"],
                "nombre_categoria": mapa_cat.get(prod["id_categoria"], "Sin categoría"),
                "unidades_vendidas": met["unidades_vendidas"],
                "numero_ventas": n_ventas,
                "ingresos_generados": round(met["ingresos_generados"], 2),
                "utilidad_estimada": round(met["utilidad_estimada"], 2),
                "promedio_unidades_por_ticket": round(
                    met["unidades_vendidas"] / n_ventas, 1
                )
                if n_ventas
                else 0.0,
                "stock_actual": int(prod["stock_actual"]),
            }
        )

    lista.sort(
        key=lambda x: (x["unidades_vendidas"], x["ingresos_generados"]), reverse=True
    )
    for idx, elem in enumerate(lista[:limite], start=1):
        elem["ranking"] = idx
    return lista[:limite]


def obtener_recomendaciones_reabastecimiento(nivel_alerta: str = "") -> list[dict[str, Any]]:
    """
    Calcula las necesidades de reposición (NECESARIO vs RECOMENDADO) según rotación
    de los últimos 30 días, tiempo de entrega del proveedor y formato de compra.
    """
    datos = cargar_datos()
    mapa_cat = {c["id_categoria"]: c["nombre_categoria"] for c in datos["categorias"]}
    mapa_prov = {p["id_proveedor"]: p for p in datos["proveedores"]}
    rotacion_30d = _calcular_unidades_vendidas_por_producto(datos["ventas"], dias_ventana=30)

    filtro = nivel_alerta.strip().upper()
    sugerencias = []

    for p in datos["productos"]:
        if not p.get("activo", True):
            continue
        idp = p["id_producto"]
        prov = mapa_prov.get(p.get("id_proveedor"))
        nombre_prov = prov["nombre_proveedor"] if prov else "Sin proveedor asignado"
        dias_entrega = int(prov["dias_entrega_estimados"]) if prov else 3

        stock = int(p["stock_actual"])
        minimo = int(p["stock_minimo"])
        vend_30d = rotacion_30d.get(idp, 0)
        prom_diario = round(vend_30d / 30.0, 2)

        demanda_cobertura = int((prom_diario * (dias_entrega + 7)) + 0.9999)
        punto_reorden = minimo + demanda_cobertura

        if stock > punto_reorden:
            continue

        stock_objetivo = punto_reorden + (minimo if minimo > 0 else 5)
        cant_sugerida = max(1, stock_objetivo - stock)

        if stock == 0:
            alerta = "NECESARIO (AGOTADO)"
        elif stock <= minimo:
            alerta = "NECESARIO"
        else:
            alerta = "RECOMENDADO"

        if filtro and not alerta.startswith(filtro):
            continue

        formato = p.get("formato_habitual", "UNIDAD")
        upf = max(1, int(p.get("unidades_por_formato", 1) or 1))
        if formato in ("CAJA", "LOTE") and upf > 1:
            cajas_sug = max(1, int((cant_sugerida + upf - 1) // upf))
            sugerencia_formato = f"{cajas_sug} {formato.title()}(s) ({cajas_sug * upf} uds)"
        else:
            sugerencia_formato = f"{cant_sugerida} unidades"

        sugerencias.append(
            {
                "id_producto": idp,
                "codigo_sku": p["codigo_sku"],
                "nombre_producto": p["nombre_producto"],
                "nombre_categoria": mapa_cat.get(p["id_categoria"], "Sin categoría"),
                "nombre_proveedor": nombre_prov,
                "dias_entrega_estimados": dias_entrega,
                "stock_actual": stock,
                "stock_minimo": minimo,
                "precio_compra": float(p["precio_compra"]),
                "unidades_vendidas_30d": vend_30d,
                "promedio_venta_diaria": prom_diario,
                "punto_reorden": punto_reorden,
                "stock_objetivo": stock_objetivo,
                "nivel_alerta": alerta,
                "cantidad_sugerida": cant_sugerida,
                "sugerencia_formato": sugerencia_formato,
                "costo_estimado_compra": round(cant_sugerida * float(p["precio_compra"]), 2),
            }
        )

    orden = {"NECESARIO (AGOTADO)": 1, "NECESARIO": 2, "RECOMENDADO": 3}
    sugerencias.sort(
        key=lambda s: (orden.get(s["nivel_alerta"], 4), -s["cantidad_sugerida"])
    )
    return sugerencias


def obtener_serie_ventas_tiempo(rango: str = "15d") -> dict[str, Any]:
    """Construye la serie temporal continua de ventas para el gráfico SVG."""
    datos = cargar_datos()
    ventas_ok = [v for v in datos["ventas"] if v.get("estado") == "COMPLETADA"]
    rango_limpio = rango.strip().lower()
    ahora = datetime.now()

    serie: list[dict[str, Any]] = []

    if rango_limpio == "24h":
        hora_fin = ahora.replace(minute=0, second=0, microsecond=0)
        cubetas: dict[str, dict[str, Any]] = {}
        for i in range(23, -1, -1):
            h = hora_fin - timedelta(hours=i)
            clave = h.strftime("%Y-%m-%d %H:00")
            cubetas[clave] = {
                "fecha_iso": clave,
                "etiqueta": h.strftime("%H:%M"),
                "cantidad_ventas": 0,
                "unidades_vendidas": 0,
                "total_ventas": 0.0,
            }

        limite_24h = ahora - timedelta(hours=24)
        for v in ventas_ok:
            try:
                dt = datetime.strptime(v["fecha_venta"], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            if dt < limite_24h:
                continue
            clave = dt.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:00")
            if clave in cubetas:
                cubetas[clave]["cantidad_ventas"] += 1
                cubetas[clave]["total_ventas"] = round(
                    cubetas[clave]["total_ventas"] + float(v["total_venta"]), 2
                )
                cubetas[clave]["unidades_vendidas"] += sum(
                    int(d["cantidad"]) for d in v.get("detalles", [])
                )
        serie = list(cubetas.values())
        modo = "hora"
    else:
        hoy = date.today()
        mapa_dias = {"7d": 7, "15d": 15, "30d": 30}
        if rango_limpio in mapa_dias:
            dias = mapa_dias[rango_limpio]
            fecha_inicio = hoy - timedelta(days=dias - 1)
        else:
            fechas_v = []
            for v in ventas_ok:
                try:
                    fechas_v.append(
                        datetime.strptime(v["fecha_venta"], "%Y-%m-%d %H:%M:%S").date()
                    )
                except ValueError:
                    pass
            fecha_inicio = min(fechas_v) if fechas_v else (hoy - timedelta(days=14))

        cubetas_d: dict[str, dict[str, Any]] = {}
        cursor_f = fecha_inicio
        while cursor_f <= hoy:
            iso = cursor_f.strftime("%Y-%m-%d")
            cubetas_d[iso] = {
                "fecha_iso": iso,
                "etiqueta": cursor_f.strftime("%d/%m"),
                "cantidad_ventas": 0,
                "unidades_vendidas": 0,
                "total_ventas": 0.0,
            }
            cursor_f += timedelta(days=1)

        for v in ventas_ok:
            iso = v["fecha_venta"][:10]
            if iso in cubetas_d:
                cubetas_d[iso]["cantidad_ventas"] += 1
                cubetas_d[iso]["total_ventas"] = round(
                    cubetas_d[iso]["total_ventas"] + float(v["total_venta"]), 2
                )
                cubetas_d[iso]["unidades_vendidas"] += sum(
                    int(d["cantidad"]) for d in v.get("detalles", [])
                )
        serie = list(cubetas_d.values())
        modo = "dia"

    return {
        "rango": rango_limpio,
        "modo": modo,
        "total_periodo": round(sum(p["total_ventas"] for p in serie), 2),
        "transacciones_periodo": sum(p["cantidad_ventas"] for p in serie),
        "unidades_periodo": sum(p["unidades_vendidas"] for p in serie),
        "serie": serie,
    }


def obtener_historial_movimientos(
    tipo: str = "", busqueda: str = "", limite: int = 100
) -> dict[str, Any]:
    """Consolida ventas y compras con fecha/hora, productos afectados y totales."""
    datos = cargar_datos()
    filtro_t = tipo.strip().upper()
    termino = busqueda.strip().lower()

    movs: list[dict[str, Any]] = []

    for v in datos["ventas"]:
        prods_txt = " | ".join(
            f"{d['cantidad']}x {d['nombre_producto']} ({d['codigo_sku']})"
            for d in v.get("detalles", [])
        )
        movs.append(
            {
                "tipo_operacion": "VENTA",
                "id_operacion": v["id_venta"],
                "documento": f"BOLETA {v.get('numero_folio', '#' + str(v['id_venta']))}",
                "contraparte": f"Cliente Caja ({v.get('metodo_pago', 'Efectivo')})",
                "fecha_hora": v["fecha_venta"],
                "responsable": v.get("responsable", "Cajero"),
                "total_unidades": sum(int(d["cantidad"]) for d in v.get("detalles", [])),
                "productos_afectados": prods_txt or "Sin detalle",
                "monto_total": float(v["total_venta"]),
                "estado": v.get("estado", "COMPLETADA"),
            }
        )

    for c in datos["compras"]:
        prods_txt = " | ".join(
            f"{d['cantidad']} uds ({d.get('cantidad_formato', d['cantidad'])} {d.get('formato_ingreso', 'UNIDAD')}) {d['nombre_producto']}"
            for d in c.get("detalles", [])
        )
        movs.append(
            {
                "tipo_operacion": "COMPRA",
                "id_operacion": c["id_compra"],
                "documento": f"FACTURA {c['numero_factura_proveedor']}",
                "contraparte": c.get("nombre_proveedor", "Proveedor"),
                "fecha_hora": c["fecha_compra"],
                "responsable": c.get("responsable", "Administrador"),
                "total_unidades": sum(int(d["cantidad"]) for d in c.get("detalles", [])),
                "productos_afectados": prods_txt or "Sin detalle",
                "monto_total": float(c["total"]),
                "estado": c.get("estado", "COMPLETADA"),
            }
        )

    filtrados = []
    for m in movs:
        if filtro_t and m["tipo_operacion"] != filtro_t:
            continue
        if termino:
            blob = (
                f"{m['documento']} {m['contraparte']} {m['productos_afectados']} {m['responsable']}"
            ).lower()
            if termino not in blob:
                continue
        filtrados.append(m)

    filtrados.sort(key=lambda x: (x["fecha_hora"], x["id_operacion"]), reverse=True)
    recorte = filtrados[:limite]

    ventas_ok = [
        m for m in recorte if m["tipo_operacion"] == "VENTA" and m["estado"] == "COMPLETADA"
    ]
    compras_ok = [
        m for m in recorte if m["tipo_operacion"] == "COMPRA" and m["estado"] == "COMPLETADA"
    ]

    return {
        "resumen": {
            "cantidad_ventas": len(ventas_ok),
            "total_ventas": round(sum(m["monto_total"] for m in ventas_ok), 2),
            "cantidad_compras": len(compras_ok),
            "total_compras": round(sum(m["monto_total"] for m in compras_ok), 2),
        },
        "movimientos": recorte,
    }


def obtener_historial_perdidas(causa: str = "", busqueda: str = "") -> dict[str, Any]:
    """Obtiene el registro auditable de pérdidas y mermas de inventario."""
    datos = cargar_datos()
    filtro_c = causa.strip().upper()
    termino = busqueda.strip().lower()

    registros = []
    for m in datos["movimientos"]:
        if m.get("tipo_movimiento") != "MERMA":
            continue
        motivo = m.get("motivo", "MERMA")
        if filtro_c and not motivo.upper().startswith(filtro_c):
            continue
        if termino:
            blob = f"{m.get('nombre_producto', '')} {m.get('codigo_sku', '')} {motivo} {m.get('responsable', '')}".lower()
            if termino not in blob:
                continue
        registros.append(m)

    registros.sort(key=lambda r: (r["fecha"], r["id_movimiento"]), reverse=True)

    return {
        "resumen": {
            "total_eventos": len(registros),
            "total_unidades": sum(int(r.get("cantidad", 0)) for r in registros),
            "costo_total": round(sum(float(r.get("costo_total", 0.0)) for r in registros), 2),
        },
        "registros": registros,
    }
