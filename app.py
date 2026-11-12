import streamlit as st
import pandas as pd
from datetime import date
import requests
import json
from fpdf import FPDF

st.set_page_config(page_title="Gestão de Obras", page_icon="🏗️", layout="centered")
st.session_state.setdefault("reset_id", 0)
st.session_state.setdefault("msg_sucesso", "")

def normalizar_colunas(df, aliases):
    if df.empty:
        return df
    cols_lower = {str(c).strip().lower(): c for c in df.columns}
    renomear = {}
    for dest, cands in aliases.items():
        if dest not in df.columns:
            for c in cands:
                if c.lower() in cols_lower:
                    renomear[cols_lower[c.lower()]] = dest
                    break
    return df.rename(columns=renomear) if renomear else df

@st.cache_data(ttl=15)
def carregar_dados():
    resp = requests.get(st.secrets["apps_script_url"], timeout=20)
    resp.raise_for_status()
    dados = resp.json()

    def ler(nome, cols, aliases=None):
        df = pd.DataFrame(dados.get(nome, []))
        if df.empty:
            return pd.DataFrame(columns=cols)
        if aliases:
            df = normalizar_colunas(df, aliases)
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        return df[cols]

    obras = ler("Obras", ["ID Obra", "Nome da Obra", "Cliente", "Valor Adjudicado", "Total Gasto", "Saldo Restante", "Estado"],
                {"ID Obra": ["ID", "Codigo", "Código"], "Nome da Obra": ["Obra", "Nome", "Designacao", "Designação"],
                 "Valor Adjudicado": ["Valor", "Orcamento", "Orçamento", "Adjudicado"]})
    elem = ler("Elementos", ["Elemento", "Valor_Dia"],
               {"Elemento": ["Colaborador", "Colaboradores", "Nome", "Trabalhador"],
                "Valor_Dia": ["Valor Dia", "Valor/Dia", "Custo_Dia", "Preco", "Preço", "Valor"]})
    meios = ler("Meios", ["Meio / Equipamento", "Valor_Dia"],
                {"Meio / Equipamento": ["Viatura", "Viaturas", "Meio", "Equipamento", "Matricula", "Matrícula"],
                 "Valor_Dia": ["Valor Dia", "Valor/Dia", "Custo_Dia", "Preco", "Preço", "Valor"]})
    mat = ler("Materiais", ["Material", "Unidade", "Preco_Unitario"],
              {"Material": ["Nome", "Artigo", "Descricao", "Descrição"], "Unidade": ["Un", "Un."],
               "Preco_Unitario": ["Preco Unitario", "Preço Unitário", "Preco", "Preço", "Valor"]})
    diario = ler("Registos_Diarios", ["ID_Registo", "Data", "ID Obra", "Elemento", "Dias Elemento", "Custo Elemento",
                                      "Meio", "Dias Meio", "Custo Meio", "Material", "Qtd Material", "Custo Material",
                                      "Total do Dia", "Notas"],
                 {"Elemento": ["Colaborador"], "Meio": ["Viatura"]})
    return obras, elem, meios, mat, diario

def gravar_aba(nome, df):
    df_clean = df.fillna("")
    rows = [df_clean.columns.tolist()] + df_clean.values.tolist()
    r = requests.post(st.secrets["apps_script_url"], data=json.dumps({"sheet": nome, "rows": rows}),
                      headers={"Content-Type": "text/plain;charset=utf-8"}, timeout=20)
    r.raise_for_status()

def atualizar_saldos(df_o, df_d):
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
    gravar_aba("Obras", o)

def parse_datas(serie):
    s = serie.fillna("").astype(str).str.strip()
    is_iso = s.str.match(r"^\d{4}-\d{2}-\d{2}")
    res = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    if is_iso.any():
        res.loc[is_iso] = pd.to_datetime(s[is_iso], format="mixed", errors="coerce", utc=True).dt.tz_localize(None).dt.round("D")
    if (~is_iso).any():
        res.loc[~is_iso] = pd.to_datetime(s[~is_iso], format="mixed", dayfirst=True, errors="coerce").dt.round("D")
    return res

try:
    df_obras, df_elem, df_meios, df_mat, df_diario = carregar_dados()
except Exception as e:
    st.error(f"Erro ao ligar à folha Google: {e}")
    st.stop()

for c in ["ID Obra", "Nome da Obra", "Cliente", "Estado"]:
    df_obras[c] = df_obras[c].fillna("").astype(str).str.strip()
for c in ["Valor Adjudicado", "Total Gasto", "Saldo Restante"]:
    df_obras[c] = pd.to_numeric(df_obras[c], errors="coerce").fillna(0.0)
