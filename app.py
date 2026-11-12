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

custos_elem = dict(zip(df_elem["Elemento"], pd.to_numeric(df_elem["Valor_Dia"], errors="coerce").fillna(0.0)))
custos_meios = dict(zip(df_meios["Meio / Equipamento"], pd.to_numeric(df_meios["Valor_Dia"], errors="coerce").fillna(0.0)))
custos_mat = dict(zip(df_mat["Material"], pd.to_numeric(df_mat["Preco_Unitario"], errors="coerce").fillna(0.0)))
unidades_mat = dict(zip(df_mat["Material"], df_mat["Unidade"].astype(str)))

st.title("🏗️ Gestão de Obras")

aba_registo, aba_config, aba_pdf = st.tabs(["📝 Registo Diário", "⚙️ Tabelas & Obras", "📄 PDF"])

# ==========================================
# ABA 1: REGISTO DIÁRIO E ESTADO DA OBRA
# ==========================================
with aba_registo:
    obras_ativas = df_obras[df_obras["Estado"].astype(str).str.lower() != "concluída"]["ID Obra"].tolist()
    todas_obras = df_obras["ID Obra"].tolist()
    opcoes_obra = obras_ativas if obras_ativas else todas_obras

    if todas_obras:
        obra_sel = st.selectbox(
            "Selecionar Obra",
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
    st.subheader("Novo Lançamento")

    with st.form("form_diario", clear_on_submit=True):
        data_reg = st.date_input("Data", value=date.today())
        obra_reg = st.selectbox("Obra", options=opcoes_obra)

        col_e1, col_e2 = st.columns([2, 1])
        elem_sel = col_e1.selectbox("Elemento / Equipa", ["Nenhum"] + list(custos_elem.keys()))
        dias_elem = col_e2.number_input("Dias Elem.", min_value=0.0, value=1.0, step=0.5)

        col_m1, col_m2 = st.columns([2, 1])
        meio_sel = col_m1.selectbox("Meio / Viatura", ["Nenhum"] + list(custos_meios.keys()))
        dias_meio = col_m2.number_input("Dias Meio", min_value=0.0, value=1.0, step=0.5)

        col_mat1, col_mat2 = st.columns([2, 1])
        mat_sel = col_mat1.selectbox(
            "Material",
            ["Nenhum"] + list(custos_mat.keys()),
            format_func=lambda m: m if m == "Nenhum" else f"{m} ({unidades_mat.get(m, '')})"
        )
        qtd_mat = col_mat2.number_input("Qtd Mat.", min_value=0.0, value=0.0, step=1.0)

        notas = st.text_input("Notas / Trabalhos realizados")
        submeter = st.form_submit_button("💾 Gravar Registo", type="primary", use_container_width=True)

    if submeter:
        custo_e = (custos_elem[elem_sel] * dias_elem) if elem_sel != "Nenhum" else 0.0
        custo_v = (custos_meios[meio_sel] * dias_meio) if meio_sel != "Nenhum" else 0.0
        custo_m = (custos_mat[mat_sel] * qtd_mat) if mat_sel != "Nenhum" else 0.0
        total_dia = custo_e + custo_v + custo_m

        if total_dia <= 0 and not notas:
            st.error("Preenche pelo menos um elemento, meio, material ou nota.")
        else:
            max_id = pd.to_numeric(df_diario["ID_Registo"], errors="coerce").max()
            novo_id = int(0 if pd.isna(max_id) else max_id) + 1
            nova_linha = pd.DataFrame([{
                "ID_Registo": novo_id,
                "Data": data_reg.strftime("%d/%m/%Y"),
                "ID Obra": obra_reg,
                "Elemento": "" if elem_sel == "Nenhum" else elem_sel,
                "Dias Elemento": dias_elem if elem_sel != "Nenhum" else 0,
                "Custo Elemento": custo_e,
                "Meio": "" if meio_sel == "Nenhum" else meio_sel,
                "Dias Meio": dias_meio if meio_sel != "Nenhum" else 0,
                "Custo Meio": custo_v,
                "Material": "" if mat_sel == "Nenhum" else mat_sel,
                "Qtd Material": qtd_mat if mat_sel != "Nenhum" else 0,
                "Custo Material": custo_m,
                "Total do Dia": total_dia,
                "Notas": notas
            }])
            df_diario_atualizado = pd.concat([df_diario, nova_linha], ignore_index=True)
            gravar_aba("Registos_Diarios", df_diario_atualizado)
            atualizar_saldos_obras(df_obras, df_diario_atualizado)
            st.cache_data.clear()
            st.success(f"Registado! Total do dia: {total_dia:,.2f} €")
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
# ABA 2: CONFIGURAÇÕES (OBRAS, ELEMENTOS, MEIOS, MATERIAIS)
# ==========================================
with aba_config:
    st.subheader("🏢 Obras e Orçamentos")
    st.caption("Para fechar uma obra, altera o Estado para 'Concluída'.")
    ed_obras = st.data_editor(
        df_obras[["ID Obra", "Nome da Obra", "Cliente", "Valor Adjudicado", "Estado"]],
        num_rows="dynamic",
        use_container_width=True,
        key="ed_obras"
    )

    st.subheader("👷 Elementos (Valor/Dia)")
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
# ABA 3: GERAR FOLHA DE PRODUÇÃO (PDF)
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
    pdf.cell(35, 7, "Elemento", 1)
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
    st.subheader("Exportar Relatório PDF")
    obra_pdf = st.selectbox("Obra", options=todas_obras, key="pdf_obra")
    c_d1, c_d2 = st.columns(2)
    d_ini = c_d1.date_input("De", value=date.today().replace(day=1))
    d_fim = c_d2.date_input("Até", value=date.today())

    df_p = df_diario[df_diario["ID Obra"] == obra_pdf].copy()
    df_p["Data_dt"] = pd.to_datetime(
        df_p["Data"], format="mixed", dayfirst=True, errors="coerce", utc=True
    ).dt.tz_localize(None)
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
