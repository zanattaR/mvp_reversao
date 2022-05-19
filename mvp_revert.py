import streamlit as st
import pandas as pd
import numpy as np
from pandas.io.json import json_normalize
import pymongo
import datetime
from pymongo import MongoClient
import base64
from io import BytesIO
import xlsxwriter


# Função para transformar df em excel
def to_excel(df):
	output = BytesIO()
	writer = pd.ExcelWriter(output, engine='xlsxwriter')
	df.to_excel(writer, sheet_name='Planilha1',index=False)
	writer.save()
	processed_data = output.getvalue()
	return processed_data
	
# Função para gerar link de download
def get_table_download_link(df):
	val = to_excel(df)
	b64 = base64.b64encode(val)
	return f'<a href="data:application/octet-stream;base64,{b64.decode()}" download="extract.xlsx">Download</a>'


st.title("Planilha de Reversão")
st.markdown('''##### Esta aplicação tem como objetivo coletar os dados de reviews e respostas do banco de dados e criar um arquivo exportável para estudar os casos de reversão de nota após uma resposta de Pulse Solution''')
init = str(st.date_input('Data Inicial'))
init_y = int(init[0:4])
init_m = int(init[5:7])
init_d = int(init[8:])

end = str(st.date_input('Data Final'))
end_y = int(end[0:4])
end_m = int(end[5:7])
end_d = int(end[8:])


# Seleção de datas e app
start = datetime.datetime(init_y,init_m,init_d)
end = datetime.datetime(end_y,end_m,end_d)

app_name = st.text_input('insira o app_id. Ex: com.globo.globotv')

btn_predict = st.button('Gerar Planilha')


if btn_predict:

	# Conectando banco
	acesso = """mongodb://thiago.montenegro:yRhyNTj-PRO6VKnsmvIYkzwav@mongo.stg.rankmylan.com:27017/
	?authSource=admin&authMechanism=SCRAM-SHA-256"""
	client = MongoClient(acesso)

	# Database
	db = client['ReviewsGplay']

	# Collection
	collection = db['reviews']

	# Query filtrando app e data
	reviews = collection.find({'appId':app_name, 'date':{'$gte':start, '$lt':end}})

	# Trasnformando resultado da query em pandas dataframe
	df=pd.DataFrame(reviews)

	# Selecionando colunas ncessárias
	df_clean = df[['_id', 'id', 'appId','history','userName','thumbsUp','lang']]

	# Selecionando reviews com 3 ou mais interações
	mask = (df_clean['history'].str.len() >= 3)
	df_filter = df_clean[mask]
	df_filter.reset_index(drop=True, inplace=True)

	# Normalizando coluna history no dataframe
	exploded = df_filter.explode('history')
	df_exp = pd.concat([exploded[["_id","userName","thumbsUp","lang"]].reset_index(drop=True),pd.json_normalize(exploded["history"])], axis=1)


	# Formatando datas
	df_exp['date'] = df_exp['date'].dt.date
	df_exp['replyDate'] = df_exp['replyDate'].dt.date

	init_scores = []
	ids = []
	final_scores = []

	for name, group in df_exp.groupby('_id'):
	    
	    # Coletando valores iniciais do review
	    user = group[group['type'] == 'user']
	    
	    init_score = user.iloc[0,1:13]
	    names = name
	    
	    init_scores.append(init_score)
	    ids.append(names)
	    
	    # Coletando valores finais do review
	    final_score = user.iloc[-1, 0:13]
	    final_scores.append(final_score)

	# Dataframe dos valores iniciais do review
	df_init_scores = pd.DataFrame(init_scores)
	df_init_scores.rename(columns = {'date':'Data do review','score':'Rating Inicial','version':'Versão_antes',
	                                 'sentiment':'Sentiment_antes','category':'Category_antes',
	                                 'subcategory':'Subcategory_antes'}, inplace = True)
	df_init_scores.insert(0, '_id', ids)

	# Dataframe dos valores finais do review
	df_final_scores = pd.DataFrame(final_scores)
	df_final_scores.drop(['type','title','text'], axis=1, inplace=True)
	df_final_scores.rename(columns = {'date':'Data reversão','score':'Rating Final','version':'Versão_depois',
	                                 'sentiment':'Sentiment_depois','category':'Category_depois',
	                                 'subcategory':'Subcategory_depois'}, inplace = True)

	# Juntando dataframes
	df_reviews = df_init_scores.merge(df_final_scores, on='_id')
	df_reviews.rename(columns = {'lang_x':'lang','userName_x':'userName','thumbsUp_x':'thumbsUp'}, inplace = True)
	df_reviews.drop(['lang_y','userName_y', 'thumbsUp_y'], axis=1, inplace=True)

	df_dev = df_exp[df_exp['type'] == 'dev']

	replies = []

	for name, group in df_dev.groupby('_id'):
	    
	    reply = group.iloc[-1,[0,13,14]]
	    replies.append(reply)

	df_replies = pd.DataFrame(replies)

	# Juntando reviews e respostas
	df_final = df_reviews.merge(df_replies, how='inner', on='_id')

	df_final['app'] = app_name
	df_final['Mudança de Rating'] = df_final['Rating Final'] - df_final['Rating Inicial']
	df_final['Mudou Versão'] = np.where(df_final['Versão_antes'] != df_final['Versão_depois'], 'Sim','Não')
	df_final['Tempo de reversão (review)'] = (df_final['Data reversão'] - df_final['Data do review']).dt.days
	df_final['Tempo de reversão (reply)'] = (df_final['Data reversão'] - df_final['replyDate']).dt.days
	df_final['Reversão Status'] = np.where(df_final['Mudança de Rating'] > 0, "Positiva",
		np.where(df_final['Mudança de Rating'] < 0, "Negativa", "Neutra"))

	cols = ['app','_id','userName', 'thumbsUp', 'lang','Rating Inicial','Rating Final','Mudança de Rating','Reversão Status',
        'Data do review','replyDate','Data reversão','Tempo de reversão (review)','Tempo de reversão (reply)','text',
        'replyText','Versão_antes','Versão_depois','Mudou Versão','Sentiment_antes','Category_antes','Subcategory_antes',
        'Sentiment_depois','Category_depois', 'Subcategory_depois']

	df_final = df_final[cols]

	st.write(df_final)
	st.write('Clique em Download para baixar o arquivo')
	st.markdown(get_table_download_link(df_final), unsafe_allow_html=True)