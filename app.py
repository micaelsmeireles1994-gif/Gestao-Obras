import streamlit as st
import pandas as pd
from datetime import date
import requests
import json
from fpdf import FPDF

st.set_page_config(page_title="Gestão de Obras", page_icon="🏗️", layout="centered")

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

aba_registo, aba_ponto, aba_config, aba_pdf = st.tabs(["📝 Registo Diário", "👷 Presenças", "⚙️ Tabelas", "📄 PDF"])

# ==========================================
# ABA 1: REGISTO DIÁRIO (SEM VALORES FINANCEIROS VISÍVEIS)
# ==========================================
with aba_registo:
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
        key="reg_colabs"
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
            key=f"dias_{c_nome}"
        )

    # 2. VIATURAS / MEIOS (MÚLTIPLA ESCOLHA)
    meios_sel = st.multiselect(
        "🚚 Viaturas / Meios",
        options=list(custos_meios.keys()),
        placeholder="Selecionar uma ou mais viaturas...",
        key="reg_meios"
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
            key=f"dias_meio_{m_nome}"
        )

    # 3. MATERIAIS (MÚLTIPLA ESCOLHA)
    mats_sel = st.multiselect(
        "📦 Material Aplicado",
        options=list(custos_mat.keys()),
        format_func=lambda m: f"{m} ({unidades_mat.get(m, '')})" if unidades_mat.get(m, "").strip() else m,
        placeholder="Selecionar um ou mais materiais...",
        key="reg_mats"
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
            key=f"qtd_mat_{mat_nome}"
        )

    notas = st.text_input("📝 Notas / Trabalhos realizados", key="reg_notas")

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
            st.success("Registo e presenças gravados com sucesso!")
            st.rerun()

    if obra_reg:
        st.divider()
        st.subheader("Histórico da Obra")
        df_hist_full = df_diario[df_diario["ID Obra"] == obra_reg].copy()
        cols_visiveis = ["ID_Registo", "Data", "Elemento", "Dias Elemento", "Meio", "Dias Meio", "Material", "Qtd Material", "Notas"]
        edited_hist = st.data_editor(
            df_hist_full[cols_visiveis],
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            disabled=["ID_Registo"],
            key="editor_hist"
        )

        if st.button("Atualizar Histórico / Apagar Linhas", use_container_width=True):
            ed = edited_hist.copy()
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
            st.success("Histórico atualizado!")
            st.rerun()

# ==========================================
# ABA 2: MAPA DE PRESENÇAS (PONTO)
# ==========================================
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

with aba_ponto:
    st.subheader("👷 Registo de Presenças")
    cp1, cp2 = st.columns(2)
    p_ini = cp1.date_input("De", value=date.today().replace(day=1), key="ponto_ini")
    p_fim = cp2.date_input("Até", value=date.today(), key="ponto_fim")

    df_pt = df_diario[df_diario["Elemento"].astype(str).str.strip() != ""].copy()
    df_pt["Data_dt"] = parse_datas(df_pt["Data"])
    df_pt = df_pt[
        df_pt["Data_dt"].notna()
        & (df_pt["Data_dt"] >= pd.Timestamp(p_ini))
        & (df_pt["Data_dt"] <= pd.Timestamp(p_fim))
    ].sort_values(["Elemento", "Data_dt"])

    colabs_disp = sorted(df_pt["Elemento"].unique().tolist())
    filtro_colab = st.selectbox("Colaborador", ["Todos"] + colabs_disp, key="ponto_colab")
    if filtro_colab != "Todos":
        df_pt = df_pt[df_pt["Elemento"] == filtro_colab]

    if not df_pt.empty:
        df_pt["Data_Fmt"] = df_pt["Data_dt"].dt.strftime("%d/%m/%Y")
        resumo_pt = (
            df_pt.groupby("Elemento", as_index=False)
            .agg(
                **{
                    "Total Dias": ("Dias Elemento", "sum"),
                    "Obras": ("ID Obra", lambda s: ", ".join(sorted(set(s.astype(str)))))
                }
            )
            .rename(columns={"Elemento": "Colaborador"})
        )
        st.dataframe(resumo_pt, use_container_width=True, hide_index=True)

        with st.expander("Ver presenças dia a dia"):
            st.dataframe(
                df_pt[["Data_Fmt", "Elemento", "ID Obra", "Dias Elemento", "Notas"]].rename(
                    columns={"Data_Fmt": "Data", "Elemento": "Colaborador", "Dias Elemento": "Dias"}
                ),
                use_container_width=True,
                hide_index=True
            )

        pdf_ponto_bytes = gerar_pdf_ponto(resumo_pt, df_pt, p_ini, p_fim)
        st.download_button(
            label="📥 Descarregar Mapa de Presenças (PDF)",
            data=pdf_ponto_bytes,
            file_name=f"Presencas_{p_ini}_{p_fim}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True
        )
    else:
        st.info("Sem presenças registadas nas datas selecionadas.")

