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

secao = st.radio("Menu", ["📝 Diário", "👷 Presenças", "💰 Contas", "⚙️ Tabelas", "📄 PDF"], horizontal=True, label_visibility="collapsed")
st.divider()

# ==========================================
# 1. REGISTO DIÁRIO (SEM VALORES VISÍVEIS)
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
        qtd_mat[nome] = c2.number_input("Qtd", 0.0, value=1.0, step=1.0, label_visibility="collapsed", key=f"qm_{nome}_{rid}")

    notas = st.text_input("📝 Notas / Trabalhos realizados", key=f"nt_{rid}")

    if st.button("💾 Gravar Registo Diário", type="primary", use_container_width=True):
        if not obra_reg:
            st.error("Seleciona uma obra.")
        elif not colabs_sel and not meios_sel and not mats_sel and not notas.strip():
            st.error("Preenche pelo menos um campo.")
        else:
            max_id = pd.to_numeric(df_diario["ID_Registo"], errors="coerce").max()
            prox_id = int(0 if pd.isna(max_id) else max_id) + 1
            data_iso = data_reg.strftime("%Y-%m-%d")
            lc = [(c, dias_colab[c]) for c in colabs_sel if dias_colab[c] > 0]
            lm = [(m, dias_meio[m]) for m in meios_sel if dias_meio[m] > 0]
            lt = [(mt, qtd_mat[mt]) for mt in mats_sel if qtd_mat[mt] > 0]
            novas = []
            for i in range(max(len(lc), len(lm), len(lt), 1)):
                en, ed = lc[i] if i < len(lc) else ("", 0.0)
                mn, md = lm[i] if i < len(lm) else ("", 0.0)
                tn, tq = lt[i] if i < len(lt) else ("", 0.0)
                ce, cm, ct = custos_elem.get(en, 0.0) * ed, custos_meios.get(mn, 0.0) * md, custos_mat.get(tn, 0.0) * tq
                novas.append({"ID_Registo": prox_id + i, "Data": data_iso, "ID Obra": obra_reg,
                              "Elemento": en, "Dias Elemento": ed, "Custo Elemento": ce,
                              "Meio": mn, "Dias Meio": md, "Custo Meio": cm,
                              "Material": tn, "Qtd Material": tq, "Custo Material": ct,
                              "Total do Dia": ce + cm + ct, "Notas": notas if i == 0 else ""})
            df_novo = pd.concat([df_diario, pd.DataFrame(novas)], ignore_index=True)
            gravar_aba("Registos_Diarios", df_novo)
            atualizar_saldos(df_obras, df_novo)
            st.cache_data.clear()
            st.session_state["reset_id"] += 1
            st.session_state["msg_sucesso"] = f"Gravado ({len(lc)} presença(s) registada(s))!"
            st.rerun()

    if obra_reg:
        st.divider()
        st.subheader("Histórico da Obra")
        hist = df_diario[df_diario["ID Obra"] == obra_reg].copy()
        hist["Data"] = parse_datas(hist["Data"]).dt.strftime("%d/%m/%Y").fillna(hist["Data"])
        cols_v = ["ID_Registo", "Data", "Elemento", "Dias Elemento", "Meio", "Dias Meio", "Material", "Qtd Material", "Notas"]
        ed_hist = st.data_editor(hist[cols_v], num_rows="dynamic", use_container_width=True, hide_index=True, disabled=["ID_Registo"])
        if st.button("Atualizar Histórico / Apagar Linhas", use_container_width=True):
            ed = ed_hist.copy()
            ed["Data"] = parse_datas(ed["Data"]).dt.strftime("%Y-%m-%d").fillna(ed["Data"].astype(str))
            ed["ID Obra"] = obra_reg
            for col_n in ["Dias Elemento", "Dias Meio", "Qtd Material"]:
                ed[col_n] = pd.to_numeric(ed[col_n], errors="coerce").fillna(0.0)
            ed["Custo Elemento"] = ed.apply(lambda r: custos_elem.get(str(r["Elemento"]), 0.0) * r["Dias Elemento"], axis=1)
            ed["Custo Meio"] = ed.apply(lambda r: custos_meios.get(str(r["Meio"]), 0.0) * r["Dias Meio"], axis=1)
            ed["Custo Material"] = ed.apply(lambda r: custos_mat.get(str(r["Material"]), 0.0) * r["Qtd Material"], axis=1)
            ed["Total do Dia"] = ed["Custo Elemento"] + ed["Custo Meio"] + ed["Custo Material"]
            df_final = pd.concat([df_diario[df_diario["ID Obra"] != obra_reg], ed[df_diario.columns.tolist()]], ignore_index=True)
            gravar_aba("Registos_Diarios", df_final)
            atualizar_saldos(df_obras, df_final)
            st.cache_data.clear()
            st.session_state["msg_sucesso"] = "Histórico atualizado!"
            st.rerun()

