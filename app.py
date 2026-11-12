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

aba_registo, aba_ponto, aba_config, aba_pdf = st.tabs(["📝 Diário", "👷 Ponto", "⚙️ Tabelas", "📄 PDF"])

# ==========================================
# ABA 1: REGISTO DIÁRIO E PONTO DE EQUIPA
# ==========================================
with aba_registo:
    obras_ativas = df_obras[df_obras["Estado"].astype(str).str.lower() != "concluída"]["ID Obra"].tolist()
    todas_obras = df_obras["ID Obra"].tolist()
    opcoes_obra = obras_ativas if obras_ativas else todas_obras

    if todas_obras:
        obra_sel = st.selectbox(
            "Consultar Obra",
            options=todas_obras,
            format_func=lambda x: f"{x} — {df_obras.loc[df_obras['ID Obra']==x, 'Nome da Obra'].values[0]}"
        )
        info_obra = df_obras[df_obras["ID Obra"] == obra_sel].iloc[0]
        adjudicado = float(info_obra["Valor Adjudicado"])
        gasto = float(info_obra["Total Gasto"])
        saldo = float(info_obra["Saldo Restante"])

        c1, c2, c3 = st.columns(3)
        c1.metric("Adjudicado", f"{adjudicado:,.2f} €")
        c2.metric("Gasto", f"{gasto:,.2f} €")
        c3.metric("Saldo", f"{saldo:,.2f} €")

        if adjudicado > 0:
            pct = min(gasto / adjudicado, 1.0)
            st.progress(pct, text=f"Orçamento consumido: {(gasto/adjudicado)*100:.1f}%")
            if saldo < 0:
                st.warning(f"⚠️ Orçamento ultrapassado em {abs(saldo):,.2f} €")

    st.divider()
    st.subheader("Novo Lançamento & Ponto")

    data_reg = st.date_input("Data", value=date.today(), key="reg_data")
    obra_reg = st.selectbox(
        "Obra",
        options=opcoes_obra,
        format_func=lambda x: f"{x} — {df_obras.loc[df_obras['ID Obra']==x, 'Nome da Obra'].values[0]}",
        key="reg_obra"
    )

    colabs_sel = st.multiselect(
        "👷 Colaboradores presentes (Ponto)",
        options=list(custos_elem.keys()),
        key="reg_colabs"
    )

    dias_por_colab = {}
    if colabs_sel:
        for c_nome in colabs_sel:
            ce1, ce2 = st.columns([2, 1])
            ce1.markdown(f"**{c_nome}** ({custos_elem[c_nome]:,.2f} €/dia)")
            dias_por_colab[c_nome] = ce2.number_input(
                f"Dias ({c_nome})",
                min_value=0.0,
                value=1.0,
                step=0.5,
                label_visibility="collapsed",
                key=f"dias_{c_nome}"
            )

    col_m1, col_m2 = st.columns([2, 1])
    meio_sel = col_m1.selectbox("🚚 Meio / Viatura", ["Nenhum"] + list(custos_meios.keys()), key="reg_meio")
    dias_meio = col_m2.number_input("Dias Meio", min_value=0.0, value=1.0, step=0.5, key="reg_dias_meio")

    col_mat1, col_mat2 = st.columns([2, 1])
    mat_sel = col_mat1.selectbox(
        "📦 Material",
        ["Nenhum"] + list(custos_mat.keys()),
        format_func=lambda m: m if m == "Nenhum" else f"{m} ({unidades_mat.get(m, '')})",
        key="reg_mat"
    )
    qtd_mat = col_mat2.number_input("Qtd Mat.", min_value=0.0, value=0.0, step=1.0, key="reg_qtd_mat")

    notas = st.text_input("Notas / Trabalhos realizados", key="reg_notas")

    custo_equipa_prev = sum(custos_elem[c] * d for c, d in dias_por_colab.items())
    custo_meio_prev = (custos_meios[meio_sel] * dias_meio) if meio_sel != "Nenhum" else 0.0
    custo_mat_prev = (custos_mat[mat_sel] * qtd_mat) if mat_sel != "Nenhum" else 0.0
    total_prev = custo_equipa_prev + custo_meio_prev + custo_mat_prev

    st.caption(f"Total previsto deste lançamento: **{total_prev:,.2f} €** (Equipa: {custo_equipa_prev:,.2f} € | Meio: {custo_meio_prev:,.2f} € | Material: {custo_mat_prev:,.2f} €)")

    if st.button("💾 Gravar Registo e Ponto", type="primary", use_container_width=True):
        if total_prev <= 0 and not notas and not colabs_sel:
            st.error("Seleciona pelo menos um colaborador, meio, material ou escreve uma nota.")
        else:
            max_id = pd.to_numeric(df_diario["ID_Registo"], errors="coerce").max()
            prox_id = int(0 if pd.isna(max_id) else max_id) + 1
            data_str = data_reg.strftime("%d/%m/%Y")
            novas_linhas = []

            if colabs_sel:
                for idx, c_nome in enumerate(colabs_sel):
                    d_c = dias_por_colab[c_nome]
                    c_c = custos_elem[c_nome] * d_c
                    primeiro = (idx == 0)
                    c_v = custo_meio_prev if primeiro else 0.0
                    c_m = custo_mat_prev if primeiro else 0.0
                    novas_linhas.append({
                        "ID_Registo": prox_id + idx,
                        "Data": data_str,
                        "ID Obra": obra_reg,
                        "Elemento": c_nome,
                        "Dias Elemento": d_c,
                        "Custo Elemento": c_c,
                        "Meio": ("" if meio_sel == "Nenhum" else meio_sel) if primeiro else "",
                        "Dias Meio": (dias_meio if meio_sel != "Nenhum" else 0) if primeiro else 0,
                        "Custo Meio": c_v,
                        "Material": ("" if mat_sel == "Nenhum" else mat_sel) if primeiro else "",
                        "Qtd Material": (qtd_mat if mat_sel != "Nenhum" else 0) if primeiro else 0,
                        "Custo Material": c_m,
                        "Total do Dia": c_c + c_v + c_m,
                        "Notas": notas if primeiro else ""
                    })
            else:
                novas_linhas.append({
                    "ID_Registo": prox_id,
                    "Data": data_str,
                    "ID Obra": obra_reg,
                    "Elemento": "",
                    "Dias Elemento": 0,
                    "Custo Elemento": 0.0,
                    "Meio": "" if meio_sel == "Nenhum" else meio_sel,
                    "Dias Meio": dias_meio if meio_sel != "Nenhum" else 0,
                    "Custo Meio": custo_meio_prev,
                    "Material": "" if mat_sel == "Nenhum" else mat_sel,
                    "Qtd Material": qtd_mat if mat_sel != "Nenhum" else 0,
                    "Custo Material": custo_mat_prev,
                    "Total do Dia": total_prev,
                    "Notas": notas
                })

            df_diario_atualizado = pd.concat([df_diario, pd.DataFrame(novas_linhas)], ignore_index=True)
            gravar_aba("Registos_Diarios", df_diario_atualizado)
            atualizar_saldos_obras(df_obras, df_diario_atualizado)
            st.cache_data.clear()
            st.success(f"Gravado! Total: {total_prev:,.2f} €")
            st.rerun()

    st.divider()
    st.subheader("Histórico da Obra")
    df_hist = df_diario[df_diario["ID Obra"] == obra_sel].copy() if todas_obras else df_diario.copy()
    edited_hist = st.data_editor(df_hist, num_rows="dynamic", use_container_width=True, key="editor_hist")

    if st.button("Atualizar Histórico / Apagar Linhas", use_container_width=True):
        for c in ["Custo Elemento", "Custo Meio", "Custo Material"]:
            edited_hist[c] = pd.to_numeric(edited_hist[c], errors="coerce").fillna(0.0)
        edited_hist["Total do Dia"] = edited_hist["Custo Elemento"] + edited_hist["Custo Meio"] + edited_hist["Custo Material"]

        df_outras = df_diario[df_diario["ID Obra"] != obra_sel]
        df_final = pd.concat([df_outras, edited_hist], ignore_index=True)
        gravar_aba("Registos_Diarios", df_final)
        atualizar_saldos_obras(df_obras, df_final)
        st.cache_data.clear()
        st.success("Histórico e saldos atualizados!")
        st.rerun()

