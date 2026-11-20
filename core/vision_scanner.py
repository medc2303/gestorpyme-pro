"""
Módulo de Escaneo de Productos con Cámara, Visión por IA, OCR en Envase,
Base Precargada del Mercado Chileno y Memoria Visual de Aprendizaje del Operario.

Características clave:
  1. BASE PRECARGADA DEL MERCADO CHILENO (36 productos comunes de almacenes y minimarkets):
     Incluye marcas reales chilenas (McKay Kuky, Tritón, Costa Tuareg, Frac, Super 8,
     Trencito, Lay's, Kryzpo, Soprole, Colun, Cachantún, Vital, Coca-Cola, Kem Piña,
     Bilz/Pap, Watt's, Tucapel, Carozzi, Lucchetti, Pomarola, Chef, Belmont, Iansa,
     Sal Lobos, Té Supremo, Nescafé, Selecta, Robinson Crusoe, Omo, Quix, Clorinda,
     Confort, Ballerina, Pepsodent, Colgate) con sus imágenes de referencia, huellas
     visuales, palabras clave OCR, pesos, formatos Caja/Lote y precios en pesos chilenos.
  2. MEMORIA VISUAL APRENDIDA DEL OPERARIO (`data/memoria_visual.json`):
     Cada vez que la IA duda o se equivoca y el operario indica cuál es el producto,
     se guarda la huella visual de esa imagen (dHash, aHash, grilla 4x4, histograma,
     OCR y miniatura) para que en futuros escaneos la IA recuerde exactamente ese objeto.
  3. DETECCIÓN DE INCOHERENCIAS / IMÁGENES BORROSAS O SIN PRODUCTO:
     Si la captura es demasiado oscura, uniforme o no coincide con certeza con ninguna
     referencia ni texto OCR, advierte explícitamente al operario para evitar ingresos
     incoherentes y respalda siempre con la referencia chilena más cercana.
"""

from __future__ import annotations

import base64
from datetime import datetime
from difflib import SequenceMatcher
import io
import json
import math
import re
from typing import Any
import numpy as np
from PIL import Image, ImageDraw

from core.store import DIRECTORIO_DATOS, obtener_catalogos, obtener_inventario_consolidado

ARCHIVO_MEMORIA_VISUAL = DIRECTORIO_DATOS / "memoria_visual.json"

_OCR_INSTANCE: Any = None
_OCR_CARGADO: bool = False


def _obtener_motor_ocr() -> Any:
    """Inicializa RapidOCR (ONNX) como singleton en memoria."""
    global _OCR_INSTANCE, _OCR_CARGADO
    if _OCR_CARGADO:
        return _OCR_INSTANCE
    _OCR_CARGADO = True
    try:
        from rapidocr_onnxruntime import RapidOCR

        _OCR_INSTANCE = RapidOCR()
    except Exception:
        _OCR_INSTANCE = None
    return _OCR_INSTANCE


# ============================================================================
# BASE PRECARGADA DE PRODUCTOS COMUNES DEL MERCADO CHILENO
# ============================================================================

