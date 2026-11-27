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
st.session_state.setdefault("novo_fundo_url", "")

def extrair_id_drive(url):
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", str(url))
    if m:
        return m.group(1)
    m2 = re.search(r"[?&]id=([a-zA-Z0-9_-]+)", str(url))
    return m2.group(1) if m2 else ""

@st.cache_data(show_spinner=False)
def obter_css_fundo(url_secreta=""):
    b64_img = ""
    ext = "jpeg"

    # 1. Tenta carregar imagem guardada no repositório GitHub (ou temporária)
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
        if img_path.lower().endswith(".png"):
            ext = "png"
        elif img_path.lower().endswith(".webp"):
            ext = "webp"
    # 2. Caso não exista no GitHub, carrega definitivamente a partir do link guardado nos Secrets
    elif url_secreta and str(url_secreta).strip().startswith("http"):
        url_clean = str(url_secreta).strip()
        fid = extrair_id_drive(url_clean)
        candidatos = (
            [
                f"https://drive.google.com/uc?export=download&id={fid}",
                f"https://drive.google.com/thumbnail?id={fid}&sz=w1600",
            ]
            if fid else [url_clean]
        )
        for u in candidatos:
            try:
                resp = requests.get(u, timeout=15)
                ctype = resp.headers.get("Content-Type", "").lower()
                if resp.status_code == 200 and resp.content and not resp.content[:15].lstrip().startswith(b"<"):
                    b64_img = base64.b64encode(resp.content).decode("utf-8")
                    if "png" in ctype:
                        ext = "png"
                    elif "webp" in ctype:
                        ext = "webp"
                    else:
                        ext = "jpeg"
                    break
            except Exception:
                continue

    if b64_img:
        return f"""
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
        """
    return ""

url_fundo_sec = st.secrets["fundo_url"] if "fundo_url" in st.secrets else ""
css_bg = obter_css_fundo(url_fundo_sec)
if css_bg:
    st.markdown(css_bg, unsafe_allow_html=True)

MESES = {
    1: "01 - Janeiro", 2: "02 - Fevereiro", 3: "03 - Março", 4: "04 - Abril",
    5: "05 - Maio", 6: "06 - Junho", 7: "07 - Julho", 8: "08 - Agosto",
    9: "09 - Setembro", 10: "10 - Outubro", 11: "11 - Novembro", 12: "12 - Dezembro"
}

ESTADOS_OBRA = ["Nova", "Execução", "Parcial", "Concluída"]

def separar_links_fotos(texto_fotos):
    if not texto_fotos:
        return []
    partes = [p.strip() for p in str(texto_fotos).replace("\n", "|").split("|")]
    return [p for p in partes if p.startswith("http")]

def mostrar_anexos_obra(obra_id, nome_obra, url_pdf, texto_fotos, prefixo="anx"):
    url_limpo = str(url_pdf).strip()
    lista_fotos = separar_links_fotos(texto_fotos)

    if url_limpo.startswith("http"):
        fid = extrair_id_drive(url_limpo)
        st.markdown(f"**📎 Documento / Projeto da Obra ({obra_id})**")
        b1, b2 = st.columns(2)
        b1.link_button("📄 Abrir PDF noutra aba", url_limpo, type="primary", use_container_width=True)
        if fid:
            b2.link_button("📥 Descarregar PDF", f"https://drive.google.com/uc?export=download&id={fid}", use_container_width=True)
            if st.toggle("👁️ Consultar PDF diretamente aqui na aplicação", key=f"{prefixo}_pdf_{obra_id}"):
                components.iframe(f"https://drive.google.com/file/d/{fid}/preview", height=520, scrolling=True)
    else:
        st.caption(f"ℹ️ A obra {obra_id} ({nome_obra}) não tem ficheiro PDF anexado.")

    if lista_fotos:
        if st.toggle(f"🖼️ Ver Fotografias da Obra ({len(lista_fotos)} foto(s))", key=f"{prefixo}_ft_{obra_id}"):
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

def df_igual(df1, df2):
    try:
        a = df1.fillna("").astype(str).apply(lambda s: s.str.strip()).reset_index(drop=True)
        b = df2.fillna("").astype(str).apply(lambda s: s.str.strip()).reset_index(drop=True)
        return a.equals(b)
    except Exception:
        return False

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
    reg_cli = df_diario_all[df_diario_all["ID Obra"].isin(ids_cli)] if not df_diario_all.empty else pd.DataFrame()
    custos_por_obra = (
        reg_cli.groupby("ID Obra")[["Custo Elemento", "Custo Meio", "Custo Material"]].sum().to_dict("index")
        if not reg_cli.empty else {}
    )

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
        ("ID Obra", 24, "L"), ("Nome da Obra", 63, "L"), ("Cliente", 34, "L"),
        ("Estado", 22, "C"), ("Adjudicado", 27, "R"), ("Colab.", 25, "R"),
        ("Viaturas", 25, "R"), ("Materiais", 25, "R"), ("Saldo", 32, "R")
    ]
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(219, 234, 254)
    for cab, larg, al in cols:
        pdf.cell(larg, 7, cab, 1, align=al, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 7.5)
    for _, r in df_obras_cli.iterrows():
        oid = str(r["ID Obra"])
        c_ob = custos_por_obra.get(oid, {})
        c_col = float(c_ob.get("Custo Elemento", 0.0))
        c_via = float(c_ob.get("Custo Meio", 0.0))
        c_mat = float(c_ob.get("Custo Material", 0.0))
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

