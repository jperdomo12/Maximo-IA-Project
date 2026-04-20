import requests
import urllib3
import json
from datetime import datetime
from typing import Optional
from mcp.server.fastmcp import FastMCP

# ============================================================
#  CONFIGURACIÓN
# ============================================================
MODO_SIMULACION = True
MAXIMO_URL      = "https://TU_SERVIDOR/maximo"   # Sin barra final
API_KEY         = "TU_API_KEY_AQUÍ"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
mcp = FastMCP("Maximo Enterprise")


# ============================================================
#  DATOS MOCK — Simulación completa
# ============================================================
OT_MOCK = {
    "OT-1001": {"wonum": "OT-1001", "description": "Mantenimiento bomba centrífuga B-201", "status": "APPR",  "assetnum": "BOMBA-B201", "siteid": "PLANTA1", "worktype": "PM", "wopriority": 2},
    "OT-1002": {"wonum": "OT-1002", "description": "Revisión compresor C-305",             "status": "INPRG", "assetnum": "COMP-C305",  "siteid": "PLANTA1", "worktype": "CM", "wopriority": 1},
    "OT-1003": {"wonum": "OT-1003", "description": "Cambio filtros HVAC zona norte",       "status": "WAPPR", "assetnum": "HVAC-ZN01",  "siteid": "PLANTA2", "worktype": "PM", "wopriority": 3},
    "OT-1004": {"wonum": "OT-1004", "description": "Reparación válvula V-102",             "status": "WMATL", "assetnum": "VALV-V102",  "siteid": "PLANTA1", "worktype": "CM", "wopriority": 1},
    "OT-1005": {"wonum": "OT-1005", "description": "Lubricación rodamientos motor M-07",   "status": "COMP",  "assetnum": "MOTOR-M07",  "siteid": "PLANTA2", "worktype": "PM", "wopriority": 3},
}

INVENTARIO_MOCK = {
    ("FILTRO-001",     "CENTRAL"): {"itemnum": "FILTRO-001",     "location": "CENTRAL", "curbal": 15, "binnum": "PASILLO-B2-ESTANTE4"},
    ("SKF-6204",       "CENTRAL"): {"itemnum": "SKF-6204",       "location": "CENTRAL", "curbal": 15, "binnum": "PASILLO-B2-ESTANTE4"},
    ("RODAMIENTO-SKF", "CENTRAL"): {"itemnum": "RODAMIENTO-SKF", "location": "CENTRAL", "curbal": 8,  "binnum": "PASILLO-A1-ESTANTE2"},
    ("VALVULA-2P",     "NORTE"):   {"itemnum": "VALVULA-2P",     "location": "NORTE",   "curbal": 3,  "binnum": "RACK-C3"},
}

ACTIVOS_MOCK = {
    "BOMBA-B201": {"assetnum": "BOMBA-B201", "description": "Bomba centrífuga B-201", "status": "OPERATING", "siteid": "PLANTA1", "location": "SALA-BOMBAS"},
    "COMP-C305":  {"assetnum": "COMP-C305",  "description": "Compresor C-305",        "status": "OPERATING", "siteid": "PLANTA1", "location": "SALA-COMPRESORES"},
    "HVAC-ZN01":  {"assetnum": "HVAC-ZN01",  "description": "Sistema HVAC Zona Norte","status": "OPERATING", "siteid": "PLANTA2", "location": "ZONA-NORTE"},
    "MOTOR-M07":  {"assetnum": "MOTOR-M07",  "description": "Motor eléctrico M-07",   "status": "OPERATING", "siteid": "PLANTA2", "location": "SALA-MOTORES"},
}

WORKFLOW_MOCK = {
    "WF-001": {"assignid": "WF-001", "wonum": "OT-1003", "process": "WOCHANGE", "assignstatus": "ACTIVE", "ownerid": "OT-1003", "allowedactions": ["APPROVE", "REJECT", "REQUESTINFO"]},
    "WF-002": {"assignid": "WF-002", "wonum": "OT-1004", "process": "WOCHANGE", "assignstatus": "ACTIVE", "ownerid": "OT-1004", "allowedactions": ["APPROVE", "REJECT"]},
}

_working_set: dict = {}
_ws_counter: int = 0

