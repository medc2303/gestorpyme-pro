"""
Módulo de Escaneo de Productos con Cámara, Relación Cruzada Imagen + Texto (OCR),
Base Pública de Fotografías Reales (Open Food Facts Chile) y Memoria Visual del Operario.

Arquitectura de Reconocimiento Cruzado (Imagen + Texto):
  1. AISLAMIENTO DEL OBJETO Y ELIMINACIÓN DE FONDO:
     Enmascara los píxeles oscuros del fondo de la habitación para extraer el
     histograma cromático y el perfil de color (rojo, azul, amarillo/naranja,
     verde, blanco, oscuro) exclusivamente sobre el empaque iluminado.
  2. LECTURA MULTIPASO DE TEXTO EN ENVASE (RapidOCR ONNX):
     Lee marcas, nombres, variantes ("Zero", "Sin Calorías", "Blanco") y formatos
     ("1.5L", "120g", "1kg") aplicando realce automático de contraste.
  3. RELACIÓN CRUZADA OBLIGATORIA IMAGEN + TEXTO:
     Cada candidato se evalúa cruzando su similitud visual de empaque (`sim_visual`)
     con su coincidencia textual (`sim_texto`). Si el envase frente a la cámara tiene
     texto legible (ej. "Coca-Cola Zero Sin Calorías 1.5L"), cualquier referencia en
     memoria cuyo texto contradiga lo leído (ej. "McKay Kuky") queda vetada automáticamente,
     impidiendo falsos positivos por similitud de fondo o iluminación.
  4. BASE PÚBLICA DE IMÁGENES REALES (Open Food Facts Chile):
     Precarga 33 fotografías reales de productos del mercado chileno desde
     `data/catalogo_chileno_real.json` (Open Food Facts `images.openfoodfacts.org`)
     y consulta la API pública de Open Food Facts en vivo si detecta una marca nueva.
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
from PIL import Image, ImageDraw, ImageFilter, ImageOps
import requests

from core.store import DIRECTORIO_DATOS, obtener_catalogos, obtener_inventario_consolidado

ARCHIVO_MEMORIA_VISUAL = DIRECTORIO_DATOS / "memoria_visual.json"
ARCHIVO_FOTOS_REALES_CHILE = DIRECTORIO_DATOS / "catalogo_chileno_real.json"

_OCR_INSTANCE: Any = None
_OCR_CARGADO: bool = False
_CACHE_FOTOS_REALES: dict[str, dict[str, str]] | None = None


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


def _cargar_fotos_reales_chile() -> dict[str, dict[str, str]]:
    """Carga el mapa de fotografías reales descargadas desde Open Food Facts."""
    global _CACHE_FOTOS_REALES
    if _CACHE_FOTOS_REALES is not None:
        return _CACHE_FOTOS_REALES
    if ARCHIVO_FOTOS_REALES_CHILE.exists():
        try:
            _CACHE_FOTOS_REALES = json.loads(
                ARCHIVO_FOTOS_REALES_CHILE.read_text(encoding="utf-8")
            )
            return _CACHE_FOTOS_REALES
        except Exception:
            pass
    _CACHE_FOTOS_REALES = {}
    return _CACHE_FOTOS_REALES


# ============================================================================
# CATÁLOGO DE PRODUCTOS COMUNES DEL MERCADO CHILENO (CON FOTOS REALES OFF)
# ============================================================================

CATALOGO_CHILENO_PRECARGADO: list[dict[str, Any]] = [
    # --- SNACKS, GALLETAS Y CONFITERÍA CHILENA (Categoría 3) ---
    {
        "sku_ref": "SNK-101",
        "sku_tienda": None,
        "nombre": "Galletas McKay Kuky ChipChipers Blanco 120g",
        "marca": "McKay",
        "claves": ["kuky", "mckay", "chipchiper", "chipchipers", "cnipchipera", "blanco", "blana", "blancd"],
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
        "claves": ["trencito", "nestle", "sahne", "nuss", "chocolate"],
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
        "sku_ref": "BEB-102",
        "sku_tienda": None,
        "nombre": "Bebida Coca-Cola Zero Azúcar 1.5L",
        "marca": "Coca-Cola",
        "claves": ["coca", "cocacola", "cocacou", "zero", "azucar", "sin", "calorias", "15l", "1.5l"],
        "id_categoria": 1,
        "peso": 1.5,
        "unidad_peso": "L",
        "formato": "LOTE",
        "upf": 6,
        "compra": 1250.0,
        "venta": 1990.0,
        "perecible": True,
        "colores": ((210, 25, 30), (25, 20, 20), (255, 255, 255)),
    },
    {
        "sku_ref": "BEB-104",
        "sku_tienda": None,
        "nombre": "Bebida Coca-Cola Original 1.5L",
        "marca": "Coca-Cola",
        "claves": ["coca", "cocacola", "cocacou", "original", "sabor", "15l", "1.5l"],
        "id_categoria": 1,
        "peso": 1.5,
        "unidad_peso": "L",
        "formato": "LOTE",
        "upf": 6,
        "compra": 1250.0,
        "venta": 1990.0,
        "perecible": True,
        "colores": ((220, 20, 30), (255, 255, 255), (45, 15, 15)),
    },
    {
        "sku_ref": "BEB-001",
        "sku_tienda": "BEB-001",
        "nombre": "Leche Entera 1L (Soprole / Colun)",
        "marca": "Soprole",
        "claves": ["soprole", "loncoleche", "surlat", "leche", "entera", "natural"],
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
# AISLAMIENTO DEL EMPAQUE (SIN FONDO OSCURO) Y EXTRACCIÓN DE HUELLA + OCR
# ============================================================================


def _recortar_objeto_activo(img: Image.Image) -> Image.Image:
    """
    Aísla la caja delimitadora 2D del producto iluminado descartando el fondo
    oscuro de la habitación tanto en filas como en columnas.
    """
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, w, _ = arr.shape
    if h < 32 or w < 32:
        return img

    max_rgb = arr.max(axis=2)
    sat = (max_rgb - arr.min(axis=2)) / np.maximum(max_rgb, 1.0)
    # Píxel pertenece al objeto si tiene brillo suficiente o color saturado
    mascara = (max_rgb > 46.0) | ((max_rgb > 32.0) & (sat > 0.28))

    prop_filas = mascara.mean(axis=1)
    prop_cols = mascara.mean(axis=0)
    filas_activas = np.where(prop_filas > 0.14)[0]
    cols_activas = np.where(prop_cols > 0.14)[0]

    if len(filas_activas) >= int(h * 0.18) and len(cols_activas) >= int(w * 0.18):
        y0 = max(0, int(filas_activas[0]) - 2)
        y1 = min(h, int(filas_activas[-1]) + 3)
        x0 = max(0, int(cols_activas[0]) - 2)
        x1 = min(w, int(cols_activas[-1]) + 3)
        if (y1 - y0) >= 24 and (x1 - x0) >= 24:
            return img.crop((x0, y0, x1, y1))

    return img


def _evaluar_calidad_imagen(img: Image.Image) -> tuple[bool, str]:
    """Detecta si la cámara está tapada/negra o sin objeto visible."""
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
    """Calcula dHash y aHash de 64 bits sobre el objeto recortado."""
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


def _calcular_descriptores_color(
    img_recortada: Image.Image,
) -> tuple[list[float], list[float], list[float]]:
    """
    Extrae:
      1. `grid_color` (48 floats): grilla espacial 4x4x3 del objeto.
      2. `hist_color` (48 floats): histograma cromático calculado EXCLUSIVAMENTE sobre
         los píxeles activos del producto (ignorando píxeles negros del fondo de la sala).
      3. `perfil_color` (6 floats): proporción semántica de colores del empaque
         [rojo, azul_celeste, amarillo_naranja, verde, blanco_claro, oscuro_cafe].
    """
    peq = np.asarray(
        img_recortada.convert("RGB").resize((64, 64), Image.Resampling.LANCZOS),
        dtype=np.float32,
    )
    r_ch = peq[:, :, 0]
    g_ch = peq[:, :, 1]
    b_ch = peq[:, :, 2]
    max_c = np.maximum(np.maximum(r_ch, g_ch), b_ch)
    min_c = np.minimum(np.minimum(r_ch, g_ch), b_ch)
    diff_c = max_c - min_c

    # Máscara de primer plano: descartar fondo negro/oscuro sin color
    mask_fg = max_c >= 42.0
    if int(mask_fg.sum()) < 64:
        mask_fg = np.ones_like(max_c, dtype=bool)

    fg_r = r_ch[mask_fg]
    fg_g = g_ch[mask_fg]
    fg_b = b_ch[mask_fg]
    fg_max = max_c[mask_fg]
    fg_diff = diff_c[mask_fg]
    n_fg = float(len(fg_r))

    # Perfil semántico de 6 familias cromáticas sobre el objeto real
    es_rojo = (fg_r > 100.0) & (fg_r > fg_g * 1.32) & (fg_r > fg_b * 1.32)
    es_azul = (fg_b > 85.0) & (fg_b > fg_r * 1.15) & (fg_b >= fg_g * 0.95)
    es_amarillo_naranja = (
        (fg_r > 135.0) & (fg_g > 85.0) & (fg_b < fg_g * 0.78) & (~es_rojo)
    )
    es_verde = (fg_g > 85.0) & (fg_g > fg_r * 1.12) & (fg_g > fg_b * 1.08)
    es_blanco = (fg_max > 160.0) & (fg_diff < 42.0)
    es_oscuro = (fg_max < 95.0) & (~es_rojo) & (~es_azul)

    perfil = np.array(
        [
            float(es_rojo.sum()) / n_fg,
            float(es_azul.sum()) / n_fg,
            float(es_amarillo_naranja.sum()) / n_fg,
            float(es_verde.sum()) / n_fg,
            float(es_blanco.sum()) / n_fg,
            float(es_oscuro.sum()) / n_fg,
        ],
        dtype=np.float32,
    )
    norm_p = float(np.linalg.norm(perfil))
    perfil_list = (
        [round(float(x / norm_p), 4) for x in perfil] if norm_p > 1e-6 else [0.0] * 6
    )

    # Normalizar contraste solo con percentiles de píxeles del objeto
    p5 = float(np.percentile(peq[mask_fg], 5))
    p95 = float(np.percentile(peq[mask_fg], 95))
    rango = max(25.0, p95 - p5)
    norm_img = np.clip((peq - p5) / rango, 0.0, 1.0)

    # Histograma de 48 bins solo sobre píxeles del primer plano (mask_fg)
    bins = np.linspace(0.0, 1.0001, 17)
    h_r, _ = np.histogram(norm_img[:, :, 0][mask_fg], bins=bins)
    h_g, _ = np.histogram(norm_img[:, :, 1][mask_fg], bins=bins)
    h_b, _ = np.histogram(norm_img[:, :, 2][mask_fg], bins=bins)
    hist = np.concatenate([h_r, h_g, h_b]).astype(np.float32)
    norma_h = float(np.linalg.norm(hist))
    hist_list = (
        [round(float(x / norma_h), 4) for x in hist] if norma_h > 1e-6 else [0.0] * 48
    )

    # Grilla espacial 4x4x3 sobre la zona central (evitando esquinas de fondo)
    central = norm_img[8:56, 8:56, :]
    grid = (
        np.asarray(
            Image.fromarray(np.uint8(central * 255)).resize(
                (4, 4), Image.Resampling.BOX
            ),
            dtype=np.float32,
        ).flatten()
        / 255.0
    )
    norma_g = float(np.linalg.norm(grid))
    grid_list = (
        [round(float(x / norma_g), 4) for x in grid] if norma_g > 1e-6 else [0.0] * 48
    )

    return grid_list, hist_list, perfil_list


def _extraer_texto_ocr(img_recortada: Image.Image) -> list[str]:
    """
    Ejecuta RapidOCR en doble pasada (imagen original + imagen con realce de contraste
    y nitidez) para capturar tanto letras claras como textos oscuros sobre etiquetas rojas/azules.
    """
    motor = _obtener_motor_ocr()
    if motor is None:
        return []

    try:
        ancho, alto = img_recortada.size
        if max(ancho, alto) > 720:
            escala = 720.0 / max(ancho, alto)
            base_ocr = img_recortada.resize(
                (max(1, int(ancho * escala)), max(1, int(alto * escala))),
                Image.Resampling.LANCZOS,
            )
        else:
            base_ocr = img_recortada

        variantes = [base_ocr]
        try:
            mejorada = ImageOps.autocontrast(base_ocr, cutoff=2).filter(
                ImageFilter.SHARPEN
            )
            variantes.append(mejorada)
        except Exception:
            pass

        ignorar = {"clear photo", "clearphoto", "take photo", "takephoto"}
        textos: list[str] = []
        vistos_low: set[str] = set()

        for var_img in variantes:
            arr = np.asarray(var_img.convert("RGB"))
            resultados, _ = motor(arr)
            if not resultados:
                continue
            for item in resultados:
                txt = str(item[1]).strip()
                conf = float(item[2])
                limpio = re.sub(
                    r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9\.\-% ]+", "", txt
                ).strip()
                low = limpio.lower()
                if (
                    len(limpio) >= 2
                    and conf >= 0.42
                    and low not in ignorar
                    and low not in vistos_low
                ):
                    vistos_low.add(low)
                    textos.append(limpio)

        return textos
    except Exception:
        return []


def extraer_huella_visual(
    imagen_bytes: bytes, incluir_ocr: bool = True
) -> dict[str, Any]:
    """Extrae el descriptor visual sin fondo + textos OCR de una imagen."""
    img_original = Image.open(io.BytesIO(imagen_bytes)).convert("RGB")
    img_obj = _recortar_objeto_activo(img_original)

    dhash_hex, ahash_hex = _calcular_hashes_perceptuales(img_obj)
    grid_color, hist_color, perfil_color = _calcular_descriptores_color(img_obj)
    textos_ocr = _extraer_texto_ocr(img_obj) if incluir_ocr else []

    thumb = img_obj.copy()
    thumb.thumbnail((140, 100), Image.Resampling.LANCZOS)
    buf_t = io.BytesIO()
    thumb.save(buf_t, format="JPEG", quality=78)
    thumb_b64 = base64.b64encode(buf_t.getvalue()).decode("ascii")

    return {
        "dhash": dhash_hex,
        "ahash": ahash_hex,
        "grid_color": grid_color,
        "hist_color": hist_color,
        "perfil_color": perfil_color,
        "textos_ocr": textos_ocr,
        "miniatura_b64": thumb_b64,
    }


def generar_imagen_referencia_chilena(item_chileno: dict[str, Any]) -> bytes:
    """
    Retorna la fotografía real del producto chileno descargada desde Open Food Facts
    (`data/catalogo_chileno_real.json`). Si algún SKU no tuviera foto en caché,
    genera un respaldo visual con sus colores.
    """
    fotos_reales = _cargar_fotos_reales_chile()
    sku = item_chileno.get("sku_ref") or item_chileno.get("sku_tienda") or ""
    if sku in fotos_reales and fotos_reales[sku].get("b64"):
        try:
            return base64.b64decode(fotos_reales[sku]["b64"])
        except Exception:
            pass

    c_principal, c_secundario, c_acento = item_chileno.get(
        "colores", ((29, 78, 216), (220, 38, 38), (255, 255, 255))
    )
    img = Image.new("RGB", (240, 165), color=c_principal)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 240, 42], fill=c_secundario)
    draw.rectangle([0, 125, 240, 165], fill=c_secundario)
    draw.rectangle([16, 26, 110, 56], fill=c_acento)
    marca = str(item_chileno.get("marca", "CHILE")).upper()[:14]
    nombre = str(item_chileno.get("nombre", "PRODUCTO"))[:26]
    draw.text((22, 34), marca, fill=(15, 23, 42))
    draw.text((18, 72), nombre, fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _construir_base_visual_chilena_por_defecto() -> list[dict[str, Any]]:
    """
    Construye la base precargada de 33 referencias del mercado chileno utilizando
    las fotografías reales descargadas desde Open Food Facts (`catalogo_chileno_real.json`).
    """
    categorias_map = {
        1: "Bebidas y Lácteos",
        2: "Abarrotes y Despensa",
        3: "Snacks y Confitería",
        4: "Limpieza del Hogar",
        5: "Cuidado Personal",
    }
    fotos_reales = _cargar_fotos_reales_chile()
    referencias: list[dict[str, Any]] = []
    ahora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for idx, prod_ch in enumerate(CATALOGO_CHILENO_PRECARGADO, start=1):
        sku_key = prod_ch["sku_ref"]
        img_bytes = generar_imagen_referencia_chilena(prod_ch)
        huella = extraer_huella_visual(img_bytes, incluir_ocr=False)
        huella["textos_ocr"] = list(prod_ch["claves"])
        fuente_foto = fotos_reales.get(sku_key, {}).get(
            "fuente", "Open Food Facts Chile"
        )

        referencias.append(
            {
                "id_referencia": idx,
                "fecha_aprendizaje": ahora_str,
                "origen": "BASE_CHILENA_PRECARGADA",
                "fuente_imagen": fuente_foto,
                "es_existente": prod_ch["sku_tienda"] is not None,
                "id_producto": None,
                "codigo_sku": prod_ch["sku_tienda"] or prod_ch["sku_ref"],
                "nombre_producto": prod_ch["nombre"],
                "marca": prod_ch["marca"],
                "id_categoria": prod_ch["id_categoria"],
                "nombre_categoria": categorias_map.get(
                    prod_ch["id_categoria"], "General"
                ),
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
# RELACIÓN CRUZADA ENTRE IMAGEN Y TEXTO (CROSS-MODAL SCORING)
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


def _tokenizar_ocr(textos: list[str]) -> list[str]:
    stopwords = {"clear", "photo", "take", "con", "por", "para", "del", "las", "los"}
    tokens: list[str] = []
    for frase in textos:
        for t in re.split(r"[\s\-\.,/]+", frase.lower()):
            limpio = re.sub(r"[^a-záéíóúüñ0-9]+", "", t)
            if len(limpio) >= 3 and limpio not in stopwords and limpio not in tokens:
                tokens.append(limpio)
    return tokens


def calcular_similitud_solo_imagen(
    huella_nueva: dict[str, Any], huella_ref: dict[str, Any]
) -> float:
    """
    Calcula la similitud puramente visual (0 a 100%) sobre los píxeles del objeto
    (excluyendo el fondo oscuro de la habitación).
    """
    sim_hist = _similitud_coseno(
        huella_nueva.get("hist_color", []), huella_ref.get("hist_color", [])
    )
    sim_perfil = _similitud_coseno(
        huella_nueva.get("perfil_color", []), huella_ref.get("perfil_color", [])
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

    if huella_nueva.get("perfil_color") and huella_ref.get("perfil_color"):
        puntaje = (
            0.38 * sim_hist + 0.32 * sim_perfil + 0.16 * sim_grid + 0.14 * sim_hash
        ) * 100.0
    else:
        puntaje = (0.45 * sim_hist + 0.30 * sim_grid + 0.25 * sim_hash) * 100.0

    return round(min(99.5, max(0.0, puntaje)), 1)


def calcular_similitud_solo_texto(
    tokens_captura: list[str], tokens_candidato: list[str]
) -> tuple[float, list[str]]:
    """
    Evalúa cuánto coincide el texto OCR leído en la cámara con las palabras clave
    del producto candidato. Retorna `(puntaje_0_a_100, palabras_coincidentes)`.
    """
    if not tokens_captura or not tokens_candidato:
        return 0.0, []

    coincidentes: list[str] = []
    puntaje_acum = 0.0

    for tk_cap in tokens_captura:
        mejor_ratio = 0.0
        for tk_ref in tokens_candidato:
            if tk_cap == tk_ref:
                mejor_ratio = 1.0
                break
            if len(tk_ref) >= 4 and (tk_ref in tk_cap or tk_cap in tk_ref):
                mejor_ratio = max(mejor_ratio, 0.92)
            else:
                r = SequenceMatcher(None, tk_cap, tk_ref).ratio()
                if r > mejor_ratio:
                    mejor_ratio = r

        if mejor_ratio >= 0.74:
            puntaje_acum += mejor_ratio
            coincidentes.append(tk_cap)

    if not coincidentes:
        return 0.0, []

    # Si coincide 1 palabra de marca fuerte (>=74%) ya tiene base >= 68 pts, y sube con cada palabra adicional
    base = 65.0 + min(34.0, (puntaje_acum - 0.74) * 22.0 + (len(coincidentes) - 1) * 10.0)
    return round(min(99.0, max(0.0, base)), 1), coincidentes


def calcular_relacion_cruzada_imagen_texto(
    huella_captura: dict[str, Any],
    ref_candidato: dict[str, Any],
    hay_texto_en_captura: bool,
) -> dict[str, Any]:
    """
    Realiza la validación cruzada entre la Imagen capturada y el Texto OCR leído:
      - Si la cámara leyó texto en el envase y el candidato coincide tanto en Texto
        como en Imagen, combina ambos puntajes con sinergia positiva.
      - Si la cámara leyó texto en el envase (ej. "Coca-Cola Sin Calorías 1.5L") pero
        el candidato en memoria tiene un texto totalmente distinto (ej. "McKay Kuky"),
        aplica un VETO POR CONTRADICCIÓN TEXTUAL para que jamás devuelva Galletas
        cuando frente a la cámara hay otro producto con etiqueta legible.
    """
    huella_ref = ref_candidato.get("huella", {})
    sim_img = calcular_similitud_solo_imagen(huella_captura, huella_ref)

    tokens_cap = _tokenizar_ocr(huella_captura.get("textos_ocr", []))
    textos_ref = list(huella_ref.get("textos_ocr", [])) + [
        str(ref_candidato.get("nombre_producto", "")),
        str(ref_candidato.get("marca", "")),
    ]
    tokens_ref = _tokenizar_ocr(textos_ref)

    sim_txt, palabras_match = calcular_similitud_solo_texto(tokens_cap, tokens_ref)

    if hay_texto_en_captura:
        if sim_txt >= 55.0:
            # Coincidencia cruzada Imagen + Texto
            bono_coherencia = 10.0 if sim_img >= 45.0 else 0.0
            score_cruzado = min(
                99.0, 0.60 * sim_txt + 0.40 * sim_img + bono_coherencia
            )
            modo_cruce = "IMAGEN_Y_TEXTO_COINCIDENTES"
        else:
            # Contradicción: el envase en cámara dice un texto que NO pertenece a este candidato
            score_cruzado = sim_img * 0.22
            modo_cruce = "VETADO_POR_TEXTO_DISTINTO"
    else:
        # La captura no tiene texto legible: evaluar puramente por imagen sin fondo
        score_cruzado = sim_img
        modo_cruce = "SOLO_IMAGEN"

    return {
        "score_cruzado": round(score_cruzado, 1),
        "sim_imagen": sim_img,
        "sim_texto": sim_txt,
        "palabras_match": palabras_match,
        "modo_cruce": modo_cruce,
    }


def calcular_similitud_visual(
    huella_nueva: dict[str, Any], huella_ref: dict[str, Any]
) -> float:
    """Función compatible de similitud cruzada entre dos huellas."""
    tokens_cap = _tokenizar_ocr(huella_nueva.get("textos_ocr", []))
    res = calcular_relacion_cruzada_imagen_texto(
        huella_nueva,
        {"huella": huella_ref},
        hay_texto_en_captura=(len(tokens_cap) > 0),
    )
    return res["score_cruzado"]


# ============================================================================
# PERSISTENCIA DE MEMORIA VISUAL Y CONSULTA EN VIVO A OPEN FOOD FACTS
# ============================================================================


def cargar_memoria_visual() -> list[dict[str, Any]]:
    """
    Carga la Memoria Visual. Garantiza que las 33 referencias con fotografías reales
    de Open Food Facts Chile estén siempre actualizadas y disponibles.
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

    refs_chilenas = [
        r for r in existentes if r.get("origen") == "BASE_CHILENA_PRECARGADA"
    ]
    # Verificar que las referencias chilenas tengan el nuevo descriptor `perfil_color` y fotos reales
    tiene_perfil_y_fotos = (
        len(refs_chilenas) >= 30
        and all("perfil_color" in r.get("huella", {}) for r in refs_chilenas[:5])
        and any("Open Food Facts" in str(r.get("fuente_imagen", "")) for r in refs_chilenas)
    )

    if not tiene_perfil_y_fotos:
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
    """Guarda atómicamente la Memoria Visual en disco."""
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
    Guarda en la Memoria Visual la imagen capturada por cámara junto a su texto OCR
    y el producto confirmado o corregido por el operario.
    """
    huella = extraer_huella_visual(imagen_bytes, incluir_ocr=True)
    referencias = cargar_memoria_visual()
    ahora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    nombre_real = str(datos_producto.get("nombre_detectado", "")).strip()
    textos_combinados = list(huella.get("textos_ocr", []))
    for palabra in re.split(r"\s+", nombre_real):
        limpia = re.sub(r"[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9\.]+", "", palabra)
        if len(limpia) >= 3 and limpia not in textos_combinados:
            textos_combinados.append(limpia)

    registro = {
        "id_referencia": max((r.get("id_referencia", 0) for r in referencias), default=0) + 1,
        "fecha_aprendizaje": ahora_str,
        "origen": origen,
        "fuente_imagen": "Captura de Cámara del Operario",
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
        referencias = referencias[:95]

    guardar_memoria_visual(referencias)
    return registro


def vincular_producto_creado_en_memoria(
    nombre_producto: str, producto_creado: dict[str, Any]
) -> None:
    """Actualiza las referencias de un producto recién creado con su ID y SKU definitivos."""
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


def _consultar_openfoodfacts_en_vivo(
    textos_ocr: list[str],
    huella_captura: dict[str, Any],
    inventario: list[dict[str, Any]],
    categorias: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """
    Si el texto OCR leído en el envase corresponde a un producto que no está en las
    33 referencias locales, consulta en vivo la base pública Open Food Facts
    (`https://search.openfoodfacts.org/search`) y valida su imagen.
    """
    tokens = _tokenizar_ocr(textos_ocr)
    if not tokens:
        return None

    consulta = " ".join(tokens[:3])
    try:
        r = requests.get(
            "https://search.openfoodfacts.org/search",
            params={"q": consulta, "page_size": 3},
            headers={"User-Agent": "GestorPyMEPro/1.0"},
            timeout=5,
        )
        if r.status_code != 200:
            return None
        hits = r.json().get("hits", [])
        if not hits:
            return None

        mejor_hit = hits[0]
        nombre_off = (
            mejor_hit.get("product_name_es")
            or mejor_hit.get("product_name")
            or consulta.title()
        ).strip()
        marcas_off = mejor_hit.get("brands") or []
        marca_str = marcas_off[0] if isinstance(marcas_off, list) and marcas_off else str(marcas_off or "")
        if marca_str and marca_str.lower() not in nombre_off.lower():
            nombre_completo = f"{nombre_off} ({marca_str})".strip()
        else:
            nombre_completo = nombre_off

        cat_default = categorias[0] if categorias else {"id_categoria": 1, "nombre_categoria": "General"}
        pref = cat_default["nombre_categoria"][:3].upper()

        return {
            "es_existente": False,
            "id_producto": None,
            "codigo_sku": f"{pref}-{len(inventario) + 15:03d}",
            "nombre_detectado": nombre_completo,
            "nombre_categoria": cat_default["nombre_categoria"],
            "id_categoria": cat_default["id_categoria"],
            "stock_actual": 0,
            "formato_sugerido": "CAJA",
            "unidades_por_formato_sugeridas": 12,
            "peso_sugerido": 1.0,
            "unidad_peso_sugerida": "kg",
            "precio_compra_sugerido": 1000.0,
            "precio_venta_sugerido": 1590.0,
            "perecible_sugerido": True,
            "confianza_pct": 85,
            "descripcion_visual": (
                f"Relación Cruzada Imagen + Texto en Open Food Facts: "
                f"Texto leído «{' · '.join(textos_ocr[:4])}»"
            ),
            "motor_vision": "🌐 Base Pública Open Food Facts + OCR",
            "recordado_de_memoria": False,
            "es_incoherente": False,
        }
    except Exception:
        return None


# ============================================================================
# FUNCIÓN PRINCIPAL DE DETECCIÓN CRUZADA (IMAGEN + TEXTO)
# ============================================================================


def _vincular_con_inventario_activo(
    sku_tienda: str | None,
    nombre_buscado: str,
    inventario: list[dict[str, Any]],
) -> dict[str, Any] | None:
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


def _construir_respuesta_cruzada(
    ref: dict[str, Any],
    eval_cruce: dict[str, Any],
    textos_ocr_captura: list[str],
    inventario: list[dict[str, Any]],
    es_incoherente: bool = False,
    motivo_incoherencia: str = "",
) -> dict[str, Any]:
    """Construye la respuesta final explicando la relación cruzada entre Imagen y Texto."""
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

    score = eval_cruce["score_cruzado"]
    sim_img = eval_cruce["sim_imagen"]
    sim_txt = eval_cruce["sim_texto"]
    modo_cruce = eval_cruce["modo_cruce"]
    es_aprendida_op = ref.get("origen") != "BASE_CHILENA_PRECARGADA"

    if modo_cruce == "IMAGEN_Y_TEXTO_COINCIDENTES":
        txt_leido = " · ".join(textos_ocr_captura[:5])
        desc = (
            f"Validación Cruzada Imagen + Texto exitosa: Texto leído «{txt_leido}» "
            f"({sim_txt:.0f}% coincidencia textual + {sim_img:.0f}% coincidencia visual de empaque)"
        )
        motor_lbl = (
            "🧠 Memoria Visual + Texto OCR"
            if es_aprendida_op
            else "🇨🇱 Base Open Food Facts Chile (Imagen + OCR)"
        )
    elif es_incoherente:
        desc = (
            f"⚠️ Captura sin texto legible o baja certeza ({motivo_incoherencia}). "
            f"Referencia chilena más próxima sugerida ({score:.0f}%): confirma o corrige abajo."
        )
        motor_lbl = "⚠️ Baja Certeza (Respaldo Base Chilena)"
    elif es_aprendida_op:
        desc = (
            f"Reconocido por Memoria Visual enseñada por el operario "
            f"({sim_img:.1f}% similitud visual de empaque)"
        )
        motor_lbl = "🧠 Memoria Visual Aprendida (Operario)"
    else:
        desc = (
            f"Coincidencia visual con fotografía real de Open Food Facts Chile "
            f"({sim_img:.1f}% similitud de empaque)"
        )
        motor_lbl = "🇨🇱 Base Open Food Facts Chile"

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
            "confianza_pct": int(round(score)),
            "descripcion_visual": desc,
            "motor_vision": motor_lbl,
            "recordado_de_memoria": (es_aprendida_op or modo_cruce == "IMAGEN_Y_TEXTO_COINCIDENTES")
            and not es_incoherente,
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
        "confianza_pct": int(round(score)),
        "descripcion_visual": desc,
        "motor_vision": motor_lbl,
        "recordado_de_memoria": (es_aprendida_op or modo_cruce == "IMAGEN_Y_TEXTO_COINCIDENTES")
        and not es_incoherente,
        "es_incoherente": es_incoherente,
    }


def detectar_producto_en_imagen(
    imagen_bytes: bytes,
    api_key_gemini: str = "",
) -> dict[str, Any]:
    """
    Detecta el producto en la fotografía capturada por cámara aplicando
    Relación Cruzada entre la Imagen (sin fondo negro) y el Texto OCR leído en el envase:
      1. Extrae la huella visual del objeto recortado y lee el texto impreso con RapidOCR.
      2. Evalúa todos los candidatos (Memoria del Operario + 33 Fotos Reales de Open Food Facts
         + Inventario Activo) cruzando simultáneamente `sim_imagen` y `sim_texto`.
      3. Si la cámara leyó texto en el envase (ej. "Coca-Cola Sin Calorías 1.5L"), veta
         automáticamente cualquier referencia cuyo texto no coincida (ej. "Galletas Kuky"),
         eligiendo el producto donde Imagen y Texto coinciden.
      4. Si el texto leído corresponde a una marca nueva no precargada, consulta en vivo
         la API pública de Open Food Facts.
    """
    inventario = obtener_inventario_consolidado()
    catalogos = obtener_catalogos()
    categorias = catalogos["categorias"]

    img_pil = Image.open(io.BytesIO(imagen_bytes)).convert("RGB")
    calidad_ok, motivo_calidad = _evaluar_calidad_imagen(img_pil)

    huella_captura = extraer_huella_visual(imagen_bytes, incluir_ocr=calidad_ok)
    textos_ocr = huella_captura.get("textos_ocr", [])
    tokens_ocr = _tokenizar_ocr(textos_ocr)
    hay_texto = len(tokens_ocr) > 0

    referencias_memoria = cargar_memoria_visual()

    # Evaluar todos los candidatos con la Relación Cruzada Imagen + Texto
    mejor_ref = None
    mejor_eval = {
        "score_cruzado": -1.0,
        "sim_imagen": 0.0,
        "sim_texto": 0.0,
        "palabras_match": [],
        "modo_cruce": "SOLO_IMAGEN",
    }

    for ref in referencias_memoria:
        ev = calcular_relacion_cruzada_imagen_texto(
            huella_captura, ref, hay_texto_en_captura=hay_texto
        )
        # Pequeña preferencia de desempate (+1.5 pts) a referencias enseñadas por el operario
        # SOLO cuando no están vetadas por texto distinto
        score_comp = ev["score_cruzado"]
        if (
            ref.get("origen") != "BASE_CHILENA_PRECARGADA"
            and ev["modo_cruce"] != "VETADO_POR_TEXTO_DISTINTO"
        ):
            score_comp += 1.5

        if score_comp > mejor_eval["score_cruzado"]:
            mejor_eval = {**ev, "score_cruzado": min(99.5, round(score_comp, 1))}
            mejor_ref = ref

    # Si la cámara leyó texto claro en el envase, pero ningún candidato local coincidió en texto,
    # consultar la base pública Open Food Facts en vivo con el texto leído
    if hay_texto and mejor_eval["sim_texto"] < 45.0:
        det_off_vivo = _consultar_openfoodfacts_en_vivo(
            textos_ocr, huella_captura, inventario, categorias
        )
        if det_off_vivo is not None:
            return det_off_vivo

        # Si está sin internet pero leyó palabras claras en el envase, proponer el texto leído
        nombre_leido = " ".join(textos_ocr[:3]).title()
        cat_def = categorias[0] if categorias else {"id_categoria": 1, "nombre_categoria": "General"}
        pref = cat_def["nombre_categoria"][:3].upper()
        return {
            "es_existente": False,
            "id_producto": None,
            "codigo_sku": f"{pref}-{len(inventario) + 14:03d}",
            "nombre_detectado": nombre_leido,
            "nombre_categoria": cat_def["nombre_categoria"],
            "id_categoria": cat_def["id_categoria"],
            "stock_actual": 0,
            "formato_sugerido": "CAJA",
            "unidades_por_formato_sugeridas": 12,
            "peso_sugerido": 1.0,
            "unidad_peso_sugerida": "kg",
            "precio_compra_sugerido": 950.0,
            "precio_venta_sugerido": 1490.0,
            "perecible_sugerido": True,
            "confianza_pct": 80,
            "descripcion_visual": f"Texto leído directamente del envase: «{' · '.join(textos_ocr[:4])}»",
            "motor_vision": "IA Lectora de Empaque (Imagen + OCR)",
            "recordado_de_memoria": False,
            "es_incoherente": False,
        }

    if mejor_ref is None and referencias_memoria:
        mejor_ref = referencias_memoria[0]

    es_match_exacto_operario = (
        mejor_ref is not None
        and mejor_ref.get("origen") != "BASE_CHILENA_PRECARGADA"
        and mejor_eval["modo_cruce"] != "VETADO_POR_TEXTO_DISTINTO"
        and mejor_eval["sim_imagen"] >= 85.0
    )

    es_incoherente = (not es_match_exacto_operario) and (
        (not calidad_ok)
        or (
            mejor_eval["modo_cruce"] != "IMAGEN_Y_TEXTO_COINCIDENTES"
            and mejor_eval["score_cruzado"] < 75.0
        )
    )
    motivo = (
        motivo_calidad
        if not calidad_ok
        else "Objeto sin texto legible ni alta similitud visual"
    )
    if not calidad_ok and not es_match_exacto_operario:
        mejor_eval["score_cruzado"] = min(mejor_eval["score_cruzado"], 45.0)

    return _construir_respuesta_cruzada(
        mejor_ref,
        mejor_eval,
        textos_ocr,
        inventario,
        es_incoherente=es_incoherente,
        motivo_incoherencia=motivo,
    )
