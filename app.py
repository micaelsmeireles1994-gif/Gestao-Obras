import streamlit as st
import pandas as pd
import calendar
from datetime import date
import requests
import json
from fpdf import FPDF

st.set_page_config(page_title="Gestão de Obras", page_icon="🏗️", layout="centered")
st.session_state.setdefault("ciclo", 0)
st.session_state.setdefault("aviso", "")
st.session_state.setdefault("usr_nome", "")
st.session_state.setdefault("usr_perfil", "")

MESES = {
    1: "01 - Janeiro", 2: "02 - Fevereiro", 3: "03 - Março", 4: "04 - Abril",
    5: "05 - Maio", 6: "06 - Junho", 7: "07 - Julho", 8: "08 - Agosto",
    9: "09 - Setembro", 10: "10 - Outubro", 11: "11 - Novembro", 12: "12 - Dezembro"
}

def txt_pdf(valor, limite=40):
    return str(valor)[:limite].encode("latin-1", "replace").decode("latin-1")

def bytes_pdf(doc):
    out = doc.output()
    return out.encode("latin-1") if isinstance(out, str) else bytes(out)

def ajustar_colunas(df, sinonimos):
    if df.empty:
        return df
    mapa = {str(c).strip().lower(): c for c in df.columns}
    trocas = {}
    for destino, opcoes in sinonimos.items():
        if destino not in df.columns:
            for op in opcoes:
                if op.lower() in mapa:
                    trocas[mapa[op.lower()]] = destino
                    break
    return df.rename(columns=trocas) if trocas else df

@st.cache_data(ttl=15)
def ler_servidor():
    r = requests.get(st.secrets["apps_script_url"], timeout=20)
    r.raise_for_status()
    pacote = r.json()

    def extrair(aba, cols, sin=None):
        df = pd.DataFrame(pacote.get(aba, []))
        if df.empty:
            return pd.DataFrame(columns=cols)
        if sin:
            df = ajustar_colunas(df, sin)
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        return df[cols]

    obras = extrair(
        "Obras",
        ["ID Obra", "Nome da Obra", "Cliente", "Valor Adjudicado", "Total Gasto", "Saldo Restante", "Estado"],
        {"ID Obra": ["ID", "Codigo", "Código"], "Nome da Obra": ["Obra", "Nome"], "Valor Adjudicado": ["Valor", "Orcamento", "Orçamento"]}
    )
    elem_raw = extrair(
        "Elementos",
        ["Elemento", "Valor_Dia", "Utilizador", "Senha", "Perfil"],
        {"Elemento": ["Colaborador", "Colaboradores", "Nome"], "Valor_Dia": ["Valor Dia", "Valor/Dia", "Custo_Dia", "Valor"]}
    )
    elem = elem_raw[["Elemento", "Valor_Dia"]].copy()
    users = elem_raw[["Utilizador", "Senha", "Perfil"]].copy()

    meios = extrair(
        "Meios",
        ["Meio / Equipamento", "Valor_Dia"],
        {"Meio / Equipamento": ["Viatura", "Viaturas", "Meio", "Equipamento"], "Valor_Dia": ["Valor Dia", "Valor/Dia", "Valor"]}
    )
    mat = extrair(
        "Materiais",
        ["Material", "Unidade", "Preco_Unitario"],
        {"Material": ["Nome", "Artigo"], "Unidade": ["Un", "Un."], "Preco_Unitario": ["Preco", "Preço", "Valor"]}
    )
    diario = extrair(
        "Registos_Diarios",
        ["ID_Registo", "Data", "ID Obra", "Elemento", "Dias Elemento", "Custo Elemento",
         "Meio", "Dias Meio", "Custo Meio", "Material", "Qtd Material", "Custo Material", "Total do Dia", "Notas"],
        {"Elemento": ["Colaborador"], "Meio": ["Viatura"]}
    )
    return obras, elem, users, meios, mat, diario

def guardar_aba(aba, df):
    limpo = df.fillna("")
    linhas = [limpo.columns.tolist()] + limpo.values.tolist()
    r = requests.post(
        st.secrets["apps_script_url"],
        data=json.dumps({"sheet": aba, "rows": linhas}),
        headers={"Content-Type": "text/plain;charset=utf-8"},
        timeout=20
    )
    r.raise_for_status()