OS_MOCK_CATALOG = {
    "MXWO":        {"description": "Órdenes de Trabajo",      "key_field": "wonum"},
    "MXWODETAIL":  {"description": "Detalle OT",              "key_field": "wonum"},
    "MXASSET":     {"description": "Activos",                 "key_field": "assetnum"},
    "MXINVENTORY": {"description": "Inventario",              "key_field": "itemnum"},
    "MXPERSON":    {"description": "Personas / Empleados",    "key_field": "personid"},
    "MXSR":        {"description": "Solicitudes de Servicio", "key_field": "ticketid"},
    "MXLABOR":     {"description": "Recursos de Labor",       "key_field": "laborcode"},
}

# ============================================================
#  LÓGICA DE NEGOCIO
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

CAMPOS_READONLY = {"status", "changeby", "changedate", "statusdate", "wonum", "ticketid"}

def _headers() -> dict:
    return {"apikey": API_KEY, "Accept": "application/json", "Content-Type": "application/json"}

def _oslc_url(os_name: str) -> str:
    return f"{MAXIMO_URL}/oslc/os/{os_name.lower()}"


# ============================================================
#  TOOL 1 — consultar_ot
# ============================================================
@mcp.tool()
def consultar_ot(num_ot: str) -> str:
    """Consulta los detalles completos de una Orden de Trabajo (OT) en Maximo."""
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
                f"🏭 Sitio: {ot.get('siteid','N/D')} | Tipo: {ot.get('worktype','N/D')} | Prioridad: {ot.get('wopriority','N/D')}\n"
                f"➡️  Puede pasar a: {transiciones}")
    try:
        params = {"oslc.where": f'wonum="{num_ot}"', "oslc.select": "wonum,description,status,assetnum,siteid,worktype,wopriority", "lean": "1"}
        r = requests.get(_oslc_url("mxwodetail"), params=params, headers=_headers(), verify=False, timeout=10)
        r.raise_for_status()
        data = r.json().get("member", [])
        if not data:
            return f"❌ OT '{num_ot}' no encontrada en Maximo."
        ot = data[0]
        estado = ot.get("status", "").upper()
        destinos = TRANSICIONES_VALIDAS.get(estado, [])
        return (f"✅ [REAL] OT: {ot.get('wonum')} — {ot.get('description')}\n"
                f"📊 Estado: {estado} | 🔧 Activo: {ot.get('assetnum')} | Sitio: {ot.get('siteid')}\n"
                f"➡️  Puede pasar a: {', '.join(destinos) or 'ninguna'}")
    except Exception as e:
        return f"❌ Error: {str(e)}"


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
        return (f"🧪 [SIMULACIÓN INVENTARIO]\nArtículo: {inv['itemnum']}\nAlmacén: {inv['location']}\n"
                f"Cantidad Disponible: {inv['curbal']} unidades\nUbicación: {inv['binnum']}")
    try:
        params = {"oslc.where": f'itemnum="{item_num}" and location="{almacen}"', "oslc.select": "itemnum,location,curbal,binnum", "lean": "1"}
        r = requests.get(_oslc_url("mxinventory"), params=params, headers=_headers(), verify=False, timeout=10)
        r.raise_for_status()
        data = r.json().get("member", [])
        if not data:
            return f"❌ Artículo '{item_num}' no encontrado en almacén '{almacen}'."
        inv = data[0]
        return f"✅ {inv.get('itemnum')} | {inv.get('location')} | Stock: {inv.get('curbal')} | {inv.get('binnum')}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================
