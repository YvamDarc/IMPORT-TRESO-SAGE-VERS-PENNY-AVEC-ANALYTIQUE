import hashlib,json
import streamlit as st
import pandas as pd
from fusion import reconcile,enrich,csv_bytes,ConversionError
st.set_page_config(page_title='FEC enrichi avec analytique',page_icon='📑',layout='wide')
st.title('Ton FEC complet + l’analytique')
st.write('Toutes les colonnes d’origine sont conservées : dates, lettrage, références, libellés et montants. On ajoute uniquement les informations du PNM.')
with st.sidebar:
    ff=st.file_uploader('FEC initial',type=['txt','csv','fec'])
    pp=st.file_uploader('PNM avec analytique',type=['pnm','txt'])
    enc=st.selectbox('Encodage PNM',['cp850','cp1252','utf-8-sig'])
    family=st.text_input('Nom de la famille analytique','Plan 1')
    mode=st.radio('Organisation des lignes',['Une ligne par ligne du FEC','Une ligne par catégorie analytique'])
    st.caption('1 ligne d’en-tête dans chaque fichier. Aucun envoi à Pennylane.')
if not ff or not pp:st.stop()
raw=ff.getvalue();pnm=pp.getvalue();key=hashlib.sha256(raw+pnm+enc.encode()).hexdigest()
try:
    if st.session_state.get('source_key')!=key:
        with st.spinner('Rapprochement des deux fichiers…'):
            result=reconcile(raw,pnm,enc)
        st.session_state['result']=result;st.session_state['source_key']=key
    result=st.session_state['result']
    ek=(key,family,mode)
    if st.session_state.get('export_key')!=ek:
        rows,fields,report=enrich(raw,result,family,'original' if mode.startswith('Une ligne par ligne') else 'categories')
        st.session_state['export']=(rows,fields,report,csv_bytes(rows,fields));st.session_state['export_key']=ek
    rows,fields,report,content=st.session_state['export']
except (ConversionError,ValueError) as e:st.error(str(e));st.stop()
a,b,c,d=st.columns(4)
a.metric('Lignes du FEC',report['source_rows']);b.metric('Cellules FEC modifiées',report['modified_cells']);c.metric('Lignes avec lettrage conservé',report['lettered_rows']);d.metric('À rapprocher',report['unresolved'])
st.success(f"Les {report['original_columns']} colonnes d’origine sont conservées à l’identique, dont EcritureLet et DateLet lorsqu’elles sont présentes.")
if report['unresolved']:st.warning(f"{report['unresolved']} correspondances sont ambiguës. Les ajouts concernés restent vides ; les candidats et leur analytique sont conservés dans CandidatsPNM, dans le même fichier. Aucun choix au hasard.")
if report['analytic_discrepancies']:st.caption(f"{report['analytic_discrepancies']} écarts analytiques source sont signalés. Cette version ne normalise et ne corrige aucun montant.")
if mode.startswith('Une ligne par ligne'):
    st.caption('Plusieurs catégories sur une ligne : valeurs séparées par |, dans le même ordre pour famille, catégorie, poids et montant. Pour mapper une seule catégorie par ligne, choisir le second mode.')
else:st.warning('Les lignes multi-catégories répètent les colonnes du FEC. Mapper IdentifiantLigneSource pour regrouper les répétitions ; ne pas sommer les montants sans dédupliquer cet identifiant.')
with st.expander('Voir les colonnes conservées et ajoutées'):
    st.write('**Colonnes FEC :** '+', '.join(fields[:report['original_columns']]))
    st.write('**Colonnes ajoutées :** '+', '.join(fields[report['original_columns']:]))
st.subheader('Aperçu')
search=st.text_input('Rechercher une facture, un compte, une date AAAAMMJJ ou un libellé')
view=[r for r in rows if search.casefold() in ' '.join(str(v) for k,v in r.items() if k not in ['DetailAnalytiquePNM','CandidatsPNM']).casefold()] if search else rows
st.dataframe(pd.DataFrame(view[:300],columns=fields),hide_index=True,width='stretch')
st.caption(f'Aperçu limité à 300 lignes. Le téléchargement contient toutes les {report["output_rows"]} lignes, toutes les colonnes. 1 ligne d’en-tête ; UTF-8 ; séparateur point-virgule.')
st.download_button('Télécharger le FEC enrichi — un seul CSV',content,'FEC_ENRICHI_ANALYTIQUE.csv','text/csv',type='primary')
st.caption('Le lettrage est conservé dans le fichier. Sa reprise effective dans Pennylane dépend du parcours et du mapping choisis. Le fichier enrichi n’est pas un FEC réglementaire : conserver le FEC initial.')
