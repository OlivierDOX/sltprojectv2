import streamlit as st
import pandas as pd
import io
from itertools import combinations_with_replacement
from pulp import LpProblem, LpVariable, LpMinimize, lpSum, PULP_CBC_CMD

st.set_page_config(layout="wide")
st.markdown("<style> .block-container { max-width: 60%; } </style>", unsafe_allow_html=True)

st.title("Cálculo de Planos de Corte de Bobinas")

# Entradas do usuário
limite_inferior = st.text_input("Limite Inferior (%)", "90")
limite_superior = st.text_input("Limite Superior (%)", "130")

# Largura do Slitter
larguras_bobina = [st.number_input("Largura utilizada no Slitter", min_value=1, value=1196, step=1)]

# Peso da bobina 
peso_bobina = st.number_input("Peso da Bobina", min_value=1, value=23500, step=1)

def input_lotes_pesos():
    st.sidebar.subheader("Definir Lotes e Pesos")
    num_lotes = st.sidebar.number_input("Número de lotes", min_value=0, max_value=50, value=0, step=1)
    lotes_pesos = {}
    
    for i in range(1, num_lotes + 1):
        lote = st.sidebar.text_input(f"Nome do lote {i}", value="")
        peso = st.sidebar.number_input(f"Peso do {lote}", min_value=0.01, value=0.01, step=0.01)
        lotes_pesos[lote] = peso
    
    return lotes_pesos

lotes_pesos = None

try:
    limite_inferior = float(limite_inferior) / 100
    limite_superior = float(limite_superior) / 100
except ValueError:
    st.error("Os limites inferior e superior devem ser números válidos em porcentagem.")
    st.stop()



# Definições dos produtos
produtos = {
    "Perfil UDC Enrijecido 50x25x10x2,00x6000mm": 105,
    "Perfil UDC Enrijecido 75x40x15x2,00x6000mm": 170,
    "Perfil UDC Enrijecido 100x40x15x2,00x6000mm": 197,
    "Perfil UDC Enrijecido 100x50x17x2,00x6000mm": 219,
    "Perfil UDC Enrijecido 127x50x17x2,00x6000mm": 244,
    "Perfil UDC Enrijecido 150x50x17x2,00x6000mm": 264,
    "Perfil UDC Enrijecido 150x60x20x2,00x6000mm": 295,
    "Perfil UDC Enrijecido 200x75x25x2,00x6000mm": 375,
    "Perfil UDC Simples 50x25x2,00x6000mm": 93,
    "Perfil UDC Simples 68x30x2,00x6000mm": 122,
    "Perfil UDC Simples 92x30x2,00x6000mm": 148,
    "Perfil UDC Simples 100x40x2,00x6000mm": 173,
    "Perfil UDC Simples 100x50x2,00x6000mm": 192,
    "Perfil UDC Simples 127x50x2,00x6000mm": 217,
    "Perfil UDC Simples 150x50x2,00x6000mm": 242,
    "Perfil UDC Simples 200x75x2,00x6000mm": 343
}

larguras_slitters = list(produtos.values())

# Entrada de demandas como seleção múltipla
# Entrada de demandas com barra de rolagem dentro do expander
with st.expander("Selecione os produtos e defina os pesos"):
    df_produtos = pd.DataFrame({
        "Produto": list(produtos.keys()),
        "Selecionado": [False] * len(produtos),
        "Peso (kg)": [0] * len(produtos)  # Agora o nome da coluna é "Peso"
    })

    # Editor de dados com barra de rolagem automática
    df_editado = st.data_editor(
        df_produtos,
        num_rows="fixed",  # Mantém número fixo de linhas
        use_container_width=True,
        hide_index=True
    )

    # Filtrando apenas os produtos selecionados
    produtos_selecionados = df_editado[df_editado["Selecionado"] == True]