CATALOGO_CHILENO_PRECARGADO: list[dict[str, Any]] = [
    # --- SNACKS, GALLETAS Y CONFITERÍA CHILENA (Categoría 3) ---
    {
        "sku_ref": "SNK-101",
        "sku_tienda": None,
        "nombre": "Galletas McKay Kuky ChipChipers Blanco 120g",
        "marca": "McKay",
        "claves": ["kuky", "mckay", "chipchiper", "chipchipers", "blanco", "blana", "cnipchipera"],
        "id_categoria": 3,
        "peso": 120.0,
        "unidad_peso": "g",
        "formato": "CAJA",
        "upf": 12,
        "compra": 750.0,
        "venta": 1290.0,
        "perecible": True,
        "colores": ((225, 238, 250), (30, 58, 138), (210, 38, 48)),
    },
    {
        "sku_ref": "SNK-102",
        "sku_tienda": None,
        "nombre": "Galletas McKay Kuky Clásica Chips Chocolate 120g",
        "marca": "McKay",
        "claves": ["kuky", "mckay", "clasica", "chips", "chocolate"],
        "id_categoria": 3,
        "peso": 120.0,
        "unidad_peso": "g",
        "formato": "CAJA",
        "upf": 12,
        "compra": 750.0,
        "venta": 1290.0,
        "perecible": True,
        "colores": ((28, 75, 175), (92, 51, 23), (220, 38, 38)),
    },
    {
        "sku_ref": "SNK-103",
        "sku_tienda": None,
        "nombre": "Galletas McKay Tritón Vainilla 126g",
        "marca": "McKay",
        "claves": ["triton", "mckay", "vainilla", "sandwich"],
        "id_categoria": 3,
        "peso": 126.0,
        "unidad_peso": "g",
        "formato": "CAJA",
        "upf": 12,
        "compra": 720.0,
        "venta": 1250.0,
        "perecible": True,
        "colores": ((20, 45, 130), (234, 88, 12), (255, 255, 255)),
    },
    {
        "sku_ref": "SNK-104",
        "sku_tienda": None,
        "nombre": "Galletas Costa Tuareg Coco 120g",
        "marca": "Costa",
        "claves": ["tuareg", "costa", "coco"],
        "id_categoria": 3,
        "peso": 120.0,
        "unidad_peso": "g",
        "formato": "CAJA",
        "upf": 12,
        "compra": 690.0,
        "venta": 1190.0,
        "perecible": True,
        "colores": ((245, 195, 25), (21, 128, 61), (120, 53, 15)),
    },
    {
        "sku_ref": "SNK-105",
        "sku_tienda": None,
        "nombre": "Galletas Costa Frac Chocolate 130g",
        "marca": "Costa",
        "claves": ["frac", "costa", "chocolate", "rellenas"],
        "id_categoria": 3,
        "peso": 130.0,
        "unidad_peso": "g",
        "formato": "CAJA",
        "upf": 12,
        "compra": 690.0,
        "venta": 1190.0,
        "perecible": True,
        "colores": ((185, 28, 28), (45, 25, 15), (250, 204, 21)),
    },
    {
        "sku_ref": "SNK-106",
        "sku_tienda": None,
        "nombre": "Oblea Bañada Super 8 Nestlé 29g",
        "marca": "Nestlé",
        "claves": ["super8", "super", "nestle", "oblea"],
        "id_categoria": 3,
        "peso": 29.0,
        "unidad_peso": "g",
        "formato": "CAJA",
        "upf": 24,
        "compra": 250.0,
        "venta": 500.0,
        "perecible": True,
        "colores": ((25, 25, 30), (250, 204, 21), (220, 38, 38)),
    },
    {
        "sku_ref": "SNK-107",
        "sku_tienda": None,
        "nombre": "Chocolate Trencito Nestlé 150g",
        "marca": "Nestlé",
        "claves": ["trencito", "nestle", "sahne", "nuss", "chocolate", "leche"],
        "id_categoria": 3,
        "peso": 150.0,
        "unidad_peso": "g",
        "formato": "CAJA",
        "upf": 12,
        "compra": 1450.0,
        "venta": 2390.0,
        "perecible": True,
        "colores": ((220, 38, 38), (250, 204, 21), (95, 50, 25)),
    },
    {
        "sku_ref": "SNK-001",
        "sku_tienda": "SNK-001",
        "nombre": "Galletas Artesanales Avena",
        "marca": "Artesanal",
        "claves": ["galletas", "artesanales", "avena", "integral", "quaker"],
        "id_categoria": 3,
        "peso": 250.0,
        "unidad_peso": "g",
        "formato": "CAJA",
        "upf": 12,
        "compra": 900.0,
        "venta": 1500.0,
        "perecible": True,
        "colores": ((210, 180, 140), (140, 95, 50), (245, 235, 220)),
    },
    {
        "sku_ref": "SNK-002",
        "sku_tienda": "SNK-002",
        "nombre": "Papas Fritas Clásicas 150g (Lay's / Kryzpo)",
        "marca": "Lay's / Kryzpo",
        "claves": ["lays", "kryzpo", "papas", "fritas", "evercrisp", "marco", "polo", "doritos"],
        "id_categoria": 3,
        "peso": 150.0,
        "unidad_peso": "g",
        "formato": "CAJA",
        "upf": 18,
        "compra": 1200.0,
        "venta": 1990.0,
        "perecible": True,
        "colores": ((250, 204, 21), (220, 38, 38), (255, 255, 255)),
    },
    # --- BEBIDAS Y LÁCTEOS CHILENOS (Categoría 1) ---
    {
        "sku_ref": "BEB-001",
        "sku_tienda": "BEB-001",
        "nombre": "Leche Entera 1L (Soprole / Colun)",
        "marca": "Soprole / Colun",
        "claves": ["soprole", "colun", "loncoleche", "surlat", "leche", "entera"],
        "id_categoria": 1,
        "peso": 1.0,
        "unidad_peso": "L",
        "formato": "CAJA",
        "upf": 12,
        "compra": 850.0,
        "venta": 1250.0,
        "perecible": True,
        "colores": ((245, 248, 255), (29, 78, 216), (220, 38, 38)),
    },
    {
        "sku_ref": "BEB-101",
        "sku_tienda": None,
        "nombre": "Leche Entera Colun Del Sur 1L",
        "marca": "Colun",
        "claves": ["colun", "leche", "sur", "magia"],
        "id_categoria": 1,
        "peso": 1.0,
        "unidad_peso": "L",
        "formato": "CAJA",
        "upf": 12,
        "compra": 860.0,
        "venta": 1290.0,
        "perecible": True,
        "colores": ((245, 250, 245), (21, 128, 61), (29, 78, 216)),
    },
    {
        "sku_ref": "BEB-002",
        "sku_tienda": "BEB-002",
        "nombre": "Agua Mineral Sin Gas 1.5L (Cachantún / Vital)",
        "marca": "Cachantún / Vital",
        "claves": ["cachantun", "vital", "benedictino", "agua", "mineral"],
        "id_categoria": 1,
        "peso": 1.5,
        "unidad_peso": "L",
        "formato": "LOTE",
        "upf": 6,
        "compra": 500.0,
        "venta": 950.0,
        "perecible": True,
        "colores": ((186, 230, 253), (2, 132, 199), (255, 255, 255)),
    },
    {
        "sku_ref": "BEB-003",
        "sku_tienda": "BEB-003",
        "nombre": "Jugo Naranja Natural 1L (Watt's / Andina)",
        "marca": "Watt's",
        "claves": ["watts", "watt", "andina", "nectar", "jugo", "naranja", "durazno"],
        "id_categoria": 1,
        "peso": 1.0,
        "unidad_peso": "L",
        "formato": "CAJA",
        "upf": 12,
        "compra": 1100.0,
        "venta": 1690.0,
        "perecible": True,
        "colores": ((249, 115, 22), (250, 204, 21), (21, 128, 61)),
    },
    {
        "sku_ref": "BEB-004",
        "sku_tienda": "BEB-004",
        "nombre": "Yogurt Griego Natural 150g (Soprole / Danone)",
        "marca": "Soprole",
        "claves": ["yogurt", "yoghurt", "griego", "batido", "next"],
        "id_categoria": 1,
        "peso": 150.0,
        "unidad_peso": "g",
        "formato": "LOTE",
        "upf": 6,
        "compra": 520.0,
        "venta": 890.0,
        "perecible": True,
        "colores": ((248, 250, 252), (30, 64, 175), (148, 163, 184)),
    },
    {
        "sku_ref": "BEB-102",
        "sku_tienda": None,
        "nombre": "Bebida Coca-Cola Original 1.5L",
        "marca": "Coca-Cola",
        "claves": ["coca", "cocacola", "cola", "original", "zero"],
        "id_categoria": 1,
        "peso": 1.5,
        "unidad_peso": "L",
        "formato": "LOTE",
        "upf": 6,
        "compra": 1250.0,
        "venta": 1990.0,
        "perecible": True,
        "colores": ((210, 20, 30), (35, 20, 20), (255, 255, 255)),
    },
    {
        "sku_ref": "BEB-103",
        "sku_tienda": None,
        "nombre": "Bebida Kem Piña / Bilz / Pap CCU 1.5L",
        "marca": "CCU",
        "claves": ["kem", "pina", "bilz", "pap", "ccu", "pepsi", "fanta", "sprite"],
        "id_categoria": 1,
        "peso": 1.5,
        "unidad_peso": "L",
        "formato": "LOTE",
        "upf": 6,
        "compra": 1050.0,
        "venta": 1750.0,
        "perecible": True,
        "colores": ((250, 204, 21), (21, 128, 61), (220, 38, 38)),
    },
    # --- ABARROTES Y DESPENSA CHILENA (Categoría 2) ---
    {
        "sku_ref": "ABA-001",
        "sku_tienda": "ABA-001",
        "nombre": "Arroz Grado 1 (1kg) (Tucapel / Miraflores)",
        "marca": "Tucapel / Miraflores",
        "claves": ["tucapel", "miraflores", "arroz", "grado", "banquete"],
        "id_categoria": 2,
        "peso": 1.0,
        "unidad_peso": "kg",
        "formato": "LOTE",
        "upf": 10,
        "compra": 1050.0,
        "venta": 1590.0,
        "perecible": True,
        "colores": ((220, 38, 38), (245, 245, 250), (29, 78, 216)),
    },
    {
        "sku_ref": "ABA-002",
        "sku_tienda": "ABA-002",
        "nombre": "Aceite Vegetal Maravilla 900ml (Chef / Belmont)",
        "marca": "Chef / Belmont",
        "claves": ["chef", "belmont", "aceite", "maravilla", "vegetal"],
        "id_categoria": 2,
        "peso": 900.0,
        "unidad_peso": "ml",
        "formato": "CAJA",
        "upf": 12,
        "compra": 1650.0,
        "venta": 2390.0,
        "perecible": True,
        "colores": ((234, 179, 8), (21, 128, 61), (254, 249, 195)),
    },
    {
        "sku_ref": "ABA-003",
        "sku_tienda": "ABA-003",
        "nombre": "Fideos Spaghetti 400g (Carozzi / Lucchetti)",
        "marca": "Carozzi / Lucchetti",
        "claves": ["carozzi", "lucchetti", "talliani", "spaghetti", "fideos", "tallarines", "espirales"],
        "id_categoria": 2,
        "peso": 400.0,
        "unidad_peso": "g",
        "formato": "CAJA",
        "upf": 20,
        "compra": 620.0,
        "venta": 990.0,
        "perecible": True,
        "colores": ((210, 30, 35), (29, 78, 216), (245, 195, 65)),
    },
    {
        "sku_ref": "ABA-102",
        "sku_tienda": None,
        "nombre": "Salsa de Tomates Pomarola Carozzi 200g",
        "marca": "Carozzi",
        "claves": ["pomarola", "salsa", "tomates", "malloa", "italiana"],
        "id_categoria": 2,
        "peso": 200.0,
        "unidad_peso": "g",
        "formato": "CAJA",
        "upf": 24,
        "compra": 480.0,
        "venta": 850.0,
        "perecible": True,
        "colores": ((185, 28, 28), (21, 128, 61), (255, 255, 255)),
    },
    {
        "sku_ref": "ABA-103",
        "sku_tienda": None,
        "nombre": "Azúcar Blanca Granulada Iansa 1kg",
        "marca": "Iansa",
        "claves": ["iansa", "azucar", "granulada", "blanca"],
        "id_categoria": 2,
        "peso": 1.0,
        "unidad_peso": "kg",
        "formato": "LOTE",
        "upf": 10,
        "compra": 980.0,
        "venta": 1490.0,
        "perecible": False,
        "colores": ((250, 250, 252), (29, 78, 216), (220, 38, 38)),
    },
    {
        "sku_ref": "ABA-104",
        "sku_tienda": None,
        "nombre": "Sal de Mesa Lobos 1kg",
        "marca": "Lobos",
        "claves": ["lobos", "sal", "yodada", "mar"],
        "id_categoria": 2,
        "peso": 1.0,
        "unidad_peso": "kg",
        "formato": "LOTE",
        "upf": 10,
        "compra": 350.0,
        "venta": 690.0,
        "perecible": False,
        "colores": ((30, 58, 138), (255, 255, 255), (220, 38, 38)),
    },
    {
        "sku_ref": "ABA-105",
        "sku_tienda": None,
        "nombre": "Té Supremo Ceylán Caja 20 Bolsitas",
        "marca": "Supremo / Club",
        "claves": ["supremo", "club", "lipton", "ceylan", "bolsitas"],
        "id_categoria": 2,
        "peso": 40.0,
        "unidad_peso": "g",
        "formato": "CAJA",
        "upf": 12,
        "compra": 690.0,
        "venta": 1190.0,
        "perecible": True,
        "colores": ((185, 28, 28), (234, 179, 8), (120, 53, 15)),
    },
    {
        "sku_ref": "ABA-106",
        "sku_tienda": None,
        "nombre": "Café Instantáneo Nescafé Tradición 170g",
        "marca": "Nescafé",
        "claves": ["nescafe", "tradicion", "cafe", "dolca", "gold", "milo"],
        "id_categoria": 2,
        "peso": 170.0,
        "unidad_peso": "g",
        "formato": "CAJA",
        "upf": 12,
        "compra": 3400.0,
        "venta": 5290.0,
        "perecible": True,
        "colores": ((75, 40, 25), (220, 38, 38), (245, 222, 179)),
    },
    {
        "sku_ref": "ABA-107",
        "sku_tienda": None,
        "nombre": "Harina Sin Polvos Selecta 1kg",
        "marca": "Selecta",
        "claves": ["selecta", "harina", "trigo", "mont", "blanc"],
        "id_categoria": 2,
        "peso": 1.0,
        "unidad_peso": "kg",
        "formato": "LOTE",
        "upf": 10,
        "compra": 890.0,
        "venta": 1390.0,
        "perecible": True,
        "colores": ((250, 245, 235), (29, 78, 216), (220, 38, 38)),
    },
    {
        "sku_ref": "ABA-108",
        "sku_tienda": None,
        "nombre": "Atún Lomitos Robinson Crusoe 160g",
        "marca": "Robinson Crusoe",
        "claves": ["robinson", "crusoe", "atun", "lomitos", "jurel", "san", "jose"],
        "id_categoria": 2,
        "peso": 160.0,
        "unidad_peso": "g",
        "formato": "CAJA",
        "upf": 24,
        "compra": 1150.0,
        "venta": 1850.0,
        "perecible": True,
        "colores": ((15, 75, 165), (250, 204, 21), (255, 255, 255)),
    },
    # --- LIMPIEZA DEL HOGAR EN CHILE (Categoría 4) ---
    {
        "sku_ref": "LIM-001",
        "sku_tienda": "LIM-001",
        "nombre": "Detergente Líquido Ropa 3L (Omo / Ariel)",
        "marca": "Omo / Ariel",
        "claves": ["omo", "ariel", "drive", "rinso", "detergente", "matic"],
        "id_categoria": 4,
        "peso": 3.0,
        "unidad_peso": "L",
        "formato": "CAJA",
        "upf": 4,
        "compra": 4200.0,
        "venta": 6490.0,
        "perecible": False,
        "colores": ((29, 78, 216), (220, 38, 38), (255, 255, 255)),
    },
    {
        "sku_ref": "LIM-002",
        "sku_tienda": "LIM-002",
        "nombre": "Cloro Gel Desinfectante 1L (Clorinda / Clorox)",
        "marca": "Clorinda / Clorox",
        "claves": ["clorinda", "clorox", "cloro", "poett", "lysoform", "desinfectante"],
        "id_categoria": 4,
        "peso": 1.0,
        "unidad_peso": "L",
        "formato": "CAJA",
        "upf": 12,
        "compra": 1150.0,
        "venta": 1850.0,
        "perecible": False,
        "colores": ((21, 128, 61), (2, 132, 199), (255, 255, 255)),
    },
    {
        "sku_ref": "LIM-101",
        "sku_tienda": None,
        "nombre": "Lavaloza Concentrado Quix Verde 750ml",
        "marca": "Quix",
        "claves": ["quix", "lavaloza", "magistral", "loza"],
        "id_categoria": 4,
        "peso": 750.0,
        "unidad_peso": "ml",
        "formato": "CAJA",
        "upf": 12,
        "compra": 1250.0,
        "venta": 1990.0,
        "perecible": False,
        "colores": ((22, 163, 74), (250, 204, 21), (255, 255, 255)),
    },
    {
        "sku_ref": "LIM-102",
        "sku_tienda": None,
        "nombre": "Papel Higiénico Confort Doble Hoja (Pack 4)",
        "marca": "Confort / Elite",
        "claves": ["confort", "elite", "noble", "papel", "higienico", "nova"],
        "id_categoria": 4,
        "peso": 400.0,
        "unidad_peso": "g",
        "formato": "LOTE",
        "upf": 12,
        "compra": 1390.0,
        "venta": 2290.0,
        "perecible": False,
        "colores": ((240, 249, 255), (2, 132, 199), (220, 38, 38)),
    },
    # --- CUIDADO PERSONAL EN CHILE (Categoría 5) ---
    {
        "sku_ref": "PER-001",
        "sku_tienda": "PER-001",
        "nombre": "Shampoo Hidratante 400ml (Ballerina / Sedal)",
        "marca": "Ballerina / Sedal",
        "claves": ["ballerina", "sedal", "pantene", "head", "shoulders", "shampoo", "familand"],
        "id_categoria": 5,
        "peso": 400.0,
        "unidad_peso": "ml",
        "formato": "CAJA",
        "upf": 12,
        "compra": 2100.0,
        "venta": 3490.0,
        "perecible": True,
        "colores": ((219, 39, 119), (250, 232, 255), (147, 51, 234)),
    },
    {
        "sku_ref": "PER-002",
        "sku_tienda": "PER-002",
        "nombre": "Pasta Dental Triple Acción 120g (Pepsodent / Colgate)",
        "marca": "Pepsodent / Colgate",
        "claves": ["pepsodent", "colgate", "sensodyne", "pasta", "dental"],
        "id_categoria": 5,
        "peso": 120.0,
        "unidad_peso": "g",
        "formato": "LOTE",
        "upf": 12,
        "compra": 980.0,
        "venta": 1650.0,
        "perecible": True,
        "colores": ((220, 38, 38), (29, 78, 216), (255, 255, 255)),
    },
]