# ==========================================
# ABA 2: MAPA DE PONTO DOS COLABORADORES
# ==========================================
def gerar_pdf_ponto(df_resumo, df_detalhe, p_ini, p_fim):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 10, "MAPA DE PONTO DE COLABORADORES", ln=True, align="C")

    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 6, f"Periodo: {p_ini.strftime('%d/%m/%Y')} a {p_fim.strftime('%d/%m/%Y')}", ln=True, align="C")
    pdf.ln(5)

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(65, 7, "Colaborador", 1)
    pdf.cell(30, 7, "Total Dias", 1, align="C")
    pdf.cell(35, 7, "Custo Total", 1, align="R")
    pdf.cell(60, 7, "Obras", 1)
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    for _, r in df_resumo.iterrows():
        pdf.cell(65, 6, str(r["Colaborador"])[:35].encode("latin-1", "replace").decode("latin-1"), 1)
        pdf.cell(30, 6, f"{r['Total Dias']:.1f}", 1, align="C")
        pdf.cell(35, 6, f"{r['Custo (€)']:,.2f} EUR", 1, align="R")
        pdf.cell(60, 6, str(r["Obras"])[:32].encode("latin-1", "replace").decode("latin-1"), 1)
        pdf.ln()

    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 7, "Registo Diario Detalhado", ln=True)

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
    st.subheader("👷 Mapa de Ponto")
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
    filtro_colab = st.selectbox("Filtrar Colaborador", ["Todos"] + colabs_disp, key="ponto_colab")
    if filtro_colab != "Todos":
        df_pt = df_pt[df_pt["Elemento"] == filtro_colab]

    if not df_pt.empty:
        df_pt["Data_Fmt"] = df_pt["Data_dt"].dt.strftime("%d/%m/%Y")
        resumo_pt = (
            df_pt.groupby("Elemento", as_index=False)
            .agg(
                **{
                    "Total Dias": ("Dias Elemento", "sum"),
                    "Custo (€)": ("Custo Elemento", "sum"),
                    "Obras": ("ID Obra", lambda s: ", ".join(sorted(set(s.astype(str)))))
                }
            )
            .rename(columns={"Elemento": "Colaborador"})
        )
        st.dataframe(resumo_pt, use_container_width=True, hide_index=True)

        with st.expander("Ver picagens dia a dia"):
            st.dataframe(
                df_pt[["Data_Fmt", "Elemento", "ID Obra", "Dias Elemento", "Custo Elemento", "Notas"]].rename(
                    columns={"Data_Fmt": "Data", "Elemento": "Colaborador", "Dias Elemento": "Dias", "Custo Elemento": "Custo (€)"}
                ),
                use_container_width=True,
                hide_index=True
            )

        pdf_ponto_bytes = gerar_pdf_ponto(resumo_pt, df_pt, p_ini, p_fim)
        st.download_button(
            label="📥 Descarregar Ponto (PDF)",
            data=pdf_ponto_bytes,
            file_name=f"Ponto_{p_ini}_{p_fim}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True
        )
    else:
        st.info("Sem registos de ponto nas datas selecionadas.")

# ==========================================
# ABA 3: CONFIGURAÇÕES (OBRAS, COLABORADORES, MEIOS, MATERIAIS)
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

    st.subheader("🚚 Meios / Viaturas (Valor/Dia)")
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
# ABA 4: GERAR FOLHA DE PRODUÇÃO (PDF)
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
    pdf.cell(30, 7, "Meio", 1)
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