def gerar_pdf_presencas(cfg, mes_n, ano_n, colab_f, quadro_res, semanas_mes, mapa_dia):
    pdf = FPDF(orientation="L", unit="mm", format="A4")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    tit = f"{cfg['pdf_cab']} | MAPA DE PRESENCAS E FALTAS - {MESES[mes_n].upper()} / {ano_n}" + (f" ({colab_f})" if colab_f != "Todos" else "")
    pdf.cell(0, 8, txt_pdf(tit, 95), ln=True, align="C")
    pdf.ln(2)

    pdf.set_font("Helvetica", "B", 8)
    for cab, larg, al in [("Colaborador", 70, "L"), ("Dias Uteis", 26, "C"), ("Sab / Dom", 28, "C"), ("Total Trab.", 26, "C"), ("Faltas", 22, "C"), ("Obras", 105, "L")]:
        pdf.cell(larg, 6, cab, 1, align=al)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8)
    for _, r in quadro_res.iterrows():
        pdf.cell(70, 6, txt_pdf(r["Colaborador"], 35), 1)
        pdf.cell(26, 6, f"{r['Dias Úteis']:.1f}", 1, align="C")
        pdf.cell(28, 6, f"{r['Sáb / Dom']:.1f}", 1, align="C")
        pdf.cell(26, 6, f"{r['Total Dias']:.1f}", 1, align="C")
        pdf.cell(22, 6, f"{r['Faltas']:.1f}", 1, align="C")
        pdf.cell(105, 6, txt_pdf(r["Obras"], 52), 1)
        pdf.ln()

    pdf.ln(4)
    cab_sem = ["Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado (FDS)", "Domingo (FDS)"]
    larg_c = 39.5
    pdf.set_font("Helvetica", "B", 8)
    for i, ds in enumerate(cab_sem):
        pdf.set_fill_color(254, 243, 199) if i >= 5 else pdf.set_fill_color(241, 245, 249)
        pdf.cell(larg_c, 6, ds, 1, align="C", fill=True)
    pdf.ln()

    alt_disp = max(90.0, 195.0 - pdf.get_y())
    alt_lin = max(16.0, alt_disp / max(len(semanas_mes), 1))
    for sem in semanas_mes:
        x0, y0 = pdf.get_x(), pdf.get_y()
        for i, d in enumerate(sem):
            xc = x0 + i * larg_c
            pdf.set_xy(xc, y0)
            if d == 0:
                pdf.set_fill_color(248, 250, 252)
                pdf.cell(larg_c, alt_lin, "", 1, fill=True)
            else:
                pdf.set_fill_color(255, 251, 235) if i >= 5 else pdf.set_fill_color(255, 255, 255)
                pdf.rect(xc, y0, larg_c, alt_lin, style="DF")
                pdf.set_xy(xc + 1.5, y0 + 1)
                pdf.set_font("Helvetica", "B", 8)
                pdf.cell(larg_c - 3, 4, str(d))
                itens_d = mapa_dia.get(d, [])
                if itens_d:
                    pdf.set_xy(xc + 1.5, y0 + 5)
                    pdf.set_font("Helvetica", "", 6.5)
                    bloco = "\n".join(itens_d[:4]) + (f"\n+{len(itens_d)-4}..." if len(itens_d) > 4 else "")
                    pdf.multi_cell(larg_c - 3, 3.1, txt_pdf(bloco, 140))
        pdf.set_xy(x0, y0 + alt_lin)
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

def converter_datas(serie):
    s = serie.fillna("").astype(str).str.strip()
    iso = s.str.match(r"^\d{4}-\d{2}-\d{2}")
    res = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    if iso.any():
        res.loc[iso] = pd.to_datetime(s[iso], format="mixed", errors="coerce", utc=True).dt.tz_localize(None).dt.round("D")
    if (~iso).any():
        res.loc[~iso] = pd.to_datetime(s[~iso], format="mixed", dayfirst=True, errors="coerce").dt.round("D")
    return res

@st.cache_data(ttl=300, show_spinner=False)
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

    for col in ["ID Obra", "Nome da Obra", "Cliente", "Estado", "PDF", "Fotos"]:
        obras[col] = obras[col].fillna("").astype(str).str.strip()
    obras["ID Obra"] = obras["ID Obra"].str.replace(r"\.0$", "", regex=True)
    obras["Estado"] = obras["Estado"].apply(normalizar_estado)
    sem_id_obra = (obras["ID Obra"] == "") & (obras["Nome da Obra"] != "")
    if sem_id_obra.any():
        obras.loc[sem_id_obra, "ID Obra"] = [f"OB-{i+1:02d}" for i in obras[sem_id_obra].index]
    for col in ["Valor Adjudicado", "Total Gasto", "Saldo Restante"]:
        obras[col] = pd.to_numeric(obras[col], errors="coerce").fillna(0.0)
    obras = obras[obras["ID Obra"] != ""].copy()

    elem["Elemento"] = elem["Elemento"].fillna("").astype(str).str.strip()
    elem["Valor_Dia"] = pd.to_numeric(elem["Valor_Dia"], errors="coerce").fillna(0.0)
    elem = elem[elem["Elemento"] != ""].copy()

    for col in ["Utilizador", "Senha", "Perfil"]:
        users[col] = users[col].fillna("").astype(str).str.strip()
    users["Senha"] = users["Senha"].str.replace(r"\.0$", "", regex=True)
    users.loc[users["Perfil"] == "", "Perfil"] = "Admin"
    users = users[users["Utilizador"] != ""].copy()
    if users.empty:
        users = pd.DataFrame([{"Utilizador": "admin", "Senha": "1234", "Perfil": "Admin"}])

    meios["Meio / Equipamento"] = meios["Meio / Equipamento"].fillna("").astype(str).str.strip()
    meios["Valor_Dia"] = pd.to_numeric(meios["Valor_Dia"], errors="coerce").fillna(0.0)
    meios = meios[meios["Meio / Equipamento"] != ""].copy()

    for col in ["Material", "Unidade"]:
        mat[col] = mat[col].fillna("").astype(str).str.strip()
    mat["Preco_Unitario"] = pd.to_numeric(mat["Preco_Unitario"], errors="coerce").fillna(0.0)
    mat = mat[mat["Material"] != ""].copy()

    for col in ["Data", "ID Obra", "Elemento", "Meio", "Material", "Notas"]:
        diario[col] = diario[col].fillna("").astype(str).str.strip()
    diario["ID Obra"] = diario["ID Obra"].str.replace(r"\.0$", "", regex=True)
    for col in ["Dias Elemento", "Custo Elemento", "Dias Meio", "Custo Meio", "Qtd Material", "Custo Material", "Total do Dia", "Dias Falta"]:
        diario[col] = pd.to_numeric(diario[col], errors="coerce").fillna(0.0)
    diario["Data_dt"] = converter_datas(diario["Data"])

    return obras, elem, users, meios, mat, diario