# ==========================================
# ABA 3: TABELAS (OBRAS, COLABORADORES, VIATURAS, MATERIAIS)
# ==========================================
with aba_config:
    st.subheader("🏢 Obras Atribuídas")
    st.caption("Para fechar uma obra, altera o Estado para 'Concluída'.")
    ed_obras = st.data_editor(
        df_obras[["ID Obra", "Nome da Obra", "Cliente", "Valor Adjudicado", "Estado"]],
        num_rows="dynamic",
        use_container_width=True,
        key="ed_obras"
    )

    st.subheader("👷 Colaboradores (Valor/Dia)")
    ed_elem = st.data_editor(df_elem, num_rows="dynamic", use_container_width=True, key="ed_elem")

    st.subheader("🚚 Viaturas / Meios (Valor/Dia)")
    ed_meios = st.data_editor(df_meios, num_rows="dynamic", use_container_width=True, key="ed_meios")

    st.subheader("📦 Materiais (Preço Unitário)")
    ed_mat = st.data_editor(df_mat, num_rows="dynamic", use_container_width=True, key="ed_mat")

    if st.button("💾 Guardar Todas as Tabelas", type="primary", use_container_width=True):
        ed_obras["Valor Adjudicado"] = pd.to_numeric(ed_obras["Valor Adjudicado"], errors="coerce").fillna(0.0)
        ed_obras["Total Gasto"] = 0.0
        ed_obras["Saldo Restante"] = ed_obras["Valor Adjudicado"]

        atualizar_saldos_obras(ed_obras, df_diario)
        gravar_aba("Elementos", ed_elem)
        gravar_aba("Meios", ed_meios)
        gravar_aba("Materiais", ed_mat)
        st.cache_data.clear()
        st.success("Tabelas guardadas no Google Sheets!")
        st.rerun()

# ==========================================
# ABA 4: GERAR FOLHA DE PRODUÇÃO E CUSTOS (PDF)
# ==========================================
def gerar_pdf(df_p, info_o, d_ini, d_fim):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 10, "FOLHA DE PRODUCAO E CUSTOS DE OBRA", ln=True, align="C")

    pdf.set_font("Helvetica", "", 10)
    titulo_obra = f"{info_o['ID Obra']} - {info_o['Nome da Obra']} ({info_o['Cliente']})"
    pdf.cell(0, 6, titulo_obra.encode("latin-1", "replace").decode("latin-1"), ln=True, align="C")
    pdf.cell(0, 6, f"Periodo: {d_ini.strftime('%d/%m/%Y')} a {d_fim.strftime('%d/%m/%Y')} | Estado: {info_o['Estado']}", ln=True, align="C")
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 10)
    resumo = f"Adjudicado: {info_o['Valor Adjudicado']:,.2f} EUR | Gasto Total Obra: {info_o['Total Gasto']:,.2f} EUR | Saldo: {info_o['Saldo Restante']:,.2f} EUR"
    pdf.cell(0, 8, resumo, ln=True)
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(20, 7, "Data", 1)
    pdf.cell(35, 7, "Colaborador", 1)
    pdf.cell(30, 7, "Viatura", 1)
    pdf.cell(42, 7, "Material", 1)
    pdf.cell(23, 7, "Total Dia", 1)
    pdf.cell(40, 7, "Notas", 1)
    pdf.ln()

    pdf.set_font("Helvetica", "", 7)
    for _, r in df_p.iterrows():
        el = f"{r['Elemento']} ({r['Dias Elemento']}d)" if r["Elemento"] else "-"
        me = f"{r['Meio']} ({r['Dias Meio']}d)" if r["Meio"] else "-"
        ma = f"{r['Material']} ({r['Qtd Material']})" if r["Material"] else "-"
        data_fmt = r["Data_dt"].strftime("%d/%m/%Y") if pd.notna(r["Data_dt"]) else str(r["Data"])

        pdf.cell(20, 6, data_fmt, 1)
        pdf.cell(35, 6, el[:22].encode("latin-1", "replace").decode("latin-1"), 1)
        pdf.cell(30, 6, me[:19].encode("latin-1", "replace").decode("latin-1"), 1)
        pdf.cell(42, 6, ma[:26].encode("latin-1", "replace").decode("latin-1"), 1)
        pdf.cell(23, 6, f"{r['Total do Dia']:,.2f} EUR", 1)
        pdf.cell(40, 6, str(r["Notas"])[:25].encode("latin-1", "replace").decode("latin-1"), 1)
        pdf.ln()

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 8, f"Total no Periodo Selecionado: {df_p['Total do Dia'].sum():,.2f} EUR", ln=True, align="R")
    return bytes(pdf.output())

with aba_pdf:
    st.subheader("Exportar Relatório PDF da Obra")
    obra_pdf = st.selectbox("Obra", options=todas_obras, key="pdf_obra")
    c_d1, c_d2 = st.columns(2)
    d_ini = c_d1.date_input("De", value=date.today().replace(day=1), key="pdf_ini")
    d_fim = c_d2.date_input("Até", value=date.today(), key="pdf_fim")

    df_p = df_diario[df_diario["ID Obra"] == obra_pdf].copy()
    df_p["Data_dt"] = parse_datas(df_p["Data"])
    df_p = df_p[
        df_p["Data_dt"].notna()
        & (df_p["Data_dt"] >= pd.Timestamp(d_ini))
        & (df_p["Data_dt"] <= pd.Timestamp(d_fim))
    ]

    if not df_p.empty:
        info_o_pdf = df_obras[df_obras["ID Obra"] == obra_pdf].iloc[0]
        pdf_bytes = gerar_pdf(df_p, info_o_pdf, d_ini, d_fim)
        st.download_button(
            label="📥 Descarregar PDF",
            data=pdf_bytes,
            file_name=f"Producao_{obra_pdf}_{d_ini}_{d_fim}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True
        )
    else:
        st.info("Sem registos para esta obra nas datas escolhidas.")