def obtener_catalogo_chileno_referencia() -> list[dict[str, Any]]:
    """Retorna la base precargada de productos comunes del mercado chileno."""
    return CATALOGO_CHILENO_PRECARGADO


# ============================================================================
# EXTRACCIÓN DE HUELLA VISUAL Y GENERACIÓN DE MINIATURAS DE REFERENCIA
# ============================================================================


def _recortar_objeto_activo(img: Image.Image) -> Image.Image:
    """Elimina bordes oscuros o vacíos de la captura de cámara."""
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, w, _ = arr.shape
    if h < 32 or w < 32:
        return img

    lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    filas_activas = np.where(np.percentile(lum, 80, axis=1) > 38.0)[0]
    cols_activas = np.where(np.percentile(lum, 80, axis=0) > 38.0)[0]

    if len(filas_activas) >= int(h * 0.22) and len(cols_activas) >= int(w * 0.22):
        y0 = max(0, int(filas_activas[0]) - 4)
        y1 = min(h, int(filas_activas[-1]) + 5)
        x0 = max(0, int(cols_activas[0]) - 4)
        x1 = min(w, int(cols_activas[-1]) + 5)
        if (y1 - y0) >= 24 and (x1 - x0) >= 24:
            return img.crop((x0, y0, x1, y1))

    return img


