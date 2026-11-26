import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import calendar
import base64
import os
import re
from datetime import date
import requests
import json
from fpdf import FPDF

st.set_page_config(page_title="Gestão LSM", page_icon="🗼", layout="centered")
st.session_state.setdefault("ciclo", 0)
st.session_state.setdefault("aviso", "")
st.session_state.setdefault("usr_nome", "")
st.session_state.setdefault("usr_perfil", "")
st.session_state.setdefault("setor", "🗼 Rede Móvel")

def aplicar_fundo_marca_agua():
    img_path = None
    preferidos = ["fundo.jpg", "fundo.jpeg", "fundo.png", "fundo.webp"]
    ficheiros_pasta = os.listdir(".")
    mapa_lower = {f.lower(): f for f in ficheiros_pasta if os.path.isfile(f)}
    for p in preferidos:
        if p in mapa_lower:
            img_path = mapa_lower[p]
            break
    if not img_path:
        for f_low, f_real in mapa_lower.items():
            if f_low.endswith((".jpg", ".jpeg", ".png", ".webp")):
                img_path = f_real
                break

    if img_path and os.path.exists(img_path):
        with open(img_path, "rb") as f:
            b64_img = base64.b64encode(f.read()).decode("utf-8")
        ext = "png" if img_path.lower().endswith(".png") else "jpeg"
        st.markdown(
            f"""
            <style>
            .stApp, [data-testid="stAppViewContainer"] {{
                background: linear-gradient(rgba(255, 255, 255, 0.82), rgba(255, 255, 255, 0.82)),
                            url("data:image/{ext};base64,{b64_img}") !important;
                background-size: cover !important;
                background-position: center top !important;
                background-attachment: fixed !important;
                background-repeat: no-repeat !important;
            }}
            [data-testid="stHeader"] {{
                background: transparent !important;
            }}
            </style>
            """,
            unsafe_allow_html=True
        )

aplicar_fundo_marca_agua()

MESES = {
    1: "01 - Janeiro", 2: "02 - Fevereiro", 3: "03 - Março", 4: "04 - Abril",
    5: "05 - Maio", 6: "06 - Junho", 7: "07 - Julho", 8: "08 - Agosto",
    9: "09 - Setembro", 10: "10 - Outubro", 11: "11 - Novembro", 12: "12 - Dezembro"
}

ESTADOS_OBRA = ["Nova", "Execução", "Parcial", "Concluída"]

def extrair_id_drive(url):
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", str(url))
    return m.group(1) if m else ""

def separar_links_fotos(texto_fotos):
    if not texto_fotos:
        return []
    partes = [p.strip() for p in str(texto_fotos).replace("\n", "|").split("|")]
    return [p for p in partes if p.startswith("http")]

def mostrar_anexos_obra(obra_id, nome_obra, url_pdf, texto_fotos):
    url_limpo = str(url_pdf).strip()
    lista_fotos = separar_links_fotos(texto_fotos)

    if url_limpo.startswith("http"):
        fid = extrair_id_drive(url_limpo)
        st.markdown(f"**📎 Documento / Projeto da Obra ({obra_id})**")
        b1, b2 = st.columns(2)
        b1.link_button("📄 Abrir PDF noutra aba", url_limpo, type="primary", use_container_width=True)
        if fid:
            b2.link_button("📥 Descarregar PDF", f"https://drive.google.com/uc?export=download&id={fid}", use_container_width=True)
            with st.expander("👁️ Consultar PDF diretamente aqui na aplicação"):
                components.iframe(f"https://drive.google.com/file/d/{fid}/preview", height=520, scrolling=True)
    else:
        st.caption(f"ℹ️ A obra {obra_id} ({nome_obra}) não tem ficheiro PDF anexado.")

    if lista_fotos:
        with st.expander(f"🖼️ Ver Fotografias da Obra ({len(lista_fotos)} foto(s))", expanded=False):
            cols_f = st.columns(2)
            for idx, link_f in enumerate(lista_fotos):
                fid_f = extrair_id_drive(link_f)
                with cols_f[idx % 2]:
                    if fid_f:
                        st.image(f"https://drive.google.com/thumbnail?id={fid_f}&sz=w800", caption=f"Foto {idx + 1}", use_container_width=True)
                    st.link_button(f"🔍 Abrir Foto {idx + 1}", link_f, use_container_width=True)
    else:
        st.caption("📷 Sem fotografias associadas a esta obra.")