df_obras = df_obras[df_obras["ID Obra"] != ""].copy()

df_elem["Elemento"] = df_elem["Elemento"].fillna("").astype(str).str.strip()
df_elem["Valor_Dia"] = pd.to_numeric(df_elem["Valor_Dia"], errors="coerce").fillna(0.0)
df_elem = df_elem[df_elem["Elemento"] != ""].copy()

df_meios["Meio / Equipamento"] = df_meios["Meio / Equipamento"].fillna("").astype(str).str.strip()
df_meios["Valor_Dia"] = pd.to_numeric(df_meios["Valor_Dia"], errors="coerce").fillna(0.0)
df_meios = df_meios[df_meios["Meio / Equipamento"] != ""].copy()

for c in ["Material", "Unidade"]:
    df_mat[c] = df_mat[c].fillna("").astype(str).str.strip()
df_mat["Preco_Unitario"] = pd.to_numeric(df_mat["Preco_Unitario"], errors="coerce").fillna(0.0)
df_mat = df_mat[df_mat["Material"] != ""].copy()

for c in ["Data", "ID Obra", "Elemento", "Meio", "Material", "Notas"]:
    df_diario[c] = df_diario[c].fillna("").astype(str).str.strip()
for c in ["Dias Elemento", "Custo Elemento", "Dias Meio", "Custo Meio", "Qtd Material", "Custo Material", "Total do Dia"]:
    df_diario[c] = pd.to_numeric(df_diario[c], errors="coerce").fillna(0.0)

custos_elem = dict(zip(df_elem["Elemento"], df_elem["Valor_Dia"]))
custos_meios = dict(zip(df_meios["Meio / Equipamento"], df_meios["Valor_Dia"]))
custos_mat = dict(zip(df_mat["Material"], df_mat["Preco_Unitario"]))
unidades_mat = dict(zip(df_mat["Material"], df_mat["Unidade"]))

st.title("🏗️ Gestão de Obras")
if st.session_state["msg_sucesso"]:
    st.success(st.session_state["msg_sucesso"])
    st.session_state["msg_sucesso"] = ""

secao = st.radio("Menu", ["📝 Diário", "👷 Presenças", "⚙️ Tabelas", "📄 PDF"], horizontal=True, label_visibility="collapsed")
st.divider()

# ==========================================
# 1. REGISTO DIÁRIO
# ==========================================
if secao == "📝 Diário":
    rid = st.session_state["reset_id"]
    ativas = df_obras[df_obras["Estado"].str.lower() != "concluída"]["ID Obra"].tolist()
    opcoes_obra = ativas if ativas else df_obras["ID Obra"].tolist()

    obra_reg = st.selectbox("🏢 Obra", opcoes_obra,
                            format_func=lambda x: f"{x} — {df_obras.loc[df_obras['ID Obra']==x, 'Nome da Obra'].values[0]}") if opcoes_obra else None
    if not obra_reg:
        st.warning("Adiciona obras em ⚙️ Tabelas.")

    data_reg = st.date_input("📅 Data", value=date.today())

    colabs_sel = st.multiselect("👷 Colaboradores em Obra (regista presença)", list(custos_elem.keys()),
                                placeholder="Selecionar colaboradores...", key=f"c_{rid}")
    dias_colab = {}
    for nome in colabs_sel:
        c1, c2 = st.columns([2, 1])
        c1.markdown(f"**{nome}**")
        dias_colab[nome] = c2.number_input("Dias", 0.0, value=1.0, step=0.5, label_visibility="collapsed", key=f"dc_{nome}_{rid}")

    meios_sel = st.multiselect("🚚 Viaturas / Meios", list(custos_meios.keys()),
                               placeholder="Selecionar viaturas...", key=f"m_{rid}")
    dias_meio = {}
    for nome in meios_sel:
        c1, c2 = st.columns([2, 1])
        c1.markdown(f"**{nome}**")
        dias_meio[nome] = c2.number_input("Dias", 0.0, value=1.0, step=0.5, label_visibility="collapsed", key=f"dm_{nome}_{rid}")

    mats_sel = st.multiselect("📦 Material Aplicado", list(custos_mat.keys()),
                              format_func=lambda m: f"{m} ({unidades_mat[m]})" if unidades_mat.get(m) else m,
                              placeholder="Selecionar materiais...", key=f"mt_{rid}")
    qtd_mat = {}
    for nome in mats_sel:
        c1, c2 = st.columns([2, 1])
        un = unidades_mat.get(nome, "")
        c1.markdown(f"**{nome}** ({un})" if un else f"**{nome}**")
        qtd_mat[nome] =