def guardar_elementos_e_users(df_e, df_u):
    e_limpo = df_e[df_e["Elemento"].fillna("").astype(str).str.strip() != ""][["Elemento", "Valor_Dia"]].reset_index(drop=True)
    u_limpo = df_u[df_u["Utilizador"].fillna("").astype(str).str.strip() != ""][["Utilizador", "Senha", "Perfil"]].reset_index(drop=True)
    combinado = pd.concat([e_limpo, u_limpo], axis=1).fillna("")
    for col in ["Elemento", "Valor_Dia", "Utilizador", "Senha", "Perfil"]:
        if col not in combinado.columns:
            combinado[col] = ""
    guardar_aba("Elementos", combinado[["Elemento", "Valor_Dia", "Utilizador", "Senha", "Perfil"]])

def recalcular_obras(df_o, df_d):
    o = df_o.copy()
    o["ID Obra"] = o["ID Obra"].fillna("").astype(str).str.strip()
    o["Valor Adjudicado"] = pd.to_numeric(o["Valor Adjudicado"], errors="coerce").fillna(0.0)
    gastos = {}
    if not df_d.empty:
        d = df_d.copy()
        d["ID Obra"] = d["ID Obra"].fillna("").astype(str).str.strip()
        d["Total do Dia"] = pd.to_numeric(d["Total do Dia"], errors="coerce").fillna(0.0)
        gastos = d.groupby("ID Obra")["Total do Dia"].sum().to_dict()
    o["Total Gasto"] = o["ID Obra"].map(gastos).fillna(0.0)
    o["Saldo Restante"] = o["Valor Adjudicado"] - o["Total Gasto"]
    guardar_aba("Obras", o)

def converter_datas(serie):
    s = serie.fillna("").astype(str).str.strip()
    iso = s.str.match(r"^\d{4}-\d{2}-\d{2}")
    res = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    if iso.any():
        res.loc[iso] = pd.to_datetime(s[iso], format="mixed", errors="coerce", utc=True).dt.tz_localize(None).dt.round("D")
    if (~iso).any():
        res.loc[~iso] = pd.to_datetime(s[~iso], format="mixed", dayfirst=True, errors="coerce").dt.round("D")
    return res

try:
    df_obras, df_elem, df_users, df_meios, df_mat, df_diario = ler_servidor()
except Exception as erro:
    st.error(f"Erro ao ligar à folha Google: {erro}")
    st.stop()

for col in ["ID Obra", "Nome da Obra", "Cliente", "Estado"]:
    df_obras[col] = df_obras[col].fillna("").astype(str).str.strip()
for col in ["Valor Adjudicado", "Total Gasto", "Saldo Restante"]:
    df_obras[col] = pd.to_numeric(df_obras[col], errors="coerce").fillna(0.0)
df_obras = df_obras[df_obras["ID Obra"] != ""].copy()

df_elem["Elemento"] = df_elem["Elemento"].fillna("").astype(str).str.strip()
df_elem["Valor_Dia"] = pd.to_numeric(df_elem["Valor_Dia"], errors="coerce").fillna(0.0)
df_elem = df_elem[df_elem["Elemento"] != ""].copy()

for col in ["Utilizador", "Senha", "Perfil"]:
    df_users[col] = df_users[col].fillna("").astype(str).str.strip()
df_users["Senha"] = df_users["Senha"].str.replace(r"\.0$", "", regex=True)
df_users = df_users[df_users["Utilizador"] != ""].copy()
if df_users.empty:
    df_users = pd.DataFrame([{"Utilizador": "admin", "Senha": "1234", "Perfil": "Admin"}])

df_meios["Meio / Equipamento"] = df_meios["Meio / Equipamento"].fillna("").astype(str).str.strip()
df_meios["Valor_Dia"] = pd.to_numeric(df_meios["Valor_Dia"], errors="coerce").fillna(0.0)
df_meios = df_meios[df_meios["Meio / Equipamento"] != ""].copy()

for col in ["Material", "Unidade"]:
    df_mat[col] = df_mat[col].fillna("").astype(str).str.strip()
df_mat["Preco_Unitario"] = pd.to_numeric(df_mat["Preco_Unitario"], errors="coerce").fillna(0.0)
df_mat = df_mat[df_mat["Material"] != ""].copy()

for col in ["Data", "ID Obra", "Elemento", "Meio", "Material", "Notas"]:
    df_diario[col] = df_diario[col].fillna("").astype(str).str.strip()
for col in ["Dias Elemento", "Custo Elemento", "Dias Meio", "Custo Meio", "Qtd Material", "Custo Material", "Total do Dia"]:
    df_diario[col] = pd.to_numeric(df_diario[col], errors="coerce").fillna(0.0)

preco_colab = dict(zip(df_elem["Elemento"], df_elem["Valor_Dia"]))
preco_meio = dict(zip(df_meios["Meio / Equipamento"], df_meios["Valor_Dia"]))
preco_mat = dict(zip(df_mat["Material"], df_mat["Preco_Unitario"]))
unid_mat = dict