# ==========================================
# 2. MAPA DE PRESENÇAS
# ==========================================
elif secao == "👷 Presenças":
    st.subheader("👷 Mapa de Presenças")
    base = df_diario[df_diario["Elemento"] != ""].copy()
    base["Data_dt"] = parse_datas(base["Data"])
    base = base[base["Data_dt"].notna()].copy()

    fim_def = max(date.today(), base["Data_dt"].max().date()) if not base.empty else date.today()
    c1, c2 = st.columns(2)
    p_ini = c1.date_input("De", value=date.today().replace(day=1), key="p_ini")
    p_fim = c2.date_input("Até", value=fim_def, key="p_fim")

    filt = base[(base["Data_dt"] >= pd.Timestamp(p_ini)) & (base["Data_dt"] <= pd.Timestamp(p_fim))].sort_values(["Elemento", "Data_dt"])
    colab_sel = st.selectbox("Colaborador", ["Todos"] + sorted(base["Elemento"].unique().tolist()))
    if colab_sel != "Todos":
        filt = filt[filt["Elemento"] == colab_sel]

    if not filt.empty:
        filt["Data_Fmt"] = filt["Data_dt"].dt.strftime("%d/%m/%Y")
        resumo = filt.groupby("Elemento", as_index=False).agg(
            **{"Total Dias": ("Dias Elemento", "sum"), "Obras": ("ID Obra", lambda s: ", ".join(sorted(set(s.astype(str)))))}
        ).rename(columns={"Elemento": "Colaborador"})
        st.dataframe(resumo, use_container_width=True, hide_index=True)

        st.markdown("**Registo dia a dia**")
        st.dataframe(filt[["Data_Fmt", "Elemento", "ID Obra", "Dias Elemento", "Notas"]].rename(
            columns={"Data_Fmt": "Data", "Elemento": "Colaborador", "Dias Elemento": "Dias"}), use_container_width=True, hide_index=True)

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, "MAPA DE PRESENCAS", ln=True, align="C")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"Periodo: {p_ini.strftime('%d/%m/%Y')} a {p_fim.strftime('%d/%m/%Y')}", ln=True, align="C")
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 9)
        for txt, w in [("Colaborador", 75), ("Total Dias", 35), ("Obras", 80)]:
            pdf.cell(w, 7, txt, 1)
        pdf.ln()
        pdf.set_font("Helvetica", "", 8)
        for _, r in resumo.iterrows():
            pdf.cell(75, 6, str(r["Colaborador"])[:40].encode("latin-1", "replace").decode("latin-1"), 1)
            pdf.cell(35, 6, f"{r['Total Dias']:.1f}", 1, align="C")
            pdf.cell(80, 6, str(r["Obras"])[:44].encode("latin-1", "replace").decode("latin-1"), 1)
            pdf.ln()
        st.download_button("📥 Descarregar Mapa de Presenças (PDF)", bytes(pdf.output()),
                           file_name=f"Presencas_{p_ini}_{p_fim}.pdf", mime="application/pdf", type="primary", use_container_width=True)
    else:
        st.info("Sem presenças registadas nas datas selecionadas.")

