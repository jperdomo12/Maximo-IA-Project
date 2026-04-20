import requests
import urllib3
from datetime import datetime
from mcp.server.fastmcp import FastMCP

# ============================================================
#  CONFIGURACIÓN
# ============================================================
MODO_SIMULACION = True
MAXIMO_URL      = "https://TU_SERVIDOR/maximo/oslc"   # Sin barra final
API_KEY         = "TU_API_KEY_AQUÍ"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
mcp = FastMCP("Maximo Enterprise")


# ============================================================
#  DATOS MOCK — Fase 1 + Fase 2A
# ============================================================
OT_MOCK = {
    "OT-1001": {"wonum": "OT-1001", "description": "Mantenimiento bomba centrífuga B-201", "status": "APPR",  "assetnum": "BOMBA-B201"},
    "OT-1002": {"wonum": "OT-1002", "description": "Revisión compresor C-305",             "status": "INPRG", "assetnum": "COMP-C305"},
    "OT-1003": {"wonum": "OT-1003", "description": "Cambio filtros HVAC zona norte",       "status": "WAPPR", "assetnum": "HVAC-ZN01"},
    "OT-1004": {"wonum": "OT-1004", "description": "Reparación válvula V-102",             "status": "WMATL", "assetnum": "VALV-V102"},
    "OT-1005": {"wonum": "OT-1005", "description": "Lubricación rodamientos motor M-07",   "status": "COMP",  "assetnum": "MOTOR-M07"},
}

INVENTARIO_MOCK = {
    ("FILTRO-001", "CENTRAL"): {"itemnum": "FILTRO-001", "location": "CENTRAL", "curbal": 15, "binnum": "PASILLO-B2-ESTANTE4"},
    ("RODAMIENTO-SKF", "CENTRAL"): {"itemnum": "RODAMIENTO-SKF", "location": "CENTRAL", "curbal": 8,  "binnum": "PASILLO-A1-ESTANTE2"},
    ("VALVULA-2P", "NORTE"): {"itemnum": "VALVULA-2P", "location": "NORTE", "curbal": 3, "binnum": "RACK-C3"},
}


# ============================================================
#  LÓGICA DE NEGOCIO — Transiciones de estado
# ============================================================
TRANSICIONES_VALIDAS = {
    "WAPPR": ["APPR", "CAN"],
    "APPR":  ["WMATL", "INPRG", "CAN"],
    "INPRG": ["COMP", "WMATL"],
    "COMP":  ["CLOSE"],
    "WMATL": ["INPRG", "CAN"],
    "CLOSE": [],
    "CAN":   [],
}

DESCRIPCION_ESTADOS = {
    "WAPPR": "Esperando Aprobación",
    "APPR":  "Aprobada",
    "INPRG": "En Progreso",
    "COMP":  "Completada",
    "WMATL": "Esperando Material",
    "CLOSE": "Cerrada",
    "CAN":   "Cancelada",
}

def _headers():
    return {"apikey": API_KEY, "Accept": "application/json", "Content-Type": "application/json"}


# ============================================================
#  TOOL 1 — consultar_ot
# ============================================================
@mcp.tool()
def consultar_ot(num_ot: str) -> str:
    """Consulta los detalles de una Orden de Trabajo (OT) en Maximo."""
    num_ot = num_ot.strip().upper()
    if MODO_SIMULACION:
        ot = OT_MOCK.get(num_ot)
        if not ot:
            return f"⚠️ [SIMULACIÓN] OT '{num_ot}' no encontrada.\nOTs disponibles: {', '.join(OT_MOCK.keys())}"
        estado = ot['status']
        destinos = TRANSICIONES_VALIDAS.get(estado, [])
        transiciones = ", ".join(destinos) if destinos else "ninguna (estado terminal)"
        return (f"🧪 [SIMULACIÓN] OT: {ot['wonum']}\n"
                f"📝 Descripción: {ot['description']}\n"
                f"📊 Estado: {estado} — {DESCRIPCION_ESTADOS.get(estado, '')}\n"
                f"🔧 Activo: {ot['assetnum']}\n"
                f"➡️  Puede pasar a: {transiciones}")
    endpoint = f"{MAXIMO_URL}/os/mxwodetail"
    params = {"oslc.where": f'wonum="{num_ot}"', "oslc.select": "wonum,description,status,assetnum"}
    try:
        r = requests.get(endpoint, params=params, headers=_headers(), verify=False, timeout=10)
        r.raise_for_status()
        data = r.json().get("member", [])
        if not data:
            return f"No se encontró la OT {num_ot}."
        ot = data[0]
        estado = ot.get("status", "").upper()
        destinos = TRANSICIONES_VALIDAS.get(estado, [])
        transiciones = ", ".join(destinos) if destinos else "ninguna (estado terminal)"
        return (f"✅ [REAL] OT: {ot.get('wonum')} | Desc: {ot.get('description')}\n"
                f"📊 Estado: {estado} — {DESCRIPCION_ESTADOS.get(estado, '')}\n"
                f"🔧 Activo: {ot.get('assetnum')}\n"
                f"➡️  Puede pasar a: {transiciones}")
    except Exception as e:
        return f"❌ Error OT: {str(e)}"