#  TOOL 3 — listar_transiciones_ot
# ============================================================
@mcp.tool()
def listar_transiciones_ot(num_ot: str) -> str:
    """Muestra el estado actual de una OT y los cambios de estado permitidos."""
    num_ot = num_ot.strip().upper()
    if MODO_SIMULACION:
        ot = OT_MOCK.get(num_ot)
        if not ot:
            return f"⚠️ OT '{num_ot}' no encontrada.\nDisponibles: {', '.join(OT_MOCK.keys())}"
        estado = ot["status"]
        destinos = TRANSICIONES_VALIDAS.get(estado, [])
        lineas = [f"📋 OT: {num_ot}  |  Activo: {ot['assetnum']}",
                  f"📊 Estado actual: {estado} — {DESCRIPCION_ESTADOS.get(estado,'')}", "",
                  "✅ Cambios permitidos:" if destinos else "🔒 Estado terminal."]
        for e in destinos:
            lineas.append(f"   → {e:<8}  {DESCRIPCION_ESTADOS.get(e,'')}")
        if destinos:
            lineas.append(f'\n💡 Usa: cambiar_estado_ot("{num_ot}", "{destinos[0]}", "tu nota")')
        return "\n".join(lineas)
    try:
        params = {"oslc.where": f'wonum="{num_ot}"', "oslc.select": "wonum,status,assetnum", "lean": "1"}
        r = requests.get(_oslc_url("mxwodetail"), params=params, headers=_headers(), verify=False, timeout=10)
        r.raise_for_status()
        data = r.json().get("member", [])
        if not data:
            return f"❌ OT '{num_ot}' no encontrada."
        ot = data[0]
        estado = ot.get("status", "").upper()
        destinos = TRANSICIONES_VALIDAS.get(estado, [])
        lineas = [f"📋 OT: {num_ot}  |  {ot.get('assetnum','N/D')}",
                  f"📊 {estado} — {DESCRIPCION_ESTADOS.get(estado,'')}", "",
                  "✅ Cambios:" if destinos else "🔒 Terminal."]
        for e in destinos:
            lineas.append(f"   → {e:<8}  {DESCRIPCION_ESTADOS.get(e,'')}")
        return "\n".join(lineas)
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================
#  TOOL 4 — cambiar_estado_ot
# ============================================================
@mcp.tool()
def cambiar_estado_ot(num_ot: str, nuevo_estado: str, memo: str = "") -> str:
    """
    Cambia el estado de una Orden de Trabajo en IBM Maximo (MAS 8.x/9.x).
    Args:
        num_ot:        Número de la OT (ej: "OT-1001")
        nuevo_estado:  Código destino: APPR, INPRG, COMP, CLOSE, CAN, WMATL
        memo:          Nota opcional para el historial
    """
    num_ot       = num_ot.strip().upper()
    nuevo_estado = nuevo_estado.strip().upper()
    timestamp    = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    memo_final   = memo.strip() or "(sin nota)"

    if nuevo_estado not in TRANSICIONES_VALIDAS:
        return f"❌ Estado '{nuevo_estado}' no reconocido.\nVálidos: {', '.join(TRANSICIONES_VALIDAS.keys())}"

    if MODO_SIMULACION:
        ot = OT_MOCK.get(num_ot)
        if not ot:
            return f"⚠️ OT '{num_ot}' no encontrada.\nDisponibles: {', '.join(OT_MOCK.keys())}"
        estado_actual = ot["status"]
        if nuevo_estado not in TRANSICIONES_VALIDAS.get(estado_actual, []):
            destinos = TRANSICIONES_VALIDAS.get(estado_actual, [])
            opciones = "\n".join(f"   → {e}  ({DESCRIPCION_ESTADOS.get(e,'')})" for e in destinos) if destinos else "   (terminal)"
            return f"❌ Transición {estado_actual}→{nuevo_estado} no permitida.\n✅ Válidas:\n{opciones}"
        estado_anterior = estado_actual
        OT_MOCK[num_ot]["status"] = nuevo_estado
        return (f"✅ [SIMULACIÓN] Estado cambiado exitosamente.\n\n"
                f"📋 OT:              {num_ot}\n🔧 Activo:          {ot['assetnum']}\n"
                f"📝 Descripción:     {ot['description']}\n"
                f"📊 Estado anterior: {estado_anterior} — {DESCRIPCION_ESTADOS.get(estado_anterior,'')}\n"
                f"🎯 Estado nuevo:    {nuevo_estado} — {DESCRIPCION_ESTADOS.get(nuevo_estado,'')}\n"
                f"📎 Memo:            {memo_final}\n🕐 Timestamp:       {timestamp}\n\n"
                f"⚠️  Cambia MODO_SIMULACION = False para afectar Maximo real.")
    try:
        params = {"oslc.where": f'wonum="{num_ot}"', "oslc.select": "wonum,status,description,assetnum", "lean": "1"}
        r = requests.get(_oslc_url("mxwodetail"), params=params, headers=_headers(), verify=False, timeout=10)
        r.raise_for_status()
        data = r.json().get("member", [])
        if not data:
            return f"❌ OT '{num_ot}' no encontrada."
        recurso = data[0]
        estado_actual = recurso.get("status", "").upper()
        href = recurso.get("href") or recurso.get("rdf:about", "")
        if nuevo_estado not in TRANSICIONES_VALIDAS.get(estado_actual, []):
            return f"❌ Transición {estado_actual}→{nuevo_estado} no permitida."
        if not href:
            return "❌ No se pudo obtener el href."
        patch_headers = {**_headers(), "x-method-override": "PATCH", "patchtype": "MERGE"}
        r2 = requests.post(href, json={"status": nuevo_estado, "memo": memo_final}, headers=patch_headers, verify=False, timeout=15)
        r2.raise_for_status()
        return f"✅ [REAL] OT {num_ot}: {estado_actual} → {nuevo_estado} | HTTP: {r2.status_code} | {timestamp}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================