def guardar_aba(url_script, aba, df):
    limpo = df.drop(columns=["Data_dt"], errors="ignore").fillna("")
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
    o["ID Obra"] = o["ID Obra"].fillna("").astype(str).str.strip()
    o["Nome da Obra"] = o["Nome da Obra"].fillna("").astype(str).str.strip()
    o["Estado"] = o["Estado"].apply(normalizar_estado)
    for col_extra in ["PDF", "Fotos"]:
        if col_extra not in o.columns:
            o[col_extra] = ""
        o[col_extra] = o[col_extra].fillna("").astype(str).str.strip()
    sem_id = (o["ID Obra"] == "") & (o["Nome da Obra"] != "")
    if sem_id.any():
        o.loc[sem_id, "ID Obra"] = [f"OB-{idx+1:02d}" for idx in o[sem_id].index]
    o["Valor Adjudicado"] = pd.to_numeric(o["Valor Adjudicado"], errors="coerce").fillna(0.0)
    gastos = {}
    if not df_d.empty:
        d = df_d.copy()
        d["ID Obra"] = d["ID Obra"].fillna("").astype(str).str.strip()
        d["Total do Dia"] = pd.to_numeric(d["Total do Dia"], errors="coerce").fillna(0.0)
        gastos = d.groupby("ID Obra")["Total do Dia"].sum().to_dict()
    o["Total Gasto"] = o["ID Obra"].map(gastos).fillna(0.0)
    o["Saldo Restante"] = o["Valor Adjudicado"] - o["Total Gasto"]
    cols_ordem = ["ID Obra", "Nome da Obra", "Cliente", "Valor Adjudicado", "Total Gasto", "Saldo Restante", "Estado", "PDF", "Fotos"]
    guardar_aba(url_script, "Obras", o[cols_ordem])

# ==========================================
# ECRÃ DE LOGIN COM ESCOLHA DE SETOR
# ==========================================
if not st.session_state["usr_nome"]:
    setor_sel = st.radio(
        "Escolher Setor",
        ["🗼 Rede Móvel", "⚡ Eletricidade"],
        index=0 if "Rede" in st.session_state["setor"] else 1,
        horizontal=True
    )
    st.session_state["setor"] = setor_sel
    cfg_login = obter_config_setor(setor_sel)

    st.title(cfg_login["titulo"])
    st.subheader("🔐 Iniciar Sessão")

    with st.form("form_login"):
        u_in = st.text_input("Utilizador")
        s_in = st.text_input("Senha / PIN", type="password")
        entrar = st.form_submit_button(f"Entrar em {setor_sel}", type="primary", use_container_width=True)

    if entrar:
        chave_sec = cfg_login["secret_key"]
        if chave_sec not in st.secrets:
            st.error(f"Falta adicionar '{chave_sec}' nos Secrets do Streamlit para ligar à base de dados de {setor_sel}.")
            st.stop()

        url_login = st.secrets[chave_sec]
        u_clean = u_in.strip().lower()
        s_clean = s_in.strip()
        if u_clean == "admin" and s_clean == "1234":
            st.session_state["usr_nome"] = "admin"
            st.session_state["usr_perfil"] = "Admin"
            st.rerun()
        else:
            try:
                _, _, df_u_login, _, _, _ = ler_servidor(url_login)
                match = df_u_login[(df_u_login["Utilizador"].str.lower() == u_clean) & (df_u_login["Senha"] == s_clean)]
                if not match.empty:
                    nome_u = match.iloc[0]["Utilizador"]
                    perf = match.iloc[0]["Perfil"].strip().lower()
                    st.session_state["usr_nome"] = nome_u
                    if u_clean == "admin" or perf in ["admin", "administrador", ""]:
                        st.session_state["usr_perfil"] = "Admin"
                    else:
                        st.session_state["usr_perfil"] = "Diário"
                    st.rerun()
                else:
                    st.error("Utilizador ou senha incorretos.")
            except Exception as e:
                st.error(f"Erro ao ligar à folha Google ({setor_sel}): {e}")
    st.stop()

# ==========================================
# CABEÇALHO E CARREGAMENTO DE DADOS (CACHE 5 MIN)
# ==========================================
cfg = obter_config_setor(st.session_state["setor"])
chave_ativa = cfg["secret_key"]

if chave_ativa not in st.secrets:
    st.error(f"Falta configurar '{chave_ativa}' nos Secrets do Streamlit.")
    if st.button("⬅️ Voltar ao Login"):
        st.session_state["usr_nome"] = ""
        st.rerun()
    st.stop()

url_ativa = st.secrets[chave_ativa]

ct1, ct2, ct3 = st.columns([3, 1, 1])
ct1.title(cfg["titulo"])
if ct2.button("🔄 Atualizar", use_container_width=True, help="Sincronizar novamente com a folha Google"):
    ler_servidor.clear()
    st.rerun()
if ct3.button(f"🚪 Sair ({st.session_state['usr_nome']})", use_container_width=True):
    st.session_state["usr_nome"] = ""
    st.session_state["usr_perfil"] = ""
    st.rerun()

try:
    df_obras, df_elem, df_users, df_meios, df_mat, df_diario = ler_servidor(url_ativa)
except Exception as erro:
    st.error(f"Erro ao ligar à folha Google ({st.session_state['setor']}): {erro}")
    if st.button("🔄 Tentar novamente"):
        ler_servidor.clear()
        st.rerun()
    st.stop()

preco_colab = dict(zip(df_elem["Elemento"], df_elem["Valor_Dia"]))
preco_meio = dict(zip(df_meios["Meio / Equipamento"], df_meios["Valor_Dia"]))
preco_mat = dict(zip(df_mat["Material"], df_mat["Preco_Unitario"]))
unid_mat = dict(zip(df_mat["Material"], df_mat["Unidade"]))
nomes_obras = dict(zip(df_obras["ID Obra"], df_obras["Nome da Obra"]))
estados_obras = dict(zip(df_obras["ID Obra"], df_obras["Estado"]))
pdfs_obras = dict(zip(df_obras["ID Obra"], df_obras["PDF"]))
fotos_obras = dict(zip(df_obras["ID Obra"], df_obras["Fotos"]))

if st.session_state["aviso"]:
    st.success(st.session_state["aviso"])
    st.session_state["aviso"] = ""

is_admin = (st.session_state["usr_perfil"] == "Admin") or (st.session_state["usr_nome"].strip().lower() == "admin")

if is_admin:
    aba = st.radio("Navegação", ["📝 Diário", "👷 Presenças", "💰 Contas", "⚙️ Tabelas"], horizontal=True, label_visibility="collapsed")
else:
    st.caption(f"👤 Sessão iniciada como **{st.session_state['usr_nome']}** ({st.session_state['setor']} — Registo Diário)")
    aba = "📝 Diário"
st.divider()

def etiqueta_obra(x):
    tag_pdf = " 📎PDF" if str(pdfs_obras.get(x, "")).startswith("http") else ""
    qtd_f = len(separar_links_fotos(fotos_obras.get(x, "")))
    tag_ft = f" 📷{qtd_f}" if qtd_f > 0 else ""
    return f"{x} — {nomes_obras.get(x, '')} [{estados_obras.get(x, '')}]{tag_pdf}{tag_ft}"