# ============================================================
#  TOOL 2 — consultar_inventario
# ============================================================
@mcp.tool()
def consultar_inventario(item_num: str, almacen: str = "CENTRAL") -> str:
    """Consulta la disponibilidad de un repuesto o artículo en un almacén específico."""
    item_num = item_num.strip().upper()
    almacen  = almacen.strip().upper()
    if MODO_SIMULACION:
        inv = INVENTARIO_MOCK.get((item_num, almacen))
        if not inv:
            return (f"⚠️ [SIMULACIÓN] Artículo '{item_num}' en almacén '{almacen}' no encontrado.\n"
                    f"Combinaciones disponibles: {', '.join(str(k) for k in INVENTARIO_MOCK.keys())}")
        return (f"🧪 [SIMULACIÓN INVENTARIO]\n"
                f"Artículo: {inv['itemnum']}\n"
                f"Almacén: {inv['location']}\n"
                f"Cantidad Disponible: {inv['curbal']} unidades\n"
                f"Ubicación: {inv['binnum']}")
    endpoint = f"{MAXIMO_URL}/os/mxinventory"
    params = {"oslc.where": f'itemnum="{item_num}" and location="{almacen}"', "oslc.select": "itemnum,location,curbal,binnum"}
    try:
        r = requests.get(endpoint, params=params, headers=_headers(), verify=False, timeout=10)
        r.raise_for_status()
        data = r.json().get("member", [])
        if not data:
            return f"No hay existencias del artículo {item_num} en {almacen}."
        inv = data[0]
        return (f"✅ [REAL] Artículo: {inv.get('itemnum')} | Almacén: {inv.get('location')} | "
                f"Stock: {inv.get('curbal')} | Ubicación: {inv.get('binnum')}")
    except Exception as e:
        return f"❌ Error Inventario: {str(e)}"