#  TOOL 5 — query_maximo  ★ NUEVA
# ============================================================
@mcp.tool()
def query_maximo(object_structure: str, where: str = "", select: str = "", order_by: str = "", page_size: int = 10) -> str:
    """
    Consulta genérica a cualquier Object Structure de Maximo via OSLC REST API.
    Args:
        object_structure: OS de Maximo (ej: MXWO, MXASSET, MXINVENTORY, MXSR, MXPERSON)
        where:     Filtro OSLC (ej: 'status="APPR" and siteid="PLANTA1"')
        select:    Campos separados por coma (ej: 'wonum,description,status')
        order_by:  Ordenamiento (ej: '-reportdate')
        page_size: Registros a retornar (default 10, max 100)
    Ejemplos: "Lista OTs aprobadas en PLANTA1", "Muestra activos en OPERATING"
    """
    os_name = object_structure.strip().upper()
    if MODO_SIMULACION:
        if "WO" in os_name:
            records = list(OT_MOCK.values())
        elif "ASSET" in os_name:
            records = list(ACTIVOS_MOCK.values())
        elif "INVENTORY" in os_name:
            records = [{"itemnum": k[0], "location": k[1], **v} for k, v in INVENTARIO_MOCK.items()]
        else:
            records = [{"info": f"OS '{os_name}' no tiene mock definido."}]
        if where and records and "info" not in records[0]:
            import re
            match = re.search(r'status\s*=\s*["\']?(\w+)["\']?', where, re.IGNORECASE)
            if match:
                records = [r for r in records if r.get("status", "").upper() == match.group(1).upper()]
        records = records[:page_size]
        lineas = [f"🧪 [SIMULACIÓN] Query {os_name} | Registros: {len(records)}", ""]
        for i, rec in enumerate(records, 1):
            lineas.append(f"  [{i}] " + " | ".join(f"{k}: {v}" for k, v in list(rec.items())[:6]))
        return "\n".join(lineas)
    try:
        params = {"lean": "1", "oslc.pageSize": str(min(page_size, 100))}
        if where:    params["oslc.where"]   = where
        if select:   params["oslc.select"]  = select
        if order_by: params["oslc.orderBy"] = order_by
        r = requests.get(_oslc_url(os_name), params=params, headers=_headers(), verify=False, timeout=15)
        r.raise_for_status()
        data    = r.json()
        members = data.get("member", [])
        total   = data.get("responseInfo", {}).get("totalCount", "?")
        lineas  = [f"✅ OS: {os_name} | Total: {total} | Mostrando: {len(members)}", ""]
        for i, rec in enumerate(members, 1):
            campos = {k: v for k, v in rec.items() if not k.startswith("_") and k != "href"}
            lineas.append(f"  [{i}] " + " | ".join(f"{k}: {v}" for k, v in list(campos.items())[:6]))
        return "\n".join(lineas)
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================
#  TOOL 6 — consultar_activo  ★ NUEVA
# ============================================================
@mcp.tool()
def consultar_activo(asset_num: str) -> str:
    """Consulta los detalles de un Activo en Maximo (MXASSET). Args: asset_num: Número del activo (ej: BOMBA-B201)"""
    asset_num = asset_num.strip().upper()
    if MODO_SIMULACION:
        activo = ACTIVOS_MOCK.get(asset_num)
        if not activo:
            return f"⚠️ Activo '{asset_num}' no encontrado.\nDisponibles: {', '.join(ACTIVOS_MOCK.keys())}"
        return (f"🧪 [SIMULACIÓN] Activo: {activo['assetnum']}\n📝 {activo['description']}\n"
                f"📊 Estado: {activo['status']}\n🏭 Sitio: {activo['siteid']} | Ubicación: {activo['location']}")
    try:
        params = {"oslc.where": f'assetnum="{asset_num}"', "oslc.select": "assetnum,description,status,siteid,location,serialnum", "lean": "1"}
        r = requests.get(_oslc_url("mxasset"), params=params, headers=_headers(), verify=False, timeout=10)
        r.raise_for_status()
        data = r.json().get("member", [])
        if not data:
            return f"❌ Activo '{asset_num}' no encontrado."
        a = data[0]
        return (f"✅ {a.get('assetnum')} — {a.get('description')}\n"
                f"Estado: {a.get('status')} | Sitio: {a.get('siteid')} | Loc: {a.get('location')} | S/N: {a.get('serialnum','N/D')}")
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================
#  TOOL 7 — listar_object_structures  ★ NUEVA
# ============================================================
@mcp.tool()
def listar_object_structures(filtro: str = "") -> str:
    """
    Lista los Object Structures (APIs) disponibles en Maximo para descubrir qué entidades puedes consultar.
    Args: filtro: Filtro por nombre (ej: "WO", "ASSET")
    """
    if MODO_SIMULACION:
        catalog = {k: v for k, v in OS_MOCK_CATALOG.items() if not filtro or filtro.upper() in k}
        lineas  = [f"🧪 [SIMULACIÓN] Object Structures ({len(catalog)}):", ""]
        for os_name, meta in catalog.items():
            lineas.append(f"  📦 {os_name:<18} — {meta['description']}  (clave: {meta['key_field']})")
        lineas.append("\n💡 Usa query_maximo(object_structure='MXWO', ...) para consultar.")
        return "\n".join(lineas)
    try:
        r = requests.get(f"{MAXIMO_URL}/api/meta/os", headers=_headers(), verify=False, timeout=10)
        r.raise_for_status()
        oss = r.json()
        if filtro:
            oss = [o for o in oss if filtro.upper() in o.get("name", "").upper()]
        lineas = [f"✅ Object Structures en Maximo ({len(oss)}):", ""]
        for o in oss[:30]:
            lineas.append(f"  📦 {o.get('name','?'):<20} — {o.get('description','')}")
        if len(oss) > 30:
            lineas.append(f"  ... y {len(oss)-30} más.")
        return "\n".join(lineas)
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================
#  TOOL 8 — crear_ot  ★ NUEVA
# ============================================================
@mcp.tool()
def crear_ot(description: str, asset_num: str, site_id: str = "PLANTA1", work_type: str = "CM", priority: int = 3, memo: str = "") -> str:
    """
    Crea una nueva Orden de Trabajo en Maximo.
    Args:
        description: Descripción (requerido)
        asset_num:   Activo asociado (requerido)
        site_id:     Sitio (default: PLANTA1)
        work_type:   CM=correctivo, PM=preventivo (default: CM)
        priority:    1-5 (1=urgente, default: 3)
        memo:        Nota inicial
    Ejemplos: "Crea OT para bomba B-201", "Abre orden correctiva válvula V-102 prioridad 1"
    """
    if MODO_SIMULACION:
        nuevo_id = f"OT-{1000 + len(OT_MOCK) + 1}"
        OT_MOCK[nuevo_id] = {"wonum": nuevo_id, "description": description, "status": "WAPPR",
                             "assetnum": asset_num.upper(), "siteid": site_id.upper(), "worktype": work_type.upper(), "wopriority": priority}
        return (f"✅ [SIMULACIÓN] OT creada exitosamente.\n\n"
                f"📋 Nueva OT:    {nuevo_id}\n📝 Descripción: {description}\n"
                f"📊 Estado:      WAPPR — Esperando Aprobación\n🔧 Activo:      {asset_num.upper()}\n"
                f"🏭 {site_id.upper()} | {work_type.upper()} | Prioridad: {priority}\n"
                f"📎 Nota:        {memo or '(ninguna)'}\n🕐 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
                f"⚠️  Cambia MODO_SIMULACION = False para crear en Maximo real.")
    try:
        payload = {"description": description, "assetnum": asset_num.upper(), "siteid": site_id.upper(),
                   "worktype": work_type.upper(), "wopriority": priority}
        if memo:
            payload["description_longdescription"] = memo
        r = requests.post(_oslc_url("mxwodetail"), json=payload, headers=_headers(), verify=False, timeout=15)
        r.raise_for_status()
        return f"✅ [REAL] OT creada. HTTP: {r.status_code} | Location: {r.headers.get('Location','')}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================