# ==========================================
# 1. DIÁRIO DE OBRA (SEM OBRAS CONCLUÍDAS + FALTAS)
# ==========================================
if aba == "📝 Diário":
    k = st.session_state["ciclo"]
    obras_disp = df_obras[~df_obras["Estado"].str.lower().isin(["concluída", "concluida"])]
    clientes_ativos = sorted([c for c in obras_disp["Cliente"].unique().tolist() if c])

    if clientes_ativos:
        cli_f = st.selectbox("👤 Cliente", ["Todos"] + clientes_ativos, key="d_cli")
        if cli_f != "Todos":
            obras_disp = obras_disp[obras_disp["Cliente"] == cli_f]

    ids_disp = obras_disp["ID Obra"].tolist()
    obra_sel = st.selectbox("🏢 Obra", ids_disp, format_func=etiqueta_obra) if ids_disp else None

    if not obra_sel:
        st.info("Sem obras ativas disponíveis no Diário (as obras concluídas estão ocultas).")
    else:
        mostrar_anexos_obra(
            obra_sel,
            nomes_obras.get(obra_sel, ""),
            pdfs_obras.get(obra_sel, ""),
            fotos_obras.get(obra_sel, ""),
            prefixo="d"
        )
        st.divider()

    dt_reg = st.date_input("📅 Data", value=date.today())

    eq_sel = st.multiselect("👷 Colaboradores em Obra (regista presença)", list(preco_colab.keys()), placeholder="Escolher colaboradores...", key=f"eq_{k}")
    dias_eq = {}
    for n in eq_sel:
        c1, c2 = st.columns([2, 1])
        c1.markdown(f"**{n}**")
        dias_eq[n] = c2.number_input("Dias", 0.0, value=1.0, step=0.5, label_visibility="collapsed", key=f"de_{n}_{k}")

    ft_sel = st.multiselect("🚫 Faltas de Colaboradores (regista ausência)", list(preco_colab.keys()), placeholder="Escolher colaboradores em falta...", key=f"ft_col_{k}")
    dias_ft = {}
    motivo_ft = {}
    for n in ft_sel:
        c1, c2, c3 = st.columns([2, 1, 2])
        c1.markdown(f"**{n}** *(Falta)*")
        dias_ft[n] = c2.number_input("Dias Falta", 0.0, value=1.0, step=0.5, label_visibility="collapsed", key=f"df_{n}_{k}")
        motivo_ft[n] = c3.text_input("Motivo", placeholder="Motivo (opcional)...", label_visibility="collapsed", key=f"mf_{n}_{k}")

    vi_sel = st.multiselect("🚚 Viaturas / Meios", list(preco_meio.keys()), placeholder="Escolher viaturas...", key=f"vi_{k}")
    dias_vi = {}
    for n in vi_sel:
        c1, c2 = st.columns([2, 1])
        c1.markdown(f"**{n}**")
        dias_vi[n] = c2.number_input("Dias", 0.0, value=1.0, step=0.5, label_visibility="collapsed", key=f"dv_{n}_{k}")

    mt_sel = st.multiselect(
        "📦 Material Aplicado",
        list(preco_mat.keys()),
        format_func=lambda m: f"{m} ({unid_mat[m]})" if unid_mat.get(m) else m,
        placeholder="Escolher materiais...",
        key=f"mt_{k}"
    )
    qtd_mt = {}
    for n in mt_sel:
        c1, c2 = st.columns([2, 1])
        u = unid_mat.get(n, "")
        c1.markdown(f"**{n}** ({u})" if u else f"**{n}**")
        qtd_mt[n] = c2.number_input("Qtd", 0.0, value=1.0, step=1.0, label_visibility="collapsed", key=f"qm_{n}_{k}")

    obs = st.text_input("📝 Notas / Trabalhos realizados", key=f"ob_{k}")

    fotos_diario = st.file_uploader(
        "📷 Anexar Fotografias da Obra (podes tirar foto ou escolher várias)",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key=f"ft_d_{k}"
    )

    if st.button("💾 Gravar Registo Diário", type="primary", use_container_width=True):
        if not obra_sel:
            st.error("Seleciona uma obra ativa.")
        elif not eq_sel and not ft_sel and not vi_sel and not mt_sel and not obs.strip() and not fotos_diario:
            st.error("Preenche pelo menos um campo ou adiciona uma fotografia.")
        else:
            with st.spinner("A gravar registo..."):
                try:
                    obras_edit = df_obras.copy()
                    n_fotos = 0
                    if fotos_diario:
                        n_fotos = adicionar_fotos_obra(obras_edit, obra_sel, fotos_diario, url_ativa)

                    l_eq = [(c, dias_eq[c]) for c in eq_sel if dias_eq[c] > 0]
                    l_ft = [(c, dias_ft[c], motivo_ft[c].strip()) for c in ft_sel if dias_ft[c] > 0]
                    l_vi = [(v, dias_vi[v]) for v in vi_sel if dias_vi[v] > 0]
                    l_mt = [(m, qtd_mt[m]) for m in mt_sel if qtd_mt[m] > 0]

                    max_id = pd.to_numeric(df_diario["ID_Registo"], errors="coerce").max()
                    prox = int(0 if pd.isna(max_id) else max_id) + 1
                    dt_iso = dt_reg.strftime("%Y-%m-%d")
                    linhas_novas = []

                    tem_principal = bool(l_eq or l_vi or l_mt or obs.strip())
                    if tem_principal:
                        for i in range(max(len(l_eq), len(l_vi), len(l_mt), 1)):
                            en, ed = l_eq[i] if i < len(l_eq) else ("", 0.0)
                            vn, vd = l_vi[i] if i < len(l_vi) else ("", 0.0)
                            mn, mq = l_mt[i] if i < len(l_mt) else ("", 0.0)
                            ce, cv, cm = preco_colab.get(en, 0.0) * ed, preco_meio.get(vn, 0.0) * vd, preco_mat.get(mn, 0.0) * mq
                            linhas_novas.append({
                                "ID_Registo": prox, "Data": dt_iso, "ID Obra": obra_sel,
                                "Elemento": en, "Dias Elemento": ed, "Custo Elemento": ce,
                                "Meio": vn, "Dias Meio": vd, "Custo Meio": cv,
                                "Material": mn, "Qtd Material": mq, "Custo Material": cm,
                                "Total do Dia": ce + cv + cm, "Notas": obs if i == 0 else "",
                                "Dias Falta": 0.0
                            })
                            prox += 1

                    for fn, fd, fmot in l_ft:
                        nota_f = f"FALTA ({fmot})" if fmot else "FALTA"
                        linhas_novas.append({
                            "ID_Registo": prox, "Data": dt_iso, "ID Obra": obra_sel,
                            "Elemento": fn, "Dias Elemento": 0.0, "Custo Elemento": 0.0,
                            "Meio": "", "Dias Meio": 0.0, "Custo Meio": 0.0,
                            "Material": "", "Qtd Material": 0.0, "Custo Material": 0.0,
                            "Total do Dia": 0.0, "Notas": nota_f,
                            "Dias Falta": fd
                        })
                        prox += 1

                    if linhas_novas:
                        atualizado = pd.concat([df_diario.drop(columns=["Data_dt"], errors="ignore"), pd.DataFrame(linhas_novas)], ignore_index=True)
                        guardar_aba(url_ativa, "Registos_Diarios", atualizado)
                    else:
                        atualizado = df_diario

                    recalcular_obras(url_ativa, obras_edit, atualizado)
                    ler_servidor.clear()
                    st.session_state["ciclo"] += 1
                    msg_ft = f", {len(l_ft)} falta(s)" if l_ft else ""
                    msg_foto = f" e {n_fotos} foto(s)" if n_fotos else ""
                    st.session_state["aviso"] = f"Gravado ({len(l_eq)} presença(s){msg_ft}{msg_foto})!"
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao gravar: {e}")

    if obra_sel:
        st.divider()
        h_obra = df_diario[df_diario["ID Obra"] == obra_sel].sort_values("Data_dt", ascending=False).copy()
        h_obra["Data"] = h_obra["Data_dt"].dt.strftime("%d/%m/%Y").fillna(h_obra["Data"])
        cols_h = ["ID_Registo", "Data", "Elemento", "Dias Elemento", "Dias Falta", "Meio", "Dias Meio", "Material", "Qtd Material", "Notas"]

        if is_admin:
            st.subheader("Histórico da Obra (Edição Admin)")
            ed_h = st.data_editor(h_obra[cols_h], num_rows="dynamic", use_container_width=True, hide_index=True, disabled=["ID_Registo"])
            if st.button("Atualizar Histórico / Apagar Linhas", use_container_width=True):
                ed = ed_h.copy()
                ed["Data"] = converter_datas(ed["Data"]).dt.strftime("%Y-%m-%d").fillna(ed["Data"].astype(str))
                ed["ID Obra"] = obra_sel
                for cn in ["Dias Elemento", "Dias Falta", "Dias Meio", "Qtd Material"]:
                    ed[cn] = pd.to_numeric(ed[cn], errors="coerce").fillna(0.0)
                ed["Custo Elemento"] = ed.apply(lambda r: preco_colab.get(str(r["Elemento"]), 0.0) * r["Dias Elemento"], axis=1)
                ed["Custo Meio"] = ed.apply(lambda r: preco_meio.get(str(r["Meio"]), 0.0) * r["Dias Meio"], axis=1)
                ed["Custo Material"] = ed.apply(lambda r: preco_mat.get(str(r["Material"]), 0.0) * r["Qtd Material"], axis=1)
                ed["Total do Dia"] = ed["Custo Elemento"] + ed["Custo Meio"] + ed["Custo Material"]
                cols_save = [c for c in df_diario.columns if c != "Data_dt"]
                final = pd.concat([df_diario[df_diario["ID Obra"] != obra_sel][cols_save], ed[cols_save]], ignore_index=True)
                guardar_aba(url_ativa, "Registos_Diarios", final)
                recalcular_obras(url_ativa, df_obras, final)
                ler_servidor.clear()
                st.session_state["aviso"] = "Histórico atualizado!"
                st.rerun()
        else:
            st.subheader("📋 Histórico da Obra (Apenas Consulta)")
            if not h_obra.empty:
                cols_consulta = ["Data", "Elemento", "Dias Elemento", "Dias Falta", "Meio", "Dias Meio", "Material", "Qtd Material", "Notas"]
                st.dataframe(
                    h_obra[cols_consulta].rename(columns={
                        "Elemento": "Colaborador", "Dias Elemento": "Dias Col.", "Dias Falta": "Faltas",
                        "Meio": "Viatura", "Dias Meio": "Dias Viat.", "Qtd Material": "Qtd"
                    }),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Ainda não existem registos diários nesta obra.")

# ==========================================
# 2. PRESENÇAS E FALTAS (CALENDÁRIO + FINS DE SEMANA À PARTE)
# ==========================================
elif aba == "👷 Presenças":
    st.subheader("👷 Mapa de Presenças e Faltas")
    base_pt = df_diario[(df_diario["Elemento"] != "") & (df_diario["Data_dt"].notna())]

    hoje = date.today()
    anos_pt = sorted(set([hoje.year - 1, hoje.year, hoje.year + 1] + (base_pt["Data_dt"].dt.year.tolist() if not base_pt.empty else [])))
    lista_eq = sorted(set(list(preco_colab.keys()) + (base_pt["Elemento"].unique().tolist() if not base_pt.empty else [])))

    c1, c2, c3 = st.columns([2, 1, 2])
    mes_n = c1.selectbox("📅 Mês", list(MESES.keys()), index=hoje.month - 1, format_func=lambda m: MESES[m], key="pt_m")
    ano_n = c2.selectbox("Ano", anos_pt, index=anos_pt.index(hoje.year), key="pt_a")
    colab_f = c3.selectbox("👷 Colaborador", ["Todos"] + lista_eq, key="pt_c")

    flt = base_pt[(base_pt["Data_dt"].dt.year == ano_n) & (base_pt["Data_dt"].dt.month == mes_n)].copy()
    if colab_f != "Todos":
        flt = flt[flt["Elemento"] == colab_f]

    flt["FDS"] = flt["Data_dt"].dt.dayofweek >= 5
    flt["Uteis"] = flt["Dias Elemento"].where(~flt["FDS"], 0.0)
    flt["SabDom"] = flt["Dias Elemento"].where(flt["FDS"], 0.0)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Dias Úteis (Seg–Sex)", f"{float(flt['Uteis'].sum()):.1f} d")
    k2.metric("Fim de Semana (Sáb/Dom)", f"{float(flt['SabDom'].sum()):.1f} d")
    k3.metric("Total Trabalhado", f"{float(flt['Dias Elemento'].sum()):.1f} d")
    k4.metric("Faltas", f"{float(flt['Dias Falta'].sum()):.1f} d")

    if not flt.empty:
        quadro_res = flt.groupby("Elemento", as_index=False).agg(
            **{
                "Dias Úteis": ("Uteis", "sum"),
                "Sáb / Dom": ("SabDom", "sum"),
                "Total Dias": ("Dias Elemento", "sum"),
                "Faltas": ("Dias Falta", "sum"),
                "Obras": ("ID Obra", lambda s: ", ".join(sorted(set(s.astype(str)))))
            }
        ).rename(columns={"Elemento": "Colaborador"})
        st.dataframe(quadro_res, use_container_width=True, hide_index=True)

    mapa_dia = {}
    if not flt.empty:
        ag = flt.groupby([flt["Data_dt"].dt.day, "Elemento", "ID Obra"], as_index=False)[["Dias Elemento", "Dias Falta"]].sum()
        for _, r in ag.iterrows():
            dn = int(r["Data_dt"])
            alvo = r["Elemento"] if colab_f == "Todos" else r["ID Obra"]
            if r["Dias Elemento"] > 0:
                mapa_dia.setdefault(dn, []).append(f"{alvo} ({r['Dias Elemento']:.1f}d)")
            if r["Dias Falta"] > 0:
                mapa_dia.setdefault(dn, []).append(f"{alvo} (FALTA {r['Dias Falta']:.1f}d)")

    semanas_mes = calendar.monthcalendar(ano_n, mes_n)
    nomes_sem = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    grelha = []
    for sem in semanas_mes:
        linha = {}
        for idx, d in enumerate(sem):
            if d == 0:
                linha[nomes_sem[idx]] = ""
            else:
                itens = " • ".join(mapa_dia.get(d, []))
                linha[nomes_sem[idx]] = f"Dia {d:02d}: {itens}" if itens else f"Dia {d:02d}"
        grelha.append(linha)

    df_calendario = pd.DataFrame(grelha, index=[f"Sem. {i}" for i in range(1, len(semanas_mes) + 1)])

    def pintar_util(v):
        s = str(v)
        if not s:
            return "background-color: #f8fafc; color: #94a3b8;"
        if ":" in s:
            if "FALTA" in s and "d)" not in s.replace("FALTA ", ""):
                return "background-color: #fee2e2; color: #991b1b; font-weight: 700;"
            return "background-color: #dbeafe; color: #1e3a8a; font-weight: 700;"
        return "color: #475569;"

    def pintar_fds(v):
        s = str(v)
        if not s:
            return "background-color: #f8fafc; color: #94a3b8;"
        if ":" in s:
            if "FALTA" in s and "d)" not in s.replace("FALTA ", ""):
                return "background-color: #fee2e2; color: #991b1b; font-weight: 700;"
            return "background-color: #fde68a; color: #78350f; font-weight: 700;"
        return "background-color: #fffbeb; color: #b45309;"

    est_cal = df_calendario.style
    if hasattr(est_cal, "map"):
        est_cal = est_cal.map(pintar_util, subset=["Seg", "Ter", "Qua", "Qui", "Sex"]).map(pintar_fds, subset=["Sáb", "Dom"])
    else:
        est_cal = est_cal.applymap(pintar_util, subset=["Seg", "Ter", "Qua", "Qui", "Sex"]).applymap(pintar_fds, subset=["Sáb", "Dom"])

    st.markdown(f"**🗓️ Calendário Mensal — {MESES[mes_n]} / {ano_n}**")
    st.dataframe(est_cal, use_container_width=True)

    if not flt.empty:
        with st.expander("Ver lista detalhada por dia, faltas e notas"):
            det = flt.sort_values(["Data_dt", "Elemento"]).copy()
            det["Data"] = det["Data_dt"].dt.strftime("%d/%m/%Y")
            det["Tipo"] = det.apply(
                lambda r: "Falta" if r["Dias Falta"] > 0 and r["Dias Elemento"] == 0 else ("Fim de Semana" if r["FDS"] else "Dia Útil"),
                axis=1
            )
            st.dataframe(
                det[["Data", "Tipo", "Elemento", "ID Obra", "Dias Elemento", "Dias Falta", "Notas"]].rename(
                    columns={"Elemento": "Colaborador", "Dias Elemento": "Dias Trab.", "Dias Falta": "Faltas"}
                ),
                use_container_width=True,
                hide_index=True
            )

        if st.button("📄 Preparar PDF de Presenças e Faltas", use_container_width=True):
            pdf_pt_bytes = gerar_pdf_presencas(cfg, mes_n, ano_n, colab_f, quadro_res, semanas_mes, mapa_dia)
            st.download_button(
                "📥 Descarregar Calendário de Presenças e Faltas (PDF)",
                pdf_pt_bytes,
                file_name=f"Presencas_{cfg['pdf_tag']}_{mes_n:02d}_{ano_n}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )
    else:
        st.info(f"Sem presenças ou faltas registadas em {MESES[mes_n]} de {ano_n}.")

# ==========================================
# 3. CONTAS (POR CLIENTE, ESTADO E OBRA + RELATÓRIOS PDF)
# ==========================================
elif aba == "💰 Contas":
    st.subheader("💰 Contas e Orçamentos")
    obras_ct = df_obras.copy()
    clientes_todos = sorted([c for c in df_obras["Cliente"].unique().tolist() if c])

    fc1, fc2 = st.columns(2)
    cli_c = fc1.selectbox("👤 Cliente", ["Todos"] + clientes_todos, key="c_cli") if clientes_todos else "Todos"
    est_c = fc2.multiselect("📌 Estado da Obra", ESTADOS_OBRA, default=ESTADOS_OBRA, key="c_est")

    if cli_c != "Todos":
        obras_ct = obras_ct[obras_ct["Cliente"] == cli_c]
    if est_c:
        obras_ct = obras_ct[obras_ct["Estado"].isin(est_c)]

    if not obras_ct.empty:
        adj_c = float(obras_ct["Valor Adjudicado"].sum())
        gas_c = float(obras_ct["Total Gasto"].sum())
        lbl_esc = f"Cliente: {cli_c}" if cli_c != "Todos" else "Todos os Clientes"
        st.caption(f"Resumo ({lbl_esc} | {len(obras_ct)} obra(s))")
        c1, c2, c3 = st.columns(3)
        c1.metric("Adjudicado", f"{adj_c:,.2f} €")
        c2.metric("Total Gasto", f"{gas_c:,.2f} €")
        c3.metric("Saldo", f"{adj_c - gas_c:,.2f} €")

        lbl_btn_cli = f"📄 Preparar Relatório de Contas por Cliente ({cli_c})" if cli_c != "Todos" else "📄 Preparar Relatório Geral (Todos os Clientes)"
        if st.button(lbl_btn_cli, use_container_width=True):
            pdf_cli_bytes = gerar_pdf_contas_cliente(cfg, cli_c, est_c, obras_ct, df_diario)
            tag_cli_nome = "Todos_Clientes" if cli_c == "Todos" else re.sub(r"[^a-zA-Z0-9_-]", "_", cli_c)
            st.download_button(
                "📥 Descarregar Relatório por Cliente (PDF)",
                pdf_cli_bytes,
                file_name=f"Contas_Cliente_{cfg['pdf_tag']}_{tag_cli_nome}_{date.today()}.pdf",
                mime="application/pdf",
                type="primary",
                use_container_width=True
            )
        st.divider()

    ids_ct = obras_ct["ID Obra"].tolist()
    if ids_ct:
        ob_c = st.selectbox("🏢 Obra", ids_ct, format_func=etiqueta_obra, key="c_ob")
        mostrar_anexos_obra(
            ob_c,
            nomes_obras.get(ob_c, ""),
            pdfs_obras.get(ob_c, ""),
            fotos_obras.get(ob_c, ""),
            prefixo="c"
        )

        info = df_obras[df_obras["ID Obra"] == ob_c].iloc[0]
        reg_ob = df_diario[df_diario["ID Obra"] == ob_c].sort_values("Data_dt", ascending=False).copy()

        v_adj = float(info["Valor Adjudicado"])
        g_eq = float(reg_ob["Custo Elemento"].sum()) if not reg_ob.empty else 0.0
        g_vi = float(reg_ob["Custo Meio"].sum()) if not reg_ob.empty else 0.0
        g_mt = float(reg_ob["Custo Material"].sum()) if not reg_ob.empty else 0.0
        g_tot = g_eq + g_vi + g_mt
        v_sal = v_adj - g_tot

        m1, m2, m3 = st.columns(3)
        m1.metric("Valor Obra", f"{v_adj:,.2f} €")
        m2.metric("Total Gasto", f"{g_tot:,.2f} €")
        m3.metric("Saldo", f"{v_sal:,.2f} €")

        if v_adj > 0:
            st.progress(min(g_tot / v_adj, 1.0), text=f"Orçamento consumido: {(g_tot / v_adj) * 100:.1f}% | Estado: {info['Estado']}")
            if v_sal < 0:
                st.warning(f"⚠️ Orçamento ultrapassado em {abs(v_sal):,.2f} €")

        st.markdown("**Gastos por Categoria**")
        g1, g2, g3 = st.columns(3)
        g1.metric("👷 Colaboradores", f"{g_eq:,.2f} €")
        g2.metric("🚚 Viaturas", f"{g_vi:,.2f} €")
        g3.metric("📦 Materiais", f"{g_mt:,.2f} €")

        with st.expander("📄 Relatório de Contas desta Obra (PDF)", expanded=False):
            datas_validas = reg_ob["Data_dt"].dropna() if not reg_ob.empty else pd.Series(dtype="datetime64[ns]")
            dt_min_ob = datas_validas.min().date() if not datas_validas.empty else date.today().replace(day=1)
            dt_max_ob = max(date.today(), datas_validas.max().date()) if not datas_validas.empty else date.today()
            dc1, dc2 = st.columns(2)
            d_ini_c = dc1.date_input("De", value=dt_min_ob, key=f"c_ini_{ob_c}")
            d_fim_c = dc2.date_input("Até", value=dt_max_ob, key=f"c_fim_{ob_c}")

            if st.button(f"⚙️ Preparar Relatório da Obra {ob_c}", use_container_width=True):
                if not reg_ob.empty:
                    reg_pdf_ob = reg_ob[(reg_ob["Data_dt"] >= pd.Timestamp(d_ini_c)) & (reg_ob["Data_dt"] <= pd.Timestamp(d_fim_c))].sort_values("Data_dt", ascending=True)
                else:
                    reg_pdf_ob = reg_ob
                pdf_ob_bytes = gerar_pdf_contas_obra(cfg, info, reg_pdf_ob, d_ini=d_ini_c, d_fim=d_fim_c)
                st.download_button(
                    f"📥 Descarregar Relatório da Obra {ob_c} (PDF)",
                    pdf_ob_bytes,
                    file_name=f"Contas_Obra_{cfg['pdf_tag']}_{ob_c}_{d_ini_c}_{d_fim_c}.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )

        st.divider()
        st.markdown("**Todos os Gastos da Obra**")
        if not reg_ob.empty:
            reg_ob["Data"] = reg_ob["Data_dt"].dt.strftime("%d/%m/%Y").fillna(reg_ob["Data"])
            cols_g = ["Data", "Elemento", "Dias Elemento", "Dias Falta", "Custo Elemento", "Meio", "Dias Meio", "Custo Meio", "Material", "Qtd Material", "Custo Material", "Total do Dia", "Notas"]
            st.dataframe(
                reg_ob[cols_g].rename(columns={
                    "Elemento": "Colaborador", "Dias Elemento": "Dias Col.", "Dias Falta": "Faltas", "Custo Elemento": "€ Col.",
                    "Meio": "Viatura", "Dias Meio": "Dias Viat.", "Custo Meio": "€ Viat.",
                    "Qtd Material": "Qtd", "Custo Material": "€ Mat.", "Total do Dia": "Total (€)"
                }),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Sem gastos registados nesta obra.")

        st.divider()
        st.subheader("📊 Quadro Geral de Obras")
        st.dataframe(
            obras_ct[["ID Obra", "Nome da Obra", "Cliente", "Valor Adjudicado", "Total Gasto", "Saldo Restante", "Estado", "PDF", "Fotos"]].rename(
                columns={"Valor Adjudicado": "Valor Obra (€)", "Total Gasto": "Gasto (€)", "Saldo Restante": "Saldo (€)"}
            ),
            use_container_width=True,
            hide_index=True,
            column_config={"PDF": st.column_config.LinkColumn("PDF", display_text="📄 Abrir")}
        )
    else:
        st.info("Sem obras para os filtros selecionados.")

# ==========================================
# 4. TABELAS DE BASE DE DADOS E UTILIZADORES
# ==========================================
elif aba == "⚙️ Tabelas":
    with st.expander("🖼️ Configurar Imagem de Fundo Definitiva (Marca de Água)", expanded=bool(st.session_state["novo_fundo_url"])):
        fich_bg = st.file_uploader("Escolher imagem de fundo (LousaMaia)", type=["jpg", "jpeg", "png", "webp"], key="up_bg_app")
        if st.button("💾 Guardar Imagem Definitiva no Google Drive", use_container_width=True):
            if not fich_bg:
                st.error("Escolhe a imagem primeiro.")
            else:
                with st.spinner("A guardar imagem no Google Drive..."):
                    try:
                        mime_bg = fich_bg.type if getattr(fich_bg, "type", "") else "image/jpeg"
                        url_bg_drive = enviar_ficheiro_drive(url_ativa, f"FUNDO_APP_{fich_bg.name}", fich_bg.getvalue(), mime_type=mime_bg)
                        with open("fundo.jpg", "wb") as f_bg:
                            f_bg.write(fich_bg.getvalue())
                        obter_css_fundo.clear()
                        st.session_state["novo_fundo_url"] = url_bg_drive
                        st.session_state["aviso"] = "Imagem guardada no Drive! Cola a linha abaixo nos Secrets do Streamlit para nunca mais desaparecer."
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao enviar imagem para o Drive: {e}")

        if st.session_state["novo_fundo_url"]:
            st.info("Copia esta linha e cola em **Manage app > Settings > Secrets** (depois clica em **Save**):")
            st.code(f'fundo_url = "{st.session_state["novo_fundo_url"]}"', language="toml")

    st.subheader("📎 Associar PDF ou Fotografias a uma Obra")
    ids_todas = df_obras["ID Obra"].tolist()
    if ids_todas:
        obra_up = st.selectbox("Selecionar ID Obra", ids_todas, format_func=etiqueta_obra, key="up_obra")
        col_pdf, col_ft = st.columns(2)

        with col_pdf:
            fich_pdf = st.file_uploader("📄 Escolher PDF da Obra", type=["pdf"], key="up_file_pdf")
            if st.button("📤 Carregar PDF", use_container_width=True):
                if not fich_pdf:
                    st.error("Escolhe um ficheiro PDF primeiro.")
                else:
                    with st.spinner("A enviar PDF para o Google Drive..."):
                        try:
                            obras_edit = df_obras.copy()
                            nome_limpo = f"{obra_up}_{fich_pdf.name}"
                            url_drive = enviar_ficheiro_drive(url_ativa, nome_limpo, fich_pdf.getvalue(), mime_type="application/pdf")
                            obras_edit.loc[obras_edit["ID Obra"] == obra_up, "PDF"] = url_drive
                            recalcular_obras(url_ativa, obras_edit, df_diario)
                            ler_servidor.clear()
                            st.session_state["aviso"] = f"PDF associado com sucesso à obra {obra_up}!"
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao carregar PDF: {e}")

        with col_ft:
            fichs_fotos = st.file_uploader(
                "📷 Escolher Fotografias (podes selecionar várias)",
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=True,
                key="up_files_fotos"
            )
            if st.button("📷 Carregar Fotografias", use_container_width=True):
                if not fichs_fotos:
                    st.error("Escolhe pelo menos uma fotografia.")
                else:
                    with st.spinner("A enviar fotografias para o Google Drive..."):
                        try:
                            obras_edit = df_obras.copy()
                            qtd_env = adicionar_fotos_obra(obras_edit, obra_up, fichs_fotos, url_ativa)
                            recalcular_obras(url_ativa, obras_edit, df_diario)
                            ler_servidor.clear()
                            st.session_state["aviso"] = f"{qtd_env} fotografia(s) associada(s) à obra {obra_up}!"
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao carregar fotografias: {e}")

            fotos_atuais_ob = separar_links_fotos(fotos_obras.get(obra_up, ""))
            if fotos_atuais_ob:
                if st.button(f"🗑️ Limpar as {len(fotos_atuais_ob)} foto(s) desta obra", use_container_width=True):
                    obras_edit = df_obras.copy()
                    obras_edit.loc[obras_edit["ID Obra"] == obra_up, "Fotos"] = ""
                    recalcular_obras(url_ativa, obras_edit, df_diario)
                    ler_servidor.clear()
                    st.session_state["aviso"] = f"Fotografias removidas da obra {obra_up}!"
                    st.rerun()

    st.divider()

    st.subheader("🔐 Utilizadores e Acessos")
    st.caption("Perfil 'Admin' vê tudo | Perfil 'Diário' vê apenas o Registo Diário.")
    ed_u = st.data_editor(
        df_users,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Perfil": st.column_config.SelectboxColumn("Perfil", options=["Admin", "Diário"], default="Admin", required=True)
        }
    )

    st.subheader("🏢 Obras Atribuídas")
    st.caption("Estados disponíveis: Nova, Execução, Parcial, Concluída.")
    outros_est = [e for e in df_obras["Estado"].unique().tolist() if e and e not in ESTADOS_OBRA]
    cols_ed_o = ["ID Obra", "Nome da Obra", "Cliente", "Valor Adjudicado", "Estado", "PDF", "Fotos"]
    ed_o = st.data_editor(
        df_obras[cols_ed_o],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Estado": st.column_config.SelectboxColumn(
                "Estado",
                options=ESTADOS_OBRA + outros_est,
                default="Nova",
                required=True
            ),
            "PDF": st.column_config.LinkColumn("PDF", display_text="📄 Abrir PDF")
        }
    )

    st.subheader("👷 Colaboradores (Valor/Dia)")
    ed_e = st.data_editor(df_elem, num_rows="dynamic", use_container_width=True, hide_index=True)
    st.subheader("🚚 Viaturas / Meios (Valor/Dia)")
    ed_v = st.data_editor(df_meios, num_rows="dynamic", use_container_width=True, hide_index=True)
    st.subheader("📦 Materiais (Preço Unitário)")
    ed_m = st.data_editor(df_mat, num_rows="dynamic", use_container_width=True, hide_index=True)

    if st.button("💾 Guardar Todas as Tabelas", type="primary", use_container_width=True):
        with st.spinner("A guardar alterações..."):
            guardadas = []
            if not df_igual(ed_o, df_obras[cols_ed_o]):
                ed_o_save = ed_o.copy()
                ed_o_save["ID Obra"] = ed_o_save["ID Obra"].fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
                ed_o_save["Valor Adjudicado"] = pd.to_numeric(ed_o_save["Valor Adjudicado"], errors="coerce").fillna(0.0)
                ed_o_save["Total Gasto"] = 0.0
                ed_o_save["Saldo Restante"] = ed_o_save["Valor Adjudicado"]
                recalcular_obras(url_ativa, ed_o_save, df_diario)
                guardadas.append("Obras")
            if not df_igual(ed_e, df_elem) or not df_igual(ed_u, df_users):
                guardar_elementos_e_users(url_ativa, ed_e, ed_u)
                guardadas.append("Colaboradores/Acessos")
            if not df_igual(ed_v, df_meios):
                guardar_aba(url_ativa, "Meios", ed_v)
                guardadas.append("Viaturas")
            if not df_igual(ed_m, df_mat):
                guardar_aba(url_ativa, "Materiais", ed_m)
                guardadas.append("Materiais")

            if guardadas:
                ler_servidor.clear()
                st.session_state["aviso"] = f"Guardado: {', '.join(guardadas)}!"
            else:
                st.session_state["aviso"] = "Sem alterações para guardar."
            st.rerun()