def _evaluar_calidad_imagen(img: Image.Image) -> tuple[bool, str]:
    """
    Detecta si una captura es incoherente (cámara tapada/negra, imagen totalmente blanca
    o sin variación de contraste/objeto).
    """
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    lum = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    media = float(lum.mean())
    desv = float(lum.std())

    if media < 18.0:
        return False, "Imagen demasiado oscura o cámara obstruida"
    if media > 248.0 and desv < 6.0:
        return False, "Imagen en blanco sin objeto visible"
    if desv < 9.0:
        return False, "Fondo plano sin empaque u objeto distinguible"
    return True, "OK"


def _calcular_hashes_perceptuales(img_recortada: Image.Image) -> tuple[str, str]:
    """Calcula dHash y aHash de 64 bits."""
    gris_d = np.asarray(
        img_recortada.convert("L").resize((9, 8), Image.Resampling.LANCZOS),
        dtype=np.float32,
    )
    diff = (gris_d[:, 1:] > gris_d[:, :-1]).flatten()
    bits_d = "".join("1" if b else "0" for b in diff)
    dhash_hex = f"{int(bits_d, 2):016x}"

    gris_a = np.asarray(
        img_recortada.convert("L").resize((8, 8), Image.Resampling.LANCZOS),
        dtype=np.float32,
    )
    media = float(gris_a.mean())
    bits_a = "".join("1" if v >= media else "0" for v in gris_a.flatten())
    ahash_hex = f"{int(bits_a, 2):016x}"
    return dhash_hex, ahash_hex


def _calcular_descriptores_color(img_recortada: Image.Image) -> tuple[list[float], list[float]]:
    """Extrae grilla espacial 4x4x3 y el histograma cromático de 48 bins."""
    peq = np.asarray(
        img_recortada.convert("RGB").resize((64, 64), Image.Resampling.LANCZOS),
        dtype=np.float32,
    )
    p5 = float(np.percentile(peq, 5))
    p95 = float(np.percentile(peq, 95))
    rango = max(25.0, p95 - p5)
    norm_img = np.clip((peq - p5) / rango, 0.0, 1.0)

    grid = np.asarray(
        Image.fromarray(np.uint8(norm_img * 255)).resize((4, 4), Image.Resampling.BOX),
        dtype=np.float32,
    ).flatten() / 255.0
    norma_g = float(np.linalg.norm(grid))
    grid_list = [round(float(x / norma_g), 4) for x in grid] if norma_g > 1e-6 else [0.0] * 48

    bins = np.linspace(0.0, 1.0001, 17)
    h_r, _ = np.histogram(norm_img[:, :, 0], bins=bins)
    h_g, _ = np.histogram(norm_img[:, :, 1], bins=bins)
    h_b, _ = np.histogram(norm_img[:, :, 2], bins=bins)
    hist = np.concatenate([h_r, h_g, h_b]).astype(np.float32)
    norma_h = float(np.linalg.norm(hist))
    hist_list = [round(float(x / norma_h), 4) for x in hist] if norma_h > 1e-6 else [0.0] * 48

    return grid_list, hist_list


def _extraer_texto_ocr(img_recortada: Image.Image) -> list[str]:
    """Ejecuta RapidOCR sobre la imagen del producto."""
    motor = _obtener_motor_ocr()
    if motor is None:
        return []

    try:
        ancho, alto = img_recortada.size
        if max(ancho, alto) > 720:
            escala = 720.0 / max(ancho, alto)
            img_ocr = img_recortada.resize(
                (max(1, int(ancho * escala)), max(1, int(alto * escala))),
                Image.Resampling.LANCZOS,
            )
        else:
            img_ocr = img_recortada

        arr = np.asarray(img_ocr.convert("RGB"))
        resultados, _ = motor(arr)
        if not resultados:
            return []

        ignorar = {"clear photo", "clearphoto", "take photo", "takephoto"}
        textos: list[str] = []
        for item in resultados:
            txt = str(item[1]).strip()
            conf = float(item[2])
            limpio = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9\.\-% ]+", "", txt).strip()
            if len(limpio) >= 2 and conf >= 0.45 and limpio.lower() not in ignorar:
                textos.append(limpio)
        return textos
    except Exception:
        return []