# Convertendo os produtos selecionados para o DataFrame final
demand = produtos_selecionados[["Produto", "Peso (kg)"]].copy()  # Agora acessamos corretamente "Peso"
demand["Largura"] = demand["Produto"].map(produtos)  # Adiciona largura com base no dicionário original

# Exibir a demanda selecionada
st.write("Demanda Selecionada:")
st.dataframe(demand, use_container_width=True)



def encontra_combinacoes_possiveis(larguras_slitters, largura_bobina):
    combinacoes = []
    for n in range(1, largura_bobina // min(larguras_slitters) + 1):
        for combinacao in combinations_with_replacement(larguras_slitters, n):
            if sum(combinacao) == largura_bobina:
                combinacoes.append(combinacao)
    return combinacoes

def resolver_problema_corte(larguras_slitters, largura_bobina, _bobina, demand):
    proporcao = _bobina / largura_bobina

    # Encontrar combinações possíveis
    combinacoes = encontra_combinacoes_possiveis(larguras_slitters, largura_bobina)

    if not combinacoes:
        return None

    # Filtrar combinações para conter apenas larguras presentes na demanda
    larguras_validas = set(demand["Largura"])
    combinacoes_filtradas = [
        comb for comb in combinacoes if set(comb).issubset(larguras_validas)
    ]

    if not combinacoes_filtradas:
        return None

    problema = LpProblem("Problema_de_Corte", LpMinimize)
    x = LpVariable.dicts("Plano", range(len(combinacoes_filtradas)), lowBound=0, cat="Integer")

    problema += lpSum(x[i] for i in range(len(combinacoes_filtradas))), "Minimizar_Bobinas"

    for _, row in demand.iterrows():
        largura = row["Largura"]
        peso_necessario = row["Peso (kg)"]

        problema += (
            lpSum(
                x[i] * combinacao.count(largura) * proporcao * largura
                for i, combinacao in enumerate(combinacoes_filtradas)
            ) >= peso_necessario * limite_inferior,
            f"Atender_Minima_{largura}",
        )
        problema += (
            lpSum(
                x[i] * combinacao.count(largura) * proporcao * largura
                for i, combinacao in enumerate(combinacoes_filtradas)
            ) <= peso_necessario * limite_superior,
            f"Atender_Maxima_{largura}",
        )

    problema.solve(PULP_CBC_CMD(msg=False))

    if problema.status != 1:
        return None

    resultado = []
    for i, combinacao in enumerate(combinacoes_filtradas):
        if x[i].varValue > 0:
            pesos_por_largura = [largura * proporcao for largura in combinacao]
            combinacao_com_pesos = [
                f"{largura} | {round(peso, 0)} kg"
                for largura, peso in zip(combinacao, pesos_por_largura)
            ]

            puxada = 2 if any(peso > 5000 for peso in pesos_por_largura) else 1

            resultado.append(
                {
                    "Plano de Corte": combinacao_com_pesos,
                    "Quantidade": int(x[i].varValue),
                    "Largura Total": sum(combinacao),
                    "Puxada": puxada,
                }
            )

    return pd.DataFrame(resultado)



def gerar_tabela_final(resultado, demand, proporcao):
    # Inicializa pesos_totais com todas as larguras e produtos do demand
    pesos_totais = {row["Largura"]: 0 for _, row in demand.iterrows()}

    for _, linha in resultado.iterrows():
        combinacao = linha["Plano de Corte"]
        quantidade = linha["Quantidade"]

        for item in combinacao:
            largura = int(str(item).split('|')[0].strip())

            # Se a largura não estiver em pesos_totais (pode ter sido adicionada no resultado e não no demand), inicializa
            if largura not in pesos_totais:
                pesos_totais[largura] = 0

            pesos_totais[largura] += quantidade * largura * proporcao

    tabela_final = []

    # Garante que a tabela final contenha apenas os produtos do demand
    for _, row in demand.iterrows():
        produto = row["Produto"]
        largura = row["Largura"]
        peso_planejado = row["Peso (kg)"]
        peso_total = pesos_totais.get(largura, 0)
        percentual_atendido = (peso_total / peso_planejado * 100) if peso_planejado > 0 else 0

        tabela_final.append({
            "Produto": produto,
            "Largura (mm)": largura,
            "Demanda Planejada (kg)": peso_planejado,
            "Peso Total (kg)": round(peso_total, 0),
            "Atendimento (%)": round(percentual_atendido, 1),
        })

    # Cálculo dos totais
    total_peso_planejado = demand["Peso (kg)"].sum()
    total_peso_atendido = sum(pesos_totais.values())

    totais = {
        "Produto": "Total",
        "Largura (mm)": "",
        "Demanda Planejada (kg)": total_peso_planejado,
        "Peso Total (kg)": round(total_peso_atendido, 0),
        "Atendimento (%)": round((total_peso_atendido / total_peso_planejado) * 100, 1) if total_peso_planejado > 0 else 0,
    }

    tabela_final.append(totais)

    # Criando DataFrame final
    df_final = pd.DataFrame(tabela_final)

    # Formatação para manter valores numéricos legíveis com separadores
    df_final = df_final.applymap(lambda x: f"{int(x):,}".replace(",", ".") if isinstance(x, (int, float)) and x == round(x, 0) else (f"{x:,}".replace(",", ".") if isinstance(x, (int, float)) else x))

    return df_final




def exibir_dataframe(df):
    st.dataframe(df, use_container_width=True, height=(len(df) * 35 + 50), hide_index=True)


def transformar_plano_de_corte(planos_de_corte):
    processed_data = []
    for index, plano in enumerate(planos_de_corte, start=1):
        row = [index]  # Iniciando com o identificador do plano de corte
        for item in plano:
            item = item.strip("[]")  # Removendo colchetes extras se houver
            largura, peso = item.split(" | ")
            peso = peso.replace(" kg", "")  # Removendo unidade de peso
            row.extend([int(largura), int(float(peso))])  # Convertendo para inteiros
        processed_data.append(row)

    # Determinando o número máximo de colunas
    max_columns = max(len(row) for row in processed_data)

    # Padronizando o tamanho das linhas para que todas tenham o mesmo número de colunas
    for row in processed_data:
        while len(row) < max_columns:
            row.append(None)  # Preenchendo com None

    # Criando os nomes das colunas dinamicamente
    column_names = ["Plano de Corte"]
    for i in range(1, (max_columns - 1) // 2 + 1):
        column_names.extend([f"Largura {i}", f"Peso {i}"])

    # Criando o DataFrame final
    df_final = pd.DataFrame(processed_data, columns=column_names)
    return df_final

if "calculos_feitos" not in st.session_state:
    st.session_state.calculos_feitos = False

if "melhor_resultado" not in st.session_state:
    st.session_state.melhor_resultado = None

if "melhor_largura" not in st.session_state:
    st.session_state.melhor_largura = None

if "tabela_final" not in st.session_state:
    st.session_state.tabela_final = None

if st.button("Calcular"):
    if demand.empty:
        st.error("Nenhuma demanda selecionada. Selecione ao menos um produto.")
    else:
        melhor_resultado = None
        melhor_largura = None

        for largura_bobina in larguras_bobina:
            resultado = resolver_problema_corte(larguras_slitters, largura_bobina, peso_bobina, demand)

            if resultado is not None:
                if melhor_resultado is None or resultado["Quantidade"].sum() < melhor_resultado["Quantidade"].sum():
                    melhor_resultado = resultado
                    melhor_largura = largura_bobina

        if melhor_resultado is not None:
            proporcao = peso_bobina / melhor_largura
            tabela_final = gerar_tabela_final(melhor_resultado, demand, proporcao)

            st.session_state.melhor_resultado = melhor_resultado
            st.session_state.melhor_largura = melhor_largura
            st.session_state.tabela_final = tabela_final
            st.session_state.calculos_feitos = True

            st.subheader("Melhor largura de bobina")
            st.write(f"{melhor_largura} mm")

            st.subheader("Resultado dos Planos de Corte")
            st.dataframe(melhor_resultado)

            st.subheader("Tabela Final")
            st.dataframe(tabela_final)

if st.session_state.calculos_feitos:
    lotes_pesos = input_lotes_pesos()
    
    if st.button("Gerar Arquivos") and lotes_pesos:
        melhor_resultado = st.session_state.melhor_resultado
        melhor_largura = st.session_state.melhor_largura
        tabela_final = st.session_state.tabela_final
        
        planos_de_corte = melhor_resultado["Plano de Corte"].dropna().apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x).tolist()
        colunas_adicionais = melhor_resultado[["Quantidade", "Largura Total", "Puxada"]]

        df_resultado = transformar_plano_de_corte(planos_de_corte)
        df_resultado = pd.concat([df_resultado, colunas_adicionais.reset_index(drop=True)], axis=1)

        df_planejamento_final = df_resultado.copy()
        
        # Passo 1: Duplicação/triplicação das linhas com base na coluna "Quantidade"
        # 1 - Duplicação baseada em "Quantidade" (primeira expansão)
        df_planejamento_final = df_planejamento_final.loc[df_planejamento_final.index.repeat(df_planejamento_final["Quantidade"].fillna(1).astype(int))].reset_index(drop=True)
        
        # 2 - Adicionar colunas "Numero do Lote" e "Peso do Lote"
        df_planejamento_final["Numero do Lote"] = list(lotes_pesos.keys())[:len(df_planejamento_final)]
        df_planejamento_final["Peso do Lote"] = df_planejamento_final["Numero do Lote"].map(lotes_pesos)
        
        # 3 - Segunda duplicação baseada em "Puxada" (após adicionar lotes)
        df_planejamento_final = df_planejamento_final.loc[df_planejamento_final.index.repeat(df_planejamento_final["Puxada"].fillna(1).astype(int))].reset_index(drop=True)
        
        # 4 - Ajuste de peso para todas as colunas que contenham "Peso"
        for col in df_planejamento_final.columns:
            if "Peso" in col and col != "Peso do Lote":  # Evita alterar a coluna "Peso do Lote" diretamente
                largura_col = col.replace("Peso", "Largura")
                if largura_col in df_planejamento_final.columns:
                    df_planejamento_final[col] = round((df_planejamento_final[largura_col] / 1200) * (df_planejamento_final["Peso do Lote"]) / df_planejamento_final["Puxada"],2)


        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_resultado.to_excel(writer, sheet_name="Transformação Feita", index=False)
            tabela_final.to_excel(writer, sheet_name="Tabela Final", index=False)
            df_planejamento_final.to_excel(writer, sheet_name="Planejamento Final", index=False)
        output.seek(0)

        df_planejamento_final_to_tabela_final = df_planejamento_final
        # 1 - Remover duplicatas
        df_planejamento_final = df_planejamento_final.drop_duplicates().reset_index(drop=True)
        
        # 2 - Criar lista para armazenar os resultados
        resultado_lista = []

        # 3 - Criar dicionário para somar os pesos por largura
        soma_pesos_por_largura = {}

        # 4 - Percorrer o dataframe e concatenar as colunas conforme a lógica
        tipo_corte = "Plano de corte"
        for index, row in df_planejamento_final.iterrows():
            linha_texto = f"{tipo_corte} {index + 1}: Lote - {row['Numero do Lote']} | Quantidade de puxadas = {row['Puxada']}"
            
            colunas_largura_peso = [col for col in df_planejamento_final.columns if "Largura" in col or "Peso" in col]
            colunas_largura_peso.sort()  # Ordenar para garantir a sequência correta
            
            for i in range(1, len(colunas_largura_peso) // 2 + 1):
                largura = row.get(f"Largura {i}", "")
                peso = row.get(f"Peso {i}", "")
                if pd.notna(largura) and pd.notna(peso) and largura != "" and peso != "":
                    linha_texto += f" | {largura}-{peso}"
                    soma_pesos_por_largura[largura] = soma_pesos_por_largura.get(largura, 0) + float(peso)
            
            resultado_lista.append(linha_texto)
        
        # 5 - Criar um novo dataframe com "largura" e "peso"
        largura_peso_lista = []
        for col in df_planejamento_final_to_tabela_final.columns:
            if "Largura" in col:
                peso_col = col.replace("Largura", "Peso")
                if peso_col in df_planejamento_final_to_tabela_final.columns:
                    for _, row in df_planejamento_final_to_tabela_final.iterrows():
                        largura = row[col]
                        peso = row[peso_col]
                        if pd.notna(largura) and pd.notna(peso):
                            largura_peso_lista.append((float(largura), float(peso)))
        
        # Criar dataframe consolidado
        df_largura_peso = pd.DataFrame(largura_peso_lista, columns=["largura", "peso"])
        df_largura_peso = df_largura_peso.groupby("largura", as_index=False).sum()
        
        # 6 - Converter "Largura (mm)" para float antes da fusão
        tabela_final["Largura (mm)"] = tabela_final["Largura (mm)"].astype(float)
        
        # 7 - Atualizar "Peso Total (kg)" na tabela_final com os valores de df_largura_peso
        tabela_final = tabela_final.merge(df_largura_peso, left_on="Largura (mm)", right_on="largura", how="left").drop(columns=["largura"])
        tabela_final["Peso Total (kg)"] = tabela_final["peso"].fillna(tabela_final["Peso Total (kg)"])
        tabela_final = tabela_final.drop(columns=["peso"])
        
        # 8 - Converter colunas numéricas para float
        tabela_final["Demanda Planejada (kg)"] = tabela_final["Demanda Planejada (kg)"].astype(float)
        tabela_final["Peso Total (kg)"] = tabela_final["Peso Total (kg)"].astype(float)
        
        # 9 - Atualizar a coluna "Atendimento (%)"
        tabela_final["Atendimento (%)"] = (tabela_final["Demanda Planejada (kg)"] / tabela_final["Peso Total (kg)"]) * 100
        # Arredondar para duas casas decimais
        tabela_final["Atendimento (%)"] = tabela_final["Atendimento (%)"].round(2)
        
        # 10 - Atualizar a última linha (Total) da tabela_final
        tabela_final.loc[tabela_final.index[-1], "Demanda Planejada (kg)"] = tabela_final["Demanda Planejada (kg)"].sum()
        tabela_final.loc[tabela_final.index[-1], "Peso Total (kg)"] = tabela_final["Peso Total (kg)"].sum()
        tabela_final.loc[tabela_final.index[-1], "Atendimento (%)"] = (tabela_final.loc[tabela_final.index[-1], "Demanda Planejada (kg)"] / tabela_final.loc[tabela_final.index[-1], "Peso Total (kg)"]) * 100
        tabela_final.loc[tabela_final.index[-1], "Atendimento (%)"] = tabela_final.loc[tabela_final.index[-1], "Atendimento (%)"].round(2)
        
        # 4 - Criar o arquivo TXT
        resultado_txt = "\n".join(resultado_lista)
        
        # 5 - Adicionar os resultados da tabela final
        resultado_txt += "\n\n" + tabela_final.to_string(index=False)
        
        # 6 - Escrever no arquivo de saída
        with open("resultado_planejamento.txt", "w", encoding="utf-8") as file:
            file.write(resultado_txt)
        
        # Código para download do arquivo no Streamlit
        st.download_button(
            label="Baixar Resultado (TXT)",
            data=resultado_txt,
            file_name="resultado_planejamento.txt",
            mime="text/plain"
        )

        st.download_button(
            label="Baixar Resultado (Excel)",
            data=output,
            file_name="resultado_corte_transformado.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )



  
