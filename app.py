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
def normalizar_colunas(df, aliases):
    if df.empty:
        return df
    renomear = {}
    cols_lower = {str(c).strip().lower(): c for c in df.columns}
    for destino, candidatos in aliases.items():
        if destino in df.columns:
            continue
        for cand in candidatos:
            if cand.lower() in cols_lower:
                renomear[cols_lower[cand.lower()]] = destino
                break
    return df.rename(columns=renomear) if renomear else df

@st.cache_data(ttl=15)
def carregar_dados():
    resp = requests.get(st.secrets["apps_script_url"], timeout=20)
    resp.raise_for_status()
    dados = resp.json()

    def ler_aba(nome, colunas, aliases=None):
        df = pd.DataFrame(dados.get(nome, []))
        if df.empty:
            return pd.DataFrame(columns=colunas)
        if aliases:
            df = normalizar_colunas(df, aliases)
        for c in colunas:
            if c not in df.columns:
                df[c] = ""
        return df[colunas]

    df_obras = ler_aba(
        "Obras",
        ["ID Obra", "Nome da Obra", "Cliente", "Valor Adjudicado", "Total Gasto", "Saldo Restante", "Estado"],
        aliases={
            "ID Obra": ["ID", "Codigo", "Código", "Obra ID"],
            "Nome da Obra": ["Obra", "Nome", "Designacao", "Designação"],
            "Valor Adjudicado": ["Valor", "Orcamento", "Orçamento", "Adjudicado"],
        },
    )
    df_elem = ler_aba(
        "Elementos",
        ["Elemento", "Valor_Dia"],
        aliases={
            "Elemento": ["Colaborador", "Colaboradores", "Nome", "Trabalhador", "Tecnico", "Técnico"],
            "Valor_Dia": ["Valor Dia", "Valor/Dia", "Custo_Dia", "Custo Dia", "Preco", "Preço", "Valor"],
        },
    )
    df_meios = ler_aba(
        "Meios",
        ["Meio / Equipamento", "Valor_Dia"],
        aliases={
            "Meio / Equipamento": ["Viatura", "Viaturas", "Meio", "Equipamento", "Matricula", "Matrícula"],
            "Valor_Dia": ["Valor Dia", "Valor/Dia", "Custo_Dia", "Custo Dia", "Preco", "Preço", "Valor"],
        },
    )
    df_mat = ler_aba(
        "Materiais",
        ["Material", "Unidade", "Preco_Unitario"],
        aliases={
            "Material": ["Nome", "Artigo", "Descricao", "Descrição", "Produto"],
            "Unidade": ["Un", "Un.", "Medida"],
            "Preco_Unitario": ["Preco Unitario", "Preço Unitário", "Preco", "Preço", "Valor", "Valor_Unitario"],
        },
    )
    df_diario = ler_aba(
        "Registos_Diarios",
        [
            "ID_Registo", "Data", "ID Obra", "Elemento", "Dias Elemento", "Custo Elemento",
            "Meio", "Dias Meio", "Custo Meio", "Material", "Qtd Material", "Custo Material",
            "Total do Dia", "Notas",
        ],
        aliases={
            "Elemento": ["Colaborador"],
            "Meio": ["Viatura"],
        },
    )
    return df_obras, df_elem, df_meios, df_mat, df_diario

def gravar_aba(nome, df):
    df_clean = df.fillna("")
    rows = [df_clean.columns.tolist()] + df_clean.values.tolist()
    resp = requests.post(
        st.secrets["apps_script_url"],
        data=json.dumps({"sheet": nome, "rows": rows}),
        headers={"Content-Type": "text/plain;charset=utf-8"},
        timeout=20,
    )
    resp.raise_for_status()