def extraer_huella_visual(
    imagen_bytes: bytes, incluir_ocr: bool = True
) -> dict[str, Any]:
    """Extrae el descriptor visual completo de una imagen."""
    img_original = Image.open(io.BytesIO(imagen_bytes)).convert("RGB")
    img_obj = _recortar_objeto_activo(img_original)

    dhash_hex, ahash_hex = _calcular_hashes_perceptuales(img_obj)
    grid_color, hist_color = _calcular_descriptores_color(img_obj)
    textos_ocr = _extraer_texto_ocr(img_obj) if incluir_ocr else []

    thumb = img_obj.copy()
    thumb.thumbnail((140, 100), Image.Resampling.LANCZOS)
    buf_t = io.BytesIO()
    thumb.save(buf_t, format="JPEG", quality=75)
    thumb_b64 = base64.b64encode(buf_t.getvalue()).decode("ascii")

    return {
        "dhash": dhash_hex,
        "ahash": ahash_hex,
        "grid_color": grid_color,
        "hist_color": hist_color,
        "textos_ocr": textos_ocr,
        "miniatura_b64": thumb_b64,
    }


def generar_imagen_referencia_chilena(item_chileno: dict[str, Any]) -> bytes:
    """
    Genera una imagen de referencia de empaque comercial con la paleta cromática real
    de la marca chilena, franjas de diseño y tipografía para precargar la base visual.
    """
    c_principal, c_secundario, c_acento = item_chileno.get(
        "colores", ((29, 78, 216), (220, 38, 38), (255, 255, 255))
    )
    img = Image.new("RGB", (240, 165), color=c_principal)
    draw = ImageDraw.Draw(img)

    # Franja superior de marca y franja inferior de categoría/formato
    draw.rectangle([0, 0, 240, 42], fill=c_secundario)
    draw.rectangle([0, 125, 240, 165], fill=c_secundario)
    draw.rectangle([16, 26, 110, 56], fill=c_acento)
    draw.ellipse([160, 50, 224, 114], fill=c_acento)

    # Textos identificadores impresos en la tarjeta de empaque
    marca = str(item_chileno.get("marca", "CHILE")).upper()[:14]
    nombre = str(item_chileno.get("nombre", "PRODUCTO"))[:26]
    peso_txt = f"{item_chileno.get('peso', 1):g}{item_chileno.get('unidad_peso', 'g')}"

    draw.text((22, 34), marca, fill=(15, 23, 42))
    draw.text((18, 72), nombre, fill=(255, 255, 255) if sum(c_principal) < 420 else (15, 23, 42))
    draw.text((170, 76), peso_txt, fill=(15, 23, 42))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _construir_base_visual_chilena_por_defecto() -> list[dict[str, Any]]:
    """
    Construye la base de imágenes de referencia precargadas con los productos
    comunes del mercado chileno para que la Memoria Visual siempre tenga respaldo.
    """
    categorias_map = {
        1: "Bebidas y Lácteos",
        2: "Abarrotes y Despensa",
        3: "Snacks y Confitería",
        4: "Limpieza del Hogar",
        5: "Cuidado Personal",
    }
    referencias: list[dict[str, Any]] = []
    ahora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for idx, prod_ch in enumerate(CATALOGO_CHILENO_PRECARGADO, start=1):
        img_bytes = generar_imagen_referencia_chilena(prod_ch)
        huella = extraer_huella_visual(img_bytes, incluir_ocr=False)
        huella["textos_ocr"] = list(prod_ch["claves"]) + [
            prod_ch["marca"],
            prod_ch["nombre"],
        ]

        referencias.append(
            {
                "id_referencia": idx,
                "fecha_aprendizaje": ahora_str,
                "origen": "BASE_CHILENA_PRECARGADA",
                "es_existente": prod_ch["sku_tienda"] is not None,
                "id_producto": None,
                "codigo_sku": prod_ch["sku_tienda"] or prod_ch["sku_ref"],
                "nombre_producto": prod_ch["nombre"],
                "marca": prod_ch["marca"],
                "id_categoria": prod_ch["id_categoria"],
                "nombre_categoria": categorias_map.get(prod_ch["id_categoria"], "General"),
                "formato_sugerido": prod_ch["formato"],
                "unidades_por_formato_sugeridas": prod_ch["upf"],
                "peso_sugerido": prod_ch["peso"],
                "unidad_peso_sugerida": prod_ch["unidad_peso"],
                "precio_compra_sugerido": prod_ch["compra"],
                "precio_venta_sugerido": prod_ch["venta"],
                "perecible_sugerido": prod_ch["perecible"],
                "huella": huella,
            }
        )

    return referencias


# ============================================================================
# SIMILITUD VISUAL Y PERSISTENCIA DE MEMORIA VISUAL
# ============================================================================


