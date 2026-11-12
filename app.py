import streamlit as st
import pandas as pd
from datetime import date
import requests
import json
from fpdf import FPDF

st.set_page_config(page_title="Gestão de Obras", page_icon="🏗️", layout="centered")

if "reset_id" not in st.session_state:
    st.session_state["reset_id"] = 0

if "msg_sucesso" not in st.session_state:
    st.session_state["msg_sucesso"] = ""

# ==========================================
# LIGAÇÃO AO GOOGLE SHEETS VIA APPS SCRIPT
# ==========================================
@st.cache_data(ttl=15)
def carregar_dados():
    resp = requests.get(st.secrets["apps_script_url"], timeout=20)
    resp.raise_for_status()
    dados = resp.json()

    def ler_aba(nome, colunas):
        df = pd.DataFrame(dados.get(nome, []))
        if df.empty:
            return pd.DataFrame(columns=colunas)
        for c in colunas:
            if c not in df.columns:
                df[c] = ""
        return df[colunas]

    df_obras = ler_aba("Obras", ["ID Obra", "Nome da Obra", "Cliente", "Valor Adjudicado", "Total Gasto", "Saldo Restante", "Estado"])
    df_elem = ler_aba("Elementos", ["Elemento", "Valor_Dia"])
    df_meios = ler_aba("Meios", ["Meio / Equipamento", "Valor_Dia"])
    df_mat = ler_aba("Materiais", ["Material", "Unidade", "Preco_Unitario"])
    df_diario = ler_aba("Registos_Diarios", [
        "ID_Registo", "Data", "ID Obra", "Elemento", "Dias Elemento", "Custo Elemento",
        "Meio", "Dias Meio", "Custo Meio", "Material", "Qtd Material", "Custo Material",
        "Total do Dia", "Notas"
    ])
    return df_obras, df_elem, df_meios, df_mat, df_diario

def gravar_aba(nome, df):
    df_clean = df.fillna("")
    rows = [df_clean.columns.tolist()] + df_clean.values.tolist()
    resp = requests.post(
        st.secrets["apps_script_url"],
        data=json.dumps({"sheet": nome, "rows": rows}),
        headers={"Content-Type": "text/plain;charset=utf-8"},
        timeout=20
    )
    resp.raise_for_status()

def atualizar_saldos_obras(df_obras, df_diario):
    df_o = df_obras.copy()
    df_o["Valor Adjudicado"] = pd.to_numeric(df_o["Valor Adjudicado"], errors="coerce").fillna(0.0)

    if not df_diario.empty:
        df_d = df_diario.copy()
        df_d["Total do Dia"] = pd.to_numeric(df_d["Total do Dia"], errors="coerce").fillna(0.0)
        gastos_por_obra = df_d.groupby("ID Obra")["Total do Dia"].sum().to_dict()
    else:
        gastos_por_obra = {}

    df_o["Total Gasto"] = df_o["ID Obra"].map(gastos_por_obra).fillna(0.0)
    df_o["Saldo Restante"] = df_o["Valor Adjudicado"] - df_o["Total Gasto"]
    gravar_aba("Obras", df_o)
    return df_o

def parse_datas(serie):
    return pd.to_datetime(serie, format="mixed", dayfirst=True, errors="coerce", utc=True).dt.tz_localize(None)

# ==========================================
# CARREGAMENTO INICIAL
# ==========================================
try:
    df_obras, df_elem, df_meios, df_mat, df_diario = carregar_dados()
except Exception as e:
    st.error(f"Erro ao ligar à folha Google: {e}")
    st.stop()

for col in ["Valor Adjudicado", "Total Gasto", "Saldo Restante"]:
    df_obras[col] = pd.to_numeric(df_obras[col], errors="coerce").fillna(0.0)

for col in ["Dias Elemento", "Custo Elemento", "Dias Meio", "Custo Meio", "Qtd Material", "Custo Material", "Total do Dia"]:
    df_diario[col] = pd.to_numeric(df_diario[col], errors="coerce").fillna(0.0)