def normalizar_estado(valor):
    v = str(valor).strip().lower()
    if v in ["execucao", "execuçao", "execução", "em curso", "em execucao", "em execução"]:
        return "Execução"
    if v in ["concluida", "concluída", "fechada", "terminada"]:
        return "Concluída"
    if v == "parcial":
        return "Parcial"
    if v == "nova" or v == "":
        return "Nova"
    return str(valor).strip()

def obter_config_setor(setor_escolhido):
    if "Eletricidade" in setor_escolhido:
        return {
            "titulo": "⚡ Eletricidade LSM",
            "pdf_cab": "ELETRICIDADE LSM",
            "pdf_tag": "Eletricidade_LSM",
            "secret_key": "apps_script_url_eletricidade"
        }
    return {
        "titulo": "🗼 Rede Móvel LSM",
        "pdf_cab": "REDE MOVEL LSM",
        "pdf_tag": "RedeMovel_LSM",
        "secret_key": "apps_script_url"
    }

def txt_pdf(valor, limite=40):
    return str(valor)[:limite].encode("latin-1", "replace").decode("latin-1")

def bytes_pdf(doc):
    out = doc.output()
    return out.encode("latin-1") if isinstance(out, str) else bytes(out)

def gerar_pdf_contas_cliente(cfg, cliente_nome, estados_lista, df_obras_cli, df_diario_all):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    tit_cli = "TODOS OS CLIENTES" if cliente_nome == "Todos" else cliente_nome.upper()
    pdf.cell(0, 8, txt_pdf(f"{cfg['pdf_cab']} - RELATORIO DE CONTAS POR CLIENTE", 95), ln=True, align="C")
    pdf.set_font("Helvetica", "", 9)
    est_txt = ", ".join(estados_lista) if estados_lista else "Todos"
    pdf.cell(0, 6, txt_pdf(f"Cliente: {tit_cli} | Estados: {est_txt} | Emissao: {date.today().strftime('%d/%m/%Y')}", 110), ln=True, align="C")
    pdf.ln(3)

    ids_cli = set(df_obras_cli["ID Obra"].tolist())
    reg_cli = df_diario_all[df_diario_all["ID Obra"].isin(ids_cli)].copy() if not df_diario_all.empty else pd.DataFrame()

    tot_adj = float(df_obras_cli["Valor Adjudicado"].sum())
    tot_gas = float(df_obras_cli["Total Gasto"].sum())
    tot_sal = tot_adj - tot_gas
    tot_col = float(reg_cli["Custo Elemento"].sum()) if not reg_cli.empty else 0.0
    tot_via = float(reg_cli["Custo Meio"].sum()) if not reg_cli.empty else 0.0
    tot_mat = float(reg_cli["Custo Material"].sum()) if not reg_cli.empty else 0.0

    pdf.set_fill_color(241, 245, 249)
    pdf.set_font("Helvetica", "B", 9)
    resumo_1 = f"Obras: {len(df_obras_cli)}   |   Adjudicado: {tot_adj:,.2f} EUR   |   Total Gasto: {tot_gas:,.2f} EUR   |   Saldo Global: {tot_sal:,.2f} EUR"
    pdf.cell(0, 7, txt_pdf(resumo_1, 120), 1, ln=True, align="C", fill=True)
    pdf.set_font("Helvetica", "", 8)
    resumo_2 = f"Detalhe Custos -> Colaboradores: {tot_col:,.2f} EUR   |   Viaturas: {tot_via:,.2f} EUR   |   Materiais: {tot_mat:,.2f} EUR"
    pdf.cell(0, 6, txt_pdf(resumo_2, 120), 1, ln=True, align="C")
    pdf.ln(4)

    cols = [
        ("ID Obra", 24, "L"),
        ("Nome da Obra", 63, "L"),
        ("Cliente", 34, "L"),
        ("Estado", 22, "C"),
        ("Adjudicado", 27, "R"),
        ("Colab.", 25, "R"),
        ("Viaturas", 25, "R"),
        ("Materiais", 25, "R"),
        ("Saldo", 32, "R")
    ]
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(219, 234, 254)
    for cab, larg, al in cols:
        pdf.cell(larg, 7, cab, 1, align=al, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 7.5)
    for _, r in df_obras_cli.iterrows():
        oid = str(r["ID Obra"])
        sub = reg_cli[reg_cli["ID Obra"] == oid] if not reg_cli.empty else pd.DataFrame()
        c_col = float(sub["Custo Elemento"].sum()) if not sub.empty else 0.0
        c_via = float(sub["Custo Meio"].sum()) if not sub.empty else 0.0
        c_mat = float(sub["Custo Material"].sum()) if not sub.empty else 0.0
        v_ad = float(r["Valor Adjudicado"])
        v_sa = float(r["Saldo Restante"])

        pdf.cell(24, 6, txt_pdf(oid, 14), 1)
        pdf.cell(63, 6, txt_pdf(r["Nome da Obra"], 36), 1)
        pdf.cell(34, 6, txt_pdf(r["Cliente"], 19), 1)
        pdf.cell(22, 6, txt_pdf(r["Estado"], 12), 1, align="C")
        pdf.cell(27, 6, f"{v_ad:,.2f}", 1, align="R")
        pdf.cell(25, 6, f"{c_col:,.2f}", 1, align="R")
        pdf.cell(25, 6, f"{c_via:,.2f}", 1, align="R")
        pdf.cell(25, 6, f"{c_mat:,.2f}", 1, align="R")
        pdf.cell(32, 6, f"{v_sa:,.2f}", 1, align="R")
        pdf.ln()

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(241, 245, 249)
    pdf.cell(143, 7, "TOTAIS (EUR)", 1, align="R", fill=True)
    pdf.cell(27, 7, f"{tot_adj:,.2f}", 1, align="R", fill=True)
    pdf.cell(25, 7, f"{tot_col:,.2f}", 1, align="R", fill=True)
    pdf.cell(25, 7, f"{tot_via:,.2f}", 1, align="R", fill=True)
    pdf.cell(25, 7, f"{tot_mat:,.2f}", 1, align="R", fill=True)
    pdf.cell(32, 7, f"{tot_sal:,.2f}", 1, align="R", fill=True)
    pdf.ln()
    return bytes_pdf(pdf)