def _similitud_coseno(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 < 1e-6 or n2 < 1e-6:
        return 0.0
    return max(0.0, min(1.0, dot / (n1 * n2)))


def _similitud_hamming_hex(h1: str, h2: str) -> float:
    try:
        x = int(h1, 16) ^ int(h2, 16)
        dist = x.bit_count()
        return max(0.0, (64.0 - dist) / 64.0)
    except Exception:
        return 0.0


def _similitud_ocr(textos_a: list[str], textos_b: list[str]) -> float:
    if not textos_a or not textos_b:
        return 0.0
    tokens_a = [
        t.lower()
        for frase in textos_a
        for t in re.split(r"\s+", frase)
        if len(t) >= 3
    ]
    tokens_b = [
        t.lower()
        for frase in textos_b
        for t in re.split(r"\s+", frase)
        if len(t) >= 3
    ]
    if not tokens_a or not tokens_b:
        return 0.0

    aciertos = 0.0
    for ta in tokens_a:
        mejor = max(
            (SequenceMatcher(None, ta, tb).ratio() for tb in tokens_b),
            default=0.0,
        )
        if mejor >= 0.74:
            aciertos += mejor
    return min(1.0, aciertos / max(1.0, min(len(tokens_a), len(tokens_b))))


def calcular_similitud_visual(
    huella_nueva: dict[str, Any], huella_ref: dict[str, Any]
) -> float:
    """Calcula el porcentaje de similitud entre la captura actual y una referencia."""
    sim_hist = _similitud_coseno(
        huella_nueva.get("hist_color", []), huella_ref.get("hist_color", [])
    )
    sim_grid = _similitud_coseno(
        huella_nueva.get("grid_color", []), huella_ref.get("grid_color", [])
    )
    sim_dhash = _similitud_hamming_hex(
        huella_nueva.get("dhash", "0"), huella_ref.get("dhash", "0")
    )
    sim_ahash = _similitud_hamming_hex(
        huella_nueva.get("ahash", "0"), huella_ref.get("ahash", "0")
    )
    sim_hash = 0.55 * sim_dhash + 0.45 * sim_ahash

    puntaje_visual = (0.42 * sim_hist + 0.30 * sim_grid + 0.28 * sim_hash) * 100.0

    sim_texto = _similitud_ocr(
        huella_nueva.get("textos_ocr", []), huella_ref.get("textos_ocr", [])
    )
    if sim_texto > 0:
        puntaje_visual = min(99.0, puntaje_visual * 0.72 + (sim_texto * 100.0) * 0.38)

    return round(min(99.5, max(0.0, puntaje_visual)), 1)


def cargar_memoria_visual() -> list[dict[str, Any]]:
    """
    Carga la Memoria Visual desde disco. Si no existe o tiene menos de 5 referencias,
    integra automáticamente toda la Base Precargada de Productos Comunes del Mercado Chileno
    preservando las fotos enseñadas por el operario en primer lugar.
    """
    DIRECTORIO_DATOS.mkdir(parents=True, exist_ok=True)
    existentes: list[dict[str, Any]] = []
    if ARCHIVO_MEMORIA_VISUAL.exists():
        try:
            data = json.loads(ARCHIVO_MEMORIA_VISUAL.read_text(encoding="utf-8"))
            if isinstance(data, list):
                existentes = data
        except Exception:
            existentes = []

    tiene_base_chilena = sum(
        1 for r in existentes if r.get("origen") == "BASE_CHILENA_PRECARGADA"
    )
    if tiene_base_chilena < 15:
        aprendidas_operario = [
            r for r in existentes if r.get("origen") != "BASE_CHILENA_PRECARGADA"
        ]
        base_chilena = _construir_base_visual_chilena_por_defecto()
        max_id = max((r.get("id_referencia", 0) for r in base_chilena), default=0)
        for idx, ap in enumerate(aprendidas_operario, start=1):
            ap["id_referencia"] = max_id + idx
        combinadas = aprendidas_operario + base_chilena
        guardar_memoria_visual(combinadas)
        return combinadas

    return existentes


def guardar_memoria_visual(referencias: list[dict[str, Any]]) -> None:
    """Guarda atómicamente la Memoria Visual."""
    DIRECTORIO_DATOS.mkdir(parents=True, exist_ok=True)
    tmp = ARCHIVO_MEMORIA_VISUAL.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(referencias, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(ARCHIVO_MEMORIA_VISUAL)


def guardar_referencia_memoria_visual(
    imagen_bytes: bytes,
    datos_producto: dict[str, Any],
    origen: str = "CORRECCION_OPERARIO",
) -> dict[str, Any]:
    """
    Guarda inmediatamente en la Memoria Visual la imagen capturada por cámara
    asociada al producto que indicó o corrigió el operario.
    """
    huella = extraer_huella_visual(imagen_bytes, incluir_ocr=True)
    referencias = cargar_memoria_visual()
    ahora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    nombre_real = str(datos_producto.get("nombre_detectado", "")).strip()
    textos_combinados = list(huella.get("textos_ocr", []))
    for palabra in re.split(r"\s+", nombre_real):
        limpia = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+", "", palabra)
        if len(limpia) >= 3 and limpia not in textos_combinados:
            textos_combinados.append(limpia)

    registro = {
        "id_referencia": max((r.get("id_referencia", 0) for r in referencias), default=0) + 1,
        "fecha_aprendizaje": ahora_str,
        "origen": origen,
        "es_existente": bool(datos_producto.get("es_existente", True)),
        "id_producto": datos_producto.get("id_producto"),
        "codigo_sku": datos_producto.get("codigo_sku", "PRD-001"),
        "nombre_producto": nombre_real,
        "id_categoria": int(datos_producto.get("id_categoria", 1) or 1),
        "nombre_categoria": datos_producto.get("nombre_categoria", "General"),
        "formato_sugerido": datos_producto.get("formato_sugerido", "CAJA"),
        "unidades_por_formato_sugeridas": int(
            datos_producto.get("unidades_por_formato_sugeridas", 12) or 12
        ),
        "peso_sugerido": float(datos_producto.get("peso_sugerido", 1.0) or 1.0),
        "unidad_peso_sugerida": datos_producto.get("unidad_peso_sugerida", "kg"),
        "precio_compra_sugerido": float(
            datos_producto.get("precio_compra_sugerido", 850.0) or 850.0
        ),
        "precio_venta_sugerido": float(
            datos_producto.get("precio_venta_sugerido", 1350.0) or 1350.0
        ),
        "perecible_sugerido": bool(datos_producto.get("perecible_sugerido", True)),
        "huella": {
            **huella,
            "textos_ocr": textos_combinados,
        },
    }

    reemplazado = False
    for idx, ref in enumerate(referencias):
        if (
            ref.get("origen") != "BASE_CHILENA_PRECARGADA"
            and ref.get("huella", {}).get("dhash") == huella["dhash"]
        ):
            registro["id_referencia"] = ref.get("id_referencia", registro["id_referencia"])
            referencias[idx] = registro
            reemplazado = True
            break

    if not reemplazado:
        referencias.insert(0, registro)
        referencias = referencias[:90]

    guardar_memoria_visual(referencias)
    return registro


def vincular_producto_creado_en_memoria(
    nombre_producto: str, producto_creado: dict[str, Any]
) -> None:
    """Actualiza las referencias de un producto recién creado para vincularlo con su ID real."""
    referencias = cargar_memoria_visual()
    modificado = False
    nom_low = nombre_producto.strip().lower()

    for ref in referencias:
        if ref.get("nombre_producto", "").strip().lower() == nom_low:
            ref["es_existente"] = True
            ref["id_producto"] = producto_creado["id_producto"]
            ref["codigo_sku"] = producto_creado["codigo_sku"]
            ref["nombre_producto"] = producto_creado["nombre_producto"]
            modificado = True

    if modificado:
        guardar_memoria_visual(referencias)


def eliminar_referencia_memoria_visual(id_referencia: int) -> None:
    """Elimina una referencia específica de la Memoria Visual."""
    referencias = [
        r for r in cargar_memoria_visual() if int(r.get("id_referencia", 0)) != int(id_referencia)
    ]
    guardar_memoria_visual(referencias)


# ============================================================================
# BÚSQUEDA POR LECTURA OCR SOBRE CATÁLOGO ACTIVO Y BASE CHILENA PRECARGADA
# ============================================================================


def _vincular_con_inventario_activo(
    sku_tienda: str | None,
    nombre_buscado: str,
    inventario: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Verifica si un producto de la base chilena ya existe en el inventario activo."""
    if sku_tienda:
        por_sku = next(
            (p for p in inventario if p["codigo_sku"].upper() == sku_tienda.upper()),
            None,
        )
        if por_sku is not None:
            return por_sku

    nom_low = nombre_buscado.strip().lower()
    for p in inventario:
        p_low = p["nombre_producto"].strip().lower()
        if nom_low == p_low or nom_low in p_low or p_low in nom_low:
            return p
    return None


def _buscar_por_ocr_en_envase(
    textos_ocr: list[str],
    inventario: list[dict[str, Any]],
    categorias: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Cruza el texto leído en el envase con el inventario y la Base Chilena Precargada."""
    if not textos_ocr:
        return None

    texto_unido = " ".join(textos_ocr)
    texto_low = texto_unido.lower()
    tokens_ocr = [
        t.lower()
        for t in re.split(r"[\s\-\.,/]+", texto_low)
        if len(t) >= 3
    ]
    if not tokens_ocr:
        return None

    # 1. Buscar primero en la Base Precargada del Mercado Chileno por marcas/palabras clave
    mejor_item_ch = None
    mejor_hits_ch = 0.0

    for item_ch in CATALOGO_CHILENO_PRECARGADO:
        puntaje = 0.0
        for clave in item_ch["claves"]:
            for tk in tokens_ocr:
                if clave == tk:
                    puntaje += 1.3
                    break
                if (len(clave) >= 4 and clave in tk) or SequenceMatcher(None, clave, tk).ratio() >= 0.77:
                    puntaje += 1.0
                    break
        if puntaje > mejor_hits_ch:
            mejor_hits_ch = puntaje
            mejor_item_ch = item_ch

    if mejor_item_ch is not None and mejor_hits_ch >= 1.0:
        prod_inv = _vincular_con_inventario_activo(
            mejor_item_ch.get("sku_tienda"), mejor_item_ch["nombre"], inventario
        )
        conf_ocr = min(97, int(84 + mejor_hits_ch * 4))
        if prod_inv is not None:
            return {
                "es_existente": True,
                "id_producto": prod_inv["id_producto"],
                "codigo_sku": prod_inv["codigo_sku"],
                "nombre_detectado": prod_inv["nombre_producto"],
                "nombre_categoria": prod_inv["nombre_categoria"],
                "id_categoria": prod_inv["id_categoria"],
                "stock_actual": prod_inv["stock_actual"],
                "formato_sugerido": prod_inv["formato_habitual"],
                "unidades_por_formato_sugeridas": prod_inv["unidades_por_formato"],
                "peso_sugerido": prod_inv["peso_unitario"],
                "unidad_peso_sugerida": prod_inv["unidad_peso"],
                "precio_compra_sugerido": prod_inv["precio_compra"],
                "precio_venta_sugerido": prod_inv["precio_venta"],
                "perecible_sugerido": prod_inv["perecible"],
                "confianza_pct": conf_ocr,
                "descripcion_visual": f"Marca chilena leída en empaque: «{' · '.join(textos_ocr[:5])}»",
                "motor_vision": "🇨🇱 Base Mercado Chileno + OCR",
                "recordado_de_memoria": False,
                "es_incoherente": False,
            }

        cat_obj = next(
            (c for c in categorias if c["id_categoria"] == mejor_item_ch["id_categoria"]),
            categorias[0],
        )
        return {
            "es_existente": False,
            "id_producto": None,
            "codigo_sku": mejor_item_ch["sku_ref"],
            "nombre_detectado": mejor_item_ch["nombre"],
            "nombre_categoria": cat_obj["nombre_categoria"],
            "id_categoria": cat_obj["id_categoria"],
            "stock_actual": 0,
            "formato_sugerido": mejor_item_ch["formato"],
            "unidades_por_formato_sugeridas": mejor_item_ch["upf"],
            "peso_sugerido": mejor_item_ch["peso"],
            "unidad_peso_sugerida": mejor_item_ch["unidad_peso"],
            "precio_compra_sugerido": mejor_item_ch["compra"],
            "precio_venta_sugerido": mejor_item_ch["venta"],
            "perecible_sugerido": mejor_item_ch["perecible"],
            "confianza_pct": conf_ocr,
            "descripcion_visual": f"Marca chilena leída en empaque: «{' · '.join(textos_ocr[:5])}»",
            "motor_vision": "🇨🇱 Base Mercado Chileno + OCR",
            "recordado_de_memoria": False,
            "es_incoherente": False,
        }

    # 2. Buscar coincidencia directa contra nombres del inventario activo
    stopwords = {"con", "sin", "por", "para", "del", "las", "los", "una", "natural", "clasicas", "grado"}
    mejor_prod_inv = None
    mejor_score_inv = 0.0

    for p in inventario:
        palabras_p = [
            w.lower()
            for w in re.split(r"[\s\(\)\-]+", p["nombre_producto"])
            if len(w) >= 3 and w.lower() not in stopwords
        ]
        if not palabras_p:
            continue
        coincidencias = 0.0
        for wp in palabras_p:
            sim_max = max(
                (SequenceMatcher(None, wp, tk).ratio() for tk in tokens_ocr),
                default=0.0,
            )
            if sim_max >= 0.78:
                coincidencias += sim_max
        score = coincidencias / len(palabras_p)
        if score > mejor_score_inv:
            mejor_score_inv = score
            mejor_prod_inv = p

    if mejor_prod_inv is not None and mejor_score_inv >= 0.55:
        return {
            "es_existente": True,
            "id_producto": mejor_prod_inv["id_producto"],
            "codigo_sku": mejor_prod_inv["codigo_sku"],
            "nombre_detectado": mejor_prod_inv["nombre_producto"],
            "nombre_categoria": mejor_prod_inv["nombre_categoria"],
            "id_categoria": mejor_prod_inv["id_categoria"],
            "stock_actual": mejor_prod_inv["stock_actual"],
            "formato_sugerido": mejor_prod_inv["formato_habitual"],
            "unidades_por_formato_sugeridas": mejor_prod_inv["unidades_por_formato"],
            "peso_sugerido": mejor_prod_inv["peso_unitario"],
            "unidad_peso_sugerida": mejor_prod_inv["unidad_peso"],
            "precio_compra_sugerido": mejor_prod_inv["precio_compra"],
            "precio_venta_sugerido": mejor_prod_inv["precio_venta"],
            "perecible_sugerido": mejor_prod_inv["perecible"],
            "confianza_pct": min(96, int(78 + mejor_score_inv * 20)),
            "descripcion_visual": f"Texto leído en el empaque: «{' · '.join(textos_ocr[:5])}»",
            "motor_vision": "IA Lectora de Empaques (OCR)",
            "recordado_de_memoria": False,
            "es_incoherente": False,
        }

    return None


# ============================================================================
# FUNCIÓN PRINCIPAL DE DETECCIÓN CON PRIORIDAD A MEMORIA Y BASE CHILENA
# ============================================================================


def _construir_respuesta_desde_referencia(
    ref: dict[str, Any],
    similitud: float,
    inventario: list[dict[str, Any]],
    es_incoherente: bool = False,
    motivo_incoherencia: str = "",
) -> dict[str, Any]:
    """Construye el diccionario de detección sincronizado con el stock actual en vivo."""
    prod_inv = None
    if ref.get("id_producto") is not None:
        prod_inv = next(
            (p for p in inventario if p["id_producto"] == int(ref["id_producto"])),
            None,
        )
    if prod_inv is None:
        prod_inv = _vincular_con_inventario_activo(
            ref.get("codigo_sku"), str(ref.get("nombre_producto", "")), inventario
        )

    es_aprendida_operario = ref.get("origen") != "BASE_CHILENA_PRECARGADA"
    motor_lbl = (
        "🧠 Memoria Visual Aprendida (Operario)"
        if es_aprendida_operario
        else "🇨🇱 Base Visual Mercado Chileno"
    )

    if es_incoherente:
        desc = (
            f"⚠️ Captura dudosa o posible incoherencia ({motivo_incoherencia}). "
            f"Referencia chilena más próxima sugerida ({similitud:.0f}%): verifica o corrige abajo."
        )
    elif es_aprendida_operario:
        desc = (
            f"Reconocido por Memoria Visual enseñada por el operario "
            f"(similitud {similitud:.1f}% con referencia #{ref['id_referencia']})"
        )
    else:
        desc = (
            f"Coincidencia con referencia precargada del mercado chileno "
            f"({similitud:.1f}% similitud visual)"
        )

    if prod_inv is not None:
        return {
            "es_existente": True,
            "id_producto": prod_inv["id_producto"],
            "codigo_sku": prod_inv["codigo_sku"],
            "nombre_detectado": prod_inv["nombre_producto"],
            "nombre_categoria": prod_inv["nombre_categoria"],
            "id_categoria": prod_inv["id_categoria"],
            "stock_actual": prod_inv["stock_actual"],
            "formato_sugerido": prod_inv["formato_habitual"],
            "unidades_por_formato_sugeridas": prod_inv["unidades_por_formato"],
            "peso_sugerido": prod_inv["peso_unitario"],
            "unidad_peso_sugerida": prod_inv["unidad_peso"],
            "precio_compra_sugerido": prod_inv["precio_compra"],
            "precio_venta_sugerido": prod_inv["precio_venta"],
            "perecible_sugerido": prod_inv["perecible"],
            "confianza_pct": int(round(similitud)),
            "descripcion_visual": desc,
            "motor_vision": motor_lbl,
            "recordado_de_memoria": es_aprendida_operario and not es_incoherente,
            "es_incoherente": es_incoherente,
        }

    return {
        "es_existente": False,
        "id_producto": None,
        "codigo_sku": ref.get("codigo_sku", "PRD-015"),
        "nombre_detectado": ref.get("nombre_producto", "Producto Chileno Referencia"),
        "nombre_categoria": ref.get("nombre_categoria", "General"),
        "id_categoria": int(ref.get("id_categoria", 1) or 1),
        "stock_actual": 0,
        "formato_sugerido": ref.get("formato_sugerido", "CAJA"),
        "unidades_por_formato_sugeridas": int(
            ref.get("unidades_por_formato_sugeridas", 12) or 12
        ),
        "peso_sugerido": float(ref.get("peso_sugerido", 1.0) or 1.0),
        "unidad_peso_sugerida": ref.get("unidad_peso_sugerida", "kg"),
        "precio_compra_sugerido": float(
            ref.get("precio_compra_sugerido", 850.0) or 850.0
        ),
        "precio_venta_sugerido": float(
            ref.get("precio_venta_sugerido", 1350.0) or 1350.0
        ),
        "perecible_sugerido": bool(ref.get("perecible_sugerido", True)),
        "confianza_pct": int(round(similitud)),
        "descripcion_visual": desc,
        "motor_vision": motor_lbl,
        "recordado_de_memoria": es_aprendida_operario and not es_incoherente,
        "es_incoherente": es_incoherente,
    }


def detectar_producto_en_imagen(
    imagen_bytes: bytes,
    api_key_gemini: str = "",
) -> dict[str, Any]:
    """
    Analiza la imagen capturada por cámara:
      1. Verifica calidad de imagen (detecta capturas en negro/vacías/incoherentes).
      2. Prioriza las imágenes aprendidas de correcciones del operario en Memoria Visual.
      3. Ejecuta lectura OCR de marcas chilenas y textos impresos en el envase.
      4. Compara contra la Base Visual Precargada de Productos del Mercado Chileno,
         advirtiendo si la certeza es baja para que el operario confirme o enseñe la imagen.
    """
    inventario = obtener_inventario_consolidado()
    catalogos = obtener_catalogos()
    categorias = catalogos["categorias"]

    img_pil = Image.open(io.BytesIO(imagen_bytes)).convert("RGB")
    calidad_ok, motivo_calidad = _evaluar_calidad_imagen(img_pil)

    huella_actual = extraer_huella_visual(imagen_bytes, incluir_ocr=calidad_ok)
    referencias_memoria = cargar_memoria_visual()

    # Separar referencias enseñadas por el operario vs base chilena precargada
    refs_operario = [
        r for r in referencias_memoria if r.get("origen") != "BASE_CHILENA_PRECARGADA"
    ]
    refs_chilenas = [
        r for r in referencias_memoria if r.get("origen") == "BASE_CHILENA_PRECARGADA"
    ]

    # 1. ¿Coincide con una imagen enseñada explícitamente por el operario?
    mejor_ref_op = None
    mejor_sim_op = 0.0
    for ref in refs_operario:
        sim = calcular_similitud_visual(huella_actual, ref.get("huella", {}))
        if sim > mejor_sim_op:
            mejor_sim_op = sim
            mejor_ref_op = ref

    if mejor_ref_op is not None and mejor_sim_op >= 74.0:
        return _construir_respuesta_desde_referencia(
            mejor_ref_op, mejor_sim_op, inventario, es_incoherente=False
        )

    # 2. ¿Tiene marca o texto legible por OCR (ej. McKay Kuky, Soprole, Tucapel, Carozzi)?
    if calidad_ok:
        det_ocr = _buscar_por_ocr_en_envase(
            huella_actual.get("textos_ocr", []), inventario, categorias
        )
        if det_ocr is not None:
            return det_ocr

    # 3. Comparar contra todas las referencias (Operario + Base Precargada del Mercado Chileno)
    mejor_ref_global = mejor_ref_op
    mejor_sim_global = mejor_sim_op

    for ref in refs_chilenas:
        sim = calcular_similitud_visual(huella_actual, ref.get("huella", {}))
        if sim > mejor_sim_global:
            mejor_sim_global = sim
            mejor_ref_global = ref

    if mejor_ref_global is None and referencias_memoria:
        mejor_ref_global = referencias_memoria[0]
        mejor_sim_global = 50.0

    es_incoherente = (not calidad_ok) or (mejor_sim_global < 72.0)
    motivo = (
        motivo_calidad
        if not calidad_ok
        else "Objeto sin marca legible ni referencia previa exacta"
    )
    sim_ajustada = min(mejor_sim_global, 48.0) if not calidad_ok else mejor_sim_global

    return _construir_respuesta_desde_referencia(
        mejor_ref_global,
        sim_ajustada,
        inventario,
        es_incoherente=es_incoherente,
        motivo_incoherencia=motivo,
    )
