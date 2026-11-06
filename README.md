# 🏪 GestorPyME Pro — MVP de Gestión de Ventas, Inventario y Caducidad

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/deploy?repository=medc2303/gestorpyme-pro&branch=main&mainModule=app.py)

Prototipo funcional desarrollado en **Streamlit + HTML/CSS** para Taller de Emprendimiento, diseñado para facilitar a pequeñas y medianas empresas (almacenes, minimarkets y comercios) el control de sus ventas, inventario en unidades, fechas de vencimiento y decisiones comerciales.

> **100% Libre de SQL y Portátil en la Nube:** Toda la persistencia funciona de forma automática en JSON (`data/tienda_inventario.json`), listo para desplegarse directamente en **Streamlit Community Cloud** sin instalar motores de bases de datos externos.

---

## 🌐 Despliegue Web Gratuito (Sin Pendrive ni Instalar Nada)

1. Abre **[share.streamlit.io](https://share.streamlit.io)** e inicia sesión con tu cuenta de GitHub (`medc2303`).
2. Haz clic en **Create app** (o haz clic directo en el botón **"Open in Streamlit"** de arriba).
3. Selecciona:
   - **Repository:** `medc2303/gestorpyme-pro`
   - **Branch:** `main`
   - **Main file path:** `app.py`
4. Presiona **Deploy!** — en ~1 minuto tendrás tu enlace web público (por ejemplo `https://gestorpyme-pro.streamlit.app`) accesible desde cualquier computador, tablet o celular.

---

## 💻 Ejecución Local (Opcional)

### Opción A: Doble clic (Windows)
Haz doble clic sobre el archivo **`iniciar.bat`**.

### Opción B: Desde terminal
```powershell
pip install -r requirements.txt
streamlit run app.py
```

---

## 🔑 Credenciales de Prueba (Incluye botones de acceso rápido en 1 clic)

| Rol | Usuario | Contraseña | Acceso |
| :--- | :--- | :--- | :--- |
| **Dueño / Administrador** | `admin` | `admin123` | Panel Principal, Caja, Inventario, Ingreso Caja/Lote, Analítica y Asesor IA |
| **Cajero / Empleado** | `empleado` | `caja123` | Módulo operativo de Punto de Venta (Caja) y sus últimas ventas |

---

## ✨ Funcionalidades Principales del MVP

1. **Panel Principal Ejecutivo con Alertas de Caducidad:**
   - Visualiza en una sola vista ingresos acumulados, utilidad neta estimada, ticket promedio, evolución temporal de ventas (gráfico vectorial SVG), productos estrella y **lo próximo a vencer / vencido**, permitiendo aplicar descuentos promocionales en 1 clic.
2. **Ingreso por Caja, Lote o Unidad con Conversión Automática:**
   - Al registrar o abastecer productos puedes elegir **Caja**, **Lote** o **Unidad**, indicando cuántas unidades trae cada formato. El sistema convierte automáticamente todo el ingreso a **unidades individuales** en el Chequeo de Inventario y calcula el costo unitario real.
3. **Registro de Peso y Control FEFO de Caducidad:**
   - Registra el peso/contenido neto por unidad (`g`, `kg`, `ml`, `L`), calcula el peso total almacenado en bodega y descuenta en Caja primero los lotes que vencen antes (**FEFO**), bloqueando la venta accidental de lotes vencidos.
4. **Asesor Comercial con IA Gratuita:**
   - Chatbot integrado que analiza en vivo ventas, márgenes, rotación de 30 días y caducidades para sugerir futuras compras, ofertas anti-merma y combos promocionales.