def atualizar_saldos_obras(df_obras, df_diario):
    df_o = df_obras.copy()
    df_o["ID Obra"] = df_o["ID Obra"].fillna("").astype(str).str.strip()
    df_o["Valor Adjudicado"] = pd.to_numeric(df_o["Valor Adjudicado"], errors="coerce").fillna(0.0)

    if not df_diario.empty:
        df_d = df_diario.copy()
        df_d["ID Obra"] = df_d["ID Obra"].fillna("").astype(str).str.strip()
        df_d["Total do Dia"] = pd.to_numeric(df_d["Total do Dia"], errors="coerce").fillna(0.0)
        gastos_por_obra = df_d.groupby("ID Obra")["Total do Dia"].sum().to_dict()
    else:
        gastos_por_obra = {}

    df_o["Total Gasto"] = df_o["ID Obra"].map(gastos_por_obra).fillna(0.0)
    df_o["Saldo Restante"] = df_o["Valor Adjudicado"] - df_o["Total Gasto"]
    gravar_aba("Obras", df_o)
    return df_o

def parse_datas(serie):
    s_str = serie.fillna("").astype(str).str.strip()
    is_iso = s_str.str.match(r"^\d{4}-\d{2}-\d{2}")
    res = pd.Series(pd.NaT, index=s_str.index, dtype="datetime64[ns]")
    if is_iso.any():
        dt_iso = pd.to_datetime(s_str[is_iso], format="mixed", errors="coerce", utc=True)
        res.loc[is_iso] = dt_iso.dt.tz_localize(None).dt.round("D")
    if (~is_iso).any():
        dt_pt = pd.to_datetime(s_str[~is_iso], format="mixed", dayfirst=True, errors="coerce")
        res.loc[~is_iso] = dt_pt.dt.round("D")
    return res

def formatar_data_pt(serie):
    dt = parse_datas(serie)
    return dt.dt.strftime("%d/%m/%Y").fillna(serie.astype(str))

# ==========================================
# CARREGAMENTO E LIMPEZA DE TIPOS
# ==========================================
try:
    df_obras, df_elem, df_meios, df_mat, df_diario = carregar_dados()
except Exception as e:
    st.error(f"Erro ao ligar à folha Google: {e}")
    st.stop()

for col in ["ID Obra", "Nome da Obra", "Cliente", "Estado"]:
    df_obras[col] = df_obras[col].fillna("").astype(str).str.strip()
for col in ["Valor Adjudicado", "Total Gasto", "Saldo Restante"]:
    df_obras[col] = pd.to_numeric(df_obras[col], errors="coerce").fillna(0.0)
df_obras = df_obras[df_obras["ID Obra"] != ""].copy()

df_elem["Elemento"] = df_elem["Elemento"].fillna("").astype(str).str.strip()
df_elem["Valor_Dia"] = pd.to_numeric(df_elem["Valor_Dia"], errors="coerce").fillna(0.0)
df_elem = df_elem[df_elem["Elemento"] != ""].copy()

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

custos_elem = dict(zip(df_elem["Elemento"], df_elem["Valor_Dia"]))
custos_meios = dict(zip(df_meios["Meio / Equipamento"], df_meios["Valor_Dia"]))
custos_mat = dict(zip(df_mat["Material"], df_mat["Preco_Unitario"]))
unidades_mat = dict(zip(df_mat["Material"], df_mat["Unidade"]))

st.title("🏗️ Gestão de Obras")

if st.session_state["msg_sucesso"]:
    st.success(st.session_state["msg_sucesso"])
    st.session_state["msg_sucesso"] = ""

secao = st.radio(
    "Navegação",
    ["📝 Diário", "👷 Presenças", "⚙️ Tabelas", "📄 PDF"],
    horizontal=True,
    label_visibility="collapsed",
)
st.divider()

