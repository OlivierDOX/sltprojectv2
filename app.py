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

try:
    limite_inferior = float(limite_inferior) / 100
    limite_superior = float(limite_superior) / 100
except ValueError:
    st.error("Os limites inferior e superior devem ser números válidos em porcentagem.")
    st.stop()

# Largura da bobina fixa
larguras_bobina = [1192]
peso_bobina = 17715

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
        "Peso": [0] * len(produtos)  # Agora o nome da coluna é "Peso"
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
demand = produtos_selecionados[["Produto", "Peso"]].copy()  # Agora acessamos corretamente "Peso"
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

def resolver_problema_corte(larguras_slitters, largura_bobina, peso_bobina, demand):
    proporcao = peso_bobina / largura_bobina

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
        peso_necessario = row["Peso"]

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
        peso_planejado = row["Peso"]
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
    total_peso_planejado = demand["Peso"].sum()
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

# Verificar se o botão foi pressionado
if st.button("Calcular"):
    melhor_resultado = gerar_melhor_resultado()  # Simulação da geração do resultado
    if melhor_resultado is not None:
        tabela_final = gerar_tabela_final(melhor_resultado)  # Simulação da geração da tabela final
        
        # Extraindo a coluna "Plano de Corte" e convertendo corretamente
        planos_de_corte = melhor_resultado["Plano de Corte"].dropna().apply(lambda x: ast.literal_eval(x) if isinstance(x, str) else x).tolist()
        
        # Extraindo as colunas adicionais
        colunas_adicionais = melhor_resultado[["Quantidade", "Largura Total", "Puxada"]]

        # Transformando os dados
        df_resultado = transformar_plano_de_corte(planos_de_corte)

        # Adicionando as colunas extras ao DataFrame transformado
        df_resultado = pd.concat([df_resultado, colunas_adicionais.reset_index(drop=True)], axis=1)

        # Criar um arquivo Excel para download
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            df_resultado.to_excel(writer, sheet_name="Transformação Feita", index=False)
            tabela_final.to_excel(writer, sheet_name="Tabela Final", index=False)
        output.seek(0)

        # Oferecer o arquivo Excel para download
        st.download_button(
            label="Baixar Resultado (Excel)",
            data=output,
            file_name="resultado_corte_transformado.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.error("Nenhuma solução encontrada!")