# ==========================================
# 3. CONTAS DA OBRA (ORÇAMENTO E TODOS OS GASTOS)
# ==========================================
elif secao == "💰 Contas":
    st.subheader("💰 Contas por Obra")
    obras_list = df_obras["ID Obra"].tolist()

    if obras_list:
        obra_ct = st.selectbox(
            "Selecionar Obra",
            obras_list,
            format_func=lambda x: f"{x} — {df_obras.loc[df_obras['ID Obra']==x, 'Nome da Obra'].values[0]}",
            key="ct_obra"
        )
        info_ct = df_obras[df_obras["ID Obra"] == obra_ct].iloc[0]
        df_ct = df_diario[df_diario["ID Obra"] == obra_ct].copy()

        adjudicado = float(info_ct["Valor Adjudicado"])
        gasto_colab = float(df_ct["Custo Elemento"].sum())
        gasto_viat = float(df_ct["Custo Meio"].sum())
        gasto_mat = float(df_ct["Custo Material"].sum())
        total_gasto = gasto_colab + gasto_viat + gasto_mat
        saldo = adjudicado - total_gasto

        m1, m2, m3 = st.columns(3)
        m1.metric("Valor Obra", f"{adjudicado:,.2f} €")
        m2.metric("Total Gasto", f"{total_gasto:,.2f} €")
        m3.metric("Saldo", f"{saldo:,.2f} €")

        if adjudicado > 0:
            pct = min(total_gasto / adjudicado, 1.0)
            st.progress(pct, text=f"Orçamento consumido: {(total_gasto / adjudicado) * 100:.1f}%")
            if saldo < 0:
                st.warning(f"⚠️ Orçamento ultrapassado em {abs(saldo):,.2f} €")

        st.markdown("**Resumo de Gastos por Categoria**")
        g1, g2, g3 = st.columns(3)
        g1.metric("👷 Colaboradores", f"{gasto_colab:,.2f} €")
        g2.metric("🚚 Viaturas", f"{gasto_viat:,.2f} €")
        g3.metric("📦 Materiais", f"{gasto_mat:,.2f} €")

        st.divider()
        st.markdown("**Detalhe de Todos os Gastos da Obra**")
        if not df_ct.empty:
            df_ct["Data_dt"] = parse_datas(df_ct["Data"])
            df_ct = df_ct.sort_values("Data_dt", ascending=False)
            df_ct["Data_Fmt"] = df_ct["Data_dt"].dt.strftime("%d/%m/%Y").fillna(df_ct["Data"])
            tab_gastos = df_ct[[
                "Data_Fmt", "Elemento", "Dias Elemento", "Custo Elemento",
                "Meio", "Dias Meio", "Custo Meio",
                "Material", "Qtd Material", "Custo Material",
                "Total do Dia", "Notas"
            ]].rename(columns={
                "Data_Fmt": "Data",
                "Elemento": "Colaborador",
                "Dias Elemento": "Dias Col.",
                "Custo Elemento": "€ Col.",
                "Meio": "Viatura",
                "Dias Meio": "Dias Viat.",
                "Custo Meio": "€ Viat.",
                "Qtd Material": "Qtd",
                "Custo Material": "€ Mat.",
                "Total do Dia": "Total (€)"
            })
            st.dataframe(tab_gastos, use_container_width=True, hide_index=True)
        else:
            st.info("Ainda não existem gastos registados nesta obra.")

        st.divider()
        st.subheader("📊 Resumo Geral de Todas as Obras")
        resumo_obras = df_obras[["ID Obra", "Nome da Obra", "Cliente", "Valor Adjudicado", "Total Gasto", "Saldo Restante", "Estado"]].rename(
            columns={
                "Valor Adjudicado": "Valor Obra (€)",
                "Total Gasto": "Gasto (€)",
                "Saldo Restante": "Saldo (€)"
            }
        )
        st.dataframe(resumo_obras, use_container_width=True, hide_index=True)
    else:
        st.info("Sem obras registadas. Adiciona obras em ⚙️ Tabelas.")

# ==========================================
# 4. TABELAS
# ==========================================
elif secao == "⚙️ Tabelas":
    st.subheader("🏢 Obras Atribuídas")
    ed_obras = st.data_editor(df_obras[["ID Obra", "Nome da Obra", "Cliente", "Valor Adjudicado", "Estado"]],
                              num_rows="dynamic", use_container_width=True, hide_index=True)
    st.subheader("👷 Colaboradores (Valor/Dia)")
    ed_elem = st.data_editor(df_elem, num_rows="dynamic", use_container_width=True, hide_index=True)
    st.subheader("🚚 Viaturas / Meios (Valor/Dia)")
    ed_meios = st.data_editor(df_meios, num_rows="dynamic", use_container_width=True, hide_index=True)
    st.subheader("📦 Materiais (Preço Unitário)")
    ed_mat = st.data_editor(df_mat, num_rows="dynamic", use_container_width=True, hide_index=True)

    if st.button("💾 Guardar Todas as Tabelas", type="primary", use_container_width=True):
        ed_obras["Valor Adjudicado"] = pd.to_numeric(ed_obras["Valor Adjudicado"], errors="coerce").fillna(0.0)
        ed_obras["Total Gasto"] = 0.0
        ed_obras["Saldo Restante"] = ed_obras["Valor Adjudicado"]
        atualizar_saldos(ed_obras, df_diario)
        gravar_aba("Elementos", ed_elem)
        gravar_aba("Meios", ed_meios)
        gravar_aba("Materiais", ed_mat)
        st.cache_data.clear()
        st.session_state["msg_sucesso"] = "Tabelas guardadas!"
        st.rerun()