# ============================================================
#  TOOL 3 — cambiar_estado_ot
# ============================================================
@mcp.tool()
def cambiar_estado_ot(num_ot: str, nuevo_estado: str, memo: str = "") -> str:
    """
    Cambia el estado de una Orden de Trabajo en IBM Maximo (MAS 8.x/9.x).

    Args:
        num_ot:        Número de la OT  (ej: "OT-1001")
        nuevo_estado:  Código de estado destino (APPR, INPRG, COMP, CLOSE, CAN, WMATL)
        memo:          Nota opcional que queda en el historial de la OT
    """
    num_ot       = num_ot.strip().upper()
    nuevo_estado = nuevo_estado.strip().upper()
    timestamp    = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    memo_final   = memo.strip() or "(sin nota)"

    if nuevo_estado not in TRANSICIONES_VALIDAS:
        return f"❌ Estado '{nuevo_estado}' no reconocido.\nEstados válidos: {', '.join(TRANSICIONES_VALIDAS.keys())}"

    if MODO_SIMULACION:
        ot = OT_MOCK.get(num_ot)
        if not ot:
            return f"⚠️ [SIMULACIÓN] OT '{num_ot}' no encontrada.\nOTs disponibles: {', '.join(OT_MOCK.keys())}"
        estado_actual = ot["status"]
        if nuevo_estado not in TRANSICIONES_VALIDAS.get(estado_actual, []):
            destinos = TRANSICIONES_VALIDAS.get(estado_actual, [])
            opciones = "\n".join(f"   → {e}  ({DESCRIPCION_ESTADOS.get(e,'')})" for e in destinos) if destinos else "   (estado terminal)"
            return (f"❌ [SIMULACIÓN] Transición no permitida.\n\n"
                    f"📋 OT: {num_ot}\n📊 Estado actual: {estado_actual}\n🚫 Solicitado: {nuevo_estado}\n\n"
                    f"✅ Transiciones válidas:\n{opciones}")
        estado_anterior = estado_actual
        OT_MOCK[num_ot]["status"] = nuevo_estado
        return (f"✅ [SIMULACIÓN] Estado cambiado exitosamente.\n\n"
                f"📋 OT:              {num_ot}\n"
                f"🔧 Activo:          {ot['assetnum']}\n"
                f"📝 Descripción:     {ot['description']}\n"
                f"📊 Estado anterior: {estado_anterior} — {DESCRIPCION_ESTADOS.get(estado_anterior,'')}\n"
                f"🎯 Estado nuevo:    {nuevo_estado} — {DESCRIPCION_ESTADOS.get(nuevo_estado,'')}\n"
                f"📎 Memo:            {memo_final}\n"
                f"🕐 Timestamp:       {timestamp}\n\n"
                f"⚠️  Esto es simulación. Cambia MODO_SIMULACION = False para afectar Maximo real.")

    try:
        endpoint = f"{MAXIMO_URL}/os/mxwodetail"
        params = {"oslc.where": f'wonum="{num_ot}"', "oslc.select": "wonum,status,description,assetnum"}
        r = requests.get(endpoint, params=params, headers=_headers(), verify=False, timeout=10)
        r.raise_for_status()
        data = r.json().get("member", [])
        if not data:
            return f"❌ OT '{num_ot}' no encontrada en Maximo."
        recurso = data[0]
        estado_actual = recurso.get("status", "").upper()
        href = recurso.get("href") or recurso.get("rdf:about", "")
        if nuevo_estado not in TRANSICIONES_VALIDAS.get(estado_actual, []):
            destinos = TRANSICIONES_VALIDAS.get(estado_actual, [])
            opciones = "\n".join(f"   → {e}  ({DESCRIPCION_ESTADOS.get(e,'')})" for e in destinos) if destinos else "   (terminal)"
            return f"❌ Transición no permitida.\nEstado actual: {estado_actual}\nVálidas:\n{opciones}"
        if not href:
            return "❌ No se pudo obtener el href del recurso."
        patch_headers = {**_headers(), "x-method-override": "PATCH", "patchtype": "MERGE"}
        r2 = requests.post(href, json={"status": nuevo_estado, "memo": memo_final}, headers=patch_headers, verify=False, timeout=15)
        r2.raise_for_status()
        return (f"✅ [REAL] Estado cambiado en Maximo MAS.\n"
                f"OT: {num_ot} | {estado_actual} → {nuevo_estado}\nMemo: {memo_final}\nHTTP: {r2.status_code}")
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================
#  TOOL 4 — listar_transiciones_ot
# ============================================================
@mcp.tool()
def listar_transiciones_ot(num_ot: str) -> str:
    """
    Muestra el estado actual de una OT y los cambios de estado permitidos.
    Úsala antes de cambiar_estado_ot para saber qué opciones hay disponibles.
    """
    num_ot = num_ot.strip().upper()
    if MODO_SIMULACION:
        ot = OT_MOCK.get(num_ot)
        if not ot:
            return f"⚠️ [SIMULACIÓN] OT '{num_ot}' no encontrada.\nDisponibles: {', '.join(OT_MOCK.keys())}"
        estado = ot["status"]
        destinos = TRANSICIONES_VALIDAS.get(estado, [])
        lineas = [
            f"📋 OT: {num_ot}  |  Activo: {ot['assetnum']}",
            f"📊 Estado actual: {estado} — {DESCRIPCION_ESTADOS.get(estado,'')}",
            "",
            "✅ Cambios permitidos:" if destinos else "🔒 Estado terminal. Sin transiciones posibles.",
        ]
        for e in destinos:
            lineas.append(f"   → {e:<8}  {DESCRIPCION_ESTADOS.get(e,'')}")
        if destinos:
            lineas.append("")
            lineas.append(f'💡 Usa: cambiar_estado_ot("{num_ot}", "{destinos[0]}", "tu nota")')
        return "\n".join(lineas)
    try:
        endpoint = f"{MAXIMO_URL}/os/mxwodetail"
        params = {"oslc.where": f'wonum="{num_ot}"', "oslc.select": "wonum,status,assetnum"}
        r = requests.get(endpoint, params=params, headers=_headers(), verify=False, timeout=10)
        r.raise_for_status()
        data = r.json().get("member", [])
        if not data:
            return f"❌ OT '{num_ot}' no encontrada en Maximo."
        ot = data[0]
        estado = ot.get("status", "").upper()
        destinos = TRANSICIONES_VALIDAS.get(estado, [])
        lineas = [
            f"📋 OT: {num_ot}  |  Activo: {ot.get('assetnum','N/D')}",
            f"📊 Estado actual: {estado} — {DESCRIPCION_ESTADOS.get(estado,'')}",
            "",
            "✅ Cambios permitidos:" if destinos else "🔒 Estado terminal.",
        ]
        for e in destinos:
            lineas.append(f"   → {e:<8}  {DESCRIPCION_ESTADOS.get(e,'')}")
        return "\n".join(lineas)
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================
if __name__ == "__main__":
    mcp.run()