#  TOOL 9 — ws_editar_ot  ★ NUEVA
# ============================================================
@mcp.tool()
def ws_editar_ot(num_ot: str, campos: str) -> str:
    """
    Edita campos de una OT con preview antes de guardar (Working Set pattern).
    Llama a ws_confirmar_cambios(ws_id) para guardar o ws_cancelar_cambios(ws_id) para descartar.
    Args:
        num_ot: Número de la OT (ej: "OT-1001")
        campos: JSON con los campos a cambiar (ej: '{"wopriority": 1, "description": "Nuevo texto"}')
                NO usar para status — usa cambiar_estado_ot() en su lugar.
    """
    global _working_set, _ws_counter
    num_ot = num_ot.strip().upper()
    try:
        updates = json.loads(campos)
    except Exception:
        return "❌ 'campos' debe ser JSON válido. Ej: '{\"wopriority\": 1}'"
    no_permitidos = [k for k in updates if k.lower() in CAMPOS_READONLY]
    if no_permitidos:
        return f"❌ Campos no editables: {', '.join(no_permitidos)}\n💡 Para status usa cambiar_estado_ot()."
    if MODO_SIMULACION:
        ot = OT_MOCK.get(num_ot)
        if not ot:
            return f"⚠️ OT '{num_ot}' no encontrada.\nDisponibles: {', '.join(OT_MOCK.keys())}"
        _ws_counter += 1
        ws_id = f"WS-{_ws_counter:04d}"
        _working_set[ws_id] = {"num_ot": num_ot, "original": dict(ot), "changes": updates, "ts": datetime.now().strftime("%d/%m/%Y %H:%M:%S")}
        lineas = [f"🔍 [SIMULACIÓN] Preview — Working Set: {ws_id}", f"📋 OT: {num_ot} — {ot['description']}", "",
                  "  Campo              | Valor Actual          | Valor Nuevo", "  " + "-"*60]
        for campo, nuevo_val in updates.items():
            lineas.append(f"  {campo:<18} | {str(ot.get(campo,'N/D')):<21} | {str(nuevo_val)}")
        lineas.append(f"\n✅ Confirmar: ws_confirmar_cambios(ws_id='{ws_id}')")
        lineas.append(f"❌ Cancelar:  ws_cancelar_cambios(ws_id='{ws_id}')")
        return "\n".join(lineas)
    try:
        params = {"oslc.where": f'wonum="{num_ot}"', "oslc.select": "wonum,status,description,assetnum,wopriority,worktype", "lean": "1"}
        r = requests.get(_oslc_url("mxwodetail"), params=params, headers=_headers(), verify=False, timeout=10)
        r.raise_for_status()
        data = r.json().get("member", [])
        if not data:
            return f"❌ OT '{num_ot}' no encontrada."
        recurso = data[0]
        href    = recurso.get("href") or recurso.get("rdf:about", "")
        _ws_counter += 1
        ws_id = f"WS-{_ws_counter:04d}"
        _working_set[ws_id] = {"num_ot": num_ot, "href": href, "changes": updates, "original": recurso, "ts": datetime.now().strftime("%d/%m/%Y %H:%M:%S")}
        lineas = [f"🔍 [REAL] Preview — Working Set: {ws_id}", f"📋 OT: {num_ot}", "",
                  "  Campo              | Valor Actual          | Valor Nuevo", "  " + "-"*60]
        for campo, nuevo_val in updates.items():
            lineas.append(f"  {campo:<18} | {str(recurso.get(campo,'N/D')):<21} | {str(nuevo_val)}")
        lineas.append(f"\n✅ Confirmar: ws_confirmar_cambios(ws_id='{ws_id}')")
        lineas.append(f"❌ Cancelar:  ws_cancelar_cambios(ws_id='{ws_id}')")
        return "\n".join(lineas)
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================
#  TOOL 10 — ws_confirmar_cambios  ★ NUEVA
# ============================================================
@mcp.tool()
def ws_confirmar_cambios(ws_id: str) -> str:
    """Confirma y guarda los cambios de un Working Set creado por ws_editar_ot(). Args: ws_id: ID del WS (ej: WS-0001)"""
    ws = _working_set.get(ws_id)
    if not ws:
        return f"❌ Working Set '{ws_id}' no encontrado. Usa ws_editar_ot() para crear uno nuevo."
    num_ot  = ws["num_ot"]
    changes = ws["changes"]
    if MODO_SIMULACION:
        ot = OT_MOCK.get(num_ot)
        if ot:
            for k, v in changes.items():
                ot[k] = v
        del _working_set[ws_id]
        return (f"✅ [SIMULACIÓN] Cambios guardados.\n📋 OT: {num_ot}\n"
                f"✏️  {', '.join(f'{k}={v}' for k,v in changes.items())}\n"
                f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
                f"⚠️  Cambia MODO_SIMULACION = False para guardar en Maximo real.")
    try:
        href = ws.get("href")
        if not href:
            return "❌ No se encontró href. Crea un nuevo WS con ws_editar_ot()."
        patch_headers = {**_headers(), "x-method-override": "PATCH", "patchtype": "MERGE"}
        r = requests.post(href, json=changes, headers=patch_headers, verify=False, timeout=15)
        r.raise_for_status()
        del _working_set[ws_id]
        return f"✅ [REAL] Cambios guardados en Maximo. OT: {num_ot} | HTTP: {r.status_code}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================