def gerar_pdf_contas_obra(cfg, info_obra, df_reg_obra, d_ini=None, d_fim=None):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, txt_pdf(f"{cfg['pdf_cab']} - RELATORIO DE CONTAS DA OBRA", 85), ln=True, align="C")
    pdf.set_font("Helvetica", "", 9.5)
    pdf.cell(0, 6, txt_pdf(f"{info_obra['ID Obra']} - {info_obra['Nome da Obra']} | Cliente: {info_obra['Cliente']} | Estado: {info_obra['Estado']}", 90), ln=True, align="C")
    if d_ini and d_fim:
        pdf.cell(0, 5, f"Periodo: {d_ini.strftime('%d/%m/%Y')} a {d_fim.strftime('%d/%m/%Y')} | Emissao: {date.today().strftime('%d/%m/%Y')}", ln=True, align="C")
    else:
        pdf.cell(0, 5, f"Historico Completo da Obra | Emissao: {date.today().strftime('%d/%m/%Y')}", ln=True, align="C")
    pdf.ln(3)

    v_adj = float(info_obra["Valor Adjudicado"])
    g_eq = float(df_reg_obra["Custo Elemento"].sum()) if not df_reg_obra.empty else 0.0
    g_vi = float(df_reg_obra["Custo Meio"].sum()) if not df_reg_obra.empty else 0.0
    g_mt = float(df_reg_obra["Custo Material"].sum()) if not df_reg_obra.empty else 0.0
    g_tot = g_eq + g_vi + g_mt
    v_sal = v_adj - g_tot

    pdf.set_fill_color(241, 245, 249)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(0, 7, f"Adjudicado: {v_adj:,.2f} EUR   |   Total Gasto: {g_tot:,.2f} EUR   |   Saldo: {v_sal:,.2f} EUR", 1, ln=True, align="C", fill=True)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.cell(0, 6, f"Colaboradores: {g_eq:,.2f} EUR   |   Viaturas: {g_vi:,.2f} EUR   |   Materiais: {g_mt:,.2f} EUR", 1, ln=True, align="C")
    pdf.ln(4)

    if not df_reg_obra.empty:
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_fill_color(219, 234, 254)
        for cab, larg, al in [("Data", 20, "C"), ("Colaborador", 36, "L"), ("Viatura", 30, "L"), ("Material", 42, "L"), ("Total", 24, "R"), ("Notas", 38, "L")]:
            pdf.cell(larg, 7, cab, 1, align=al, fill=True)
        pdf.ln()
        pdf.set_font("Helvetica", "", 7)
        for _, r in df_reg_obra.iterrows():
            if r["Elemento"]:
                el = f"{r['Elemento']} (FALTA {r['Dias Falta']}d)" if r["Dias Falta"] > 0 and r["Dias Elemento"] == 0 else f"{r['Elemento']} ({r['Dias Elemento']}d)"
            else:
                el = "-"
            me = f"{r['Meio']} ({r['Dias Meio']}d)" if r["Meio"] else "-"
            ma = f"{r['Material']} ({r['Qtd Material']})" if r["Material"] else "-"
            dt_str = r["Data_dt"].strftime("%d/%m/%Y") if pd.notna(r["Data_dt"]) else str(r["Data"])
            pdf.cell(20, 6, dt_str, 1, align="C")
            pdf.cell(36, 6, txt_pdf(el, 22), 1)
            pdf.cell(30, 6, txt_pdf(me, 19), 1)
            pdf.cell(42, 6, txt_pdf(ma, 26), 1)
            pdf.cell(24, 6, f"{r['Total do Dia']:,.2f} EUR", 1, align="R")
            pdf.cell(38, 6, txt_pdf(r["Notas"], 23), 1)
            pdf.ln()
    else:
        pdf.set_font("Helvetica", "I", 9)
        pdf.cell(0, 8, "Sem registos de gastos no periodo selecionado.", ln=True)

    return bytes_pdf(pdf)

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
def ler_servidor(url_script):
    r = requests.get(url_script, timeout=15)
    r.raise_for_status()
    pacote = r.json()

    def extrair(aba, cols, sin=None, pos_fallback=True, max_pos=None):
        df = pd.DataFrame(pacote.get(aba, []))
        if df.empty:
            return pd.DataFrame(columns=cols)
        if sin:
            df = ajustar_colunas(df, sin)
        cols_orig = list(df.columns)
        limite_pos = len(cols) if max_pos is None else max_pos
        for i, c in enumerate(cols):
            if c not in df.columns:
                if pos_fallback and i < limite_pos and i < len(cols_orig) and cols_orig[i] not in cols:
                    df[c] = df[cols_orig[i]]
                else:
                    df[c] = ""
        return df[cols]

    obras = extrair(
        "Obras",
        ["ID Obra", "Nome da Obra", "Cliente", "Valor Adjudicado", "Total Gasto", "Saldo Restante", "Estado", "PDF", "Fotos"],
        {
            "ID Obra": ["ID", "Codigo", "Código", "Obra ID", "Ref"],
            "Nome da Obra": ["Obra", "Nome", "Designacao", "Designação", "Local"],
            "Cliente": ["Clientes", "Entidade"],
            "Valor Adjudicado": ["Valor", "Orcamento", "Orçamento", "Adjudicado", "Valor Obra"],
            "PDF": ["Link PDF", "Ficheiro", "Projeto", "Anexo", "URL"],
            "Fotos": ["Foto", "Fotografias", "Imagens", "Links Fotos"]
        },
        pos_fallback=True,
        max_pos=7
    )
    elem_raw = extrair(
        "Elementos",
        ["Elemento", "Valor_Dia", "Utilizador", "Senha", "Perfil"],
        {
            "Elemento": ["Colaborador", "Colaboradores", "Nome", "Trabalhador", "Tecnico", "Técnico"],
            "Valor_Dia": ["Valor Dia", "Valor/Dia", "Custo_Dia", "Custo Dia", "Preco", "Preço", "Valor"]
        },
        pos_fallback=False
    )
    cols_e_orig = list(pd.DataFrame(pacote.get("Elementos", [])).columns)
    if "Elemento" not in elem_raw.columns or (elem_raw["Elemento"].astype(str).str.strip() == "").all():
        if len(cols_e_orig) >= 1 and cols_e_orig[0] not in ["Utilizador", "Senha", "Perfil"]:
            df_tmp = pd.DataFrame(pacote.get("Elementos", []))
            elem_raw["Elemento"] = df_tmp[cols_e_orig[0]]
            if len(cols_e_orig) >= 2 and cols_e_orig[1] not in ["Utilizador", "Senha", "Perfil"]:
                elem_raw["Valor_Dia"] = df_tmp[cols_e_orig[1]]

    elem = elem_raw[["Elemento", "Valor_Dia"]].copy()
    users = elem_raw[["Utilizador", "Senha", "Perfil"]].copy()

    meios = extrair(
        "Meios",
        ["Meio / Equipamento", "Valor_Dia"],
        {
            "Meio / Equipamento": ["Viatura", "Viaturas", "Meio", "Equipamento", "Matricula", "Matrícula", "Nome"],
            "Valor_Dia": ["Valor Dia", "Valor/Dia", "Custo_Dia", "Custo Dia", "Preco", "Preço", "Valor"]
        }
    )
    mat = extrair(
        "Materiais",
        ["Material", "Unidade", "Preco_Unitario"],
        {
            "Material": ["Nome", "Artigo", "Descricao", "Descrição", "Produto"],
            "Unidade": ["Un", "Un.", "Medida", "Unid"],
            "Preco_Unitario": ["Preco Unitario", "Preço Unitário", "Preco", "Preço", "Valor", "Valor_Unitario", "Custo"]
        }
    )
    diario = extrair(
        "Registos_Diarios",
        ["ID_Registo", "Data", "ID Obra", "Elemento", "Dias Elemento", "Custo Elemento",
         "Meio", "Dias Meio", "Custo Meio", "Material", "Qtd Material", "Custo Material", "Total do Dia", "Notas", "Dias Falta"],
        {"Elemento": ["Colaborador"], "Meio": ["Viatura"], "Dias Falta": ["Faltas", "Falta"]},
        pos_fallback=True,
        max_pos=14
    )
    return obras, elem, users, meios, mat, diario