# ==========================================
# 5. PDF DA OBRA
# ==========================================
elif secao == "📄 PDF":
    st.subheader("Exportar Relatório PDF da Obra")
    obras_list = df_obras["ID Obra"].tolist()
    if obras_list:
        obra_pdf = st.selectbox("Obra", obras_list)
        bp = df_diario[df_diario["ID Obra"] == obra_pdf].copy()
        bp["Data_dt"] = parse_datas(bp["Data"])
        bp = bp[bp["Data_dt"].notna()].copy()
        fim_pdf = max(date.today(), bp["Data_dt"].max().date()) if not bp.empty else date.today()
        c1, c2 = st.columns(2)
        d_ini = c1.date_input("De", value=date.today().replace(day=1), key="pdf_ini")
        d_fim = c2.date_input("Até", value=fim_pdf, key="pdf_fim")
        df_p = bp[(bp["Data_dt"] >= pd.Timestamp(d_ini)) & (bp["Data_dt"] <= pd.Timestamp(d_fim))]

        if not df_p.empty:
            info = df_obras[df_obras["ID Obra"] == obra_pdf].iloc[0]
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(0, 10, "FOLHA DE PRODUCAO E CUSTOS DE OBRA", ln=True, align="C")
            pdf.set_font("Helvetica", "", 10)
            tit = f"{info['ID Obra']} - {info['Nome da Obra']} ({info['Cliente']})"
            pdf.cell(0, 6, tit.encode("latin-1", "replace").decode("latin-1"), ln=True, align="C")
            pdf.cell(0, 6, f"Periodo: {d_ini.strftime('%d/%m/%Y')} a {d_fim.strftime('%d/%m/%Y')}", ln=True, align="C")
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(0, 7, f"Adjudicado: {info['Valor Adjudicado']:,.2f} EUR | Gasto: {info['Total Gasto']:,.2f} EUR | Saldo: {info['Saldo Restante']:,.2f} EUR", ln=True)
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 8)
            for txt, w in [("Data", 20), ("Colaborador", 35), ("Viatura", 30), ("Material", 42), ("Total", 23), ("Notas", 40)]:
                pdf.cell(w, 7, txt, 1)
            pdf.ln()
            pdf.set_font("Helvetica", "", 7)
            for _, r in df_p.iterrows():
                el = f"{r['Elemento']} ({r['Dias Elemento']}d)" if r["Elemento"] else "-"
                me = f"{r['Meio']} ({r['Dias Meio']}d)" if r["Meio"] else "-"
                ma = f"{r['Material']} ({r['Qtd Material']})" if r["Material"] else "-"
                pdf.cell(20, 6, r["Data_dt"].strftime("%d/%m/%Y"), 1)
                pdf.cell(35, 6, el[:22].encode("latin-1", "replace").decode("latin-1"), 1)
                pdf.cell(30, 6, me[:19].encode("latin-1", "replace").decode("latin-1"), 1)
                pdf.cell(42, 6, ma[:26].encode("latin-1", "replace").decode("latin-1"), 1)
                pdf.cell(23, 6, f"{r['Total do Dia']:,.2f} EUR", 1)
                pdf.cell(40, 6, str(r["Notas"])[:25].encode("latin-1", "replace").decode("latin-1"), 1)
                pdf.ln()
            st.download_button("📥 Descarregar PDF", bytes(pdf.output()),
                               file_name=f"Producao_{obra_pdf}_{d_ini}_{d_fim}.pdf", mime="application/pdf", type="primary", use_container_width=True)
        else:
            st.info("Sem registos nas datas escolhidas.")