#  TOOL 11 — ws_cancelar_cambios  ★ NUEVA
# ============================================================
@mcp.tool()
def ws_cancelar_cambios(ws_id: str) -> str:
    """Cancela y descarta un Working Set sin guardar nada. Args: ws_id: ID del WS (ej: WS-0001)"""
    if ws_id in _working_set:
        num_ot = _working_set[ws_id]["num_ot"]
        del _working_set[ws_id]
        return f"🚫 Working Set '{ws_id}' cancelado. Cambios para OT {num_ot} descartados."
    return f"⚠️ Working Set '{ws_id}' no encontrado (ya procesado o cancelado)."


# ============================================================
#  TOOL 12 — obtener_workflow_assignments  ★ NUEVA
# ============================================================
@mcp.tool()
def obtener_workflow_assignments(solo_activos: bool = True) -> str:
    """
    Lista las asignaciones de Workflow pendientes en Maximo (aprobaciones, decisiones).
    Args: solo_activos: Si True (default), solo muestra los workflows ACTIVE.
    Ejemplos: "¿Qué workflows tengo pendientes?", "Muestra aprobaciones pendientes"
    """
    if MODO_SIMULACION:
        assignments = [a for a in WORKFLOW_MOCK.values() if not solo_activos or a.get("assignstatus") == "ACTIVE"]
        if not assignments:
            return "✅ [SIMULACIÓN] No hay asignaciones de workflow pendientes."
        lineas = [f"🧪 [SIMULACIÓN] Workflows pendientes: {len(assignments)}", ""]
        for a in assignments:
            lineas.append(f"  📌 ID: {a['assignid']} | OT: {a['wonum']} | Proceso: {a['process']}")
            lineas.append(f"     Estado: {a['assignstatus']} | Acciones: {', '.join(a.get('allowedactions', []))}")
            lineas.append(f"     💡 enviar_workflow_response(assign_id='{a['assignid']}', accion='APPROVE')")
            lineas.append("")
        return "\n".join(lineas)
    try:
        params = {"lean": "1", "oslc.select": "assignid,wonum,process,assignstatus,ownerid,allowedactions"}
        if solo_activos:
            params["oslc.where"] = 'assignstatus="ACTIVE"'
        r = requests.get(_oslc_url("wfassignment"), params=params, headers=_headers(), verify=False, timeout=10)
        r.raise_for_status()
        data = r.json().get("member", [])
        if not data:
            return "✅ No hay asignaciones pendientes."
        lineas = [f"✅ Workflow Assignments: {len(data)}", ""]
        for a in data:
            lineas.append(f"  📌 {a.get('assignid')} | OT: {a.get('wonum')} | {a.get('process')} | {a.get('assignstatus')}")
        return "\n".join(lineas)
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================
#  TOOL 13 — enviar_workflow_response  ★ NUEVA
# ============================================================
@mcp.tool()
def enviar_workflow_response(assign_id: str, accion: str, memo: str = "") -> str:
    """
    Responde a una asignación de Workflow en Maximo (aprobar, rechazar, etc.).
    Llama primero a obtener_workflow_assignments() para ver las acciones disponibles.
    Args:
        assign_id: ID del workflow (ej: "WF-001")
        accion:    APPROVE, REJECT, REQUESTINFO, ROUTE
        memo:      Nota/comentario (obligatorio para rechazos)
    Ejemplos: "Aprueba workflow WF-001", "Rechaza WF-002 nota: falta documentación"
    """
    assign_id  = assign_id.strip().upper()
    accion     = accion.strip().upper()
    memo_final = memo.strip() or "(sin comentario)"
    if MODO_SIMULACION:
        wf = WORKFLOW_MOCK.get(assign_id)
        if not wf:
            return f"⚠️ Asignación '{assign_id}' no encontrada.\nDisponibles: {', '.join(WORKFLOW_MOCK.keys())}"
        allowed = wf.get("allowedactions", [])
        if accion not in allowed:
            return f"❌ Acción '{accion}' no permitida.\nVálidas: {', '.join(allowed)}"
        del WORKFLOW_MOCK[assign_id]
        return (f"✅ [SIMULACIÓN] Workflow response enviada.\n\n"
                f"📌 Assignment: {assign_id} | 📋 OT: {wf['wonum']}\n"
                f"🎯 Acción: {accion} | 📎 Memo: {memo_final}\n"
                f"🕐 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n\n"
                f"⚠️  Cambia MODO_SIMULACION = False para afectar Maximo real.")
    try:
        params = {"oslc.where": f'assignid="{assign_id}"', "oslc.select": "assignid,ownerid,process,wonum", "lean": "1"}
        r = requests.get(_oslc_url("wfassignment"), params=params, headers=_headers(), verify=False, timeout=10)
        r.raise_for_status()
        data = r.json().get("member", [])
        if not data:
            return f"❌ Assignment '{assign_id}' no encontrado."
        wf = data[0]
        endpoint = f"{_oslc_url('mxwodetail')}/{wf.get('ownerid')}/action"
        r2 = requests.post(endpoint, json={"wfaction": accion, "memo": memo_final}, headers=_headers(), verify=False, timeout=15)
        r2.raise_for_status()
        return f"✅ [REAL] Workflow {assign_id} → {accion} | OT: {wf.get('wonum')} | HTTP: {r2.status_code}"
    except Exception as e:
        return f"❌ Error: {str(e)}"