def guardar_aba(url_script, aba, df):
    limpo = df.fillna("")
    linhas = [limpo.columns.tolist()] + limpo.values.tolist()
    r = requests.post(
        url_script,
        data=json.dumps({"sheet": aba, "rows": linhas}),
        headers={"Content-Type": "text/plain;charset=utf-8"},
        timeout=25
    )
    r.raise_for_status()

def enviar_ficheiro_drive(url_script, nome_fich, bytes_fich, mime_type="application/pdf"):
    b64 = base64.b64encode(bytes_fich).decode("utf-8")
    r = requests.post(
        url_script,
        data=json.dumps({
            "action": "upload_pdf",
            "filename": nome_fich,
            "mime": mime_type,
            "base64": b64
        }),
        headers={"Content-Type": "text/plain;charset=utf-8"},
        timeout=45
    )
    r.raise_for_status()
    resp = r.json()
    if "url" not in resp:
        raise ValueError(resp.get("error", "O Apps Script não devolveu o link do ficheiro."))
    return resp["url"]

def adicionar_fotos_obra(df_o, id_obra, lista_ficheiros, url_script):
    atuais = []
    if not df_o[df_o["ID Obra"] == id_obra].empty:
        atuais = separar_links_fotos(df_o.loc[df_o["ID Obra"] == id_obra, "Fotos"].iloc[0])
    novos = []
    for f in lista_ficheiros:
        mime = f.type if getattr(f, "type", "") else "image/jpeg"
        nome_f = f"FOTO_{id_obra}_{f.name}"
        url_f = enviar_ficheiro_drive(url_script, nome_f, f.getvalue(), mime_type=mime)
        novos.append(url_f)
    todos = atuais + novos
    df_o.loc[df_o["ID Obra"] == id_obra, "Fotos"] = " | ".join(todos)
    return len(novos)

def guardar_elementos_e_users(url_script, df_e, df_u):
    e_limpo = df_e[df_e["Elemento"].fillna("").astype(str).str.strip() != ""][["Elemento", "Valor_Dia"]].reset_index(drop=True)
    u_limpo = df_u[df_u["Utilizador"].fillna("").astype(str).str.strip() != ""][["Utilizador", "Senha", "Perfil"]].reset_index(drop=True)
    u_limpo["Perfil"] = u_limpo["Perfil"].fillna("").astype(str).str.strip()
    u_limpo.loc[u_limpo["Perfil"] == "", "Perfil"] = "Admin"
    u_limpo.loc[u_limpo["Utilizador"].str.lower() == "admin", "Perfil"] = "Admin"
    combinado = pd.concat([e_limpo, u_limpo], axis=1).fillna("")
    for col in ["Elemento", "Valor_Dia", "Utilizador", "Senha", "Perfil"]:
        if col not in combinado.columns:
            combinado[col] = ""
    guardar_aba(url_script, "Elementos", combinado[["Elemento", "Valor_Dia", "Utilizador", "Senha", "Perfil"]])

def recalcular_obras(url_script, df_o, df_d):
    o = df_o.copy()
    o["ID
