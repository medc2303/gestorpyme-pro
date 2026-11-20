"""
Módulo de Escaneo de Productos con Cámara, Relación Cruzada Imagen + Texto (OCR),
Reconstrucción de Fragmentos de Texto en Envases Curvos, Base Masiva de 106
Productos Reales del Mercado Chileno (Open Food Facts + Wikimedia Commons) y
Memoria Visual de Aprendizaje del Operario.

Mejoras clave:
  1. BASE MASIVA DE 106 PRODUCTOS DEL MERCADO CHILENO CON FOTOGRAFÍAS REALES:
     Incluye isotónicas (Powerade, Gatorade), energéticas (Monster, Red Bull, Score),
     gaseosas (Coca-Cola Zero/Original, Pepsi, Fanta, Sprite, Kem Piña, Bilz, Pap,
     Canada Dry), aguas (Cachantún, Vital, Benedictino), jugos (Watt's, Andina, Kapo),
     lácteos y refrigerados (Soprole, Colun, Loncoleche, Chandelle, Manjar, Queso Gauda,
     Mantequilla), galletas y confites (McKay Kuky, Tritón, Morocha, Criollitas, Soda,
     Nik, Costa Tuareg, Frac, Gretel, Chocman, Super 8, Trencito, Sahne-Nuss, KitKat,
     Rama, Golpe, Bon o Bon, Frugelé), snacks (Lay's, Kryzpo, Pringles, Doritos,
     Cheetos, Ramitas, Marco Polo), abarrotes (Tucapel, Chef, Belmont, Carozzi,
     Lucchetti, Pomarola, Iansa, Sal Lobos, Té Supremo, Yerba Mate, Nescafé, Milo,
     Chocapic, Quaker, Selecta, Robinson Crusoe, San José, Banquete, Wasil, Hellmann's,
     JB, Maggi, Ideal/Bimbo) y limpieza/cuidado personal (Omo, Soft, Clorinda, Quix,
     Poett, Lysoform, Confort, Nova, Ballerina, Pepsodent, Colgate, Rexona, Dove, Ladysoft).
  2. RECONSTRUCCIÓN DE PALABRAS PARTIDAS EN BOTELLAS CURVAS (`_tokenizar_ocr`):
     Cuando el OCR lee palabras partidas por la curvatura del envase (como «POWER» +
     «YYADE» en una botella de Powerade, o «GATO» + «RADE», «COCA» + «COLA»), une
     automáticamente fragmentos adyacentes y normaliza letras repetidas («poweryyade» ->
     «poweryade» -> 94% de coincidencia con «powerade»).
  3. VALIDACIÓN ESTRICTA EN OPEN FOOD FACTS EN VIVO:
     Jamás recomienda un producto en inglés o sin relación si el nombre/marca devuelto
     por la API no supera el umbral de coincidencia textual con lo leído por el OCR.
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
    """Carga el mapa de fotografías reales descargadas desde Open Food Facts y Wikimedia."""
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
# BASE MASIVA DE 106 PRODUCTOS DEL MERCADO CHILENO
# ============================================================================

def _crear_item_cat(
    sku_ref: str,
    sku_tienda: str | None,
    nombre: str,
    marca: str,
    id_cat: int,
    peso: float,
    unid_peso: str,
    fmt: str,
    upf: int,
    compra: float,
    venta: float,
    perecible: bool,
    color_p: tuple[int, int, int],
    claves: list[str],
) -> dict[str, Any]:
    c2 = (max(0, color_p[0] - 45), max(0, color_p[1] - 45), max(0, color_p[2] - 45))
    return {
        "sku_ref": sku_ref,
        "sku_tienda": sku_tienda,
        "nombre": nombre,
        "marca": marca,
        "id_categoria": id_cat,
        "peso": float(peso),
        "unidad_peso": unid_peso,
        "formato": fmt,
        "upf": int(upf),
        "compra": float(compra),
        "venta": float(venta),
        "perecible": bool(perecible),
        "colores": (color_p, c2, (255, 255, 255)),
        "claves": claves,
    }


CATALOGO_CHILENO_PRECARGADO: list[dict[str, Any]] = [
    # 1. BEBIDAS, ISOTÓNICAS, ENERGÉTICAS, AGUAS, JUGOS Y LÁCTEOS (Cat 1)
    _crear_item_cat("BEB-110", None, "Bebida Isotónica Powerade Mountain Blast Azul 600ml", "Powerade", 1, 600, "ml", "LOTE", 6, 850, 1490, True, (2, 132, 199), ["powerade", "power", "yyade", "poweryade", "poweryyade", "ion4", "mountain", "blast", "isotonica"]),
    _crear_item_cat("BEB-111", None, "Bebida Isotónica Powerade Frutas Tropicales Rojo 600ml", "Powerade", 1, 600, "ml", "LOTE", 6, 850, 1490, True, (220, 38, 38), ["powerade", "power", "yyade", "poweryade", "poweryyade", "ion4", "tropicales", "frutas"]),
    _crear_item_cat("BEB-112", None, "Bebida Isotónica Powerade Naranja 600ml", "Powerade", 1, 600, "ml", "LOTE", 6, 850, 1490, True, (249, 115, 22), ["powerade", "power", "yyade", "poweryade", "naranja", "ion4"]),
    _crear_item_cat("BEB-113", None, "Bebida Isotónica Gatorade Cool Blue 500ml", "Gatorade", 1, 500, "ml", "LOTE", 6, 890, 1550, True, (14, 165, 233), ["gatorade", "gato", "rade", "cool", "blue", "isotonica"]),
    _crear_item_cat("BEB-114", None, "Bebida Isotónica Gatorade Frutas Tropicales 500ml", "Gatorade", 1, 500, "ml", "LOTE", 6, 890, 1550, True, (220, 38, 38), ["gatorade", "frutas", "tropicales"]),
    _crear_item_cat("BEB-115", None, "Bebida Energética Monster Energy Green Lata 473ml", "Monster", 1, 473, "ml", "CAJA", 6, 1250, 1990, True, (22, 163, 74), ["monster", "energy", "taurina", "473ml"]),
    _crear_item_cat("BEB-116", None, "Bebida Energética Monster Ultra White Sin Azúcar 473ml", "Monster", 1, 473, "ml", "CAJA", 6, 1250, 1990, True, (241, 245, 249), ["monster", "ultra", "zero", "energy"]),
    _crear_item_cat("BEB-117", None, "Bebida Energética Red Bull Lata 250ml", "Red Bull", 1, 250, "ml", "CAJA", 12, 1150, 1890, True, (29, 78, 216), ["redbull", "red", "bull", "energetica", "energy"]),
    _crear_item_cat("BEB-118", None, "Bebida Energética Score Energy Lata 473ml", "Score", 1, 473, "ml", "CAJA", 12, 850, 1490, True, (25, 25, 30), ["score", "energy", "gorilla", "energetica"]),
    _crear_item_cat("BEB-102", None, "Bebida Coca-Cola Zero Azúcar Sin Calorías 1.5L", "Coca-Cola", 1, 1.5, "L", "LOTE", 6, 1250, 1990, True, (210, 25, 30), ["coca", "cocacola", "cocacou", "zero", "azucar", "sin", "calorias", "calorian", "15l", "1.5l"]),
    _crear_item_cat("BEB-104", None, "Bebida Coca-Cola Original 1.5L", "Coca-Cola", 1, 1.5, "L", "LOTE", 6, 1250, 1990, True, (220, 20, 30), ["coca", "cocacola", "cocacou", "original", "sabor", "15l", "1.5l"]),
    _crear_item_cat("BEB-119", None, "Bebida Coca-Cola Original Lata 350ml", "Coca-Cola", 1, 350, "ml", "CAJA", 12, 580, 990, True, (220, 20, 30), ["coca", "cocacola", "350ml", "lata"]),
    _crear_item_cat("BEB-120", None, "Bebida Pepsi Regular 1.5L", "Pepsi", 1, 1.5, "L", "LOTE", 6, 1050, 1750, True, (29, 78, 216), ["pepsi", "cola", "1.5l"]),
    _crear_item_cat("BEB-121", None, "Bebida Pepsi Zero Sin Azúcar 1.5L", "Pepsi", 1, 1.5, "L", "LOTE", 6, 1050, 1750, True, (20, 20, 25), ["pepsi", "zero", "max", "black"]),
    _crear_item_cat("BEB-122", None, "Bebida Fanta Naranja 1.5L", "Fanta", 1, 1.5, "L", "LOTE", 6, 1150, 1890, True, (249, 115, 22), ["fanta", "naranja", "orange"]),
    _crear_item_cat("BEB-123", None, "Bebida Sprite Lima Limón 1.5L", "Sprite", 1, 1.5, "L", "LOTE", 6, 1150, 1890, True, (22, 163, 74), ["sprite", "lima", "limon"]),
    _crear_item_cat("BEB-103", None, "Bebida Kem Piña CCU 1.5L", "Kem", 1, 1.5, "L", "LOTE", 6, 1050, 1750, True, (250, 204, 21), ["kem", "pina", "xtreme", "ccu"]),
    _crear_item_cat("BEB-124", None, "Bebida Bilz CCU 1.5L", "Bilz", 1, 1.5, "L", "LOTE", 6, 1050, 1750, True, (220, 38, 38), ["bilz", "ccu", "fantasia"]),
    _crear_item_cat("BEB-125", None, "Bebida Pap Papaya CCU 1.5L", "Pap", 1, 1.5, "L", "LOTE", 6, 1050, 1750, True, (245, 158, 11), ["pap", "papaya", "ccu"]),
    _crear_item_cat("BEB-126", None, "Bebida Canada Dry Ginger Ale 1.5L", "Canada Dry", 1, 1.5, "L", "LOTE", 6, 1100, 1790, True, (21, 128, 61), ["canada", "dry", "ginger", "ale", "limon", "soda"]),
    _crear_item_cat("BEB-002", "BEB-002", "Agua Mineral Cachantún Sin Gas 1.5L", "Cachantún", 1, 1.5, "L", "LOTE", 6, 500, 950, True, (186, 230, 253), ["cachantun", "agua", "mineral", "natural", "gas"]),
    _crear_item_cat("BEB-127", None, "Agua Mineral Vital Sin Gas 1.5L", "Vital", 1, 1.5, "L", "LOTE", 6, 490, 950, True, (56, 189, 248), ["vital", "chanqueahue", "agua", "mineral"]),
    _crear_item_cat("BEB-128", None, "Agua Purificada Benedictino Sin Gas 1.5L", "Benedictino", 1, 1.5, "L", "LOTE", 6, 480, 900, True, (125, 211, 252), ["benedictino", "agua", "purificada"]),
    _crear_item_cat("BEB-129", None, "Agua Saborizada Cachantún Más Granada 1.5L", "Cachantún", 1, 1.5, "L", "LOTE", 6, 650, 1190, True, (244, 63, 94), ["cachantun", "mas", "granada", "saborizada"]),
    _crear_item_cat("BEB-003", "BEB-003", "Jugo Naranja Natural 1L (Watt's)", "Watt's", 1, 1.0, "L", "CAJA", 12, 1100, 1690, True, (249, 115, 22), ["watts", "watt", "nectar", "jugo", "naranja"]),
    _crear_item_cat("BEB-130", None, "Néctar Watt's Durazno 1L", "Watt's", 1, 1.0, "L", "CAJA", 12, 1100, 1690, True, (251, 146, 60), ["watts", "durazno", "nectar", "damasco"]),
    _crear_item_cat("BEB-131", None, "Jugo Andina del Valle Naranja 1.5L", "Andina del Valle", 1, 1.5, "L", "LOTE", 6, 1050, 1650, True, (249, 115, 22), ["andina", "valle", "nectar", "jugo"]),
    _crear_item_cat("BEB-132", None, "Jugo Individual Kapo Naranja / Frambuesa 200ml", "Kapo", 1, 200, "ml", "CAJA", 24, 220, 450, True, (249, 115, 22), ["kapo", "jugo", "200ml"]),
    _crear_item_cat("BEB-001", "BEB-001", "Leche Entera Soprole 1L", "Soprole", 1, 1.0, "L", "CAJA", 12, 850, 1250, True, (245, 248, 255), ["soprole", "leche", "entera", "natural", "1l"]),
    _crear_item_cat("BEB-133", None, "Leche Descremada Soprole 1L", "Soprole", 1, 1.0, "L", "CAJA", 12, 850, 1250, True, (186, 230, 253), ["soprole", "leche", "descremada", "semidescremada"]),
    _crear_item_cat("BEB-101", None, "Leche Entera Colun Del Sur 1L", "Colun", 1, 1.0, "L", "CAJA", 12, 860, 1290, True, (245, 250, 245), ["colun", "leche", "sur", "magia"]),
    _crear_item_cat("BEB-134", None, "Leche con Chocolate Colun / Soprole 200ml", "Colun", 1, 200, "ml", "CAJA", 24, 380, 690, True, (120, 53, 15), ["leche", "chocolate", "colun", "soprole", "200ml"]),
    _crear_item_cat("BEB-135", None, "Leche Entera Loncoleche / Surlat 1L", "Loncoleche", 1, 1.0, "L", "CAJA", 12, 840, 1250, True, (240, 249, 255), ["loncoleche", "surlat", "leche", "sin", "lactosa"]),
    _crear_item_cat("BEB-004", "BEB-004", "Yogurt Griego Natural Soprole / Danone 150g", "Soprole", 1, 150, "g", "LOTE", 6, 520, 890, True, (248, 250, 252), ["yogurt", "yoghurt", "griego", "natural", "danone"]),
    _crear_item_cat("BEB-136", None, "Yogurt Batido Soprole Frutilla / Vainilla 125g", "Soprole", 1, 125, "g", "LOTE", 12, 280, 520, True, (251, 113, 133), ["yogurt", "batido", "soprole", "colun", "125g"]),
    _crear_item_cat("BEB-137", None, "Yogurt con Cereal Gold / 1+1 Soprole 140g", "Soprole", 1, 140, "g", "LOTE", 12, 420, 750, True, (250, 204, 21), ["gold", "uno", "yogurt", "cereal", "yogu"]),
    _crear_item_cat("BEB-138", None, "Postre Chandelle Nestlé Chocolate / Manjar 130g", "Nestlé", 1, 130, "g", "LOTE", 12, 480, 850, True, (120, 53, 15), ["chandelle", "postre", "flan", "soprole", "manjar"]),
    _crear_item_cat("BEB-139", None, "Manjar Colun / Soprole Bolsa 400g", "Colun", 1, 400, "g", "CAJA", 12, 1250, 1990, True, (146, 64, 14), ["manjar", "colun", "soprole", "nestle"]),
    _crear_item_cat("BEB-140", None, "Mantequilla Colun / Soprole Pan 250g", "Colun", 1, 250, "g", "CAJA", 12, 1850, 2790, True, (254, 240, 138), ["mantequilla", "colun", "soprole", "margarina", "calo"]),
    _crear_item_cat("BEB-141", None, "Queso Gauda Laminado Colun / Quilque 250g", "Colun", 1, 250, "g", "CAJA", 12, 1950, 2990, True, (253, 224, 71), ["queso", "gauda", "ranco", "chanco", "colun", "quillayes"]),
    _crear_item_cat("BEB-142", None, "Crema de Leche Colun / Nestlé 200ml", "Colun", 1, 200, "ml", "CAJA", 24, 750, 1250, True, (248, 250, 252), ["crema", "leche", "batir", "nestle", "colun"]),
    _crear_item_cat("BEB-143", None, "Leche Condensada Nestlé Tarro 397g", "Nestlé", 1, 397, "g", "CAJA", 24, 1150, 1790, True, (241, 245, 249), ["condensada", "lechera", "ideal", "evaporada", "nestle"]),

    # 2. SNACKS, GALLETAS, CHOCOLATES Y CONFITERÍA CHILENA (Cat 3)
    _crear_item_cat("SNK-101", None, "Galletas McKay Kuky ChipChipers Blanco 120g", "McKay", 3, 120, "g", "CAJA", 12, 750, 1290, True, (225, 238, 250), ["kuky", "mckay", "chipchiper", "chipchipers", "cnipchipera", "blanco", "blana", "blancd"]),
    _crear_item_cat("SNK-102", None, "Galletas McKay Kuky Clásica Chips Chocolate 120g", "McKay", 3, 120, "g", "CAJA", 12, 750, 1290, True, (28, 75, 175), ["kuky", "mckay", "clasica", "chips", "chocolate"]),
    _crear_item_cat("SNK-103", None, "Galletas McKay Tritón Vainilla / Naranja 126g", "McKay", 3, 126, "g", "CAJA", 12, 720, 1250, True, (20, 45, 130), ["triton", "mckay", "vainilla", "sandwich"]),
    _crear_item_cat("SNK-110", None, "Galletas McKay Morocha Bañadas Chocolate 100g", "McKay", 3, 100, "g", "CAJA", 12, 750, 1290, True, (245, 158, 11), ["morocha", "mckay", "chocolate"]),
    _crear_item_cat("SNK-111", None, "Galletas McKay Criollitas / Vino / Grill 140g", "McKay", 3, 140, "g", "CAJA", 12, 650, 1150, True, (220, 38, 38), ["criollitas", "vino", "niza", "grill", "alteza", "mckay"]),
    _crear_item_cat("SNK-112", None, "Galletas de Soda / Agua McKay Clásica 180g", "McKay", 3, 180, "g", "CAJA", 12, 680, 1190, True, (239, 68, 68), ["soda", "agua", "mckay", "saladas", "club", "social"]),
    _crear_item_cat("SNK-113", None, "Oblea McKay Nik Vainilla / Frutilla 71g", "McKay", 3, 71, "g", "CAJA", 24, 380, 690, True, (220, 38, 38), ["nik", "oblea", "wafer", "mckay"]),
    _crear_item_cat("SNK-104", None, "Galletas Costa Tuareg Coco 120g", "Costa", 3, 120, "g", "CAJA", 12, 690, 1190, True, (245, 195, 25), ["tuareg", "costa", "coco"]),
    _crear_item_cat("SNK-105", None, "Galletas Costa Frac Chocolate / Vainilla 130g", "Costa", 3, 130, "g", "CAJA", 12, 690, 1190, True, (185, 28, 28), ["frac", "costa", "chocolate"]),
    _crear_item_cat("SNK-114", None, "Galletas Costa Gretel / Mantequilla / Limón 140g", "Costa", 3, 140, "g", "CAJA", 12, 680, 1190, True, (250, 204, 21), ["gretel", "dindon", "mantequilla", "limon", "costa"]),
    _crear_item_cat("SNK-115", None, "Bizcocho Costa Chocman / Mankeke 33g", "Costa", 3, 33, "g", "CAJA", 24, 260, 500, True, (146, 64, 14), ["chocman", "mankeke", "costa", "marinela", "pinguino", "gansito"]),
    _crear_item_cat("SNK-106", None, "Oblea Bañada Super 8 Nestlé 29g", "Nestlé", 3, 29, "g", "CAJA", 24, 250, 500, True, (25, 25, 30), ["super8", "super", "nestle", "oblea"]),
    _crear_item_cat("SNK-107", None, "Chocolate Trencito Nestlé Leche 150g", "Nestlé", 3, 150, "g", "CAJA", 12, 1450, 2390, True, (220, 38, 38), ["trencito", "nestle", "chocolate"]),
    _crear_item_cat("SNK-116", None, "Chocolate Sahne-Nuss Nestlé Almendras 250g", "Nestlé", 3, 250, "g", "CAJA", 10, 2450, 3890, True, (180, 83, 9), ["sahne", "nuss", "nestle", "almendras", "golden"]),
    _crear_item_cat("SNK-117", None, "Chocolate KitKat / Prestigio / Sublime Nestlé 41g", "Nestlé", 3, 41, "g", "CAJA", 24, 550, 990, True, (220, 38, 38), ["kitkat", "kit", "kat", "prestigio", "sublime"]),
    _crear_item_cat("SNK-118", None, "Chocolate Costa Rama / Vizzio / Mecano 115g", "Costa", 3, 115, "g", "CAJA", 12, 1350, 2190, True, (120, 53, 15), ["rama", "vizzio", "carezza", "mecano", "orly"]),
    _crear_item_cat("SNK-119", None, "Barra Golpe / Bon o Bon / Sapito Arcor 30g", "Ambrosoli / Arcor", 3, 30, "g", "CAJA", 24, 250, 500, True, (234, 88, 12), ["golpe", "bon", "bonobon", "sapito", "arcor", "ambrosoli"]),
    _crear_item_cat("SNK-120", None, "Gomitas Frugelé / Loop / Flipy Ambrosoli 100g", "Ambrosoli", 3, 100, "g", "CAJA", 12, 650, 1150, True, (34, 197, 94), ["frugele", "ambrosoli", "loop", "flipy", "gomitas", "masticables"]),
    _crear_item_cat("SNK-121", None, "Chicles / Mentas Bigtime / Grover / Menthoplus", "Arcor", 3, 18, "g", "CAJA", 20, 350, 690, True, (14, 165, 233), ["bigtime", "grover", "menthoplus", "alka", "halls", "trident", "orbit"]),
    _crear_item_cat("SNK-001", "SNK-001", "Galletas Artesanales Avena (Quaker / Vivo)", "Quaker / Artesanal", 3, 250, "g", "CAJA", 12, 900, 1500, True, (210, 180, 140), ["galletas", "artesanales", "avena", "quaker", "vivo"]),
    _crear_item_cat("SNK-122", None, "Barra de Cereal Cereal Bar Costa / Vivo 21g", "Costa / Vivo", 3, 21, "g", "CAJA", 20, 240, 490, True, (234, 179, 8), ["cereal", "bar", "barra", "quaker", "nature", "valley"]),
    _crear_item_cat("SNK-002", "SNK-002", "Papas Fritas Lay's Corte Americano 150g", "Lay's", 3, 150, "g", "CAJA", 18, 1200, 1990, True, (250, 204, 21), ["lays", "papas", "fritas", "corte", "americano", "evercrisp"]),
    _crear_item_cat("SNK-123", None, "Papas Fritas Kryzpo / Pringles Tarro 140g", "Kryzpo / Pringles", 3, 140, "g", "CAJA", 12, 1350, 2190, True, (220, 38, 38), ["kryzpo", "pringles", "papas", "tarro"]),
    _crear_item_cat("SNK-124", None, "Snack Doritos Queso Nacho Evercrisp 140g", "Doritos", 3, 140, "g", "CAJA", 14, 1150, 1890, True, (234, 88, 12), ["doritos", "nacho", "queso", "evercrisp"]),
    _crear_item_cat("SNK-125", None, "Snack Cheetos / Ramitas / Fritos Evercrisp 130g", "Evercrisp", 3, 130, "g", "CAJA", 14, 950, 1590, True, (249, 115, 22), ["cheetos", "ramitas", "fritos", "chispop", "gatolate", "twistos"]),
    _crear_item_cat("SNK-126", None, "Maní Salado / Japonés Marco Polo 120g", "Marco Polo", 3, 120, "g", "CAJA", 16, 750, 1290, True, (185, 28, 28), ["marco", "polo", "mani", "salado", "japones", "nueces", "almendras"]),

    # 3. ABARROTES, DESPENSA, CONSERVAS Y DESAYUNO CHILENO (Cat 2)
    _crear_item_cat("ABA-001", "ABA-001", "Arroz Grado 1 (1kg) (Tucapel / Miraflores)", "Tucapel", 2, 1.0, "kg", "LOTE", 10, 1050, 1590, True, (220, 38, 38), ["tucapel", "miraflores", "arroz", "grado", "banquete", "1kg"]),
    _crear_item_cat("ABA-002", "ABA-002", "Aceite Vegetal Maravilla 900ml (Chef / Belmont)", "Chef / Belmont", 2, 900, "ml", "CAJA", 12, 1650, 2390, True, (234, 179, 8), ["chef", "belmont", "natura", "aceite", "maravilla", "vegetal", "900ml"]),
    _crear_item_cat("ABA-120", None, "Aceite de Oliva Extra Virgen Chef / Traverso 500ml", "Chef / Traverso", 2, 500, "ml", "CAJA", 12, 3400, 5290, True, (21, 128, 61), ["oliva", "virgen", "traverso", "carbonell"]),
    _crear_item_cat("ABA-003", "ABA-003", "Fideos Spaghetti Nº5 400g (Carozzi / Lucchetti)", "Carozzi", 2, 400, "g", "CAJA", 20, 620, 990, True, (210, 30, 35), ["carozzi", "lucchetti", "talliani", "spaghetti", "fideos", "tallarines"]),
    _crear_item_cat("ABA-121", None, "Fideos Espirales / Corbatas Lucchetti / Carozzi 400g", "Lucchetti", 2, 400, "g", "CAJA", 20, 640, 1050, True, (29, 78, 216), ["espirales", "corbatas", "coditos", "cabello", "lucchetti", "carozzi"]),
    _crear_item_cat("ABA-102", None, "Salsa de Tomates Pomarola Carozzi / Malloa 200g", "Carozzi", 2, 200, "g", "CAJA", 24, 480, 850, True, (185, 28, 28), ["pomarola", "salsa", "tomates", "malloa", "italiana", "tuco"]),
    _crear_item_cat("ABA-103", None, "Azúcar Blanca Granulada Iansa 1kg", "Iansa", 2, 1.0, "kg", "LOTE", 10, 980, 1490, False, (250, 250, 252), ["iansa", "azucar", "granulada", "blanca"]),
    _crear_item_cat("ABA-122", None, "Endulzante Líquido Stevia / Sucralosa Iansa Cero K / Daily", "Iansa / Daily", 2, 180, "ml", "CAJA", 12, 1450, 2290, True, (34, 197, 94), ["endulzante", "stevia", "sucralosa", "daily", "cerok"]),
    _crear_item_cat("ABA-104", None, "Sal de Mesa Lobos 1kg", "Lobos", 2, 1.0, "kg", "LOTE", 10, 350, 690, False, (30, 58, 138), ["lobos", "sal", "yodada", "mar"]),
    _crear_item_cat("ABA-105", None, "Té Supremo / Club Ceylán Caja 20 Bolsitas", "Supremo / Club", 2, 40, "g", "CAJA", 12, 690, 1190, True, (185, 28, 28), ["supremo", "club", "lipton", "ceylan", "bolsitas"]),
    _crear_item_cat("ABA-123", None, "Yerba Mate Taragüi / CBSE / Supremo 500g", "Taragüi / Supremo", 2, 500, "g", "LOTE", 10, 1650, 2590, True, (220, 38, 38), ["yerba", "mate", "taragui", "cbse", "pipore"]),
    _crear_item_cat("ABA-106", None, "Café Instantáneo Nescafé Tradición Tarro 170g", "Nescafé", 2, 170, "g", "CAJA", 12, 3400, 5290, True, (75, 40, 25), ["nescafe", "tradicion", "cafe", "dolca", "gold", "cruzeiro"]),
    _crear_item_cat("ABA-124", None, "Alimento en Polvo Milo Nestlé 400g", "Nestlé", 2, 400, "g", "CAJA", 12, 2350, 3690, True, (22, 163, 74), ["milo", "nesquik", "cacao", "colacao"]),
    _crear_item_cat("ABA-125", None, "Cereal Desayuno Chocapic / Trix / Zucosos Nestlé 350g", "Nestlé", 2, 350, "g", "CAJA", 12, 1950, 3190, True, (146, 64, 14), ["chocapic", "trix", "zucosos", "estrellitas", "kelloggs", "zucaritas"]),
    _crear_item_cat("ABA-126", None, "Avena Instantánea Quaker / Carozzi 500g", "Quaker", 2, 500, "g", "CAJA", 12, 1150, 1790, True, (29, 78, 216), ["quaker", "avena", "instantanea", "tradicional"]),
    _crear_item_cat("ABA-107", None, "Harina de Trigo Selecta / Mont Blanc 1kg", "Selecta", 2, 1.0, "kg", "LOTE", 10, 890, 1390, True, (250, 245, 235), ["selecta", "harina", "trigo", "mont", "blanc", "polvos"]),
    _crear_item_cat("ABA-108", None, "Atún Lomitos Robinson Crusoe / San José 160g", "Robinson Crusoe", 2, 160, "g", "CAJA", 24, 1150, 1850, True, (15, 75, 165), ["robinson", "crusoe", "atun", "lomitos", "vancamps"]),
    _crear_item_cat("ABA-127", None, "Jurel Tipo Salmón San José / Único Tarro 425g", "San José", 2, 425, "g", "CAJA", 24, 1250, 1990, True, (220, 38, 38), ["jurel", "salmon", "sanjose", "unico", "colorado"]),
    _crear_item_cat("ABA-128", None, "Legumbres Lentejas / Porotos / Garbanzos Banquete 1kg", "Banquete / Iansa", 2, 1.0, "kg", "LOTE", 10, 1650, 2590, True, (180, 83, 9), ["lentejas", "porotos", "garbanzos", "arvejas", "wasil", "banquete"]),
    _crear_item_cat("ABA-129", None, "Conserva Duraznos en Mitades Wasil / Dos Caballos 590g", "Wasil", 2, 590, "g", "CAJA", 12, 1450, 2290, True, (245, 158, 11), ["duraznos", "mitades", "conserva", "wasil", "caballos", "pina"]),
    _crear_item_cat("ABA-130", None, "Mayonesa Hellmann's / Kraft / JB Doypack 400g", "Hellmann's / JB", 2, 400, "g", "CAJA", 12, 1550, 2490, True, (254, 249, 195), ["hellmanns", "mayonesa", "kraft", "alacena", "supreme"]),
    _crear_item_cat("ABA-131", None, "Ketchup / Mostaza JB / Hellmann's 380g", "JB / Heinz", 2, 380, "g", "CAJA", 12, 1150, 1850, True, (220, 38, 38), ["ketchup", "mostaza", "heinz", "jb", "malloa"]),
    _crear_item_cat("ABA-132", None, "Sopa / Crema / Caldo Maggi Sobre 68g", "Maggi", 2, 68, "g", "CAJA", 24, 480, 850, True, (250, 204, 21), ["maggi", "sopa", "caldo", "costilla", "gallina", "gourmet", "pure"]),
    _crear_item_cat("ABA-133", None, "Pan de Molde Blanco / Integral Ideal / Bimbo 550g", "Ideal / Bimbo", 2, 550, "g", "LOTE", 6, 1550, 2390, True, (245, 245, 250), ["ideal", "bimbo", "castano", "pan", "molde", "tortillas", "rapiditas"]),
    _crear_item_cat("ABA-134", None, "Mermelada Watt's Mora / Frutilla / Damasco 250g", "Watt's", 2, 250, "g", "CAJA", 12, 850, 1390, True, (190, 18, 60), ["mermelada", "watts", "mora", "frutilla", "damasco"]),

    # 4. LIMPIEZA DEL HOGAR Y PAPEL EN CHILE (Cat 4)
    _crear_item_cat("LIM-001", "LIM-001", "Detergente Líquido Ropa 3L (Omo / Ariel / Drive)", "Omo / Ariel", 4, 3.0, "L", "CAJA", 4, 4200, 6490, False, (29, 78, 216), ["omo", "ariel", "drive", "rinso", "ace", "fuzol", "detergente", "matic"]),
    _crear_item_cat("LIM-110", None, "Suavizante de Ropa Soft / Downy 1L", "Soft / Downy", 4, 1.0, "L", "CAJA", 12, 1650, 2590, False, (56, 189, 248), ["soft", "downy", "suavizante", "fuzol"]),
    _crear_item_cat("LIM-002", "LIM-002", "Cloro Gel Desinfectante 1L (Clorinda / Clorox)", "Clorinda / Clorox", 4, 1.0, "L", "CAJA", 12, 1150, 1850, False, (21, 128, 61), ["clorinda", "clorox", "cloro", "gel", "desinfectante"]),
    _crear_item_cat("LIM-101", None, "Lavaloza Concentrado Quix / Magistral 750ml", "Quix", 4, 750, "ml", "CAJA", 12, 1250, 1990, False, (22, 163, 74), ["quix", "magistral", "lavaloza", "loza", "sapolio"]),
    _crear_item_cat("LIM-111", None, "Limpiador de Pisos Poett / Fabuloso Lavanda 900ml", "Poett", 4, 900, "ml", "CAJA", 12, 1150, 1850, False, (147, 51, 234), ["poett", "fabuloso", "limpiador", "lavanda", "aromatizante", "glade"]),
    _crear_item_cat("LIM-112", None, "Desinfectante Aerosol Lysoform / Cif Crema 400ml", "Lysoform / Cif", 4, 400, "ml", "CAJA", 12, 1950, 3190, False, (2, 132, 199), ["lysoform", "cif", "musculo", "virutex", "raid", "tanax"]),
    _crear_item_cat("LIM-102", None, "Papel Higiénico Confort / Elite Doble Hoja (Pack 4)", "Confort / Elite", 4, 400, "g", "LOTE", 12, 1390, 2290, False, (240, 249, 255), ["confort", "elite", "noble", "favorita", "papel", "higienico"]),
    _crear_item_cat("LIM-113", None, "Toalla de Papel Absorbente Nova / Elite (Pack 2)", "Nova / Elite", 4, 300, "g", "LOTE", 12, 1250, 1990, False, (248, 250, 252), ["nova", "toalla", "absorbente", "servilletas", "abo"]),

    # 5. CUIDADO PERSONAL, HIGIENE Y PERFUMERÍA EN CHILE (Cat 5)
    _crear_item_cat("PER-001", "PER-001", "Shampoo Hidratante 400ml (Ballerina / Sedal / Pantene)", "Ballerina / Sedal", 5, 400, "ml", "CAJA", 12, 2100, 3490, True, (219, 39, 119), ["ballerina", "sedal", "pantene", "shoulders", "shampoo", "familand", "fructis", "elvive", "acondicionador"]),
    _crear_item_cat("PER-002", "PER-002", "Pasta Dental Triple Acción 120g (Pepsodent / Colgate)", "Pepsodent / Colgate", 5, 120, "g", "LOTE", 12, 980, 1650, True, (220, 38, 38), ["pepsodent", "colgate", "sensodyne", "oralb", "pasta", "dental"]),
    _crear_item_cat("PER-110", None, "Desodorante Aerosol / Roll-On Rexona / Dove / Axe 150ml", "Rexona / Dove", 5, 150, "ml", "CAJA", 12, 1850, 2990, True, (30, 58, 138), ["rexona", "dove", "nivea", "axe", "old", "spice", "speed", "stick", "desodorante"]),
    _crear_item_cat("PER-111", None, "Jabón en Barra / Líquido Dove / Le Sancy / Lux 90g", "Dove / Le Sancy", 5, 90, "g", "CAJA", 24, 650, 1150, True, (241, 245, 249), ["dove", "sancy", "lux", "protex", "jabon", "simonds", "glicerina"]),
    _crear_item_cat("PER-112", None, "Toallas Higiénicas Ladysoft / Kotex / Always (Pack 8)", "Ladysoft / Kotex", 5, 120, "g", "CAJA", 18, 950, 1590, False, (236, 72, 153), ["ladysoft", "kotex", "always", "nosotras", "panales", "pampers", "huggies", "emubaby"]),
]


def obtener_catalogo_chileno_referencia() -> list[dict[str, Any]]:
    """Retorna la base masiva precargada de 106 productos comunes del mercado chileno."""
    return CATALOGO_CHILENO_PRECARGADO


# ============================================================================
# AISLAMIENTO DEL EMPAQUE (SIN FONDO OSCURO) Y EXTRACCIÓN DE HUELLA + OCR
# ============================================================================


def _recortar_objeto_activo(img: Image.Image) -> Image.Image:
    """Aísla la caja delimitadora 2D del producto iluminado descartando el fondo oscuro."""
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, w, _ = arr.shape
    if h < 32 or w < 32:
        return img

    max_rgb = arr.max(axis=2)
    sat = (max_rgb - arr.min(axis=2)) / np.maximum(max_rgb, 1.0)
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
         los píxeles activos del producto (ignorando píxeles negros del fondo).
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

    mask_fg = max_c >= 42.0
    if int(mask_fg.sum()) < 64:
        mask_fg = np.ones_like(max_c, dtype=bool)

    fg_r = r_ch[mask_fg]
    fg_g = g_ch[mask_fg]
    fg_b = b_ch[mask_fg]
    fg_max = max_c[mask_fg]
    fg_diff = diff_c[mask_fg]
    n_fg = float(len(fg_r))

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

    p5 = float(np.percentile(peq[mask_fg], 5))
    p95 = float(np.percentile(peq[mask_fg], 95))
    rango = max(25.0, p95 - p5)
    norm_img = np.clip((peq - p5) / rango, 0.0, 1.0)

    bins = np.linspace(0.0, 1.0001, 17)
    h_r, _ = np.histogram(norm_img[:, :, 0][mask_fg], bins=bins)
    h_g, _ = np.histogram(norm_img[:, :, 1][mask_fg], bins=bins)
    h_b, _ = np.histogram(norm_img[:, :, 2][mask_fg], bins=bins)
    hist = np.concatenate([h_r, h_g, h_b]).astype(np.float32)
    norma_h = float(np.linalg.norm(hist))
    hist_list = (
        [round(float(x / norma_h), 4) for x in hist] if norma_h > 1e-6 else [0.0] * 48
    )

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
    """Ejecuta RapidOCR en doble pasada con realce de contraste."""
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
    o Wikimedia Commons (`data/catalogo_chileno_real.json`).
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
    """Construye la base masiva de 106 referencias del mercado chileno con sus fotos reales."""
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
# RELACIÓN CRUZADA IMAGEN + TEXTO CON RECONSTRUCCIÓN DE PALABRAS PARTIDAS
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


def _tokenizar_ocr(textos: list[str], reconstruir_pares: bool = False) -> list[str]:
    """
    Convierte textos leídos por OCR en tokens limpios.
    Si `reconstruir_pares=True` (para lecturas de cámara en botellas o envases curvos),
    une además fragmentos adyacentes y elimina letras duplicadas por distorsión óptica
    (ej. ['POWER', 'YYADE'] -> genera también 'poweryyade' y 'poweryade' -> coincide con 'powerade').
    """
    stopwords = {"clear", "photo", "take", "con", "por", "para", "del", "las", "los"}
    tokens_base: list[str] = []
    for frase in textos:
        for t in re.split(r"[\s\-\.,/]+", frase.lower()):
            limpio = re.sub(r"[^a-záéíóúüñ0-9]+", "", t)
            if len(limpio) >= 3 and limpio not in stopwords and limpio not in tokens_base:
                tokens_base.append(limpio)

    if not reconstruir_pares or len(tokens_base) < 2:
        return tokens_base

    tokens_expandidos = list(tokens_base)
    for i in range(len(tokens_base) - 1):
        unido = tokens_base[i] + tokens_base[i + 1]
        if 5 <= len(unido) <= 18 and unido not in tokens_expandidos:
            tokens_expandidos.append(unido)
        # Versión sin letras duplicadas consecutivas (ej. "poweryyade" -> "poweryade")
        colapsado = re.sub(r"(.)\1+", r"\1", unido)
        if 5 <= len(colapsado) <= 18 and colapsado not in tokens_expandidos:
            tokens_expandidos.append(colapsado)

    return tokens_expandidos


def calcular_similitud_solo_imagen(
    huella_nueva: dict[str, Any], huella_ref: dict[str, Any]
) -> float:
    """Calcula la similitud visual (0 a 100%) sobre los píxeles del objeto sin fondo."""
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
    Evalúa cuánto coincide el texto OCR leído en la cámara (incluyendo palabras
    reconstruidas de fragmentos curvos) con las palabras clave del producto candidato.
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
            if len(tk_ref) >= 5 and len(tk_cap) >= 4 and (tk_ref in tk_cap or tk_cap in tk_ref):
                mejor_ratio = max(mejor_ratio, 0.90)
            else:
                r = SequenceMatcher(None, tk_cap, tk_ref).ratio()
                if r > mejor_ratio:
                    mejor_ratio = r

        if mejor_ratio >= 0.75:
            puntaje_acum += mejor_ratio
            coincidentes.append(tk_cap)

    if not coincidentes:
        return 0.0, []

    base = 68.0 + min(31.0, (puntaje_acum - 0.75) * 22.0 + (len(coincidentes) - 1) * 9.0)
    return round(min(99.0, max(0.0, base)), 1), coincidentes


def calcular_relacion_cruzada_imagen_texto(
    huella_captura: dict[str, Any],
    ref_candidato: dict[str, Any],
    hay_texto_en_captura: bool,
) -> dict[str, Any]:
    """
    Cruza la similitud de la Imagen (color/estructura sin fondo) con el Texto OCR leído:
      - Si el texto leído en cámara (o su reconstrucción de fragmentos curvos, ej.
        'POWER' + 'YYADE' -> 'POWERADE') coincide con el candidato, suma la similitud
        visual del envase (ej. diferenciando Powerade Azul vs Powerade Rojo vs Naranja).
      - Si el candidato contradice el texto leído en cámara, queda vetado.
    """
    huella_ref = ref_candidato.get("huella", {})
    sim_img = calcular_similitud_solo_imagen(huella_captura, huella_ref)

    tokens_cap = _tokenizar_ocr(huella_captura.get("textos_ocr", []), reconstruir_pares=True)
    textos_ref = list(huella_ref.get("textos_ocr", [])) + [
        str(ref_candidato.get("nombre_producto", "")),
        str(ref_candidato.get("marca", "")),
    ]
    tokens_ref = _tokenizar_ocr(textos_ref, reconstruir_pares=False)

    sim_txt, palabras_match = calcular_similitud_solo_texto(tokens_cap, tokens_ref)

    if hay_texto_en_captura:
        if sim_txt >= 55.0:
            bono_coherencia = 10.0 if sim_img >= 45.0 else 0.0
            score_cruzado = min(
                99.0, 0.58 * sim_txt + 0.42 * sim_img + bono_coherencia
            )
            modo_cruce = "IMAGEN_Y_TEXTO_COINCIDENTES"
        else:
            score_cruzado = sim_img * 0.20
            modo_cruce = "VETADO_POR_TEXTO_DISTINTO"
    else:
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
    tokens_cap = _tokenizar_ocr(huella_nueva.get("textos_ocr", []), reconstruir_pares=True)
    res = calcular_relacion_cruzada_imagen_texto(
        huella_nueva,
        {"huella": huella_ref},
        hay_texto_en_captura=(len(tokens_cap) > 0),
    )
    return res["score_cruzado"]


# ============================================================================
# PERSISTENCIA DE MEMORIA VISUAL Y BÚSQUEDA VERIFICADA EN OPEN FOOD FACTS
# ============================================================================


def cargar_memoria_visual() -> list[dict[str, Any]]:
    """
    Carga la Memoria Visual garantizando que las 106 referencias del mercado chileno
    con sus fotografías reales estén siempre activas.
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
    tiene_base_106 = (
        len(refs_chilenas) >= 100
        and all("perfil_color" in r.get("huella", {}) for r in refs_chilenas[:5])
    )

    if not tiene_base_106:
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
    """Guarda inmediatamente en la Memoria Visual la imagen y el producto confirmado por el operario."""
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
        referencias = referencias[:150]

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
    Si el texto OCR leído corresponde a un producto que no está entre las 106
    referencias locales, consulta Open Food Facts en vivo PERO exige validación
    estricta: el nombre o marca devuelto por la API DEBE coincidir textualmente
    (>= 75%) con las palabras leídas por el OCR, impidiendo recomendaciones incoherentes.
    """
    tokens_expandidos = _tokenizar_ocr(textos_ocr, reconstruir_pares=True)
    if not tokens_expandidos:
        return None

    # Probar con los tokens más largos/representativos (incluyendo palabras reconstruidas)
    candidatos_query = sorted(tokens_expandidos, key=len, reverse=True)[:3]
    try:
        for q in candidatos_query:
            r = requests.get(
                "https://search.openfoodfacts.org/search",
                params={"q": q, "page_size": 5},
                headers={"User-Agent": "GestorPyMEPro/2.0"},
                timeout=4,
            )
            if r.status_code != 200:
                continue
            for hit in r.json().get("hits", []):
                nom_hit = (
                    hit.get("product_name_es")
                    or hit.get("product_name")
                    or ""
                ).strip()
                marcas_hit = hit.get("brands") or []
                marca_str = (
                    marcas_hit[0]
                    if isinstance(marcas_hit, list) and marcas_hit
                    else str(marcas_hit or "")
                ).strip()
                if not nom_hit and not marca_str:
                    continue

                tokens_hit = _tokenizar_ocr([nom_hit, marca_str], reconstruir_pares=False)
                sim_t, _ = calcular_similitud_solo_texto(tokens_expandidos, tokens_hit)
                # Exigir que el nombre o la marca del resultado coincida de verdad con el OCR
                if sim_t < 72.0:
                    continue

                if marca_str and marca_str.lower() not in nom_hit.lower():
                    nombre_completo = f"{nom_hit} ({marca_str})".strip()
                else:
                    nombre_completo = nom_hit or marca_str

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
                    "confianza_pct": int(round(sim_t)),
                    "descripcion_visual": (
                        f"Verificado en Open Food Facts: Texto leído «{' · '.join(textos_ocr[:4])}» "
                        f"coincide con «{nombre_completo}»"
                    ),
                    "motor_vision": "🌐 Base Pública Open Food Facts + OCR",
                    "recordado_de_memoria": False,
                    "es_incoherente": False,
                }
    except Exception:
        pass
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
            else "🇨🇱 Base Pública Mercado Chileno (Imagen + OCR)"
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
            f"Coincidencia visual con fotografía real de base pública chilena "
            f"({sim_img:.1f}% similitud de empaque)"
        )
        motor_lbl = "🇨🇱 Base Pública Mercado Chileno"

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
    Detecta el producto en la imagen capturada por cámara cruzando Imagen + Texto OCR:
      1. Extrae la huella visual sin fondo y reconstruye palabras partidas por envases curvos
         (ej. 'POWER' + 'YYADE' -> 'POWERADE').
      2. Cruza `sim_imagen` y `sim_texto` contra la Memoria del Operario y la Base Masiva
         de 106 Productos del Mercado Chileno (con fotografías reales de Open Food Facts
         y Wikimedia Commons).
      3. Si el texto leído corresponde a un producto externo, valida estrictamente contra
         Open Food Facts o usa directamente el texto leído del envase (sin inventar
         productos no relacionados).
    """
    inventario = obtener_inventario_consolidado()
    catalogos = obtener_catalogos()
    categorias = catalogos["categorias"]

    img_pil = Image.open(io.BytesIO(imagen_bytes)).convert("RGB")
    calidad_ok, motivo_calidad = _evaluar_calidad_imagen(img_pil)

    huella_captura = extraer_huella_visual(imagen_bytes, incluir_ocr=calidad_ok)
    textos_ocr = huella_captura.get("textos_ocr", [])
    tokens_ocr = _tokenizar_ocr(textos_ocr, reconstruir_pares=True)
    hay_texto = len(tokens_ocr) > 0

    referencias_memoria = cargar_memoria_visual()

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
        score_comp = ev["score_cruzado"]
        if (
            ref.get("origen") != "BASE_CHILENA_PRECARGADA"
            and ev["modo_cruce"] != "VETADO_POR_TEXTO_DISTINTO"
        ):
            score_comp += 1.5

        if score_comp > mejor_eval["score_cruzado"]:
            mejor_eval = {**ev, "score_cruzado": min(99.5, round(score_comp, 1))}
            mejor_ref = ref

    if hay_texto and mejor_eval["sim_texto"] < 55.0:
        det_off_vivo = _consultar_openfoodfacts_en_vivo(
            textos_ocr, huella_captura, inventario, categorias
        )
        if det_off_vivo is not None:
            return det_off_vivo

        # Construir propuesta directamente con las palabras reales leídas en el envase
        nombre_leido = " ".join(textos_ocr[:3]).title()
        cat_def = categorias[0] if categorias else {"id_categoria": 1, "nombre_categoria": "General"}
        pref = cat_def["nombre_categoria"][:3].upper()
        return {
            "es_existente": False,
            "id_producto": None,
            "codigo_sku": f"{pref}-{len(inventario) + 14:03d}",
            "nombre_categoria": cat_def["nombre_categoria"],
            "id_categoria": cat_def["id_categoria"],
            "nombre_detectado": nombre_leido,
            "stock_actual": 0,
            "formato_sugerido": "CAJA",
            "unidades_por_formato_sugeridas": 12,
            "peso_sugerido": 1.0,
            "unidad_peso_sugerida": "kg",
            "precio_compra_sugerido": 950.0,
            "precio_venta_sugerido": 1490.0,
            "perecible_sugerido": True,
            "confianza_pct": 82,
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