df_elem = df_elem[df_elem["Elemento"].astype(str).str.strip() != ""].copy()
df_meios = df_meios[df_meios["Meio / Equipamento"].astype(str).str.strip() != ""].copy()
df_mat = df_mat[df_mat["Material"].astype(str).str.strip() != ""].copy()

custos_elem = dict(zip(df_elem["Elemento"], pd.to_numeric(df_elem["Valor_Dia"], errors="coerce").fillna(0.0)))
custos_meios = dict(zip(df_meios["Meio / Equipamento"], pd.to_numeric(df_meios["Valor_Dia"], errors="coerce").fillna(0.0)))
custos_mat = dict(zip(df_mat["Material"], pd.to_numeric(df_mat["Preco_Unitario"], errors="coerce").fillna(0.0)))
unidades_mat = dict(zip(df_mat["Material"], df_mat["Unidade"].astype(str)))

st.title("🏗️ Gestão de Obras")

if st.session_state["msg_sucesso"]:
    st.success(st.session_state["msg_sucesso"])
    st.session_state["msg_sucesso"] = ""

aba_registo, aba_ponto, aba_config, aba_pdf = st.tabs(["📝 Registo Diário", "👷 Presenças", "⚙️ Tabelas", "📄 PDF"])

# ==========================================
# ABA 1: REGISTO DIÁRIO (SEM VALORES FINANCEIROS VISÍVEIS)
# ==========================================
with aba_registo:
    rid = st.session_state["reset_id"]
    obras_ativas = df_obras[df_obras["Estado"].astype(str).str.lower() != "concluída"]["ID Obra"].tolist()
    todas_obras = df_obras["ID Obra"].tolist()
    opcoes_obra = obras_ativas if obras_ativas else todas_obras

    if opcoes_obra:
        obra_reg = st.selectbox(
            "🏢 Selecionar Obra",
            options=opcoes_obra,
            format_func=lambda x: f"{x} — {df_obras.loc[df_obras['ID Obra']==x, 'Nome da Obra'].values[0]}",
            key="reg_obra"
        )
    else:
        st.warning("Sem obras ativas. Adiciona obras no separador Tabelas.")
        obra_reg = None

    data_reg = st.date_input("📅 Data", value=date.today(), key="reg_data")

    st.divider()

    # 1. COLABORADORES (MÚLTIPLA ESCOLHA -> ALIMENTA PRESENÇAS)
    colabs_sel = st.multiselect(
        "👷 Colaboradores em Obra",
        options=list(custos_elem.keys()),
        placeholder="Selecionar um ou mais colaboradores...",
        key=f"reg_colabs_{rid}"
    )
    dias_por_colab = {}
    for c_nome in colabs_sel:
        ce1, ce2 = st.columns([2, 1])
        ce1.markdown(f"**{c_nome}**")
        dias_por_colab[c_nome] = ce2.number_input(
            f"Dias ({c_nome})",
            min_value=0.0,
            value=1.0,
            step=0.5,
            label_visibility="collapsed",
            key=f"dias_{c_nome}_{rid}"
        )

    # 2. VIATURAS / MEIOS (MÚLTIPLA ESCOLHA)
    meios_sel = st.multiselect(
        "🚚 Viaturas / Meios",
        options=list(custos_meios.keys()),
        placeholder="Selecionar uma ou mais viaturas...",
        key=f"reg_meios_{rid}"
    )
    dias_por_meio = {}
    for m_nome in meios_sel:
        cm1, cm2 = st.columns([2, 1])
        cm1.markdown(f"**{m_nome}**")
        dias_por_meio[m_nome] = cm2.number_input(
            f"Dias ({m_nome})",
            min_value=0.0,
            value=1.0,
            step=0.5,
            label_visibility="collapsed",
            key=f"dias_meio_{m_nome}_{rid}"
        )

    # 3. MATERIAIS (MÚLTIPLA ESCOLHA)
    mats_sel = st.multiselect(
        "📦 Material Aplicado",
        options=list(custos_mat.keys()),
        format_func=lambda m: f"{m} ({unidades_mat.get(m, '')})" if unidades_mat.get(m, "").strip() else m,
        placeholder="Selecionar um ou mais materiais...",
        key=f"reg_mats_{rid}"
    )
    qtd_por_mat = {}
    for mat_nome in mats_sel:
        cmat1, cmat2 = st.columns([2, 1])
        un = unidades_mat.get(mat_nome, "").strip()
        label_mat = f"**{mat_nome}** ({un})" if un else f"**{mat_nome}**"
        cmat1.markdown(label_mat)
        qtd_por_mat[mat_nome] = cmat2.number_input(
            f"Qtd ({mat_nome})",
            min_value=0.0,
            value=1.0,
            step=1.0,
            label_visibility="collapsed",
            key=f"qtd_mat_{mat_nome}_{rid}"
        )

    notas = st.text_input("📝 Notas / Trabalhos realizados", key=f"reg_notas_{rid}")

    if st.button("💾 Gravar Registo Diário", type="primary", use_container_width=True):
        if not obra_reg:
            st.error("Seleciona uma obra primeiro.")
        elif not colabs_sel and not meios_sel and not mats_sel and not notas.strip():
            st.error("Preenche pelo menos um colaborador, viatura, material ou nota.")
        else:
            max_id = pd.to_numeric(df_diario["ID_Registo"], errors="coerce").max()
            prox_id = int(0 if pd.isna(max_id) else max_id) + 1
            data_str = data_reg.strftime("%d/%m/%Y")

            lista_colabs = [(c, dias_por_colab[c]) for c in colabs_sel if dias_por_colab[c] > 0]
            lista_meios = [(m, dias_por_meio[m]) for m in meios_sel if dias_por_meio[m] > 0]
            lista_mats = [(mt, qtd_por_mat[mt]) for mt in mats_sel if qtd_por_mat[mt] > 0]

            num_linhas = max(len(lista_colabs), len(lista_meios), len(lista_mats), 1)
            novas_linhas = []

            for i in range(num_linhas):
                el_nome, el_dias = lista_colabs[i] if i < len(lista_colabs) else ("", 0.0)
                el_custo = custos_elem.get(el_nome, 0.0) * el_dias if el_nome else 0.0

                me_nome, me_dias = lista_meios[i] if i < len(lista_meios) else ("", 0.0)
                me_custo = custos_meios.get(me_nome, 0.0) * me_dias if me_nome else 0.0

                mt_nome, mt_qtd = lista_mats[i] if i < len(lista_mats) else ("", 0.0)
                mt_custo = custos_mat.get(mt_nome, 0.0) * mt_qtd if mt_nome else 0.0

                novas_linhas.append({
                    "ID_Registo": prox_id + i,
                    "Data": data_str,
                    "ID Obra": obra_reg,
                    "Elemento": el_nome,
                    "Dias Elemento": el_dias,
                    "Custo Elemento": el_custo,
                    "Meio": me_nome,
                    "Dias Meio": me_dias,
                    "Custo Meio": me_custo,
                    "Material": mt_nome,
                    "Qtd Material": mt_qtd,
                    "Custo Material": mt_custo,
                    "Total do Dia": el_custo + me_custo + mt_custo,
                    "Notas": notas if i == 0 else ""
                })

            df_diario_atualizado = pd.concat([df_diario, pd.DataFrame(novas_linhas)], ignore_index=True)
            gravar_aba("Registos_Diarios", df_diario_atualizado)
            atualizar_saldos_obras(df_obras, df_diario_atualizado)
            st.cache_data.clear()
            st.session_state["reset_id"] += 1
            st.session_state["msg_sucesso"] = "Registo e presenças gravados com sucesso!"
            st.rerun()

    if obra_reg:
        st.divider()
        st.subheader("Histórico da Obra")
        df_hist_full = df_diario