# ============================================================
#  TOOL 14 — verificar_conexion
# ============================================================
@mcp.tool()
def verificar_conexion() -> str:
    """Verifica la conexión con el servidor de Maximo y lista las tools disponibles."""
    if MODO_SIMULACION:
        return (f"✅ Conexión exitosa con el servidor de Maximo\n"
                f"🧪 Modo: SIMULACIÓN | 🕐 {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
                f"📦 14 Tools disponibles:\n"
                f"   [Consulta]  consultar_ot, consultar_inventario, consultar_activo, query_maximo\n"
                f"   [Listado]   listar_transiciones_ot, listar_object_structures\n"
                f"   [Cambio]    cambiar_estado_ot\n"
                f"   [Creación]  crear_ot\n"
                f"   [Edición]   ws_editar_ot, ws_confirmar_cambios, ws_cancelar_cambios\n"
                f"   [Workflow]  obtener_workflow_assignments, enviar_workflow_response\n"
                f"   [Sistema]   verificar_conexion")
    try:
        r = requests.get(f"{MAXIMO_URL}/api/whoami", headers=_headers(), verify=False, timeout=8)
        r.raise_for_status()
        info = r.json()
        return (f"✅ [REAL] Conexión exitosa.\nUsuario: {info.get('personid','?')} | Lang: {info.get('baseLang','?')}\n"
                f"Servidor: {MAXIMO_URL}")
    except Exception as e:
        return f"❌ Error de conexión: {str(e)}"


# ============================================================
if __name__ == "__main__":
    mcp.run()