# ==========================================
# SECÇÃO 1: REGISTO DIÁRIO (SEM VALORES FINANCEIROS VISÍVEIS)
# ==========================================
if secao == "📝 Diário":
    rid = st.session_state["reset_id"]
    obras_ativas = df_obras[df_obras["Estado"].str.lower() != "concluída"]["ID Obra"].tolist()
    todas_obras = df_obras["ID Obra"].tolist()
    opcoes_obra = obras_ativas if obras_ativas else todas_obras

    if opcoes_obra:
        obra_reg = st.selectbox(
            "🏢 Selecionar Obra",
            options=opcoes_obra,
            format_func=lambda x: f"{x} — {df_obras.loc[df_obras['ID Obra']==x, 'Nome da Obra'].values[0]}",
            key="reg_obra",
        )
    else:
        st.warning("Sem obras ativas. Adiciona obras em ⚙️ Tabelas.")
        obra_reg = None

    data_reg = st.date_input("📅 Data", value=date.today(), key="reg_data")

    # 1. COLABORADORES -> ALIMENTA PRESENÇAS
    if not custos_elem:
        st.info("Ainda não tens colaboradores carregados. Adiciona-os em ⚙️ Tabelas.")
    colabs_sel = st.multiselect(
        "👷 Colaboradores em Obra (regista presença)",
        options=list(custos_elem.keys()),
        placeholder="Selecionar um ou mais colaboradores...",
        key=f"reg_colabs_{rid}",
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
            key=f"dias_{c_nome}_{rid}",
        )

    # 2. VIATURAS / MEIOS (MÚLTIPLA ESCOLHA)
    meios_sel = st.multiselect(
        "🚚 Viaturas / Meios",
        options=list(custos_meios.keys()),
        placeholder="Selecionar uma ou mais viaturas...",
        key=f"reg_meios_{rid}",
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
            key=f"dias_meio_{m_nome}_{rid}",
        )

    # 3. MATERIAIS (MÚLTIPLA ESCOLHA)
    mats_sel = st.multiselect(
        "📦 Material Aplicado",
        options=list(custos_mat.keys()),
        format_func=lambda m: f"{m} ({unidades_mat.get(m, '')})" if unidades_mat.get(m, "") else m,
        placeholder="Selecionar um ou mais materiais...",
        key=f"reg_mats_{rid}",
    )
    qtd_por_mat = {}
    for mat_nome in mats_sel:
        cmat1, cmat2 = st.columns([2, 1])
        un = unidades_mat.get(mat_nome, "")
        label_mat = f"**{mat_nome}** ({un})" if un else f"**{mat_nome}**"
        cmat1.markdown(label_mat)
        qtd_por_mat[mat_nome] = cmat2.number_input(
            f"Qtd ({mat_nome})",
            min_value=0.0,
            value=1.0,
            step=1.0,
            label_visibility="collapsed",
            key=f"qtd_mat_{mat_nome}_{rid}",
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
            data_iso = data_reg.strftime("%Y-%m-%d")

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

                novas_linhas.append(
                    {
                        "ID_Registo": prox_id + i,
                        "Data": data_iso,
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
                        "Notas": notas if i == 0 else "",
                    }
                )

            df_diario_atualizado = pd.concat([df_diario, pd.DataFrame(novas_linhas)], ignore_index=True)
            gravar_aba("Registos_Diarios", df_diario_atualizado)
            atualizar_saldos_obras(df_obras, df_diario_atualizado)
            st.cache_data.clear()
            st.session_state["reset_id"] += 1
            st.session_state["msg_sucesso"] = f"Gravado ({len(lista_colabs)} presença(s) registada(s))!"
            st.rerun()

    if obra_reg:
        st.divider()
        st.subheader("Histórico da Obra")
        df_hist_full = df_diario[df_diario["ID Obra"] == obra_reg].copy()
        df_hist_full["Data"] = formatar_data_pt(df_hist_full["Data"])
        cols_visiveis = ["ID_Registo", "Data", "Elemento", "Dias Elemento", "Meio", "Dias Meio", "Material", "Qtd Material", "Notas"]
        edited_hist = st.data_editor(
            df_hist_full[cols_visiveis],
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            disabled=["ID_Registo"],
            key="editor_hist",
        )

        if st.button("Atualizar Histórico / Apagar Linhas", use_container_width=True):
            ed = edited_hist.copy()
            dt_ed = parse_datas(ed["Data"])
            ed["Data"] = dt_ed.dt.strftime("%Y-%m-%d").fillna(ed["Data"].astype(str))
            ed["ID Obra"] = obra_reg
            ed["Dias Elemento"] = pd.to_numeric(ed["Dias Elemento"], errors="coerce").fillna(0.0)
            ed["Dias Meio"] = pd.to_numeric(ed["Dias Meio"], errors="coerce").fillna(0.0)
            ed["Qtd Material"] = pd.to_numeric(ed["Qtd Material"], errors="coerce").fillna(0.0)

            ed["Custo Elemento"] = ed.apply(lambda r: custos_elem.get(str(r["Elemento"]), 0.0) * r["Dias Elemento"], axis=1)
            ed["Custo Meio"] = ed.apply(lambda r: custos_meios.get(str(r["Meio"]), 0.0) * r["Dias Meio"], axis=1)
            ed["Custo Material"] = ed.apply(lambda r: custos_mat.get(str(r["Material"]), 0.0) * r["Qtd Material"], axis=1)
            ed["Total do Dia"] = ed["Custo Elemento"] + ed["Custo Meio"] + ed["Custo Material"]

            cols_ordem = df_diario.columns.tolist()
            df_outras = df_diario[df_diario["ID Obra"] != obra_reg]
            df_final = pd.concat([df_outras, ed[cols_ordem]], ignore_index=True)
            gravar_aba("Registos_Diarios", df_final)
            atualizar_saldos_obras(df_obras, df_final)
            st.cache_data.clear()
            st.session_state["msg_sucesso"] = "Histórico atualizado!"
            st.rerun()

# ==========================================
# SECÇÃO 2: MAPA DE PRESENÇAS
# ==========================================
elif secao == "👷 Presenças":
    def gerar_pdf_ponto(df_resumo, df_detalhe, p_ini, p_fim):
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 15)
        pdf.cell(0, 10, "MAPA DE PRESENCAS DE COLABORADORES", ln=True, align="C")

        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"Periodo: {p_ini.strftime('%d/%m/%Y')} a {p_fim.strftime('%d/%m/%Y')}", ln=True, align="C")
        pdf.ln(5)

        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(75, 7, "Colaborador", 1)
        pdf.cell(35, 7, "Total Dias", 1, align="C")
        pdf.cell(80, 7, "Obras", 1)
        pdf.ln()

        pdf.set_font("Helvetica", "", 8)
        for _, r in df_resumo.iterrows():
            pdf.cell(75, 6, str(r["Colaborador"])[:40].encode("latin-1", "replace").decode("latin-1"), 1)
            pdf.cell(35, 6, f"{r['Total Dias']:.1f}", 1, align="C")
            pdf.cell(80, 6, str(r["Obras"])[:44].encode("latin-1", "replace").decode("latin-1"), 1)
            pdf.ln()

        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 7, "Detalhe Diario de Presencas", ln=True)

        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(24, 6, "Data", 1)
        pdf.cell(55, 6, "Colaborador", 1)
        pdf.cell(30, 6, "Obra", 1)
        pdf.cell(18, 6, "Dias", 1, align="C")
        pdf.cell(63, 6, "Notas", 1)
        pdf.ln()

        pdf.set_font("Helvetica", "", 7)
        for _, r in df_detalhe.iterrows():
            pdf.cell(24, 6, str(r["Data_Fmt"]), 1)
            pdf.cell(55, 6, str(r["Elemento"])[:30].encode("latin-1", "replace").decode("latin-1"), 1)
            pdf.cell(30, 6, str(r["ID Obra"])[:16].encode("latin-1", "replace").decode("latin-1"), 1)
            pdf.cell(18, 6, f"{r['Dias Elemento']:.1f}", 1, align="C")
            pdf.cell(63, 6, str(r["Notas"])[:35].encode("latin-1", "replace").decode("latin-1"), 1)
            pdf.ln()

        return bytes(pdf.output())

    st.subheader("👷 Mapa de Presenças")

    df_pt_all = df_diario[df_diario["Elemento"] != ""].copy()
    df_pt_all["Data_dt"] = parse_datas(df_pt_all["Data"])
    df_pt_all = df_pt_
